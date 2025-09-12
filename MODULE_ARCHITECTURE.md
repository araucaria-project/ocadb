# OCADB Module Architecture

## Module Purposes & Responsibilities

### 📁 `ocadb/` - Core Domain Library
**Purpose**: Core business logic and domain models for astronomical data management

**Responsibilities**:
- **Domain Models** (`models/`): Core astronomical entities (Object, SkyCoord, User)
- **Database Layer** (`database.py`): MongoDB connection management and configuration
- **CLI Interface** (`cli/`): Command-line tools for data management
- **File Parsers** (`files/`): Data import/export utilities
- **Business Logic**: Core astronomical calculations and data processing

**Key Principles**:
- ✅ Framework-agnostic (can be used with any web framework)
- ✅ Pure domain logic (no HTTP/API concerns)
- ✅ Reusable across different interfaces (CLI, API, notebooks)
- ✅ Contains all Beanie Document models for database persistence

### 📁 `api/` - HTTP API Layer
**Purpose**: FastAPI-based REST API server exposing OCADB functionality via HTTP

**Responsibilities**:
- **Routers** (`routers/`): HTTP endpoint definitions and request/response handling
- **Services** (`services/`): API-specific business logic and orchestration
- **Schemas** (`schemas.py`): API-specific Pydantic models for request/response serialization
- **Application** (`main.py`): FastAPI app configuration and startup

**Key Principles**:
- ✅ Thin HTTP layer - delegates to `ocadb/` for business logic
- ✅ HTTP-specific concerns only (authentication, serialization, routing)
- ✅ No database models (imports from `ocadb.models`)
- ✅ Stateless request handlers

### 📁 `frontend/` - Web Interface
**Purpose**: Vue.js web application for interactive data exploration

**Responsibilities**:
- User interface for astronomical data visualization
- Integration with REST API endpoints
- Interactive data exploration tools

## Directory Structure

```
ocadb/
├── ocadb/                     # 🏛️  CORE DOMAIN LIBRARY
│   ├── models/                # 📊 Domain Models (MongoDB Documents)
│   │   ├── object.py         #     Astronomical objects
│   │   ├── geo.py            #     Coordinate systems  
│   │   ├── user.py           #     User management
│   │   └── __init__.py       #     Model registration for Beanie
│   ├── database.py           # 🔌 Database connection singleton
│   ├── cli/                  # 🖥️  Command-line interface
│   │   ├── ocadb.py         #     Main CLI app
│   │   └── importer.py      #     Data import commands
│   ├── files/                # 📁 File parsers and data processors
│   └── exceptions.py         # ❌ Domain exceptions
│
├── api/                       # 🌐 HTTP API LAYER
│   ├── main.py               # 🚀 FastAPI app and lifecycle
│   ├── routers/              # 🛣️  HTTP endpoints
│   │   ├── objects.py        #     /api/v1/objects/* routes
│   │   ├── api_auth.py       #     /api/v1/auth/* routes  
│   │   └── sample_api.py     #     /api/v1/test/* routes
│   ├── services/             # 🔧 API business logic
│   │   ├── auth_service.py   #     JWT authentication
│   │   ├── crypto_service.py #     Password hashing
│   │   └── database_connection.py # User database operations
│   └── schemas.py            # 📋 API request/response models
│
└── frontend/                  # 🖼️  WEB INTERFACE
    ├── src/                  # Vue.js application
    └── package.json          # Node.js dependencies
```

## Data Flow

```
[Frontend] → HTTP → [API Routes] → [API Services] → [OCADB Domain] → [MongoDB]
     ↑                  ↓              ↓              ↓
   Vue.js           FastAPI        Business        Beanie ODM
                   Routers         Logic           Documents
```

## Import Guidelines

### ✅ Correct Imports
```python
# API layer importing domain models
from ocadb.models import Object, User, UserInDB

# API services importing domain database
from ocadb.database import Connection

# API using domain exceptions
from ocadb.exceptions import ValidationError
```

### ❌ Incorrect Imports
```python
# Domain layer should NOT import API concerns
from api.services import AuthService        # ❌ No API imports in domain

# Frontend/external should NOT import API internals  
from api.services.auth_service import ...   # ❌ API internals are private
```

## Dependency Graph

```
┌─────────────┐
│  Frontend   │ (HTTP client)
└─────────────┘
       │
       ↓ HTTP/REST
┌─────────────┐
│     API     │ (FastAPI routers & services)
└─────────────┘
       │
       ↓ Python imports
┌─────────────┐
│    OCADB    │ (Domain models & business logic)
└─────────────┘
       │
       ↓ Beanie ODM
┌─────────────┐
│   MongoDB   │ (Database)
└─────────────┘
```

## Installation Patterns

```bash
# Core library only (CLI, domain models)
poetry install

# Core + API server (no auth)  
poetry install --extras api

# Core + authentication only
poetry install --extras auth

# Full server stack (recommended)
poetry install --extras server
```

This architecture ensures clear separation of concerns, testability, and maintainability.