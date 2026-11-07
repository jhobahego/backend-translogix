"""Shared pytest fixtures for unit and integration tests.

Provides mocked RAG services, embedders, and FastAPI test clients to allow
fast, deterministic test execution without requiring Ollama, GPU, or a live database.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session, get_rag_service
from app.infrastructure.ollama import OllamaEmbedder
from app.main import app as main_app
from app.services.rag_service import RAGService


@pytest.fixture(autouse=True)
def cleanup_dependency_overrides() -> Iterator[None]:
    """Ensure FastAPI dependency overrides are cleared after every single test."""
    yield
    main_app.dependency_overrides.clear()


@pytest.fixture
def app() -> FastAPI:
    """Provide the FastAPI application instance."""
    return main_app


@pytest.fixture
def mock_rag_service() -> MagicMock:
    """Provide a mocked RAGService with deterministic behavior."""
    service = MagicMock(spec=RAGService)
    service.model = "qwen2.5:test"
    service.embed_model = "nomic-embed-test"
    service.count.return_value = 100
    service.categories.return_value = [
        "Atención al Ciudadano",
        "Tarifas y Envíos",
        "PQRSD",
    ]

    service.ask = AsyncMock(
        return_value={
            "answer": "Horario de atención: lunes a viernes de 8:00 a 17:00.",
            "sources": [
                {
                    "content": "Horario de atención general: 8:00 AM a 5:00 PM.",
                    "metadata": {
                        "source": "manual-atencion.md",
                        "categoria": "Atención al Ciudadano",
                    },
                    "distance": 0.12,
                }
            ],
        }
    )

    service.prepare = AsyncMock(
        return_value=[
            {
                "content": "Horario de atención general: 8:00 AM a 5:00 PM.",
                "metadata": {
                    "source": "manual-atencion.md",
                    "categoria": "Atención al Ciudadano",
                },
                "distance": 0.12,
            }
        ]
    )

    async def fake_stream_answer(
        question: str, chunks: list[dict]
    ) -> AsyncIterator[str]:
        tokens = ["Horario ", "de ", "atención: ", "8:00 ", "a ", "17:00."]
        for token in tokens:
            yield token

    service.stream_answer = fake_stream_answer
    return service


@pytest.fixture
def mock_embedder() -> MagicMock:
    """Provide a mocked OllamaEmbedder returning mock vectors."""
    embedder = MagicMock(spec=OllamaEmbedder)
    embedder.model = "nomic-embed-test"
    embedder.embed_documents.side_effect = lambda texts: [[0.05] * 768 for _ in texts]
    embedder.embed_query.side_effect = lambda text: [0.05] * 768
    return embedder


@pytest.fixture
def client(mock_rag_service: MagicMock) -> Iterator[TestClient]:
    """Provide a TestClient with RAG dependency overridden by default."""
    main_app.dependency_overrides[get_rag_service] = lambda: mock_rag_service
    # Keep semaphore initialized in app.state
    if not hasattr(main_app.state, "semaphore") or main_app.state.semaphore is None:
        main_app.state.semaphore = asyncio.Semaphore(1)

    with TestClient(main_app) as test_client:
        yield test_client


@pytest.fixture
def unconfigured_db_client(client: TestClient) -> TestClient:
    """Provide a TestClient where database is guaranteed to be unconfigured (503)."""
    def override_get_db() -> Iterator[None]:
        yield None

    main_app.dependency_overrides[get_db_session] = override_get_db
    return client
