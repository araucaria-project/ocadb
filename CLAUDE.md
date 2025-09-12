# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

**Python Environment:**
```bash
# Install dependencies (core + optional server components)
poetry install --extras server

# Run tests
poetry run pytest
poetry run pytest --cov=ocadb  # with coverage
poetry run pytest tests/test_model_object.py  # specific test file

# Start API server (development)
poetry run ocadb-server  # uses api/main.py:start_development_server

# CLI usage
poetry run ocadb --help
poetry run ocadb import --help
```

**Frontend Development (Vue.js):**
```bash
cd frontend/
npm install
npm run serve    # development server
npm run build    # production build
npm run lint     # ESLint
```

**Docker Development Environment:**
```bash
# Start all services (MongoDB, API, Web, Mongo Express)
docker-compose up -d

# View logs
docker-compose logs -f fastapi
docker-compose logs -f vuejs

# Restart specific service
docker-compose restart fastapi

# Services:
# - MongoDB: localhost:27017
# - API: localhost:8084
# - Web: localhost:8085  
# - Mongo Express: localhost:8083 (admin:pass)
```

## Architecture Overview

**Monorepo Structure**: Three main components in single repository:
- `ocadb/` - Core Python library with models, database, CLI
- `api/` - FastAPI REST server 
- `frontend/` - Vue.js 3 web application

**Database**: MongoDB with Beanie ODM for async operations. All models auto-registered via `document_models` list in `ocadb/models/__init__.py`.

**Connection Management**: Singleton pattern in `ocadb/database.py`. Environment variables:
- `MONGODB_URL` (default: mongodb://localhost:27017)
- `MONGODB_DATABASE` (default: ocadb)

## Authentication & Authorization

**JWT-based Authentication**: Uses JSON Web Tokens for API authentication with the following components:

- **AuthService** (`api/services/auth_service.py`) - Core auth logic with token creation/validation
- **User Management** (`ocadb/models/user.py`) - MongoDB-backed user storage via Beanie ODM  
- **Password Security** (`api/services/crypto_service.py`) - bcrypt hashing for secure password storage
- **Auth Endpoints** (`api/routers/api_auth.py`) - Login, registration, and user management

**Environment Variables**:
- `JWT_SECRET_KEY` - Secret key for JWT signing (required in production)
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` - Token expiration time (default: 30 minutes)

**API Protection**:
- Write operations (POST, PUT, DELETE) on `/api/v1/objects` require authentication
- Read operations (GET) are public
- Auth endpoints: `/api/v1/auth/token` (login), `/api/v1/auth/register`, `/api/v1/auth/me`
- Test endpoints: `/api/v1/test/free` (public), `/api/v1/test/protected` (requires auth)

**Usage Examples**:
```bash
# Register new user
curl -X POST "http://localhost:8084/api/v1/auth/register" \
     -H "Content-Type: application/json" \
     -d '{"username":"testuser","email":"test@example.com","full_name":"Test User","password":"testpass123"}'

# Login to get token  
curl -X POST "http://localhost:8084/api/v1/auth/token" \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=testuser&password=testpass123&grant_type=password"

# Use token for protected endpoints
curl -X POST "http://localhost:8084/api/v1/objects/" \
     -H "Authorization: Bearer YOUR_JWT_TOKEN_HERE" \
     -H "Content-Type: application/json" \
     -d '{"name":"Test Object","coord":{"ra":123.45,"dec":67.89}}'
```

## Key Patterns and Conventions

**FastAPI Patterns:**
- Uses modern `lifespan` context manager (not deprecated `@app.on_event`)
- Type hints with `Annotated[Model, Body(...)]` for request bodies
- Pydantic v2: use `.model_dump()` instead of deprecated `.dict()`
- Database initialization in lifespan startup

**Async/Await**: All database operations are async. CLI uses event loop integration with Typer.

**Models Structure:**
- `Object` model in `ocadb/models/object.py` - Core astronomical objects
- `SkyCoord` model in `ocadb/models/geo.py` - Coordinate system with GeoJSON Point2D
- Models use Beanie ODM with MongoDB collections

**Testing Setup:**
- Uses `pytest` with `pytest-asyncio` for async tests
- Test database: `mongodb://localhost:27017/test` (see `tests/conftest.py`)
- Beanie fixture provides initialized database connection

**Import System:**
- File parsers in `ocadb/files/` directory
- CLI import commands in `ocadb/cli/importer.py`
- Coordinate conversion via pyaraucaria dependency
- Name canonization for searchable object names

## Project-Specific Notes

**Poetry Scripts**: Two main entry points defined in `pyproject.toml`:
- `ocadb-server` - FastAPI development server
- `ocadb` - CLI tool

**Dependencies**: Core uses Python 3.12+ with optional server extras. Key libraries:
- Beanie (MongoDB ODM), FastAPI, Pydantic v2, Typer (CLI), Rich (formatting)
- Frontend: Vue.js 3 with Node.js 20

**Docker Composition**: Full development stack with hot-reload for both API and frontend. MongoDB data persisted in Docker volume.

**Coordinate System**: Custom GeoJSON-based coordinate model with RA/Dec conversion utilities and epoch support (default 2000.0).

## DigitalOcean Deployment

**App Platform Configuration**: `.do/app.yaml` defines the deployment spec for DigitalOcean App Platform:

- **API Service**: Python environment, builds with Poetry, runs on port 8000
  - Build: `poetry install --extras server --no-dev`
  - Run: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
  - Health check: `/health` endpoint
  - Environment variables: `MONGODB_URL` (secret), `MONGODB_DATABASE`, `PYTHONPATH`, `JWT_SECRET_KEY` (secret)

- **Frontend Service**: Node.js environment, builds Vue.js app
  - Build: `npm ci && npm run build`
  - Static site served from `/frontend/dist`
  - Build-time variable: `VUE_APP_API_URL=/api/v1`

- **Database**: Configured for unmanaged MongoDB Atlas connection
- **Routing**: API on `/api` path, frontend on `/` path
- **Auto-deploy**: Triggered on pushes to main branch

**Deployment Notes**:
- Update GitHub repo reference in `.do/app.yaml` before deploying
- Set required secrets in DigitalOcean dashboard:
  - `MONGODB_URL` - MongoDB Atlas connection string
  - `JWT_SECRET_KEY` - Strong secret key for JWT signing (generate with `openssl rand -hex 32`)
- Uses basic-xxs instances for cost efficiency