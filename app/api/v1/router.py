"""Version 1 API router grouping all v1 sub-routers."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints.pqrsd import router as pqrsd_router
from app.api.v1.endpoints.rag import router as rag_router

api_v1_router = APIRouter(prefix="/api/v1")

# Mount RAG endpoints (/api/v1/ask, /api/v1/ask/stream, /api/v1/sync-kb)
api_v1_router.include_router(rag_router)

# Mount PQRSD endpoints (/api/v1/pqrsd, /api/v1/pqrsd/{radicado}, etc.)
api_v1_router.include_router(pqrsd_router)

__all__ = ["api_v1_router"]
