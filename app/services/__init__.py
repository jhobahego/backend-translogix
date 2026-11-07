"""Services layer re-exports."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.ingest_service import (
        IngestService,
        build_or_update_vector_db,
    )
    from app.services.pqrsd_service import PqrsdService
    from app.services.rag_service import LocalVectorRAG, RAGService

__all__ = [
    "IngestService",
    "LocalVectorRAG",
    "PqrsdService",
    "RAGService",
    "build_or_update_vector_db",
]


def __getattr__(name: str) -> Any:
    if name in {"IngestService", "build_or_update_vector_db"}:
        import app.services.ingest_service as _ingest

        return getattr(_ingest, name)
    if name == "PqrsdService":
        from app.services.pqrsd_service import PqrsdService

        return PqrsdService
    if name in {"LocalVectorRAG", "RAGService"}:
        import app.services.rag_service as _rag

        return getattr(_rag, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
