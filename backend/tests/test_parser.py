import pytest

from app.models import Unit
from app.services.parser import PromptParseError, parse_box_prompt, parse_design_prompt, parse_shaft_prompt


def test_parses_metric_box() -> None:
    design = parse_box_prompt("Create a box 5m × 3m × 2m")

    assert design.unit is Unit.METER
    assert design.dimensions.length == 5
    assert design.dimensions_mm.height == 2000


def test_rejects_missing_unit() -> None:
    with pytest.raises(PromptParseError, match="Include one unit"):
        parse_box_prompt("Create a box 5 x 3 x 2")


def test_rejects_unsupported_object() -> None:
    with pytest.raises(PromptParseError, match="supports a box"):
        parse_box_prompt("Create a sphere 5m x 3m x 2m")


def test_parses_steel_shaft() -> None:
    design = parse_shaft_prompt("Create a 500mm steel shaft with 40mm diameter")
    assert design.object_type == "shaft"
    assert design.material == "steel"
    assert design.feature_parameters["diameter"] == 40


@pytest.mark.parametrize("prompt", [
    "make a 5m cube",
    "create a 5 meter cube",
    "create cube 5000mm",
    "make a cube with side 2m",
    "build cube 5m",
    "generate a 5 metre cube",
    "create cube with 5000 mm side",
    "make a cube having side 5m",
])
def test_cube_prompt_variants_normalize_to_equal_millimeter_dimensions(prompt: str) -> None:
    design = parse_design_prompt(prompt)
    assert design.feature_parameters["is_cube"] == 1
    assert design.dimensions_mm.length == design.dimensions_mm.width == design.dimensions_mm.height
    assert design.dimensions_mm.length in {2000, 5000}
