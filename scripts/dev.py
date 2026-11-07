"""Cross-platform development CLI for the local RAG service.

Run from the repository root with any Python 3.10+ interpreter:

    python scripts/dev.py <command> [options]

Only the standard library is imported at module level. Commands other than
``setup`` re-execute this script with the repository ``.venv`` interpreter
when one exists, so activating the virtual environment is never required.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENV_DIR = REPO_ROOT / ".venv"
VENV_PYTHON = VENV_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
REQUIREMENTS = REPO_ROOT / "requirements.txt"
ENV_FILE = REPO_ROOT / ".env"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

# Running this file by path puts scripts/ on sys.path, not the repository root.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

EPILOG = """\
commands:
  setup   Create .venv, install requirements.txt, and create .env if missing.
  models  Pull the configured chat and embedding models from Ollama.
  ingest  Rebuild the vector index (extra args go to python -m app.services.ingest_service).
  api     Run uvicorn on API_PORT (extra args go to uvicorn).
  smoke   Run end-to-end HTTP checks against a running API.
  check   Verify Ollama, models, compileall, and docker compose config.
  rubric  Run the KODO TAKAI rubric bench (see scripts/rubric_check.py).
  db-init Create the relational schema from the models or from db/schema.sql.
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cross-platform development CLI for the local RAG service.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    subparsers.add_parser(
        "setup",
        help="create .venv, install dependencies, and create .env if missing",
    )

    subparsers.add_parser(
        "models",
        help="pull the configured chat and embedding models",
    )

    ingest = subparsers.add_parser(
        "ingest",
        help="rebuild the vector index from knowledge_base/",
    )
    ingest.add_argument(
        "--reset",
        action="store_true",
        help="delete and recreate the collection before indexing",
    )

    api = subparsers.add_parser(
        "api",
        help="start the API with uvicorn",
    )
    api.add_argument(
        "--host",
        default=None,
        help="interface to bind; uvicorn defaults to 127.0.0.1",
    )
    api.add_argument(
        "--port",
        type=int,
        default=None,
        help="port to bind; defaults to API_PORT from app.core.config",
    )
    api.add_argument(
        "--reload",
        action="store_true",
        help="reload the server when source files change",
    )

    smoke = subparsers.add_parser(
        "smoke",
        help="run end-to-end checks against a running API",
    )
    smoke.add_argument(
        "--url",
        default=None,
        help="base URL; defaults to API_URL or http://localhost:API_PORT",
    )

    subparsers.add_parser(
        "check",
        help="verify Ollama, models, source compilation, and compose config",
    )

    subparsers.add_parser(
        "rubric",
        help="run the KODO TAKAI rubric bench (extra args go to the script)",
    )

    db_init = subparsers.add_parser(
        "db-init",
        help="create the relational schema (models by default, DDL on request)",
    )
    db_init.add_argument(
        "--from-schema",
        action="store_true",
        help="run db/schema.sql instead of creating the tables from the models",
    )
    db_init.add_argument(
        "--seed",
        action="store_true",
        help="load db/seed.sql catalogs when the database is still empty",
    )
    db_init.add_argument(
        "--reset",
        action="store_true",
        help="drop every mapped table and the reporting view before creating",
    )
    db_init.add_argument(
        "--database-url",
        default=None,
        help="override DATABASE_URL for this run only",
    )

    return parser


def _running_in_project_venv() -> bool:
    """Whether the current interpreter belongs to the repository .venv."""
    current = os.path.normcase(os.path.abspath(sys.executable))
    target = os.path.normcase(os.path.abspath(VENV_PYTHON))
    if current == target:
        return True
    try:
        return Path(sys.prefix).resolve() == VENV_DIR.resolve()
    except OSError:
        return False


def _ensure_venv_interpreter() -> int | None:
    """Re-exec in the project venv, or return an exit code on failure."""
    if _running_in_project_venv():
        return None
    if VENV_PYTHON.exists():
        completed = subprocess.run(
            [
                str(VENV_PYTHON),
                str(Path(__file__).resolve()),
                *sys.argv[1:],
            ],
            cwd=REPO_ROOT,
        )
        return completed.returncode
    print("No .venv found. Run: python scripts/dev.py setup", file=sys.stderr)
    return 1


def _setup(_args: argparse.Namespace, _extras: list[str]) -> int:
    """Create the venv, install dependencies, and seed .env."""
    if not VENV_PYTHON.exists():
        print(f"Creating virtual environment in {VENV_DIR} ...")
        completed = subprocess.run(
            [sys.executable, "-m", "venv", str(VENV_DIR)],
            cwd=REPO_ROOT,
        )
        if completed.returncode != 0:
            print("FAIL: could not create .venv", file=sys.stderr)
            return completed.returncode
        if not VENV_PYTHON.exists():
            print("FAIL: virtual environment interpreter was not created", file=sys.stderr)
            return 1

    print(f"Installing dependencies from {REQUIREMENTS.name} ...")
    completed = subprocess.run(
        [str(VENV_PYTHON), "-m", "pip", "install", "-r", str(REQUIREMENTS)],
        cwd=REPO_ROOT,
    )
    if completed.returncode != 0:
        print("FAIL: dependency installation failed", file=sys.stderr)
        return completed.returncode

    if not ENV_FILE.exists() and ENV_EXAMPLE.exists():
        shutil.copyfile(ENV_EXAMPLE, ENV_FILE)
        print(f"Created {ENV_FILE.name} from {ENV_EXAMPLE.name}.")

    print("Setup complete. Next commands:")
    print("  python scripts/dev.py models")
    print("  python scripts/dev.py ingest")
    print("  python scripts/dev.py api")
    return 0


def _models(_args: argparse.Namespace, _extras: list[str]) -> int:
    """Pull the configured chat and embedding models from Ollama."""
    import httpx
    import ollama

    from app.core import config

    client = ollama.Client(host=config.OLLAMA_BASE_URL)
    for model in (config.OLLAMA_MODEL, config.OLLAMA_EMBED_MODEL):
        print(f"Pulling {model} ...")
        last_status = None
        try:
            for progress in client.pull(model, stream=True):
                status = getattr(progress, "status", None)
                if isinstance(status, str) and status != last_status:
                    print(f"  {status}")
                    last_status = status
        except (ConnectionError, ollama.ResponseError, httpx.HTTPError) as exc:
            print(f"FAIL: could not pull {model!r}: {exc}", file=sys.stderr)
            print(
                "FAIL: Ollama is not reachable. Start it with 'ollama serve' or "
                "'docker compose up -d', then retry.",
                file=sys.stderr,
            )
            return 1
    print("PASS: models are ready")
    return 0


def _ingest(args: argparse.Namespace, extras: list[str]) -> int:
    """Run the ingestion module, forwarding --reset and extra arguments."""
    command = [sys.executable, "-m", "app.services.ingest_service"]
    if args.reset:
        command.append("--reset")
    command.extend(extras)
    return subprocess.run(command, cwd=REPO_ROOT).returncode


def _api(args: argparse.Namespace, extras: list[str]) -> int:
    """Run uvicorn in the foreground with the configured port."""
    from app.core import config

    port = args.port if args.port is not None else config.API_PORT
    command = [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)]
    if args.host is not None:
        command.extend(["--host", args.host])
    if args.reload:
        command.append("--reload")
    command.extend(extras)
    try:
        return subprocess.run(command, cwd=REPO_ROOT).returncode
    except KeyboardInterrupt:
        return 0


def _smoke(args: argparse.Namespace, _extras: list[str]) -> int:
    """Run end-to-end HTTP checks against a running API."""
    import httpx

    from app.core import config

    base = (
        args.url
        or os.getenv("API_URL")
        or f"http://localhost:{config.API_PORT}"
    ).rstrip("/")
    on_domain = {"question": "¿Cuál es el horario de atención?"}
    failures = 0

    def record_pass(message: str) -> None:
        print(f"PASS: {message}")

    def record_fail(message: str) -> None:
        nonlocal failures
        failures += 1
        print(f"FAIL: {message}")

    def decode(response: httpx.Response) -> object | None:
        try:
            return response.json()
        except ValueError:
            return None

    with httpx.Client(
        base_url=base,
        timeout=httpx.Timeout(400.0, connect=10.0),
    ) as client:
        # (a) Health: reachable and the index is not empty.
        try:
            response = client.get("/health", timeout=10.0)
            response.raise_for_status()
            health = decode(response)
        except httpx.HTTPError as exc:
            record_fail(f"(a) /health is unreachable at {base}: {exc}")
            print(
                "FAIL: start the API with 'python scripts/dev.py api', then run: "
                "python scripts/dev.py ingest"
            )
            return 1

        chunks = 0
        if isinstance(health, dict):
            try:
                chunks = int(health.get("kb_chunks", 0))
            except (TypeError, ValueError):
                chunks = 0
        if chunks <= 0:
            record_fail(f"(a) /health reports no indexed chunks: {health}")
            print("FAIL: run: python scripts/dev.py ingest")
            return 1
        record_pass("(a) /health reports kb_chunks > 0")

        # (b) On-domain question: answer and sources must be non-empty.
        try:
            response = client.post("/api/v1/ask", json=on_domain)
            response.raise_for_status()
            payload = decode(response)
        except httpx.HTTPError as exc:
            record_fail(f"(b) /api/v1/ask failed for an on-domain question: {exc}")
        else:
            if (
                isinstance(payload, dict)
                and str(payload.get("answer") or "").strip()
                and isinstance(payload.get("sources"), list)
                and payload["sources"]
            ):
                record_pass("(b) /api/v1/ask answers an on-domain question with sources")
            else:
                record_fail(
                    f"(b) /api/v1/ask returned an incomplete answer: {payload}"
                )

        # (c) Off-domain question: refusal with no sources.
        try:
            response = client.post(
                "/api/v1/ask",
                json={"question": "¿Quién ganó el mundial de fútbol?"},
            )
            response.raise_for_status()
            payload = decode(response)
        except httpx.HTTPError as exc:
            record_fail(f"(c) /api/v1/ask failed for an off-domain question: {exc}")
        else:
            if (
                isinstance(payload, dict)
                and payload.get("sources") == []
                and "No tengo esa información" in str(payload.get("answer") or "")
            ):
                record_pass("(c) /api/v1/ask refuses an off-domain question with no sources")
            else:
                record_fail(
                    f"(c) /api/v1/ask did not return the expected refusal: {payload}"
                )

        # (d) Streaming endpoint: plain text body must be non-empty.
        try:
            response = client.post("/api/v1/ask/stream", json=on_domain)
            response.raise_for_status()
            body = response.text
        except httpx.HTTPError as exc:
            record_fail(f"(d) /api/v1/ask/stream failed: {exc}")
        else:
            if body.strip():
                record_pass("(d) /api/v1/ask/stream returns a non-empty body")
            else:
                record_fail("(d) /api/v1/ask/stream returned an empty body")

        # (e) Unknown category: HTTP 422 with the indexed values listed.
        categories: list = []
        try:
            response = client.post(
                "/api/v1/ask",
                json={"question": on_domain["question"], "categoria": "string"},
                timeout=10.0,
            )
            status = response.status_code
            payload = decode(response)
        except httpx.HTTPError as exc:
            record_fail(f"(e) /api/v1/ask failed for an unknown categoria: {exc}")
        else:
            if status == 422:
                record_pass("(e) /api/v1/ask rejects an unknown categoria with 422")
            else:
                record_fail(
                    f"(e) /api/v1/ask returned HTTP {status} for an unknown categoria"
                )
            detail = payload.get("detail") if isinstance(payload, dict) else None
            raw_categories = (
                detail.get("available_categories")
                if isinstance(detail, dict)
                else None
            )
            if isinstance(raw_categories, list) and raw_categories:
                categories = raw_categories
                record_pass("(e) 422 detail lists the available categories")
            else:
                record_fail(
                    f"(e) 422 detail did not list available categories: {payload}"
                )

        # (f) A category read from the 422 payload must return sources.
        if not categories:
            record_fail("(f) no available category could be read from the 422 payload")
        else:
            category = next(
                (item for item in categories if "FAQ" in str(item)),
                categories[0],
            )
            try:
                response = client.post(
                    "/api/v1/ask",
                    json={"question": on_domain["question"], "categoria": category},
                )
                response.raise_for_status()
                payload = decode(response)
            except httpx.HTTPError as exc:
                record_fail(
                    f"(f) /api/v1/ask failed for categoria {category!r}: {exc}"
                )
            else:
                if (
                    isinstance(payload, dict)
                    and isinstance(payload.get("sources"), list)
                    and payload["sources"]
                ):
                    record_pass(
                        f"(f) /api/v1/ask returns sources for categoria {category!r}"
                    )
                else:
                    record_fail(
                        f"(f) /api/v1/ask returned no sources for {category!r}: {payload}"
                    )

    if failures:
        print("FAIL: smoke test had failures")
        return 1
    print("PASS: smoke test completed")
    return 0


def _check(_args: argparse.Namespace, _extras: list[str]) -> int:
    """Verify Ollama, configured models, sources, and optional Docker."""
    import compileall
    import platform

    import httpx

    from app.core import config

    failures = 0
    print(f"Python {platform.python_version()} ({sys.executable})")
    base = config.OLLAMA_BASE_URL.rstrip("/")

    with httpx.Client(timeout=5.0) as client:
        try:
            response = client.get(f"{base}/api/version")
            response.raise_for_status()
            version = response.json().get("version", "unknown")
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            print(f"FAIL: Ollama is unreachable at {base}: {exc}")
            print("FAIL: start Ollama with 'ollama serve' or 'docker compose up -d'.")
            failures += 1
        else:
            print(f"PASS: Ollama {version} is reachable at {base}")

        names: set[str] = set()
        try:
            response = client.get(f"{base}/api/tags")
            response.raise_for_status()
            models = response.json().get("models", [])
            names = {
                item.get("name")
                for item in models
                if isinstance(item, dict) and item.get("name")
            }
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            print(f"FAIL: could not list Ollama models at {base}: {exc}")
            failures += 1
        else:
            for model in (config.OLLAMA_MODEL, config.OLLAMA_EMBED_MODEL):
                if model in names or f"{model}:latest" in names:
                    print(f"PASS: model {model!r} is available.")
                else:
                    print(
                        f"FAIL: model {model!r} is missing. "
                        "Run: python scripts/dev.py models"
                    )
                    failures += 1

    for relative in ("app", "scripts"):
        if compileall.compile_dir(str(REPO_ROOT / relative), quiet=1):
            print(f"PASS: compileall {relative}/")
        else:
            print(f"FAIL: compileall {relative}/")
            failures += 1

    if shutil.which("docker"):
        completed = subprocess.run(
            ["docker", "compose", "config", "--quiet"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            print("PASS: docker compose config")
        else:
            detail = (completed.stderr or completed.stdout or "").strip()
            print(f"FAIL: docker compose config{': ' + detail if detail else ''}")
            failures += 1
    else:
        print("SKIP: docker not installed (optional).")

    if failures:
        print("FAIL: local checks had failures")
        return 1
    print("PASS: local checks passed")
    return 0


def _rubric(_args: argparse.Namespace, extras: list[str]) -> int:
    """Run the rubric bench, forwarding every extra argument to the script."""
    command = [sys.executable, str(REPO_ROOT / "scripts" / "rubric_check.py")]
    command.extend(extras)
    return subprocess.run(command, cwd=REPO_ROOT).returncode


def _db_init(args: argparse.Namespace, _extras: list[str]) -> int:
    """Create the relational schema, from the models or from db/schema.sql."""
    if args.database_url:
        # app.core.config reads DATABASE_URL at import time, so set it before import.
        os.environ["DATABASE_URL"] = args.database_url

    from sqlalchemy.exc import SQLAlchemyError

    from app.core import bootstrap
    from app.core import database as db

    db.reset()
    if db.database_url() is None:
        print(
            "FAIL: DATABASE_URL is empty. Export it or pass --database-url.",
            file=sys.stderr,
        )
        return 1

    engine = db.get_engine()
    source = "db/schema.sql" if args.from_schema else "app/models/pqrsd.py"

    try:
        if args.reset:
            print("Dropping the mapped tables and the reporting view ...")
            bootstrap.reset(engine)
        print(f"Creating the relational schema from {source} ...")
        stats = (
            bootstrap.create_from_schema(engine)
            if args.from_schema
            else bootstrap.create_from_models(engine)
        )
        seed = bootstrap.load_seed(engine) if args.seed else None
    except bootstrap.BootstrapError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    except (SQLAlchemyError, OSError) as exc:
        print(f"FAIL: could not create the schema: {exc}", file=sys.stderr)
        return 1

    print(
        f"PASS: {stats['tables']} tables, {stats['views']} view(s), "
        f"{stats['triggers']} trigger(s), {stats['functions']} function(s)"
    )
    if seed is not None:
        status = "PASS" if seed["applied"] else "SKIP"
        print(f"{status}: seed - {seed['reason']}")
    return 0


_HANDLERS = {
    "setup": _setup,
    "models": _models,
    "ingest": _ingest,
    "api": _api,
    "smoke": _smoke,
    "check": _check,
    "rubric": _rubric,
    "db-init": _db_init,
}


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, switch to the project venv, and dispatch."""
    parser = _build_parser()
    args, extras = parser.parse_known_args(argv)

    if args.command is None:
        if extras:
            parser.error(f"unrecognized arguments: {' '.join(extras)}")
        parser.print_help()
        return 0
    if args.command not in {"ingest", "api", "rubric"} and extras:
        parser.error(f"unrecognized arguments: {' '.join(extras)}")

    if args.command != "setup":
        venv_result = _ensure_venv_interpreter()
        if venv_result is not None:
            return venv_result

    return _HANDLERS[args.command](args, extras)


if __name__ == "__main__":
    raise SystemExit(main())
