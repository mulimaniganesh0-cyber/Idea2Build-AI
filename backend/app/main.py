import json
import os
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from app.models import CadGenerationResponse, ChatRequest, ChatResponse, DesignSpec, HouseProjectState, ParseRequest, ProjectPlan, ProjectRevisionRequest
from app.services import ollama_service
from app.services.cad import generate_primitive
from app.services.house_cad import build_canonical_house_cad
from app.services.house import create_house_concept_model
from app.services.house_design import HouseDesignOptionsRequest, HouseOptionSelection, HouseRequirements, analyze_site, create_design_options, extract_requirements, merge_requirements
from app.services.cad_exporter import (
    build_parametric_json,
    export_dxf,
    export_glb,
    export_obj,
    export_step,
    export_stl,
    rebuild_design,
)
from app.services.chat import handle_message
from app.services.ingestion import ingest_text, ingest_seed_documents
from app.services.orchestrator import create_plan
from app.services.parser import PromptParseError, parse_design_prompt
from app.services.pg_store import ensure_schema, health as pg_health
from app.services.project_store import (
    delete_engineering_load,
    delete_engineering_support,
    get_conversation,
    get_engineering_loads,
    get_engineering_supports,
    history,
    latest,
    latest_design,
    latest_geometry,
    latest_parametric,
    latest_cad_report,
    list_projects,
    save,
    save_conversation_turn,
    save_engineering_load,
    save_engineering_support,
    save_geometry,
    save_parametric,
    get_house_state,
    save_house_state,
    save_design,
    save_cad_report,
)
from app.services.retrieval import retrieve


class ExportRequest(BaseModel):
    """Parametric design JSON document submitted for CAD export."""
    parametric_json: dict[str, Any]


class HouseStateRequest(BaseModel):
    """House project state submitted to the canonical CAD engine."""
    project_id: str | None = None
    site_width_m: float | None = None
    site_length_m: float | None = None
    floors: int = 2
    building_width_m: float | None = None
    building_length_m: float | None = None
    floor_height_m: float = 3.0
    material: str | None = "reinforced_concrete"
    roof_type: str = "pitched"
    bedrooms: int = 3
    bathrooms: int = 2
    balcony: bool = False
    terrace: bool = True
    color_palette: str = "contemporary"
    version: int = 1

    def to_project_state(self) -> Any:
        return HouseProjectState(
            project_id=self.project_id or "house_default",
            site_width_m=self.site_width_m,
            site_length_m=self.site_length_m,
            floors=self.floors,
            building_width_m=self.building_width_m,
            building_length_m=self.building_length_m,
            floor_height_m=self.floor_height_m,
            material=self.material,
            roof_type=self.roof_type,
            bedrooms=self.bedrooms,
            bathrooms=self.bathrooms,
            balcony=self.balcony,
            terrace=self.terrace,
            color_palette=self.color_palette,
        )

app = FastAPI(title="AI-CAD Engineer API", version="0.2.0")

origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize PostgreSQL schema and seed engineering reference documents."""
    try:
        ensure_schema()
        ingest_seed_documents()
    except Exception as exc:
        # Startup continues even if pg/Ollama is temporarily unavailable
        print(f"[STARTUP WARNING] Could not initialize RAG: {exc}")


# ── Health ──────────────────────────────────────────────────────────────────

@app.get("/api/v1/health")
def health() -> dict:
    ollama = ollama_service.health()
    pg = pg_health()
    return {
        "status": "ok",
        "service": "ai-cad-engineer-api",
        "ollama": ollama.get("available", False),
        "chat_model": ollama_service.CHAT_MODEL,
        "embedding_model": ollama_service.EMBED_MODEL,
        "chat_model_ready": ollama.get("chat_model_ready", False),
        "embed_model_ready": ollama.get("embed_model_ready", False),
        "postgres": pg.get("postgres", False),
        "pgvector": pg.get("pgvector", False),
        "indexed_documents": pg.get("indexed_documents", 0),
        "indexed_chunks": pg.get("indexed_chunks", 0),
    }


# ── Chat ─────────────────────────────────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        response = handle_message(request.message, request.project_id)
        save_conversation_turn(response.project_id, request.message, response.message)
        saved_design = latest_design(response.project_id)
        if response.geometry is not None and saved_design is not None:
            version = saved_design[0]
            save_geometry(response.project_id, version, response.geometry.model_dump_json())
            if response.parametric_json is not None:
                save_parametric(response.project_id, version, json.dumps(response.parametric_json))
            house_state = get_house_state(response.project_id)
            if house_state is not None:
                house_model = build_canonical_house_cad(house_state, version=version)
                response.kernel_report = house_model.to_inspector_dict()
                response.house_design_state = house_state.model_dump(mode="json")
                save_cad_report(response.project_id, version, json.dumps(response.kernel_report))
        return response
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


# ── RAG ──────────────────────────────────────────────────────────────────────

@app.post("/api/rag/ingest")
async def rag_ingest(file: UploadFile = File(...)) -> dict:
    """Ingest a plain-text engineering document into the RAG knowledge base."""
    try:
        content_bytes = await file.read()
        text = content_bytes.decode("utf-8", errors="replace")
        result = ingest_text(
            text=text,
            filename=file.filename or "upload.txt",
            title=file.filename or "Uploaded Document",
            source="user_upload",
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/rag/query")
def rag_query(request: ParseRequest) -> dict:
    """Test RAG retrieval directly."""
    return retrieve(request.prompt, top_k=5)


# ── Design & CAD ─────────────────────────────────────────────────────────────

@app.post("/api/v1/designs/parse", response_model=DesignSpec)
def parse_design(request: ParseRequest) -> DesignSpec:
    try:
        return parse_design_prompt(request.prompt)
    except PromptParseError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/cad/generate", response_model=CadGenerationResponse)
def generate_cad(design: DesignSpec) -> CadGenerationResponse:
    try:
        return generate_primitive(design)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


# ── CAD Export ───────────────────────────────────────────────────────────────

def _get_boxes_from_request(request: ExportRequest):
    """Validate and rebuild Box3D geometry from a parametric JSON export request."""
    doc = request.parametric_json
    if not doc:
        raise HTTPException(status_code=422, detail="parametric_json is empty.")
    features = doc.get("features", [])
    if not features:
        raise HTTPException(status_code=422, detail="parametric_json has no features — cannot rebuild geometry.")
    boxes = rebuild_design(doc)
    if not boxes:
        raise HTTPException(
            status_code=422,
            detail="No solid geometry could be reconstructed from the feature history. "
                   "Ensure at least one box/plate/gusset feature exists."
        )
    return boxes, doc


@app.post("/api/cad/export/step")
def export_cad_step(request: ExportRequest) -> Response:
    """Export the parametric design as a genuine STEP AP203 CAD file.

    STEP is the primary mechanical CAD exchange format — not a renamed OBJ.
    The file contains CLOSED_SHELL / MANIFOLD_SOLID_BREP entities that can
    be opened in SolidWorks, CATIA, FreeCAD, and any AP203-compatible viewer.
    """
    boxes, doc = _get_boxes_from_request(request)
    try:
        step_bytes = export_step(boxes, doc)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"STEP export failed: {exc}") from exc
    if not step_bytes:
        raise HTTPException(status_code=500, detail="STEP exporter produced empty output.")
    obj_type = doc.get("object_type", "model").replace(" ", "_")
    version  = doc.get("version", 1)
    return Response(
        content=step_bytes,
        media_type="application/step",
        headers={"Content-Disposition": f'attachment; filename="{obj_type}_v{version}.step"'},
    )


@app.post("/api/cad/export/stl")
def export_cad_stl(request: ExportRequest) -> Response:
    """Export as binary STL for 3-D printing / mesh inspection."""
    boxes, doc = _get_boxes_from_request(request)
    try:
        stl_bytes = export_stl(boxes, doc.get("object_type", "part"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"STL export failed: {exc}") from exc
    if not stl_bytes:
        raise HTTPException(status_code=500, detail="STL exporter produced empty output.")
    obj_type = doc.get("object_type", "model").replace(" ", "_")
    version  = doc.get("version", 1)
    return Response(
        content=stl_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{obj_type}_v{version}.stl"'},
    )


@app.post("/api/cad/export/obj")
def export_cad_obj(request: ExportRequest) -> Response:
    """Export as Wavefront OBJ with face normals."""
    boxes, doc = _get_boxes_from_request(request)
    try:
        obj_bytes = export_obj(boxes, doc)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"OBJ export failed: {exc}") from exc
    obj_type = doc.get("object_type", "model").replace(" ", "_")
    version  = doc.get("version", 1)
    return Response(
        content=obj_bytes,
        media_type="model/obj",
        headers={"Content-Disposition": f'attachment; filename="{obj_type}_v{version}.obj"'},
    )


@app.post("/api/cad/export/glb")
def export_cad_glb(request: ExportRequest) -> Response:
    """Export as binary glTF 2.0 (GLB) for Three.js / web viewers."""
    boxes, doc = _get_boxes_from_request(request)
    try:
        glb_bytes = export_glb(boxes, doc)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"GLB export failed: {exc}") from exc
    obj_type = doc.get("object_type", "model").replace(" ", "_")
    version  = doc.get("version", 1)
    return Response(
        content=glb_bytes,
        media_type="model/gltf-binary",
        headers={"Content-Disposition": f'attachment; filename="{obj_type}_v{version}.glb"'},
    )


@app.post("/api/cad/export/dxf")
def export_cad_dxf(request: ExportRequest) -> Response:
    """Export a 2-D top-view DXF footprint drawing."""
    boxes, doc = _get_boxes_from_request(request)
    try:
        dxf_bytes = export_dxf(boxes, doc)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"DXF export failed: {exc}") from exc
    obj_type = doc.get("object_type", "model").replace(" ", "_")
    version  = doc.get("version", 1)
    return Response(
        content=dxf_bytes,
        media_type="application/dxf",
        headers={"Content-Disposition": f'attachment; filename="{obj_type}_v{version}.dxf"'},
    )


@app.post("/api/cad/export/parametric-json")
def export_parametric_json_endpoint(request: ExportRequest) -> Response:
    """Return the canonical parametric JSON — the editable AI/design source."""
    doc = request.parametric_json
    if not doc:
        raise HTTPException(status_code=422, detail="parametric_json is empty.")
    obj_type = doc.get("object_type", "model").replace(" ", "_")
    version  = doc.get("version", 1)
    return Response(
        content=json.dumps(doc, indent=2).encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{obj_type}_parametric_v{version}.json"'},
    )


@app.post("/api/cad/rebuild")
def rebuild_and_validate(request: ExportRequest) -> dict:
    """Validate that a parametric JSON can be successfully rebuilt into geometry.

    Returns the feature count, box count, and bounding box of the rebuilt model.
    Use this to confirm JSON round-trip fidelity before running heavy exports.
    """
    boxes, doc = _get_boxes_from_request(request)
    all_verts = [v for box in boxes for v in box.vertices()]
    xs = [v.x for v in all_verts]
    ys = [v.y for v in all_verts]
    zs = [v.z for v in all_verts]
    return {
        "status": "rebuild_ok",
        "model_id": doc.get("model_id"),
        "object_type": doc.get("object_type"),
        "version": doc.get("version"),
        "feature_count": len(doc.get("features", [])),
        "solid_count": len(boxes),
        "bounding_box_m": {
            "min": {"x": round(min(xs), 6), "y": round(min(ys), 6), "z": round(min(zs), 6)},
            "max": {"x": round(max(xs), 6), "y": round(max(ys), 6), "z": round(max(zs), 6)},
        },
        "supported_exports": ["step", "stl", "obj", "glb", "dxf", "json"],
    }


# ── House CAD Engineering Endpoints ─────────────────────────────────────────

@app.post("/api/house/cad/generate")
def house_cad_generate(request: HouseStateRequest) -> dict:
    """Build the canonical OpenCASCADE/build123d house CAD model.

    Returns genuine B-Rep topology metrics, physical properties, material
    assignments, and the parametric JSON needed for all downstream exports.
    ALL values come directly from the OpenCASCADE kernel — no fake data.
    """
    try:
        state = request.to_project_state()
        model = build_canonical_house_cad(state, version=request.version)
        return model.to_inspector_dict()
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"House CAD generation failed: {exc}") from exc


@app.post("/api/house/design-options")
def house_design_options(request: HouseDesignOptionsRequest) -> dict:
    """Persist explicit house requirements and return deterministic alternatives."""
    req = request.requirements
    plan = latest(req.project_id) if req.project_id else None
    state = get_house_state(req.project_id) if req.project_id else None
    if not plan:
        prompt = f"House design requirements: {req.model_dump_json(exclude={'project_id'})}"
        plan = save(create_plan(prompt))
    req.project_id = plan.project_id
    state = state or get_house_state(plan.project_id) or HouseProjectState(project_id=plan.project_id)
    previous = extract_requirements(plan.source_prompt, project_id=plan.project_id).model_dump(mode="json", exclude_none=True)
    previous.update({key: value for key, value in state.house_requirements.items() if value is not None})
    current = req.model_dump(mode="json", exclude_none=True)
    req = HouseRequirements.model_validate({**previous, **current, "project_id": plan.project_id})
    result = create_design_options(req, use_rag=request.use_rag)
    if result.get("requires_clarification"):
        state.house_requirements = {**previous, **current}
        save_house_state(state)
        return {"project_id": plan.project_id, **result}
    state = merge_requirements(state, req, result)
    save_house_state(state)
    return {"project_id": plan.project_id, "revision": state.design_revision, **result}


@app.post("/api/house/design-options/select")
def select_house_design_option(request: HouseOptionSelection) -> dict:
    """Select and persist an option, then regenerate viewer and canonical house geometry."""
    state = get_house_state(request.project_id)
    plan = latest(request.project_id)
    if not state or not plan:
        raise HTTPException(status_code=404, detail="House design project was not found.")
    option = next((item for item in state.design_options if item.get("option_id") == request.option_id), None)
    if option is None:
        raise HTTPException(status_code=404, detail="Design option was not found for this project.")
    state.selected_design_option_id = option["option_id"]
    state.roof_type = option["roof_type"]
    state.style = option["style"]
    state.interior_style = option["interior_style"]
    state.color_palette = option["palette"]
    state.roof_slope_deg = float(option["roof_slope_deg"])
    state.roof_overhang_mm = float(option["overhang_mm"])
    state.balcony = bool(option.get("balcony", state.balcony))
    state.parking = bool(option.get("parking", state.parking))
    state.gutters = bool(option.get("gutters", False))
    state.drainage = bool(option.get("drainage", False))
    state.design_revision += 1
    design = create_house_concept_model(state)
    design.feature_parameters.update({
        "bedrooms": float(state.bedrooms), "bathrooms": float(state.bathrooms),
        "parking": float(bool(state.parking)), "balcony": float(bool(state.balcony)),
        "terrace": float(bool(state.terrace)), "style": state.style,
        "interior_style": state.interior_style, "color_palette": state.color_palette,
        "roof_slope_deg": float(option["roof_slope_deg"]), "roof_overhang_mm": float(option["overhang_mm"]),
        "design_option_id": option["option_id"], "design_revision": float(state.design_revision),
        "site_area_sqft": float(state.site_analysis.get("plot_area_sqft") or 0),
        "drainage": float(state.drainage), "gutters": float(state.gutters),
        "ventilation_strategy": str(option.get("ventilation", "NOT_SPECIFIED")),
        "climate_profile": json.dumps(state.climate_profile, sort_keys=True),
        "knowledge_status": "FOUND" if state.knowledge_provenance else "NOT_REQUIRED",
        "pooja_room": float(state.pooja_room), "study_room": float(state.study_room), "utility": float(state.utility),
    })
    current = latest_design(request.project_id)
    version = (current[0] if current else 0) + 1
    save(create_plan(plan.source_prompt, project_id=request.project_id, version=plan.version + 1))
    save_design(request.project_id, version, design.model_dump_json())
    save_house_state(state)
    generated = generate_primitive(design)
    save_geometry(request.project_id, version, generated.geometry.model_dump_json())
    canonical = build_canonical_house_cad(state, version=version)
    report = canonical.to_inspector_dict()
    save_cad_report(request.project_id, version, json.dumps(report))
    parametric_json = canonical.to_parametric_json()
    save_parametric(request.project_id, version, json.dumps(parametric_json))
    return {"project_id": request.project_id, "version": version, "revision": canonical.revision, "option": option, "design_state": design, "house_design_state": state.model_dump(mode="json"), "geometry": generated.geometry, "kernel_report": report, "parametric_json": parametric_json, "site_analysis": state.site_analysis, "room_allocation": state.room_allocation, "reasoning": state.design_reasoning, "knowledge": {"status": state.knowledge_status, "trace": state.knowledge_trace, "sources": state.knowledge_provenance}}

@app.post("/api/house/cad/tree")
def house_cad_tree(request: HouseStateRequest) -> dict:
    """Return the full hierarchical component tree for the canonical house model.

    Returns all components with their types, structural classification, material
    assignments, positions, dimensions, and dependency chains.
    """
    try:
        state = request.to_project_state()
        model = build_canonical_house_cad(state, version=request.version)
        tree = model.tree
        components = tree.get_components()
        return {
            "model_id": model.model_id,
            "project_id": state.project_id,
            "revision": model.revision,
            "component_count": len(components),
            "structural_count": model.structural_components_count,
            "non_structural_count": model.non_structural_components_count,
            "structural_breakdown": model.structural_breakdown,
            "components": [
                {
                    "component_id": c.component_id,
                    "name": c.name,
                    "component_type": c.component_type,
                    "parent_id": c.parent_id,
                    "level": c.level,
                    "structural": c.structural,
                    "classification": c.classification.value,
                    "material_id": c.material_id,
                    "position_m": list(c.position_m),
                    "dimensions_m": list(c.dimensions_m),
                    "material_color": c.material_color,
                    "dependencies": c.dependencies,
                    "order_index": c.order_index,
                    "parameters": c.parameters,
                }
                for c in components
            ],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Component tree failed: {exc}") from exc


@app.post("/api/house/cad/properties")
def house_cad_properties(request: HouseStateRequest) -> dict:
    """Return verified physical and mechanical properties from the CAD kernel.

    All values (volume, surface area, mass, center of mass, moment of inertia)
    are computed by OpenCASCADE from the canonical solid geometry.
    """
    try:
        state = request.to_project_state()
        model = build_canonical_house_cad(state, version=request.version)
        return {
            "model_id": model.model_id,
            "project_id": state.project_id,
            "revision": model.revision,
            "source": "OpenCASCADE B-Rep kernel",
            "solid_topology": {
                "solid_count": model.solid_count,
                "shell_count": model.shell_count,
                "face_count": model.face_count,
                "edge_count": model.edge_count,
                "vertex_count": model.vertex_count,
            },
            "geometry": {
                "volume_m3": round(model.volume_m3, 4),
                "surface_area_m2": round(model.surface_area_m2, 4),
                "bounding_box_m": model.bounding_box_m,
                "bounding_box_mm": model.bounding_box_mm,
            },
            "physical_properties": {
                "mass_kg": round(model.total_mass_kg, 2),
                "effective_density_kg_m3": round(model.effective_density_kg_m3, 2),
                "center_of_mass_m": model.center_of_mass_m,
                "center_of_mass_mm": {
                    k: round(v * 1000.0, 2) for k, v in model.center_of_mass_m.items()
                },
                "moment_of_inertia": model.moment_of_inertia or "Not calculated",
            },
            "primary_material": model.primary_material.model_dump(),
            "all_materials": [m.model_dump() for m in model.materials_used],
            "disclaimer": "PRELIMINARY ENGINEERING CONCEPT — NOT STRUCTURALLY VALIDATED",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Physical properties failed: {exc}") from exc


@app.post("/api/house/cad/faces")
def house_cad_faces(request: HouseStateRequest) -> dict:
    """Return per-face B-Rep metadata from the canonical CAD kernel.

    Each face entry contains: area, centroid, surface normal, geometry type,
    and bounding box — all computed from real OpenCASCADE topology.
    """
    try:
        state = request.to_project_state()
        model = build_canonical_house_cad(state, version=request.version)
        return {
            "model_id": model.model_id,
            "project_id": state.project_id,
            "revision": model.revision,
            "face_count": len(model.face_metadata),
            "faces": [f.to_dict() for f in model.face_metadata],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Face metadata failed: {exc}") from exc


@app.post("/api/house/cad/parametric-json")
def house_cad_parametric_json(request: HouseStateRequest) -> Response:
    """Export the canonical parametric design JSON for a house — the editable source.

    This JSON can be submitted to /api/cad/export/* for STEP/STL/OBJ/GLB exports
    or stored as the authoritative design document for round-trip rebuild.
    """
    try:
        state = request.to_project_state()
        model = build_canonical_house_cad(state, version=request.version)
        doc = model.to_parametric_json()
        return Response(
            content=json.dumps(doc, indent=2).encode("utf-8"),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="house_v{request.version}_parametric.json"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Parametric JSON export failed: {exc}") from exc


@app.post("/api/house/cad/export/step")
def house_cad_export_step(request: HouseStateRequest) -> Response:
    """Export the canonical house CAD model as a genuine STEP AP214 solid.

    The STEP file contains real OpenCASCADE CLOSED_SHELL / MANIFOLD_SOLID_BREP
    entities — not a renamed mesh. Opens in SolidWorks, CATIA, FreeCAD, etc.
    """
    try:
        state = request.to_project_state()
        model = build_canonical_house_cad(state, version=request.version)
        step_bytes = model.export_step()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"House STEP export failed: {exc}") from exc
    return Response(
        content=step_bytes,
        media_type="application/step",
        headers={"Content-Disposition": f'attachment; filename="house_{state.project_id}_v{request.version}.step"'},
    )


@app.post("/api/house/cad/export/stl")
def house_cad_export_stl(request: HouseStateRequest) -> Response:
    """Export canonical house CAD solids as binary STL for 3D printing / mesh inspection."""
    try:
        state = request.to_project_state()
        model = build_canonical_house_cad(state, version=request.version)
        stl_bytes = model.export_stl()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"House STL export failed: {exc}") from exc
    return Response(
        content=stl_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="house_{state.project_id}_v{request.version}.stl"'},
    )


@app.post("/api/house/cad/export/obj")
def house_cad_export_obj(request: HouseStateRequest) -> Response:
    """Export canonical house CAD solids as Wavefront OBJ with face normals."""
    try:
        state = request.to_project_state()
        model = build_canonical_house_cad(state, version=request.version)
        obj_bytes = model.export_obj()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"House OBJ export failed: {exc}") from exc
    return Response(
        content=obj_bytes,
        media_type="model/obj",
        headers={"Content-Disposition": f'attachment; filename="house_{state.project_id}_v{request.version}.obj"'},
    )


# ── Projects ──────────────────────────────────────────────────────────────────

@app.post("/api/v1/projects/analyze", response_model=ProjectPlan, status_code=201)
def analyze_project(request: ParseRequest) -> ProjectPlan:
    return save(create_plan(request.prompt))


@app.get("/api/v1/projects", response_model=list[ProjectPlan])
def list_saved_projects() -> list[ProjectPlan]:
    return list_projects()


@app.get("/api/v1/projects/{project_id}/session")
def get_project_session(project_id: str) -> dict:
    plan = latest(project_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Project not found")
    design = latest_design(project_id)
    geometry = latest_geometry(project_id)
    parametric = latest_parametric(project_id)
    cad_report = latest_cad_report(project_id)
    house_state = get_house_state(project_id)
    return {
        "plan": plan.model_dump(mode="json"),
        "design_state": json.loads(design[1]) if design else None,
        "design_version": design[0] if design else None,
        "geometry": json.loads(geometry[1]) if geometry else None,
        "parametric_json": json.loads(parametric[1]) if parametric else None,
        "kernel_report": json.loads(cad_report[1]) if cad_report else None,
        "house_design_state": house_state.model_dump(mode="json") if house_state else None,
        "messages": get_conversation(project_id),
    }

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


# ════════════════════════════════════════════════════════════════════════════
# Phase 5.5 — Face Metadata, Engineering Loads & Supports
# ════════════════════════════════════════════════════════════════════════════

class _FaceInspectRequest(BaseModel):
    """Client asks for authoritative CAD face metadata from the server."""
    model_id: str
    geometry_hash: str
    model_revision: str
    component_id: str
    face_id: str


class _EngineeringLoadRequest(BaseModel):
    """Define a mechanical load on a specific CAD face (server-side only)."""
    model_id: str
    project_id: str
    model_revision: str
    geometry_hash: str
    component_id: str
    face_id: str
    type: str = "FORCE"            # FORCE | PRESSURE | MOMENT | TORQUE
    magnitude: float               # N or Pa or N·m
    unit: str = "N"
    direction_x: float = 0.0
    direction_y: float = 0.0
    direction_z: float = -1.0


class _EngineeringSupportRequest(BaseModel):
    """Define a boundary support on a specific CAD face."""
    model_id: str
    project_id: str
    model_revision: str
    geometry_hash: str
    component_id: str
    face_id: str
    type: str = "FIXED"            # FIXED | PINNED | ROLLER | SYMMETRY


def _resolve_face_metadata(geometry_hash: str, component_id: str, face_id: str) -> dict | None:
    """Look up authoritative face metadata from the CAD face cache."""
    from app.services.cad_face_system import get_cached_faces
    faces = get_cached_faces(geometry_hash)
    if faces is None:
        return None
    for f in faces:
        if f.component_id == component_id and f.face_id == face_id:
            return {
                "face_id": f.face_id,
                "component_id": f.component_id,
                "geometry_hash": f.geometry_hash,
                "model_revision": f.model_revision,
                "area_m2": f.area_m2,
                "area_mm2": f.area_mm2,
                "normal": f.normal,
                "center_m": f.center_m,
                "center_mm": f.center_mm,
                "surface_type": f.surface_type,
                "structural": f.structural,
                "classification": f.classification,
                "material_id": f.material_id,
                "bounding_box": f.bounding_box,
            }
    return None


def _validate_face_ownership(model_id: str, geometry_hash: str, model_revision: str,
                             component_id: str, face_id: str) -> dict:
    """Cross-check client-supplied face identity against authoritative server record."""
    meta = _resolve_face_metadata(geometry_hash, component_id, face_id)
    if meta is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Face '{face_id}' on component '{component_id}' (hash {geometry_hash}) "
                "is not registered in the CAD face cache. "
                "Regenerate the model first or resend the geometry."
            ),
        )
    if meta["model_revision"] != model_revision:
        raise HTTPException(
            status_code=409,
            detail=(
                f"model_revision mismatch: client sent '{model_revision}', "
                f"CAD authority says '{meta['model_revision']}'. "
                "Refresh the model before defining boundary conditions."
            ),
        )
    return meta


@app.post("/api/v1/cad/face/inspect")
def inspect_face(req: _FaceInspectRequest) -> dict:
    """Return server-authoritative face metadata for a single picked face."""
    meta = _resolve_face_metadata(req.geometry_hash, req.component_id, req.face_id)
    if meta is None:
        raise HTTPException(
            status_code=404,
            detail="Face not found in CAD authority. Rebuild the model first.",
        )
    return {"ok": True, "face": meta}


@app.get("/api/v1/cad/{geometry_hash}/faces")
def list_faces(geometry_hash: str) -> dict:
    """Return all authoritative faces for a geometry hash."""
    from app.services.cad_face_system import get_cached_faces
    faces = get_cached_faces(geometry_hash)
    if faces is None:
        raise HTTPException(
            status_code=404,
            detail="No faces cached for this geometry hash. Rebuild the model.",
        )
    return {
        "ok": True,
        "geometry_hash": geometry_hash,
        "count": len(faces),
        "faces": [
            {
                "face_id": f.face_id,
                "component_id": f.component_id,
                "area_m2": f.area_m2,
                "area_mm2": f.area_mm2,
                "normal": f.normal,
                "center_m": f.center_m,
                "center_mm": f.center_mm,
                "surface_type": f.surface_type,
                "structural": f.structural,
                "classification": f.classification,
                "material_id": f.material_id,
            }
            for f in faces
        ],
    }


# ── Loads ────────────────────────────────────────────────────────────────────

@app.post("/api/v1/engineering/loads", status_code=201)
def create_load(req: _EngineeringLoadRequest) -> dict:
    """Register an engineering load on a CAD face (server validates face identity)."""
    from uuid import uuid4
    from datetime import datetime, timezone
    import math

    # Server-side validation — client cannot fake face geometry
    meta = _validate_face_ownership(
        req.model_id, req.geometry_hash, req.model_revision, req.component_id, req.face_id
    )

    # Normalise direction vector
    dx, dy, dz = req.direction_x, req.direction_y, req.direction_z
    mag = math.sqrt(dx**2 + dy**2 + dz**2)
    if mag < 1e-9:
        raise HTTPException(status_code=422, detail="Direction vector must be non-zero.")
    dx, dy, dz = dx / mag, dy / mag, dz / mag

    load_type = req.type.upper()
    if load_type not in {"FORCE", "PRESSURE", "MOMENT", "TORQUE"}:
        raise HTTPException(status_code=422, detail=f"Unknown load type '{req.type}'.")

    if req.magnitude <= 0:
        raise HTTPException(status_code=422, detail="Load magnitude must be positive.")

    now = datetime.now(timezone.utc).isoformat()
    load_id = f"ld_{uuid4().hex[:12]}"
    record = {
        "load_id": load_id,
        "model_id": req.model_id,
        "project_id": req.project_id,
        "model_revision": req.model_revision,
        "geometry_hash": req.geometry_hash,
        "type": load_type,
        "magnitude": req.magnitude,
        "unit": req.unit,
        "direction_x": dx,
        "direction_y": dy,
        "direction_z": dz,
        "component_id": req.component_id,
        "face_id": req.face_id,
        "status": "ACTIVE",
        "created_at": now,
        "updated_at": now,
    }
    save_engineering_load(record)

    # Simple engineering sanity check
    warnings: list[str] = []
    if load_type == "FORCE" and req.magnitude > 500_000:
        warnings.append("Load exceeds 500 kN — verify units.")
    if load_type == "PRESSURE" and req.magnitude > 50_000_000:
        warnings.append("Pressure exceeds 50 MPa — verify units.")
    if not meta["structural"]:
        warnings.append(
            "Face is on a non-structural component — ensure load path is intended."
        )

    return {
        "ok": True,
        "load_id": load_id,
        "face": meta,
        "warnings": warnings,
        "message": f"{load_type} of {req.magnitude} {req.unit} registered on face {req.face_id}.",
    }


@app.get("/api/v1/engineering/loads/{model_id}")
def list_loads(model_id: str) -> dict:
    """Return all active loads for a model."""
    rows = get_engineering_loads(model_id)
    return {"ok": True, "model_id": model_id, "count": len(rows), "loads": rows}


@app.delete("/api/v1/engineering/loads/{load_id}")
def remove_load(load_id: str) -> dict:
    """Soft-delete a registered load."""
    if not delete_engineering_load(load_id):
        raise HTTPException(status_code=404, detail="Load not found or already deleted.")
    return {"ok": True, "load_id": load_id, "status": "DELETED"}


# ── Supports ─────────────────────────────────────────────────────────────────

@app.post("/api/v1/engineering/supports", status_code=201)
def create_support(req: _EngineeringSupportRequest) -> dict:
    """Register a structural support on a CAD face."""
    from uuid import uuid4
    from datetime import datetime, timezone

    meta = _validate_face_ownership(
        req.model_id, req.geometry_hash, req.model_revision, req.component_id, req.face_id
    )

    support_type = req.type.upper()
    if support_type not in {"FIXED", "PINNED", "ROLLER", "SYMMETRY"}:
        raise HTTPException(status_code=422, detail=f"Unknown support type '{req.type}'.")

    now = datetime.now(timezone.utc).isoformat()
    support_id = f"sp_{uuid4().hex[:12]}"
    record = {
        "support_id": support_id,
        "model_id": req.model_id,
        "project_id": req.project_id,
        "model_revision": req.model_revision,
        "geometry_hash": req.geometry_hash,
        "type": support_type,
        "component_id": req.component_id,
        "face_id": req.face_id,
        "status": "ACTIVE",
        "created_at": now,
        "updated_at": now,
    }
    save_engineering_support(record)

    warnings: list[str] = []
    if not meta["structural"]:
        warnings.append("Face is on a non-structural component — verify support intent.")

    return {
        "ok": True,
        "support_id": support_id,
        "face": meta,
        "warnings": warnings,
        "message": f"{support_type} support registered on face {req.face_id}.",
    }


@app.get("/api/v1/engineering/supports/{model_id}")
def list_supports(model_id: str) -> dict:
    """Return all active supports for a model."""
    rows = get_engineering_supports(model_id)
    return {"ok": True, "model_id": model_id, "count": len(rows), "supports": rows}


@app.delete("/api/v1/engineering/supports/{support_id}")
def remove_support(support_id: str) -> dict:
    """Soft-delete a registered support."""
    if not delete_engineering_support(support_id):
        raise HTTPException(status_code=404, detail="Support not found or already deleted.")
    return {"ok": True, "support_id": support_id, "status": "DELETED"}


# ── Engineering Summary ───────────────────────────────────────────────────────

@app.get("/api/v1/engineering/summary/{model_id}")
def engineering_summary(model_id: str) -> dict:
    """Return a combined load+support summary and basic equilibrium sanity-check."""
    import math
    loads = get_engineering_loads(model_id)
    supports = get_engineering_supports(model_id)

    # Resultant force vector (Newtons only)
    rx, ry, rz = 0.0, 0.0, 0.0
    for ld in loads:
        if ld["type"] == "FORCE":
            f = ld["magnitude"]
            rx += ld["direction_x"] * f
            ry += ld["direction_y"] * f
            rz += ld["direction_z"] * f
    resultant = math.sqrt(rx**2 + ry**2 + rz**2)

    warnings: list[str] = []
    if loads and not supports:
        warnings.append("Loads are defined but no supports exist — model is unrestrained.")
    if supports and not loads:
        warnings.append("Supports are defined but no loads are applied.")
    if resultant > 1e6:
        warnings.append(f"Total resultant force is {resultant/1000:.1f} kN — verify inputs.")

    return {
        "ok": True,
        "model_id": model_id,
        "load_count": len(loads),
        "support_count": len(supports),
        "resultant_force_N": round(resultant, 3),
        "warnings": warnings,
        "loads": loads,
        "supports": supports,
    }
