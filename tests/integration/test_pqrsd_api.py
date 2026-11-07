"""Integration tests for PQRSD endpoints and 503 graceful degradation.

Covers:
- POST /api/v1/pqrsd:
  - Invalid payload rejected with 422 before database access
  - Valid payload degrades to 503 when database is unconfigured
- GET /api/v1/pqrsd:
  - Degrades to 503 when database is unconfigured
- GET /api/v1/pqrsd/{radicado}:
  - Degrades to 503 when database is unconfigured
- PATCH /api/v1/pqrsd/{radicado}:
  - Invalid payload rejected with 422 before database access
  - Valid payload degrades to 503 when database is unconfigured
- POST /api/v1/pqrsd/{radicado}/anexos:
  - Invalid payload rejected with 422 before database access
  - Valid payload degrades to 503 when database is unconfigured
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.database import NOT_CONFIGURED_DETAIL


# ==============================================================================
# POST /api/v1/pqrsd tests
# ==============================================================================


def test_create_pqrsd_invalid_body_returns_422(
    unconfigured_db_client: TestClient,
) -> None:
    """Malformed body must be rejected with 422 before touching the database."""
    # Missing required fields
    response = unconfigured_db_client.post("/api/v1/pqrsd", json={})
    assert response.status_code == 422

    # Asunto too short (< 5 chars)
    response_short = unconfigured_db_client.post(
        "/api/v1/pqrsd",
        json={
            "tipo_peticion_id": 1,
            "canal_id": 1,
            "dependencia_id": 1,
            "asunto": "Abc",
            "detalle": "Detalle suficientemente extenso de más de veinte caracteres.",
        },
    )
    assert response_short.status_code == 422


def test_create_pqrsd_valid_body_unconfigured_db_returns_503(
    unconfigured_db_client: TestClient,
) -> None:
    """Valid body must degrade to 503 with NOT_CONFIGURED_DETAIL if db is unavailable."""
    valid_payload = {
        "tipo_peticion_id": 1,
        "canal_id": 1,
        "dependencia_id": 1,
        "asunto": "Petición sobre retraso en envío",
        "detalle": "Solicito información acerca del estado actual de mi paquete con guía 12345.",
    }
    response = unconfigured_db_client.post("/api/v1/pqrsd", json=valid_payload)
    assert response.status_code == 503
    assert response.json()["detail"] == NOT_CONFIGURED_DETAIL


# ==============================================================================
# GET /api/v1/pqrsd and GET /api/v1/pqrsd/{radicado} tests
# ==============================================================================


def test_list_pqrsd_unconfigured_db_returns_503(
    unconfigured_db_client: TestClient,
) -> None:
    """GET /api/v1/pqrsd returns 503 when database is unconfigured."""
    response = unconfigured_db_client.get("/api/v1/pqrsd")
    assert response.status_code == 503
    assert response.json()["detail"] == NOT_CONFIGURED_DETAIL


def test_get_pqrsd_by_radicado_unconfigured_db_returns_503(
    unconfigured_db_client: TestClient,
) -> None:
    """GET /api/v1/pqrsd/{radicado} returns 503 when database is unconfigured."""
    response = unconfigured_db_client.get("/api/v1/pqrsd/PQRSD-2026-000001")
    assert response.status_code == 503
    assert response.json()["detail"] == NOT_CONFIGURED_DETAIL


# ==============================================================================
# PATCH /api/v1/pqrsd/{radicado} tests
# ==============================================================================


def test_update_pqrsd_invalid_body_returns_422(
    unconfigured_db_client: TestClient,
) -> None:
    """PATCH with incoherence (respondida without respuesta) returns 422 before db."""
    response = unconfigured_db_client.patch(
        "/api/v1/pqrsd/PQRSD-2026-000001",
        json={"estado": "respondida"},  # Missing respuesta and respondida_en
    )
    assert response.status_code == 422


def test_update_pqrsd_valid_body_unconfigured_db_returns_503(
    unconfigured_db_client: TestClient,
) -> None:
    """PATCH with valid state update returns 503 when db is unconfigured."""
    response = unconfigured_db_client.patch(
        "/api/v1/pqrsd/PQRSD-2026-000001",
        json={"estado": "en_tramite"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == NOT_CONFIGURED_DETAIL


# ==============================================================================
# POST /api/v1/pqrsd/{radicado}/anexos tests
# ==============================================================================


def test_add_anexo_invalid_body_returns_422(
    unconfigured_db_client: TestClient,
) -> None:
    """POST /api/v1/pqrsd/{radicado}/anexos with invalid hash returns 422."""
    invalid_anexo = {
        "nombre_archivo": "documento.pdf",
        "tipo_mime": "application/pdf",
        "tamano_bytes": 1024,
        "hash_sha256": "invalid_hash_too_short",
        "ruta": "/anexos/doc.pdf",
    }
    response = unconfigured_db_client.post(
        "/api/v1/pqrsd/PQRSD-2026-000001/anexos",
        json=invalid_anexo,
    )
    assert response.status_code == 422


def test_add_anexo_valid_body_unconfigured_db_returns_503(
    unconfigured_db_client: TestClient,
) -> None:
    """POST /api/v1/pqrsd/{radicado}/anexos returns 503 when db is unconfigured."""
    valid_anexo = {
        "nombre_archivo": "documento.pdf",
        "tipo_mime": "application/pdf",
        "tamano_bytes": 1024,
        "hash_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "ruta": "/anexos/doc.pdf",
    }
    response = unconfigured_db_client.post(
        "/api/v1/pqrsd/PQRSD-2026-000001/anexos",
        json=valid_anexo,
    )
    assert response.status_code == 503
    assert response.json()["detail"] == NOT_CONFIGURED_DETAIL
