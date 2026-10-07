"""Deterministic residential requirement, site and room planning.

All computed areas are estimates for concept planning, not regulatory setbacks or
code checks. Climate measurements are never inferred from a place name.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models import HouseProjectState
from app.services.house import extract_site_dimensions, parse_floor_expression
from app.services.retrieval import retrieve


class HouseRequirements(BaseModel):
    project_id: str | None = None
    plot_width: float | None = Field(default=None, gt=0)
    plot_length: float | None = Field(default=None, gt=0)
    plot_unit: str = "ft"
    plot_area_sqft: float | None = Field(default=None, gt=0)
    built_up_area_sqft: float | None = Field(default=None, gt=0)
    floors: int | None = Field(default=None, ge=1, le=50)
    bedrooms: int | None = Field(default=None, ge=0, le=30)
    bathrooms: int | None = Field(default=None, ge=0, le=30)
    parking: bool | None = None
    kitchen_type: str | None = None
    balcony: bool | None = None
    terrace: bool | None = None
    style: str | None = None
    interior_style: str | None = None
    color_palette: str | None = None
    location: str | None = None
    orientation: str | None = None
    climate: dict[str, float | str] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    pooja_room: bool | None = None
    study_room: bool | None = None
    utility: bool | None = None
    budget_category: str | None = None
    pooja_room: bool | None = None
    study_room: bool | None = None
    utility: bool | None = None
    budget_category: str | None = None


class HouseDesignOptionsRequest(BaseModel):
    requirements: HouseRequirements
    use_rag: bool = True


class HouseOptionSelection(BaseModel):
    project_id: str
    option_id: str


PALETTES: dict[str, dict[str, str]] = {
    "modern_vibrant": {"wall": "#f5f0e6", "accent": "#0f766e", "wood": "#a16207", "roof": "#334155", "window_frame": "#1f2937", "interior_floor": "#c4a77d"},
    "warm_luxury": {"wall": "#f3e8d1", "accent": "#9a3412", "wood": "#6b3f24", "roof": "#3f2d20", "window_frame": "#292524", "interior_floor": "#bda27e"},
    "contemporary": {"wall": "#f8fafc", "accent": "#64748b", "wood": "#8b5e3c", "roof": "#334155", "window_frame": "#111827", "interior_floor": "#cbd5e1"},
    "tropical": {"wall": "#f5f5e6", "accent": "#166534", "wood": "#854d0e", "roof": "#9a3412", "window_frame": "#292524", "interior_floor": "#c4a77d"},
}


def extract_requirements(prompt: str, project_id: str | None = None) -> HouseRequirements:
    """Extract explicit house facts. Missing facts remain null."""
    req: dict[str, Any] = {"project_id": project_id}
    width_m, length_m, unit = extract_site_dimensions(prompt)
    if width_m and length_m:
        factor = 3.280839895 if unit == "ft" else 1.0
        req.update(plot_width=width_m * factor, plot_length=length_m * factor, plot_unit="ft" if unit == "ft" else "m")
        req["plot_area_sqft"] = width_m * length_m * 10.7639104
    area = re.search(r"(?P<n>\d+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|square\s+feet)\b", prompt, re.I)
    if area:
        req["plot_area_sqft"] = float(area.group("n"))
    built = re.search(r"(?:built[ -]?up|floor)\s*(?:area)?\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|square\s+feet)\b", prompt, re.I)
    if built:
        req["built_up_area_sqft"] = float(built.group(1))
    floors, *_ = parse_floor_expression(prompt)
    if floors is not None:
        req["floors"] = floors
    for name, key in (("bedrooms?", "bedrooms"), ("bathrooms?", "bathrooms")):
        match = re.search(rf"\b(\d+|one|two|three|four|five)\s+{name}\b", prompt, re.I)
        if match:
            words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
            req[key] = int(match.group(1)) if match.group(1).isdigit() else words[match.group(1).lower()]
    lower = prompt.lower()
    if re.search(r"\b(with|include|need)\s+parking\b|\bparking\s+(?:for|space)\b", lower): req["parking"] = True
    elif re.search(r"\bno\s+parking\b", lower): req["parking"] = False
    if "open kitchen" in lower: req["kitchen_type"] = "open"
    elif "closed kitchen" in lower: req["kitchen_type"] = "closed"
    for term, field in (("pooja", "pooja_room"), ("study", "study_room"), ("utility", "utility")):
        if re.search(rf"\b{term}(?:\s+room|\s+area)?\b", lower): req[field] = True
    for term, field in (("pooja", "pooja_room"), ("study", "study_room"), ("utility", "utility")):
        if re.search(rf"\b{term}(?:\s+room|\s+area)?\b", lower): req[field] = True
    for term in ("balcony", "terrace"):
        if re.search(rf"\b(?:with|include|add)\s+(?:a\s+)?{term}\b", lower): req[term] = True
        elif re.search(rf"\bno\s+{term}\b", lower): req[term] = False
    for key, choices in {
        "style": ("modern", "traditional", "luxury", "minimal", "tropical", "contemporary"),
        "interior_style": ("modern luxury", "modern minimal", "indian contemporary", "premium", "budget efficient"),
        "color_palette": ("modern vibrant", "warm luxury", "contemporary", "tropical"),
    }.items():
        found = next((choice for choice in choices if choice in lower), None)
        if found:
            req[key] = found.replace(" ", "_")
    loc = re.search(r"\b(?:in|location\s*:)\s+([A-Z][\w -]{1,50}?)(?:[,.]|\s+with\b|\s+on\b|$)", prompt)
    if loc: req["location"] = loc.group(1).strip()
    for k, pat in (("orientation", r"\b(north|south|east|west)(?:[- ]facing)?\b"),):
        m = re.search(pat, lower)
        if m: req[k] = m.group(1)
    if "high rainfall" in lower or "heavy rainfall" in lower:
        req["climate"] = {"rainfall_class": "high"}
    elif "hot climate" in lower or "hot and humid" in lower:
        req["climate"] = {"temperature_class": "hot_humid"}
    return HouseRequirements.model_validate(req)


def analyze_site(req: HouseRequirements) -> dict[str, Any]:
    area = req.plot_area_sqft
    if area is None and req.plot_width and req.plot_length:
        factor = 1.0 if req.plot_unit == "ft" else 10.7639104
        area = req.plot_width * req.plot_length * factor
    footprint = None
    assumptions = []
    if req.plot_width and req.plot_length:
        # Concept-only allocation allowance. Explicitly not a legal setback.
        footprint = req.plot_width * req.plot_length * 0.75 * 0.70
        assumptions.append("Concept footprint uses a 75% × 70% planning allowance; this is not a regulatory setback.")
    elif area:
        footprint = area * 0.75 * 0.70
        assumptions.append("Plot dimensions unavailable; footprint estimate uses 75% × 70% of stated area, not a regulatory setback.")
    else:
        assumptions.append("Plot area and dimensions not specified.")
    floors = req.floors or 2
    total_gross = req.built_up_area_sqft or (footprint * floors if footprint else None)
    floor_gross = total_gross / floors if total_gross is not None else None
    return {"plot_area_sqft": round(area, 2) if area is not None else None, "estimated_footprint_sqft": round(footprint, 2) if footprint is not None else None, "built_up_area_sqft": round(total_gross, 2) if total_gross is not None else None, "floors": floors, "gross_area_per_floor_sqft": round(floor_gross, 2) if floor_gross is not None else None, "circulation_allowance_pct": 22, "parking_area_sqft": 180 if req.parking else 0, "setbacks": "NOT_SPECIFIED", "assumptions": assumptions}


def validate_rectangles(rectangles: list[dict[str, Any]], bound_width: float, bound_length: float) -> dict[str, Any]:
    """Validate axis-aligned planning rectangles against an envelope and each other."""
    issues: list[dict[str, str]] = []
    epsilon = 1e-6
    for i, rect in enumerate(rectangles):
        x, y = float(rect.get("x", rect.get("x_ft", 0))), float(rect.get("y", rect.get("y_ft", 0)))
        width = float(rect.get("width", rect.get("width_ft", 0)))
        length = float(rect.get("length", rect.get("length_ft", 0)))
        name = str(rect.get("id", rect.get("room_id", f"rectangle_{i+1}")))
        if width <= 0 or length <= 0:
            issues.append({"status": "ERROR", "kind": "invalid_dimensions", "items": name})
        if x < -epsilon or y < -epsilon or x + width > bound_width + epsilon or y + length > bound_length + epsilon:
            issues.append({"status": "ERROR", "kind": "outside_envelope", "items": name})
        for other in rectangles[:i]:
            ox, oy = float(other.get("x", other.get("x_ft", 0))), float(other.get("y", other.get("y_ft", 0)))
            ow = float(other.get("width", other.get("width_ft", 0)))
            ol = float(other.get("length", other.get("length_ft", 0)))
            if x < ox + ow - epsilon and x + width > ox + epsilon and y < oy + ol - epsilon and y + length > oy + epsilon:
                other_name = str(other.get("id", other.get("room_id", "rectangle")))
                issues.append({"status": "ERROR", "kind": "overlap", "items": f"{other_name}, {name}"})
    return {"status": "ERROR" if issues else "PASS", "issues": issues, "checked_rectangles": len(rectangles), "boundary": {"width": bound_width, "length": bound_length}}


def allocate_rooms(req: HouseRequirements, site: dict[str, Any]) -> dict[str, Any]:
    floors = req.floors or 2
    count_bed = req.bedrooms or 3
    count_bath = req.bathrooms or max(1, count_bed)
    gross = site["gross_area_per_floor_sqft"]
    if gross is None:
        return {"floors": [], "overlap_check": "NOT_AVAILABLE", "fit_check": "REQUIRES_SITE_AREA"}
    net = gross * 0.78
    if req.plot_width and req.plot_length:
        plot_w_ft = req.plot_width if req.plot_unit == "ft" else req.plot_width * 3.280839895
        plot_l_ft = req.plot_length if req.plot_unit == "ft" else req.plot_length * 3.280839895
        bound_w, bound_l = plot_w_ft * 0.75, plot_l_ft * 0.70
    else:
        bound_w = math.sqrt(max(site["estimated_footprint_sqft"] or 0, 1) * 1.25)
        bound_l = math.sqrt(max(site["estimated_footprint_sqft"] or 0, 1) / 1.25)
    room_specs: list[tuple[str, float, int]] = [("living", 0.20, 0), ("kitchen", 0.11, 0), ("dining", 0.10, 0)]
    room_specs += [("bedroom", 0.18, min(floors - 1, i % floors)) for i in range(count_bed)]
    room_specs += [("bathroom", 0.05, min(floors - 1, i % floors)) for i in range(count_bath)]
    if req.pooja_room: room_specs.append(("pooja", 0.035, 0))
    if req.study_room: room_specs.append(("study", 0.10, min(1, floors - 1)))
    if req.utility: room_specs.append(("utility", 0.06, 0))
    room_specs += [("staircase", 0.08, f) for f in range(max(1, floors - 1))]
    if req.parking: room_specs.append(("parking", 180 / max(net, 1), 0))
    if req.balcony: room_specs.append(("balcony", 0.05, min(1, floors - 1)))
    if req.terrace: room_specs.append(("terrace", 0.08, floors - 1))
    grouped = []
    for floor in range(floors):
        rooms = []
        for i, (name, ratio, assigned) in enumerate(room_specs):
            if assigned != floor: continue
            area = max(35.0, net * ratio)
            length = math.sqrt(area * 1.25)
            width = area / length
            rooms.append({"room_id": f"{name}_{i+1}_f{floor+1}", "type": name, "area_sqft": round(area, 2), "width_ft": round(width, 2), "length_ft": round(length, 2), "x_ft": None, "y_ft": None})
        total = sum(r["area_sqft"] for r in rooms)
        cursor_x = cursor_y = row_depth = 0.0
        packed = True
        for room in rooms:
            w, l = room["width_ft"], room["length_ft"]
            if cursor_x + w > bound_w:
                cursor_x, cursor_y, row_depth = 0.0, cursor_y + row_depth, 0.0
            if cursor_y + l > bound_l:
                packed = False
            room["x_ft"], room["y_ft"] = round(cursor_x, 2), round(cursor_y, 2)
            cursor_x += w
            row_depth = max(row_depth, l)
        grouped.append({"floor": floor + 1, "rooms": rooms, "allocated_sqft": round(total, 2), "circulation_sqft": round(max(0, gross - total), 2), "packing_fit": packed, "available_width_ft": round(bound_w, 2), "available_length_ft": round(bound_l, 2)})
    for floor in grouped:
        floor["room_validation"] = validate_rectangles(floor["rooms"], floor["available_width_ft"], floor["available_length_ft"])
    fit = all(f["allocated_sqft"] <= gross * 1.02 and f["packing_fit"] and f["room_validation"]["status"] == "PASS" for f in grouped)
    all_issues = [issue for floor in grouped for issue in floor["room_validation"]["issues"]]
    overlap_status = "ERROR" if any(issue["kind"] == "overlap" for issue in all_issues) else "PASS"
    boundary_status = "ERROR" if any(issue["kind"] in ("outside_envelope", "invalid_dimensions") for issue in all_issues) else "PASS"
    return {"floors": grouped, "overlap_check": f"{overlap_status}: pairwise room rectangle intersections checked", "boundary_check": f"{boundary_status}: room rectangles checked against estimated floor envelope", "fit_check": "PASS" if fit else "WARNING: room allocation does not fit the estimated floor envelope", "furniture_collision_check": "NOT_RUN: furniture placements are not generated by the area planner", "wall_door_stair_check": "NOT_RUN: wall and door geometry is not part of the area planner", "basis": "Deterministic concept allocation; not construction documentation."}


def create_design_options(req: HouseRequirements, use_rag: bool = True) -> dict[str, Any]:
    missing = []
    if req.plot_area_sqft is None and not (req.plot_width and req.plot_length): missing.append("plot_size")
    if req.floors is None: missing.append("floors")
    if req.bedrooms is None: missing.append("bedrooms")
    if missing:
        questions = []
        if "plot_size" in missing: questions.append("What is the plot size (width × length or total area)?")
        if "floors" in missing or "bedrooms" in missing: questions.append("How many floors and bedrooms do you need?")
        return {"requirements": req.model_dump(mode="json"), "requires_clarification": True, "missing_requirements": missing, "questions": questions, "options": []}
    site = analyze_site(req)
    rooms = allocate_rooms(req, site)
    climate = req.climate or {"status": "NOT_SPECIFIED", "location_data": "NOT_AVAILABLE" if req.location else "NOT_SPECIFIED"}
    rag = {"status": "NOT_REQUIRED", "results": [], "trace": None}
    if use_rag and any(k in req.climate for k in ("rainfall_class", "temperature_class", "humidity_pct")):
        rag = retrieve("residential architecture guidance for " + json.dumps(req.climate), top_k=4)
    text = " ".join(str(x.get("content", "")) for x in rag.get("results", []))
    rag_roof = bool(req.climate.get("rainfall_class") == "high" and rag.get("status") == "FOUND" and re.search(r"pitched|sloped|gable|rainfall|drainage|gutter", text, re.I))
    style = req.style or "modern"
    palette = req.color_palette or "contemporary"
    options = [
        {"option_id": "modern_tropical", "name": "Modern Tropical", "style": "modern", "roof_type": "mixed", "roof_slope_deg": 20, "overhang_mm": 600, "ventilation": "cross_ventilation", "interior_style": req.interior_style or "modern_luxury", "palette": "tropical", "balcony": True if req.balcony is None else req.balcony, "palette_values": PALETTES["tropical"]},
        {"option_id": "contemporary", "name": "Contemporary", "style": "contemporary", "roof_type": "flat", "roof_slope_deg": 0, "overhang_mm": 300, "ventilation": "shaded_openings", "interior_style": req.interior_style or "modern_minimal", "palette": palette if palette in PALETTES else "contemporary", "balcony": False if req.balcony is None else req.balcony, "palette_values": PALETTES.get(palette, PALETTES["contemporary"])},
        {"option_id": "climate_optimized", "name": "Climate Optimized", "style": style, "roof_type": "pitched" if rag_roof or req.climate.get("rainfall_class") == "high" else "hip", "roof_slope_deg": 25 if req.climate.get("rainfall_class") == "high" else 18, "overhang_mm": 750 if req.climate.get("rainfall_class") == "high" else 500, "ventilation": "cross_ventilation", "drainage": bool(req.climate.get("rainfall_class") == "high"), "gutters": rag_roof, "interior_style": req.interior_style or "indian_contemporary", "palette": "warm_luxury", "balcony": req.balcony or False, "palette_values": PALETTES["warm_luxury"]},
    ]
    for option in options:
        option["roof_type"] = "gable" if option["roof_type"] in ("mixed", "pitched") else option["roof_type"]
        option["option_hash"] = hashlib.sha256(json.dumps(option, sort_keys=True).encode()).hexdigest()[:16]
    if req.parking is not None: options[0]["parking"] = req.parking
    for option in options:
        option.setdefault("parking", bool(req.parking))
    reasoning = [{"decision": "roof_type", "value": options[2]["roof_type"], "basis": "retrieved_architectural_guidance" if rag_roof else "explicit_climate_constraint" if req.climate.get("rainfall_class") == "high" else "design_option_strategy", "source_ids": [x.get("chunk_id") for x in rag.get("results", [])] if rag_roof else []}]
    return {"requirements": req.model_dump(mode="json"), "site_analysis": site, "climate_profile": climate, "room_allocation": rooms, "options": options, "knowledge": {"status": rag.get("status", "NOT_REQUIRED"), "trace": rag.get("trace"), "sources": rag.get("results", [])}, "reasoning": reasoning}


def merge_requirements(state: HouseProjectState, req: HouseRequirements, result: dict[str, Any]) -> HouseProjectState:
    values = req.model_dump(exclude={"project_id"}, exclude_none=True)
    if req.plot_width and req.plot_length:
        factor = 0.3048 if req.plot_unit == "ft" else 1.0
        state.site_width_m, state.site_length_m, state.unit = req.plot_width * factor, req.plot_length * factor, req.plot_unit
    elif req.plot_area_sqft and not (state.site_width_m and state.site_length_m):
        # A documented equivalent rectangular envelope is only a planning assumption.
        area_m2 = req.plot_area_sqft / 10.7639104
        state.site_width_m = math.sqrt(area_m2 * 1.25)
        state.site_length_m = math.sqrt(area_m2 / 1.25)
        state.unit = "m"
        result["site_analysis"]["assumptions"].append("Equivalent 1.25:1 plot rectangle used for a preview because only plot area was supplied; confirm actual plot dimensions before detailed design.")
    if req.floors: state.floors = req.floors
    if req.bedrooms is not None: state.bedrooms = req.bedrooms
    if req.bathrooms is not None: state.bathrooms = req.bathrooms
    for field in ("parking", "kitchen_type", "balcony", "terrace", "style", "interior_style", "color_palette", "location", "orientation", "built_up_area_sqft", "pooja_room", "study_room", "utility", "budget_category"):
        value = getattr(req, field)
        if value is not None: setattr(state, field, value)
    state.climate_profile = result["climate_profile"]
    state.house_requirements = {**state.house_requirements, **values}
    state.site_analysis = result["site_analysis"]
    state.room_allocation = result["room_allocation"]["floors"]
    state.room_planning_report = {k: v for k, v in result["room_allocation"].items() if k != "floors"}
    state.design_options = result["options"]
    state.design_reasoning = result["reasoning"]
    state.knowledge_provenance = result["knowledge"]["sources"]
    state.knowledge_status = result["knowledge"]["status"]
    state.knowledge_trace = result["knowledge"].get("trace") or {}
    state.status = "options_ready"
    return state
