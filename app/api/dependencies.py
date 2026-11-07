"""Dependency injection providers for FastAPI endpoints."""
from __future__ import annotations

import asyncio
from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db, require_session
from app.repositories.pqrsd_repository import PqrsdRepository
from app.services.pqrsd_service import PqrsdService
from app.services.rag_service import RAGService


def get_rag_service(request: Request) -> RAGService:
    """Provide the application's shared RAG service instance."""
    rag: RAGService | None = getattr(
        request.app.state, "rag_service", getattr(request.app.state, "rag", None)
    )
    if rag is None:
        rag = RAGService()
        request.app.state.rag = rag
        request.app.state.rag_service = rag
    return rag


def get_semaphore(request: Request) -> asyncio.Semaphore:
    """Provide the global semaphore enforcing concurrency limits for generation."""
    semaphore: asyncio.Semaphore | None = getattr(
        request.app.state, "semaphore", None
    )
    if semaphore is None:
        semaphore = asyncio.Semaphore(settings.LLM_CONCURRENCY_LIMIT)
        request.app.state.semaphore = semaphore
    return semaphore


def get_db_session() -> Iterator[Session | None]:
    """Yield a database session or None if relational storage is disabled."""
    yield from get_db()


def get_pqrsd_repo(
    session: Session | None = Depends(get_db_session),
) -> PqrsdRepository:
    """Provide a validated PqrsdRepository instance."""
    valid_session = require_session(session)
    return PqrsdRepository(valid_session)


def get_pqrsd_service(
    repo: PqrsdRepository = Depends(get_pqrsd_repo),
) -> PqrsdService:
    """Provide a PqrsdService instance bound to the repository."""
    return PqrsdService(repo)


__all__ = [
    "get_db_session",
    "get_pqrsd_repo",
    "get_pqrsd_service",
    "get_rag_service",
    "get_semaphore",
]
