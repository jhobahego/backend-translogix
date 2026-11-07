# AGENTS.md

Agent and contributor guide for `asistencia-cliente-local`: a 100% local
customer-support RAG service (FastAPI + ChromaDB + Ollama). No cloud, no
telemetry, no API keys.

Feature branch of record: `feat/rag-vectorial/jhon-hernandez`.

## What the service does

1. `app/services/ingest_service.py` reads `knowledge_base/**/*.md|pdf`, splits documents into
   chunks, embeds them with a local Ollama embedding model and persists the
   vectors in ChromaDB on disk (`chroma_db/`).
2. `app/services/rag_service.py` embeds the user question, retrieves the nearest chunks with
   cosine distance, applies the hybrid relevance gate and builds a grounded
   prompt.
3. `app/main.py` exposes the flow through FastAPI, including source/distance
   traceability and token streaming.
4. Ollama generates the answer with a small local chat model. The system
   prompt (`app/core/system_prompt.txt`) forces grounding and a fixed refusal.

## Local hardware budget (READ BEFORE CHOOSING MODELS)

This machine is CPU-only. Treat these numbers as hard constraints, not
suggestions:

| Resource | Value |
|---|---|
| CPU | AMD A12-9720P, 4 cores / 4 threads, 2.7 GHz max |
| RAM | 7.2 GB total, ~1.8–2.7 GB available while working |
| GPU | Radeon R7 integrated only; no CUDA, no usable ROCm |
| Disk free | ~27 GB |
| Python | 3.13 in `.venv` |
| Ollama | 0.40.13 at `http://localhost:11434` |

Consequences:

- One generation at a time (`LLM_CONCURRENCY_LIMIT=1`). Two concurrent 3B
  generations will swap.
- A full answer takes roughly 20–100 s on this CPU. Use the streaming
  endpoints for UX; do not lower timeouts below 300/400 s.
- Keep chunks small (800–900 chars) so the embedding context stays near the
  model's default and RAM stays flat.

### Approved models for this machine

| Role | Model | Disk | Why |
|---|---|---|---|
| Chat | `qwen2.5:3b-instruct-q4_K_M` | ~1.9 GB | Already installed; best Spanish/instruction balance that fits 7.2 GB |
| Embeddings | `nomic-embed-text` | ~274 MB | 768 dims, CPU-fast, prefixes handled in code |

Do **not** switch this machine to:

- `llama3.1` / `llama3.1:8b` (~4.7 GB) — does not fit alongside the OS.
- `bge-m3` (1.2 GB, 1024 dims) — better Spanish, but the extra RAM and CPU cost
  are not affordable here. Revisit only with 16 GB+ RAM or a GPU.
- `qwen3-embedding:0.6b` (639 MB) — better multilingual score, roughly 4x
  slower than nomic on 4 cores. Optional upgrade with more RAM.

Changing the embedding model invalidates the whole index: vectors from
different models live in different spaces. See “Changing the embedding model”.

## Architecture

![Vector RAG architecture](docs/arquitectura-rag.png)

```
knowledge_base/ ──ingest──> ChromaDB (cosine/HNSW, on disk)
                                   ▲
question ──embed(query)──> retrieve top_k ──hybrid gate──> prompt ──Ollama──> answer
```

## Repository map

| Path | Role |
|---|---|
| `app/core/config.py` | Single source of env config; loads the repo-root `.env` via python-dotenv and resolves repo-root paths |
| `app/infrastructure/ollama.py` | Ollama embed/chat clients; nomic document/query prefixes; batching |
| `app/infrastructure/lexical.py` | Spanish lexical evidence used as the precision gate |
| `app/services/ingest_service.py` | Markdown/PDF chunking, deterministic IDs, prune, upsert, `--reset` |
| `app/services/rag_service.py` | `LocalVectorRAG` / `RAGService`: retrieval, gate, prompt, ask/stream |
| `app/main.py` | FastAPI lifespan, semaphore, canonical endpoints |
| `app/core/bootstrap.py` | Relational schema creation and seed loader |
| `app/core/database.py` | Optional PostgreSQL layer: lazy engine, session dependency |
| `app/models/` | SQLAlchemy ORM models |
| `app/schemas/` | Pydantic schemas with extra='forbid' |
| `app/repositories/` | Vector and PQRSD repositories |
| `app/domain/` | Pure business rules and business-day deadlines |
| `app/core/system_prompt.txt` | Grounding rules and the exact refusal string |
| `knowledge_base/` | **Only** indexed corpus (`.md` and `.pdf`) |
| `docs/` | Meta-documentation (`MODELOS.md`, `BENCHMARK.md`, `EVALUACION.md`), not indexed |
| `scripts/dev.py` | Cross-platform CLI: `setup`, `models`, `ingest`, `api`, `smoke`, `check`, `rubric`, `db-init`; re-executes in `.venv` |
| `scripts/rubric_check.py` | KODO TAKAI rubric bench: executable evidence per criterion, estimated score and open gaps |
| `scripts/check_schema.py` | Offline guard: models vs `db/schema.sql`, Pydantic rejections, business-day arithmetic |
| `db/schema.sql` | PostgreSQL 13+ DDL: 28 tables, constraints, triggers, `next_radicado`, reporting view, RLS notes |
| `db/seed.sql` | Catalog seed data taken verbatim from the manuals |
| `chroma_db/` | Generated index; gitignored, never commit |

## Setup from zero

The same commands work on Linux, macOS, and Windows:

```bash
docker compose up -d                 # optional: Ollama + Open WebUI
python scripts/dev.py setup         # creates .venv, installs deps, seeds .env
python scripts/dev.py models        # chat + embedding models, once
python scripts/dev.py ingest        # builds chroma_db/, ~30-40 s here
python scripts/dev.py api           # uvicorn on API_PORT from config
```

`scripts/dev.py` re-executes itself with the repository `.venv` interpreter,
so activating the virtual environment is unnecessary. Use `python3` on
Linux/macOS when `python` is not on `PATH`, and `py -3` on Windows when the
`python` launcher is not on `PATH`.

## Environment variables

| Variable | Default | Notes |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `OLLAMA_MODEL` | `qwen2.5:3b-instruct-q4_K_M` | Chat model |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Embedding model; change requires re-index |
| `API_PORT` | `8000` | Port used by `scripts/dev.py api` and `smoke`; not read by `app/main.py` |
| `RAG_TOP_K` | `4` | Retrieved chunks before the gate |
| `RAG_MAX_DISTANCE` | `0.50` | Cosine distance ceiling |
| `RAG_STRONG_DISTANCE` | `0.25` | Distance accepted without lexical evidence |
| `LLM_CONCURRENCY_LIMIT` | `1` | Keep at 1 on this hardware |
| `EMBED_BATCH_SIZE` | `32` | Ingestion batch size |
| `CHROMA_DB_PATH` | `./chroma_db` | Resolved against repo root |
| `CHROMA_COLLECTION` | `asistencia_cliente_kb` | Collection name |
| `KNOWLEDGE_BASE_DIR` | `./knowledge_base` | Indexed corpus root |
| `TEMPERATURE` | `0.2` | `0.0` makes refusal/answer behavior more deterministic |
| `OLLAMA_TIMEOUT` | `300` | Full answer timeout (seconds) |
| `OLLAMA_STREAM_TIMEOUT` | `400` | Stream timeout (seconds) |
| `DATABASE_URL` | *(empty)* | PostgreSQL URL (`postgresql+psycopg://...`); empty disables the relational layer and leaves the RAG intact |
| `DB_POOL_SIZE` | `5` | SQLAlchemy pool size |
| `DB_POOL_TIMEOUT` | `10` | Seconds to wait for a free pooled connection |
| `DB_CONNECT_TIMEOUT` | `5` | Connect timeout; a dead host answers 503 fast instead of hanging the request |
| `DB_ECHO` | `false` | Echo generated SQL |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `asistencia` | Compose-only: credentials and database created by the `postgres` service. Not read by `app/core/config.py` |

`.env` is optional. `app/core/config.py` loads it from the repository root with
`python-dotenv` at import time; variables already exported in the process
environment take precedence over the file, and a missing file falls back to the
defaults above. `.env.example` documents the CPU-tuned values. Never commit
`.env`.

## Ingestion contract

- Indexed files: `knowledge_base/**/*.md` and `knowledge_base/**/*.pdf`.
  Everything else is ignored; `docs/` is intentionally outside the corpus.
- Markdown: two-stage split preserving hierarchy. `#` → `categoria`,
  `##` → `seccion`, `###` → `pregunta`; then `RecursiveCharacterTextSplitter`
  at 800 chars with 150 overlap. Chunks under 40 chars are dropped.
- PDF: `pypdf` page by page, 900 chars with 180 overlap; metadata includes
  `page`.
- IDs: `{source}_chunk_{index}_{md5(content)[:8]}`. Re-running ingestion is
  idempotent; stale IDs for an edited source are deleted, and chunks whose
  source file was removed are pruned.
- `python -m app.services.ingest_service --reset` drops and recreates the collection.
- Metadata values are strings/integers only (Chroma constraint).

## Retrieval contract (do not simplify to one threshold)

Measured with the real FAQ: a single `max_distance` is unusable. Off-domain
questions score 0.32–0.45, overlapping on-domain 0.20–0.41. Therefore each
chunk is kept only when:

```
distance <= RAG_MAX_DISTANCE
AND (distance <= RAG_STRONG_DISTANCE OR lexical_evidence(query, chunk) > 0)
```

- Vector search supplies recall; `app/infrastructure/lexical.py` supplies precision.
- `nomic-embed-text` requires `search_document: ` on stored chunks and
  `search_query: ` on questions. `app/infrastructure/ollama.py` owns this; never call
  Chroma with `query_texts` or attach a Chroma embedding function.
- Send embeddings explicitly (`upsert(embeddings=...)`,
  `query(query_embeddings=...)`) and use `hnsw:space=cosine`.
- Use `truncate=False` when embedding: silent truncation would index the wrong
  meaning.
- If you change documents, chunk sizes or the embedding model, re-measure the
  gate. The calibration table lives in `odd/tasks/rag-vectorial.md`.

## API contract

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | `{status, model, embedding_model, kb_chunks}`; never calls Ollama |
| `POST` | `/api/v1/ask` | `{question, categoria?}` → `{answer, sources[{content, metadata, distance}]}` |
| `POST` | `/api/v1/ask/stream` | Same input; plain-text token stream |
| `POST` | `/api/v1/sync-kb` | Re-indexes in a worker thread; returns ingest stats |
| `POST` | `/api/v1/pqrsd` | Files a case; returns the assigned `radicado` and its deadline |
| `GET` | `/api/v1/pqrsd` | Lists cases; filters `estado`, `dependencia_id`, `limit`, `offset` |
| `GET` | `/api/v1/pqrsd/{radicado}` | Reads one case with its state log and attachments |
| `PATCH` | `/api/v1/pqrsd/{radicado}` | Moves the case to another status and logs the transition |
| `POST` | `/api/v1/pqrsd/{radicado}/anexos` | Attaches a SHA-256 file hash to the case |

`categoria` is an exact match on the indexed `categoria` metadata values (the
`#` headings). An unknown value returns `422` with the indexed values in
`detail.available_categories`; omit the field or send a blank string to
disable the filter.

## Operations

- Add or edit a document: put it under `knowledge_base/`, then
  `python scripts/dev.py ingest` (or `POST /api/v1/sync-kb`). A 3B answer is not
  affected, but ingestion takes ~30–40 s for this corpus.
- First run after cloning: ingest before querying. `/health` showing
  `kb_chunks: 0` means every answer will be the refusal.
- Changing the embedding model: update `OLLAMA_EMBED_MODEL`, run
  `python scripts/dev.py ingest --reset`, and re-measure the gate. Never mix
  spaces.
- Deleting `chroma_db/` is safe: it is a generated artifact.
- Start the relational store with `docker compose up -d postgres`; the official
  entrypoint loads `db/schema.sql` and `db/seed.sql` on first boot, so
  `DATABASE_URL=postgresql+psycopg://asistencia:asistencia@localhost:5432/asistencia`
  works immediately. Init scripts run only on an empty data volume: to re-seed,
  `docker compose down -v` and start it again.
- Without Docker, create the schema from the models:
  `python scripts/dev.py db-init --seed`. It runs `Base.metadata.create_all()`
  and replays the objects SQLAlchemy cannot express (the `pg_trgm` extension,
  the trigger functions, the triggers and the reporting view) from
  `db/schema.sql`, so both routes behave the same. Add `--reset` to drop the
  mapped tables first; `--from-schema` executes the DDL verbatim instead.
  Without `DATABASE_URL` those routes answer 503 and the RAG keeps working.
  `db/schema.sql` stays the reference DDL and the artifact
  `scripts/check_schema.py` validates the models against.
- Holidays are not seeded. Load the official Colombian calendar into `festivo`;
  otherwise business-day deadlines only skip weekends.
- The `radicado` is assigned by the `secuencia_radicado` correlative through
  `next_radicado(p_vigencia integer)`, and a trigger rejects any `UPDATE` on the
  column. Do not generate it in the application. The helper takes the year as an
  integer, so `select next_radicado(2091)` works without a cast.
- Do not run ingestion concurrently with a heavy query on this machine; both
  compete for the embedding/chat models and RAM.
- Chroma telemetry is disabled in both `ingest.py` and `rag.py`.

## Verification protocol

Run these before reporting the feature complete:

```bash
python scripts/dev.py check                # Ollama + compose + models + compileall
python scripts/dev.py rubric               # rubric bench: contract, validation, model state
python scripts/check_schema.py             # models vs db/schema.sql, contracts, deadlines
python scripts/dev.py ingest               # twice; same collection_count both times
python scripts/dev.py api                  # in one terminal
python scripts/dev.py smoke                # in another terminal
```

Expected: `/health` has `kb_chunks` greater than 0 (504 with the current
manuals); the on-domain question returns a non-empty answer and sources; the
off-domain question returns `sources: []` and the exact refusal; the stream
returns text.

`python scripts/dev.py rubric --database-url "$DATABASE_URL" --db-write` is the
only check that exercises the relational schema (constraints, triggers, audit
trail, radicado and concurrency). Without a database that criterion is reported
as unverifiable, not as passed.

TDD exception: the repo has no pytest dependency or test suite. The runnable
checks are `compileall`, ingest idempotency and the end-to-end smoke test.
Adding pytest is welcome, but do not claim RED/GREEN evidence that was not
observed.

## Known limitations and pitfalls

- The 3B model occasionally over-refuses a paraphrase even when the correct
  chunk is in context (safe failure). Lower `TEMPERATURE` to `0.0` for more
  deterministic behavior, or use a larger chat model when hardware allows.
- The system prompt does not calculate quotes: the 3B model fails the
  arithmetic (measured `50 × 40 × 30` as 37.500 and then 30 kg). It reports
  the route rates from CONTEXT and leaves the total to the cotizador.
- PDF ingestion is implemented but this corpus has no PDF, so the real PDF
  path is not exercised end to end. Add a small PDF and re-run the smoke test
  before relying on it.
- Docker is not installed on this machine, so the `postgres` compose service
  cannot be used here. The schema is created instead with
  `python scripts/dev.py db-init`, which was executed against a local
  PostgreSQL 18.6 server: 28 tables, 9 triggers, the reporting view and the
  seeded catalogs. The rubric bench's database criterion still requires
  `python scripts/dev.py rubric --database-url ... --db-write`.
- `app/core/system_prompt.txt` is re-read on every request; context headers are
  deliberately placed at the END of each block (source labels first caused the
  3B model to echo the header instead of answering).
- The list of files is re-scanned on every ingestion; a full-collection
  `get(include=["metadatas"])` is used to prune deleted sources. Fine at this
  scale, revisit for thousands of chunks.
- No authentication. Bind to `127.0.0.1` unless the network is trusted.
- `categoria` values are validated against the categories currently indexed,
  so a typo fails with `422` instead of the off-domain refusal. The earlier
  phantom refusal came from Swagger UI injecting the literal `"string"` into
  the generated example body; the documented example now omits the field.

## Notion task tracking

The Notion MCP is configured for this project:

- Project page: https://app.notion.com/p/Proyecto-Kodo-Takai-40ccc16fb0fd809e9546de6713f89d10
- Task manager: https://app.notion.com/p/Gestor-de-Tareas-40ccc16fb0fd8033bd1ec81ce45108bf

The task manager is the source of truth for task status.

- When a task starts, change its status from `Pendiente` to `En curso` and move it to the corresponding column before starting the work.
- A task is complete when the assigned user confirms it, or when its work is committed or pushed. On completion, change its status to `Terminado` and move it to the `Terminado` column.
- Do not mark a task as `Terminado` until one of those completion conditions is met.
- Keep the project page aligned with the current state of `main`; do not present unmerged feature-branch work as shipped.

## Conventions

- README is neutral Spanish; code, comments, docstrings and this file are
  English. No voseo or slang in artifacts.
- Keep the stack small: `fastapi`, `uvicorn`, `pydantic`, `httpx`, `chromadb`,
  `ollama`, `langchain-text-splitters`, `pypdf`, `python-dotenv`. No vector DB
  service, no cloud calls.
- Never commit `.env`, `chroma_db/`, model files or generated caches.
- Do not change `docker-compose.yml` to a GPU variant on this machine; the
  current file is intentionally CPU-only.
- Keep the refusal string in `app/core/system_prompt.txt` exactly:
  `No tengo esa información en mi base local`.
- Prefer small, reviewable changes that keep tests, docs and behavior together.
