# UFC Graph — pipeline de datos

Ingestión, resolución de entidades y publicación del grafo que alimenta UFC Graph.

Convierte fuentes públicas (Wikipedia, feeds de medios) en un modelo canónico en Postgres,
con **procedencia obligatoria**: de cada dato se guarda de dónde salió, con qué confianza y
desde cuándo vale. Lo dudoso pasa por revisión humana antes de publicarse.

## Arquitectura

```text
CRUDO                CANÓNICO                      PUBLICADO
lo que dijo          lo que damos por cierto       lo que lee la web
la fuente            (con procedencia e historia)
   │                        │                             │
fetch ──► normalizar ──► resolver ──► revisar ──► publicar ──► grafo
```

- **Conectores** (puertos y adaptadores): añadir una fuente no toca el núcleo.
- **`raw_docs` con hash**: repetir un trabajo nunca duplica datos.
- **`claims`**: ningún valor se escribe sin su fuente y su periodo de validez.
- **Resolución de entidades por niveles**: id externo → alias → contexto → aproximado.
  Una noticia nunca crea entidades nuevas por su cuenta.

## Puesta en marcha

```bash
uv sync

# Postgres local con pgvector
docker run -d --name ufc-pg -e POSTGRES_PASSWORD=postgres -p 55432:5432 pgvector/pgvector:pg17

# Contra la nube: crea .env con DATABASE_URL (nunca se versiona)
uv run ufc-ingest migrate-db
uv run ufc-ingest status
```

## Comprobaciones

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest -q
```

## Estructura

```text
schema/              migraciones SQL, única fuente de verdad del modelo
src/ufc_ingest/
  config.py          configuración por entorno
  db.py              acceso a Postgres (psycopg 3, SQL plano)
  migrate.py         aplicador de migraciones
  cli.py             comandos
  connectors/        una carpeta por fuente
tests/
```

## Licencia y datos

El código es abierto. Los datos que produce llevan la atribución de sus fuentes; las de
Wikimedia se usan bajo CC BY-SA con la atribución correspondiente.
