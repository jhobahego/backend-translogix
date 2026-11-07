"""V1 API endpoint modules."""
from __future__ import annotations

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.pqrsd import router as pqrsd_router
from app.api.v1.endpoints.rag import router as rag_router

__all__ = ["health_router", "pqrsd_router", "rag_router"]
