# AI-CAD Engineer

An early, production-oriented foundation for a **prompt-to-CAD engineering platform**.

Describe an engineering idea in plain language — `Create a box 5m × 3m × 2m`, `Design a pedestrian bridge over a 50m span`, or `Create a 500mm steel shaft with 40mm diameter` — and the system returns a validated parametric design specification and renders a live 3D model in an interactive Three.js viewport.

The interface is **chat-first**: users describe an idea, receive structured clarification questions when requirements are missing, and see the preliminary 3D model beside the conversation. Internal plans, dependency-task graphs, and validation rules stay out of the user's way.

## Features

- **Conversational design loop** — create a box, then say `Make it 6m long` to regenerate and save a new design version
- **Multi-domain support** — mechanical primitives (box, cube, cylinder, shaft, plate, hole, sphere, cone) and civil/structural concepts (pedestrian bridges with truss, girder, arch, and cable-supported forms)
- **Bridge workflow** — context-aware multi-turn conversation to capture span, deck width, crossing environment, and bridge concept before generating a 3D concept model
- **Parametric geometry** — every model is a structured `ParametricGeometry` object rendered component-by-component in the Three.js viewer
- **Auditable project plans** — every request creates a persistent `ProjectPlan` with an engineering task dependency graph, missing-requirement flags, and explicit assumptions
- **Design versioning** — project plans and design specs are stored and versioned; full revision history is accessible via the API
- **Unit flexibility** — dimensions accepted and stored in mm, cm, m, in, and ft with automatic normalisation to millimetres
- **Safety rails** — dimension limits (up to 100 000 in source unit), ambiguity detection, and validation warnings on every design
- **Tests** — parser unit tests and API integration tests covering all supported primitives and the bridge workflow
- **Docker support** — `docker-compose.yml` for containerised local development

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite 5, Three.js 0.168 |
| Backend | FastAPI 0.115+, Pydantic 2.9+, Python 3.11+ |
| Testing | pytest 8+, HTTPX |
| Containerisation | Docker / docker-compose |

## Project Structure

```
AI-CAD-Engineer/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI app and API route definitions
│   │   ├── models.py             # Pydantic data models (DesignSpec, ProjectPlan, …)
│   │   └── services/
│   │       ├── parser.py         # Deterministic NL → DesignSpec parser
│   │       ├── cad.py            # Parametric geometry generator (Phase 1 boundary)
│   │       ├── chat.py           # Chat adapter; routes messages to the right handler
│   │       ├── orchestrator.py   # Deterministic project planner / task-graph builder
│   │       ├── bridge.py         # Context-aware pedestrian bridge workflow
│   │       └── project_store.py  # In-memory project and design version store
│   ├── tests/
│   │   ├── test_api.py           # Full API integration tests
│   │   └── test_parser.py        # Parser unit tests
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.tsx               # Chat UI and landing page
│   │   ├── ModelViewport.tsx     # Three.js 3D viewer component
│   │   ├── api.ts                # Typed fetch helpers
│   │   └── types.ts              # Shared TypeScript types
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
└── start-backend.ps1             # Windows one-command backend launcher
```

## Quick Start (Windows)

**Requirements:** Python 3.11+ and Node.js 20+.

Open two PowerShell windows from the project root:

```powershell
# Window 1 — API server
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

```powershell
# Window 2 — Web app
cd frontend
npm install
npm run dev
```

Open the Vite URL printed in the second window (normally **http://localhost:5173**).

The API allows both `http://localhost:5173` and `http://127.0.0.1:5173` as CORS origins; use either consistently in your browser.

### One-Command Backend Start (Windows)

From the project root, use the included launcher. It always uses the backend virtual environment and `backend/requirements.txt`. If port 8000 is taken by another service, it automatically falls back to port 8001.

```powershell
.\start-backend.ps1
```

## Docker

```powershell
docker-compose up --build
```

| Service | URL |
|---|---|
| API | http://localhost:8000 |
| Web app | http://localhost:5173 |

The `CORS_ORIGINS` environment variable in `docker-compose.yml` controls which origins the API accepts.

## API Reference

Base URL: `http://localhost:8000`

### Health

```http
GET /api/v1/health
```

### Chat (primary interface)

```powershell
# Start a new conversation
Invoke-RestMethod -Method Post http://localhost:8000/api/chat `
  -ContentType 'application/json' `
  -Body '{"message":"Create a box 5m x 3m x 2m"}'

# Continue an existing conversation (update a dimension)
Invoke-RestMethod -Method Post http://localhost:8000/api/chat `
  -ContentType 'application/json' `
  -Body '{"project_id":"<id>","message":"Make it 6m long"}'

# Bridge workflow
Invoke-RestMethod -Method Post http://localhost:8000/api/chat `
  -ContentType 'application/json' `
  -Body '{"message":"Design a pedestrian bridge over a 50m span."}'
```

The `ChatResponse` body includes:

| Field | Description |
|---|---|
| `message` | Plain-language reply |
| `requires_clarification` | Whether the assistant needs more information |
| `questions` | Structured clarification prompts |
| `suggestions` | Clickable option list (e.g. crossing environments, bridge concepts) |
| `project_id` | ID to pass on subsequent turns |
| `design_state` | Current `DesignSpec` when a model has been generated |
| `geometry` | `ParametricGeometry` object for the Three.js viewer |
| `active_domain` | `"bridge"` \| `"primitive"` \| `null` |

### Designs

```powershell
# Parse a prompt directly into a DesignSpec
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/designs/parse `
  -ContentType 'application/json' `
  -Body '{"prompt":"Create a box 5m x 3m x 2m"}'

# Generate parametric CAD geometry from a DesignSpec
Invoke-RestMethod -Method Post http://localhost:8000/api/cad/generate `
  -ContentType 'application/json' `
  -Body '<DesignSpec JSON>'
```

### Projects

```powershell
# Create an auditable project plan
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/projects/analyze `
  -ContentType 'application/json' `
  -Body '{"prompt":"Design a 100 metre pedestrian bridge"}'

# Retrieve the latest project plan
Invoke-RestMethod http://localhost:8000/api/v1/projects/<project_id>

# Retrieve the full version history
Invoke-RestMethod http://localhost:8000/api/v1/projects/<project_id>/versions

# Create a project revision
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/projects/<project_id>/revisions `
  -ContentType 'application/json' `
  -Body '{"prompt":"Design a 100 metre pedestrian bridge, 8m wide"}'
```

## Running Tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest
```

Tests cover: health check, prompt parsing, project analysis and versioning, chat-driven primitive creation and editing, cube creation and modification, shaft generation, cylinder generation, bridge context routing, bridge concept selection, and deck-width updates.

## Key Data Models

| Model | Description |
|---|---|
| `DesignSpec` | Versioned design contract between the parser/AI layer and the geometry layer. Includes object type, dimensions in source unit and normalised mm, material, feature parameters, and warnings. Schema version `1.0`. |
| `ProjectPlan` | Persistent project memory: engineering domain (civil, mechanical, structural, multidisciplinary), complexity level 1–7, task dependency graph, missing-requirement issues, and explicit assumptions. |
| `EngineeringTask` | A single task in the plan with a specialist label, dependency list, and status (`pending`, `blocked`, `ready`). |
| `ParametricGeometry` | List of `GeometryComponent` objects (name, type, position, dimensions in metres) consumed directly by the Three.js viewer. |
| `ChatResponse` | Full chat-turn response: reply text, clarification flags, design state, geometry, model action, and active domain. |
| `BridgeProjectState` | Mutable state for the multi-turn bridge workflow (span, deck width, crossing environment, bridge concept, material). |

## Supported Primitives

| Primitive | Example prompt |
|---|---|
| box | `Create a box 5m x 3m x 2m` |
| cube | `Create a cube of 3cm` |
| cylinder | `Create a cylinder with radius 20mm and height 100mm` |
| shaft | `Create a 500mm steel shaft with 40mm diameter` |
| plate | `Create a steel plate 200mm x 100mm x 10mm` |
| sphere | `Create a sphere with radius 50mm` |
| cone | `Create a cone with base radius 30mm and height 60mm` |
| hole | `Create a hole with radius 10mm and depth 50mm` |
| bridge | `Design a pedestrian bridge over a 50m span` |

## Roadmap

1. Replace/augment the deterministic parser and planner with an LLM structured-output adapter.
2. Expand the primitive and component library (wall, room, truss member, gear, bearing).
3. Convert validated `DesignSpec` into OpenCASCADE B-Rep geometry and export STEP / STL files.
4. Migrate the in-memory project store to PostgreSQL; add pgvector RAG with citation-backed engineering sources.
5. Add user authentication and multi-project management.

## Important Note

This MVP generates **visualisation geometry only**. It is not certified engineering software and must not be used for construction, safety, or manufacturing decisions without review by a qualified professional engineer.
