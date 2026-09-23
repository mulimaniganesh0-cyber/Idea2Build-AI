"""Constrained Phase 1 parser for box prompts.

Keep this deterministic parser when an LLM is introduced: it provides predictable
tests and a clear contract for structured-output validation.
"""

import re

from app.models import DesignSpec, Dimensions, Unit


class PromptParseError(ValueError):
    """The prompt cannot be represented by the Phase 1 design contract."""


_UNIT_ALIASES = {
    "mm": Unit.MILLIMETER,
    "millimeter": Unit.MILLIMETER,
    "millimeters": Unit.MILLIMETER,
    "cm": Unit.CENTIMETER,
    "centimeter": Unit.CENTIMETER,
    "centimeters": Unit.CENTIMETER,
    "m": Unit.METER,
    "meter": Unit.METER,
    "meters": Unit.METER,
    "metre": Unit.METER,
    "metres": Unit.METER,
    "in": Unit.INCH,
    "inch": Unit.INCH,
    "inches": Unit.INCH,
    "ft": Unit.FOOT,
    "foot": Unit.FOOT,
    "feet": Unit.FOOT,
}
_TO_MM = {
    Unit.MILLIMETER: 1,
    Unit.CENTIMETER: 10,
    Unit.METER: 1000,
    Unit.INCH: 25.4,
    Unit.FOOT: 304.8,
}
_DIMENSIONS = re.compile(
    r"(?P<length>\d+(?:\.\d+)?)\s*(?P<unit>[a-zA-Z]+)?\s*[x×]\s*"
    r"(?P<width>\d+(?:\.\d+)?)\s*(?P=unit)?\s*[x×]\s*"
    r"(?P<height>\d+(?:\.\d+)?)\s*(?P=unit)?",
    re.IGNORECASE,
)


def parse_box_prompt(prompt: str) -> DesignSpec:
    """Parse `box 5m x 3m x 2m` into the canonical design specification."""
    if "box" not in prompt.lower():
        raise PromptParseError("Phase 1 supports a box. Include the word 'box' in the prompt.")

    match = _DIMENSIONS.search(prompt)
    if not match:
        raise PromptParseError(
            "Give three dimensions, for example: Create a box 5m x 3m x 2m."
        )

    raw_unit = (match.group("unit") or "").lower()
    if not raw_unit:
        raise PromptParseError("Include one unit, for example mm, cm, m, in, or ft.")
    unit = _UNIT_ALIASES.get(raw_unit)
    if unit is None:
        raise PromptParseError(f"Unsupported unit '{raw_unit}'. Use mm, cm, m, in, or ft.")

    dimensions = Dimensions(
        length=float(match.group("length")),
        width=float(match.group("width")),
        height=float(match.group("height")),
    )
    scale = _TO_MM[unit]
    dimensions_mm = Dimensions(
        length=dimensions.length * scale,
        width=dimensions.width * scale,
        height=dimensions.height * scale,
    )
    warnings: list[str] = []
    if max(dimensions_mm.model_dump().values()) > 20_000:
        warnings.append("Large model: verify dimensions and intended unit.")

    return DesignSpec(
        object_type="box",
        dimensions=dimensions,
        unit=unit,
        dimensions_mm=dimensions_mm,
        source_prompt=prompt,
        warnings=warnings,
    )


_MEASUREMENT = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mm|cm|m|in|ft|millimeters?|centimeters?|meters?|metres?|inches?|feet|foot)\b",
    re.IGNORECASE,
)


def parse_shaft_prompt(prompt: str) -> DesignSpec:
    """Parse `500mm steel shaft with 40mm diameter` into a parametric shaft."""
    measurements = list(_MEASUREMENT.finditer(prompt))
    if len(measurements) < 2 or "shaft" not in prompt.lower() or not re.search(r"diameter|[øØφ]|dia\.?", prompt, re.IGNORECASE):
        raise PromptParseError("Give shaft length and diameter, for example: Create a 500mm steel shaft with 40mm diameter.")
    length_match, diameter_match = measurements[0], measurements[1]
    raw_length_unit = length_match.group("unit").lower()
    raw_diameter_unit = diameter_match.group("unit").lower()
    unit = _UNIT_ALIASES.get(raw_length_unit)
    diameter_unit = _UNIT_ALIASES.get(raw_diameter_unit)
    if unit is None or diameter_unit is None:
        raise PromptParseError("Use mm, cm, m, in, or ft for shaft dimensions.")
    length = float(length_match.group("value"))
    diameter = float(diameter_match.group("value"))
    length_mm = length * _TO_MM[unit]
    diameter_mm = diameter * _TO_MM[diameter_unit]
    warnings: list[str] = []
    if diameter_mm > length_mm:
        warnings.append("Diameter is greater than length; verify the shaft dimensions.")
    material_match = re.search(r"\b(steel|aluminum|aluminium|stainless steel|brass)\b", prompt, re.IGNORECASE)
    material = material_match.group(1).lower() if material_match else None
    return DesignSpec(
        object_type="shaft",
        dimensions=Dimensions(length=length, width=diameter, height=diameter),
        unit=unit,
        dimensions_mm=Dimensions(length=length_mm, width=diameter_mm, height=diameter_mm),
        material=material,
        feature_parameters={"length": length_mm, "diameter": diameter_mm},
        source_prompt=prompt,
        warnings=warnings,
    )


def parse_design_prompt(prompt: str) -> DesignSpec:
    lower = prompt.lower()
    if "shaft" in lower:
        return parse_shaft_prompt(prompt)
    if "cube" in lower:
        measurements = list(_MEASUREMENT.finditer(prompt))
        if not measurements:
            raise PromptParseError("Give the cube size, for example: Create a cube of 3cm.")
        size = float(measurements[0].group("value"))
        unit = _UNIT_ALIASES[measurements[0].group("unit").lower()]
        size_mm = size * _TO_MM[unit]
        return DesignSpec(object_type="box", dimensions=Dimensions(length=size, width=size, height=size), unit=unit, dimensions_mm=Dimensions(length=size_mm, width=size_mm, height=size_mm), feature_parameters={"length": size_mm, "width": size_mm, "height": size_mm, "is_cube": 1}, source_prompt=prompt)
    if any(kind in lower for kind in ("cylinder", "sphere", "cone", "hole")):
        return parse_round_primitive(prompt)
    if "plate" in lower:
        design = parse_box_dimensions(prompt, "plate")
        return design.model_copy(update={"object_type": "plate"})
    return parse_box_prompt(prompt)


def parse_box_dimensions(prompt: str, object_type: str) -> DesignSpec:
    """Parse a 3-dimension rectangular primitive, preserving normalized mm."""
    match = _DIMENSIONS.search(prompt)
    if not match:
        raise PromptParseError(f"Give three dimensions, for example: Create a {object_type} 200mm x 100mm x 10mm.")
    raw_unit = (match.group("unit") or "").lower()
    unit = _UNIT_ALIASES.get(raw_unit)
    if unit is None:
        raise PromptParseError("Include one unit, for example mm, cm, m, in, or ft.")
    dimensions = Dimensions(length=float(match.group("length")), width=float(match.group("width")), height=float(match.group("height")))
    scale = _TO_MM[unit]
    normalized = Dimensions(length=dimensions.length * scale, width=dimensions.width * scale, height=dimensions.height * scale)
    return DesignSpec(object_type=object_type, dimensions=dimensions, unit=unit, dimensions_mm=normalized, feature_parameters={"length": normalized.length, "width": normalized.width, "height": normalized.height}, source_prompt=prompt)


def parse_round_primitive(prompt: str) -> DesignSpec:
    lower = prompt.lower()
    object_type = "cylinder" if "cylinder" in lower else "sphere" if "sphere" in lower else "cone" if "cone" in lower else "hole"
    radius_match = re.search(r"(?:radius|r\s*=?)\s*(\d+(?:\.\d+)?)\s*(mm|cm|m|in|ft)\b", prompt, re.IGNORECASE)
    diameter_match = re.search(r"(?:diameter|dia\.?|[øØφ])\s*(\d+(?:\.\d+)?)\s*(mm|cm|m|in|ft)\b", prompt, re.IGNORECASE)
    height_match = re.search(r"(?:height|deep|depth|long|length)\s*(\d+(?:\.\d+)?)\s*(mm|cm|m|in|ft)\b", prompt, re.IGNORECASE)
    measurements = list(_MEASUREMENT.finditer(prompt))
    if radius_match:
        radius = float(radius_match.group(1)); unit = _UNIT_ALIASES[radius_match.group(2).lower()]
    elif diameter_match:
        radius = float(diameter_match.group(1)) / 2; unit = _UNIT_ALIASES[diameter_match.group(2).lower()]
    elif measurements:
        radius = float(measurements[0].group("value")); unit = _UNIT_ALIASES[measurements[0].group("unit").lower()]
    else:
        raise PromptParseError(f"Give a radius or diameter for the {object_type}.")
    height = 2 * radius if object_type == "sphere" else radius * 2
    if height_match:
        height = float(height_match.group(1)) * _TO_MM[_UNIT_ALIASES[height_match.group(2).lower()]] / _TO_MM[unit]
    elif len(measurements) >= 2 and object_type != "sphere":
        height = float(measurements[1].group("value")) * _TO_MM[_UNIT_ALIASES[measurements[1].group("unit").lower()]] / _TO_MM[unit]
    scale = _TO_MM[unit]; radius_mm = radius * scale; height_mm = height * scale
    return DesignSpec(object_type=object_type, dimensions=Dimensions(length=height, width=radius * 2, height=radius * 2), unit=unit, dimensions_mm=Dimensions(length=height_mm, width=radius_mm * 2, height=radius_mm * 2), feature_parameters={"radius": radius_mm, "height": height_mm, "diameter": radius_mm * 2}, source_prompt=prompt)
