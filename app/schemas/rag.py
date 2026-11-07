"""Pydantic schemas for the Vector RAG endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field, StringConstraints

from app.schemas.base import AppBaseModel


class AskRequest(AppBaseModel):
    """Incoming question with an optional category filter."""

    question: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    categoria: str | None = Field(
        default=None,
        description=(
            "Exact match against indexed `categoria` metadata values. "
            "An unknown value returns 422 with the available categories."
        ),
    )


class SourceModel(AppBaseModel):
    """One grounding fragment returned with the answer."""

    content: str
    metadata: dict[str, Any]
    distance: float


class AskResponse(AppBaseModel):
    """Grounded answer plus its traceable sources."""

    answer: str
    sources: list[SourceModel]
