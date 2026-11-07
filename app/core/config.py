"""Environment-driven configuration for the application.

Centralizes configuration by loading ``.env`` via python-dotenv with repository
root resolution. Exposes a typed ``Settings`` dataclass and a singleton ``settings``
instance, alongside module-level attributes for backwards compatibility.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Resolves to repository root: <repo_root>/app/core/config.py -> parent x 3
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = REPO_ROOT / ".env"
load_dotenv(ENV_FILE)


def _env(name: str, default: str) -> str:
    """Return the env value for ``name``, or ``default`` when unset/blank."""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    """Parse an integer env var and clamp it to ``minimum`` when given."""
    raw = _env(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if minimum is not None and value < minimum:
        return minimum
    return value


def _env_float(name: str, default: float) -> float:
    """Parse a float env var."""
    raw = _env(name, str(default))
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


def _resolve_path(name: str, default: str, root: Path = REPO_ROOT) -> Path:
    """Resolve a possibly relative path against the repository root."""
    path = Path(_env(name, default)).expanduser()
    return path if path.is_absolute() else (root / path).resolve()


@dataclass(frozen=True)
class Settings:
    """Central application settings resolved from environment variables."""

    REPO_ROOT: Path = field(default_factory=lambda: REPO_ROOT)
    ENV_FILE: Path = field(default_factory=lambda: ENV_FILE)

    API_PORT: int = field(default_factory=lambda: _env_int("API_PORT", 8000, minimum=1))
    OLLAMA_BASE_URL: str = field(
        default_factory=lambda: _env("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    )
    OLLAMA_MODEL: str = field(
        default_factory=lambda: _env("OLLAMA_MODEL", "qwen2.5:3b-instruct-q4_K_M")
    )
    OLLAMA_EMBED_MODEL: str = field(
        default_factory=lambda: _env("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    )
    TEMPERATURE: float = field(default_factory=lambda: _env_float("TEMPERATURE", 0.2))

    # Retrieval gate settings
    RAG_TOP_K: int = field(default_factory=lambda: _env_int("RAG_TOP_K", 4, minimum=1))
    RAG_MAX_DISTANCE: float = field(
        default_factory=lambda: _env_float("RAG_MAX_DISTANCE", 0.50)
    )
    RAG_STRONG_DISTANCE: float = field(
        default_factory=lambda: _env_float("RAG_STRONG_DISTANCE", 0.25)
    )

    # Hardware budget & concurrency
    LLM_CONCURRENCY_LIMIT: int = field(
        default_factory=lambda: _env_int("LLM_CONCURRENCY_LIMIT", 1, minimum=1)
    )
    EMBED_BATCH_SIZE: int = field(
        default_factory=lambda: _env_int("EMBED_BATCH_SIZE", 32, minimum=1)
    )

    # Chroma and knowledge base paths
    CHROMA_DB_PATH: Path = field(
        default_factory=lambda: _resolve_path("CHROMA_DB_PATH", "./chroma_db")
    )
    CHROMA_COLLECTION: str = field(
        default_factory=lambda: _env("CHROMA_COLLECTION", "asistencia_cliente_kb")
    )
    KNOWLEDGE_BASE_DIR: Path = field(
        default_factory=lambda: _resolve_path("KNOWLEDGE_BASE_DIR", "./knowledge_base")
    )

    # Relational database backend settings
    DATABASE_URL: str = field(default_factory=lambda: _env("DATABASE_URL", ""))
    DB_POOL_SIZE: int = field(default_factory=lambda: _env_int("DB_POOL_SIZE", 5, minimum=1))
    DB_POOL_TIMEOUT: int = field(
        default_factory=lambda: _env_int("DB_POOL_TIMEOUT", 10, minimum=1)
    )
    DB_CONNECT_TIMEOUT: int = field(
        default_factory=lambda: _env_int("DB_CONNECT_TIMEOUT", 5, minimum=1)
    )
    DB_ECHO: bool = field(
        default_factory=lambda: _env("DB_ECHO", "false").lower() in {"1", "true", "yes", "on"}
    )

    # Timeouts (in seconds)
    OLLAMA_TIMEOUT: float = field(
        default_factory=lambda: _env_float("OLLAMA_TIMEOUT", 300.0)
    )
    OLLAMA_STREAM_TIMEOUT: float = field(
        default_factory=lambda: _env_float("OLLAMA_STREAM_TIMEOUT", 400.0)
    )


# Singleton instance
settings = Settings()

# Module-level exports for direct import compatibility:
# `from app.core.config import DATABASE_URL`
REPO_ROOT = settings.REPO_ROOT
ENV_FILE = settings.ENV_FILE
API_PORT = settings.API_PORT
OLLAMA_BASE_URL = settings.OLLAMA_BASE_URL
OLLAMA_MODEL = settings.OLLAMA_MODEL
OLLAMA_EMBED_MODEL = settings.OLLAMA_EMBED_MODEL
TEMPERATURE = settings.TEMPERATURE
RAG_TOP_K = settings.RAG_TOP_K
RAG_MAX_DISTANCE = settings.RAG_MAX_DISTANCE
RAG_STRONG_DISTANCE = settings.RAG_STRONG_DISTANCE
LLM_CONCURRENCY_LIMIT = settings.LLM_CONCURRENCY_LIMIT
EMBED_BATCH_SIZE = settings.EMBED_BATCH_SIZE
CHROMA_DB_PATH = settings.CHROMA_DB_PATH
CHROMA_COLLECTION = settings.CHROMA_COLLECTION
KNOWLEDGE_BASE_DIR = settings.KNOWLEDGE_BASE_DIR
DATABASE_URL = settings.DATABASE_URL
DB_POOL_SIZE = settings.DB_POOL_SIZE
DB_POOL_TIMEOUT = settings.DB_POOL_TIMEOUT
DB_CONNECT_TIMEOUT = settings.DB_CONNECT_TIMEOUT
DB_ECHO = settings.DB_ECHO
OLLAMA_TIMEOUT = settings.OLLAMA_TIMEOUT
OLLAMA_STREAM_TIMEOUT = settings.OLLAMA_STREAM_TIMEOUT

__all__ = [
    "API_PORT",
    "CHROMA_COLLECTION",
    "CHROMA_DB_PATH",
    "DATABASE_URL",
    "DB_CONNECT_TIMEOUT",
    "DB_ECHO",
    "DB_POOL_SIZE",
    "DB_POOL_TIMEOUT",
    "EMBED_BATCH_SIZE",
    "ENV_FILE",
    "KNOWLEDGE_BASE_DIR",
    "LLM_CONCURRENCY_LIMIT",
    "OLLAMA_BASE_URL",
    "OLLAMA_EMBED_MODEL",
    "OLLAMA_MODEL",
    "OLLAMA_STREAM_TIMEOUT",
    "OLLAMA_TIMEOUT",
    "RAG_MAX_DISTANCE",
    "RAG_STRONG_DISTANCE",
    "RAG_TOP_K",
    "REPO_ROOT",
    "Settings",
    "TEMPERATURE",
    "settings",
]
