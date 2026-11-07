"""Unit tests for document chunking, metadata preservation, and ID generation.

Covers:
- generate_chunk_id: determinism, structure, and 8-char MD5 digest
- _markdown_chunks: header-based hierarchy, size boundaries, and < 40 char pruning
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.services.ingest_service import (
    MIN_CHUNK_CHARS,
    _markdown_chunks,
    generate_chunk_id,
)


def test_generate_chunk_id_determinism_and_format() -> None:
    """generate_chunk_id must produce deterministic IDs with 8-char MD5 hash."""
    source = "manual_servicio.md"
    index = 4
    content = "El horario de atención es de lunes a viernes de 8:00 a 17:00."

    chunk_id_1 = generate_chunk_id(source, index, content)
    chunk_id_2 = generate_chunk_id(source, index, content)

    # Determinism
    assert chunk_id_1 == chunk_id_2

    # Structure: {source}_chunk_{index}_{md5[:8]}
    expected_digest = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]
    assert chunk_id_1 == f"{source}_chunk_{index}_{expected_digest}"
    assert chunk_id_1.startswith(f"{source}_chunk_{index}_")
    assert len(chunk_id_1.split("_")[-1]) == 8


def test_generate_chunk_id_changes_with_content() -> None:
    """Different content at same index produces different digest and ID."""
    source = "manual.md"
    id1 = generate_chunk_id(source, 1, "Contenido número uno para procesar.")
    id2 = generate_chunk_id(source, 1, "Contenido número dos diferente al anterior.")
    assert id1 != id2


def test_markdown_chunking_hierarchy_and_metadata(tmp_path: Path) -> None:
    """Markdown chunking splits on #, ##, ### and captures category/section/question."""
    doc_content = (
        "# Atención al Ciudadano\n\n"
        "## Canales de Atención\n\n"
        "### Canal Telefónico\n"
        "La línea nacional 018000 está disponible de lunes a viernes para todos los ciudadanos "
        "con cobertura en los 32 departamentos del territorio nacional colombiano.\n\n"
        "### Canal Presencial\n"
        "Las sedes físicas atienden en jornada continua de 8:00 AM a 5:00 PM con turno preferencial "
        "para personas de la tercera edad, mujeres gestantes y personas en situación de discapacidad.\n"
    )

    sample_file = tmp_path / "sample.md"
    sample_file.write_text(doc_content, encoding="utf-8")

    chunks = _markdown_chunks(sample_file, "sample.md")

    # Should generate at least 2 chunks corresponding to the questions
    assert len(chunks) >= 2

    for chunk in chunks:
        assert chunk.metadata["source"] == "sample.md"
        assert chunk.metadata["file_type"] == "markdown"
        assert chunk.metadata["categoria"] == "Atención al Ciudadano"
        assert chunk.metadata["seccion"] == "Canales de Atención"
        assert chunk.metadata["pregunta"] in {"Canal Telefónico", "Canal Presencial"}
        assert len(chunk.content) >= MIN_CHUNK_CHARS


def test_markdown_chunking_discards_short_fragments(tmp_path: Path) -> None:
    """Fragments with fewer than MIN_CHUNK_CHARS (40 chars) must be discarded."""
    doc_content = (
        "# A\n"
        "## B\n"
        "### C\n"
        "Ok.\n\n"  # Entire section including headers is < 40 chars
        "# Atención al Ciudadano\n\n"
        "## Canales de Atención\n\n"
        "### Pregunta Valida\n"
        "Este es un párrafo de texto suficientemente largo para superar el límite mínimo de cuarenta caracteres.\n"
    )

    sample_file = tmp_path / "short_test.md"
    sample_file.write_text(doc_content, encoding="utf-8")

    chunks = _markdown_chunks(sample_file, "short_test.md")

    # The < 40 char piece must be skipped, leaving only the valid one
    assert len(chunks) == 1
    assert "suficientemente largo" in chunks[0].content
    assert chunks[0].metadata["pregunta"] == "Pregunta Valida"


def test_markdown_chunking_bounds_chunk_size(tmp_path: Path) -> None:
    """Text larger than 800 characters is split into multiple bounded chunks."""
    long_paragraph = "TransLogix ofrece transporte seguro y confiable. " * 30  # ~1500 chars
    doc_content = (
        "# Cobertura y Tarifas\n\n"
        "## Tarifas Nacionales\n\n"
        f"### Detalle de Tarifas\n{long_paragraph}\n"
    )

    sample_file = tmp_path / "long_test.md"
    sample_file.write_text(doc_content, encoding="utf-8")

    chunks = _markdown_chunks(sample_file, "long_test.md")

    # Must be split into multiple chunks
    assert len(chunks) >= 2

    for chunk in chunks:
        # Recursive splitter keeps chunk size within reasonable bounds around 800
        assert len(chunk.content) <= 900
        assert len(chunk.content) >= MIN_CHUNK_CHARS
        assert chunk.metadata["categoria"] == "Cobertura y Tarifas"
