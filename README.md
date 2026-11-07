# Translogix Backend

Backend RAG vectorial 100 % local para TransLogix Colombia S.A.S. (TransLogix Express): FastAPI +
ChromaDB + Ollama. Sin nube, sin telemetría, sin costo por consulta y con los
datos siempre en el equipo.

El flujo es simple:

1. Los documentos de `knowledge_base/` se fragmentan y se indexan en ChromaDB.
2. La pregunta se convierte en un vector con `nomic-embed-text`.
3. Se recuperan los fragmentos más cercanos y se filtran con una compuerta
   híbrida (distancia + evidencia léxica).
4. El LLM local responde usando solo esos fragmentos y devuelve las fuentes.

## Arquitectura

![Arquitectura del RAG vectorial](docs/arquitectura-rag.png)

```text
knowledge_base/ ──ingesta──> ChromaDB persistente (cosine/HNSW)
                                      ▲
pregunta ──embedding──> top_k ──compuerta──> prompt ──Ollama──> respuesta
```

## Perfiles de hardware

| Perfil             | Descripción                         | Modelos de chat          | Embeddings                        |
|--------------------|-------------------------------------|--------------------------|-----------------------------------|
| Modesto (CPU-only) | Sin GPU dedicada; todo corre en CPU | 1B–3.8B en GGUF `Q4_K_M` | `nomic-embed-text`                |
| Potente (NVIDIA)   | GPU NVIDIA con CUDA                 | 7B–14B                   | `bge-m3` o `qwen3-embedding:0.6b` |

> Este repositorio está calibrado para el perfil modesto: 4 núcleos, 7.2 GB de
> RAM y sin CUDA/ROCm. Los modelos y umbrales concretos de esa máquina están
> documentados en `AGENTS.md`.

## Requerimientos

| Necesidad | Versión mínima | Para qué se usa |
| ----------- | ---------------- | ----------------- |
| Docker + Compose v2 (`docker compose`) | Docker 24+ | Opcional: levanta Ollama, Open WebUI y PostgreSQL 16. Sin Docker, se puede usar Ollama nativo y un PostgreSQL ya instalado |
| Python + venv + pip | Python 3.10+ | API RAG y CLI `scripts/dev.py` |
| Ollama CLI (`ollama`) | Última estable | Descarga los modelos una sola vez |
| Puertos libres | — | `3000` (Open WebUI), `5432` (PostgreSQL), `8000` (API), `11434` (Ollama) |
| Disco | ~1 GB libre | Modelo de chat (~2 GB aparte) + embeddings (274 MB) + venv (~530 MB) + índice |

Dependencias de Python (`requirements.txt`): `fastapi`, `uvicorn`,
`pydantic`, `httpx`, `chromadb`, `ollama`, `langchain-text-splitters`, `pypdf`,
`python-dotenv`.

### Linux

- Docker Engine + plugin Compose, con el servicio en ejecución y el usuario en
  el grupo `docker` (o usar `sudo`).
- `python3`, `python3-venv`, `pip` y `git`.
- Verificar con: `docker --version`, `docker compose version`,
  `python3 --version`, `ollama --version`.

### Windows

- Windows 10/11 de 64 bits.
- Python 3.10+ desde `python.org` con la opción `Add to PATH` marcada; si el
  lanzador `python` no está disponible, usar `py -3`.
- Ollama Desktop para Windows, o descargar los modelos dentro del contenedor:
  `docker exec -it <contenedor-ollama> ollama pull qwen2.5:3b-instruct-q4_K_M`.
- Docker Desktop (backend WSL2) es opcional.

## Quickstart

Los mismos comandos funcionan en Linux, macOS y Windows:

```bash
# 1. Ollama + Open WebUI + PostgreSQL (CPU-only); omitir si ya hay Ollama nativo
docker compose up -d

# 2. Entorno virtual, dependencias y .env (una sola vez)
python scripts/dev.py setup

# 3. Modelos: chat + embeddings (una sola vez)
python scripts/dev.py models

# 4. Índice vectorial (una sola vez, o después de cambiar documentos)
python scripts/dev.py ingest

# 5. API (lee API_PORT desde .env)
python scripts/dev.py api
```

> `docker compose up -d` también levanta PostgreSQL 16 y carga `db/schema.sql`
> y `db/seed.sql` en el primer arranque. Para levantar solo el stack del RAG:
> `docker compose up -d ollama open-webui`; para levantar solo la base:
> `docker compose up -d postgres`.
>
> Sin Docker, el esquema relacional se crea desde los modelos con
> `python scripts/dev.py db-init --seed`, o desde el DDL con
> `python scripts/dev.py db-init --from-schema --seed`. Ver «Capa relacional».

En otra terminal:

```bash
python scripts/dev.py smoke
```

> `scripts/dev.py` se reejecuta con el intérprete de `.venv` del repositorio,
> así que no hace falta activar el entorno virtual. Si `python` no está
> disponible, usar el lanzador equivalente: `python3` en Linux/macOS o `py -3`
> en Windows (por ejemplo, `python3 scripts/dev.py setup`).

Documentación interactiva: `http://localhost:8000/docs`.

## Scripts

| Comando | Propósito | Opciones |
| --------- | ----------- | ---------- |
| `python scripts/dev.py setup` | Crea `.venv`, instala `requirements.txt` y copia `.env.example` a `.env` si falta | — |
| `python scripts/dev.py models` | Descarga el modelo de chat y el de embeddings configurados | — |
| `python scripts/dev.py ingest` | Reconstruye o actualiza el índice vectorial | `--reset` (borra y recrea la colección) |
| `python scripts/dev.py api` | Inicia uvicorn en `API_PORT` | `--host`, `--port`, `--reload` |
| `python scripts/dev.py smoke` | Verifica una API en ejecución | `--url` (por defecto `API_URL` o `http://localhost:API_PORT`) |
| `python scripts/dev.py check` | Verifica Ollama, modelos, `compileall` y `docker compose config` si Docker está instalado | — |
| `python scripts/dev.py rubric` | Banco de pruebas de la rúbrica KODO TAKAI: contrato HTTP, validación, modelo local y base de datos | `--live-ai`, `--database-url`, `--db-write`, `--json`, `--verbose`, `--strict` |

Los argumentos adicionales se reenvían a `python -m app.services.ingest_service` en `ingest` y a
`uvicorn` en `api`.

## Uso sin Docker (Ollama nativo)

Sin Docker no hay Open WebUI en `http://localhost:3000`; la API en
`http://localhost:8000` funciona igual porque solo necesita
`http://localhost:11434`.

Si Ollama ya corre como servicio (systemd en Linux, app de escritorio en
macOS/Windows), no ejecutes `ollama serve` otra vez ni levantes además el
contenedor con `docker compose up -d`: ambos usan el puerto `11434` y fallan
con `address already in use`.

```bash
# 1. Instalar Ollama (una sola vez): https://ollama.com/download
# 2. Verificar el servidor (si ya corre como servicio, omitir `ollama serve`)
ollama list    # responde con los modelos instalados
ollama serve   # solo si el anterior falló; dejarlo en otra terminal

# 3. Entorno, dependencias y modelos
python scripts/dev.py setup
python scripts/dev.py models

# 4. Índice y API RAG
python scripts/dev.py ingest
python scripts/dev.py api
```

> Open WebUI es un chat directo contra Ollama: no pasa por esta API ni usa la
> base vectorial. Para consultar el RAG, usar `/api/v1/ask`, el streaming o
> `http://localhost:8000/docs`.
>
> Sin Docker tampoco hay servicio `postgres`: los endpoints de `/api/v1/pqrsd`
> necesitan un PostgreSQL 13+ propio (con `pg_trgm`) y su `DATABASE_URL`.

## Base de conocimiento

- Solo se indexan `knowledge_base/**/*.md` y `knowledge_base/**/*.pdf`.
- Markdown: `#` se guarda como `categoria`, `##` como `seccion` y `###` como
  `pregunta`. Conviene mantener una pregunta por `##` para que cada fragmento
  sea autocontenido.
- PDF: se indexa página por página y la metadata incluye `page`.
- `docs/` contiene documentación meta (`MODELOS.md`, `BENCHMARK.md`,
  `EVALUACION.md`) y **no** se indexa.
- Después de agregar o editar documentos:

```bash
python scripts/dev.py ingest   # reconstruye/actualiza el índice
# o, con la API levantada:
curl -X POST localhost:8000/api/v1/sync-kb
```

La ingesta es idempotente: volver a ejecutarla no duplica fragmentos y elimina
los que ya no corresponden a ningún archivo.

## Variables de entorno

`app/core/config.py` carga `.env` desde la raíz del repositorio con `python-dotenv`
al importarse. Las variables ya exportadas en el entorno tienen prioridad sobre
el archivo; si `.env` no existe, se usan los valores por defecto. `API_PORT` lo
leen `python scripts/dev.py api` y `python scripts/dev.py smoke`, no
`app/main.py`.

| Variable | Valor por defecto | Descripción |
| ---------- | ------------------- | ------------- |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL del servidor Ollama |
| `OLLAMA_MODEL` | `qwen2.5:3b-instruct-q4_K_M` | Modelo de chat |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Modelo de embeddings; cambiarlo exige reindexar |
| `API_PORT` | `8000` | Puerto por defecto de `scripts/dev.py api` y `smoke` |
| `RAG_TOP_K` | `4` | Fragmentos recuperados antes de la compuerta |
| `RAG_MAX_DISTANCE` | `0.50` | Distancia de coseno máxima |
| `RAG_STRONG_DISTANCE` | `0.25` | Distancia aceptada sin evidencia léxica |
| `LLM_CONCURRENCY_LIMIT` | `1` | Generaciones simultáneas; 1 en CPU-only |
| `EMBED_BATCH_SIZE` | `32` | Tamaño de lote de embeddings |
| `CHROMA_DB_PATH` | `./chroma_db` | Ruta del índice persistente |
| `CHROMA_COLLECTION` | `asistencia_cliente_kb` | Nombre de la colección |
| `KNOWLEDGE_BASE_DIR` | `./knowledge_base` | Corpus indexado |
| `TEMPERATURE` | `0.2` | Temperatura de generación (`0.0` = más determinista) |
| `OLLAMA_TIMEOUT` | `300` | Timeout de respuesta completa (segundos) |
| `OLLAMA_STREAM_TIMEOUT` | `400` | Timeout de streaming (segundos) |
| `DATABASE_URL` | vacío | URL de PostgreSQL (`postgresql+psycopg://...`); vacío desactiva la capa relacional |
| `DB_POOL_SIZE` | `5` | Conexiones del pool de SQLAlchemy |
| `DB_POOL_TIMEOUT` | `10` | Espera máxima por una conexión libre del pool (segundos) |
| `DB_CONNECT_TIMEOUT` | `5` | Timeout de conexión; una base caída falla rápido en vez de colgar el request |
| `DB_ECHO` | `false` | Imprime el SQL generado por SQLAlchemy |
| `POSTGRES_USER` | `asistencia` | Usuario que crea el servicio `postgres` del compose; no lo lee `app/core/config.py` |
| `POSTGRES_PASSWORD` | `asistencia` | Clave del mismo usuario; solo para desarrollo local |
| `POSTGRES_DB` | `asistencia` | Base que crea el servicio `postgres` al inicializarse |

Las variables `DATABASE_URL` y `DB_*` son opcionales. Sin `DATABASE_URL` el
servicio RAG arranca igual y las rutas de `/api/v1/pqrsd` responden `503`; nunca
se abre una conexión al importar el módulo.

Las tres variables `POSTGRES_*` solo las consume `docker-compose.yml`: las usa la
imagen oficial para crear usuario, clave y base en el primer arranque. Si se
cambia `DATABASE_URL`, hay que cambiar estas en conjunto o el servicio apuntará
a una base distinta.

Timeouts recomendados:

| Perfil             | `OLLAMA_TIMEOUT` | `OLLAMA_STREAM_TIMEOUT` |
|--------------------|------------------|-------------------------|
| Modesto (CPU-only) | 300              | 400                     |
| Potente (NVIDIA)   | 60–120           | 120–180                 |

## Endpoints de la API

| Método | Ruta | Descripción |
| -------- | ------ | ------------- |
| `GET` | `/health` | Estado, modelos y cantidad de fragmentos indexados |
| `POST` | `/api/v1/ask` | `{question, categoria?}` → `{answer, sources[{content, metadata, distance}]}` |
| `POST` | `/api/v1/ask/stream` | Misma entrada; respuesta token por token en texto plano |
| `POST` | `/api/v1/sync-kb` | Reindexa `knowledge_base/` en un hilo aparte |
| `POST` | `/api/v1/pqrsd` | Radica una PQRSD y devuelve su radicado y vencimiento |
| `GET` | `/api/v1/pqrsd` | Lista casos con `estado`, `dependencia_id`, `limit` y `offset` |
| `GET` | `/api/v1/pqrsd/{radicado}` | Consulta un caso con su bitácora de estados y sus anexos |
| `PATCH` | `/api/v1/pqrsd/{radicado}` | Cambia el estado y registra la transición en la bitácora |
| `POST` | `/api/v1/pqrsd/{radicado}/anexos` | Adjunta el hash SHA-256 de un archivo al caso |

Los cinco endpoints de `/api/v1/pqrsd` dependen de `DATABASE_URL`. El body se
valida **antes** de tocar la base: un payload inválido devuelve `422` aunque no
haya base configurada; una petición válida sin base devuelve `503`, y una base
inalcanzable también `503` después de `DB_CONNECT_TIMEOUT` segundos.

`categoria` es un filtro exacto sobre la metadata del encabezado `#`. Una
categoría inexistente devuelve `sources: []` y la respuesta de rechazo.

Ejemplo de streaming:

```bash
curl -N -X POST localhost:8000/api/v1/ask/stream \
  -H 'Content-Type: application/json' \
  -d '{"question":"¿Hacen envíos a domicilio?"}'
```

## Capa relacional (opcional)

El índice vectorial guarda conocimiento; PostgreSQL guarda el expediente. Esa
división es deliberada: los fragmentos y los embeddings viven en `chroma_db/` y
la capa relacional **nunca** los duplica.

- `db/schema.sql`: 28 tablas con restricciones, índices, triggers, la función
  `next_radicado`, una vista de vencidas y la política de row level security
  documentada. Requiere PostgreSQL 13+ y la extensión `pg_trgm`.
- `db/seed.sql`: catálogos tomados de los manuales (plazos de la Resolución 369
  de 2019, canales, atributos del buen servicio, enfoque diferencial y glosario
  de lenguaje ciudadano).
- `app/models/pqrsd.py`: modelos SQLAlchemy 2.0. `app/schemas/pqrsd.py`: contratos
  Pydantic con `extra="forbid"` y validadores cruzados.
- `app/repositories/pqrsd_repository.py`: transacciones, bitácora append-only y máquina de
  estados. `app/domain/plazos.py`: suma de días hábiles con festivos.

`db/seed.sql` **no** trae `dependencia`, `sede`, `tramite` ni `festivo`: solo
canales, tipos de petición, atributos del servicio, categorías diferenciales y
glosario. Para radicar una PQRSD hace falta insertar al menos una dependencia,
porque `pqrsd.dependencia_id` es una clave foránea obligatoria; y mientras
`festivo` esté vacía los vencimientos solo excluyen fines de semana.

```sql
insert into dependencia (codigo, nombre)
values ('DEP-ATN', 'Atención al ciudadano');
```

### Con Docker (vía más corta)

El servicio `postgres` del compose crea el usuario y la base con las variables
`POSTGRES_*` y ejecuta `db/schema.sql` y `db/seed.sql` cuando el volumen de datos
está vacío.

```bash
docker compose up -d postgres
```

Luego, en `.env`:

```bash
DATABASE_URL=postgresql+psycopg://asistencia:asistencia@localhost:5432/asistencia
```

Los scripts de inicialización corren **una sola vez**, al crear el volumen. Si se
edita el esquema o los catálogos, hay que recrear el volumen y volver a levantar:

```bash
docker compose down -v
docker compose up -d postgres
```

### Sin Docker: desde los modelos

Cuando no hay Docker, los modelos SQLAlchemy son la fuente de verdad de las
tablas: `create_all()` las crea junto con sus restricciones e índices. Lo que el
ORM no puede expresar de forma portable —la extensión `pg_trgm`, las funciones de
trigger, los triggers y la vista de vencidas— se replica desde `db/schema.sql` en
dos fases alrededor de `create_all`, para que el esquema creado desde el código se
comporte igual que el creado con el DDL.

```bash
# contra DATABASE_URL, o contra el servidor que indique --database-url
python scripts/dev.py db-init --seed

# desde cero, descartando las tablas mapeadas y la vista
python scripts/dev.py db-init --reset --seed
```

La operación es idempotente: una segunda corrida sin `--reset` no rompe nada, y
`--seed` se salta la carga si los catálogos ya tienen filas.

### Sin Docker: desde el DDL

`db/schema.sql` sigue siendo el DDL de referencia y la vía que usa el entrypoint
de Docker. Se puede ejecutar tal cual, o a través del mismo CLI:

```bash
python scripts/dev.py db-init --from-schema --seed

# equivalente a:
psql "$DATABASE_URL" -f db/schema.sql
psql "$DATABASE_URL" -f db/seed.sql
```

### Validar los modelos contra el DDL

```bash
python scripts/check_schema.py    # modelos vs DDL, contratos y días hábiles
```

`scripts/check_schema.py` no necesita servidor: compara modelos y DDL, prueba los
rechazos de Pydantic y la aritmética de días hábiles. Los **festivos no vienen
cargados**: sin filas en `festivo` el cálculo solo excluye fines de semana, así
que hay que cargar el calendario oficial antes de confiar en los vencimientos.

## Modelos recomendados

### Perfil modesto (CPU-only)

- **Chat por defecto:** `qwen2.5:3b-instruct-q4_K_M` (~1.9 GB). Mejor
  equilibrio entre español, instrucciones y RAM en 3B.
- **Embeddings:** `nomic-embed-text` (~274 MB, 768 dimensiones). Requiere los
  prefijos `search_document:` y `search_query:`; el código ya los aplica.
- **Alternativa de chat:** `gemma3:1b` si el equipo necesita más velocidad.
- **No usar en 7 GB:** `llama3.1:8b` (~4.7 GB) no entra junto con el sistema;
  `bge-m3` (1.2 GB) es mejor en español pero compite por RAM y CPU.

### Perfil potente (NVIDIA)

- **Chat:** 7B–14B en `Q4_K_M` (`qwen2.5:7b`, `qwen2.5:14b`), según VRAM.
- **Embeddings:** `bge-m3` (1024 dimensiones, sin prefijos) o
  `qwen3-embedding:0.6b` (1024 dimensiones, mejor multilingüe).
- Al cambiar el modelo de embeddings hay que reindexar todo:
  `python scripts/dev.py ingest --reset`.

## Operación y diagnóstico

- **Primer arranque:** si `/health` devuelve `kb_chunks: 0`, falta ejecutar
  `python scripts/dev.py ingest`. Sin índice, todas las respuestas son el
  rechazo.
- **Respuestas lentas:** en CPU-only una respuesta completa tarda ~20–100 s.
  Usar `/api/v1/ask/stream` para ver los tokens mientras se generan.
- **Reindexar:** `python scripts/dev.py ingest`; tarda ~30–40 s para el corpus
  de ejemplo.
- **Cambiar el modelo de embeddings:** actualizar `OLLAMA_EMBED_MODEL`, ejecutar
  `python scripts/dev.py ingest --reset` y volver a medir la compuerta. Mezclar
  vectores de modelos distintos produce resultados inválidos.
- **Borrar el índice:** `chroma_db/` es un artefacto generado; se puede borrar
  y reconstruir sin riesgo.
- **PDF:** la ruta está implementada, pero el corpus de ejemplo no incluye PDF.
  Agregar uno pequeño y repetir el smoke test antes de confiar en ella.
- **Capa relacional:** `docker compose up -d postgres` deja la base lista con el
  esquema y los catálogos cargados; después basta apuntar `DATABASE_URL` a ella.
  Sin `DATABASE_URL` esas rutas responden `503` y el RAG sigue funcionando. Si la
  base está caída, el request tarda `DB_CONNECT_TIMEOUT` segundos y no queda
  colgado.
- **Reinicializar la base:** los scripts de `docker-entrypoint-initdb.d` solo se
  ejecutan con el volumen vacío. `docker compose down -v` seguido de
  `docker compose up -d postgres` es la forma de volver a cargar esquema y
  catálogos; el volumen es un artefacto de desarrollo.
- **Puerto 5432 ocupado:** si ya hay un PostgreSQL nativo escuchando en 5432, el
  contenedor no arranca. Detener el servicio nativo o cambiar el mapeo de puertos
  en el compose y en `DATABASE_URL`.
- **Radicado:** el número lo asigna la secuencia de PostgreSQL y un trigger
  rechaza cualquier `UPDATE` sobre la columna. No lo generes en la aplicación.

## Verificación

```bash
python scripts/dev.py check       # Ollama, compose, modelos y compileall
python scripts/check_schema.py    # modelos SQLAlchemy vs db/schema.sql
python scripts/dev.py ingest      # ejecutar dos veces: mismo collection_count
python scripts/dev.py api         # en una terminal
python scripts/dev.py smoke       # en otra terminal, con la API en ejecución
```

Resultado esperado: `/health` con `kb_chunks` mayor que 0 (504 con los cuatro
manuales actuales); una pregunta del dominio devuelve respuesta y fuentes; una
pregunta fuera del dominio devuelve `sources: []` y el texto exacto
`No tengo esa información en mi base local`.

## Banco de pruebas de la rúbrica

`scripts/rubric_check.py` traduce los cuatro criterios de la rúbrica KODO TAKAI
a pruebas ejecutables y emite un puntaje estimado sobre 60 junto con las brechas
que impiden el nivel sobresaliente. Por defecto no escribe nada: levanta la API
en proceso con `TestClient`, valida contratos y esquemas, y salta lo que necesita
un servidor real.

```bash
python scripts/dev.py rubric                  # contrato, validación y estado del modelo
python scripts/dev.py rubric --live-ai        # + latencia, fidelidad, rechazo e inyección
python scripts/dev.py rubric --json           # informe legible por máquina
python scripts/dev.py rubric --database-url "postgresql+psycopg://usuario:clave@localhost:5432/asistencia" --db-write
```

| Criterio | Sin flags | Con `--live-ai` | Con `--database-url` |
| ---------- | ----------- | ----------------- | ---------------------- |
| 1. Rendimiento de IA local | índice, dimensiones, modelos instalados, presupuesto de RAM, frase de rechazo | p50/p95, primer token, fidelidad al contexto, rechazo fuera de dominio, inyección de prompt | — |
| 2. Endpoints y lógica | inventario OpenAPI, `/health`, PQRSD, plazos hábiles, máquina de estados, paginación, ausencia de rutas legacy | respuesta con fuentes, streaming, `/sync-kb` con `--live-ingest` | alta, consulta y transición de punta a punta con `--db-write` |
| 3. Validación y seguridad | payloads inválidos, tipos, categoría inexistente, errores 5xx, higiene de secretos | resistencia a inyección de prompt | 404 de radicado inexistente |
| 4. Base de datos | esquema SQL vs modelos, triggers, índices, normalización, catálogos | — | objetos instalados, 13 restricciones, append-only, auditoría, correlativo y concurrencia |

Sin `DATABASE_URL`, el criterio 4 queda como «no verificable» y su techo es 10
puntos: el diseño está probado de forma estática, pero no hay evidencia en
ejecución. `--db-write` crea sus propias filas y las elimina al terminar.

Códigos de salida: `0` sin fallos críticos, `1` con al menos un fallo crítico,
`2` si no se puede iniciar el banco. `--strict` también devuelve `1` cuando queda
una brecha o una prueba sin ejecutar.

## Docker

El `docker-compose.yml` es CPU-only y define tres servicios:

| Servicio | Imagen | Puerto | Datos |
| ---------- | -------- | -------- | ------- |
| `ollama` | `ollama/ollama` | `11434` | Volumen `ollama` |
| `open-webui` | `ghcr.io/open-webui/open-webui:main` | `3000` | Volumen `open-webui` |
| `postgres` | `postgres:16-alpine` | `127.0.0.1:5432` | Volumen `postgres-data`, más `db/schema.sql` y `db/seed.sql` |

`postgres` cubre los endpoints que no son RAG. Se enlaza solo a loopback porque
usa una clave de desarrollo y la API corre en el host; los fragmentos y
embeddings siguen en `chroma_db/` y la base nunca los duplica. El healthcheck usa
`pg_isready` y el contenedor reserva 128 MB de `/dev/shm` para workers paralelos,
que es lo razonable en una máquina que comparte RAM con Ollama.

Para NVIDIA, agregar `gpus: all` al servicio `ollama` en una copia local; no
modificar el archivo del repositorio:

```yaml
services:
  ollama:
    image: ollama/ollama
    gpus: all  # solo variante NVIDIA
```

## Privacidad

- Sin llamadas a servicios externos: solo `OLLAMA_BASE_URL`.
- Telemetría de Chroma deshabilitada en ingesta y consulta.
- Sin autenticación: enlazar a `127.0.0.1` salvo que la red sea confiable.
- No commitear `.env`, `chroma_db/`, modelos ni cachés generadas.
