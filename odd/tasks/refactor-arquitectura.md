# Feature: refactor-arquitectura

## Objective

Restructure and modernize the `asistencia-cliente-local` codebase by migrating from a flat coupled `api/` structure to a Clean Layered Architecture (`app/`), applying the production patterns from `.agents/skills`:
1. `fastapi-templates`: Layered presentation (`app/api`), configuration (`app/core`), data access (`app/repositories`, `app/models`), schemas (`app/schemas`), domain & services (`app/services`, `app/domain`), and clean Dependency Injection (`Depends`).
2. `pydantic`: Strict validation schemas with `extra="forbid"`, `Annotated`, `Field`, and `str_strip_whitespace=True`, resolving rubric warning C3.2.
3. `python-testing-patterns`: Comprehensive `pytest` test suite (`tests/unit`, `tests/integration`) with fixtures, SQLite in-memory, and Ollama/hardware mocks.
4. `rag-implementation`: Decoupled RAG components (embedder, vector store, lexical gate, generation/streamer) adhering strictly to CPU-only hardware budgets (concurrency 1, timeout budgets, 800-900 char chunks, exact refusal string).
5. Zero-downtime backwards compatibility: Facades in `api/` re-exporting from `app/` so all existing test scripts (`scripts/dev.py`, `scripts/check_schema.py`, `scripts/rubric_check.py`) and external callers work seamlessly.

Branch: `feat/refactor-architecture-and-structure`

## Problem

The service logic was concentrated in `api/`: `main.py` directly handled HTTP routing, lifespan state, Ollama error mapping, request validation, and business logic coordination. `rag.py` mixed vector retrieval, hybrid gating, prompt formatting, and LLM calls. PQRSD schemas lacked unified base configurations (`extra="forbid"` on `AskRequest`), triggering C3.2 warnings. Furthermore, no automated `pytest` test suite existed, making regressions harder to catch quickly.

## Why

Migrating to Clean Architecture separates concerns cleanly:
- Presentation (`app/api`): only HTTP routing, request parsing, and status mapping.
- Core & Domain (`app/core`, `app/domain`): configuration, exceptions, business rules (plazos).
- Data Access (`app/models`, `app/repositories`): database models and vector/relational queries.
- Services (`app/services`): orchestration of business use cases.
- Infrastructure (`app/infrastructure`): external clients (Ollama, lexical tokenizer).
- DI (`Depends`): facilitates unit/integration testing via `dependency_overrides`.

## Hardware Budget & Constraints

| Resource | Constraint |
|---|---|
| CPU | AMD A12-9720P, 4 cores |
| RAM | 7.2 GB total |
| Concurrency | `LLM_CONCURRENCY_LIMIT=1` |
| Refusal String | `No tengo esa información en mi base local` |
| Ingestion Batch | `EMBED_BATCH_SIZE=32` |

## Authorized Scope

- `app/` (all subpackages: `core`, `domain`, `models`, `schemas`, `repositories`, `infrastructure`, `services`, `api`, `main.py`)
- `api/` (facades re-exporting from `app/`)
- `tests/` (`conftest.py`, `unit/`, `integration/`)
- `scripts/dev.py` (updated to point to `app.main:app` with `api.main:app` fallback)
- `odd/tasks/refactor-arquitectura.md`

## Out of Scope

- Modifying the underlying ChromaDB vector database index or `knowledge_base/` documents.
- Changing `db/schema.sql` or `db/seed.sql`.
- Changing the exact refusal string.

## Delivery Strategy

`ask-on-risk` (ODD default). Conventional Commits per completed work unit.

## Tasks

- [x] **TASK-1**: Core & Domain Layer (`app/core/config.py`, `app/core/database.py`, `app/core/exceptions.py`, `app/domain/exceptions.py`, `app/domain/plazos.py`)
- [x] **TASK-2**: Models & Schemas Layer (`app/models/pqrsd.py`, `app/schemas/base.py`, `app/schemas/rag.py`, `app/schemas/pqrsd.py`, `app/schemas/catalogs.py`)
- [x] **TASK-3**: Infrastructure & Repositories (`app/infrastructure/ollama.py`, `app/infrastructure/lexical.py`, `app/repositories/vector_repository.py`, `app/repositories/pqrsd_repository.py`)
- [x] **TASK-4**: Services Layer (`app/services/rag_service.py`, `app/services/ingest_service.py`, `app/services/pqrsd_service.py`)
- [x] **TASK-5**: Presentation Layer & Dependency Injection (`app/api/dependencies.py`, `app/api/v1/router.py`, `app/api/v1/endpoints/health.py`, `app/api/v1/endpoints/rag.py`, `app/api/v1/endpoints/pqrsd.py`, `app/main.py`)
- [x] **TASK-6**: Retrocompatibility Facades & CLI (`api/` modules forwarding to `app/`, `api/db/` forwarding to `app/`, `scripts/dev.py`)
- [x] **TASK-7**: Pytest Automated Test Suite (`tests/conftest.py`, `tests/unit/`, `tests/integration/`)
- [x] **TASK-8**: Verification & Benchmark (`scripts/dev.py check`, `pytest tests/`, `scripts/check_schema.py`, `scripts/rubric_check.py`, `scripts/dev.py smoke`)
- [x] **TASK-9**: Decommission `api/` directory: relocate active resources (`bootstrap.py`, `system_prompt.txt`, `requirements.txt`), update scripts (`check_schema.py`, `rubric_check.py`, `dev.py`), remove `api/`, update docs, and verify all tests.

## Verification Evidence

- `TASK-1`: Commit 9656d12. Verified import and evaluation of config, database, exceptions and plazos.
- `TASK-2`: Commit a687b5f. 28 tables and 180 columns in app/models match db/schema.sql, strict Pydantic schemas with extra forbid.
- `TASK-3`: Commit 0f260c2. Vector and PQRSD repositories operational with ChromaDB and PostgreSQL, Spanish lexical gate and Ollama client.
- `TASK-4`: Commit 173be1e. Services functional with decoupled RAGService, IngestService and PqrsdService.
- `TASK-5`: Commit 3e337f2. Endpoints respond with expected schemas and DI overrides via Depends.
- `TASK-6`: Commit 3c5eb8c. Backward compatibility intact; legacy api.* imports work without modification, dev.py updated.
- `TASK-7`: Commit e835444. Pytest suite passes 100% (70 tests in 3.24s).
- `TASK-8`: Rubric check passes with 43/60 (71.3%), C3.2 is green (extra='forbid' verified), dev.py check passes, check_schema passes, and 70/70 pytest tests pass.
- `TASK-9`: Commit 251be47. Decommissioned api/ directory, relocated bootstrap.py, system_prompt.txt, and requirements.txt, updated all scripts and documentation, 70/70 tests pass.
