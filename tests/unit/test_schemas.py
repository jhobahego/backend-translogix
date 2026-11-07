"""Unit tests for Pydantic schema validation and business contracts.

Covers:
- AskRequest validation, whitespace stripping, min_length, and extra="forbid"
- PqrsdCreate validation, past deadline rejection, constraints
- PqrsdUpdate / PqrsdTransicion state machine and coherence
- CiudadanoCreate document coherence and EMAIL_REGEX
- PqrsdAnexoCreate SHA256_REGEX and size boundaries
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import re
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.pqrsd import (
    EMAIL_REGEX,
    RADICADO_PQRSD_REGEX,
    SHA256_REGEX,
    CiudadanoCreate,
    EstadoPQRSD,
    PqrsdAnexoCreate,
    PqrsdCreate,
    PqrsdTransicion,
    PqrsdUpdate,
    SUCCESSOR_STATES,
)
from app.schemas.rag import AskRequest, AskResponse, SourceModel


# ==============================================================================
# AskRequest tests
# ==============================================================================


def test_ask_request_valid() -> None:
    """Valid question and optional categoria should instantiate successfully."""
    req = AskRequest(question="¿Cuál es el horario de atención?", categoria="Atención")
    assert req.question == "¿Cuál es el horario de atención?"
    assert req.categoria == "Atención"


def test_ask_request_strips_whitespace() -> None:
    """Leading and trailing whitespace should be automatically stripped."""
    req = AskRequest(question="   ¿Cuánto cuesta el envío a Cali?   \n")
    assert req.question == "¿Cuánto cuesta el envío a Cali?"


def test_ask_request_empty_or_blank_rejected() -> None:
    """Empty question or string containing only whitespace must fail validation."""
    with pytest.raises(ValidationError) as exc_empty:
        AskRequest(question="")
    assert "min_length" in str(exc_empty.value) or "at least 1" in str(exc_empty.value)

    with pytest.raises(ValidationError) as exc_blank:
        AskRequest(question="   \t\n  ")
    assert "min_length" in str(exc_blank.value) or "at least 1" in str(exc_blank.value)


def test_ask_request_rejects_extra_fields() -> None:
    """Crucial security check: extra='forbid' must reject unexpected fields."""
    with pytest.raises(ValidationError) as exc:
        AskRequest(
            question="¿Tienen cobertura nacional?",
            injected_field="malicious_payload",
        )
    assert "Extra inputs are not permitted" in str(exc.value)


def test_ask_request_max_length() -> None:
    """Question exceeding 2000 characters must fail validation."""
    oversized = "a" * 2001
    with pytest.raises(ValidationError):
        AskRequest(question=oversized)


def test_ask_response_and_sources_valid() -> None:
    """AskResponse and SourceModel must serialize and validate correctly."""
    source = SourceModel(
        content="Texto de prueba",
        metadata={"source": "manual.md", "page": 1},
        distance=0.18,
    )
    resp = AskResponse(answer="Respuesta válida", sources=[source])
    assert resp.answer == "Respuesta válida"
    assert len(resp.sources) == 1
    assert resp.sources[0].distance == 0.18


# ==============================================================================
# PqrsdCreate tests
# ==============================================================================


def test_pqrsd_create_valid() -> None:
    """PqrsdCreate with all valid fields should succeed."""
    payload = PqrsdCreate(
        tipo_peticion_id=1,
        canal_id=2,
        dependencia_id=3,
        ciudadano_id=uuid4(),
        asunto="Solicitud de copia de guía",
        detalle="Por favor remitir copia de la guía de despacho emitida el día de ayer.",
        fecha_vencimiento=date.today() + timedelta(days=15),
    )
    assert payload.tipo_peticion_id == 1
    assert payload.asunto == "Solicitud de copia de guía"


def test_pqrsd_create_rejects_past_vencimiento() -> None:
    """fecha_vencimiento in the past must be rejected by model validator."""
    past_date = date.today() - timedelta(days=1)
    with pytest.raises(ValidationError) as exc:
        PqrsdCreate(
            tipo_peticion_id=1,
            canal_id=1,
            dependencia_id=1,
            asunto="Asunto válido",
            detalle="Detalle con más de veinte caracteres válidos.",
            fecha_vencimiento=past_date,
        )
    assert "fecha_vencimiento cannot be in the past" in str(exc.value)


def test_pqrsd_create_field_constraints() -> None:
    """Validation of min lengths and positive IDs."""
    # Negative / zero ID
    with pytest.raises(ValidationError):
        PqrsdCreate(
            tipo_peticion_id=0,
            canal_id=1,
            dependencia_id=1,
            asunto="Asunto válido",
            detalle="Detalle con más de veinte caracteres válidos.",
        )

    # Asunto too short (< 5 chars)
    with pytest.raises(ValidationError):
        PqrsdCreate(
            tipo_peticion_id=1,
            canal_id=1,
            dependencia_id=1,
            asunto="Hola",
            detalle="Detalle con más de veinte caracteres válidos.",
        )

    # Detalle too short (< 20 chars)
    with pytest.raises(ValidationError):
        PqrsdCreate(
            tipo_peticion_id=1,
            canal_id=1,
            dependencia_id=1,
            asunto="Asunto válido",
            detalle="Demasiado corto",
        )


def test_pqrsd_create_rejects_extra_fields() -> None:
    """extra='forbid' must reject extra keys in PqrsdCreate."""
    with pytest.raises(ValidationError):
        PqrsdCreate(
            tipo_peticion_id=1,
            canal_id=1,
            dependencia_id=1,
            asunto="Asunto válido",
            detalle="Detalle con más de veinte caracteres válidos.",
            extra_token="invalid",
        )


# ==============================================================================
# PqrsdUpdate and State Machine tests
# ==============================================================================


def test_pqrsd_state_machine_transitions() -> None:
    """Verify allowable state transitions according to SUCCESSOR_STATES."""
    # RECIBIDA transitions
    up_tramite = PqrsdUpdate(estado=EstadoPQRSD.EN_TRAMITE)
    assert up_tramite.transicion_valida(EstadoPQRSD.RECIBIDA) is True

    up_respondida = PqrsdUpdate(
        estado=EstadoPQRSD.RESPONDIDA,
        respuesta="Se resuelve la solicitud de manera favorable al peticionario.",
        respondida_en=datetime.now(),
    )
    # Direct RECIBIDA -> RESPONDIDA is invalid
    assert up_respondida.transicion_valida(EstadoPQRSD.RECIBIDA) is False

    # EN_TRAMITE -> RESPONDIDA is valid
    assert up_respondida.transicion_valida(EstadoPQRSD.EN_TRAMITE) is True

    # Terminal states (CERRADA, ARCHIVADA) have no successors
    assert len(SUCCESSOR_STATES[EstadoPQRSD.CERRADA]) == 0
    assert len(SUCCESSOR_STATES[EstadoPQRSD.ARCHIVADA]) == 0

    assert up_tramite.transicion_valida(EstadoPQRSD.CERRADA) is False
    assert up_tramite.transicion_valida(EstadoPQRSD.ARCHIVADA) is False


def test_pqrsd_update_same_state_is_valid() -> None:
    """Transition to same state or None state should always be valid."""
    update_same = PqrsdUpdate(estado=EstadoPQRSD.EN_TRAMITE)
    assert update_same.transicion_valida(EstadoPQRSD.EN_TRAMITE) is True

    update_no_state = PqrsdUpdate(usuario_responsable_id=uuid4())
    assert update_no_state.transicion_valida(EstadoPQRSD.RECIBIDA) is True


def test_pqrsd_update_respuesta_coherence() -> None:
    """estado 'respondida' requires both respuesta and respondida_en."""
    # Missing respuesta and respondida_en
    with pytest.raises(ValidationError) as exc1:
        PqrsdUpdate(estado=EstadoPQRSD.RESPONDIDA)
    assert "requires both 'respuesta' and 'respondida_en'" in str(exc1.value)

    # Missing respondida_en
    with pytest.raises(ValidationError) as exc2:
        PqrsdUpdate(
            estado=EstadoPQRSD.RESPONDIDA,
            respuesta="Esta es una respuesta suficientemente extensa para el caso.",
        )
    assert "requires both 'respuesta' and 'respondida_en'" in str(exc2.value)

    # Both provided -> valid
    valid_up = PqrsdUpdate(
        estado=EstadoPQRSD.RESPONDIDA,
        respuesta="Esta es una respuesta formal y completa sobre el caso radicado.",
        respondida_en=datetime.now(),
    )
    assert valid_up.estado == EstadoPQRSD.RESPONDIDA


def test_pqrsd_transicion_alias() -> None:
    """PqrsdTransicion should be an alias of PqrsdUpdate."""
    assert PqrsdTransicion is PqrsdUpdate


# ==============================================================================
# Regex and Document Validation tests
# ==============================================================================


@pytest.mark.parametrize(
    "email,expected",
    [
        ("usuario@translogix.com.co", True),
        ("servicio.cliente@dominio.org", True),
        ("test_123+tag@gmail.com", True),
        ("invalido", False),
        ("usuario@", False),
        ("@dominio.com", False),
        ("usuario@dominio", False),
        ("usuario con espacios@dominio.com", False),
    ],
)
def test_email_regex(email: str, expected: bool) -> None:
    """Test EMAIL_REGEX pattern against valid and invalid formats."""
    is_match = bool(re.match(EMAIL_REGEX, email))
    assert is_match == expected


@pytest.mark.parametrize(
    "sha_hash,expected",
    [
        ("a" * 64, True),
        ("0123456789abcdef" * 4, True),
        ("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", True),
        ("A" * 64, False),  # Uppercase not allowed
        ("a" * 63, False),  # Too short
        ("a" * 65, False),  # Too long
        ("g" * 64, False),  # Non-hex characters
    ],
)
def test_sha256_regex(sha_hash: str, expected: bool) -> None:
    """Test SHA256_REGEX pattern against valid and invalid hashes."""
    is_match = bool(re.match(SHA256_REGEX, sha_hash))
    assert is_match == expected


def test_radicado_regex() -> None:
    """Test RADICADO_PQRSD_REGEX pattern."""
    assert bool(re.match(RADICADO_PQRSD_REGEX, "PQRSD-2026-000001")) is True
    assert bool(re.match(RADICADO_PQRSD_REGEX, "PQRSD-2026-123456")) is True
    assert bool(re.match(RADICADO_PQRSD_REGEX, "PQRS-2026-000001")) is False
    assert bool(re.match(RADICADO_PQRSD_REGEX, "PQRSD-26-000001")) is False
    assert bool(re.match(RADICADO_PQRSD_REGEX, "PQRSD-2026-0001")) is False


def test_ciudadano_documento_coherente() -> None:
    """CiudadanoCreate requires tipo_documento and numero_documento together."""
    # Both provided: OK
    c1 = CiudadanoCreate(
        nombres="Carlos",
        apellidos="Gómez",
        tipo_documento="CC",
        numero_documento="123456789",
    )
    assert c1.nombres == "Carlos"

    # Both omitted: OK (anonymous petition)
    c2 = CiudadanoCreate(
        nombres="Anónimo",
        apellidos="Ciudadano",
    )
    assert c2.tipo_documento is None

    # Only tipo_documento provided: Error
    with pytest.raises(ValidationError) as exc1:
        CiudadanoCreate(
            nombres="Carlos",
            apellidos="Gómez",
            tipo_documento="CC",
        )
    assert "must be provided together" in str(exc1.value)

    # Only numero_documento provided: Error
    with pytest.raises(ValidationError) as exc2:
        CiudadanoCreate(
            nombres="Carlos",
            apellidos="Gómez",
            numero_documento="123456789",
        )
    assert "must be provided together" in str(exc2.value)


def test_pqrsd_anexo_create_validation() -> None:
    """PqrsdAnexoCreate validates file size and sha256 hash."""
    valid_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    anexo = PqrsdAnexoCreate(
        nombre_archivo="evidencia.pdf",
        tipo_mime="application/pdf",
        tamano_bytes=1024,
        hash_sha256=valid_hash,
        ruta="/storage/anexos/evidencia.pdf",
    )
    assert anexo.nombre_archivo == "evidencia.pdf"

    # File size <= 0
    with pytest.raises(ValidationError):
        PqrsdAnexoCreate(
            nombre_archivo="evidencia.pdf",
            tipo_mime="application/pdf",
            tamano_bytes=0,
            hash_sha256=valid_hash,
            ruta="/storage/anexos/evidencia.pdf",
        )

    # File size > 10MB
    with pytest.raises(ValidationError):
        PqrsdAnexoCreate(
            nombre_archivo="evidencia.pdf",
            tipo_mime="application/pdf",
            tamano_bytes=10 * 1024 * 1024 + 1,
            hash_sha256=valid_hash,
            ruta="/storage/anexos/evidencia.pdf",
        )
