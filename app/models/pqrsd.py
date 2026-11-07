"""SQLAlchemy 2.0 models for the citizen-service relational schema.

Scope: tables, columns, unique/foreign-key/check constraints and indexes.
Triggers (``pqrsd`` radicado immutability, append-only event log, audit trail),
the ``next_radicado`` function, the reporting view and the row-level-security
policy are defined only in ``db/schema.sql``.

Identifiers use the domain language of the manuals (Spanish nouns) because
they are business vocabulary; docstrings and comments stay in English.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

EMAIL_REGEX = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
SHA256_REGEX = r"^[a-f0-9]{64}$"
RADICADO_REGEX = r"^PQRSD-[0-9]{4}-[0-9]{6}$"

ESTADOS_PQRSD = ("recibida", "en_tramite", "respondida", "vencida", "cerrada", "archivada")


class Base(DeclarativeBase):
    """Declarative base carrying the constraint naming convention."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """Creation and update timestamps maintained by ``set_updated_at``."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Catalogs
# ---------------------------------------------------------------------------


class Dependencia(Base, TimestampMixin):
    __tablename__ = "dependencia"

    id: Mapped[int] = mapped_column(SmallInteger, Identity(always=True), primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    sedes: Mapped[list["Sede"]] = relationship(back_populates="dependencia")
    tramites: Mapped[list["Tramite"]] = relationship(back_populates="dependencia")


class CanalAtencion(Base):
    __tablename__ = "canal_atencion"

    id: Mapped[int] = mapped_column(SmallInteger, Identity(always=True), primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    es_presencial: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )


class TipoPeticion(Base):
    __tablename__ = "tipo_peticion"
    __table_args__ = (
        CheckConstraint(
            "plazo_dias_habiles between 1 and 60", name="plazo_dias_habiles_range"
        ),
    )

    id: Mapped[int] = mapped_column(SmallInteger, Identity(always=True), primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    plazo_dias_habiles: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    base_legal: Mapped[str] = mapped_column(Text, nullable=False)


class Festivo(Base):
    __tablename__ = "festivo"

    fecha: Mapped[date] = mapped_column(Date, primary_key=True)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)


class CategoriaDiferencial(Base):
    __tablename__ = "categoria_diferencial"

    id: Mapped[int] = mapped_column(SmallInteger, Identity(always=True), primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)


class AtributoServicio(Base):
    __tablename__ = "atributo_servicio"

    id: Mapped[int] = mapped_column(SmallInteger, Identity(always=True), primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)


class GlosarioTermino(Base):
    __tablename__ = "glosario_termino"

    id: Mapped[int] = mapped_column(SmallInteger, Identity(always=True), primary_key=True)
    termino_tecnico: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    termino_ciudadano: Mapped[str] = mapped_column(Text, nullable=False)
    ejemplo: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Organization and service points
# ---------------------------------------------------------------------------


class Sede(Base, TimestampMixin):
    __tablename__ = "sede"
    __table_args__ = (UniqueConstraint("dependencia_id", "nombre"),)

    id: Mapped[int] = mapped_column(SmallInteger, Identity(always=True), primary_key=True)
    dependencia_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("dependencia.id"), nullable=False
    )
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    direccion: Mapped[str] = mapped_column(Text, nullable=False)
    ciudad: Mapped[str] = mapped_column(Text, nullable=False)
    telefono: Mapped[str | None] = mapped_column(Text)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    dependencia: Mapped[Dependencia] = relationship(back_populates="sedes")
    horarios: Mapped[list["HorarioAtencion"]] = relationship(
        back_populates="sede", cascade="all, delete-orphan"
    )


class HorarioAtencion(Base):
    __tablename__ = "horario_atencion"
    __table_args__ = (
        CheckConstraint("dia_semana between 1 and 7", name="dia_semana_range"),
        CheckConstraint("hora_fin > hora_inicio", name="rango_horario"),
        UniqueConstraint("sede_id", "dia_semana", "hora_inicio"),
    )

    id: Mapped[int] = mapped_column(SmallInteger, Identity(always=True), primary_key=True)
    sede_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("sede.id", ondelete="CASCADE"), nullable=False
    )
    dia_semana: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    hora_inicio: Mapped[time] = mapped_column(Time, nullable=False)
    hora_fin: Mapped[time] = mapped_column(Time, nullable=False)

    sede: Mapped[Sede] = relationship(back_populates="horarios")


class CanalSede(Base):
    """Contact value of a channel for a specific site."""

    __tablename__ = "canal_sede"

    canal_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("canal_atencion.id"), primary_key=True
    )
    sede_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("sede.id", ondelete="CASCADE"), primary_key=True
    )
    valor: Mapped[str] = mapped_column(Text, primary_key=True)


# ---------------------------------------------------------------------------
# Service portfolio
# ---------------------------------------------------------------------------


class Tramite(Base, TimestampMixin):
    __tablename__ = "tramite"

    id: Mapped[int] = mapped_column(SmallInteger, Identity(always=True), primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    dependencia_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("dependencia.id"), nullable=False
    )
    canal_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("canal_atencion.id")
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    dependencia: Mapped[Dependencia] = relationship(back_populates="tramites")
    requisitos: Mapped[list["RequisitoTramite"]] = relationship(
        back_populates="tramite", cascade="all, delete-orphan"
    )
    costos: Mapped[list["CostoTramite"]] = relationship(
        back_populates="tramite", cascade="all, delete-orphan"
    )


class RequisitoTramite(Base):
    __tablename__ = "requisito_tramite"
    __table_args__ = (
        CheckConstraint("orden > 0", name="orden_positivo"),
        UniqueConstraint("tramite_id", "orden"),
    )

    id: Mapped[int] = mapped_column(SmallInteger, Identity(always=True), primary_key=True)
    tramite_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("tramite.id", ondelete="CASCADE"), nullable=False
    )
    orden: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    obligatorio: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    tramite: Mapped[Tramite] = relationship(back_populates="requisitos")


class CostoTramite(Base):
    __tablename__ = "costo_tramite"
    __table_args__ = (
        CheckConstraint("valor >= 0", name="valor_no_negativo"),
        CheckConstraint(
            "vigente_hasta is null or vigente_hasta >= vigente_desde", name="vigencia_coherente"
        ),
    )

    id: Mapped[int] = mapped_column(SmallInteger, Identity(always=True), primary_key=True)
    tramite_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("tramite.id", ondelete="CASCADE"), nullable=False
    )
    concepto: Mapped[str] = mapped_column(Text, nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    vigente_desde: Mapped[date] = mapped_column(Date, nullable=False)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)

    tramite: Mapped[Tramite] = relationship(back_populates="costos")


# ---------------------------------------------------------------------------
# People and access control
# ---------------------------------------------------------------------------


class Ciudadano(Base, TimestampMixin):
    __tablename__ = "ciudadano"
    __table_args__ = (
        CheckConstraint(
            "(tipo_documento is null) = (numero_documento is null)", name="documento_coherente"
        ),
        CheckConstraint(f"correo is null or correo ~* '{EMAIL_REGEX}'", name="email_format"),
        CheckConstraint(
            "telefono is null or telefono ~ '^[0-9+() -]{7,20}$'", name="telefono_format"
        ),
        Index(
            "ciudadano_documento_uq",
            "tipo_documento",
            "numero_documento",
            unique=True,
            postgresql_where=text("numero_documento is not null"),
        ),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    tipo_documento: Mapped[str | None] = mapped_column(Text)
    numero_documento: Mapped[str | None] = mapped_column(Text)
    nombres: Mapped[str] = mapped_column(Text, nullable=False)
    apellidos: Mapped[str] = mapped_column(Text, nullable=False)
    correo: Mapped[str | None] = mapped_column(Text)
    telefono: Mapped[str | None] = mapped_column(Text)
    autoriza_datos: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )


class Usuario(Base, TimestampMixin):
    __tablename__ = "usuario"
    __table_args__ = (
        CheckConstraint(f"correo ~* '{EMAIL_REGEX}'", name="email_format"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    dependencia_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("dependencia.id"), nullable=False
    )
    correo: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    hash_password: Mapped[str] = mapped_column(Text, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    roles: Mapped[list["Rol"]] = relationship(
        secondary="usuario_rol", back_populates="usuarios", viewonly=True
    )


class Rol(Base):
    __tablename__ = "rol"

    id: Mapped[int] = mapped_column(SmallInteger, Identity(always=True), primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)

    usuarios: Mapped[list[Usuario]] = relationship(
        secondary="usuario_rol", back_populates="roles", viewonly=True
    )


class UsuarioRol(Base):
    __tablename__ = "usuario_rol"

    usuario_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True
    )
    rol_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("rol.id", ondelete="CASCADE"), primary_key=True
    )


class Sesion(Base):
    __tablename__ = "sesion"
    __table_args__ = (
        CheckConstraint("expira_en > emitida_en", name="vigencia_coherente"),
        Index("sesion_usuario_idx", "usuario_id", "expira_en"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    usuario_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False
    )
    emitida_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revocada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Case file: PQRSD
# ---------------------------------------------------------------------------


class SecuenciaRadicado(Base):
    """Yearly correlative for the radicado."""

    __tablename__ = "secuencia_radicado"
    __table_args__ = (CheckConstraint("ultimo >= 0", name="ultimo_no_negativo"),)

    vigencia: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    ultimo: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))


class Pqrsd(Base, TimestampMixin):
    __tablename__ = "pqrsd"
    __table_args__ = (
        CheckConstraint("char_length(asunto) between 5 and 200", name="asunto_longitud"),
        CheckConstraint("char_length(detalle) >= 20", name="detalle_longitud"),
        CheckConstraint(
            "estado in ('recibida', 'en_tramite', 'respondida', 'vencida', 'cerrada', 'archivada')",
            name="estado_valido",
        ),
        CheckConstraint(
            "respondida_en is null or respondida_en >= fecha_radicacion",
            name="respondida_despues_de_radicada",
        ),
        CheckConstraint(
            "estado <> 'respondida' or (respondida_en is not null and respuesta is not null)",
            name="respuesta_completa",
        ),
        CheckConstraint(f"radicado ~ '{RADICADO_REGEX}'", name="radicado_format"),
        Index(
            "pqrsd_vencimiento_idx",
            "estado",
            "fecha_vencimiento",
            postgresql_where=text("estado in ('recibida', 'en_tramite')"),
        ),
        Index("pqrsd_dependencia_idx", "dependencia_id", "estado"),
        Index(
            "pqrsd_ciudadano_idx",
            "ciudadano_id",
            postgresql_where=text("ciudadano_id is not null"),
        ),
        Index(
            "pqrsd_asunto_trgm_idx",
            "asunto",
            postgresql_using="gin",
            postgresql_ops={"asunto": "gin_trgm_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    radicado: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
        server_default=text("next_radicado(extract(year from now())::integer)"),
    )
    tipo_peticion_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("tipo_peticion.id"), nullable=False
    )
    canal_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("canal_atencion.id"), nullable=False
    )
    dependencia_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("dependencia.id"), nullable=False
    )
    ciudadano_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("ciudadano.id")
    )
    usuario_responsable_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("usuario.id")
    )
    asunto: Mapped[str] = mapped_column(Text, nullable=False)
    detalle: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'recibida'"))
    fecha_radicacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fecha_vencimiento: Mapped[date] = mapped_column(Date, nullable=False)
    respondida_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    respuesta: Mapped[str | None] = mapped_column(Text)

    eventos: Mapped[list["PqrsdEvento"]] = relationship(
        back_populates="pqrsd", cascade="all, delete-orphan", order_by="PqrsdEvento.ocurrido_en"
    )
    anexos: Mapped[list["PqrsdAnexo"]] = relationship(
        back_populates="pqrsd", cascade="all, delete-orphan"
    )


class PqrsdEvento(Base):
    """Append-only state transition log; enforced by a trigger."""

    __tablename__ = "pqrsd_evento"
    __table_args__ = (
        CheckConstraint(
            "estado_anterior is null or estado_anterior <> estado_nuevo",
            name="transicion_real",
        ),
        Index("pqrsd_evento_pqrsd_idx", "pqrsd_id", "ocurrido_en"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    pqrsd_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("pqrsd.id", ondelete="CASCADE"), nullable=False
    )
    estado_anterior: Mapped[str | None] = mapped_column(Text)
    estado_nuevo: Mapped[str] = mapped_column(Text, nullable=False)
    usuario_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("usuario.id")
    )
    nota: Mapped[str | None] = mapped_column(Text)
    ocurrido_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    pqrsd: Mapped[Pqrsd] = relationship(back_populates="eventos")


class PqrsdAnexo(Base):
    __tablename__ = "pqrsd_anexo"
    __table_args__ = (
        CheckConstraint(
            "tamano_bytes > 0 and tamano_bytes <= 10485760", name="tamano_valido"
        ),
        CheckConstraint(f"hash_sha256 ~ '{SHA256_REGEX}'", name="hash_format"),
        UniqueConstraint("pqrsd_id", "hash_sha256"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    pqrsd_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("pqrsd.id", ondelete="CASCADE"), nullable=False
    )
    nombre_archivo: Mapped[str] = mapped_column(Text, nullable=False)
    tipo_mime: Mapped[str] = mapped_column(Text, nullable=False)
    tamano_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hash_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    ruta: Mapped[str] = mapped_column(Text, nullable=False)
    subido_por: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("usuario.id")
    )
    subido_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    pqrsd: Mapped[Pqrsd] = relationship(back_populates="anexos")


# ---------------------------------------------------------------------------
# Attention sessions and satisfaction
# ---------------------------------------------------------------------------


class Atencion(Base):
    __tablename__ = "atencion"
    __table_args__ = (
        CheckConstraint("char_length(motivo) between 5 and 300", name="motivo_longitud"),
        CheckConstraint(
            "finalizada_en is null or finalizada_en >= iniciada_en", name="fin_despues_de_inicio"
        ),
        Index("atencion_sede_idx", "sede_id", "iniciada_en"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    sede_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("sede.id"), nullable=False)
    canal_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("canal_atencion.id"), nullable=False
    )
    ciudadano_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("ciudadano.id")
    )
    categoria_diferencial_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("categoria_diferencial.id")
    )
    atendida_por: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("usuario.id")
    )
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    iniciada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finalizada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duracion_segundos: Mapped[int | None] = mapped_column(
        Integer,
        Computed(
            "extract(epoch from (finalizada_en - iniciada_en))::integer", persisted=True
        ),
    )


class EncuestaSatisfaccion(Base):
    __tablename__ = "encuesta_satisfaccion"
    __table_args__ = (
        CheckConstraint("puntaje between 1 and 5", name="puntaje_range"),
        CheckConstraint("char_length(comentario) <= 1000", name="comentario_longitud"),
        CheckConstraint("num_nonnulls(atencion_id, pqrsd_id) = 1", name="un_solo_origen"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    atencion_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("atencion.id", ondelete="CASCADE")
    )
    pqrsd_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("pqrsd.id", ondelete="CASCADE")
    )
    puntaje: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comentario: Mapped[str | None] = mapped_column(Text)
    enviada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Postal and email correspondence
# ---------------------------------------------------------------------------


class Correspondencia(Base):
    __tablename__ = "correspondencia"
    __table_args__ = (
        CheckConstraint("radicado ~ '^[A-Z0-9-]{6,32}$'", name="radicado_format"),
        CheckConstraint("tipo in ('recibida', 'despachada')", name="tipo_valido"),
        CheckConstraint("folios > 0", name="folios_positivo"),
        CheckConstraint(
            "tipo <> 'recibida' or remitente is not null", name="remitente_requerido"
        ),
        CheckConstraint(
            "tipo <> 'despachada' or destinatario is not null", name="destinatario_requerido"
        ),
        Index("correspondencia_tipo_idx", "tipo", "registrada_en"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    radicado: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    tipo: Mapped[str] = mapped_column(Text, nullable=False)
    remitente: Mapped[str | None] = mapped_column(Text)
    destinatario: Mapped[str | None] = mapped_column(Text)
    asunto: Mapped[str] = mapped_column(Text, nullable=False)
    folios: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    planilla: Mapped[str | None] = mapped_column(Text)
    canal_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("canal_atencion.id")
    )
    registrada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    registrada_por: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("usuario.id")
    )


# ---------------------------------------------------------------------------
# Operations: normative versions, query metrics, audit trail
# ---------------------------------------------------------------------------


class DocumentoNormativo(Base):
    __tablename__ = "documento_normativo"
    __table_args__ = (
        CheckConstraint(f"hash_sha256 ~ '{SHA256_REGEX}'", name="hash_format"),
        UniqueConstraint("nombre", "version"),
    )

    id: Mapped[int] = mapped_column(SmallInteger, Identity(always=True), primary_key=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    vigente_desde: Mapped[date] = mapped_column(Date, nullable=False)
    hash_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    ruta: Mapped[str] = mapped_column(Text, nullable=False)


class ConsultaLog(Base):
    """Latency metrics for the local model; the question is only hashed."""

    __tablename__ = "consulta_log"
    __table_args__ = (
        CheckConstraint("latencia_ms > 0", name="latencia_positiva"),
        CheckConstraint("fuentes >= 0", name="fuentes_no_negativas"),
        Index("consulta_log_fecha_idx", "ocurrida_en"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    pregunta_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    modelo: Mapped[str] = mapped_column(Text, nullable=False)
    latencia_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    tuvo_contexto: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fuentes: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    ocurrida_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Auditoria(Base):
    __tablename__ = "auditoria"
    __table_args__ = (
        CheckConstraint("operacion in ('insert', 'update', 'delete')", name="operacion_valida"),
        Index("auditoria_tabla_idx", "tabla", "ocurrida_en"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    tabla: Mapped[str] = mapped_column(Text, nullable=False)
    operacion: Mapped[str] = mapped_column(Text, nullable=False)
    registro_id: Mapped[str] = mapped_column(Text, nullable=False)
    usuario_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("usuario.id")
    )
    datos: Mapped[dict | None] = mapped_column(JSONB)
    ocurrida_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
