# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

```bash
# Install dependencies (core + optional server components)
poetry install --extras server

# Run tests (requires MongoDB on localhost:27017)
poetry run pytest
poetry run pytest --cov=ocadb
poetry run pytest tests/test_model_object.py

# Start API server (dev mode with hot-reload on 0.0.0.0:8084)
poetry run ocadb-server

# CLI tool
poetry run ocadb --help
poetry run ocadb import --help
```

**Docker full-stack dev environment:**
```bash
docker compose up -d
# MongoDB: :27017 | API: :8084 | Web: :8085 | Mongo Express: :8083 (admin:pass)
```

**Frontend (Angular 21):**
```bash
cd frontend/ && npm install
npm run dev          # dev server on :8085, API proxied from localhost:8084
npm run dev:local    # dev server on :8085, API direct to localhost:8084 (no proxy)
npm run dev:remote   # dev server on :8085, API proxied from api.ocadb.space
npm run build        # production build → frontend/dist/
```

## Architecture Overview

**Monorepo** with three components: `ocadb/` (core Python library), `api/` (FastAPI server), `frontend/` (Angular 21 app).

### Frontend

Angular 21 with standalone components, signals (no RxJS observables for state), Vite build, Tailwind CSS (CDN). Uses native `fetch()` API, not Angular HttpClient.

- **Environment configs**: `src/environments/environment*.ts` — `dev` (proxy), `local` (direct :8084), `production` (relative `/api/v1`)
- **Services**: `ocadb.service.ts` (auth + observation search), `api-log.service.ts` (request debug logging), `fits.service.ts` (FITS file parsing), `gemini.service.ts` (AI analysis, stubbed)
- **Dev server**: port 8085, proxy config in `proxy.conf.json`

**Database**: MongoDB with Beanie ODM. All document models are collected via per-module `document_models` lists, aggregated in `ocadb/models/__init__.py`, and auto-registered by the singleton `Connection` in `ocadb/database.py` during `init_beanie`.

### API Versioning

Routers are mounted with version prefixes in `api/main.py`:
- `/api/v1/` — objects, observations, auth, files, test endpoints
- `/api/v2/` — observations_v2, files_v2 (newer patterns)

Swagger docs at `/swagger` (not the default `/docs`). OpenAPI spec at `/api/v1/openapi.json`.

### Core Domain Models

- **`Object`** (`ocadb/models/object.py`) — Astronomical catalog objects. Names auto-canonized via `pyaraucaria.lookup_objects.name_canonizator` in model validators. Aliases stored in canonized form. Uses `extra = "allow"` for flexible fields.
- **`Observation`** (`ocadb/models/observation.py`) — FITS observation records. Has multiple `@model_validator(mode='after')` that derive `telescope_coordinates`, `canonized_object_name`, `date_obs`, and `access_tags` from the embedded `FitsHeader`. Links to `FITSFile` documents via `List[Link[FITSFile]]`.
- **`FITSFile`** (`ocadb/models/file.py`) — Individual FITS files with storage tracking across three locations (observatory/hub/cloud) via `StorageStatus`. Integrates with S3 (Backblaze B2) for presigned URL generation.
- **`SkyCoord`** (`ocadb/models/geo.py`) — Coordinates stored as GeoJSON `Point2D` for MongoDB geospatial indexing. RA/Dec (0-360) converted to longitude (-180,180) internally. Construct with `SkyCoord(radec=(ra, dec))`.

### Access Control Model

Observations use document-level access control via `access_tags` (derived from FITS header fields: INSTRUME, ORIGIN, PI). The `AggregationQueryBuilder` (`api/services/aggregation_query_builder.py`) injects a `$redact` stage into MongoDB aggregation pipelines, filtering documents where user's `access_tags` intersect with document's tags. Paginated queries use `$facet` with `metadata` (count) and `data` (skip/limit).

### Geospatial Queries

`telescope_coordinates.lon_lat` has a `2dsphere` index. Cone searches use `$geoWithin` / `$centerSphere` via `QueryBuilder` and `OcaWithin` operator classes. The `ArchDistance` model converts arc-seconds to radians for MongoDB geo operators.

### Multi-Parameter Search

`MultiSearchForm` (`api/services/query_builder.py`) defines the search schema. The v2 observations router chains `.find()` calls conditionally for each non-null parameter, building queries incrementally.

## Key Patterns and Conventions

- **FastAPI**: `lifespan` context manager for startup/shutdown. `Annotated[Model, Body(...)]` for request bodies. `Annotated[str, Depends(AuthService.validate_token)]` for protected endpoints.
- **Pydantic v2**: `.model_dump()` not `.dict()`. `model_config` dict not inner `Config` class.
- **Async everywhere**: All DB operations are async. CLI uses event loop integration with Typer.
- **Name canonization**: All object name lookups use `name_canonizator()` from pyaraucaria — strips non-alphanumeric, lowercases. Always canonize before querying.
- **FITS header field naming**: `FitsHeader` uses aliases for hyphenated FITS keywords (e.g., `DATE_OBS` with `alias="DATE-OBS"`). Has `extra = "allow"` for non-standard headers.

## Authentication

JWT-based. Auth logic in `api/services/auth_service.py`, password hashing in `api/services/crypto_service.py` (bcrypt), user model in `ocadb/models/user.py`.

- Write operations require auth token; read operations on `/objects` are public
- Observations endpoints require auth for all operations (access-tag filtering)
- Auth endpoints: `/api/v1/auth/token` (login), `/api/v1/auth/register`, `/api/v1/auth/me`

## Environment Variables

Managed via `pydantic-settings` in `api/config.py` with `.env` file support (prefix: `ocadb.`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `MONGODB_URL` | `mongodb://localhost:27017` | Database connection |
| `MONGODB_DATABASE` | `ocadb` | Database name |
| `JWT_SECRET_KEY` | dev fallback | JWT signing (set properly in production) |
| `S3_KEY_ID`, `S3_SECRET`, `S3_REGION`, `ENDPOINT`, `BUCKET_NAME` | dev defaults | Backblaze B2 / S3 storage |

## Testing

- `pytest` + `pytest-asyncio` for async tests
- Test database: `mongodb://localhost:27017/test` (see `tests/conftest.py`)
- `beanie` fixture provides initialized DB connection via the singleton `Connection`

## Deployment

API deployed on Railway.com via `uvicorn api.main:app`. Frontend is a static SPA built from `frontend/dist`. CORS allows `localhost`, `*.ocadb.space`, and `*.app.github.dev`.
