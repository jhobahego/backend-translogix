"""Vector repository abstraction over ChromaDB.

Encapsulates persistent client initialization with anonymized telemetry disabled,
cosine distance space, and clean data-access methods for RAG ingestion and retrieval.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

from app.core.config import settings


class ChromaVectorRepository:
    """Repository managing embeddings and vector documents in ChromaDB."""

    def __init__(
        self,
        chroma_path: str | Path | None = None,
        collection_name: str | None = None,
        client: chromadb.ClientAPI | None = None,
    ) -> None:
        self.chroma_path = Path(
            chroma_path if chroma_path is not None else settings.CHROMA_DB_PATH
        )
        self.collection_name = collection_name or settings.CHROMA_COLLECTION
        if client is not None:
            self._client = client
        else:
            self.chroma_path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(self.chroma_path),
                settings=Settings(anonymized_telemetry=False),
            )
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def client(self) -> chromadb.ClientAPI:
        """Access the underlying ChromaDB client."""
        return self._client

    @property
    def collection(self) -> chromadb.Collection:
        """Access the underlying ChromaDB collection."""
        return self._collection

    def count(self) -> int:
        """Number of chunks currently stored in the collection."""
        return int(self._collection.count())

    def categories(self) -> list[str]:
        """Distinct, non-empty ``categoria`` values currently indexed."""
        result = self._collection.get(include=["metadatas"])
        metadatas = result.get("metadatas") or []
        return sorted(
            {
                str(metadata["categoria"])
                for metadata in metadatas
                if metadata and metadata.get("categoria")
            }
        )

    def query_similar(
        self,
        query_embedding: list[float],
        top_k: int = 4,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve top_k nearest chunks matching the embedding and optional metadata filter.

        Returns structured chunks:
            [{"id": str, "content": str, "metadata": dict, "distance": float}]
        """
        if self.count() == 0:
            return []

        query_kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": max(1, top_k),
            "include": ["documents", "metadatas", "distances"],
        }
        # Chroma rejects empty where clause dictionaries
        if where:
            query_kwargs["where"] = where

        result = self._collection.query(**query_kwargs)
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        ids = (result.get("ids") or [[]])[0]

        chunks: list[dict[str, Any]] = []
        for chunk_id, doc, meta, raw_dist in zip(ids, documents, metadatas, distances):
            if doc is None or raw_dist is None:
                continue
            chunks.append(
                {
                    "id": str(chunk_id),
                    "content": str(doc),
                    "metadata": dict(meta or {}),
                    "distance": round(float(raw_dist), 4),
                }
            )
        return chunks

    async def async_query_similar(
        self,
        query_embedding: list[float],
        top_k: int = 4,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Async query execution run in a separate worker thread to avoid event loop stalls."""
        return await asyncio.to_thread(self.query_similar, query_embedding, top_k, where)

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> None:
        """Insert or update chunks with their vectors, content, and metadata."""
        if not ids:
            return
        self._collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

    def delete(
        self,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> None:
        """Delete chunks by explicit IDs or metadata filter."""
        kwargs: dict[str, Any] = {}
        if ids is not None:
            kwargs["ids"] = ids
        if where:
            kwargs["where"] = where
        if kwargs:
            self._collection.delete(**kwargs)

    def get(
        self,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch records by ID or metadata filter."""
        kwargs: dict[str, Any] = {}
        if ids is not None:
            kwargs["ids"] = ids
        if where:
            kwargs["where"] = where
        if include is not None:
            kwargs["include"] = include
        return self._collection.get(**kwargs)

    def reset_collection(self) -> None:
        """Drop and recreate the ChromaDB collection."""
        existing = {col.name for col in self._client.list_collections()}
        if self.collection_name in existing:
            self._client.delete_collection(self.collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )


VectorRepository = ChromaVectorRepository

__all__ = [
    "ChromaVectorRepository",
    "VectorRepository",
]
