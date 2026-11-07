"""Health check and liveness probe endpoint."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.api.dependencies import get_rag_service
from app.services.rag_service import RAGService

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
def health(
    rag: Annotated[RAGService, Depends(get_rag_service)],
) -> dict[str, Any]:
    """Liveness probe; never calls Ollama."""
    return {
        "status": "ok",
        "model": rag.model,
        "embedding_model": rag.embed_model,
        "kb_chunks": rag.count(),
    }


__all__ = ["health", "router"]
