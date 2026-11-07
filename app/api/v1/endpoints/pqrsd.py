"""HTTP routes for the PQRSD case file.

Body validation runs before any database access, so a malformed payload is
rejected with 422 even when DATABASE_URL is empty. A valid request without
a configured or reachable database degrades to 503.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session, get_pqrsd_repo, get_pqrsd_service
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
from app.services.pqrsd_service import PqrsdService

router = APIRouter(prefix="/pqrsd", tags=["pqrsd"])


def _http_error(exc: RepositoryError) -> HTTPException:
    """Map a domain error to its HTTP status."""
    if isinstance(exc, NotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (Conflict, InvalidTransition)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, RepositoryError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail="Unhandled repository error")


@router.post(
    "",
    response_model=PqrsdRead,
    status_code=status.HTTP_201_CREATED,
    summary="File a PQRSD and get its radicado",
)
def create_pqrsd(
    payload: PqrsdCreate,
    session: Annotated[Session | None, Depends(get_db_session)],
) -> PqrsdRead:
    """Create the case, its first state event and return the assigned radicado."""
    repo = get_pqrsd_repo(session)
    service = get_pqrsd_service(repo)
    try:
        return service.create_case(payload)
    except RepositoryError as exc:
        raise _http_error(exc) from exc


@router.get(
    "",
    response_model=list[PqrsdRead],
    summary="List PQRSD cases with optional filters",
)
def list_pqrsd(
    estado: Annotated[EstadoPQRSD | None, Query(description="Filter by status")] = None,
    dependencia_id: Annotated[int | None, Query(gt=0)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    service: Annotated[PqrsdService, Depends(get_pqrsd_service)] = None,  # type: ignore[assignment]
) -> list[PqrsdRead]:
    """Newest first; the page size is capped at 200 rows."""
    try:
        return service.list_cases(
            estado=estado,
            dependencia_id=dependencia_id,
            limit=limit,
            offset=offset,
        )
    except RepositoryError as exc:
        raise _http_error(exc) from exc


@router.get(
    "/{radicado}",
    response_model=PqrsdRead,
    summary="Read one PQRSD by radicado",
)
def get_pqrsd(
    radicado: str,
    service: Annotated[PqrsdService, Depends(get_pqrsd_service)],
) -> PqrsdRead:
    """Read one PQRSD case with its timeline events and attachments."""
    try:
        return service.get_case(radicado)
    except NotFound as exc:
        raise HTTPException(
            status_code=404, detail=f"PQRSD {radicado!r} not found"
        ) from exc
    except RepositoryError as exc:
        raise _http_error(exc) from exc


@router.patch(
    "/{radicado}",
    response_model=PqrsdRead,
    summary="Move a PQRSD to another status and record the transition",
)
def update_pqrsd(
    radicado: str,
    payload: PqrsdUpdate,
    session: Annotated[Session | None, Depends(get_db_session)],
) -> PqrsdRead:
    """Rejects status changes that skip the allowed state machine."""
    repo = get_pqrsd_repo(session)
    service = get_pqrsd_service(repo)
    try:
        return service.update_case(radicado, payload)
    except RepositoryError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/{radicado}/anexos",
    response_model=PqrsdAnexoRead,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a file hash to an existing PQRSD",
)
def add_anexo(
    radicado: str,
    payload: PqrsdAnexoCreate,
    session: Annotated[Session | None, Depends(get_db_session)],
) -> PqrsdAnexoRead:
    """Attach a verified file hash to the specified case."""
    repo = get_pqrsd_repo(session)
    service = get_pqrsd_service(repo)
    try:
        return service.add_attachment(radicado, payload)
    except RepositoryError as exc:
        raise _http_error(exc) from exc


__all__ = [
    "_http_error",
    "add_anexo",
    "create_pqrsd",
    "get_pqrsd",
    "list_pqrsd",
    "router",
    "update_pqrsd",
]
