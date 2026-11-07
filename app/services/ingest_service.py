"""Knowledge base ingestion service for Markdown and PDF documents into ChromaDB."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from pypdf import PdfReader

from app.core.config import settings
from app.infrastructure.ollama import OllamaEmbedder
from app.repositories.vector_repository import VectorRepository

MARKDOWN_HEADERS = [("#", "categoria"), ("##", "seccion"), ("###", "pregunta")]
MARKDOWN_SEPARATORS = ["\n\n", "\n", ".", " ", ""]
MIN_CHUNK_CHARS = 40
SUPPORTED_SUFFIXES = {".md", ".pdf"}


@dataclass(frozen=True)
class Chunk:
    """One indexed fragment with its deterministic ID and metadata."""

    id: str
    content: str
    metadata: dict[str, str | int]


def generate_chunk_id(source: str, index: int, content: str) -> str:
    """Build a stable chunk ID from the source, position, and content."""
    digest = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]
    return f"{source}_chunk_{index}_{digest}"


def _knowledge_base_files(root: Path | None = None) -> list[Path]:
    """Every ``.md``/``.pdf`` file under the knowledge base, sorted."""
    base_dir = root if root is not None else settings.KNOWLEDGE_BASE_DIR
    if not base_dir.is_dir():
        return []
    return sorted(
        (
            path
            for path in base_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
        ),
        key=lambda path: path.relative_to(base_dir).as_posix(),
    )


def _markdown_chunks(path: Path, source: str) -> list[Chunk]:
    """Split Markdown by headers first, then by size, keeping the headers."""
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=MARKDOWN_HEADERS, strip_headers=False
    )
    size_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        separators=MARKDOWN_SEPARATORS,
    )
    chunks: list[Chunk] = []
    index = 0
    for document in header_splitter.split_text(path.read_text(encoding="utf-8")):
        for piece in size_splitter.split_text(document.page_content):
            content = piece.strip()
            if len(content) < MIN_CHUNK_CHARS:
                continue
            metadata: dict[str, str | int] = {
                "source": source,
                "file_type": "markdown",
                "categoria": str(document.metadata.get("categoria", "General")),
                "seccion": str(document.metadata.get("seccion", "N/A")),
                "pregunta": str(document.metadata.get("pregunta", "N/A")),
            }
            chunks.append(
                Chunk(generate_chunk_id(source, index, content), content, metadata)
            )
            index += 1
    return chunks


def _pdf_chunks(path: Path, source: str) -> list[Chunk]:
    """Split a PDF page by page, keeping the page number in metadata."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=900,
        chunk_overlap=180,
        separators=MARKDOWN_SEPARATORS,
    )
    chunks: list[Chunk] = []
    index = 0
    reader = PdfReader(str(path))
    for page_number, page in enumerate(reader.pages, start=1):
        for piece in splitter.split_text(page.extract_text() or ""):
            content = piece.strip()
            if len(content) < MIN_CHUNK_CHARS:
                continue
            metadata: dict[str, str | int] = {
                "source": source,
                "file_type": "pdf",
                "page": page_number,
                "categoria": "Documento PDF",
            }
            chunks.append(
                Chunk(generate_chunk_id(source, index, content), content, metadata)
            )
            index += 1
    return chunks


def _chunks_for_file(path: Path, source: str) -> list[Chunk]:
    if path.suffix.lower() == ".pdf":
        return _pdf_chunks(path, source)
    return _markdown_chunks(path, source)


def _delete_orphan_sources(
    vector_repo: VectorRepository, known_sources: set[str]
) -> None:
    """Drop chunks whose source file no longer exists in the knowledge base."""
    if vector_repo.count() == 0:
        return
    rows = vector_repo.get(include=["metadatas"])
    metadatas = rows.get("metadatas") or []
    ids = rows.get("ids") or []
    orphan_ids = [
        chunk_id
        for chunk_id, metadata in zip(ids, metadatas)
        if (metadata or {}).get("source") not in known_sources
    ]
    if orphan_ids:
        vector_repo.delete(ids=orphan_ids)


class IngestService:
    """Service orchestrating document parsing, chunking, embedding, and vector storage."""

    def __init__(
        self,
        vector_repo: VectorRepository | None = None,
        embedder: OllamaEmbedder | None = None,
        knowledge_base_dir: str | Path | None = None,
        batch_size: int | None = None,
    ) -> None:
        self.vector_repo = vector_repo or VectorRepository()
        self.embedder = embedder or OllamaEmbedder()
        self.knowledge_base_dir = Path(
            knowledge_base_dir
            if knowledge_base_dir is not None
            else settings.KNOWLEDGE_BASE_DIR
        )
        self.batch_size = (
            batch_size if batch_size is not None else settings.EMBED_BATCH_SIZE
        )
        self.batch_size = max(1, self.batch_size)

    def knowledge_base_files(self) -> list[Path]:
        return _knowledge_base_files(self.knowledge_base_dir)

    def markdown_chunks(self, path: Path, source: str) -> list[Chunk]:
        return _markdown_chunks(path, source)

    def pdf_chunks(self, path: Path, source: str) -> list[Chunk]:
        return _pdf_chunks(path, source)

    def chunks_for_file(self, path: Path, source: str) -> list[Chunk]:
        return _chunks_for_file(path, source)

    def delete_orphan_sources(self, known_sources: set[str]) -> None:
        _delete_orphan_sources(self.vector_repo, known_sources)

    def ingest(self, reset: bool = False) -> dict[str, int]:
        """Index ``knowledge_base/`` into Chroma and return run statistics."""
        if reset:
            self.vector_repo.reset_collection()

        files_indexed = 0
        chunks_indexed = 0
        known_sources: set[str] = set()

        for path in self.knowledge_base_files():
            source = path.relative_to(self.knowledge_base_dir).as_posix()
            known_sources.add(source)
            chunks = self.chunks_for_file(path, source)
            if not chunks:
                continue

            wanted_ids = {chunk.id for chunk in chunks}
            existing = self.vector_repo.get(where={"source": source}, include=[])
            existing_ids = existing.get("ids") or []
            stale_ids = [
                chunk_id for chunk_id in existing_ids if chunk_id not in wanted_ids
            ]
            if stale_ids:
                self.vector_repo.delete(ids=stale_ids)

            # Bounded batches: 32 short chunks is the CPU/RAM sweet spot here.
            for start in range(0, len(chunks), self.batch_size):
                batch = chunks[start : start + self.batch_size]
                embeddings = self.embedder.embed_documents(
                    [chunk.content for chunk in batch]
                )
                self.vector_repo.upsert(
                    ids=[chunk.id for chunk in batch],
                    documents=[chunk.content for chunk in batch],
                    metadatas=[chunk.metadata for chunk in batch],
                    embeddings=embeddings,
                )

            files_indexed += 1
            chunks_indexed += len(chunks)

        self.delete_orphan_sources(known_sources)

        return {
            "files_indexed": files_indexed,
            "chunks_indexed": chunks_indexed,
            "collection_count": self.vector_repo.count(),
        }


def build_or_update_vector_db(
    reset: bool = False,
    service: IngestService | None = None,
) -> dict[str, int]:
    """Convenience function matching the legacy signature."""
    svc = service or IngestService()
    return svc.ingest(reset=reset)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: index the knowledge base and print one JSON line."""
    parser = argparse.ArgumentParser(
        description="Index knowledge_base/ into the local ChromaDB collection."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete and recreate the collection before indexing",
    )
    args = parser.parse_args(argv)

    stats = build_or_update_vector_db(reset=args.reset)
    if stats["files_indexed"] == 0:
        print(
            "WARNING: no indexable .md/.pdf content found in "
            f"{settings.KNOWLEDGE_BASE_DIR}; the collection is empty.",
            file=sys.stderr,
        )
    print(json.dumps(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
