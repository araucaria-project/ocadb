# OCADB - Observatory Cerro Murphy Database

A comprehensive astronomical database system for Observatory Cerro Murphy (OCM), designed to manage astronomical object catalogs, observations, and telescope operations.

## Main Components

### 1. **Core Library** (`ocadb/`)
Python package providing database models, utilities, and business logic. Contains:
- **Models**: Pydantic/Beanie models for astronomical objects, coordinates, observations
- **Database**: MongoDB connection management with configurable connection strings
- **File Parsers**: Utilities for importing data from various astronomical formats
- **CLI Module**: Command-line interface implementation

### 2. **REST API Server** (`api/`)
FastAPI-based HTTP server providing RESTful endpoints:
- **Endpoints**: CRUD operations for astronomical objects (`/api/v1/objects/`)
- **Modern FastAPI**: Uses lifespan context managers, dependency injection
- **Environment Config**: Configurable via `MONGODB_URL`, `MONGODB_DATABASE`
- **Auto Documentation**: Swagger/OpenAPI docs at `/docs`

### 3. **Web Application** (`frontend/`)
Vue.js 3 frontend for interactive data exploration:
- **Framework**: Vue.js with Node.js 20
- **API Integration**: Consumes REST API endpoints
- **Development**: Hot-reload development server

### 4. **CLI Tool**
Command-line interface for database operations:
- **Command**: `ocadb` (installed via Poetry scripts)
- **Import Functions**: Data ingestion from CSV, catalogs, various formats
- **Database Management**: Connection testing, basic operations

### 5. **Development Environment**
Docker Compose setup for full-stack development:
- **MongoDB**: Primary database (port 27017)
- **Mongo Express**: Database admin interface (port 8083, admin:pass)
- **API Server**: FastAPI backend (port 8084)
- **Web App**: Vue.js frontend (port 8085)

## Architecture Overview

**Monorepo Structure**: All components in single repository for coordinated development
**Database**: MongoDB with Beanie ODM for async operations and flexible schema
**Coordinate System**: GeoJSON Point2D with RA/Dec conversion utilities
**Name Canonization**: Standardized object naming for efficient searching
**Modern Python**: Python 3.12+ with type hints, async/await patterns

## Quick Start

### Prerequisites
- Python 3.12+
- Poetry (package manager)
- Docker & Docker Compose (for containerized setup)

### Installation

1. **Clone and setup**
   ```bash
   git clone <repository-url>
   cd ocadb
   poetry install --extras server
   ```

2. **Start development environment**
   ```bash
   docker-compose up -d
   ```

3. **Verify services**
   - API: `curl http://localhost:8084/`
   - Web: `http://localhost:8085`
   - CLI: `poetry run ocadb --help`

## Database Schema

### Core Models

**Object** (`ocadb/models/object.py`) - Astronomical objects:
```python
- name: str                              # Primary identifier
- canonized_name: str                    # Searchable normalized name
- aliases: list[str]                     # Alternative names
- coo: SkyCoord                         # Sky coordinates
- brightness: list[Brightness]          # Photometry (band, value)
- periodicity: list[Periodicity]        # Variability info
- area: Optional[SkyCoordPolygon]       # Extended objects
- parent_object_id: Optional[str]       # Hierarchical relationships
```

**SkyCoord** (`ocadb/models/geo.py`) - Coordinate system:
```python
- _lon_lat: Point2D                     # GeoJSON internal format
- epoch: float = 2000.0                 # Coordinate epoch
- radec: property                       # RA/Dec access (0-360, -90/+90)
```

**Observation Models**:
- `ObservationParameters` - Telescope scheduling requests
- `ScheduledObservationParameters` - Timed observation sequences
- `Project` - PI-led observation campaigns with object lists

## Development Workflow

### Local Development
```bash
# Install with all dependencies
poetry install --extras server

# Start MongoDB
docker run -d -p 27017:27017 mongo:latest

# Run API server
poetry run ocadb-server

# Use CLI
poetry run ocadb import --help
```

### Docker Development
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f fastapi

# Restart specific service
docker-compose restart fastapi
```

## Project Structure

```
ocadb/
├── api/                    # FastAPI REST API
│   ├── main.py            # App with lifespan, environment config
│   ├── routers/           # API endpoints (objects.py)
│   └── Dockerfile         # Container build
├── ocadb/                 # Core Python package
│   ├── models/            # Database models (object.py, geo.py)
│   │   └── __init__.py    # document_models list for Beanie
│   ├── cli/               # CLI implementation (ocadb.py, importer.py)
│   ├── files/             # Data parsers (common.py, tab_all.py)
│   ├── database.py        # Connection singleton with config
│   └── exceptions.py      # Custom exceptions
├── frontend/              # Vue.js web application
│   ├── src/               # Vue components and main app
│   └── package.json       # Node.js dependencies
├── tests/                 # Test suite (pytest + pytest-asyncio)
├── docker-compose.yml     # Development environment
└── pyproject.toml         # Poetry config, scripts, dependencies
```

## Key Development Notes

### Database Connection
- **Connection**: Singleton pattern in `database.py`
- **Configuration**: Environment variables `MONGODB_URL`, `MONGODB_DATABASE`
- **Models**: Auto-registered via `document_models` list
- **Async**: All operations use async/await with Motor driver

### API Patterns
- **Modern FastAPI**: Uses `lifespan` context manager (not deprecated `@app.on_event`)
- **Type Safety**: `Annotated[Model, Body(...)]` for request bodies
- **Pydantic v2**: `.model_dump()` instead of deprecated `.dict()`
- **Error Handling**: Proper HTTP status codes and error messages

### CLI Architecture
- **Typer**: Modern CLI framework with type hints
- **Async**: Event loop integration for database operations
- **Subcommands**: Import functionality organized in separate modules

### Import System
- **File Parsers**: Located in `ocadb/files/`
- **Coordinate Conversion**: RA/Dec string parsing via pyaraucaria
- **Name Processing**: Canonization for consistent searching
- **Brightness**: Multi-band photometry support (V, B, R, I, J, H, K)

## Configuration

### Environment Variables
```bash
MONGODB_URL=mongodb://localhost:27017    # Database connection
MONGODB_DATABASE=ocadb                   # Database name
```

### Poetry Scripts
```bash
ocadb-server    # Start FastAPI development server
ocadb          # CLI tool entry point
```

## Testing

```bash
# Run full test suite
poetry run pytest

# With coverage
poetry run pytest --cov=ocadb

# Specific test files
poetry run pytest tests/test_model_object.py
```

## Contributing

1. Fork repository and create feature branch
2. Follow existing code patterns and type hints
3. Add tests for new functionality
4. Update documentation for API changes
5. Ensure Docker Compose setup still works

## Technology Stack

- **Backend**: Python 3.12, FastAPI, Beanie (MongoDB ODM), Pydantic v2
- **Database**: MongoDB with geospatial indexing support
- **Frontend**: Vue.js 3, Node.js 20
- **CLI**: Typer with Rich formatting
- **Testing**: Pytest with async support
- **Containerization**: Docker, Docker Compose
- **Package Management**: Poetry with modern dependency groups

## License

This project is licensed under the GNU Lesser General Public License v3.0 (LGPLv3).

## Support

For development questions:
- Review existing test cases for usage patterns
- Check API documentation at `http://localhost:8084/docs`
- Examine model definitions in `ocadb/models/`
- Use CLI help: `poetry run ocadb --help`