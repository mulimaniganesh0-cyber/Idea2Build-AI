import pytest

from app.models import Unit
from app.services.parser import PromptParseError, parse_box_prompt, parse_shaft_prompt


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
