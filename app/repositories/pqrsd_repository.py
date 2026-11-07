"""Repository for the PQRSD case file.

Transactions are owned here: each public method commits on success and rolls
back before raising a domain error. SQLAlchemy session handling stays out of
the HTTP presentation layer.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.domain.exceptions import (
    BusinessRuleViolationError,
    DomainError,
    EntityNotFoundError,
    InvalidStateTransitionError,
)
from app.domain.plazos import add_business_days
from app.models.pqrsd import Festivo, Pqrsd, PqrsdAnexo, PqrsdEvento, TipoPeticion
from app.schemas.pqrsd import (
    EstadoPQRSD,
    PqrsdAnexoCreate,
    PqrsdCreate,
    PqrsdUpdate,
)

# Deadlines are at most 60 business days (~86 calendar days); this window is a
# safe bound for loading the holiday catalog for one calculation.
HOLIDAY_WINDOW_DAYS = 120


class RepositoryError(DomainError):
    """Base class for domain errors raised by the repository."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class NotFound(RepositoryError, EntityNotFoundError):
    """The requested entity does not exist."""

    def __init__(
        self, message_or_entity: str, entity_id: str | int | None = None
    ) -> None:
        if entity_id is not None:
            EntityNotFoundError.__init__(self, message_or_entity, entity_id)
            RepositoryError.__init__(self, self.message)
        else:
            DomainError.__init__(self, message_or_entity)
            self.entity_name = "PQRSD"
            self.entity_id = message_or_entity


class Conflict(RepositoryError, BusinessRuleViolationError):
    """A uniqueness or integrity rule rejected the write."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class InvalidTransition(RepositoryError, InvalidStateTransitionError):
    """The requested PQRSD status is not reachable from the current one."""

    def __init__(
        self,
        message_or_current: str,
        target_state: str | None = None,
        reason: str | None = None,
    ) -> None:
        if target_state is not None:
            InvalidStateTransitionError.__init__(
                self, message_or_current, target_state, reason
            )
            RepositoryError.__init__(self, self.message)
        else:
            DomainError.__init__(self, message_or_current)
            self.current_state = ""
            self.target_state = ""
            self.reason = message_or_current


class PqrsdRepository:
    """Data access for PQRSD cases, their state log and their attachments."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def _loaded_query(self) -> Select[tuple[Pqrsd]]:
        return select(Pqrsd).options(
            selectinload(Pqrsd.eventos),
            selectinload(Pqrsd.anexos),
        )

    def get_by_radicado(self, radicado: str) -> Pqrsd | None:
        statement = self._loaded_query().where(Pqrsd.radicado == radicado)
        return self.session.execute(statement).scalar_one_or_none()

    def _reload(self, radicado: str) -> Pqrsd | None:
        """Re-read a case after a commit, overwriting the identity-map copy.

        ``expire_on_commit=False`` (see ``app.core.database``) keeps the loaded
        instance alive, so a plain re-query returns the stale object and the
        selectin-loaded ``eventos`` collection still misses the row the
        transaction just added. ``populate_existing`` forces the reload.
        """
        statement = (
            self._loaded_query()
            .where(Pqrsd.radicado == radicado)
            .execution_options(populate_existing=True)
        )
        return self.session.execute(statement).scalar_one_or_none()

    def list(
        self,
        estado: EstadoPQRSD | None = None,
        dependencia_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Pqrsd]:
        statement = self._loaded_query()
        if estado is not None:
            statement = statement.where(Pqrsd.estado == estado.value)
        if dependencia_id is not None:
            statement = statement.where(Pqrsd.dependencia_id == dependencia_id)
        statement = (
            statement.order_by(Pqrsd.fecha_radicacion.desc())
            .limit(limit)
            .offset(offset)
        )
        return self.session.execute(statement).scalars().all()

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def _holidays(self, start: date) -> set[date]:
        window_end = start + timedelta(days=HOLIDAY_WINDOW_DAYS)
        statement = select(Festivo.fecha).where(
            Festivo.fecha.between(start, window_end)
        )
        return set(self.session.execute(statement).scalars().all())

    def create(self, payload: PqrsdCreate) -> Pqrsd:
        tipo = self.session.get(TipoPeticion, payload.tipo_peticion_id)
        if tipo is None:
            raise NotFound(f"Unknown tipo_peticion_id {payload.tipo_peticion_id}")

        today = date.today()
        vencimiento = payload.fecha_vencimiento or add_business_days(
            today, tipo.plazo_dias_habiles, self._holidays(today)
        )

        case = Pqrsd(
            tipo_peticion_id=payload.tipo_peticion_id,
            canal_id=payload.canal_id,
            dependencia_id=payload.dependencia_id,
            ciudadano_id=str(payload.ciudadano_id) if payload.ciudadano_id else None,
            asunto=payload.asunto,
            detalle=payload.detalle,
            estado=EstadoPQRSD.RECIBIDA.value,
            fecha_vencimiento=vencimiento,
        )
        self.session.add(case)
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise Conflict(
                "The PQRSD violates a uniqueness or foreign key rule"
            ) from exc

        self.session.add(
            PqrsdEvento(
                pqrsd_id=case.id,
                estado_anterior=None,
                estado_nuevo=EstadoPQRSD.RECIBIDA.value,
                nota="Radicación inicial",
            )
        )
        radicado = case.radicado
        if radicado is None:
            self.session.refresh(case)
            radicado = case.radicado
        self.session.commit()

        created = self._reload(radicado)
        if created is None:  # pragma: no cover - the row was just committed
            raise Conflict(
                f"PQRSD {radicado!r} was created but cannot be read back"
            )
        return created

    def update(self, radicado: str, payload: PqrsdUpdate) -> Pqrsd:
        case = self.get_by_radicado(radicado)
        if case is None:
            raise NotFound(f"PQRSD {radicado!r} not found")

        current = EstadoPQRSD(case.estado)
        target = payload.estado
        if target is not None and not payload.transicion_valida(current):
            raise InvalidTransition(
                f"Cannot move a PQRSD from {current.value!r} to {target.value!r}"
            )

        if target is not None and target is not current:
            self.session.add(
                PqrsdEvento(
                    pqrsd_id=case.id,
                    estado_anterior=current.value,
                    estado_nuevo=target.value,
                    usuario_id=(
                        str(payload.usuario_responsable_id)
                        if payload.usuario_responsable_id
                        else None
                    ),
                )
            )
            case.estado = target.value

        if payload.respuesta is not None:
            case.respuesta = payload.respuesta
        if payload.respondida_en is not None:
            case.respondida_en = payload.respondida_en
        if payload.usuario_responsable_id is not None:
            case.usuario_responsable_id = str(payload.usuario_responsable_id)

        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise Conflict(
                "The update violates a check or foreign key rule; "
                "'respondida' requires both respuesta and respondida_en"
            ) from exc

        updated = self._reload(radicado)
        if updated is None:  # pragma: no cover - the row was just committed
            raise NotFound(f"PQRSD {radicado!r} not found after update")
        return updated

    def add_anexo(self, radicado: str, payload: PqrsdAnexoCreate) -> PqrsdAnexo:
        case = self.get_by_radicado(radicado)
        if case is None:
            raise NotFound(f"PQRSD {radicado!r} not found")

        anexo = PqrsdAnexo(
            pqrsd_id=case.id,
            nombre_archivo=payload.nombre_archivo,
            tipo_mime=payload.tipo_mime,
            tamano_bytes=payload.tamano_bytes,
            hash_sha256=payload.hash_sha256,
            ruta=payload.ruta,
        )
        self.session.add(anexo)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise Conflict(
                "The attachment duplicates an existing file hash for this PQRSD"
            ) from exc
        self.session.refresh(anexo)
        return anexo


__all__ = [
    "HOLIDAY_WINDOW_DAYS",
    "Conflict",
    "InvalidTransition",
    "NotFound",
    "PqrsdRepository",
    "RepositoryError",
]
