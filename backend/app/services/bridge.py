"""Context-aware preliminary bridge workflow; not structural design software."""

import re

from app.models import BridgeProjectState, BridgeType, DesignSpec, Dimensions, Unit

_WIDTH = re.compile(r"(?:(?:deck|bridge)\s+)?(?:width|wide)\s*(?:to\s+)?(\d+(?:\.\d+)?)\s*(m|metres?|meters?|ft)\b|(?:deck|bridge)\s+(\d+(?:\.\d+)?)\s*(m|metres?|meters?|ft)\s+wide\b", re.I)
_ARCH_HEIGHT = re.compile(r"(?:arch\s+height|arch\s+rise)\s*(?:of\s+)?(\d+(?:\.\d+)?)\s*(m|metres?|meters?|ft)\b", re.I)
_TOWER_HEIGHT = re.compile(r"(?:tower\s+height|pylon\s+height)\s*(?:of\s+)?(\d+(?:\.\d+)?)\s*(m|metres?|meters?|ft)\b", re.I)
_TRUSS_HEIGHT = re.compile(r"(?:truss\s+height|truss\s+depth)\s*(?:of\s+)?(\d+(?:\.\d+)?)\s*(m|metres?|meters?|ft)\b", re.I)
_ENVIRONMENTS = {"river", "canal", "road", "flyover", "railway", "valley", "urban"}

_TYPE_DISPLAY = {
    BridgeType.BEAM_GIRDER: "Beam / Girder Bridge",
    BridgeType.TRUSS: "Truss Bridge",
    BridgeType.ARCH: "Arch Bridge",
    BridgeType.SUSPENSION: "Suspension Bridge",
    BridgeType.CABLE_STAYED: "Cable-Stayed Bridge",
}


def is_bridge_request(message: str) -> bool:
    return any(term in message.lower() for term in ("bridge", "overpass", "flyover"))


def normalize_bridge_type(text: str) -> BridgeType | None:
    lower = text.lower()
    if "cable-stayed" in lower or "cable stayed" in lower:
        return BridgeType.CABLE_STAYED
    if "suspension" in lower:
        return BridgeType.SUSPENSION
    if "arch" in lower:
        return BridgeType.ARCH
    if "truss" in lower:
        return BridgeType.TRUSS
    if "beam" in lower or "girder" in lower:
        return BridgeType.BEAM_GIRDER
    if "cable" in lower:
        return BridgeType.CABLE_STAYED
    return None


def initial_state(project_id: str, message: str) -> BridgeProjectState:
    span_m = _extract_span(message)
    width_m = _extract_width(message)
    b_type = normalize_bridge_type(message)
    concept = _TYPE_DISPLAY[b_type] if b_type else None

    state = BridgeProjectState(
        project_id=project_id,
        span_m=span_m,
        deck_width_m=width_m,
        bridge_type=b_type,
        bridge_concept=concept,
        crossing_environment=detect_environment(message),
    )
    _extract_heights(state, message)
    return state


_SPAN = re.compile(r"(?:span(?:ning)?(?:\s+(?:a|of))?|length(?:\s+(?:of))?)\s*(\d+(?:\.\d+)?)\s*(m|metres?|meters?|ft)\b|\b(\d+(?:\.\d+)?)\s*(m|metres?|meters?|ft)\s*(?:span|long|length|bridge)\b", re.I)


def _meters(value: float, unit: str) -> float:
    return value * 0.3048 if unit.lower() == "ft" else value


def _extract_span(message: str) -> float | None:
    m = _SPAN.search(message)
    if m:
        val = m.group(1) or m.group(3)
        unit = m.group(2) or m.group(4)
        if val and unit:
            return _meters(float(val), unit)
    # Fallback for "across 150m river" or "80m arch bridge"
    fallback = re.search(r"\b(\d+(?:\.\d+)?)\s*(m|metres?|meters?|ft)\b(?=.*(?:bridge|river|road|crossing|canal|valley))", message, re.I)
    if fallback:
        return _meters(float(fallback.group(1)), fallback.group(2))
    return None


def _extract_width(message: str) -> float | None:
    width = _WIDTH.search(message)
    if width:
        value, unit = (width.group(1), width.group(2)) if width.group(1) else (width.group(3), width.group(4))
        return _meters(float(value), unit)
    return None


def _extract_heights(state: BridgeProjectState, message: str) -> None:
    arch_m = _ARCH_HEIGHT.search(message)
    if arch_m:
        state.arch_height_m = _meters(float(arch_m.group(1)), arch_m.group(2))

    tower_m = _TOWER_HEIGHT.search(message)
    if tower_m:
        state.tower_height_m = _meters(float(tower_m.group(1)), tower_m.group(2))

    truss_m = _TRUSS_HEIGHT.search(message)
    if truss_m:
        state.truss_height_m = _meters(float(truss_m.group(1)), truss_m.group(2))


def detect_environment(message: str) -> str | None:
    lower = message.lower()
    return next((environment for environment in _ENVIRONMENTS if environment in lower), None)


def detect_concept(message: str) -> str | None:
    b_type = normalize_bridge_type(message)
    if b_type:
        return _TYPE_DISPLAY[b_type]
    return None


def update_bridge(state: BridgeProjectState, message: str) -> tuple[BridgeProjectState, str | None]:
    environment = detect_environment(message)
    if environment:
        state.crossing_environment = environment

    b_type = normalize_bridge_type(message)
    if b_type:
        state.bridge_type = b_type
        state.bridge_concept = _TYPE_DISPLAY[b_type]

    width_m = _extract_width(message)
    if width_m:
        state.deck_width_m = width_m

    span_m = _extract_span(message)
    if span_m:
        state.span_m = span_m

    _extract_heights(state, message)

    if "minimum distance" in message.lower():
        return state, "minimum_distance"
    if re.fullmatch(r"\s*\d+(?:\.\d+)?\s*(?:m|metres?|meters?|ft)\s*bridge\s*", message, re.I):
        return state, "ambiguous_measurement"
    return state, None


def concept_suggestions(environment: str | None) -> list[str]:
    mapping = {
        "river": ["Beam / Girder Bridge", "Truss Bridge", "Arch Bridge", "Cable-Stayed Bridge", "Suspension Bridge"],
        "canal": ["Beam / Girder Bridge", "Truss Bridge", "Arch Bridge"],
        "road": ["Beam / Girder Bridge", "Truss Bridge", "Cable-Stayed Bridge"],
        "flyover": ["Beam / Girder Bridge", "Truss Bridge"],
        "railway": ["Truss Bridge", "Beam / Girder Bridge"],
        "valley": ["Arch Bridge", "Suspension Bridge", "Cable-Stayed Bridge", "Truss Bridge"],
    }
    return mapping.get(environment or "", ["Beam / Girder Bridge", "Truss Bridge", "Arch Bridge", "Suspension Bridge", "Cable-Stayed Bridge"])


def create_concept_model(state: BridgeProjectState) -> DesignSpec:
    span = state.span_m or 30.0
    width = state.deck_width_m or 3.0
    support_h = state.support_height_m or 5.0

    b_type = state.bridge_type or normalize_bridge_type(state.bridge_concept or "") or BridgeType.BEAM_GIRDER
    state.bridge_type = b_type
    state.bridge_concept = _TYPE_DISPLAY[b_type]

    arch_h = state.arch_height_m if state.arch_height_m is not None else max(4.0, span * 0.16)
    tower_h = state.tower_height_m if state.tower_height_m is not None else max(8.0, span * 0.24)
    truss_h = state.truss_height_m if state.truss_height_m is not None else max(3.0, span * 0.10)
    sag = state.cable_sag_m if state.cable_sag_m is not None else tower_h * 0.65
    panels = state.number_of_panels if state.number_of_panels is not None else max(6, min(16, int(span / 5)))

    state.arch_height_m = arch_h
    state.tower_height_m = tower_h
    state.truss_height_m = truss_h
    state.cable_sag_m = sag
    state.number_of_panels = panels

    state.assumptions = []
    if state.span_m is None:
        state.assumptions.append("Preliminary 30 m span assumed.")
    if state.deck_width_m is None:
        state.assumptions.append("Preliminary 3 m deck width assumed.")
    state.status = "concept_generated"

    height_metric = support_h
    if b_type == BridgeType.ARCH:
        height_metric = support_h + arch_h
    elif b_type in (BridgeType.SUSPENSION, BridgeType.CABLE_STAYED):
        height_metric = support_h + tower_h
    elif b_type == BridgeType.TRUSS:
        height_metric = support_h + truss_h

    features: dict[str, float | str] = {
        "bridge_type": b_type.value,
        "span_m": span,
        "deck_width_m": width,
        "support_height_m": support_h,
        "arch_height_m": arch_h,
        "tower_height_m": tower_h,
        "truss_height_m": truss_h,
        "cable_sag_m": sag,
        "number_of_panels": panels,
        "material": state.material or "steel",
    }

    warnings = [
        "Preliminary Concept — Not Structurally Validated. Site survey, hydraulic/wind load analysis, and code compliance required."
    ]

    return DesignSpec(
        object_type="bridge",
        dimensions=Dimensions(length=span, width=width, height=height_metric),
        unit=Unit.METER,
        dimensions_mm=Dimensions(length=span * 1000, width=width * 1000, height=height_metric * 1000),
        material=state.material or "steel",
        feature_parameters=features,
        source_prompt=f"{b_type.value} bridge concept",
        warnings=warnings,
    )

