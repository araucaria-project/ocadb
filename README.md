# OCADB — Observatory Cerro Murphy Database

Astronomical object catalog management system: search, browse, and maintain observatory targets.

## Quick Start

```bash
docker compose up -d
```

Open [localhost:8085](http://localhost:8085) (frontend) or [localhost:8084/swagger](http://localhost:8084/swagger) (API docs).

Login: **dev** / **dev** (auto-seeded on fresh database, along with 12 sample observations).

| Service       | URL                     |
|---------------|-------------------------|
| Frontend      | http://localhost:8085    |
| API (Swagger) | http://localhost:8084/swagger |
| Mongo Express | http://localhost:8083 (admin / pass) |
| MongoDB       | localhost:27017         |

## Development Scenarios

**Prerequisites:** Python 3.12+, Node 22+, Poetry

### Full local stack (Docker)

```bash
docker compose up -d
```

### Frontend against production API

```bash
cd frontend && npm run dev:remote
```

Proxies `/api` to `api.ocadb.space` — no local backend needed.

### Local API against production database

```bash
ocadb.MONGODB_URL="mongodb+srv://..." poetry run ocadb-server
```

Or combine with the frontend: run the above, then `cd frontend && npm run dev` (proxies to local :8084).

### CLI

```bash
poetry install --extras server
poetry run ocadb --help
```

## Architecture

```
ocadb/       Core Python library — models (Beanie ODM), DB access, file parsers, CLI
api/         FastAPI REST server — CRUD, JWT auth, serves on :8084
frontend/    Angular 21 web app — Vite + Tailwind CSS, serves on :8085
```

- **Database:** MongoDB with Beanie (async ODM). GeoJSON coordinates with RA/Dec conversion.
- **Auth:** JWT-based. Reads are public, writes require authentication.
- **CLI:** Typer-based tool for data import and DB operations.

## Environment Variables

| Variable                         | Default                          | Description                  |
|----------------------------------|----------------------------------|------------------------------|
| `MONGODB_URL`                    | `mongodb://localhost:27017`      | MongoDB connection string    |
| `MONGODB_DATABASE`               | `ocadb`                          | Database name                |
| `JWT_SECRET_KEY`                 | *(generated)*                    | JWT signing secret           |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`| `30`                             | Token TTL in minutes         |

## Testing

Requires MongoDB on localhost:27017.

```bash
poetry run pytest
poetry run pytest --cov=ocadb
```

## License

LGPL-3.0-or-later
