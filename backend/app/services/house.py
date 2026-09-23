"""Context-aware residential house, building, and interior workflow."""

import re

from app.models import DesignSpec, Dimensions, HouseProjectState, Unit

_SITE_PATTERN = re.compile(
    r"(?P<w>\d+(?:\.\d+)?)\s*(?:\*|x|×|by)\s*(?P<l>\d+(?:\.\d+)?)\s*(?P<unit>ft|feet|foot|m|meters?|metres?|cm|mm)?\b",
    re.I,
)

_WORD_TO_INT = {
    "zero": 0,
    "one": 1,
    "single": 1,
    "two": 2,
    "double": 2,
    "three": 3,
    "triple": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

_FT_TO_M = 0.3048


def is_house_request(message: str) -> bool:
    lower = message.lower()
    return any(
        term in lower
        for term in (
            "house",
            "villa",
            "home",
            "residential",
            "duplex",
            "apartment",
            "cottage",
            "bungalow",
            "building",
            "interior",
            "furniture",
            "living room",
            "bedroom",
            "kitchen",
            "bathroom",
            "sofa",
            "dining table",
            "cutaway",
            "g+1",
            "g+2",
            "g+3",
            "g+4",
            "g+5",
        )
    ) or (
        ("site" in lower or "plot" in lower or "land" in lower)
        and any(w in lower for w in ("story", "storey", "floor", "floors", "level", "levels", "x", "*", "by", "ft", "m"))
    ) or (
        any(w in lower for w in ("floor", "floors", "storey", "storeys", "story", "stories"))
        and any(action in lower for action in ("make", "add", "change", "set", "build", "create", "design", "show"))
    )


def extract_site_dimensions(message: str) -> tuple[float | None, float | None, str]:
    """Returns (width_m, length_m, unit_str)."""
    match = _SITE_PATTERN.search(message)
    if not match:
        return None, None, "ft"

    w_val = float(match.group("w"))
    l_val = float(match.group("l"))
    raw_unit = (match.group("unit") or "ft").lower()

    if raw_unit in ("ft", "feet", "foot"):
        return w_val * _FT_TO_M, l_val * _FT_TO_M, "ft"
    elif raw_unit in ("m", "meter", "meters", "metre", "metres"):
        return w_val, l_val, "m"
    elif raw_unit == "cm":
        return w_val / 100, l_val / 100, "cm"
    elif raw_unit == "mm":
        return w_val / 1000, l_val / 1000, "mm"

    # Default unit assumption is ft if not specified but values are typical plot size like 30x40
    if max(w_val, l_val) > 15:
        return w_val * _FT_TO_M, l_val * _FT_TO_M, "ft"
    return w_val, l_val, "m"


def parse_floor_expression(message: str, current_floors: int | None = None) -> tuple[int | None, bool, int, str]:
    """
    Parses floor expression from user text.
    Returns: (total_floor_count, ground_floor_included, upper_floor_count, floor_label)
    
    Standard definition:
    - '3 floors' -> 3 physical levels (Ground + 2 upper = G+2)
    - 'G+2' -> 3 physical levels (Ground + 2 upper = G+2)
    - 'Add another floor' -> (current_floors or 2) + 1
    """
    lower = message.lower()

    # If it is purely a view mode request like "show ground floor" without "make" or "add", don't change total floor count
    if "show " in lower and not any(action in lower for action in ("make", "add", "change", "set", "build", "create")):
        return None, True, 0, "Unknown"

    # 1. Check incremental addition phrases:
    # "add another floor", "add one more floor", "add a floor", "add 1 floor", "add 2 floors"
    add_match = re.search(r"\b(?:add|increase\s+by)\s+(?:another|one\s+more|a|an|(?P<delta>\d+|one|two|three))\s*(?:more\s+)?(?:floor|floors|storey|storeys|story|stories|level|levels)\b", lower)
    if add_match:
        delta_str = add_match.group("delta")
        if delta_str:
            delta = _WORD_TO_INT.get(delta_str, int(delta_str) if delta_str.isdigit() else 1)
        else:
            delta = 1
        base = current_floors if current_floors and current_floors > 0 else 2
        total = max(1, min(50, base + delta))
        upper = max(0, total - 1)
        label = "Ground Floor" if total == 1 else f"G+{upper}"
        return total, True, upper, label

    # 2. Check transition phrasing: "change (from X floors) to Y floors"
    change_to = re.search(r"\b(?:to|into)\s+(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:floors|floor|storeys|storey|stories|story|levels|level)\b", lower)
    if change_to:
        c_str = change_to.group("count")
        total = _WORD_TO_INT.get(c_str, int(c_str) if c_str.isdigit() else 2)
        total = max(1, min(50, total))
        upper = max(0, total - 1)
        label = "Ground Floor" if total == 1 else f"G+{upper}"
        return total, True, upper, label

    # 3. Check G+ notation: "G+1", "G+2", "G+3", "ground + 2", "ground plus 2"
    g_match = re.search(r"\b(?:g|ground)\s*(?:\+|\bplus\b)\s*(?P<upper>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b", lower)
    if g_match:
        u_str = g_match.group("upper")
        upper = _WORD_TO_INT.get(u_str, int(u_str) if u_str.isdigit() else 1)
        total = 1 + upper
        label = f"G+{upper}"
        return total, True, upper, label

    # "ground floor and 2 upper floors" / "ground floor + 2 upper floors"
    ground_upper = re.search(r"\bground\s+floor\s*(?:and|\+)\s*(?P<upper>\d+|one|two|three|four|five)\s*upper\s+floors?\b", lower)
    if ground_upper:
        u_str = ground_upper.group("upper")
        upper = _WORD_TO_INT.get(u_str, int(u_str) if u_str.isdigit() else 1)
        total = 1 + upper
        label = f"G+{upper}"
        return total, True, upper, label

    # 4. Check explicit floor count expressions:
    # "3 floors", "3-story", "3 storeys", "three floors", "make the building 3 floors"
    floor_match = re.search(
        r"\b(?P<count>\d+)\s*(?:story|storey|stories|storeys|floor|floors|level|levels)\b|"
        r"\b(?P<word>one|two|three|four|five|six|seven|eight|nine|ten|single|double|triple)\s*[- ]*(?:story|storey|stories|storeys|floor|floors|level|levels)\b",
        lower,
    )
    if floor_match:
        if floor_match.group("count"):
            total = int(floor_match.group("count"))
        else:
            total = _WORD_TO_INT.get(floor_match.group("word"), 2)
        total = max(1, min(50, total))
        upper = max(0, total - 1)
        label = "Ground Floor" if total == 1 else f"G+{upper}"
        return total, True, upper, label

    # 5. "ground floor only" / "single floor"
    if "ground floor only" in lower or "single floor" in lower or "single storey" in lower:
        return 1, True, 0, "Ground Floor"

    return None, True, 0, "Unknown"


def extract_floor_count(message: str, current_floors: int | None = None) -> int | None:
    """Returns the total number of physical floor levels."""
    total, _, _, _ = parse_floor_expression(message, current_floors)
    return total


def detect_view_mode_intent(message: str) -> tuple[str | None, int | None]:
    """Detects view mode and active floor filter from natural language request."""
    lower = message.lower()

    active_floor: int | None = None
    if "ground floor" in lower or "floor 0" in lower or "level 0" in lower:
        active_floor = 0
    elif "first floor" in lower or "1st floor" in lower or "floor 1" in lower or "level 1" in lower:
        active_floor = 1
    elif "second floor" in lower or "2nd floor" in lower or "floor 2" in lower or "level 2" in lower:
        active_floor = 2
    elif "all floors" in lower or "full building" in lower:
        active_floor = None

    if "cutaway" in lower or "cross section" in lower or "section" in lower:
        return "cutaway", active_floor
    if "floor plan" in lower or "top view" in lower or "plan view" in lower:
        return "floor_plan", active_floor
    if "interior" in lower or "inside" in lower or "rooms" in lower or "furniture" in lower:
        return "interior", active_floor
    if "exterior" in lower or "outside" in lower or "facade" in lower:
        return "exterior", active_floor
    if active_floor is not None:
        return "interior", active_floor

    return None, None


def detect_furniture_command(message: str) -> dict | None:
    """Detects request to add custom furniture objects."""
    lower = message.lower()
    if not any(k in lower for k in ("add", "place", "insert", "put")):
        return None

    if "sofa" in lower or "couch" in lower:
        room = "living_room" if "living" in lower else "living_room"
        return {"type": "furniture_sofa", "room_id": f"{room}_custom", "name": "custom_sofa", "color": "#1e40af"}
    if "bed" in lower:
        room = "bedroom" if "bed" in lower else "bedroom_master"
        return {"type": "furniture_bed", "room_id": f"{room}_custom", "name": "custom_bed", "color": "#854d0e"}
    if "table" in lower or "desk" in lower:
        room = "dining" if "dining" in lower else "study"
        return {"type": "furniture_table", "room_id": f"{room}_custom", "name": "custom_table", "color": "#78350f"}
    if "chair" in lower:
        return {"type": "furniture_chair", "room_id": "living_custom", "name": "custom_chair", "color": "#334155"}
    if "wardrobe" in lower or "closet" in lower:
        return {"type": "furniture_wardrobe", "room_id": "bedroom_custom", "name": "custom_wardrobe", "color": "#475569"}
    if "tv" in lower:
        return {"type": "furniture_tv_unit", "room_id": "living_custom", "name": "custom_tv_unit", "color": "#0f172a"}
    return None


def initial_house_state(project_id: str, message: str) -> HouseProjectState:
    w_m, l_m, unit = extract_site_dimensions(message)
    total_floors, g_included, upper, label = parse_floor_expression(message)
    floors = total_floors or 2
    upper_count = upper if total_floors else 1
    floor_label = label if total_floors else "G+1"
    floor_h = 3.0
    total_h = (floors * floor_h) + 1.2
    view_mode, active_floor = detect_view_mode_intent(message)

    return HouseProjectState(
        project_id=project_id,
        site_width_m=w_m,
        site_length_m=l_m,
        floors=floors,
        ground_floor_included=g_included,
        upper_floor_count=upper_count,
        floor_label=floor_label,
        floor_height_m=floor_h,
        total_height_m=total_h,
        view_mode=view_mode or "exterior",
        active_floor=active_floor,
        unit=unit,
    )


def update_house(state: HouseProjectState, message: str) -> HouseProjectState:
    w_m, l_m, unit = extract_site_dimensions(message)
    if w_m and l_m:
        state.site_width_m = w_m
        state.site_length_m = l_m
        state.unit = unit

    total_floors, g_included, upper, label = parse_floor_expression(message, current_floors=state.floors)
    if total_floors:
        state.floors = total_floors
        state.ground_floor_included = g_included
        state.upper_floor_count = upper
        state.floor_label = label
        state.total_height_m = (total_floors * state.floor_height_m) + 1.2

    # Check view mode intent
    view_mode, active_floor = detect_view_mode_intent(message)
    if view_mode:
        state.view_mode = view_mode
    if active_floor is not None:
        state.active_floor = active_floor

    # Check custom furniture commands
    furniture = detect_furniture_command(message)
    if furniture:
        state.custom_furniture.append(furniture)
        state.view_mode = "interior"

    if "pitched" in message.lower() or "slope" in message.lower():
        state.roof_type = "pitched"
    elif "flat" in message.lower() or "terrace" in message.lower():
        state.roof_type = "flat"

    return state


def create_house_concept_model(state: HouseProjectState) -> DesignSpec:
    # Set default site dimensions if none provided (30 ft x 40 ft default)
    w_m = state.site_width_m or (30.0 * _FT_TO_M)
    l_m = state.site_length_m or (40.0 * _FT_TO_M)
    floors = max(1, min(50, state.floors or 2))
    floor_height_m = state.floor_height_m or 3.0

    # Building footprint: 75% of site width and 70% of site length with setbacks
    b_width_m = w_m * 0.75
    b_length_m = l_m * 0.70
    total_height_m = (floors * floor_height_m) + 1.2  # plus roof/parapet height
    state.total_height_m = total_height_m

    upper_count = max(0, floors - 1)
    floor_label = "Ground Floor" if floors == 1 else f"G+{upper_count}"
    state.floor_label = floor_label
    state.upper_floor_count = upper_count

    state.assumptions = []
    if state.site_width_m is None or state.site_length_m is None:
        state.assumptions.append("Default 30 × 40 ft site dimensions assumed.")
    state.assumptions.append(f"Building setback applied: footprint {b_width_m / _FT_TO_M:.1f} × {b_length_m / _FT_TO_M:.1f} ft.")
    state.assumptions.append(f"Standard floor height of {floor_height_m:g} m per level ({floors} total levels, {floor_label}).")
    state.status = "concept_generated"

    # Dimensions in mm for DesignSpec contract
    site_w_mm = w_m * 1000
    site_l_mm = l_m * 1000
    total_h_mm = total_height_m * 1000

    unit_enum = Unit.FOOT if state.unit == "ft" else Unit.METER

    return DesignSpec(
        object_type="house",
        dimensions=Dimensions(
            length=site_l_mm / (304.8 if state.unit == "ft" else 1000),
            width=site_w_mm / (304.8 if state.unit == "ft" else 1000),
            height=total_h_mm / (304.8 if state.unit == "ft" else 1000),
        ),
        unit=unit_enum,
        dimensions_mm=Dimensions(length=site_l_mm, width=site_w_mm, height=total_h_mm),
        material=state.material or "concrete_and_masonry",
        feature_parameters={
            "site_width_m": w_m,
            "site_length_m": l_m,
            "building_width_m": b_width_m,
            "building_length_m": b_length_m,
            "floors": float(floors),
            "floor_count": float(floors),
            "upper_floor_count": float(upper_count),
            "floor_label": floor_label,
            "floor_height_m": floor_height_m,
            "total_building_height_m": total_height_m,
            "roof_type": state.roof_type,
            "view_mode": state.view_mode,
            "active_floor": float(state.active_floor) if state.active_floor is not None else -1.0,
            "has_interior": 1.0,
            "custom_furniture_count": float(len(state.custom_furniture)),
            "is_house": 1.0,
        },
        source_prompt=f"House on {w_m / _FT_TO_M:.0f}×{l_m / _FT_TO_M:.0f} ft plot with {floors} floors ({floor_label}), view mode: {state.view_mode}",
        warnings=[
            "Preliminary architectural massing and interior space planning concept.",
            "Local building codes, structural calculations, set-back rules, and site surveys must be verified by a licensed architect/engineer.",
        ],
    )
