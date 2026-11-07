"""Integration tests for the Vector RAG API contracts.

Covers:
- POST /api/v1/ask:
  - Valid question returns 200 and AskResponse
  - Valid question with indexed category returns 200
  - Unknown category returns 422 with available_categories
  - Blank / empty question returns 422
  - Unexpected extra field returns 422 (extra="forbid")
- POST /api/v1/ask/stream:
  - Streaming tokens plain text
  - X-Sources-Base64 header traceability
  - Validation failures before stream begins
- POST /api/v1/sync-kb:
  - Worker thread re-indexing returning status="ok"
"""
from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


# ==============================================================================
# POST /api/v1/ask tests
# ==============================================================================


def test_ask_valid_question_returns_200(
    client: TestClient, mock_rag_service: MagicMock
) -> None:
    """POST /api/v1/ask with valid question returns 200 and grounded answer."""
    mock_rag_service.ask = AsyncMock(
        return_value={
            "answer": "La tarifa mínima para envíos locales es de $8.500 COP.",
            "sources": [
                {
                    "content": "Tarifa mínima local: $8.500 COP.",
                    "metadata": {
                        "source": "tarifas.md",
                        "categoria": "Tarifas y Envíos",
                    },
                    "distance": 0.15,
                }
            ],
        }
    )

    response = client.post(
        "/api/v1/ask",
        json={"question": "¿Cuál es la tarifa mínima de un envío?"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "tarifa mínima" in data["answer"]
    assert len(data["sources"]) == 1
    assert data["sources"][0]["metadata"]["categoria"] == "Tarifas y Envíos"
    assert data["sources"][0]["distance"] == 0.15


def test_ask_with_valid_category_filter(
    client: TestClient, mock_rag_service: MagicMock
) -> None:
    """POST /api/v1/ask with an indexed category passes the filter to RAG."""
    mock_rag_service.categories.return_value = ["Atención al Ciudadano", "Tarifas"]
    mock_rag_service.ask = AsyncMock(
        return_value={"answer": "Atendemos de 8 a 17.", "sources": []}
    )

    response = client.post(
        "/api/v1/ask",
        json={
            "question": "¿Cuál es el horario?",
            "categoria": "Atención al Ciudadano",
        },
    )

    assert response.status_code == 200
    mock_rag_service.ask.assert_called_once_with(
        "¿Cuál es el horario?", "Atención al Ciudadano"
    )


def test_ask_with_unknown_category_returns_422(
    client: TestClient, mock_rag_service: MagicMock
) -> None:
    """POST /api/v1/ask with unknown category returns 422 with available list."""
    mock_rag_service.categories.return_value = ["Atención al Ciudadano", "Tarifas"]

    response = client.post(
        "/api/v1/ask",
        json={"question": "¿Cuál es el horario?", "categoria": "Categoría Falsa"},
    )

    assert response.status_code == 422
    data = response.json()
    detail = data["detail"]
    assert "available_categories" in detail
    assert "Atención al Ciudadano" in detail["available_categories"]


def test_ask_blank_question_returns_422(client: TestClient) -> None:
    """POST /api/v1/ask with empty or whitespace-only question returns 422."""
    # Whitespace only
    resp_blank = client.post("/api/v1/ask", json={"question": "   \n\t  "})
    assert resp_blank.status_code == 422

    # Empty string
    resp_empty = client.post("/api/v1/ask", json={"question": ""})
    assert resp_empty.status_code == 422


def test_ask_rejects_extra_fields(client: TestClient) -> None:
    """POST /api/v1/ask rejects unknown fields in body with 422 (extra='forbid')."""
    response = client.post(
        "/api/v1/ask",
        json={
            "question": "¿Dónde queda la oficina principal?",
            "extra_field": "unauthorized_data",
        },
    )
    assert response.status_code == 422
    detail_str = str(response.json())
    assert "extra" in detail_str.lower() or "extra_forbidden" in detail_str.lower()


# ==============================================================================
# POST /api/v1/ask/stream tests
# ==============================================================================


def test_ask_stream_tokens_and_header(
    client: TestClient, mock_rag_service: MagicMock
) -> None:
    """POST /api/v1/ask/stream streams plain text and includes X-Sources-Base64 header."""
    mock_rag_service.prepare = AsyncMock(
        return_value=[
            {
                "content": "Punto de atención Bogotá Calle 26.",
                "metadata": {"source": "puntos.md", "seccion": "Bogotá"},
                "distance": 0.20,
            }
        ]
    )

    response = client.post(
        "/api/v1/ask/stream",
        json={"question": "¿Dónde están ubicados?"},
    )

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]

    # Verify X-Sources-Base64 header
    assert "x-sources-base64" in response.headers
    raw_header = response.headers["x-sources-base64"]
    decoded_sources = json.loads(base64.b64decode(raw_header).decode("utf-8"))
    assert len(decoded_sources) == 1
    assert decoded_sources[0]["content"] == "Punto de atención Bogotá Calle 26."
    assert decoded_sources[0]["distance"] == 0.20

    # Verify body text has tokens yielded by mock stream
    assert len(response.text) > 0
    assert "Horario" in response.text


def test_ask_stream_validation_failure_before_stream(client: TestClient) -> None:
    """POST /api/v1/ask/stream validates payload before opening the stream."""
    response = client.post(
        "/api/v1/ask/stream",
        json={"question": "   "},
    )
    assert response.status_code == 422


# ==============================================================================
# POST /api/v1/sync-kb tests
# ==============================================================================


def test_sync_kb_success(client: TestClient) -> None:
    """POST /api/v1/sync-kb delegates to ingest service and returns status='ok'."""
    mock_stats = {
        "files_scanned": 12,
        "chunks_indexed": 504,
        "pruned": 0,
    }

    with patch(
        "app.services.ingest_service.build_or_update_vector_db",
        return_value=mock_stats,
    ):
        response = client.post("/api/v1/sync-kb")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["files_scanned"] == 12
    assert data["chunks_indexed"] == 504
