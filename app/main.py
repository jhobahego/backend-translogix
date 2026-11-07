"""FastAPI application entrypoint for asistencia-cliente-local.

Exposes the local vector RAG over Ollama and optional PQRSD case endpoints.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from app.api.dependencies import get_rag_service
from app.api.v1.endpoints.health import health as health_handler
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.exceptions import database_unreachable_handler, register_exception_handlers
from app.schemas.rag import AskRequest, AskResponse, SourceModel
from app.services.rag_service import RAGService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create the vector RAG and generation semaphore once per process."""
    rag_service = RAGService()
    app.state.rag = rag_service
    app.state.rag_service = rag_service
    app.state.semaphore = asyncio.Semaphore(settings.LLM_CONCURRENCY_LIMIT)
    yield


app = FastAPI(
    title="asistencia-cliente-local",
    description="Local vector RAG and PQRSD customer support API",
    version="1.0.0",
    lifespan=lifespan,
)

# Register global exception handlers
register_exception_handlers(app)


@app.exception_handler(DBAPIError)
async def _database_unreachable(request: Request, exc: DBAPIError) -> JSONResponse:
    """A configured but unreachable database degrades to 503, never 500."""
    return await database_unreachable_handler(request, exc)


# Root health check endpoint
@app.get("/health", tags=["health"], summary="Liveness probe")
def health(
    rag: Annotated[RAGService, Depends(get_rag_service)],
) -> dict[str, Any]:
    """Liveness probe; never calls Ollama."""
    return health_handler(rag)


# Mount versioned API router
app.include_router(api_v1_router)

__all__ = [
    "AskRequest",
    "AskResponse",
    "SourceModel",
    "app",
    "health",
    "lifespan",
]
