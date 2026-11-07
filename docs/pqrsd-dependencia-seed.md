# PQRSD: falta de datos en `dependencia` impide el alta (201)

## Estado

Abierto. Pendiente de corrección.

## Resumen

En una base recién inicializada, `POST /api/v1/pqrsd` con un payload
válido responde **409 Conflict** en lugar de **201 Created**. La causa no es
un error del endpoint: la tabla `dependencia` queda vacía porque
`db/seed.sql` no la carga, y `pqrsd.dependencia_id` es una FK obligatoria.

## Síntoma

```http
POST /api/v1/pqrsd
Content-Type: application/json

{
  "tipo_peticion_id": 1,
  "canal_id": 1,
  "dependencia_id": 1,
  "asunto": "Petición sobre retraso en envío",
  "detalle": "Solicito información acerca del estado actual de mi paquete con guía 12345."
}
```

Respuesta observada:

```json
{
  "detail": "The PQRSD violates a uniqueness or foreign key rule"
}
```

Estado HTTP: `409`.

## Causa raíz

1. `db/seed.sql` inserta datos en `canal_atencion`, `tipo_peticion`,
   `atributo_servicio`, `categoria_diferencial` y `glosario_termino`, pero
   **no inserta ninguna fila en `dependencia`**.
2. `db/schema.sql:260` declara la columna como obligatoria:
   `dependencia_id smallint not null references dependencia`.
3. `PqrsdRepository.create()` (`app/repositories/pqrsd_repository.py:151`)
   hace `flush()` y transforma el `IntegrityError` en `Conflict`, que el
   router (`app/api/v1/endpoints/pqrsd.py:52`) mapea a **409**.

El 409 es el comportamiento correcto dado el estado de la base. El defecto
está en los datos de arranque, no en la lógica del endpoint.

## Evidencia medida

Sobre la base configurada en `.env`:

| Tabla | Filas |
|---|---:|
| `dependencia` | 0 |
| `canal_atencion` | 4 |
| `tipo_peticion` | 7 |
| `categoria_diferencial` | 13 |
| `glosario_termino` | 10 |

Comprobaciones adicionales:

- `POST /api/v1/pqrsd` con `tipo_peticion_id` inexistente → 404 (correcto).
- `POST /api/v1/pqrsd` con body inválido → 422 (correcto).
- `GET /api/v1/pqrsd` → 200 con lista vacía (correcto).
- `GET /api/v1/pqrsd/{radicado}` inexistente → 404 (correcto).

## Impacto

- No se puede ejercitar el camino feliz (`201`) en una instalación limpia
  creada con `python scripts/dev.py db-init --seed`.
- Un cliente que envía una PQRSD válida recibe 409, que suele interpretarse
  como un conflicto de negocio cuando en realidad falta un catálogo.
- `scripts/rubric_check.py --db-write` **no detecta el faltante** porque
  crea su propia dependencia de prueba
  (`insert into dependencia ... 'Probe'`, ver `scripts/rubric_check.py:1558`
  y `scripts/rubric_check.py:1853`). El rubric pasa aunque el seed real no
  sirva para dar de alta una PQRSD.

## Corrección propuesta

Agregar al menos una dependencia real a `db/seed.sql`, de forma idempotente:

```sql
-- Catálogo mínimo para poder radicar PQRSD.
insert into dependencia (codigo, nombre, activa) values
    ('atencion_ciudadano', 'Atención al Ciudadano', true)
on conflict (codigo) do nothing;
```

Notas:

- El `codigo` y el `nombre` deben alinearse con el catálogo real de la
  entidad. El ejemplo usa el área de atención al ciudadano de los manuales.
- Para el alta de PQRSD solo `dependencia` es obligatoria; `sede`, `tramite`,
  `usuario` y `ciudadano` son opcionales y no bloquean el 201.
- Si se prefiere no sembrar datos de negocio, la alternativa es documentar
  explícitamente que el despliegue debe insertar la dependencia antes de
  habilitar el endpoint. Aun así, el seed por defecto debería permitir el
  camino feliz.

## Verificación

1. Base limpia y seed:

   ```bash
   python scripts/dev.py db-init --reset --seed
   ```

   O, con Docker:

   ```bash
   docker compose down -v && docker compose up -d postgres
   ```

2. Confirmar el catálogo:

   ```bash
   psql "$DATABASE_URL" -c "select id, codigo, nombre from dependencia;"
   ```

3. Alta real usando el `id` devuelto por la consulta anterior:

   ```bash
   curl -s -X POST http://127.0.0.1:8000/api/v1/pqrsd \
     -H 'Content-Type: application/json' \
     -d '{
       "tipo_peticion_id": 1,
       "canal_id": 1,
       "dependencia_id": 1,
       "asunto": "Petición sobre retraso en envío",
       "detalle": "Solicito información acerca del estado actual de mi paquete con guía 12345."
     }'
   ```

## Criterios de aceptación

- [ ] `db/seed.sql` inserta al menos una fila en `dependencia` de forma
      idempotente (`on conflict do nothing`).
- [ ] Una base limpia inicializada con `db-init --seed` deja
      `select count(*) from dependencia` mayor que cero.
- [ ] `POST /api/v1/pqrsd` con payload válido responde **201**.
- [ ] La respuesta incluye `radicado` con formato `PQRSD-YYYY-NNNNNN`,
      `estado = "recibida"`, el evento "Radicación inicial" y una
      `fecha_vencimiento` calculada en días hábiles.
- [ ] `python scripts/dev.py rubric --database-url "$DATABASE_URL" --db-write`
      sigue pasando.
- [ ] Se agrega una prueba de regresión que cubra el alta real contra la base
      sembrada, no solo los casos 422/503 con la base desconfigurada.

## Alcance

Esto no es una regresión del refactor `app/` frente a `api/`: ambos
entrypoints comparten la misma aplicación y el endpoint responde 409 de forma
correcta ante la violación de FK. Es un faltante de datos de arranque en
`db/seed.sql`.

## Referencias

- `db/schema.sql:254-273` — definición de `pqrsd`, FK a `dependencia`.
- `db/seed.sql` — catálogos sembrados; no incluye `dependencia`.
- `app/repositories/pqrsd_repository.py:151` — `create()` y mapeo de
  `IntegrityError` a `Conflict`.
- `app/api/v1/endpoints/pqrsd.py:52` — `POST /api/v1/pqrsd`.
- `scripts/rubric_check.py:1558,1853` — dependencia de prueba que oculta el
  faltante.
