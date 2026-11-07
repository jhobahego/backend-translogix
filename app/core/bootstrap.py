"""Create the relational schema from the ORM models or from ``db/schema.sql``.

The repository offers two bootstraps for the same database:

``models``
    ``Base.metadata.create_all()`` creates tables, columns, constraints and
    indexes from ``app/models/pqrsd.py``, which is the single source of truth for
    the table shape. The objects SQLAlchemy cannot express portably - the
    ``pg_trgm`` extension, the trigger functions, the triggers and the
    reporting view - are replayed from ``db/schema.sql`` in two phases around
    ``create_all``: the extension and functions must exist before the trigram
    index and the ``next_radicado`` default are created, while triggers and
    views need their tables first.

``script``
    ``db/schema.sql`` is executed verbatim, exactly as ``psql -f`` does. That
    file stays the reference DDL, the artifact ``scripts/check_schema.py``
    validates the models against, and the artifact the Docker entrypoint loads.

Replaying the non-portable objects instead of copying them keeps a single
source for them: adding a trigger or a function to ``db/schema.sql`` is enough
for both paths. A statement the model bootstrap cannot classify raises
``BootstrapError`` rather than being skipped silently.
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import Engine

from app.core import config
from app.models.pqrsd import Base

SCHEMA_SQL = config.REPO_ROOT / "db" / "schema.sql"
SEED_SQL = config.REPO_ROOT / "db" / "seed.sql"

_DOLLAR_TAG = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")
_TRIGGER_NAME = re.compile(r"^create trigger (\w+)\b", re.IGNORECASE)
_TRIGGER_TABLE = re.compile(r"\bon\s+(\w+)\s+for\b", re.IGNORECASE)

# Statements the model path lets create_all own, or that only make sense for
# an interactive psql session.
_IGNORED_PREFIXES = (
    "begin",
    "commit",
    "set ",
    "create table",
    "create index",
    "create unique index",
    "create sequence",
    "alter table",
    "alter sequence",
    "comment on",
)
_BEFORE_TABLES = ("create extension", "create function", "create or replace function")
_AFTER_TABLES = ("create trigger", "create view", "create or replace view")


class BootstrapError(RuntimeError):
    """The schema script contains a statement this module cannot place."""


def _body(statement: str) -> str:
    """Drop leading/trailing ``--`` comment lines and the surrounding blanks."""
    lines = [
        line for line in statement.splitlines() if not line.strip().startswith("--")
    ]
    return "\n".join(lines).strip()


def _head(body: str) -> str:
    """Collapse a statement to its lowercase, whitespace-normalised head."""
    return " ".join(body.split()).lower()


def split_statements(sql: str) -> list[str]:
    """Split SQL text on top-level semicolons.

    Semicolons inside ``$$`` bodies, single-quoted strings and comments do not
    split, which is what makes the trigger functions in ``db/schema.sql`` come
    out as one statement each.
    """
    statements: list[str] = []
    buffer: list[str] = []
    index = 0
    length = len(sql)

    while index < length:
        char = sql[index]

        if char == "-" and sql.startswith("--", index):
            newline = sql.find("\n", index)
            if newline == -1:
                buffer.append(sql[index:])
                break
            buffer.append(sql[index : newline + 1])
            index = newline + 1
            continue

        if char == "/" and sql.startswith("/*", index):
            close = sql.find("*/", index + 2)
            end = length if close == -1 else close + 2
            buffer.append(sql[index:end])
            index = end
            continue

        if char == "'":
            start = index
            index += 1
            while index < length:
                if sql[index] == "'":
                    if index + 1 < length and sql[index + 1] == "'":
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            buffer.append(sql[start:index])
            continue

        if char == "$":
            match = _DOLLAR_TAG.match(sql, index)
            if match:
                tag = match.group(0)
                close = sql.find(tag, match.end())
                end = length if close == -1 else close + len(tag)
                buffer.append(sql[index:end])
                index = end
                continue

        if char == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
            index += 1
            continue

        buffer.append(char)
        index += 1

    tail = "".join(buffer).strip()
    if tail:
        statements.append(tail)
    return statements


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _execute(connection, statement: str) -> None:
    """Run one statement, escaping literal percent signs for the DBAPI.

    psycopg reads ``%`` as a parameter placeholder even when no parameters are
    passed, and the trigger functions raise messages such as
    ``'table %.% is append-only'``. Doubling the sign is the DBAPI-level escape,
    so the server still receives the original text.
    """
    connection.exec_driver_sql(statement.replace("%", "%%"))


def split_objects(sql: str) -> tuple[list[str], list[str]]:
    """Return the statements that must run before and after ``create_all``."""
    before: list[str] = []
    after: list[str] = []

    for raw in split_statements(sql):
        body = _body(raw)
        if not body:
            continue
        head = _head(body)
        if head.startswith(_IGNORED_PREFIXES):
            continue
        if head.startswith(_BEFORE_TABLES):
            before.append(body)
        elif head.startswith(_AFTER_TABLES):
            after.append(body)
        else:
            raise BootstrapError(
                "db/schema.sql contains a statement the model bootstrap cannot "
                f"classify; teach app/core/bootstrap.py where it belongs: {head[:80]!r}"
            )
    return before, after


def _idempotent(body: str) -> str:
    """Make a trigger or view statement safe to replay on an existing schema."""
    head = _head(body)

    if head.startswith("create trigger"):
        name = _TRIGGER_NAME.match(body)
        table = _TRIGGER_TABLE.search(body)
        if not name or not table:
            raise BootstrapError(
                f"cannot make this trigger replayable, check its syntax: {head[:80]!r}"
            )
        return f"drop trigger if exists {name.group(1)} on {table.group(1)};\n{body}"

    if head.startswith("create view"):
        return "create or replace view" + body[len("create view") :]

    return body


def reset(engine: Engine) -> None:
    """Drop every mapped table plus the reporting view, and nothing else."""
    with engine.begin() as connection:
        connection.exec_driver_sql("drop view if exists v_pqrsd_vencidas")
    Base.metadata.drop_all(engine, checkfirst=True)


def create_from_models(engine: Engine) -> dict[str, int]:
    """Create tables with ``create_all`` and replay the non-portable objects."""
    before, after = split_objects(_read(SCHEMA_SQL))

    with engine.begin() as connection:
        for statement in before:
            _execute(connection, statement)

    Base.metadata.create_all(engine)

    with engine.begin() as connection:
        for statement in after:
            _execute(connection, _idempotent(statement))

    return inspect(engine)


def create_from_schema(engine: Engine) -> dict[str, int]:
    """Execute ``db/schema.sql`` statement by statement, as ``psql -f`` would."""
    statements = [
        _body(raw) for raw in split_statements(_read(SCHEMA_SQL))
    ]

    with engine.begin() as connection:
        for statement in statements:
            if not statement:
                continue
            if _head(statement) in {"begin", "commit"}:
                # The context manager already owns the transaction.
                continue
            _execute(connection, statement)

    return inspect(engine)


def load_seed(engine: Engine) -> dict[str, object]:
    """Load ``db/seed.sql`` once; a seeded database is left untouched."""
    with engine.connect() as connection:
        existing = connection.exec_driver_sql(
            "select count(*) from canal_atencion"
        ).scalar_one()

    if existing:
        return {
            "applied": False,
            "reason": f"canal_atencion already holds {existing} rows; use --reset to re-seed",
        }

    statements = [_body(raw) for raw in split_statements(_read(SEED_SQL))]
    with engine.begin() as connection:
        for statement in statements:
            if not statement or _head(statement) in {"begin", "commit"}:
                continue
            _execute(connection, statement)

    return {"applied": True, "reason": "catalogs inserted"}


def inspect(engine: Engine) -> dict[str, int]:
    """Count the objects a complete schema must expose in the public schema."""
    queries = {
        "tables": (
            "select count(*) from information_schema.tables "
            "where table_schema = 'public' and table_type = 'BASE TABLE'"
        ),
        "views": (
            "select count(*) from information_schema.views "
            "where table_schema = 'public'"
        ),
        "triggers": (
            "select count(*) from pg_trigger t "
            "join pg_class c on c.oid = t.tgrelid "
            "join pg_namespace n on n.oid = c.relnamespace "
            "where not t.tgisinternal and n.nspname = 'public'"
        ),
        "functions": (
            "select count(*) from pg_proc p "
            "join pg_namespace n on n.oid = p.pronamespace "
            "where n.nspname = 'public'"
        ),
    }

    with engine.connect() as connection:
        return {
            key: int(connection.exec_driver_sql(sql).scalar_one())
            for key, sql in queries.items()
        }
