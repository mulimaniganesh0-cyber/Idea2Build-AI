import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import HouseProjectState
from app.services.house_cad import (
    CanonicalHouseCADModel,
    build_canonical_house_cad,
)
from app.services.house_tree import HouseComponentTree
from app.services.material_registry import get_material, list_materials

client = TestClient(app)


def test_material_registry():
    mat = get_material("reinforced_concrete")
    assert mat is not None
    assert mat.density_kg_m3 == 2400.0
    assert mat.youngs_modulus_pa == 31.0e9
    assert mat.poisson_ratio == 0.20
    assert "Eurocode" in mat.source or "IS" in mat.source

    mat_steel = get_material("structural_steel")
    assert mat_steel.density_kg_m3 == 7850.0

    all_materials = list_materials()
    assert len(all_materials) >= 4


def test_house_component_tree():
    state = HouseProjectState(
        project_id="test_house_tree",
        site_width_m=9.144,
        site_length_m=12.192,
        floors=2,
        building_width_m=7.144,
        building_length_m=10.192,
        floor_height_m=3.0,
        roof_type="pitched",
    )
    tree = HouseComponentTree(state)
    comps = tree.get_components()
    assert len(comps) >= 15
    struct_comps = tree.get_structural_components()
    assert len(struct_comps) >= 6
    non_struct_comps = tree.get_non_structural_components()
    assert len(non_struct_comps) >= 5
    geo_comps = tree.to_geometry_components()
    assert len(geo_comps) == len(comps)
    for comp in comps:
        assert comp.component_id
        assert comp.classification.value in ["structural", "non_structural", "architectural", "decorative"]


def test_build_canonical_house_cad():
    state = HouseProjectState(
        project_id="test_house_cad",
        site_width_m=9.144,
        site_length_m=12.192,
        floors=2,
        building_width_m=7.144,
        building_length_m=10.192,
        floor_height_m=3.0,
        roof_type="pitched",
    )
    cad = build_canonical_house_cad(state)
    assert isinstance(cad, CanonicalHouseCADModel)
    assert cad.solid_count >= 10
    assert cad.face_count >= 60
    assert cad.edge_count >= 120
    assert cad.vertex_count >= 80
    assert cad.validation_passed is True
    assert cad.volume_m3 > 0.0
    assert cad.total_mass_kg > 0.0
    assert cad.surface_area_m2 > 0.0
    assert isinstance(cad.center_of_mass_m, dict)

    # Check inspector dict conversion
    insp = cad.to_inspector_dict()
    assert insp["solid_topology"]["solid_count"] == cad.solid_count
    assert insp["physical_properties"]["mass_kg"] == round(cad.total_mass_kg, 2)
    assert insp["material"]["primary"]["name"] == "Reinforced Concrete C25/30"

    # Check STEP export
    step_data = cad.export_step()
    assert len(step_data) > 0
    assert b"ISO-10303-21" in step_data

    # Check STL export
    stl_data = cad.export_stl()
    assert len(stl_data) > 0

    # Check OBJ export
    obj_data = cad.export_obj()
    assert len(obj_data) > 0
    assert b"v " in obj_data or b"#" in obj_data


def test_api_house_cad_generate():
    payload = {
        "site_width_m": 9.144,
        "site_length_m": 12.192,
        "floors": 2,
        "building_width_m": 7.144,
        "building_length_m": 10.192,
        "floor_height_m": 3.0,
        "material": "reinforced_concrete",
        "roof_type": "pitched",
    }
    resp = client.post("/api/house/cad/generate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "solid_topology" in data
    assert data["solid_topology"]["solid_count"] >= 10
    assert data["validity"] == "PASS"
    assert "physical_properties" in data
    assert data["physical_properties"]["mass_kg"] > 0


def test_api_house_cad_properties():
    payload = {
        "floors": 2,
        "building_width_m": 8.0,
        "building_length_m": 10.0,
        "floor_height_m": 3.0,
    }
    resp = client.post("/api/house/cad/properties", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["geometry"]["volume_m3"] > 0
    assert data["physical_properties"]["mass_kg"] > 0


def test_api_house_cad_tree():
    payload = {"floors": 2}
    resp = client.post("/api/house/cad/tree", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "components" in data
    assert data["structural_count"] >= 6
    assert len(data["components"]) >= 15


def test_api_house_cad_faces():
    payload = {"floors": 1}
    resp = client.post("/api/house/cad/faces", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["face_count"] > 0
    assert len(data["faces"]) > 0
    face0 = data["faces"][0]
    assert "face_id" in face0
    assert "area_m2" in face0
    assert "normal" in face0


def test_api_house_cad_exports():
    payload = {"floors": 2}

    # STEP export
    resp_step = client.post("/api/house/cad/export/step", json=payload)
    assert resp_step.status_code == 200
    assert resp_step.headers["content-type"] == "application/step"
    assert len(resp_step.content) > 0
    assert b"ISO-10303-21" in resp_step.content

    # STL export
    resp_stl = client.post("/api/house/cad/export/stl", json=payload)
    assert resp_stl.status_code == 200
    assert resp_stl.headers["content-type"] == "application/octet-stream"
    assert len(resp_stl.content) > 0

    # OBJ export
    resp_obj = client.post("/api/house/cad/export/obj", json=payload)
    assert resp_obj.status_code == 200
    assert resp_obj.headers["content-type"] == "model/obj"
    assert len(resp_obj.content) > 0
