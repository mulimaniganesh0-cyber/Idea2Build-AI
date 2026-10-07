"""LLM-driven structured design extraction for mechanical parts.

Flow:
  1. User prompt + RAG context → Ollama llama3.2 → raw JSON
  2. Pydantic MechanicalDesignSpec validates it
  3. Validated spec → deterministic CAD kernel
"""

import hashlib
import json
import re
from uuid import uuid4

from app.mechanical_models import (
    BasePlateDef,
    ChamferDef,
    FilletDef,
    GussetDef,
    HoleDef,
    MechanicalDesignSpec,
    UprightPlateDef,
)
from app.services import ollama_service
from app.services import retrieval as rag

_MECHANICAL_SYSTEM_PROMPT = """You are a CAD engineering assistant that extracts structured mechanical part specifications.

RULES:
1. Return ONLY valid JSON — no prose, no markdown, no code fences.
2. Preserve all explicit user dimensions exactly as stated.
3. DO NOT invent dimensions that are not in the prompt.
4. DO NOT include any architectural fields (floors, rooms, roof_type, g+1, etc.).
5. The JSON must conform to this schema:

{
  "domain": "mechanical",
  "object_type": "<e.g. mounting_bracket, shaft, plate, bracket>",
  "units": "mm",
  "material": "<steel|aluminium|stainless_steel|cast_iron|etc>",
  "base_plate": {
    "length_mm": <number>,
    "width_mm": <number>,
    "thickness_mm": <number>
  },
  "upright_plate": {
    "width_mm": <number>,
    "height_mm": <number>,
    "thickness_mm": <number>
  },
  "gussets": {
    "count": <number>,
    "type": "triangular"
  },
  "holes": [
    {
      "diameter_mm": <number>,
      "count": <number>,
      "location": "base|upright|custom",
      "description": "<brief description>"
    }
  ],
  "fillets": [
    {
      "radius_mm": <number>,
      "location": "<where>"
    }
  ],
  "chamfers": [
    {
      "size_mm": <number>,
      "angle_deg": 45,
      "location": "<where>"
    }
  ],
  "parametric": true,
  "source_prompt": "<original user prompt>"
}

6. Extract ALL distinct hole features into the "holes" array. Every hole specification (base corner holes, base center mounting holes, upright holes, central upright hole) must be a separate item in the "holes" array.
7. Use location="base" for holes on the base plate, and location="upright" for holes on the upright plate.

If the part has no upright_plate, omit it (set to null).
If the part has no base_plate, omit it.
"""


_UNIT_TO_MM = {
    "mm": 1.0, "millimeter": 1.0, "millimeters": 1.0, "millimetre": 1.0, "millimetres": 1.0,
    "cm": 10.0, "centimeter": 10.0, "centimeters": 10.0, "centimetre": 10.0, "centimetres": 10.0,
    "m": 1000.0, "meter": 1000.0, "meters": 1000.0, "metre": 1000.0, "metres": 1000.0,
    "in": 25.4, "inch": 25.4, "inches": 25.4,
    "ft": 304.8, "foot": 304.8, "feet": 304.8,
}


def _explicit_dimension_triplet(prompt: str, anchor_pattern: str) -> tuple[float, float, float] | None:
    """Read an unambiguous three-dimension plate callout immediately after its label."""
    anchor = re.search(anchor_pattern, prompt, re.IGNORECASE)
    if not anchor:
        return None
    clause = re.split(r"[,;.!?\n]", prompt[anchor.end():], maxsplit=1)[0]
    clause = re.sub(r"^\s*(?:dimensions?|size|of|is|are|measures?|measuring)\s*[:=]?\s*", "", clause, flags=re.IGNORECASE)
    number_unit = r"(\d+(?:\.\d+)?)\s*(mm|millimeters?|millimetres?|cm|centimeters?|centimetres?|m|meters?|metres?|inches?|in|ft|feet|foot)?"
    match = re.match(rf"^\s*{number_unit}\s*(?:x|×|by)\s*{number_unit}\s*(?:x|×|by)\s*{number_unit}\b", clause, re.IGNORECASE)
    if not match:
        return None
    groups = match.groups()
    raw_values = [float(groups[i]) for i in (0, 2, 4)]
    units = [groups[i].lower() if groups[i] else None for i in (1, 3, 5)]
    default_unit = next((unit for unit in reversed(units) if unit), "mm")
    return tuple(value * _UNIT_TO_MM[unit or default_unit] for value, unit in zip(raw_values, units))


def _explicit_hole_callout(prompt: str) -> tuple[int, float] | None:
    """Read clear calls such as 'four 12 mm holes' or '4 x Ø12 mm holes'."""
    count_words = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
    diameter_unit = r"(?P<diameter>\d+(?:\.\d+)?)\s*(?P<unit>mm|millimeters?|millimetres?|cm|centimeters?|centimetres?|m|meters?|metres?|inches?|in|ft|feet|foot)?"
    pattern = rf"\b(?P<count>{count_words})\s*(?:x|×)?\s*(?:ø\s*)?{diameter_unit}\s*(?:diameter|dia\.?|(?:mounting\s+)?(?:through[- ]?)?holes?)\b"
    match = re.search(pattern, prompt, re.IGNORECASE)
    if not match:
        return None
    count_text = match.group("count").lower()
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    count = words.get(count_text, int(count_text) if count_text.isdigit() else 0)
    unit = (match.group("unit") or "mm").lower()
    return (count, float(match.group("diameter")) * _UNIT_TO_MM[unit]) if count > 0 else None


def _preserve_explicit_requirements(spec: MechanicalDesignSpec, prompt: str) -> MechanicalDesignSpec:
    """Keep clearly stated plate dimensions and hole callouts authoritative over model output."""
    updates = {}
    base = _explicit_dimension_triplet(prompt, r"\bbase\s+plate\b")
    if base:
        updates["base_plate"] = BasePlateDef(length_mm=base[0], width_mm=base[1], thickness_mm=base[2])
    upright = _explicit_dimension_triplet(prompt, r"\b(?:upright|vertical)\s+plate\b")
    if upright:
        updates["upright_plate"] = UprightPlateDef(width_mm=upright[0], height_mm=upright[1], thickness_mm=upright[2])
    hole = _explicit_hole_callout(prompt)
    if hole:
        count, diameter = hole
        target_index = next((i for i, item in enumerate(spec.holes) if item.count == count and item.location.lower() in ("base", "custom")), None)
        if target_index is not None:
            corrected = list(spec.holes)
            corrected[target_index] = corrected[target_index].model_copy(update={"diameter_mm": diameter})
            updates["holes"] = corrected
    return spec.model_copy(update=updates) if updates else spec


def extract_mechanical_spec(
    user_prompt: str,
    context_block: str = "",
    *,
    trace_id: str | None = None,
) -> MechanicalDesignSpec:
    """Call Ollama to extract a mechanical DesignSpec from the user prompt.

    Args:
        user_prompt: The original user request.
        context_block: RAG-retrieved engineering context to inject.

    Returns:
        Validated MechanicalDesignSpec.

    Raises:
        ValueError: If the LLM output fails Pydantic validation.
        RuntimeError: If Ollama is unavailable.
    """
    trace_id = trace_id or str(uuid4())
    rag_section = f"\n\n{context_block}\n\n" if context_block else ""
    full_prompt = (
        f"ENGINEERING PROMPT:\n{user_prompt}"
        f"{rag_section}"
        "\n\nExtract the complete mechanical part specification as JSON."
    )

    raw = ollama_service.generate(
        prompt=full_prompt,
        system_prompt=_MECHANICAL_SYSTEM_PROMPT,
        temperature=0.05,
        format_json=True,
        rag_trace={
            "trace_id": trace_id,
            "context_present": bool(context_block),
            "source_count": context_block.count("\n[Source "),
            "context_characters": len(context_block),
            "context_sha256": hashlib.sha256(context_block.encode("utf-8")).hexdigest() if context_block else None,
        },
    )

    # Strip any accidental markdown fences
    raw_clean = re.sub(r"```(?:json)?|```", "", raw).strip()

    try:
        data = json.loads(raw_clean)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned invalid JSON: {exc}\n\nRaw output:\n{raw_clean}") from exc

    # Reject known architectural hallucinations before Pydantic sees them
    _ARCH_KEYS = {"floor_count", "floor_height", "roof_type", "rooms", "bedrooms", "g+1", "g+2", "site_width"}
    found = {k for k in data if k.lower() in _ARCH_KEYS}
    if found:
        raise ValueError(
            f"LLM returned architectural fields {found} inside a mechanical spec. "
            "Domain misclassification — retry with explicit mechanical context."
        )

    # Map LLM JSON → Pydantic
    spec = MechanicalDesignSpec.model_validate(data)
    spec = _preserve_explicit_requirements(spec, user_prompt)
    spec.source_prompt = user_prompt
    return spec


def build_mechanical_spec_from_prompt(user_prompt: str, *, use_rag: bool = True) -> tuple[MechanicalDesignSpec, dict]:
    """Full pipeline: RAG → LLM → validation → MechanicalDesignSpec.

    Returns (spec, rag_result) so the caller can surface RAG metadata to the UI.
    """
    # Simple geometry commands use only supplied parameters and CAD rules.
    if use_rag:
        rag_result = rag.retrieve(user_prompt, top_k=5)
        context_block = rag.build_context_block(rag_result)
    else:
        rag_result = {"status": "NOT_REQUIRED", "method": "none", "results": []}
        context_block = ""

    # LLM extraction + Pydantic validation
    spec = extract_mechanical_spec(user_prompt, context_block, trace_id=rag_result.get("trace", {}).get("trace_id"))
    return spec, rag_result
