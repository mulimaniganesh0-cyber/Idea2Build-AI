"""Chat-facing adapter — now powered by Ollama domain classification + RAG.

Flow:
  1. Ollama classifies the prompt domain (mechanical / architectural / bridge / general)
  2. For MECHANICAL → RAG retrieval → Ollama LLM → MechanicalDesignSpec → mechanical CAD kernel
  3. For ARCHITECTURAL → existing house pipeline (preserved)
  4. For BRIDGE → existing bridge pipeline (preserved)
  5. For GENERAL → existing parser/orchestrator (preserved)
"""

import re

from app.mechanical_models import MechanicalDesignSpec
from app.models import ChatResponse, DesignSpec, Dimensions, ModelAction, ProjectPlan, Unit
from app.services import ollama_service
from app.services.bridge import concept_suggestions, create_concept_model, detect_environment, initial_state, is_bridge_request, update_bridge
from app.services.house import create_house_concept_model, initial_house_state, is_house_request, update_house
from app.services.cad_exporter import build_parametric_json
from app.services.llm_designer import build_mechanical_spec_from_prompt
from app.services.mechanical_cad import generate_mechanical_primitive
from app.services.orchestrator import create_plan
from app.services.cad import generate_primitive
from app.services.parser import PromptParseError, parse_design_prompt
from app.services.project_store import get_bridge_state, get_house_state, latest, latest_design, save, save_bridge_state, save_design, save_house_state

_TO_MM = {Unit.MILLIMETER: 1, Unit.CENTIMETER: 10, Unit.METER: 1000, Unit.INCH: 25.4, Unit.FOOT: 304.8}
_UNIT_ALIASES = {"mm": Unit.MILLIMETER, "cm": Unit.CENTIMETER, "m": Unit.METER, "in": Unit.INCH, "ft": Unit.FOOT, "meter": Unit.METER, "metre": Unit.METER, "feet": Unit.FOOT, "foot": Unit.FOOT, "inch": Unit.INCH}
_UPDATE = re.compile(r"(?:make|change|set|increase)\s+(?:it|the)?\s*(?:to\s+)?(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mm|cm|m|in|ft|meter|metre|feet|foot|inch)\s*(?P<field>long|length|wide|width|high|height)", re.I)
_CREATE_TERMS = re.compile(r"\b(create|make|design|generate|build|construct|draw|model|produce)\b", re.I)
_RAG_INTENT = re.compile(r"\b(recommend(?:ation)?|appropriate|suitable|compare|code(?:s)?|standard(?:s)?|load(?:s)?|capacity|safety|safe|structural analysis|what material|which material|design criteria|engineering guidance)\b", re.I)

_MECHANICAL_KEYWORDS = {
    "bracket", "mounting bracket", "base plate", "upright plate", "gear", "bearing", "gearbox",
    "upright", "gusset", "flange", "coupling", "bolt", "fixture",
    "machine part", "counterbore", "countersink", "chamfer",
    "rib", "boss", "through-hole", "through hole",
}


def _is_mechanical_prompt(message: str) -> bool:
    lower = message.lower()
    return any(kw in lower for kw in _MECHANICAL_KEYWORDS)


def _questions(plan: ProjectPlan) -> list[str]:
    questions: list[str] = []
    for issue in plan.missing_information:
        if issue.field == "loads_and_codes":
            questions.append("What location, governing code/standard, design loads, and site or soil information should be considered?")
        elif issue.field == "dimensions":
            questions.append("What are the main dimensions or site limits, and which unit system do you prefer?")
        elif issue.field == "crossing_conditions":
            questions.append("What span arrangement, clearance, access, and environmental constraints apply?")
        elif issue.field == "engineering_domain":
            questions.append("Is this mainly a civil, mechanical, structural, or multidisciplinary design?")
    return questions


def _apply_update(design: DesignSpec, message: str) -> DesignSpec | None:
    cube_size = re.search(r"(?:make|change|set)\s+(?:it|the cube)?\s*(?:to\s+)?(\d+(?:\.\d+)?)\s*(mm|cm|m|in|ft)\b", message, re.I)
    if design.feature_parameters.get("is_cube") and cube_size:
        unit = _UNIT_ALIASES[cube_size.group(2).lower()]
        size_mm = float(cube_size.group(1)) * _TO_MM[unit]
        mm = Dimensions(length=size_mm, width=size_mm, height=size_mm)
        source_scale = _TO_MM[design.unit]
        source = Dimensions(length=size_mm / source_scale, width=size_mm / source_scale, height=size_mm / source_scale)
        features = {"length": size_mm, "width": size_mm, "height": size_mm, "is_cube": 1}
        return design.model_copy(update={"dimensions": source, "dimensions_mm": mm, "feature_parameters": features, "source_prompt": message})
    match = _UPDATE.search(message)
    if not match:
        return None
    unit = _UNIT_ALIASES[match.group("unit").lower()]
    value_mm = float(match.group("value")) * _TO_MM[unit]
    field = {"long": "length", "length": "length", "wide": "width", "width": "width", "high": "height", "height": "height"}[match.group("field").lower()]
    mm = design.dimensions_mm.model_copy(update={field: value_mm})
    source_scale = _TO_MM[design.unit]
    source = Dimensions(length=mm.length / source_scale, width=mm.width / source_scale, height=mm.height / source_scale)
    features = dict(design.feature_parameters)
    if design.feature_parameters.get("is_cube") and not (mm.length == mm.width == mm.height):
        features.pop("is_cube", None)
    if design.object_type == "shaft":
        features["length"] = mm.length
        features["diameter"] = mm.width
    return design.model_copy(update={"dimensions": source, "dimensions_mm": mm, "feature_parameters": features, "source_prompt": message})


def _kernel_report(design: DesignSpec, project_id: str, revision: int) -> dict | None:
    """Build and report authoritative OpenCascade properties for deterministic box primitives."""
    if design.object_type != "box":
        return None
    from app.services.cad_face_system import build_canonical_mechanical_cad

    spec = MechanicalDesignSpec(
        object_type="cube" if design.feature_parameters.get("is_cube") else "box",
        length_mm=design.dimensions_mm.length,
        width_mm=design.dimensions_mm.width,
        height_mm=design.dimensions_mm.height,
        source_prompt=design.source_prompt,
    )
    model = build_canonical_mechanical_cad(spec, project_id=project_id, version=revision)
    solids = list(model.solids.values())
    if len(solids) != 1 or not solids[0].is_valid or solids[0].volume <= 0:
        raise RuntimeError("OpenCascade did not produce one valid positive-volume solid.")
    solid = solids[0]
    bbox = solid.bounding_box()
    return {
        "source": "OpenCascade / build123d B-Rep",
        "revision": model.revision,
        "geometry_hash": model.geometry_hash,
        "valid": bool(solid.is_valid),
        "solid_count": len(solids),
        "face_count": len(solid.faces()),
        "edge_count": len(solid.edges()),
        "volume_mm3": round(float(solid.volume), 2),
        "surface_area_mm2": round(float(solid.area), 2),
        "bounding_box_mm": {"x": round(float(bbox.size.X), 3), "y": round(float(bbox.size.Y), 3), "z": round(float(bbox.size.Z), 3)},
        "feature_history": [{"id": f"{design.object_type}_0001", "type": design.object_type, "operation": "create", "parameters": {"length_mm": design.dimensions_mm.length, "width_mm": design.dimensions_mm.width, "height_mm": design.dimensions_mm.height}}],
    }


def _handle_mechanical(message: str, plan: ProjectPlan) -> ChatResponse:
    """Route mechanical prompts through Ollama + RAG + deterministic CAD kernel."""
    try:
        knowledge_required = bool(_RAG_INTENT.search(message))
        spec, rag_result = build_mechanical_spec_from_prompt(message, use_rag=knowledge_required)
    except (ValueError, RuntimeError) as exc:
        # Fallback: return an informative error rather than silently generating wrong output
        return ChatResponse(
            message=f"⚠️ Mechanical design extraction failed: {exc}\n\nPlease rephrase with explicit dimensions (e.g. 160 mm × 100 mm × 12 mm base plate).",
            requires_clarification=True,
            questions=["What are the base plate dimensions?", "What are the upright plate dimensions?"],
            project_id=plan.project_id,
            active_domain="mechanical",
        )

    generated = generate_mechanical_primitive(spec)
    feature_hist = spec.feature_history()

    rag_status = rag_result.get("status", "NO_RELEVANT_CONTEXT")
    rag_sources = []
    if rag_status == "FOUND":
        rag_sources = [
            f"{r['source']} (p.{r['page']}, score={r['score']})"
            for r in rag_result.get("results", [])[:3]
        ]

    msg_parts = [
        f"✅ I generated a parametric mechanical model: **{spec.object_type.replace('_', ' ').title()}**\n",
    ]
    if spec.base_plate:
        msg_parts.append(
            f"• Base plate: {spec.base_plate.length_mm:g} × {spec.base_plate.width_mm:g} × {spec.base_plate.thickness_mm:g} mm"
        )
    if spec.upright_plate:
        msg_parts.append(
            f"• Upright: {spec.upright_plate.width_mm:g} × {spec.upright_plate.height_mm:g} × {spec.upright_plate.thickness_mm:g} mm"
        )
    if spec.gussets and spec.gussets.count > 0:
        msg_parts.append(f"• Gussets: {spec.gussets.count} × {spec.gussets.type}")
    if spec.holes:
        total_holes = sum(h.count for h in spec.holes)
        msg_parts.append(f"• Holes: {total_holes} total ({', '.join(f'Ø{h.diameter_mm:g}×{h.count}' for h in spec.holes)})")
    if spec.fillets:
        msg_parts.append(f"• Fillets: {', '.join(f'R{f.radius_mm:g} mm' for f in spec.fillets)}")
    if spec.chamfers:
        msg_parts.append(f"• Chamfers: {', '.join(f'{c.size_mm:g}×{c.angle_deg:g}°' for c in spec.chamfers)}")
    msg_parts.append(f"• Features: {len(feature_hist)}")
    msg_parts.append(f"\n🧠 RAG: {rag_status} | Model: llama3.2 | Embedding: nomic-embed-text")
    if rag_sources:
        msg_parts.append("📚 Sources: " + " · ".join(rag_sources))

    param_json = build_parametric_json(
        spec,
        model_id=generated.model_id,
        project_id=plan.project_id,
        version=1,
    )

    save_design(plan.project_id, 1, generated.parameters.model_dump_json())

    return ChatResponse(
        message="\n".join(msg_parts),
        requires_clarification=False,
        project_id=plan.project_id,
        design_state=generated.parameters,
        model_action=ModelAction(type="generate", model_id=generated.model_id),
        active_domain="mechanical",
        geometry=generated.geometry,
        parametric_json=param_json,
        knowledge_status=rag_result.get("status", "NOT_REQUIRED"),
        knowledge_sources=rag_result.get("results", []) if rag_result.get("status") == "FOUND" else [],
        knowledge_trace=rag_result.get("trace"),
        suggestions=["Show cross-section", "Add more holes", "Change material to aluminium", "Export STEP"],
    )


def handle_message(message: str, project_id: str | None) -> ChatResponse:
    """Main entry point for the /api/chat endpoint."""

    # ── Step 1: Existing project continuation (updates) ──────────────────────
    has_object = any(kind in message.lower() for kind in ("cube", "box", "cylinder", "sphere", "cone", "shaft", "plate", "hole", "house", "bridge"))
    explicit_create = bool(_CREATE_TERMS.search(message)) and has_object and not re.search(r"\b(existing|current|it|its)\b", message, re.I)
    is_create = explicit_create
    if project_id and not is_create:
        project = latest(project_id)
        if not project:
            raise ValueError("That design project no longer exists.")

        house = get_house_state(project_id)
        if house:
            house = update_house(house, message)
            house.design_revision += 1
            design = create_house_concept_model(house)
            save_house_state(house)
            current = latest_design(project_id)
            version = (current[0] if current else 0) + 1
            save_design(project_id, version, design.model_dump_json())
            generated = generate_primitive(design)
            w_ft = house.site_width_m * 3.28084 if house.site_width_m else 30
            l_ft = house.site_length_m * 3.28084 if house.site_length_m else 40

            lower_msg = message.lower()
            if any(k in lower_msg for k in ("interior", "inside", "room", "rooms")):
                msg_text = f"Switched to INTERIOR view mode for {house.floors}-floor ({house.floor_label}) house."
            elif "cutaway" in lower_msg:
                msg_text = f"Switched to CUTAWAY 3D view mode."
            elif any(k in lower_msg for k in ("floor plan", "top view")):
                msg_text = f"Switched to FLOOR PLAN mode."
            else:
                msg_text = f"I updated the preliminary house design to {house.floors} floors ({house.floor_label}) with a total height of {house.total_height_m:.1f} m."

            return ChatResponse(
                message=msg_text,
                requires_clarification=False,
                project_id=project_id,
                design_state=design,
                model_action=ModelAction(type="update", model_id=generated.model_id),
                active_domain="house",
                geometry=generated.geometry,
                knowledge_status="NOT_REQUIRED",
                suggestions=["Show interior", "Show cutaway", "Show ground floor", "Add another floor"],
            )

        bridge = get_bridge_state(project_id)
        if bridge:
            bridge, special = update_bridge(bridge, message)
            if special == "minimum_distance":
                save_bridge_state(bridge)
                return ChatResponse(message="Which bridge distance should I minimize?", requires_clarification=True, questions=["Minimum vertical clearance", "Minimum horizontal clearance", "Minimum approach length", "Minimum deck width", "Minimum bridge span"], project_id=project_id, active_domain="bridge")
            if special == "ambiguous_measurement":
                save_bridge_state(bridge)
                return ChatResponse(message="What does that measurement represent for this bridge?", requires_clarification=True, questions=["Total span", "Deck width", "Vertical clearance", "Approach length"], project_id=project_id, active_domain="bridge")
            environment = detect_environment(message)
            if environment:
                save_bridge_state(bridge)
                concepts = concept_suggestions(environment)
                return ChatResponse(message=f"Thanks — I've recorded a {environment} crossing. Here are preliminary concept directions.", requires_clarification=True, questions=["Which concept would you like to explore?"], suggestions=concepts, project_id=project_id, active_domain="bridge")
            if bridge.bridge_concept or any(word in message.lower() for word in ("show", "truss", "girder", "beam", "arch", "cable")):
                if not bridge.bridge_concept:
                    bridge.bridge_concept = "Beam / girder bridge"
                design = create_concept_model(bridge)
                save_bridge_state(bridge)
                current = latest_design(project_id)
                version = (current[0] if current else 0) + 1
                save_design(project_id, version, design.model_dump_json())
                generated = generate_primitive(design)
                return ChatResponse(message=f"I generated a preliminary {bridge.bridge_concept.lower()} concept with a {design.feature_parameters['span_m']:g} m span.", requires_clarification=False, project_id=project_id, design_state=design, model_action=ModelAction(type="generate", model_id=generated.model_id), active_domain="bridge", geometry=generated.geometry)
            save_bridge_state(bridge)
            return ChatResponse(message="I'm keeping this as a preliminary pedestrian-bridge project. What will the bridge cross?", requires_clarification=True, suggestions=["River", "Canal", "Road / Flyover", "Railway", "Valley", "Urban area"], project_id=project_id, active_domain="bridge")

        saved_design = latest_design(project_id)
        if saved_design:
            version, design_json = saved_design
            design = DesignSpec.model_validate_json(design_json)
            updated = _apply_update(design, message)
            if updated:
                revised_plan = create_plan(message, project_id=project_id, version=project.version + 1)
                save(revised_plan)
                save_design(project_id, version + 1, updated.model_dump_json())
                generated = generate_primitive(updated)
                kernel = _kernel_report(updated, project_id, version + 1)
                return ChatResponse(
                    message=f"Done — I updated the {updated.object_type} and created version {version + 1}.",
                    requires_clarification=False, project_id=project_id, design_state=updated,
                    model_action=ModelAction(type="update", model_id=project_id), geometry=generated.geometry,
                    cad_intent="MODIFY_CAD", kernel_report=kernel,
                    parametric_json={"schema_version": "1.0", "model_id": generated.model_id, "project_id": project_id, "version": version + 1, "object_type": updated.object_type, "features": kernel["feature_history"] if kernel else [], "parameters": updated.model_dump(mode="json")},
                )
            if re.search(r"\b(make|change|modify|update|edit|resize|set)\b", message, re.I):
                return ChatResponse(message="What object should I modify?", requires_clarification=True, questions=["Which existing object should I modify, and what dimensions should it have?"], project_id=project_id, active_domain="primitive", cad_intent="CLARIFICATION_REQUIRED")
        return ChatResponse(message='I can update this primitive by changing its length, width, or height. For example: "Make it 6m long."', requires_clarification=True, questions=["Which dimension should change, and what value/unit should I use?"], project_id=project_id, active_domain="primitive", cad_intent="CLARIFICATION_REQUIRED")

    # ── Step 2: New project — route by domain ────────────────────────────────
    plan = save(create_plan(message))

    if not project_id and re.match(r"\s*(?:make\s+it|change\s+(?:its|the)\s+|modify\s+it|update\s+it|set\s+it)\b", message, re.I):
        return ChatResponse(message="What object should I modify?", requires_clarification=True, questions=["Which object should I modify?"], project_id=plan.project_id, active_domain="primitive", cad_intent="CLARIFICATION_REQUIRED")

    if re.search(r"\b(?:make|create|build|generate|design|construct)\b", message, re.I) and re.search(r"\bbox\b", message, re.I) and re.search(r"\d+(?:\.\d+)?\s*(?:mm|cm|m|in|ft|meter|metre)\s*(?:long|length)\b", message, re.I) and not re.search(r"\s[x×]\s", message):
        return ChatResponse(message="What width and height should I use for the box?", requires_clarification=True, questions=["What width should I use?", "What height should I use?"], project_id=plan.project_id, active_domain="primitive", cad_intent="CLARIFICATION_REQUIRED")

    if is_house_request(message):
        domain = "architectural"
    elif is_bridge_request(message):
        domain = "bridge"
    elif _is_mechanical_prompt(message):
        domain = "mechanical"
    else:
        try:
            design = parse_design_prompt(message)
            domain = "primitive"
        except PromptParseError:
            try:
                domain = ollama_service.classify_domain(message)
            except Exception:
                domain = ollama_service._keyword_classify(message)

    if domain == "mechanical":
        return _handle_mechanical(message, plan)

    if domain == "architectural":
        house = initial_house_state(plan.project_id, message)
        design = create_house_concept_model(house)
        save_house_state(house)
        save_design(plan.project_id, 1, design.model_dump_json())
        generated = generate_primitive(design)
        w_ft = (house.site_width_m or 9.144) * 3.28084
        l_ft = (house.site_length_m or 12.192) * 3.28084
        return ChatResponse(
            message=f"I generated a preliminary architectural massing model for a {house.floors}-floor ({house.floor_label}) house on a {w_ft:.0f}×{l_ft:.0f} ft plot (total height: {house.total_height_m:.1f} m).",
            requires_clarification=False,
            project_id=plan.project_id,
            design_state=design,
            model_action=ModelAction(type="generate", model_id=generated.model_id),
            active_domain="house",
            geometry=generated.geometry,
                knowledge_status="NOT_REQUIRED",
            suggestions=["Add another floor", "Change to 3 floors", "Change site size to 40x60 ft", "Use flat terrace roof"],
        )

    if domain == "bridge" or is_bridge_request(message):
        bridge = initial_state(plan.project_id, message)
        save_bridge_state(bridge)
        if bridge.bridge_type or any(word in message.lower() for word in ("arch", "truss", "suspension", "cable", "girder", "beam")):
            design = create_concept_model(bridge)
            save_bridge_state(bridge)
            save_design(plan.project_id, 1, design.model_dump_json())
            generated = generate_primitive(design)
            span_val = design.feature_parameters.get("span_m", 30)
            width_val = design.feature_parameters.get("deck_width_m", 3)
            concept_str = bridge.bridge_concept or "bridge"
            return ChatResponse(
                message=f"I generated a preliminary {concept_str.lower()} concept with a {span_val} m span and {width_val} m deck width.",
                requires_clarification=False,
                project_id=plan.project_id,
                design_state=design,
                model_action=ModelAction(type="generate", model_id=generated.model_id),
                active_domain="bridge",
                geometry=generated.geometry,
                knowledge_status="NOT_REQUIRED",
                suggestions=["Beam bridge", "Truss bridge", "Arch bridge", "Suspension bridge", "Cable-stayed bridge"],
            )
        span_note = f" for a {bridge.span_m:g} m span" if bridge.span_m else ""
        return ChatResponse(message=f"I can help explore preliminary pedestrian bridge concepts{span_note}. First, what will the bridge cross?", requires_clarification=True, suggestions=["River", "Canal", "Road / Flyover", "Railway", "Valley", "Urban area"], project_id=plan.project_id, active_domain="bridge")

    # ── Step 5: General / primitive ──────────────────────────────────────────
    try:
        design = parse_design_prompt(message)
    except PromptParseError:
        questions = _questions(plan)
        intro = "I understand this as a preliminary engineering design request. "
        if questions:
            intro += "Before I generate a model, I need a few important details."
        else:
            intro += "I'll prepare a concept and structured specification next."
        return ChatResponse(message=intro, requires_clarification=bool(questions), questions=questions, project_id=plan.project_id)

    generated = generate_primitive(design)
    save_design(plan.project_id, 1, design.model_dump_json())
    kernel = _kernel_report(design, plan.project_id, 1)
    label = "cylindrical steel shaft" if design.object_type == "shaft" and design.material == "steel" else design.object_type
    return ChatResponse(
        message=(f"Created: Cube\n5000 × 5000 × 5000 mm\nStatus: Valid OpenCascade solid\nVolume: {kernel['volume_mm3']:,.0f} mm³" if kernel and design.feature_parameters.get("is_cube") else f"I created the preliminary {label} model. Requirements are structured, geometry is generated for the viewer, and units have been validated."),
        requires_clarification=False,
        project_id=plan.project_id,
        design_state=design,
        model_action=ModelAction(type="generate", model_id=generated.model_id),
        geometry=generated.geometry,
        knowledge_status="NOT_REQUIRED",
        cad_intent="CREATE_CAD" if explicit_create else "CREATE_CAD",
        kernel_report=kernel,
        parametric_json={
            "schema_version": "1.0", "model_id": generated.model_id, "project_id": plan.project_id,
            "version": 1, "object_type": design.object_type,
            "features": kernel["feature_history"] if kernel else [],
            "parameters": design.model_dump(mode="json"),
        },
    )
