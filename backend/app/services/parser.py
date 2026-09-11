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
        dimensions=dimensions,
        unit=unit,
        dimensions_mm=dimensions_mm,
        source_prompt=prompt,
        warnings=warnings,
    )
