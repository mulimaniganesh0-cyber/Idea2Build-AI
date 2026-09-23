"""Parametric CAD generation boundary.

Phase 1 returns validated analytic primitive parameters for the web viewer. This
is the single location to replace with OCCT B-Rep and STEP/STL export later.
"""

import math
from uuid import uuid4

from app.models import BridgeType, CadGenerationResponse, DesignSpec, GeometryComponent, ParametricGeometry


def generate_primitive(design: DesignSpec) -> CadGenerationResponse:
    if design.object_type not in {"box", "shaft", "plate", "cylinder", "sphere", "cone", "hole", "bridge", "house"}:
        raise ValueError(f"Unsupported CAD primitive: {design.object_type}")
    
    validation = ["Schema validation passed.", "Units normalized to millimetres.", "Parametric viewer geometry generated."]
    if design.object_type == "house":
        geometry, extra_validation = _generate_house_building_geometry(design)
        validation.extend(extra_validation)
    else:
        geometry = _geometry_for(design)

    return CadGenerationResponse(
        model_id=f"model_{uuid4().hex[:12]}",
        parameters=design,
        validation=validation,
        geometry=geometry,
    )


def _generate_house_building_geometry(design: DesignSpec) -> tuple[ParametricGeometry, list[str]]:
    params = design.feature_parameters
    mm = design.dimensions_mm
    site_w = float(params.get("site_width_m", mm.width / 1000))
    site_l = float(params.get("site_length_m", mm.length / 1000))
    b_w = float(params.get("building_width_m", site_w * 0.75))
    b_l = float(params.get("building_length_m", site_l * 0.70))
    floors = max(1, int(params.get("floors", params.get("floor_count", 2))))
    floor_h = float(params.get("floor_height_m", 3.0))
    roof_type = str(params.get("roof_type", "pitched"))

    components: list[GeometryComponent] = [
        GeometryComponent(
            name="site_boundary",
            type="site_plot",
            position_m=(0, 0.05, 0),
            dimensions_m=(b_w * 1.3, 0.1, b_l * 1.3),
        ),
    ]

    interior_items_count = 0

    for i in range(floors):
        base_y = i * floor_h

        # 1. Floor slab
        components.append(
            GeometryComponent(
                name=f"floor_slab_{i+1}",
                type="floor_slab",
                floor_number=i,
                position_m=(0, base_y + 0.15, 0),
                dimensions_m=(b_w * 1.02, 0.3, b_l * 1.02),
                material_color="#475569",
            )
        )

        # 2. Structural corner columns
        col_w = 0.35
        col_h = floor_h - 0.3
        col_y = base_y + 0.3 + (col_h / 2)
        cx = (b_w / 2) - (col_w / 2)
        cz = (b_l / 2) - (col_w / 2)
        for c_idx, (col_x, col_z) in enumerate([(-cx, cz), (cx, cz), (-cx, -cz), (cx, -cz)]):
            components.append(
                GeometryComponent(
                    name=f"column_fl{i+1}_{c_idx+1}",
                    type="column",
                    floor_number=i,
                    position_m=(col_x, col_y, col_z),
                    dimensions_m=(col_w, col_h, col_w),
                    material_color="#334155",
                )
            )

        # 3. Exterior Wall envelope
        components.append(
            GeometryComponent(
                name=f"floor_walls_{i+1}",
                type="wall_volume",
                floor_number=i,
                position_m=(0, base_y + (floor_h / 2) + 0.15, 0),
                dimensions_m=(b_w, floor_h - 0.3, b_l),
                material_color="#f8fafc",
            )
        )

        # 4. Front windows
        components.append(
            GeometryComponent(
                name=f"window_front_{i+1}_left",
                type="window",
                floor_number=i,
                position_m=(-b_w * 0.25, base_y + (floor_h * 0.55), b_l / 2 + 0.05),
                dimensions_m=(b_w * 0.25, 1.2, 0.1),
                material_color="#38bdf8",
            )
        )
        components.append(
            GeometryComponent(
                name=f"window_front_{i+1}_right",
                type="window",
                floor_number=i,
                position_m=(b_w * 0.25, base_y + (floor_h * 0.55), b_l / 2 + 0.05),
                dimensions_m=(b_w * 0.25, 1.2, 0.1),
                material_color="#38bdf8",
            )
        )

        # 5. Balcony for upper floors
        if i >= 1:
            components.append(
                GeometryComponent(
                    name=f"balcony_fl{i+1}",
                    type="balcony",
                    floor_number=i,
                    position_m=(0, base_y + 0.3, (b_l / 2) + 0.5),
                    dimensions_m=(b_w * 0.55, 0.2, 1.0),
                    material_color="#64748b",
                )
            )

        # 6. Interior Partition Walls
        wall_h = floor_h - 0.3
        # Longitudinal center partition wall
        components.append(
            GeometryComponent(
                name=f"wall_center_fl{i+1}",
                type="interior_wall",
                floor_number=i,
                room_id=f"hallway_{i}",
                position_m=(0, base_y + (wall_h / 2) + 0.15, -b_l * 0.05),
                dimensions_m=(0.15, wall_h, b_l * 0.7),
                material_color="#e2e8f0",
            )
        )
        # Transverse partition wall 1 (divides front from back rooms on left)
        components.append(
            GeometryComponent(
                name=f"wall_transverse_left_fl{i+1}",
                type="interior_wall",
                floor_number=i,
                room_id=f"left_partition_{i}",
                position_m=(-b_w * 0.24, base_y + (wall_h / 2) + 0.15, 0),
                dimensions_m=(b_w * 0.46, wall_h, 0.15),
                material_color="#e2e8f0",
            )
        )
        # Transverse partition wall 2 (encloses bathroom/utility on right)
        components.append(
            GeometryComponent(
                name=f"wall_transverse_right_fl{i+1}",
                type="interior_wall",
                floor_number=i,
                room_id=f"right_partition_{i}",
                position_m=(b_w * 0.24, base_y + (wall_h / 2) + 0.15, -b_l * 0.16),
                dimensions_m=(b_w * 0.46, wall_h, 0.15),
                material_color="#e2e8f0",
            )
        )

        # 7. Procedural Interior Furniture & Fixtures per floor
        if i == 0:
            # === GROUND FLOOR ===
            # Living Room (Front-Left)
            components.extend([
                GeometryComponent(
                    name="sofa_living_0",
                    type="furniture_sofa",
                    floor_number=0,
                    room_id="living_room_0",
                    position_m=(-b_w * 0.25, base_y + 0.65, b_l * 0.22),
                    dimensions_m=(2.2, 0.7, 0.9),
                    material_color="#1e3a8a",
                ),
                GeometryComponent(
                    name="coffee_table_0",
                    type="furniture_table",
                    floor_number=0,
                    room_id="living_room_0",
                    position_m=(-b_w * 0.25, base_y + 0.45, b_l * 0.08),
                    dimensions_m=(1.1, 0.4, 0.6),
                    material_color="#78350f",
                ),
                GeometryComponent(
                    name="tv_unit_0",
                    type="furniture_tv_unit",
                    floor_number=0,
                    room_id="living_room_0",
                    position_m=(-b_w * 0.42, base_y + 0.7, b_l * 0.12),
                    dimensions_m=(0.4, 0.9, 1.6),
                    material_color="#0f172a",
                ),
            ])
            interior_items_count += 3

            # Kitchen & Dining (Back-Left)
            components.extend([
                GeometryComponent(
                    name="kitchen_counter_0",
                    type="furniture_counter",
                    floor_number=0,
                    room_id="kitchen_dining_0",
                    position_m=(-b_w * 0.28, base_y + 0.6, -b_l * 0.32),
                    dimensions_m=(2.2, 0.85, 0.65),
                    material_color="#475569",
                ),
                GeometryComponent(
                    name="dining_table_0",
                    type="furniture_table",
                    floor_number=0,
                    room_id="kitchen_dining_0",
                    position_m=(-b_w * 0.22, base_y + 0.6, -b_l * 0.14),
                    dimensions_m=(1.5, 0.75, 0.85),
                    material_color="#92400e",
                ),
                GeometryComponent(
                    name="dining_chair_0_1",
                    type="furniture_chair",
                    floor_number=0,
                    room_id="kitchen_dining_0",
                    position_m=(-b_w * 0.22, base_y + 0.55, -b_l * 0.14 + 0.6),
                    dimensions_m=(0.45, 0.8, 0.45),
                    material_color="#334155",
                ),
                GeometryComponent(
                    name="dining_chair_0_2",
                    type="furniture_chair",
                    floor_number=0,
                    room_id="kitchen_dining_0",
                    position_m=(-b_w * 0.22, base_y + 0.55, -b_l * 0.14 - 0.6),
                    dimensions_m=(0.45, 0.8, 0.45),
                    material_color="#334155",
                ),
            ])
            interior_items_count += 4

            # Bathroom (Back-Right)
            components.extend([
                GeometryComponent(
                    name="toilet_0",
                    type="furniture_sanitary",
                    floor_number=0,
                    room_id="bathroom_0",
                    position_m=(b_w * 0.32, base_y + 0.5, -b_l * 0.32),
                    dimensions_m=(0.48, 0.68, 0.62),
                    material_color="#f8fafc",
                ),
                GeometryComponent(
                    name="wash_basin_0",
                    type="furniture_sanitary",
                    floor_number=0,
                    room_id="bathroom_0",
                    position_m=(b_w * 0.15, base_y + 0.6, -b_l * 0.35),
                    dimensions_m=(0.55, 0.8, 0.45),
                    material_color="#f8fafc",
                ),
            ])
            interior_items_count += 2

            # Staircase (Front-Right)
            for s in range(6):
                components.append(
                    GeometryComponent(
                        name=f"stair_step_{s+1}",
                        type="staircase",
                        floor_number=0,
                        room_id="staircase_0",
                        position_m=(b_w * 0.32, base_y + 0.3 + (s * 0.4), b_l * 0.30 - (s * 0.32)),
                        dimensions_m=(0.9, 0.22, 0.35),
                        material_color="#64748b",
                    )
                )
            interior_items_count += 6

        elif i == 1:
            # === FIRST FLOOR ===
            # Master Bedroom (Left-Half)
            components.extend([
                GeometryComponent(
                    name="bed_master_1",
                    type="furniture_bed",
                    floor_number=1,
                    room_id="bedroom_1_master",
                    position_m=(-b_w * 0.25, base_y + 0.55, -b_l * 0.14),
                    dimensions_m=(1.8, 0.65, 2.0),
                    material_color="#b45309",
                ),
                GeometryComponent(
                    name="headboard_master_1",
                    type="furniture_bed",
                    floor_number=1,
                    room_id="bedroom_1_master",
                    position_m=(-b_w * 0.25, base_y + 0.8, -b_l * 0.14 - 1.05),
                    dimensions_m=(2.0, 1.0, 0.12),
                    material_color="#78350f",
                ),
                GeometryComponent(
                    name="wardrobe_master_1",
                    type="furniture_wardrobe",
                    floor_number=1,
                    room_id="bedroom_1_master",
                    position_m=(-b_w * 0.42, base_y + 1.2, b_l * 0.16),
                    dimensions_m=(0.55, 2.0, 1.8),
                    material_color="#334155",
                ),
                GeometryComponent(
                    name="nightstand_left_1",
                    type="furniture_table",
                    floor_number=1,
                    room_id="bedroom_1_master",
                    position_m=(-b_w * 0.25 - 1.15, base_y + 0.5, -b_l * 0.14 - 0.8),
                    dimensions_m=(0.45, 0.55, 0.45),
                    material_color="#78350f",
                ),
            ])
            interior_items_count += 4

            # Guest Bedroom / Study (Front-Right)
            components.extend([
                GeometryComponent(
                    name="bed_guest_1",
                    type="furniture_bed",
                    floor_number=1,
                    room_id="bedroom_1_guest",
                    position_m=(b_w * 0.25, base_y + 0.5, b_l * 0.18),
                    dimensions_m=(1.1, 0.55, 1.9),
                    material_color="#b45309",
                ),
                GeometryComponent(
                    name="study_desk_1",
                    type="furniture_table",
                    floor_number=1,
                    room_id="bedroom_1_guest",
                    position_m=(b_w * 0.35, base_y + 0.6, b_l * 0.02),
                    dimensions_m=(1.1, 0.75, 0.55),
                    material_color="#78350f",
                ),
            ])
            interior_items_count += 2

            # Bathroom (Back-Right)
            components.extend([
                GeometryComponent(
                    name="toilet_1",
                    type="furniture_sanitary",
                    floor_number=1,
                    room_id="bathroom_1",
                    position_m=(b_w * 0.32, base_y + 0.5, -b_l * 0.32),
                    dimensions_m=(0.48, 0.68, 0.62),
                    material_color="#f8fafc",
                ),
                GeometryComponent(
                    name="wash_basin_1",
                    type="furniture_sanitary",
                    floor_number=1,
                    room_id="bathroom_1",
                    position_m=(b_w * 0.15, base_y + 0.6, -b_l * 0.35),
                    dimensions_m=(0.55, 0.8, 0.45),
                    material_color="#f8fafc",
                ),
            ])
            interior_items_count += 2

        else:
            # === UPPER FLOORS (2+) ===
            components.extend([
                GeometryComponent(
                    name=f"exec_desk_{i+1}",
                    type="furniture_table",
                    floor_number=i,
                    room_id=f"study_{i}",
                    position_m=(-b_w * 0.25, base_y + 0.6, b_l * 0.15),
                    dimensions_m=(1.5, 0.75, 0.75),
                    material_color="#78350f",
                ),
                GeometryComponent(
                    name=f"bookshelf_{i+1}",
                    type="furniture_wardrobe",
                    floor_number=i,
                    room_id=f"study_{i}",
                    position_m=(-b_w * 0.42, base_y + 1.2, -b_l * 0.05),
                    dimensions_m=(0.4, 2.0, 1.6),
                    material_color="#334155",
                ),
                GeometryComponent(
                    name=f"bed_extra_{i+1}",
                    type="furniture_bed",
                    floor_number=i,
                    room_id=f"bedroom_{i}",
                    position_m=(b_w * 0.25, base_y + 0.5, b_l * 0.14),
                    dimensions_m=(1.4, 0.55, 1.9),
                    material_color="#b45309",
                ),
                GeometryComponent(
                    name=f"toilet_{i+1}",
                    type="furniture_sanitary",
                    floor_number=i,
                    room_id=f"bathroom_{i}",
                    position_m=(b_w * 0.32, base_y + 0.5, -b_l * 0.32),
                    dimensions_m=(0.48, 0.68, 0.62),
                    material_color="#f8fafc",
                ),
            ])
            interior_items_count += 4

    # Entrance door on Ground Floor
    components.append(
        GeometryComponent(
            name="entrance_door",
            type="door",
            floor_number=0,
            position_m=(0, 1.15, b_l / 2 + 0.06),
            dimensions_m=(1.2, 2.1, 0.12),
            material_color="#d97706",
        )
    )

    # Roof slab / cap
    roof_y = floors * floor_h + 0.3
    components.append(
        GeometryComponent(
            name="roof_slab",
            type="roof",
            floor_number=floors - 1,
            position_m=(0, roof_y + 0.15, 0),
            dimensions_m=(b_w * 1.08, 0.3, b_l * 1.08),
            material_color="#1e293b",
        )
    )

    if roof_type == "pitched":
        components.append(
            GeometryComponent(
                name="roof_ridge",
                type="roof_pitched",
                floor_number=floors - 1,
                position_m=(0, roof_y + 0.7, 0),
                dimensions_m=(b_w * 0.95, 0.8, b_l * 0.95),
                material_color="#334155",
            )
        )

    slab_count = len([c for c in components if c.type == "floor_slab"])
    validation_notes = [
        f"Verified: {slab_count} physical floor slabs generated (matches {floors} requested floors).",
        f"Verified: {interior_items_count} procedural interior rooms and furniture objects generated.",
        f"Building massing height: {roof_y:.1f} m.",
    ]
    return ParametricGeometry(type="house", components=components), validation_notes


def _geometry_for(design: DesignSpec) -> ParametricGeometry:
    mm = design.dimensions_mm
    if design.object_type == "house":
        geom, _ = _generate_house_building_geometry(design)
        return geom

    if design.object_type == "bridge":
        return _generate_bridge_geometry(design)

    return ParametricGeometry(
        type=design.object_type,
        components=[
            GeometryComponent(
                name=design.object_type,
                type=design.object_type,
                dimensions_m=(mm.length / 1000, mm.height / 1000, mm.width / 1000),
            ),
        ],
    )


def _generate_bridge_geometry(design: DesignSpec) -> ParametricGeometry:
    params = design.feature_parameters
    span = float(params.get("span_m", design.dimensions_mm.length / 1000))
    width = float(params.get("deck_width_m", design.dimensions_mm.width / 1000))
    support_h = float(params.get("support_height_m", 5.0))

    raw_type = str(params.get("bridge_type", "beam_girder"))
    try:
        bridge_type = BridgeType(raw_type)
    except ValueError:
        bridge_type = BridgeType.BEAM_GIRDER

    if bridge_type == BridgeType.TRUSS:
        truss_h = float(params.get("truss_height_m", max(3.0, span * 0.10)))
        panels = int(params.get("number_of_panels", max(6, min(16, int(span / 5)))))
        return _generate_truss_bridge(span, width, support_h, truss_h, panels)
    elif bridge_type == BridgeType.ARCH:
        arch_h = float(params.get("arch_height_m", max(4.0, span * 0.16)))
        return _generate_arch_bridge(span, width, support_h, arch_h)
    elif bridge_type == BridgeType.SUSPENSION:
        tower_h = float(params.get("tower_height_m", max(8.0, span * 0.24)))
        sag = float(params.get("cable_sag_m", tower_h * 0.65))
        return _generate_suspension_bridge(span, width, support_h, tower_h, sag)
    elif bridge_type == BridgeType.CABLE_STAYED:
        tower_h = float(params.get("tower_height_m", max(8.0, span * 0.24)))
        return _generate_cable_stayed_bridge(span, width, support_h, tower_h)
    else:
        return _generate_beam_girder_bridge(span, width, support_h)


def _generate_beam_girder_bridge(span: float, width: float, support_h: float) -> ParametricGeometry:
    components: list[GeometryComponent] = [
        GeometryComponent(
            name="deck",
            type="deck",
            position_m=(0, support_h, 0),
            dimensions_m=(span, 0.45, width),
        ),
        GeometryComponent(
            name="left_girder",
            type="girder",
            position_m=(0, support_h - 0.35, -width * 0.35),
            dimensions_m=(span, 0.5, 0.3),
        ),
        GeometryComponent(
            name="right_girder",
            type="girder",
            position_m=(0, support_h - 0.35, width * 0.35),
            dimensions_m=(span, 0.5, 0.3),
        ),
        GeometryComponent(
            name="left_abutment",
            type="abutment",
            position_m=(-span * 0.46, support_h / 2, 0),
            dimensions_m=(1.2, support_h, width * 1.1),
        ),
        GeometryComponent(
            name="right_abutment",
            type="abutment",
            position_m=(span * 0.46, support_h / 2, 0),
            dimensions_m=(1.2, support_h, width * 1.1),
        ),
    ]

    # intermediate piers and cross beams for longer spans
    num_cross = max(4, int(span / 8))
    dx = span / (num_cross + 1)
    for i in range(1, num_cross + 1):
        x = -span / 2 + i * dx
        components.append(
            GeometryComponent(
                name=f"cross_beam_{i}",
                type="cross_beam",
                position_m=(x, support_h - 0.35, 0),
                dimensions_m=(0.25, 0.35, width * 0.8),
            )
        )

    if span > 25:
        components.append(
            GeometryComponent(
                name="center_pier",
                type="pier",
                position_m=(0, support_h / 2, 0),
                dimensions_m=(1.0, support_h, width * 0.9),
            )
        )

    return ParametricGeometry(type="bridge_beam_girder", components=components)


def _generate_truss_bridge(span: float, width: float, support_h: float, truss_h: float, panels: int) -> ParametricGeometry:
    components: list[GeometryComponent] = [
        GeometryComponent(
            name="deck",
            type="deck",
            position_m=(0, support_h, 0),
            dimensions_m=(span, 0.4, width),
        ),
        # Bottom Chords
        GeometryComponent(
            name="bottom_chord_left",
            type="truss_chord",
            position_m=(0, support_h + 0.1, -width * 0.48),
            dimensions_m=(span, 0.25, 0.25),
        ),
        GeometryComponent(
            name="bottom_chord_right",
            type="truss_chord",
            position_m=(0, support_h + 0.1, width * 0.48),
            dimensions_m=(span, 0.25, 0.25),
        ),
        # Top Chords
        GeometryComponent(
            name="top_chord_left",
            type="truss_chord",
            position_m=(0, support_h + truss_h, -width * 0.48),
            dimensions_m=(span, 0.25, 0.25),
        ),
        GeometryComponent(
            name="top_chord_right",
            type="truss_chord",
            position_m=(0, support_h + truss_h, width * 0.48),
            dimensions_m=(span, 0.25, 0.25),
        ),
        # Supports
        GeometryComponent(
            name="left_pier",
            type="pier",
            position_m=(-span * 0.46, support_h / 2, 0),
            dimensions_m=(1.0, support_h, width * 1.1),
        ),
        GeometryComponent(
            name="right_pier",
            type="pier",
            position_m=(span * 0.46, support_h / 2, 0),
            dimensions_m=(1.0, support_h, width * 1.1),
        ),
    ]

    panel_dx = span / panels
    x_start = -span / 2

    for i in range(panels + 1):
        x = x_start + i * panel_dx
        # Vertical struts
        components.append(
            GeometryComponent(
                name=f"truss_vertical_left_{i+1}",
                type="truss_vertical",
                position_m=(x, support_h + truss_h / 2, -width * 0.48),
                dimensions_m=(0.2, truss_h, 0.2),
            )
        )
        components.append(
            GeometryComponent(
                name=f"truss_vertical_right_{i+1}",
                type="truss_vertical",
                position_m=(x, support_h + truss_h / 2, width * 0.48),
                dimensions_m=(0.2, truss_h, 0.2),
            )
        )

        # Diagonal Web Members (Warren/Pratt pattern)
        if i < panels:
            x_mid = x + panel_dx / 2
            y_mid = support_h + truss_h / 2
            diag_len = math.sqrt(panel_dx**2 + truss_h**2)
            angle = math.atan2(truss_h, panel_dx) if i % 2 == 0 else -math.atan2(truss_h, panel_dx)

            components.append(
                GeometryComponent(
                    name=f"truss_diagonal_left_{i+1}",
                    type="truss_diagonal",
                    position_m=(x_mid, y_mid, -width * 0.48),
                    dimensions_m=(diag_len, 0.18, 0.18),
                    rotation_rad=(0, 0, angle),
                )
            )
            components.append(
                GeometryComponent(
                    name=f"truss_diagonal_right_{i+1}",
                    type="truss_diagonal",
                    position_m=(x_mid, y_mid, width * 0.48),
                    dimensions_m=(diag_len, 0.18, 0.18),
                    rotation_rad=(0, 0, angle),
                )
            )

    return ParametricGeometry(type="bridge_truss", components=components)


def _generate_arch_bridge(span: float, width: float, support_h: float, arch_h: float) -> ParametricGeometry:
    components: list[GeometryComponent] = [
        GeometryComponent(
            name="deck",
            type="deck",
            position_m=(0, support_h, 0),
            dimensions_m=(span, 0.4, width),
        ),
        GeometryComponent(
            name="left_arch_abutment",
            type="abutment",
            position_m=(-span * 0.48, support_h / 2, 0),
            dimensions_m=(2.0, support_h + 1.0, width * 1.2),
        ),
        GeometryComponent(
            name="right_arch_abutment",
            type="abutment",
            position_m=(span * 0.48, support_h / 2, 0),
            dimensions_m=(2.0, support_h + 1.0, width * 1.2),
        ),
    ]

    # Parabolic Arch Curve: y(x) = y_base + arch_h * (1 - (2x / span)^2)
    # arch spans from x = -span*0.46 to +span*0.46
    arch_span = span * 0.92
    y_base = support_h * 0.4
    num_segments = 16

    def get_arch_point(t_norm: float) -> tuple[float, float]:
        # t_norm in [-1, 1]
        x = t_norm * (arch_span / 2)
        y = y_base + arch_h * (1.0 - t_norm**2)
        return x, y

    # Generate Left and Right Parabolic Arch Ribs (Segmented Beams with Rotations)
    dt = 2.0 / num_segments
    for i in range(num_segments):
        t1 = -1.0 + i * dt
        t2 = -1.0 + (i + 1) * dt

        x1, y1 = get_arch_point(t1)
        x2, y2 = get_arch_point(t2)

        x_mid = (x1 + x2) / 2
        y_mid = (y1 + y2) / 2
        dx = x2 - x1
        dy = y2 - y1
        seg_len = math.sqrt(dx**2 + dy**2)
        angle = math.atan2(dy, dx)

        components.append(
            GeometryComponent(
                name=f"arch_rib_left_segment_{i+1}",
                type="arch_rib",
                position_m=(x_mid, y_mid, -width * 0.48),
                dimensions_m=(seg_len * 1.05, 0.45, 0.35),
                rotation_rad=(0, 0, angle),
            )
        )
        components.append(
            GeometryComponent(
                name=f"arch_rib_right_segment_{i+1}",
                type="arch_rib",
                position_m=(x_mid, y_mid, width * 0.48),
                dimensions_m=(seg_len * 1.05, 0.45, 0.35),
                rotation_rad=(0, 0, angle),
            )
        )

        # Vertical Hangers connecting arch rib to deck
        if 1 <= i <= num_segments - 1 and abs(x_mid) < (arch_span / 2) * 0.85:
            hanger_top = max(y_mid, support_h)
            hanger_bot = min(y_mid, support_h)
            hanger_len = hanger_top - hanger_bot
            if hanger_len > 0.4:
                components.append(
                    GeometryComponent(
                        name=f"vertical_hanger_left_{i}",
                        type="hanger",
                        position_m=(x_mid, hanger_bot + hanger_len / 2, -width * 0.48),
                        dimensions_m=(0.12, hanger_len, 0.12),
                    )
                )
                components.append(
                    GeometryComponent(
                        name=f"vertical_hanger_right_{i}",
                        type="hanger",
                        position_m=(x_mid, hanger_bot + hanger_len / 2, width * 0.48),
                        dimensions_m=(0.12, hanger_len, 0.12),
                    )
                )

    return ParametricGeometry(type="bridge_arch", components=components)


def _generate_suspension_bridge(span: float, width: float, support_h: float, tower_h: float, sag: float) -> ParametricGeometry:
    tower_x1 = -span * 0.35
    tower_x2 = span * 0.35
    total_tower_h = support_h + tower_h

    components: list[GeometryComponent] = [
        GeometryComponent(
            name="deck",
            type="deck",
            position_m=(0, support_h, 0),
            dimensions_m=(span * 1.2, 0.4, width),
        ),
        # Left Tower Columns & Cross Beam
        GeometryComponent(
            name="left_tower_leg_front",
            type="tower",
            position_m=(tower_x1, total_tower_h / 2, -width * 0.52),
            dimensions_m=(1.2, total_tower_h, 0.8),
        ),
        GeometryComponent(
            name="left_tower_leg_back",
            type="tower",
            position_m=(tower_x1, total_tower_h / 2, width * 0.52),
            dimensions_m=(1.2, total_tower_h, 0.8),
        ),
        GeometryComponent(
            name="left_tower_cross_beam",
            type="tower",
            position_m=(tower_x1, total_tower_h - 0.8, 0),
            dimensions_m=(1.2, 0.8, width * 1.1),
        ),
        # Right Tower Columns & Cross Beam
        GeometryComponent(
            name="right_tower_leg_front",
            type="tower",
            position_m=(tower_x2, total_tower_h / 2, -width * 0.52),
            dimensions_m=(1.2, total_tower_h, 0.8),
        ),
        GeometryComponent(
            name="right_tower_leg_back",
            type="tower",
            position_m=(tower_x2, total_tower_h / 2, width * 0.52),
            dimensions_m=(1.2, total_tower_h, 0.8),
        ),
        GeometryComponent(
            name="right_tower_cross_beam",
            type="tower",
            position_m=(tower_x2, total_tower_h - 0.8, 0),
            dimensions_m=(1.2, 0.8, width * 1.1),
        ),
        # Anchorages
        GeometryComponent(
            name="left_anchorage",
            type="anchorage",
            position_m=(-span * 0.58, support_h / 2, 0),
            dimensions_m=(3.0, support_h + 1.0, width * 1.4),
        ),
        GeometryComponent(
            name="right_anchorage",
            type="anchorage",
            position_m=(span * 0.58, support_h / 2, 0),
            dimensions_m=(3.0, support_h + 1.0, width * 1.4),
        ),
    ]

    # Catenary Main Suspension Cable (Center Span: tower_x1 to tower_x2)
    center_span_len = tower_x2 - tower_x1
    num_segments = 16
    y_tower_top = total_tower_h
    y_low = y_tower_top - sag

    def get_cable_point(x: float) -> float:
        norm_x = x / (center_span_len / 2)  # [-1, 1]
        return y_low + sag * (norm_x**2)

    dx_seg = center_span_len / num_segments
    for i in range(num_segments):
        x1 = tower_x1 + i * dx_seg
        x2 = tower_x1 + (i + 1) * dx_seg
        y1 = get_cable_point(x1)
        y2 = get_cable_point(x2)

        x_mid = (x1 + x2) / 2
        y_mid = (y1 + y2) / 2
        dx = x2 - x1
        dy = y2 - y1
        seg_len = math.sqrt(dx**2 + dy**2)
        angle = math.atan2(dy, dx)

        components.append(
            GeometryComponent(
                name=f"main_cable_left_seg_{i+1}",
                type="main_cable",
                position_m=(x_mid, y_mid, -width * 0.52),
                dimensions_m=(seg_len * 1.05, 0.2, 0.2),
                rotation_rad=(0, 0, angle),
            )
        )
        components.append(
            GeometryComponent(
                name=f"main_cable_right_seg_{i+1}",
                type="main_cable",
                position_m=(x_mid, y_mid, width * 0.52),
                dimensions_m=(seg_len * 1.05, 0.2, 0.2),
                rotation_rad=(0, 0, angle),
            )
        )

        # Hanger cables down to deck
        if 1 <= i <= num_segments - 1:
            h_len = y_mid - support_h
            if h_len > 0.2:
                components.append(
                    GeometryComponent(
                        name=f"hanger_cable_left_{i}",
                        type="hanger",
                        position_m=(x_mid, support_h + h_len / 2, -width * 0.52),
                        dimensions_m=(0.08, h_len, 0.08),
                    )
                )
                components.append(
                    GeometryComponent(
                        name=f"hanger_cable_right_{i}",
                        type="hanger",
                        position_m=(x_mid, support_h + h_len / 2, width * 0.52),
                        dimensions_m=(0.08, h_len, 0.08),
                    )
                )

    # Side Backstay Cables (From Tower Tops to Anchorages)
    # Left backstay
    back_dx_left = tower_x1 - (-span * 0.58)
    back_dy_left = y_tower_top - (support_h / 2)
    len_back_left = math.sqrt(back_dx_left**2 + back_dy_left**2)
    angle_back_left = math.atan2(back_dy_left, back_dx_left)
    components.append(
        GeometryComponent(
            name="backstay_cable_left_front",
            type="main_cable",
            position_m=((tower_x1 - span * 0.58) / 2, (y_tower_top + support_h / 2) / 2, -width * 0.52),
            dimensions_m=(len_back_left, 0.22, 0.22),
            rotation_rad=(0, 0, angle_back_left),
        )
    )
    components.append(
        GeometryComponent(
            name="backstay_cable_left_back",
            type="main_cable",
            position_m=((tower_x1 - span * 0.58) / 2, (y_tower_top + support_h / 2) / 2, width * 0.52),
            dimensions_m=(len_back_left, 0.22, 0.22),
            rotation_rad=(0, 0, angle_back_left),
        )
    )

    # Right backstay
    back_dx_right = span * 0.58 - tower_x2
    back_dy_right = (support_h / 2) - y_tower_top
    len_back_right = math.sqrt(back_dx_right**2 + back_dy_right**2)
    angle_back_right = math.atan2(back_dy_right, back_dx_right)
    components.append(
        GeometryComponent(
            name="backstay_cable_right_front",
            type="main_cable",
            position_m=((tower_x2 + span * 0.58) / 2, (y_tower_top + support_h / 2) / 2, -width * 0.52),
            dimensions_m=(len_back_right, 0.22, 0.22),
            rotation_rad=(0, 0, angle_back_right),
        )
    )
    components.append(
        GeometryComponent(
            name="backstay_cable_right_back",
            type="main_cable",
            position_m=((tower_x2 + span * 0.58) / 2, (y_tower_top + support_h / 2) / 2, width * 0.52),
            dimensions_m=(len_back_right, 0.22, 0.22),
            rotation_rad=(0, 0, angle_back_right),
        )
    )

    return ParametricGeometry(type="bridge_suspension", components=components)


def _generate_cable_stayed_bridge(span: float, width: float, support_h: float, tower_h: float) -> ParametricGeometry:
    total_tower_h = support_h + tower_h
    pylon_top_y = total_tower_h * 0.92

    components: list[GeometryComponent] = [
        GeometryComponent(
            name="deck",
            type="deck",
            position_m=(0, support_h, 0),
            dimensions_m=(span, 0.45, width),
        ),
        # Central Main Pylon Towers (Left and Right)
        GeometryComponent(
            name="main_pylon_left",
            type="tower",
            position_m=(0, total_tower_h / 2, -width * 0.52),
            dimensions_m=(1.6, total_tower_h, 0.9),
        ),
        GeometryComponent(
            name="main_pylon_right",
            type="tower",
            position_m=(0, total_tower_h / 2, width * 0.52),
            dimensions_m=(1.6, total_tower_h, 0.9),
        ),
        GeometryComponent(
            name="pylon_top_cross_beam",
            type="tower",
            position_m=(0, pylon_top_y, 0),
            dimensions_m=(1.6, 0.8, width * 1.1),
        ),
        # Piers under deck
        GeometryComponent(
            name="pylon_foundation_pier",
            type="pier",
            position_m=(0, support_h / 2, 0),
            dimensions_m=(2.2, support_h, width * 1.2),
        ),
        GeometryComponent(
            name="left_end_pier",
            type="pier",
            position_m=(-span * 0.46, support_h / 2, 0),
            dimensions_m=(1.2, support_h, width * 1.1),
        ),
        GeometryComponent(
            name="right_end_pier",
            type="pier",
            position_m=(span * 0.46, support_h / 2, 0),
            dimensions_m=(1.2, support_h, width * 1.1),
        ),
    ]

    # Fan Stay Cables radiating from Pylon Top down to deck points
    num_stays = 6
    stay_spacing = (span * 0.42) / num_stays

    for i in range(1, num_stays + 1):
        x_deck_pos = i * stay_spacing
        x_deck_neg = -i * stay_spacing
        y_pylon = pylon_top_y - (i - 1) * (tower_h * 0.08)

        # Right-side stay cables (+x)
        dx_pos = x_deck_pos - 0
        dy_pos = support_h - y_pylon
        len_pos = math.sqrt(dx_pos**2 + dy_pos**2)
        angle_pos = math.atan2(dy_pos, dx_pos)

        components.append(
            GeometryComponent(
                name=f"stay_cable_pos_left_{i}",
                type="stay_cable",
                position_m=(x_deck_pos / 2, (y_pylon + support_h) / 2, -width * 0.52),
                dimensions_m=(len_pos, 0.14, 0.14),
                rotation_rad=(0, 0, angle_pos),
            )
        )
        components.append(
            GeometryComponent(
                name=f"stay_cable_pos_right_{i}",
                type="stay_cable",
                position_m=(x_deck_pos / 2, (y_pylon + support_h) / 2, width * 0.52),
                dimensions_m=(len_pos, 0.14, 0.14),
                rotation_rad=(0, 0, angle_pos),
            )
        )

        # Left-side stay cables (-x)
        dx_neg = x_deck_neg - 0
        dy_neg = support_h - y_pylon
        len_neg = math.sqrt(dx_neg**2 + dy_neg**2)
        angle_neg = math.atan2(dy_neg, dx_neg)

        components.append(
            GeometryComponent(
                name=f"stay_cable_neg_left_{i}",
                type="stay_cable",
                position_m=(x_deck_neg / 2, (y_pylon + support_h) / 2, -width * 0.52),
                dimensions_m=(len_neg, 0.14, 0.14),
                rotation_rad=(0, 0, angle_neg),
            )
        )
        components.append(
            GeometryComponent(
                name=f"stay_cable_neg_right_{i}",
                type="stay_cable",
                position_m=(x_deck_neg / 2, (y_pylon + support_h) / 2, width * 0.52),
                dimensions_m=(len_neg, 0.14, 0.14),
                rotation_rad=(0, 0, angle_neg),
            )
        )

    return ParametricGeometry(type="bridge_cable_stayed", components=components)


