"""RAG (Retrieval-Augmented Generation) endpoints for customer inquiries."""
from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator
import json
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.dependencies import get_rag_service, get_semaphore
from app.core.exceptions import (
    OLLAMA_UNAVAILABLE,
    internal_error_exception,
    ollama_unavailable_exception,
)
from app.schemas.rag import AskRequest, AskResponse
from app.services.rag_service import RAGService

router = APIRouter(tags=["rag"])

_ASK_BODY_EXAMPLES = {
    "sin_categoria": {
        "summary": "No category filter",
        "description": (
            "Omit categoria unless you know the exact indexed value; "
            "an unknown value is rejected with 422."
        ),
        "value": {"question": "¿Cuál es el horario de atención?"},
    }
}


def _question(payload: AskRequest) -> str:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="question must not be blank")
    return question


async def _category(rag: RAGService, categoria: str | None) -> str | None:
    """Normalize and validate the optional exact-match category filter."""
    if categoria is None:
        return None
    value = categoria.strip()
    if not value:
        return None
    available = await asyncio.to_thread(rag.categories)
    if value not in available:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"Unknown categoria: {value!r}",
                "available_categories": available,
            },
        )
    return value


async def _answer(
    rag: RAGService,
    semaphore: asyncio.Semaphore,
    question: str,
    categoria: str | None,
) -> dict[str, Any]:
    # Concurrency 1 on this hardware: the semaphore covers retrieval and
    # generation so a second request never competes for RAM.
    try:
        async with semaphore:
            return await rag.ask(question, categoria)
    except OLLAMA_UNAVAILABLE as exc:
        raise ollama_unavailable_exception() from exc
    except Exception as exc:
        raise internal_error_exception() from exc


async def _prepare(
    rag: RAGService, question: str, categoria: str | None
) -> list[dict[str, Any]]:
    try:
        return await rag.prepare(question, categoria)
    except OLLAMA_UNAVAILABLE as exc:
        raise ollama_unavailable_exception() from exc
    except Exception as exc:
        raise internal_error_exception() from exc


@router.post("/ask", response_model=AskResponse, summary="Grounded RAG answer")
async def ask(
    payload: Annotated[AskRequest, Body(openapi_examples=_ASK_BODY_EXAMPLES)],
    rag: Annotated[RAGService, Depends(get_rag_service)],
    semaphore: Annotated[asyncio.Semaphore, Depends(get_semaphore)],
) -> AskResponse:
    """Answer a question grounded on the local knowledge base."""
    question = _question(payload)
    categoria = await _category(rag, payload.categoria)
    result = await _answer(rag, semaphore, question, categoria)
    return AskResponse(**result)


@router.post("/ask/stream", summary="Stream grounded RAG tokens")
async def ask_stream(
    payload: Annotated[AskRequest, Body(openapi_examples=_ASK_BODY_EXAMPLES)],
    rag: Annotated[RAGService, Depends(get_rag_service)],
    semaphore: Annotated[asyncio.Semaphore, Depends(get_semaphore)],
) -> StreamingResponse:
    """Stream answer tokens as plain text.

    Retrieval runs before the response starts so failures still map to a
    proper HTTP status; only generation errors appear inside the stream.
    """
    question = _question(payload)
    categoria = await _category(rag, payload.categoria)
    chunks = await _prepare(rag, question, categoria)

    async def tokens() -> AsyncIterator[str]:
        try:
            async with semaphore:
                async for token in rag.stream_answer(question, chunks):
                    yield token
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # headers are already sent, so mark the body
            yield f"\n[stream error: {exc}]"

    sources_payload = [
        {
            "content": c.get("content"),
            "metadata": c.get("metadata", {}),
            "distance": c.get("distance", 0.0),
        }
        for c in chunks
    ]
    encoded_sources = base64.b64encode(
        json.dumps(sources_payload).encode("utf-8")
    ).decode("ascii")

    return StreamingResponse(
        tokens(),
        media_type="text/plain; charset=utf-8",
        headers={"X-Sources-Base64": encoded_sources},
    )


@router.post("/sync-kb", summary="Re-index knowledge base")
async def sync_kb() -> dict[str, Any]:
    """Re-index the knowledge base in a worker thread."""
    try:
        from app.services.ingest_service import build_or_update_vector_db
    except ImportError:
        from api.ingest import build_or_update_vector_db  # type: ignore[no-redef]

    try:
        stats = await asyncio.to_thread(build_or_update_vector_db)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Knowledge base sync failed"
        ) from exc
    return {"status": "ok", **stats}


__all__ = [
    "_ASK_BODY_EXAMPLES",
    "_answer",
    "_category",
    "_prepare",
    "_question",
    "ask",
    "ask_stream",
    "router",
    "sync_kb",
]
