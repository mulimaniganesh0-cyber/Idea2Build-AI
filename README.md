# AI-CAD Engineer

An early, production-oriented foundation for a prompt-to-CAD engineering platform.

It turns a constrained natural-language request such as `Create a box 5m × 3m × 2m` into a validated parametric design specification and displays the model in an interactive Three.js viewport.

## What is included

- **Frontend:** React, TypeScript, Vite, Three.js
- **Backend:** FastAPI and Pydantic
- **Design contract:** a versioned JSON object between the AI/parser layer and geometry layer
- **Project reasoning foundation:** persistent project plans, dependency-task graphs, explicit missing requirements, and revisions
- **Safety:** explicit validation, dimension limits, and warnings for ambiguous prompts
- **Tests:** parser and API tests

The parser and project planner are deliberately deterministic in this early phase. They are safe fallbacks and test harnesses that a future LLM structured-output adapter will target; they do not claim to perform engineering design.

## Quick start (Windows)

Requirements: Python 3.11+ and Node.js 20+.

Open two PowerShell windows from this folder.

```powershell
# Window 1 — API
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

```powershell
# Window 2 — web app
cd frontend
npm install
npm run dev
```

Then open the Vite URL printed in the second window (normally http://localhost:5173).

## API example

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/designs/parse `
  -ContentType 'application/json' `
  -Body '{"prompt":"Create a box 5m x 3m x 2m"}'
```

Create an auditable project plan before design generation:

```powershell
Invoke-RestMethod -Method Post http://localhost:8000/api/v1/projects/analyze `
  -ContentType 'application/json' `
  -Body '{"prompt":"Design a 100 metre pedestrian bridge"}'
```

## Next milestones

1. Add primitive and component generators (cylinder, plate, hole, shaft, wall, room).
2. Replace/augment the deterministic planner with an LLM structured-output adapter.
3. Convert validated design JSON into OpenCASCADE B-Rep geometry and export STEP/STL.
4. Migrate project memory to PostgreSQL; add pgvector RAG with citation-backed sources.

## Important note

This MVP creates visualization geometry only. It is not certified engineering software and must not be used for construction, safety, or manufacturing decisions without qualified review.
