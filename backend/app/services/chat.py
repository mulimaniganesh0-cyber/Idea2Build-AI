"""Chat-facing adapter that keeps the engineering pipeline behind a simple UX."""

import re

from app.models import ChatResponse, DesignSpec, Dimensions, ModelAction, ProjectPlan, Unit
from app.services.bridge import concept_suggestions, create_concept_model, detect_environment, initial_state, is_bridge_request, update_bridge
from app.services.house import create_house_concept_model, initial_house_state, is_house_request, update_house
from app.services.orchestrator import create_plan
from app.services.cad import generate_primitive
from app.services.parser import PromptParseError, parse_design_prompt
from app.services.project_store import get_bridge_state, get_house_state, latest, latest_design, save, save_bridge_state, save_design, save_house_state

_TO_MM = {Unit.MILLIMETER: 1, Unit.CENTIMETER: 10, Unit.METER: 1000, Unit.INCH: 25.4, Unit.FOOT: 304.8}
_UNIT_ALIASES = {"mm": Unit.MILLIMETER, "cm": Unit.CENTIMETER, "m": Unit.METER, "in": Unit.INCH, "ft": Unit.FOOT, "meter": Unit.METER, "metre": Unit.METER, "feet": Unit.FOOT, "foot": Unit.FOOT, "inch": Unit.INCH}
_UPDATE = re.compile(r"(?:make|change|set|increase)\s+(?:it|the)?\s*(?:to\s+)?(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mm|cm|m|in|ft|meter|metre|feet|foot|inch)\s*(?P<field>long|length|wide|width|high|height)", re.I)
_CREATE_TERMS = re.compile(r"\b(create|design|generate|build)\b", re.I)


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
    if design.object_type == "shaft":
        features["length"] = mm.length
        features["diameter"] = mm.width
    return design.model_copy(update={"dimensions": source, "dimensions_mm": mm, "feature_parameters": features, "source_prompt": message})


def handle_message(message: str, project_id: str | None) -> ChatResponse:
    is_create = bool(_CREATE_TERMS.search(message)) and any(kind in message.lower() for kind in ("cube", "box", "cylinder", "sphere", "cone", "shaft", "plate", "hole", "house", "bridge"))
    if project_id and not is_create:
        project = latest(project_id)
        if not project:
            raise ValueError("That design project no longer exists.")
        
        # Check house state
        house = get_house_state(project_id)
        if house:
            house = update_house(house, message)
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
                msg_text = f"Switched to INTERIOR view mode for {house.floors}-floor ({house.floor_label}) house. Interior partitions, living room sofa, dining table, kitchen counter, bedrooms, and bathrooms are visible."
            elif "cutaway" in lower_msg:
                msg_text = f"Switched to CUTAWAY 3D view mode. Exterior front envelope is clipped to inspect all {house.floors} furnished levels simultaneously."
            elif any(k in lower_msg for k in ("floor plan", "top view")):
                msg_text = f"Switched to FLOOR PLAN mode. Displaying 2D/3D layout {f'for Level {house.active_floor}' if house.active_floor is not None else 'from overhead'}."
            elif any(k in lower_msg for k in ("ground floor", "first floor", "second floor", "floor 0", "floor 1", "floor 2")):
                msg_text = f"Filtered view to Floor {house.active_floor} in {house.floors}-floor ({house.floor_label}) house."
            elif any(k in lower_msg for k in ("sofa", "bed", "table", "chair", "wardrobe", "furniture")):
                msg_text = f"Added custom furniture to the house model. Interior view mode activated."
            else:
                msg_text = f"I updated the preliminary house design to {house.floors} floors ({house.floor_label}) with {house.floors} physical levels and a total height of {house.total_height_m:.1f} m for a {w_ft:.0f}×{l_ft:.0f} ft site."

            return ChatResponse(
                message=msg_text,
                requires_clarification=False,
                project_id=project_id,
                design_state=design,
                model_action=ModelAction(type="update", model_id=generated.model_id),
                active_domain="house",
                geometry=generated.geometry,
                suggestions=["Show interior", "Show cutaway", "Show ground floor", "Add another floor", "Add a sofa to the living room"],
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
                return ChatResponse(message=f"Thanks — I’ve recorded a {environment} crossing. Here are preliminary concept directions to explore; final selection requires site, loading, clearance, constructability, and code review.", requires_clarification=True, questions=["Which concept would you like to explore?"], suggestions=concepts, project_id=project_id, active_domain="bridge")
            if bridge.bridge_concept or any(word in message.lower() for word in ("show", "truss", "girder", "beam", "arch", "cable")):
                if not bridge.bridge_concept:
                    bridge.bridge_concept = "Beam / girder bridge"
                design = create_concept_model(bridge)
                save_bridge_state(bridge)
                current = latest_design(project_id)
                version = (current[0] if current else 0) + 1
                save_design(project_id, version, design.model_dump_json())
                generated = generate_primitive(design)
                return ChatResponse(message=f"I generated a preliminary {bridge.bridge_concept.lower()} concept with a {design.feature_parameters['span_m']:g} m span and {design.feature_parameters['deck_width_m']:g} m deck width. It is conceptual only and requires professional engineering review.", requires_clarification=False, project_id=project_id, design_state=design, model_action=ModelAction(type="generate", model_id=generated.model_id), active_domain="bridge", geometry=generated.geometry)
            save_bridge_state(bridge)
            return ChatResponse(message="I’m keeping this as a preliminary pedestrian-bridge project. What will the bridge cross?", requires_clarification=True, suggestions=["River", "Canal", "Road / Flyover", "Railway", "Valley", "Urban area"], project_id=project_id, active_domain="bridge")
        saved_design = latest_design(project_id)
        if saved_design:
            version, design_json = saved_design
            design = DesignSpec.model_validate_json(design_json)
            updated = _apply_update(design, message)
            if updated:
                revised_plan = create_plan(message, project_id=project_id, version=project.version + 1)
                save(revised_plan)
                save_design(project_id, version + 1, updated.model_dump_json())
                return ChatResponse(message=f"Done — I updated the {updated.object_type} and created version {version + 1}.", requires_clarification=False, project_id=project_id, design_state=updated, model_action=ModelAction(type="update", model_id=project_id))
        return ChatResponse(message="I can update this primitive by changing its length, width, or height. For example: “Make it 6m long.”", requires_clarification=True, questions=["Which dimension should change, and what value/unit should I use?"], project_id=project_id, active_domain="primitive")

    plan = save(create_plan(message))
    if is_house_request(message):
        house = initial_house_state(plan.project_id, message)
        design = create_house_concept_model(house)
        save_house_state(house)
        save_design(plan.project_id, 1, design.model_dump_json())
        generated = generate_primitive(design)
        w_ft = (house.site_width_m or 9.144) * 3.28084
        l_ft = (house.site_length_m or 12.192) * 3.28084
        return ChatResponse(
            message=f"I generated a preliminary architectural massing model for a {house.floors}-floor ({house.floor_label}) house on a {w_ft:.0f}×{l_ft:.0f} ft plot (total height: {house.total_height_m:.1f} m). The model includes {house.floors} floor slabs, corner columns, wall envelopes, windows, entrance door, and roof structure.",
            requires_clarification=False,
            project_id=plan.project_id,
            design_state=design,
            model_action=ModelAction(type="generate", model_id=generated.model_id),
            active_domain="house",
            geometry=generated.geometry,
            suggestions=["Add another floor", "Change to 3 floors", "Change site size to 40x60 ft", "Use flat terrace roof"],
        )

    if is_bridge_request(message):
        bridge = initial_state(plan.project_id, message)
        save_bridge_state(bridge)
        if bridge.bridge_type or any(word in message.lower() for word in ("arch", "truss", "suspension", "cable", "girder", "beam")):
            design = create_concept_model(bridge)
            save_bridge_state(bridge)
            save_design(plan.project_id, 1, design.model_dump_json())
            generated = generate_primitive(design)
            span_val = design.feature_parameters.get('span_m', 30)
            width_val = design.feature_parameters.get('deck_width_m', 3)
            concept_str = bridge.bridge_concept or "bridge"
            return ChatResponse(
                message=f"I generated a preliminary {concept_str.lower()} concept with a {span_val} m span and {width_val} m deck width. It is conceptual only and requires professional engineering review.",
                requires_clarification=False,
                project_id=plan.project_id,
                design_state=design,
                model_action=ModelAction(type="generate", model_id=generated.model_id),
                active_domain="bridge",
                geometry=generated.geometry,
                suggestions=["Beam bridge", "Truss bridge", "Arch bridge", "Suspension bridge", "Cable-stayed bridge"],
            )
        span_note = f" for a {bridge.span_m:g} m span" if bridge.span_m else ""
        return ChatResponse(message=f"I can help explore preliminary pedestrian bridge concepts{span_note}. First, what will the bridge cross?", requires_clarification=True, suggestions=["River", "Canal", "Road / Flyover", "Railway", "Valley", "Urban area"], project_id=plan.project_id, active_domain="bridge")
    try:
        design = parse_design_prompt(message)
    except PromptParseError:
        questions = _questions(plan)
        intro = "I understand this as a preliminary engineering design request. "
        if questions:
            intro += "Before I generate a model, I need a few important details."
        else:
            intro += "I’ll prepare a concept and structured specification next."
        return ChatResponse(message=intro, requires_clarification=bool(questions), questions=questions, project_id=plan.project_id)

    generated = generate_primitive(design)
    save_design(plan.project_id, 1, design.model_dump_json())
    label = "cylindrical steel shaft" if design.object_type == "shaft" and design.material == "steel" else design.object_type
    return ChatResponse(message=f"I created the preliminary {label} model. Requirements are structured, geometry is generated for the viewer, and units have been validated. You can rotate it or request a change such as “Make it 6m long.”", requires_clarification=False, project_id=plan.project_id, design_state=design, model_action=ModelAction(type="generate", model_id=generated.model_id), geometry=generated.geometry)

