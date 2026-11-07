"""PQRSD domain application service.

Coordinates PQRSD use cases, business validation, and conversion between
domain models and Pydantic schemas.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from app.models.pqrsd import Pqrsd, PqrsdAnexo
from app.repositories.pqrsd_repository import (
    Conflict,
    InvalidTransition,
    NotFound,
    PqrsdRepository,
    RepositoryError,
)
from app.schemas.pqrsd import (
    EstadoPQRSD,
    PqrsdAnexoCreate,
    PqrsdAnexoRead,
    PqrsdCreate,
    PqrsdRead,
    PqrsdUpdate,
)


class PqrsdService:
    """Application service for managing PQRSD cases and their lifecycles."""

    def __init__(self, repository: PqrsdRepository | Session) -> None:
        if isinstance(repository, Session):
            self.repository = PqrsdRepository(repository)
        else:
            self.repository = repository

    def get_case(self, radicado: str) -> PqrsdRead:
        """Fetch a single PQRSD case by its radicado identifier.

        Raises:
            NotFound: If the case does not exist.
        """
        case = self.repository.get_by_radicado(radicado)
        if case is None:
            raise NotFound(f"PQRSD {radicado!r} not found")
        return PqrsdRead.model_validate(case)

    def list_cases(
        self,
        estado: EstadoPQRSD | str | None = None,
        dependencia_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PqrsdRead]:
        """List PQRSD cases with optional state and dependency filters."""
        if isinstance(estado, str):
            estado = EstadoPQRSD(estado)

        cases: Sequence[Pqrsd] = self.repository.list(
            estado=estado,
            dependencia_id=dependencia_id,
            limit=limit,
            offset=offset,
        )
        return [PqrsdRead.model_validate(case) for case in cases]

    def create_case(self, payload: PqrsdCreate | dict[str, Any]) -> PqrsdRead:
        """Create a new PQRSD case, assigning radicado and computing deadline."""
        if not isinstance(payload, PqrsdCreate):
            payload = PqrsdCreate.model_validate(payload)

        case: Pqrsd = self.repository.create(payload)
        return PqrsdRead.model_validate(case)

    def update_case(
        self, radicado: str, payload: PqrsdUpdate | dict[str, Any]
    ) -> PqrsdRead:
        """Update case status, response or assigned handler with state machine validation."""
        if not isinstance(payload, PqrsdUpdate):
            payload = PqrsdUpdate.model_validate(payload)

        case: Pqrsd = self.repository.update(radicado, payload)
        return PqrsdRead.model_validate(case)

    def add_attachment(
        self, radicado: str, payload: PqrsdAnexoCreate | dict[str, Any]
    ) -> PqrsdAnexoRead:
        """Attach a SHA-256 verified document to an existing case."""
        if not isinstance(payload, PqrsdAnexoCreate):
            payload = PqrsdAnexoCreate.model_validate(payload)

        anexo: PqrsdAnexo = self.repository.add_anexo(radicado, payload)
        return PqrsdAnexoRead.model_validate(anexo)


__all__ = [
    "Conflict",
    "InvalidTransition",
    "NotFound",
    "PqrsdService",
    "RepositoryError",
]
