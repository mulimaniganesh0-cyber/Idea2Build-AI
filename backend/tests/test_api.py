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
