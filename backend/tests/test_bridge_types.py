from fastapi.testclient import TestClient
from app.main import app
from app.models import BridgeType, DesignSpec, Dimensions, Unit
from app.services.cad import generate_primitive

client = TestClient(app)


def test_beam_girder_bridge_generation() -> None:
    res = client.post("/api/chat", json={"message": "Design a 50 m beam bridge, 3m wide"})
    assert res.status_code == 200
    data = res.json()
    assert data["active_domain"] == "bridge"
    assert data["design_state"]["feature_parameters"]["bridge_type"] == "beam_girder"
    assert data["design_state"]["feature_parameters"]["span_m"] == 50
    assert data["design_state"]["feature_parameters"]["deck_width_m"] == 3

    comps = data["geometry"]["components"]
    comp_names = [c["name"] for c in comps]
    assert any("deck" in n for n in comp_names)
    assert any("girder" in n for n in comp_names)
    assert any("abutment" in n for n in comp_names)


def test_truss_bridge_generation() -> None:
    res = client.post("/api/chat", json={"message": "Design a 50 m truss bridge, 3m wide"})
    assert res.status_code == 200
    data = res.json()
    assert data["design_state"]["feature_parameters"]["bridge_type"] == "truss"

    comps = data["geometry"]["components"]
    comp_types = [c["type"] for c in comps]

    assert any("chord" in t for t in comp_types)
    assert any("truss_vertical" in t for t in comp_types)
    assert any("truss_diagonal" in t for t in comp_types)
    assert any(c["rotation_rad"] != [0, 0, 0] for c in comps)


def test_arch_bridge_generation() -> None:
    res = client.post("/api/chat", json={"message": "Design a 50 m arch bridge with arch height of 8m"})
    assert res.status_code == 200
    data = res.json()
    assert data["design_state"]["feature_parameters"]["bridge_type"] == "arch"
    assert data["design_state"]["feature_parameters"]["arch_height_m"] == 8

    comps = data["geometry"]["components"]
    comp_types = [c["type"] for c in comps]

    assert "arch_rib" in comp_types
    assert "hanger" in comp_types
    assert "abutment" in comp_types
    assert any(c["rotation_rad"] != [0, 0, 0] for c in comps)


def test_suspension_bridge_generation() -> None:
    res = client.post("/api/chat", json={"message": "Design a 50 m suspension bridge with tower height of 12m"})
    assert res.status_code == 200
    data = res.json()
    assert data["design_state"]["feature_parameters"]["bridge_type"] == "suspension"
    assert data["design_state"]["feature_parameters"]["tower_height_m"] == 12

    comps = data["geometry"]["components"]
    comp_types = [c["type"] for c in comps]

    assert "tower" in comp_types
    assert "main_cable" in comp_types
    assert "hanger" in comp_types
    assert "anchorage" in comp_types


def test_cable_stayed_bridge_generation() -> None:
    res = client.post("/api/chat", json={"message": "Design a 50 m cable-stayed bridge with tower height of 12m"})
    assert res.status_code == 200
    data = res.json()
    assert data["design_state"]["feature_parameters"]["bridge_type"] == "cable_stayed"
    assert data["design_state"]["feature_parameters"]["tower_height_m"] == 12

    comps = data["geometry"]["components"]
    comp_types = [c["type"] for c in comps]

    assert "tower" in comp_types
    assert "stay_cable" in comp_types
    assert any(c["rotation_rad"] != [0, 0, 0] for c in comps)


def test_all_bridge_geometries_are_distinct() -> None:
    types = [
        BridgeType.BEAM_GIRDER,
        BridgeType.TRUSS,
        BridgeType.ARCH,
        BridgeType.SUSPENSION,
        BridgeType.CABLE_STAYED,
    ]

    results = {}
    for b_type in types:
        spec = DesignSpec(
            object_type="bridge",
            dimensions=Dimensions(length=50, width=3, height=10),
            unit=Unit.METER,
            dimensions_mm=Dimensions(length=50000, width=3000, height=10000),
            feature_parameters={
                "bridge_type": b_type.value,
                "span_m": 50,
                "deck_width_m": 3,
                "support_height_m": 5,
                "arch_height_m": 8,
                "tower_height_m": 12,
                "truss_height_m": 5,
            },
            source_prompt=f"50m {b_type.value} test",
        )
        gen = generate_primitive(spec)
        assert gen.geometry.components, f"Geometry for {b_type.value} is empty"
        results[b_type.value] = {
            "comp_count": len(gen.geometry.components),
            "type_set": set(c.type for c in gen.geometry.components),
            "name_set": set(c.name for c in gen.geometry.components),
        }

    # Verify every bridge type produces a unique component signature
    type_sets = [r["type_set"] for r in results.values()]
    for i in range(len(type_sets)):
        for j in range(i + 1, len(type_sets)):
            assert type_sets[i] != type_sets[j], f"Bridge type {types[i].value} and {types[j].value} produced identical geometry types!"
