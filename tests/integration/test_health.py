"""Integration test for the /health liveness probe."""
from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient


def test_health_endpoint_returns_ok_and_metadata(
    client: TestClient, mock_rag_service: MagicMock
) -> None:
    """GET /health should return 200 with status='ok' and RAG metadata."""
    mock_rag_service.model = "qwen2.5:test-instruct"
    mock_rag_service.embed_model = "nomic-embed-text-test"
    mock_rag_service.count.return_value = 504

    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["model"] == "qwen2.5:test-instruct"
    assert data["embedding_model"] == "nomic-embed-text-test"
    assert data["kb_chunks"] == 504
    mock_rag_service.count.assert_called_once()
