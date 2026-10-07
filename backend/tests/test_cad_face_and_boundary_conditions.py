import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.mechanical_models import (
    BasePlateDef,
    GussetDef,
    HoleDef,
    MechanicalDesignSpec,
    UprightPlateDef,
)
from app.models import HouseProjectState
from app.services.cad_face_system import (
    build_canonical_mechanical_cad,
    build_canonical_house_faces,
    get_cached_faces,
    get_cached_model,
)

client = TestClient(app)


@pytest.fixture
def mechanical_bracket_spec():
    return MechanicalDesignSpec(
        object_type="bracket_l_gusset",
        base_plate=BasePlateDef(length_mm=160.0, width_mm=100.0, thickness_mm=12.0),
        upright_plate=UprightPlateDef(width_mm=100.0, height_mm=120.0, thickness_mm=12.0),
        gussets=GussetDef(count=2, type="triangular"),
        holes=[
            HoleDef(diameter_mm=10.0, count=4, location="base"),
            HoleDef(diameter_mm=14.0, count=1, location="upright"),
        ],
        material="structural_steel",
    )


@pytest.fixture
def house_state():
    return HouseProjectState(
        project_id="house_test_55",
        site_width_m=12.0,
        site_length_m=16.0,
        building_width_m=9.0,
        building_length_m=11.0,
        floors=2,
        floor_height_m=3.0,
        roof_type="pitched",
        material="reinforced_concrete",
    )


# ── 1. CAD Face System Unit Tests ──────────────────────────────────────────

def test_mechanical_cad_face_extraction(mechanical_bracket_spec):
    model = build_canonical_mechanical_cad(mechanical_bracket_spec, project_id="test_bracket")
    assert model.domain == "mechanical"
    assert len(model.faces) > 0
    assert model.geometry_hash is not None

    # Check face metadata properties
    first_face = model.faces[0]
    assert first_face.face_id.startswith("base_plate:face:")
    assert first_face.area_mm2 > 0
    assert first_face.area_m2 > 0
    assert "x" in first_face.normal
    assert "y" in first_face.normal
    assert "z" in first_face.normal
    assert first_face.structural is True
    assert first_face.face_signature is not None

    # Determinism / Stability: building again should produce identical hashes and IDs
    model_again = build_canonical_mechanical_cad(mechanical_bracket_spec, project_id="test_bracket")
    assert model_again.geometry_hash == model.geometry_hash
    assert len(model_again.faces) == len(model.faces)
    assert [f.face_id for f in model_again.faces] == [f.face_id for f in model.faces]
    assert [f.face_signature for f in model_again.faces] == [f.face_signature for f in model.faces]


def test_house_cad_face_extraction(house_state):
    model = build_canonical_house_faces(house_state)
    assert model.domain == "architectural"
    assert len(model.faces) > 0
    assert model.geometry_hash is not None

    # Check that structural and non-structural classifications are preserved
    has_structural = any(f.structural for f in model.faces)
    assert has_structural is True


# ── 2. Phase 5.5 Face API Endpoints ────────────────────────────────────────

def test_api_list_and_inspect_faces(mechanical_bracket_spec):
    model = build_canonical_mechanical_cad(mechanical_bracket_spec, project_id="test_api")
    h = model.geometry_hash

    # GET /api/v1/cad/{geometry_hash}/faces
    res = client.get(f"/api/v1/cad/{h}/faces")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["count"] == len(model.faces)
    assert len(data["faces"]) == len(model.faces)

    # Inspect first face
    target = model.faces[0]
    inspect_res = client.post("/api/v1/cad/face/inspect", json={
        "model_id": model.model_id,
        "geometry_hash": h,
        "model_revision": model.revision,
        "component_id": target.component_id,
        "face_id": target.face_id,
    })
    assert inspect_res.status_code == 200
    inspect_data = inspect_res.json()
    assert inspect_data["ok"] is True
    assert inspect_data["face"]["face_id"] == target.face_id
    assert inspect_data["face"]["area_m2"] == target.area_m2


def test_api_unknown_geometry_hash():
    res = client.get("/api/v1/cad/unknown_hash_9999/faces")
    assert res.status_code == 404


# ── 3. Engineering Loads and Supports ──────────────────────────────────────

def test_api_loads_and_supports_crud(mechanical_bracket_spec):
    import uuid
    model = build_canonical_mechanical_cad(mechanical_bracket_spec, project_id="test_crud")
    h = model.geometry_hash
    rev = model.revision
    m_id = f"mech_crud_{uuid.uuid4().hex[:8]}"
    target_face = model.faces[0]

    # 1. Create a load
    load_res = client.post("/api/v1/engineering/loads", json={
        "model_id": m_id,
        "project_id": "test_crud",
        "model_revision": rev,
        "geometry_hash": h,
        "component_id": target_face.component_id,
        "face_id": target_face.face_id,
        "type": "FORCE",
        "magnitude": 5000.0,
        "unit": "N",
        "direction_x": 0.0,
        "direction_y": -1.0,
        "direction_z": 0.0,
    })
    assert load_res.status_code == 201
    load_data = load_res.json()
    assert load_data["ok"] is True
    load_id = load_data["load_id"]

    # 2. List loads
    list_loads_res = client.get(f"/api/v1/engineering/loads/{m_id}")
    assert list_loads_res.status_code == 200
    loads_list = list_loads_res.json()
    assert loads_list["count"] >= 1
    assert any(ld["load_id"] == load_id for ld in loads_list["loads"])

    # 3. Create a support
    support_face = model.faces[1]
    supp_res = client.post("/api/v1/engineering/supports", json={
        "model_id": m_id,
        "project_id": "test_crud",
        "model_revision": rev,
        "geometry_hash": h,
        "component_id": support_face.component_id,
        "face_id": support_face.face_id,
        "type": "FIXED",
    })
    assert supp_res.status_code == 201
    supp_data = supp_res.json()
    assert supp_data["ok"] is True
    supp_id = supp_data["support_id"]

    # 4. List supports
    list_supp_res = client.get(f"/api/v1/engineering/supports/{m_id}")
    assert list_supp_res.status_code == 200
    supp_list = list_supp_res.json()
    assert supp_list["count"] >= 1
    assert any(s["support_id"] == supp_id for s in supp_list["supports"])

    # 5. Engineering Summary
    sum_res = client.get(f"/api/v1/engineering/summary/{m_id}")
    assert sum_res.status_code == 200
    sum_data = sum_res.json()
    assert sum_data["load_count"] >= 1
    assert sum_data["support_count"] >= 1
    assert sum_data["resultant_force_N"] == 5000.0

    # 6. Delete load
    del_ld = client.delete(f"/api/v1/engineering/loads/{load_id}")
    assert del_ld.status_code == 200

    # Verify deleted load is no longer in active list
    list_loads_after = client.get(f"/api/v1/engineering/loads/{m_id}").json()
    assert not any(ld["load_id"] == load_id for ld in list_loads_after["loads"])

    # 7. Delete support
    del_sp = client.delete(f"/api/v1/engineering/supports/{supp_id}")
    assert del_sp.status_code == 200


def test_api_reject_invalid_face_id(mechanical_bracket_spec):
    model = build_canonical_mechanical_cad(mechanical_bracket_spec, project_id="test_reject")
    h = model.geometry_hash
    rev = model.revision

    # Attempt load on a bogus face_id
    bad_res = client.post("/api/v1/engineering/loads", json={
        "model_id": model.model_id,
        "project_id": "test_reject",
        "model_revision": rev,
        "geometry_hash": h,
        "component_id": "base_plate",
        "face_id": "nonexistent:face:9999",
        "type": "FORCE",
        "magnitude": 1000.0,
    })
    assert bad_res.status_code == 422


def test_api_reject_revision_mismatch(mechanical_bracket_spec):
    model = build_canonical_mechanical_cad(mechanical_bracket_spec, project_id="test_mismatch")
    target_face = model.faces[0]

    # Send stale revision string
    mismatch_res = client.post("/api/v1/engineering/loads", json={
        "model_id": model.model_id,
        "project_id": "test_mismatch",
        "model_revision": "rev_stale_0000",
        "geometry_hash": model.geometry_hash,
        "component_id": target_face.component_id,
        "face_id": target_face.face_id,
        "type": "FORCE",
        "magnitude": 1000.0,
    })
    assert mismatch_res.status_code == 409
