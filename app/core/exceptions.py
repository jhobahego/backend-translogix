"""Global exception handlers and HTTP error helpers.

Translates lower-level errors (database connectivity, Ollama outages, domain
exceptions) into standardized HTTP responses with appropriate status codes.
"""
from __future__ import annotations

from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from app.core.config import settings
from app.domain.exceptions import (
    BusinessRuleViolationError,
    DomainError,
    EntityNotFoundError,
    InvalidStateTransitionError,
)

try:
    import ollama

    _OllamaResponseError: tuple[type[Exception], ...] = (ollama.ResponseError,)
except (ImportError, AttributeError):
    _OllamaResponseError = ()

# ollama-python rewrites httpx.ConnectError into the builtin ConnectionError,
# so the builtin type must be part of the "Ollama is unavailable" mapping.
OLLAMA_UNAVAILABLE: tuple[type[Exception], ...] = (
    httpx.ConnectError,
    httpx.TimeoutException,
    *_OllamaResponseError,
    ConnectionError,
)


async def database_unreachable_handler(
    request: Request, exc: DBAPIError
) -> JSONResponse:
    """A configured but unreachable database degrades to 503, never 500."""
    return JSONResponse(
        status_code=503,
        content={"detail": "Relational database is unreachable"},
    )


async def entity_not_found_handler(
    request: Request, exc: EntityNotFoundError
) -> JSONResponse:
    """Map domain EntityNotFoundError to 404 Not Found."""
    return JSONResponse(
        status_code=404,
        content={"detail": exc.message},
    )


async def business_rule_violation_handler(
    request: Request, exc: BusinessRuleViolationError
) -> JSONResponse:
    """Map domain BusinessRuleViolationError to 422 Unprocessable Entity."""
    return JSONResponse(
        status_code=422,
        content={"detail": exc.message},
    )


async def domain_error_handler(
    request: Request, exc: DomainError
) -> JSONResponse:
    """Fallback handler for generic domain errors, mapping to 400 Bad Request."""
    return JSONResponse(
        status_code=400,
        content={"detail": exc.message},
    )


def ollama_unavailable_exception(
    base_url: str | None = None,
) -> HTTPException:
    """HTTP 503 exception when Ollama cannot be reached."""
    target_url = base_url or settings.OLLAMA_BASE_URL
    return HTTPException(
        status_code=503,
        detail=f"Ollama unavailable at {target_url}",
    )


def internal_error_exception(
    detail: str = "Internal error while answering the question",
) -> HTTPException:
    """HTTP 500 exception for unhandled internal failures during generation."""
    return HTTPException(
        status_code=500,
        detail=detail,
    )


# Backwards compatibility aliases matching api/main.py naming
_database_unreachable = database_unreachable_handler
_ollama_unavailable = ollama_unavailable_exception
_internal_error = internal_error_exception


def register_exception_handlers(app: FastAPI) -> None:
    """Register all global exception handlers on a FastAPI application."""
    app.add_exception_handler(DBAPIError, database_unreachable_handler)  # type: ignore[arg-type]
    app.add_exception_handler(EntityNotFoundError, entity_not_found_handler)  # type: ignore[arg-type]
    app.add_exception_handler(
        BusinessRuleViolationError, business_rule_violation_handler  # type: ignore[arg-type]
    )
    app.add_exception_handler(DomainError, domain_error_handler)  # type: ignore[arg-type]


__all__ = [
    "OLLAMA_UNAVAILABLE",
    "_database_unreachable",
    "_internal_error",
    "_ollama_unavailable",
    "business_rule_violation_handler",
    "database_unreachable_handler",
    "domain_error_handler",
    "entity_not_found_handler",
    "internal_error_exception",
    "ollama_unavailable_exception",
    "register_exception_handlers",
]
