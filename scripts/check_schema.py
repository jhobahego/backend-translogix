"""Offline guard for the relational model.

Checks two things without a database server:

1. Every SQLAlchemy table, column and foreign key in ``app/models/pqrsd.py`` is
   present in ``db/schema.sql`` (and the other way around).
2. The Pydantic schemas accept a valid payload and reject the invalid ones that
   matter: unknown fields, malformed email, past due date, half-filled
   document, and a status change without its required fields.

Usage:
    python scripts/check_schema.py

Exit code 0 means no drift and every schema rule still holds.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

VENV_DIR = REPO_ROOT / ".venv"
VENV_PYTHON = VENV_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

SCHEMA_SQL = REPO_ROOT / "db" / "schema.sql"

TABLE_BLOCK = re.compile(r"create table (\w+) \((.*?)\n\);", re.DOTALL)
COLUMN_LINE = re.compile(r"^ {4}([a-z_][a-z0-9_]*)\s", re.MULTILINE)
RESERVED = {
    "check",
    "unique",
    "primary",
    "foreign",
    "constraint",
    "exclude",
    "like",
}


def _running_in_project_venv() -> bool:
    current = os.path.normcase(os.path.abspath(sys.executable))
    target = os.path.normcase(os.path.abspath(VENV_PYTHON))
    if current == target:
        return True
    try:
        return Path(sys.prefix).resolve() == VENV_DIR.resolve()
    except OSError:
        return False


def _ensure_venv_interpreter() -> int | None:
    """Re-exec in the project venv (SQLAlchemy lives there), or return the exit code."""
    if _running_in_project_venv():
        return None
    if VENV_PYTHON.exists():
        completed = subprocess.run(
            [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]],
            cwd=REPO_ROOT,
        )
        return completed.returncode
    print("No .venv found. Run: python scripts/dev.py setup", file=sys.stderr)
    return 1


def parse_sql_schema() -> dict[str, set[str]]:
    text = SCHEMA_SQL.read_text(encoding="utf-8")
    tables: dict[str, set[str]] = {}
    for name, body in TABLE_BLOCK.findall(text):
        columns = {c for c in COLUMN_LINE.findall(body) if c not in RESERVED}
        tables[name] = columns
    return tables


def compare_sql_and_models() -> list[str]:
    from app.models.pqrsd import Base

    problems: list[str] = []
    sql_tables = parse_sql_schema()
    model_tables = {t.name: {c.name for c in t.columns} for t in Base.metadata.tables.values()}

    for name in sorted(set(model_tables) - set(sql_tables)):
        problems.append(f"table '{name}' exists in models but not in db/schema.sql")
    for name in sorted(set(sql_tables) - set(model_tables)):
        problems.append(f"table '{name}' exists in db/schema.sql but not in models")

    for name in sorted(set(model_tables) & set(sql_tables)):
        missing = model_tables[name] - sql_tables[name]
        extra = sql_tables[name] - model_tables[name]
        if missing:
            problems.append(f"table '{name}': columns missing in SQL: {sorted(missing)}")
        if extra:
            problems.append(f"table '{name}': columns missing in models: {sorted(extra)}")

    for table in Base.metadata.tables.values():
        for fk in table.foreign_keys:
            target = fk.column.table.name
            if target not in sql_tables:
                problems.append(f"table '{table.name}': foreign key points to '{target}' not in SQL")

    return problems


def check_pydantic() -> list[str]:
    from pydantic import ValidationError

    from app.schemas.pqrsd import (
        CiudadanoCreate,
        CorrespondenciaCreate,
        EncuestaCreate,
        PqrsdCreate,
        PqrsdUpdate,
        TipoCorrespondencia,
    )

    problems: list[str] = []
    future = date.today() + timedelta(days=10)

    valid = CiudadanoCreate(
        nombres="Ana Maria",
        apellidos="Perez Gomez",
        correo="ana@example.com",
        telefono="+57 300 1234567",
    )
    if valid.nombres != "Ana Maria":
        problems.append("CiudadanoCreate: valid payload was not accepted")

    invalid_cases = [
        ("unknown field", lambda: CiudadanoCreate(nombres="Ana", apellidos="Perez", extra=1)),
        ("bad email", lambda: CiudadanoCreate(nombres="Ana", apellidos="Perez", correo="ana@")),
        (
            "half document",
            lambda: CiudadanoCreate(nombres="Ana", apellidos="Perez", tipo_documento="CC"),
        ),
        (
            "past due date",
            lambda: PqrsdCreate(
                tipo_peticion_id=1,
                canal_id=1,
                dependencia_id=1,
                asunto="Solicitud de copias",
                detalle="Necesito copia del documento radicado la semana pasada.",
                fecha_vencimiento=date.today() - timedelta(days=1),
            ),
        ),
        (
            "respondida without respuesta",
            lambda: PqrsdUpdate(estado="respondida"),
        ),
        ("encuesta without origin", lambda: EncuestaCreate(puntaje=5)),
        (
            "encuesta with two origins",
            lambda: EncuestaCreate(
                atencion_id="00000000-0000-0000-0000-000000000001",
                pqrsd_id="00000000-0000-0000-0000-000000000002",
                puntaje=5,
            ),
        ),
        (
            "received without remitente",
            lambda: CorrespondenciaCreate(
                radicado="AGN-2026-000123",
                tipo=TipoCorrespondencia.RECIBIDA,
                asunto="Radicacion de documentos",
            ),
        ),
    ]

    for label, build in invalid_cases:
        try:
            build()
        except ValidationError:
            continue
        problems.append(f"schema accepted an invalid payload: {label}")

    accepted = PqrsdCreate(
        tipo_peticion_id=1,
        canal_id=1,
        dependencia_id=1,
        asunto="Solicitud de copias",
        detalle="Necesito copia del documento radicado la semana pasada.",
        fecha_vencimiento=future,
    )
    if accepted.fecha_vencimiento != future:
        problems.append("PqrsdCreate: valid payload was not accepted")

    return problems


def check_plazos() -> list[str]:
    """Prove the business-day arithmetic and the optional deadline payload."""
    from pydantic import ValidationError

    from app.domain.plazos import add_business_days
    from app.schemas.pqrsd import PqrsdCreate

    problems: list[str] = []
    friday = date(2026, 11, 6)
    monday = date(2026, 11, 9)

    if add_business_days(friday, 1) != monday:
        problems.append("add_business_days: Friday + 1 business day must be Monday")
    if add_business_days(monday, 5) != date(2026, 11, 16):
        problems.append("add_business_days: Monday + 5 business days must be the next Monday")
    if add_business_days(monday, 5, {date(2026, 11, 16)}) != date(2026, 11, 17):
        problems.append("add_business_days: holidays must be skipped")

    try:
        add_business_days(friday, 0)
    except ValueError:
        pass
    else:
        problems.append("add_business_days accepted days=0")

    try:
        PqrsdCreate(
            tipo_peticion_id=1,
            canal_id=1,
            dependencia_id=1,
            asunto="Solicitud de copias",
            detalle="Necesito copia del documento radicado la semana pasada.",
        )
    except ValidationError as exc:
        problems.append(f"PqrsdCreate rejected the API-computed deadline: {exc}")

    return problems


def main() -> int:
    venv_exit = _ensure_venv_interpreter()
    if venv_exit is not None:
        return venv_exit

    problems = compare_sql_and_models()
    problems.extend(check_pydantic())
    problems.extend(check_plazos())

    if problems:
        for problem in problems:
            print(f"FAIL: {problem}")
        print(f"{len(problems)} problem(s) found")
        return 1

    from app.models.pqrsd import Base

    sql_tables = parse_sql_schema()
    columns = sum(len(cols) for cols in sql_tables.values())
    print(f"PASS: {len(Base.metadata.tables)} tables and {columns} columns match db/schema.sql")
    print("PASS: Pydantic schemas reject the invalid payloads and accept the valid ones")
    print("PASS: business-day deadlines skip weekends and holidays")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
