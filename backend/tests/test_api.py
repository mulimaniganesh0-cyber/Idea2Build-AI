from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_parse_endpoint() -> None:
    response = client.post(
        "/api/v1/designs/parse", json={"prompt": "Create a box 500mm x 300mm x 200mm"}
    )
    assert response.status_code == 200
    assert response.json()["dimensions_mm"]["length"] == 500


def test_project_analysis_is_versioned() -> None:
    created = client.post("/api/v1/projects/analyze", json={"prompt": "Design a 100 metre pedestrian bridge"})
    assert created.status_code == 201
    project = created.json()
    assert project["domain"] == "civil"
    assert project["missing_information"]

    revision = client.post(f"/api/v1/projects/{project['project_id']}/revisions", json={"prompt": "Design a 100 metre pedestrian bridge, 8m wide"})
    assert revision.status_code == 201
    assert revision.json()["version"] == 2


def test_chat_creates_and_updates_a_model() -> None:
    created = client.post("/api/chat", json={"message": "Create a box 5m x 3m x 2m"})
    assert created.status_code == 200
    project_id = created.json()["project_id"]
    assert created.json()["design_state"]["dimensions_mm"]["length"] == 5000

    updated = client.post("/api/chat", json={"project_id": project_id, "message": "Make it 6m long"})
    assert updated.status_code == 200
    assert updated.json()["design_state"]["dimensions_mm"]["length"] == 6000


def test_chat_generates_a_shaft() -> None:
    response = client.post("/api/chat", json={"message": "Create a 500mm steel shaft with 40mm diameter"})
    assert response.status_code == 200
    assert response.json()["design_state"]["object_type"] == "shaft"
    assert response.json()["design_state"]["feature_parameters"]["diameter"] == 40


def test_chat_creates_cube_and_modifies_all_edges() -> None:
    created = client.post("/api/chat", json={"message": "create a cube of 3cm"})
    assert created.status_code == 200
    design = created.json()["design_state"]
    assert design["dimensions_mm"] == {"length": 30, "width": 30, "height": 30}
    modified = client.post("/api/chat", json={"project_id": created.json()["project_id"], "message": "make it 5cm"})
    assert modified.status_code == 200
    assert modified.json()["design_state"]["dimensions_mm"] == {"length": 50, "width": 50, "height": 50}


def test_create_is_not_mistaken_for_modify_when_project_exists() -> None:
    first = client.post("/api/chat", json={"message": "create a box 100mm x 50mm x 20mm"}).json()
    second = client.post("/api/chat", json={"project_id": first["project_id"], "message": "create a cube of 3cm"}).json()
    assert second["design_state"]["feature_parameters"]["is_cube"] == 1


def test_cylinder_generation_contract() -> None:
    response = client.post("/api/chat", json={"message": "create a cylinder with radius 20mm and height 100mm"})
    assert response.status_code == 200
    assert response.json()["design_state"]["object_type"] == "cylinder"
    assert response.json()["design_state"]["feature_parameters"]["radius"] == 20


def test_bridge_context_is_not_sent_to_primitive_handler() -> None:
    created = client.post("/api/chat", json={"message": "Design a pedestrian bridge over a 50m span."})
    assert created.status_code == 200
    assert created.json()["active_domain"] == "bridge"
    assert "River" in created.json()["suggestions"]

    ambiguous = client.post("/api/chat", json={"project_id": created.json()["project_id"], "message": "take the minimum distance"})
    assert ambiguous.status_code == 200
    assert "vertical clearance" in ambiguous.json()["questions"][0].lower()


def test_bridge_concept_and_deck_width_update() -> None:
    created = client.post("/api/chat", json={"message": "Design a pedestrian bridge over a 50m span."}).json()
    project_id = created["project_id"]
    client.post("/api/chat", json={"project_id": project_id, "message": "River"})
    model = client.post("/api/chat", json={"project_id": project_id, "message": "Show me a truss bridge."})
    assert model.status_code == 200
    assert model.json()["design_state"]["object_type"] == "bridge"
    changed = client.post("/api/chat", json={"project_id": project_id, "message": "Make the deck 4m wide."})
    assert changed.status_code == 200
    assert changed.json()["design_state"]["feature_parameters"]["deck_width_m"] == 4
