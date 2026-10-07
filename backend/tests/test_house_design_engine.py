from app.models import HouseProjectState
from app.services import house_design
from app.services.house_design import HouseRequirements, allocate_rooms, analyze_site, create_design_options, extract_requirements, validate_rectangles
from fastapi.testclient import TestClient
from app.main import app


def test_extracts_explicit_house_requirements_and_keeps_unknowns_empty() -> None:
    req = extract_requirements("Modern house on 30 x 40 ft plot, 2 floors, 3 bedrooms, 2 bathrooms in Chikkodi")
    assert abs(req.plot_width - 30) < 0.001 and abs(req.plot_length - 40) < 0.001 and req.plot_unit == "ft"
    assert (req.floors, req.bedrooms, req.bathrooms) == (2, 3, 2)
    assert req.location == "Chikkodi"
    assert req.climate == {}
    assert req.parking is None


def test_progressive_clarification_requests_only_missing_critical_requirements() -> None:
    result = create_design_options(HouseRequirements(plot_area_sqft=1200), use_rag=False)
    assert result["requires_clarification"]
    assert result["missing_requirements"] == ["floors", "bedrooms"]
    assert result["options"] == []


def test_site_estimate_labels_planning_allowance_and_does_not_claim_setback_compliance() -> None:
    req = HouseRequirements(plot_width=30, plot_length=40, floors=2, bedrooms=3)
    site = analyze_site(req)
    assert site["plot_area_sqft"] == 1200
    assert site["estimated_footprint_sqft"] == 630
    assert site["setbacks"] == "NOT_SPECIFIED"
    assert "not a regulatory setback" in site["assumptions"][0]


def test_room_allocation_is_structured_and_reports_actual_packing_status() -> None:
    req = HouseRequirements(plot_width=30, plot_length=40, floors=2, bedrooms=3, bathrooms=2)
    result = allocate_rooms(req, analyze_site(req))
    assert len(result["floors"]) == 2
    assert all(room["x_ft"] is not None and room["y_ft"] is not None for floor in result["floors"] for room in floor["rooms"])
    assert result["overlap_check"].startswith("PASS:")
    assert result["boundary_check"].startswith("ERROR:")
    assert result["fit_check"].startswith("WARNING:")
    assert any(floor["room_validation"]["status"] == "ERROR" for floor in result["floors"])
    assert result["furniture_collision_check"].startswith("NOT_RUN")


def test_rectangle_collision_validator_passes_room_fixtures_and_rejects_overlap_and_boundary() -> None:
    living_room = [
        {"id": "sofa", "x": 0, "y": 0, "width": 7, "length": 3},
        {"id": "coffee_table", "x": 8, "y": 0, "width": 3, "length": 2},
        {"id": "tv_console", "x": 12, "y": 0, "width": 5, "length": 1},
    ]
    bedroom = [
        {"id": "bed", "x": 0, "y": 0, "width": 6, "length": 7},
        {"id": "wardrobe", "x": 8, "y": 0, "width": 2, "length": 6},
        {"id": "side_table", "x": 7, "y": 8, "width": 2, "length": 2},
    ]
    kitchen = [
        {"id": "counter", "x": 0, "y": 0, "width": 10, "length": 2},
        {"id": "cabinets", "x": 12, "y": 0, "width": 2, "length": 8},
        {"id": "island", "x": 5, "y": 5, "width": 4, "length": 2},
    ]
    for fixture in (living_room, bedroom, kitchen):
        assert validate_rectangles(fixture, 18, 12)["status"] == "PASS"
    invalid = [
        {"id": "bed", "x": 0, "y": 0, "width": 7, "length": 8},
        {"id": "wardrobe", "x": 6, "y": 4, "width": 3, "length": 5},
        {"id": "outside_item", "x": 17, "y": 0, "width": 2, "length": 2},
    ]
    report = validate_rectangles(invalid, 18, 12)
    assert report["status"] == "ERROR"
    assert {issue["kind"] for issue in report["issues"]} == {"overlap", "outside_envelope"}


def test_options_are_distinct_and_include_parameterized_roof_palette_and_interior() -> None:
    req = HouseRequirements(plot_area_sqft=1200, floors=2, bedrooms=3, style="modern", interior_style="modern_luxury")
    result = create_design_options(req, use_rag=False)
    assert len(result["options"]) == 3
    assert len({o["option_hash"] for o in result["options"]}) == 3
    assert {o["roof_type"] for o in result["options"]} == {"gable", "flat", "hip"}
    assert len({o["palette"] for o in result["options"]}) == 3


def test_rag_ab_decision_and_provenance_marker_reach_design_planner(monkeypatch) -> None:
    marker = "RAG_TEST_MARKER_HOUSE_ABC123 gutter guidance"
    def fake_retrieve(query: str, top_k: int = 4) -> dict:
        assert "rainfall_class" in query
        return {"status": "FOUND", "trace": {"trace_id": "trace-house-test"}, "results": [{"chunk_id": 4321, "source": "house-climate.pdf", "title": "Rainfall roof guidance", "page": 4, "score": 0.91, "content": marker}]}
    monkeypatch.setattr(house_design, "retrieve", fake_retrieve)
    req = HouseRequirements(plot_area_sqft=1200, floors=2, bedrooms=3, climate={"rainfall_class": "high"})
    enabled = create_design_options(req, use_rag=True)
    disabled = create_design_options(req, use_rag=False)
    enabled_option = enabled["options"][2]
    disabled_option = disabled["options"][2]
    assert enabled["knowledge"]["sources"][0]["content"] == marker
    assert enabled_option["gutters"] is True
    assert disabled_option["gutters"] is False
    assert enabled_option["option_hash"] != disabled_option["option_hash"]
    assert enabled["reasoning"][0]["source_ids"] == [4321]


def test_merge_persists_requirements_and_documents_area_only_envelope_assumption() -> None:
    req = HouseRequirements(plot_area_sqft=1200, floors=2, bedrooms=3)
    result = create_design_options(req, use_rag=False)
    state = house_design.merge_requirements(HouseProjectState(project_id="plan-test"), req, result)
    assert state.house_requirements["bedrooms"] == 3
    assert state.site_width_m and state.site_length_m
    assert any("Equivalent 1.25:1" in note for note in state.site_analysis["assumptions"])
    assert len(state.design_options) == 3


def test_house_option_selection_persists_revision_and_regenerates_canonical_geometry() -> None:
    client = TestClient(app)
    options = client.post("/api/house/design-options", json={"requirements": {"plot_area_sqft": 1200, "floors": 2, "bedrooms": 3, "bathrooms": 2, "balcony": True}, "use_rag": False})
    assert options.status_code == 200
    body = options.json()
    assert len(body["options"]) == 3
    generated = client.post("/api/house/design-options/select", json={"project_id": body["project_id"], "option_id": "climate_optimized"})
    assert generated.status_code == 200
    result = generated.json()
    assert result["version"] == 1
    assert result["design_state"]["feature_parameters"]["bedrooms"] == 3
    assert result["design_state"]["feature_parameters"]["roof_type"] == "hip"
    assert result["kernel_report"]["solid_topology"]["solid_count"] > 0
    assert result["kernel_report"]["validity"] == "PASS"
    assert result["geometry"]["components"]
