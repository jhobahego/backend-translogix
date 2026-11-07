"""Engine and session management for the optional PostgreSQL backend.

The relational store is optional: when ``DATABASE_URL`` is empty the RAG
service must still start, so the engine is created lazily on first use and
never during application startup.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None

NOT_CONFIGURED_DETAIL = (
    "Relational database is not configured: set DATABASE_URL to enable the "
    "PQRSD case endpoints"
)


class DatabaseNotConfigured(RuntimeError):
    """``DATABASE_URL`` is empty; the backend was never configured."""


def database_url() -> str | None:
    """Return the configured URL, or None when the backend is disabled."""
    value = settings.DATABASE_URL.strip()
    return value or None


def get_engine() -> Engine:
    """Create (once) and return the engine without opening a connection."""
    global _engine
    if _engine is None:
        url = database_url()
        if url is None:
            raise DatabaseNotConfigured("DATABASE_URL is not set")
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=settings.DB_POOL_SIZE,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            max_overflow=0,
            echo=settings.DB_ECHO,
            # A dead host must fail fast: without connect_timeout the request
            # hangs until the OS gives up, and a hung request looks like a
            # model latency problem.
            connect_args={"connect_timeout": settings.DB_CONNECT_TIMEOUT},
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the session factory bound to the shared engine."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            expire_on_commit=False,
        )
    return _session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for scripts: commit on success, roll back on error."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping() -> bool:
    """Whether a ``select 1`` round trip succeeds; never raises."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("select 1"))
        return True
    except (DatabaseNotConfigured, SQLAlchemyError, OSError):
        return False


def reset() -> None:
    """Dispose the cached engine and factory (tests and env changes)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def get_db() -> Iterator[Session | None]:
    """Yield a session for the request and always close it afterwards.

    Yields None when the relational backend is disabled so that endpoint
    validation can run before returning 503 via :func:`require_session`.
    """
    try:
        factory = get_session_factory()
    except DatabaseNotConfigured:
        yield None
        return

    session = factory()
    try:
        yield session
    finally:
        session.close()


def require_session(session: Session | None) -> Session:
    """Raise 503 when the relational backend was never configured."""
    if session is None:
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED_DETAIL)
    return session


__all__ = [
    "DatabaseNotConfigured",
    "NOT_CONFIGURED_DETAIL",
    "database_url",
    "get_db",
    "get_engine",
    "get_session_factory",
    "ping",
    "require_session",
    "reset",
    "session_scope",
]
