import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.models import DesignSpec, HealthResponse, ParseRequest, ProjectPlan, ProjectRevisionRequest
from app.services.orchestrator import create_plan
from app.services.parser import PromptParseError, parse_box_prompt
from app.services.project_store import history, latest, save

app = FastAPI(title="AI-CAD Engineer API", version="0.1.0")

origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="ai-cad-engineer-api")


@app.post("/api/v1/designs/parse", response_model=DesignSpec)
def parse_design(request: ParseRequest) -> DesignSpec:
    try:
        return parse_box_prompt(request.prompt)
    except PromptParseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/v1/projects/analyze", response_model=ProjectPlan, status_code=201)
def analyze_project(request: ParseRequest) -> ProjectPlan:
    """Create a durable, explicit project plan before performing design work."""
    return save(create_plan(request.prompt))


@app.get("/api/v1/projects/{project_id}", response_model=ProjectPlan)
def get_project(project_id: str) -> ProjectPlan:
    project = latest(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.get("/api/v1/projects/{project_id}/versions", response_model=list[ProjectPlan])
def get_project_versions(project_id: str) -> list[ProjectPlan]:
    versions = history(project_id)
    if not versions:
        raise HTTPException(status_code=404, detail="Project not found")
    return versions


@app.post("/api/v1/projects/{project_id}/revisions", response_model=ProjectPlan, status_code=201)
def create_revision(project_id: str, request: ProjectRevisionRequest) -> ProjectPlan:
    current = latest(project_id)
    if not current:
        raise HTTPException(status_code=404, detail="Project not found")
    return save(create_plan(request.prompt, project_id=project_id, version=current.version + 1))
