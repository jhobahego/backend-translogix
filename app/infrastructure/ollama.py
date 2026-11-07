"""Ollama client wrappers for embeddings and chat completions.

Embeddings are always passed explicitly to Chroma, so this module never
registers a Chroma embedding function and never re-embeds implicitly.
Chat clients use async Ollama clients with tuned timeouts for local CPU inference.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import ollama

from app.core.config import settings

DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "


class OllamaEmbedder:
    """Batch document embeddings and single query embeddings via Ollama."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        batch_size: int | None = None,
    ) -> None:
        self.model = model or settings.OLLAMA_EMBED_MODEL
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.batch_size = (
            batch_size if batch_size is not None else settings.EMBED_BATCH_SIZE
        )
        self.batch_size = max(1, self.batch_size)
        # nomic-embed-text is trained with task prefixes; other models are
        # used as-is so the same client keeps working with a swapped model.
        self._uses_prefix = self.model.startswith("nomic-embed-text")
        self._client = ollama.Client(host=self.base_url)
        self._async_client = ollama.AsyncClient(host=self.base_url)

    def _document_input(self, text: str) -> str:
        return f"{DOCUMENT_PREFIX}{text}" if self._uses_prefix else text

    def _query_input(self, text: str) -> str:
        return f"{QUERY_PREFIX}{text}" if self._uses_prefix else text

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed documents in bounded batches, preserving input order."""
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = [
                self._document_input(text)
                for text in texts[start : start + self.batch_size]
            ]
            # truncate=False fails loudly instead of silently cutting input:
            # a truncated chunk would be indexed with the wrong meaning.
            response = self._client.embed(
                model=self.model, input=batch, truncate=False
            )
            vectors.extend(list(embedding) for embedding in response.embeddings)
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        """Embed one search query with the query prefix."""
        response = await self._async_client.embed(
            model=self.model, input=self._query_input(text), truncate=False
        )
        return list(response.embeddings[0])


class OllamaChatClient:
    """Async chat client for Ollama with timeout management and streaming support."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
        timeout: float | None = None,
        stream_timeout: float | None = None,
    ) -> None:
        self.model = model or settings.OLLAMA_MODEL
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.temperature = (
            temperature if temperature is not None else settings.TEMPERATURE
        )
        self.timeout = (
            timeout if timeout is not None else settings.OLLAMA_TIMEOUT
        )
        self.stream_timeout = (
            stream_timeout
            if stream_timeout is not None
            else settings.OLLAMA_STREAM_TIMEOUT
        )
        # Separate clients for full responses vs token streaming so each honors
        # its own expected duration threshold.
        self._chat_client = ollama.AsyncClient(
            host=self.base_url,
            timeout=self.timeout,
        )
        self._stream_client = ollama.AsyncClient(
            host=self.base_url,
            timeout=self.stream_timeout,
        )

    @property
    def chat_client(self) -> ollama.AsyncClient:
        """Return the underlying async client for full generations."""
        return self._chat_client

    @property
    def stream_client(self) -> ollama.AsyncClient:
        """Return the underlying async client for streaming generations."""
        return self._stream_client

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Execute a full chat completion and return the stripped text response."""
        chat_options: dict[str, Any] = {
            "temperature": self.temperature if temperature is None else temperature
        }
        if options:
            chat_options.update(options)

        response = await self._chat_client.chat(
            model=model or self.model,
            messages=messages,
            stream=False,
            options=chat_options,
        )
        return (response.message.content or "").strip()

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        options: dict[str, Any] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream token fragments for a chat completion."""
        chat_options: dict[str, Any] = {
            "temperature": self.temperature if temperature is None else temperature
        }
        if options:
            chat_options.update(options)

        stream = await self._stream_client.chat(
            model=model or self.model,
            messages=messages,
            stream=True,
            options=chat_options,
        )
        async for part in stream:
            content = part.message.content
            if content:
                yield content


__all__ = [
    "DOCUMENT_PREFIX",
    "QUERY_PREFIX",
    "OllamaChatClient",
    "OllamaEmbedder",
]
