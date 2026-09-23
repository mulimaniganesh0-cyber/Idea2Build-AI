from fastapi.testclient import TestClient

from app.main import app
from app.models import HouseProjectState
from app.services.cad import generate_primitive
from app.services.house import create_house_concept_model, extract_floor_count, extract_site_dimensions, is_house_request, parse_floor_expression

client = TestClient(app)


def test_is_house_request_detection() -> None:
    assert is_house_request("a house for 30*40 site with 2 story")
    assert is_house_request("I want to design a 3-storey villa on a 40 x 60 ft plot.")
    assert is_house_request("Make the building 3 floors")
    assert is_house_request("Build a G+2 house")
    assert is_house_request("Make it G+3")
    assert not is_house_request("Create a box 5m x 3m x 2m")


def test_extract_site_and_floors() -> None:
    w_m, l_m, unit = extract_site_dimensions("a house for 30*40 site with 2 story")
    assert w_m is not None and l_m is not None
    assert abs(w_m - (30 * 0.3048)) < 0.01
    assert unit == "ft"
    assert extract_floor_count("a house for 30*40 site with 2 story") == 2


def test_floor_parsing_variations() -> None:
    # "Make the building 3 floors"
    total, g_inc, upper, label = parse_floor_expression("Make the building 3 floors")
    assert total == 3
    assert g_inc is True
    assert upper == 2
    assert label == "G+2"

    # "Make it three floors"
    total, _, upper, label = parse_floor_expression("Make it three floors")
    assert total == 3
    assert upper == 2
    assert label == "G+2"

    # "Add one more floor" starting from 3 floors
    total, _, upper, label = parse_floor_expression("Add one more floor", current_floors=3)
    assert total == 4
    assert upper == 3
    assert label == "G+3"

    # "Add another floor" starting from 2 floors
    total, _, upper, label = parse_floor_expression("Add another floor", current_floors=2)
    assert total == 3
    assert upper == 2
    assert label == "G+2"

    # "Change it to 4 floors"
    total, _, upper, label = parse_floor_expression("Change it to 4 floors")
    assert total == 4
    assert upper == 3
    assert label == "G+3"

    # "I want a ground floor and 2 upper floors"
    total, _, upper, label = parse_floor_expression("I want a ground floor and 2 upper floors")
    assert total == 3
    assert upper == 2
    assert label == "G+2"

    # "Build a G+2 house"
    total, _, upper, label = parse_floor_expression("Build a G+2 house")
    assert total == 3
    assert upper == 2
    assert label == "G+2"

    # "Make it G+3"
    total, _, upper, label = parse_floor_expression("Make it G+3")
    assert total == 4
    assert upper == 3
    assert label == "G+3"

    # "Change the house from 2 floors to 3 floors"
    total, _, upper, label = parse_floor_expression("Change the house from 2 floors to 3 floors")
    assert total == 3
    assert upper == 2
    assert label == "G+2"

    # Single floor
    total, _, upper, label = parse_floor_expression("Single floor house")
    assert total == 1
    assert upper == 0
    assert label == "Ground Floor"


def test_building_geometry_slab_count_and_elevations() -> None:
    for n_floors in [1, 2, 3, 4]:
        state = HouseProjectState(
            project_id=f"p_{n_floors}",
            site_width_m=9.144,
            site_length_m=12.192,
            floors=n_floors,
        )
        design = create_house_concept_model(state)
        res = generate_primitive(design)
        
        slabs = [c for c in res.geometry.components if c.type == "floor_slab"]
        walls = [c for c in res.geometry.components if c.type == "wall_volume"]
        columns = [c for c in res.geometry.components if c.type == "column"]
        roof = [c for c in res.geometry.components if c.type == "roof"]

        assert len(slabs) == n_floors, f"Expected {n_floors} slabs, got {len(slabs)}"
        assert len(walls) == n_floors, f"Expected {n_floors} wall volumes, got {len(walls)}"
        assert len(columns) == n_floors * 4, f"Expected {n_floors * 4} columns, got {len(columns)}"
        assert len(roof) == 1, "Expected 1 roof slab"

        # Verify elevations of each slab
        for idx, slab in enumerate(slabs):
            expected_y = idx * 3.0 + 0.15
            assert abs(slab.position_m[1] - expected_y) < 0.01

        # Check validation messages
        assert any(f"{n_floors} physical floor slabs generated" in msg for msg in res.validation)


def test_chat_multi_turn_conversational_modifications() -> None:
    # Turn 1: Initial 2-floor house
    r1 = client.post("/api/chat", json={"message": "Design a house for a 30x40 site with 2 floors"})
    assert r1.status_code == 200
    d1 = r1.json()
    project_id = d1["project_id"]
    assert d1["design_state"]["feature_parameters"]["floors"] == 2
    assert d1["design_state"]["feature_parameters"]["floor_label"] == "G+1"
    slabs_1 = [c for c in d1["geometry"]["components"] if c["type"] == "floor_slab"]
    assert len(slabs_1) == 2

    # Turn 2: "Make the building 3 floors"
    r2 = client.post("/api/chat", json={"project_id": project_id, "message": "Make the building 3 floors"})
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["design_state"]["feature_parameters"]["floors"] == 3
    assert d2["design_state"]["feature_parameters"]["floor_label"] == "G+2"
    assert abs(d2["design_state"]["feature_parameters"]["site_width_m"] - (30 * 0.3048)) < 0.01
    assert abs(d2["design_state"]["feature_parameters"]["site_length_m"] - (40 * 0.3048)) < 0.01
    slabs_2 = [c for c in d2["geometry"]["components"] if c["type"] == "floor_slab"]
    assert len(slabs_2) == 3

    # Turn 3: "Add another floor"
    r3 = client.post("/api/chat", json={"project_id": project_id, "message": "Add another floor"})
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["design_state"]["feature_parameters"]["floors"] == 4
    assert d3["design_state"]["feature_parameters"]["floor_label"] == "G+3"
    slabs_3 = [c for c in d3["geometry"]["components"] if c["type"] == "floor_slab"]
    assert len(slabs_3) == 4

    # Turn 4: "Change it to 2 floors"
    r4 = client.post("/api/chat", json={"project_id": project_id, "message": "Change it to 2 floors"})
    assert r4.status_code == 200
    d4 = r4.json()
    assert d4["design_state"]["feature_parameters"]["floors"] == 2
    assert d4["design_state"]["feature_parameters"]["floor_label"] == "G+1"
    slabs_4 = [c for c in d4["geometry"]["components"] if c["type"] == "floor_slab"]
    assert len(slabs_4) == 2


def test_house_interior_procedural_components() -> None:
    state = HouseProjectState(
        project_id="house_interior_test",
        site_width_m=9.144,
        site_length_m=12.192,
        floors=2,
    )
    design = create_house_concept_model(state)
    res = generate_primitive(design)

    components = res.geometry.components
    types = {c.type for c in components}

    # Verify key interior architectural elements
    assert "interior_wall" in types, "Missing interior partition walls"
    assert "furniture_sofa" in types, "Missing living room sofa"
    assert "furniture_bed" in types, "Missing bedroom beds"
    assert "furniture_counter" in types, "Missing kitchen counter"
    assert "furniture_table" in types, "Missing dining table or desk"
    assert "furniture_chair" in types, "Missing chairs"
    assert "furniture_sanitary" in types, "Missing bathroom sanitary fixtures"
    assert "staircase" in types, "Missing staircase for multi-story house"

    # Verify floor_number and room_id metadata tagging
    interior_comps = [c for c in components if c.type.startswith("furniture_") or c.type == "interior_wall"]
    assert len(interior_comps) > 0
    for comp in interior_comps:
        assert comp.floor_number is not None, f"Component {comp.name} missing floor_number"
        assert comp.room_id is not None, f"Component {comp.name} missing room_id"


def test_view_mode_and_furniture_chat_intents() -> None:
    # 1. Create a house
    r1 = client.post("/api/chat", json={"message": "a house for 30*40 site with 2 story"})
    assert r1.status_code == 200
    d1 = r1.json()
    project_id = d1["project_id"]

    # 2. Switch to interior view
    r2 = client.post("/api/chat", json={"project_id": project_id, "message": "Show the interior layout"})
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["design_state"]["feature_parameters"]["view_mode"] == "interior"
    assert "interior" in d2["message"].lower()

    # 3. Filter to ground floor
    r3 = client.post("/api/chat", json={"project_id": project_id, "message": "Show ground floor only"})
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["design_state"]["feature_parameters"]["active_floor"] == 0

    # 4. Filter to first floor
    r4 = client.post("/api/chat", json={"project_id": project_id, "message": "Show level 1 floor plan"})
    assert r4.status_code == 200
    d4 = r4.json()
    assert d4["design_state"]["feature_parameters"]["active_floor"] == 1
    assert d4["design_state"]["feature_parameters"]["view_mode"] == "floor_plan"

    # 5. Add custom furniture
    r5 = client.post("/api/chat", json={"project_id": project_id, "message": "Add a desk to the bedroom"})
    assert r5.status_code == 200
    d5 = r5.json()
    furniture_comps = [c for c in d5["geometry"]["components"] if "desk" in c["name"].lower()]
    assert len(furniture_comps) > 0

