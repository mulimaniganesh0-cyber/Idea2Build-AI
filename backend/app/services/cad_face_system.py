"""Canonical CAD Face Identity and Topology Extraction System.

Governed by OpenCASCADE / build123d as the sole geometry authority.
Computes deterministic face identity, exact B-Rep areas, normals, centroids,
surface types, and bounding boxes for both Mechanical and House models.

No Three.js mesh calculations or client-side geometry assumptions are trusted.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import build123d as bd
from pydantic import BaseModel, Field

from app.mechanical_models import MechanicalDesignSpec
from app.models import DesignSpec, HouseProjectState
from app.services.house_tree import ComponentClassification, HouseComponentTree
from app.services.material_registry import MaterialDefinition, get_material


class CADFaceMetadata(BaseModel):
    """Authoritative CAD face metadata derived exclusively from OpenCASCADE B-Rep."""
    face_id: str = Field(description="Deterministic face identity: {component_id}:face:{index}")
    component_id: str = Field(description="ID of the parent CAD component")
    model_revision: str = Field(description="Model revision string (e.g. rev_0001)")
    geometry_hash: str = Field(description="SHA-256 hash of canonical model parameters")
    area_mm2: float = Field(description="Exact face surface area in mm²")
    area_m2: float = Field(description="Exact face surface area in m²")
    center_mm: dict[str, float] = Field(description="Centroid {x, y, z} in mm")
    center_m: dict[str, float] = Field(description="Centroid {x, y, z} in m")
    normal: dict[str, float] = Field(description="Unit normal vector {x, y, z} evaluated at centroid")
    surface_type: str = Field(description="B-Rep surface geometry type (Plane, Cylinder, etc.)")
    bounding_box: dict[str, float] = Field(description="Axis-aligned bbox in mm: min_x, max_x, min_y, max_y, min_z, max_z")
    structural: bool = Field(default=True, description="Whether this face belongs to a structural load-bearing member")
    classification: str = Field(default="structural", description="Classification: structural, non_structural, architectural, decorative")
    material_id: str = Field(default="structural_steel", description="Material ID from engineering material registry")
    face_signature: str = Field(description="Geometric signature hash for topology stability tracking")

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


def _face_sort_key(f: bd.Face) -> tuple:
    """Deterministic sort key for OpenCASCADE faces within a component."""
    c = f.center()
    try:
        norm = f.normal_at(c)
        n = (round(float(norm.X), 3), round(float(norm.Y), 3), round(float(norm.Z), 3))
    except Exception:
        n = (0.0, 0.0, 0.0)
    return (
        str(f.geom_type),
        n[0], n[1], n[2],
        round(float(c.X), 2), round(float(c.Y), 2), round(float(c.Z), 2),
        round(float(f.area), 2),
    )


def extract_faces_from_solid(
    solid: bd.Solid,
    component_id: str,
    model_revision: str,
    geometry_hash: str,
    structural: bool = True,
    classification: str = "structural",
    material_id: str = "structural_steel",
    scale_to_mm: float = 1.0,  # 1.0 if solid is in mm, 1000.0 if solid is in m
) -> list[CADFaceMetadata]:
    """Extract deterministic CADFaceMetadata list from an OpenCASCADE solid."""
    faces = list(solid.faces())
    # Sort deterministically so face indices never jump across rebuilds
    faces.sort(key=_face_sort_key)

    result: list[CADFaceMetadata] = []
    for f_idx, face in enumerate(faces):
        fc = face.center()
        normal_vec = (0.0, 1.0, 0.0)
        try:
            norm = face.normal_at(fc)
            normal_vec = (float(norm.X), float(norm.Y), float(norm.Z))
        except Exception:
            pass

        # Normal unit vector normalization check
        norm_len = (normal_vec[0]**2 + normal_vec[1]**2 + normal_vec[2]**2)**0.5
        if norm_len > 1e-6:
            normal_vec = (normal_vec[0] / norm_len, normal_vec[1] / norm_len, normal_vec[2] / norm_len)

        f_bbox = face.bounding_box()

        # Handle SI units
        if scale_to_mm == 1.0:
            # Solid is natively in mm
            area_mm2 = float(face.area)
            area_m2 = area_mm2 / 1_000_000.0
            center_mm = {"x": round(float(fc.X), 3), "y": round(float(fc.Y), 3), "z": round(float(fc.Z), 3)}
            center_m = {"x": round(center_mm["x"] / 1000.0, 5), "y": round(center_mm["y"] / 1000.0, 5), "z": round(center_mm["z"] / 1000.0, 5)}
            bbox_mm = {
                "min_x": round(float(f_bbox.min.X), 3), "max_x": round(float(f_bbox.max.X), 3),
                "min_y": round(float(f_bbox.min.Y), 3), "max_y": round(float(f_bbox.max.Y), 3),
                "min_z": round(float(f_bbox.min.Z), 3), "max_z": round(float(f_bbox.max.Z), 3),
            }
        else:
            # Solid is natively in meters
            area_m2 = float(face.area)
            area_mm2 = area_m2 * 1_000_000.0
            center_m = {"x": round(float(fc.X), 4), "y": round(float(fc.Y), 4), "z": round(float(fc.Z), 4)}
            center_mm = {"x": round(center_m["x"] * 1000.0, 2), "y": round(center_m["y"] * 1000.0, 2), "z": round(center_m["z"] * 1000.0, 2)}
            bbox_mm = {
                "min_x": round(float(f_bbox.min.X) * 1000.0, 2), "max_x": round(float(f_bbox.max.X) * 1000.0, 2),
                "min_y": round(float(f_bbox.min.Y) * 1000.0, 2), "max_y": round(float(f_bbox.max.Y) * 1000.0, 2),
                "min_z": round(float(f_bbox.min.Z) * 1000.0, 2), "max_z": round(float(f_bbox.max.Z) * 1000.0, 2),
            }

        face_id = f"{component_id}:face:{f_idx}"
        sig_raw = f"{component_id}:{face.geom_type}:{round(normal_vec[0], 2)}_{round(normal_vec[1], 2)}_{round(normal_vec[2], 2)}:{round(center_mm['x'], 1)}_{round(center_mm['y'], 1)}_{round(center_mm['z'], 1)}:{round(area_mm2, 1)}"
        face_signature = hashlib.sha256(sig_raw.encode("utf-8")).hexdigest()[:12]

        surface_type_str = str(face.geom_type).replace("GeomType.", "").capitalize()

        result.append(
            CADFaceMetadata(
                face_id=face_id,
                component_id=component_id,
                model_revision=model_revision,
                geometry_hash=geometry_hash,
                area_mm2=round(area_mm2, 2),
                area_m2=round(area_m2, 6),
                center_mm=center_mm,
                center_m=center_m,
                normal={"x": round(normal_vec[0], 4), "y": round(normal_vec[1], 4), "z": round(normal_vec[2], 4)},
                surface_type=surface_type_str,
                bounding_box=bbox_mm,
                structural=structural,
                classification=classification,
                material_id=material_id,
                face_signature=face_signature,
            )
        )

    return result


@dataclass
class CanonicalCADModel:
    model_id: str
    project_id: str
    revision: str
    geometry_hash: str
    domain: str  # "mechanical" | "architectural"
    faces: list[CADFaceMetadata]
    solids: dict[str, bd.Solid]
    components: list[dict[str, Any]]
    total_volume_mm3: float
    total_mass_kg: float
    primary_material: MaterialDefinition

    def get_face(self, face_id: str) -> CADFaceMetadata | None:
        for f in self.faces:
            if f.face_id == face_id:
                return f
        return None


# In-memory geometry cache by geometry_hash to prevent repeated OpenCASCADE solid rebuilds on UI clicks
_GEOMETRY_CACHE: dict[str, CanonicalCADModel] = {}


def build_canonical_mechanical_cad(spec: MechanicalDesignSpec, project_id: str = "mech_default", version: int = 1) -> CanonicalCADModel:
    """Build genuine OpenCASCADE solids and extract canonical CADFaceMetadata for a mechanical spec."""
    revision = f"rev_{version:04d}"

    # Calculate deterministic geometry hash from spec
    spec_dict = spec.model_dump(exclude={"warnings", "source_prompt"})
    geom_hash = hashlib.sha256(json.dumps(spec_dict, sort_keys=True).encode("utf-8")).hexdigest()[:16]

    if geom_hash in _GEOMETRY_CACHE:
        return _GEOMETRY_CACHE[geom_hash]

    solids: dict[str, bd.Solid] = {}
    faces: list[CADFaceMetadata] = []
    comp_defs: list[dict[str, Any]] = []
    total_vol_mm3 = 0.0

    mat = get_material(spec.material or "structural_steel")

    # 1. Base Plate
    if spec.base_plate:
        bp = spec.base_plate
        bp_l = bp.length_mm
        bp_w = bp.width_mm
        bp_t = bp.thickness_mm
        # Centered on X and Z, Y from 0 to bp_t
        bp_solid = bd.Pos(0, bp_t / 2, 0) * bd.Box(bp_l, bp_t, bp_w)

        # Apply base plate hole cuts if any
        base_holes = [h for h in spec.holes if "base" in h.location.lower() or ("upright" not in h.location.lower() and "upright" not in (h.description or "").lower())]
        for hole_def in base_holes:
            r = hole_def.diameter_mm / 2
            margin_x = min(bp_l * 0.20, 25.0)
            margin_z = min(bp_w * 0.20, 20.0)
            x_coords = [-(bp_l / 2 - margin_x), (bp_l / 2 - margin_x)]
            z_coords = [-(bp_w / 2 - margin_z), (bp_w / 2 - margin_z)]
            hole_positions = []
            if hole_def.count == 4:
                hole_positions = [(x, z) for x in x_coords for z in z_coords]
            elif hole_def.count == 2:
                hole_positions = [(-(bp_l / 2 - margin_x), 0), (bp_l / 2 - margin_x, 0)]
            elif hole_def.count == 1:
                hole_positions = [(0, 0)]
            else:
                hole_positions = [(x, z) for x in x_coords for z in z_coords][:hole_def.count]

            for hx, hz in hole_positions:
                cutter = bd.Pos(hx, bp_t / 2, hz) * bd.Cylinder(radius=r, height=bp_t * 2)
                try:
                    bp_solid = bp_solid - cutter
                except Exception:
                    pass

        solids["base_plate"] = bp_solid
        bp_faces = extract_faces_from_solid(
            solid=bp_solid,
            component_id="base_plate",
            model_revision=revision,
            geometry_hash=geom_hash,
            structural=True,
            classification="structural",
            material_id=mat.material_id,
            scale_to_mm=1.0,
        )
        faces.extend(bp_faces)
        total_vol_mm3 += float(bp_solid.volume)
        comp_defs.append({
            "component_id": "base_plate",
            "name": "Base Plate",
            "type": "base_plate",
            "structural": True,
            "classification": "structural",
            "material_id": mat.material_id,
            "face_count": len(bp_faces),
        })

    # 2. Upright Plate
    if spec.upright_plate:
        up = spec.upright_plate
        bp_t = spec.base_plate.thickness_mm if spec.base_plate else 0.0
        up_w = up.width_mm
        up_h = up.height_mm
        up_t = up.thickness_mm

        up_solid = bd.Pos(0, bp_t + up_h / 2, 0) * bd.Box(up_t, up_h, up_w)

        # Apply upright hole cuts if any
        upright_holes = [h for h in spec.holes if "upright" in h.location.lower() or "upright" in (h.description or "").lower()]
        for hole_def in upright_holes:
            r = hole_def.diameter_mm / 2
            h_y = bp_t + up_h * 0.65
            if hole_def.count == 1:
                cutter = bd.Pos(0, h_y, 0) * bd.Rot(Y=90) * bd.Cylinder(radius=r, height=up_t * 2)
                try:
                    up_solid = up_solid - cutter
                except Exception:
                    pass
            elif hole_def.count == 2:
                for z in [-up_w * 0.25, up_w * 0.25]:
                    cutter = bd.Pos(0, h_y, z) * bd.Rot(Y=90) * bd.Cylinder(radius=r, height=up_t * 2)
                    try:
                        up_solid = up_solid - cutter
                    except Exception:
                        pass

        solids["upright_plate"] = up_solid
        up_faces = extract_faces_from_solid(
            solid=up_solid,
            component_id="upright_plate",
            model_revision=revision,
            geometry_hash=geom_hash,
            structural=True,
            classification="structural",
            material_id=mat.material_id,
            scale_to_mm=1.0,
        )
        faces.extend(up_faces)
        total_vol_mm3 += float(up_solid.volume)
        comp_defs.append({
            "component_id": "upright_plate",
            "name": "Upright Plate",
            "type": "upright_plate",
            "structural": True,
            "classification": "structural",
            "material_id": mat.material_id,
            "face_count": len(up_faces),
        })

    # 3. Gussets
    if spec.gussets and spec.gussets.count > 0 and spec.upright_plate:
        up = spec.upright_plate
        bp_t = spec.base_plate.thickness_mm if spec.base_plate else 0.0
        up_h = up.height_mm
        up_t = up.thickness_mm
        up_w = up.width_mm
        gd = up_h * 0.5
        gt = up_t * 0.8
        for i in range(spec.gussets.count):
            gz = (up_w / 2 - gt / 2) * (1 if i == 0 else -1)
            cid = f"gusset_{'left' if i == 0 else 'right'}"
            # Model gusset box/wedge
            g_solid = bd.Pos(-(up_t / 2 + gd / 2), bp_t + gd / 2, gz) * bd.Box(gd, gd, gt)
            solids[cid] = g_solid
            g_faces = extract_faces_from_solid(
                solid=g_solid,
                component_id=cid,
                model_revision=revision,
                geometry_hash=geom_hash,
                structural=True,
                classification="structural",
                material_id=mat.material_id,
                scale_to_mm=1.0,
            )
            faces.extend(g_faces)
            total_vol_mm3 += float(g_solid.volume)
            comp_defs.append({
                "component_id": cid,
                "name": cid.replace("_", " ").title(),
                "type": "gusset_triangular",
                "structural": True,
                "classification": "structural",
                "material_id": mat.material_id,
                "face_count": len(g_faces),
            })

    # 4. Fallback for generic box/cylinder primitive
    if not solids:
        l = spec.length_mm or 100.0
        w = spec.width_mm or 100.0
        h = spec.height_mm or 100.0
        cid = "primitive_body"
        prim_solid = bd.Pos(0, h / 2, 0) * bd.Box(l, h, w)
        solids[cid] = prim_solid
        prim_faces = extract_faces_from_solid(
            solid=prim_solid,
            component_id=cid,
            model_revision=revision,
            geometry_hash=geom_hash,
            structural=True,
            classification="structural",
            material_id=mat.material_id,
            scale_to_mm=1.0,
        )
        faces.extend(prim_faces)
        total_vol_mm3 += float(prim_solid.volume)
        comp_defs.append({
            "component_id": cid,
            "name": "Primitive Body",
            "type": spec.object_type,
            "structural": True,
            "classification": "structural",
            "material_id": mat.material_id,
            "face_count": len(prim_faces),
        })

    total_vol_m3 = total_vol_mm3 * 1e-9
    total_mass_kg = total_vol_m3 * mat.density_kg_m3

    model = CanonicalCADModel(
        model_id=f"mech_{geom_hash[:8]}",
        project_id=project_id,
        revision=revision,
        geometry_hash=geom_hash,
        domain="mechanical",
        faces=faces,
        solids=solids,
        components=comp_defs,
        total_volume_mm3=round(total_vol_mm3, 2),
        total_mass_kg=round(total_mass_kg, 4),
        primary_material=mat,
    )
    _GEOMETRY_CACHE[geom_hash] = model
    return model


def build_canonical_house_faces(state: HouseProjectState, version: int = 1) -> CanonicalCADModel:
    """Build canonical CADFaceMetadata for all structural and architectural house elements."""
    revision = f"rev_{version:04d}"

    tree = HouseComponentTree(state)
    components = tree.get_components()

    # Geometry hash based on house dimensions and floor parameters
    hash_payload = {
        "site_w": state.site_width_m,
        "site_l": state.site_length_m,
        "b_w": state.building_width_m,
        "b_l": state.building_length_m,
        "floors": state.floors,
        "floor_h": state.floor_height_m,
        "roof": state.roof_type,
        "comp_count": len(components),
    }
    geom_hash = hashlib.sha256(json.dumps(hash_payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]

    if geom_hash in _GEOMETRY_CACHE:
        return _GEOMETRY_CACHE[geom_hash]

    solids: dict[str, bd.Solid] = {}
    faces: list[CADFaceMetadata] = []
    comp_defs: list[dict[str, Any]] = []
    total_vol_m3 = 0.0
    total_mass_kg = 0.0

    primary_mat = get_material(state.material or "reinforced_concrete")

    for comp in components:
        comp_mat = get_material(comp.material_id)
        pos = comp.position_m
        dim = comp.dimensions_m
        dx = max(0.01, dim[0])
        dy = max(0.01, dim[1])
        dz = max(0.01, dim[2])

        try:
            solid = bd.Pos(pos[0], pos[1], pos[2]) * bd.Box(dx, dy, dz)
            if not solid.is_valid or solid.volume <= 0:
                continue

            solids[comp.component_id] = solid
            comp_faces = extract_faces_from_solid(
                solid=solid,
                component_id=comp.component_id,
                model_revision=revision,
                geometry_hash=geom_hash,
                structural=comp.structural,
                classification=comp.classification.value,
                material_id=comp_mat.material_id,
                scale_to_mm=1000.0,  # Convert SI meters to mm
            )
            faces.extend(comp_faces)
            v = float(solid.volume)
            total_vol_m3 += v
            total_mass_kg += v * comp_mat.density_kg_m3
            comp_defs.append({
                "component_id": comp.component_id,
                "name": comp.name,
                "type": comp.component_type,
                "structural": comp.structural,
                "classification": comp.classification.value,
                "material_id": comp_mat.material_id,
                "face_count": len(comp_faces),
            })
        except Exception:
            pass

    model = CanonicalCADModel(
        model_id=f"house_{state.project_id}_{version}",
        project_id=state.project_id,
        revision=revision,
        geometry_hash=geom_hash,
        domain="architectural",
        faces=faces,
        solids=solids,
        components=comp_defs,
        total_volume_mm3=round(total_vol_m3 * 1e9, 2),
        total_mass_kg=round(total_mass_kg, 2),
        primary_material=primary_mat,
    )
    _GEOMETRY_CACHE[geom_hash] = model
    return model


def get_cached_faces(geometry_hash: str) -> list[CADFaceMetadata] | None:
    """Return cached face list for a geometry hash, or None if not yet built."""
    model = _GEOMETRY_CACHE.get(geometry_hash)
    return model.faces if model is not None else None


def get_cached_model(geometry_hash: str) -> CanonicalCADModel | None:
    """Return the full CanonicalCADModel for a geometry hash, or None."""
    return _GEOMETRY_CACHE.get(geometry_hash)
