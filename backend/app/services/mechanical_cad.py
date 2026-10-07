"""Deterministic CAD geometry kernel for mechanical parts.

Takes a validated MechanicalDesignSpec and produces a ParametricGeometry
that the Three.js viewer can render.  No LLM, no randomness — pure geometry math.
"""

import math
from uuid import uuid4

from app.mechanical_models import MechanicalDesignSpec
from app.models import CadGenerationResponse, DesignSpec, Dimensions, GeometryComponent, ParametricGeometry, Unit


def generate_mechanical_primitive(spec: MechanicalDesignSpec) -> CadGenerationResponse:
    """Generate Three.js-renderable geometry from a MechanicalDesignSpec."""
    components: list[GeometryComponent] = []

    bp = spec.base_plate
    up = spec.upright_plate

    # ── 1. BASE PLATE ────────────────────────────────────────────────────────
    bp_l = bp.length_mm / 1000 if bp else 0.16
    bp_w = bp.width_mm / 1000 if bp else 0.10
    bp_t = bp.thickness_mm / 1000 if bp else 0.012

    if bp:
        components.append(
            GeometryComponent(
                name="base_plate",
                type="base_plate",
                position_m=(0.0, bp_t / 2, 0.0),
                dimensions_m=(bp_l, bp_t, bp_w),
                material_color="#a0aec0",
            )
        )

    # ── 2. UPRIGHT PLATE ─────────────────────────────────────────────────────
    up_w = up.width_mm / 1000 if up else 0.10
    up_h = up.height_mm / 1000 if up else 0.12
    up_t = up.thickness_mm / 1000 if up else 0.012

    if up:
        components.append(
            GeometryComponent(
                name="upright_plate",
                type="upright_plate",
                position_m=(0.0, bp_t + up_h / 2, 0.0),
                dimensions_m=(up_t, up_h, up_w),
                material_color="#718096",
            )
        )

    # ── 3. GUSSETS ───────────────────────────────────────────────────────────
    gusset_count = spec.gussets.count if spec.gussets else 0
    if gusset_count > 0 and up:
        gusset_depth = up_h * 0.5   # height of the gusset triangle
        gusset_thick = up_t * 0.8   # z-thickness follows upright thickness
        gusset_base = bp_t * 0.8

        sides = [up_w / 2 - gusset_thick / 2, -(up_w / 2 - gusset_thick / 2)]
        for i, gz in enumerate(sides[:gusset_count]):
            components.append(
                GeometryComponent(
                    name=f"gusset_{'left' if i == 0 else 'right'}",
                    type="gusset_triangular",
                    position_m=(-(up_t / 2 + gusset_depth / 2), bp_t + gusset_depth / 2, gz),
                    dimensions_m=(gusset_depth, gusset_depth, gusset_thick),
                    rotation_rad=(0.0, 0.0, 0.0),
                    material_color="#4a5568",
                )
            )

    # ── 4. BASE PLATE HOLES (rendered as thin cylinders that cut through) ────
    base_holes = [
        h for h in spec.holes
        if "base" in h.location.lower() or ("upright" not in h.location.lower() and "upright" not in (h.description or "").lower())
    ]
    for hole_def in base_holes:
        r = hole_def.diameter_mm / 2 / 1000
        # Distribute holes symmetrically on base plate
        _place_holes_on_base(components, hole_def, bp_l, bp_w, bp_t, r)

    # ── 5. UPRIGHT HOLES ─────────────────────────────────────────────────────
    upright_holes = [
        h for h in spec.holes
        if "upright" in h.location.lower() or "upright" in (h.description or "").lower()
    ]
    for hole_def in upright_holes:
        r = hole_def.diameter_mm / 2 / 1000
        _place_holes_on_upright(components, hole_def, up_t, up_h, up_w, bp_t, r)

    # ── 6. FILLETS (represented as rounded corner strips on the model) ────────
    for fillet in spec.fillets:
        r_m = fillet.radius_mm / 1000
        if up and fillet.location in ("external_vertical", "external vertical edges"):
            # Add small rounded-edge indicators at the four vertical corners
            corner_x = up_t / 2
            corner_y = bp_t + up_h / 2
            corners = [(corner_x, up_w / 2), (corner_x, -up_w / 2),
                       (-corner_x, up_w / 2), (-corner_x, -up_w / 2)]
            for j, (cx, cz) in enumerate(corners):
                components.append(
                    GeometryComponent(
                        name=f"fillet_R{fillet.radius_mm:g}_{j}",
                        type="fillet_indicator",
                        position_m=(cx, corner_y, cz),
                        dimensions_m=(r_m, up_h, r_m),
                        material_color="#63b3ed",
                    )
                )

    # Build legacy DesignSpec for compatibility with the existing API contract
    total_h = (bp_t if bp else 0) + (up_h if up else 0)
    legacy_spec = DesignSpec(
        object_type="mechanical_bracket",
        dimensions=Dimensions(
            length=bp_l * 1000 if bp else 1,
            width=bp_w * 1000 if bp else 1,
            height=total_h * 1000,
        ),
        unit=Unit.MILLIMETER,
        dimensions_mm=Dimensions(
            length=bp_l * 1000 if bp else 1,
            width=bp_w * 1000 if bp else 1,
            height=total_h * 1000,
        ),
        material=spec.material,
        feature_parameters={
            "domain": "mechanical",
            "object_type": spec.object_type,
            "base_length_mm": bp.length_mm if bp else 0,
            "base_width_mm": bp.width_mm if bp else 0,
            "base_thickness_mm": bp.thickness_mm if bp else 0,
            "upright_width_mm": up.width_mm if up else 0,
            "upright_height_mm": up.height_mm if up else 0,
            "upright_thickness_mm": up.thickness_mm if up else 0,
            "gusset_count": float(gusset_count),
            "total_holes": float(sum(h.count for h in spec.holes)),
            "fillet_count": float(len(spec.fillets)),
            "chamfer_count": float(len(spec.chamfers)),
            "feature_history": "|".join(spec.feature_history()),
            "parametric": 1.0,
            "is_mechanical": 1.0,
        },
        source_prompt=spec.source_prompt,
        warnings=spec.warnings,
    )

    import hashlib, json
    spec_dict = spec.model_dump(exclude={"warnings", "source_prompt"})
    _geom_hash = hashlib.sha256(json.dumps(spec_dict, sort_keys=True).encode()).hexdigest()[:16]

    try:
        from app.services.cad_face_system import build_canonical_mechanical_cad
        build_canonical_mechanical_cad(spec)
    except Exception:
        pass

    geometry = ParametricGeometry(
        type="mechanical_parametric",
        unit="m",
        model_revision="rev_0001",
        geometry_hash=_geom_hash,
        components=components,
    )

    return CadGenerationResponse(
        model_id=f"mech_{uuid4().hex[:12]}",
        parameters=legacy_spec,
        validation=[
            "MechanicalDesignSpec validated.",
            f"Domain: mechanical",
            f"Object: {spec.object_type}",
            f"Features: {len(spec.feature_history())}",
            "CAD kernel: deterministic parametric geometry.",
        ],
        geometry=geometry,
    )


def _place_holes_on_base(
    components: list[GeometryComponent],
    hole_def,
    bp_l: float,
    bp_w: float,
    bp_t: float,
    r: float,
) -> None:
    """Place holes symmetrically on the base plate."""
    count = hole_def.count
    diam_mm = hole_def.diameter_mm
    edge_offset = max(0.020, r * 2)  # 20 mm or 2×radius from edge

    is_central = "central" in (hole_def.description or "").lower() or "center" in (hole_def.description or "").lower()
    if is_central and count == 4:
        positions = [
            (bp_l / 6, bp_w / 6),
            (bp_l / 6, -bp_w / 6),
            (-bp_l / 6, bp_w / 6),
            (-bp_l / 6, -bp_w / 6),
        ]
    elif count == 4:
        positions = [
            (bp_l / 2 - edge_offset, bp_w / 2 - edge_offset),
            (bp_l / 2 - edge_offset, -(bp_w / 2 - edge_offset)),
            (-(bp_l / 2 - edge_offset), bp_w / 2 - edge_offset),
            (-(bp_l / 2 - edge_offset), -(bp_w / 2 - edge_offset)),
        ]
    elif count == 2:
        positions = [
            (bp_l / 4, 0.0),
            (-bp_l / 4, 0.0),
        ]
    else:
        # Uniform grid
        positions = []
        per_row = max(1, int(math.ceil(math.sqrt(count))))
        for i in range(count):
            row, col = divmod(i, per_row)
            x = (col - per_row / 2 + 0.5) * (bp_l / (per_row + 1))
            z = (row - (count // per_row) / 2 + 0.5) * (bp_w / (count // per_row + 1))
            positions.append((x, z))

    for idx, (hx, hz) in enumerate(positions):
        components.append(
            GeometryComponent(
                name=f"hole_base_d{diam_mm:g}_{idx + 1}",
                type="hole_cylinder",
                position_m=(hx, bp_t / 2, hz),
                dimensions_m=(r * 2, bp_t * 1.1, r * 2),
                material_color="#1a202c",
            )
        )


def _place_holes_on_upright(
    components: list[GeometryComponent],
    hole_def,
    up_t: float,
    up_h: float,
    up_w: float,
    bp_t: float,
    r: float,
) -> None:
    """Place holes on the upright plate."""
    count = hole_def.count
    diam_mm = hole_def.diameter_mm

    center_y = bp_t + up_h / 2  # vertical center of upright

    if count == 1:
        positions = [(0.0, center_y, 0.0)]
    elif count == 2:
        offset_z = up_w / 4
        positions = [(0.0, center_y, offset_z), (0.0, center_y, -offset_z)]
    elif count == 4:
        offset_z = up_w / 4
        offset_y = up_h / 4
        positions = [
            (0.0, center_y + offset_y, offset_z),
            (0.0, center_y + offset_y, -offset_z),
            (0.0, center_y - offset_y, offset_z),
            (0.0, center_y - offset_y, -offset_z),
        ]
    else:
        positions = [(0.0, center_y, 0.0)]

    for idx, (hx, hy, hz) in enumerate(positions):
        components.append(
            GeometryComponent(
                name=f"hole_upright_d{diam_mm:g}_{idx + 1}",
                type="hole_cylinder",
                position_m=(hx, hy, hz),
                dimensions_m=(up_t * 1.1, r * 2, r * 2),
                rotation_rad=(0.0, 0.0, math.pi / 2),
                material_color="#1a202c",
            )
        )
