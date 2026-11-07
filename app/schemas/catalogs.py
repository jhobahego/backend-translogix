"""Pydantic schemas for the catalog tables and service portfolio."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from pydantic import Field

from app.schemas.base import OrmBaseModel


class CanalRead(OrmBaseModel):
    id: int
    codigo: str
    nombre: str
    descripcion: str | None = None
    es_presencial: bool


class TipoPeticionRead(OrmBaseModel):
    id: int
    codigo: str
    nombre: str
    plazo_dias_habiles: int = Field(ge=1, le=60)
    base_legal: str


class DependenciaRead(OrmBaseModel):
    id: int
    codigo: str
    nombre: str
    activa: bool


class CategoriaDiferencialRead(OrmBaseModel):
    id: int
    codigo: str
    nombre: str
    descripcion: str | None = None


class GlosarioTerminoRead(OrmBaseModel):
    id: int
    termino_tecnico: str
    termino_ciudadano: str
    ejemplo: str | None = None


class TramiteRead(OrmBaseModel):
    id: int
    codigo: str
    nombre: str
    descripcion: str | None = None
    dependencia_id: int
    canal_id: int | None = None
    activo: bool


class HorarioAtencionRead(OrmBaseModel):
    dia_semana: int = Field(ge=1, le=7, description="ISO-8601: 1 = Monday, 7 = Sunday")
    hora_inicio: time
    hora_fin: time


class SedeRead(OrmBaseModel):
    id: int
    dependencia_id: int
    nombre: str
    direccion: str
    ciudad: str
    telefono: str | None = None
    activa: bool
    horarios: list[HorarioAtencionRead] = Field(default_factory=list)


class CostoTramiteRead(OrmBaseModel):
    concepto: str
    valor: Decimal = Field(ge=0)
    vigente_desde: date
    vigente_hasta: date | None = None


class RequisitoTramiteRead(OrmBaseModel):
    orden: int = Field(gt=0)
    descripcion: str
    obligatorio: bool
