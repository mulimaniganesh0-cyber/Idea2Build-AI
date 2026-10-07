"""Canonical House Parametric Component Tree.

Organizes building elements into a rigorous hierarchical engineering tree:
HOUSE
├── SITE (plot, landscape)
├── FOUNDATION (foundation raft/footings)
├── LEVELS (Ground floor, First floor, ...)
│   ├── SLAB
│   ├── COLUMNS
│   ├── BEAMS
│   ├── WALLS (structural & partition)
│   ├── DOORS
│   └── WINDOWS
├── STAIRCASE (flight & landings)
├── BALCONIES (slab & railings)
├── ROOF (structural roof slab/rafters & parapet)
└── NON_STRUCTURAL / DECORATIVE (furniture, fixtures)

Each component has:
- stable component_id
- component_type
- parent_id
- structural flag
- classification (STRUCTURAL, NON_STRUCTURAL, ARCHITECTURAL, DECORATIVE)
- material_id (linked to material_registry)
- level number
- bounding dimensions and positions in SI metres
- dependency chain and construction order
"""

from __future__ import annotations

from enum import Enum
import math
from typing import Any
from pydantic import BaseModel, Field

from app.models import GeometryComponent, HouseProjectState


class ComponentClassification(str, Enum):
    STRUCTURAL = "structural"
    NON_STRUCTURAL = "non_structural"
    ARCHITECTURAL = "architectural"
    DECORATIVE = "decorative"


class HouseComponent(BaseModel):
    component_id: str
    name: str
    component_type: str
    parent_id: str
    level: int = 0
    structural: bool = True
    classification: ComponentClassification = ComponentClassification.STRUCTURAL
    material_id: str = "reinforced_concrete"
    position_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    dimensions_m: tuple[float, float, float] = (1.0, 1.0, 1.0)
    rotation_rad: tuple[float, float, float] = (0.0, 0.0, 0.0)
    material_color: str = "#94a3b8"
    room_id: str | None = None
    enabled: bool = True
    dependencies: list[str] = Field(default_factory=list)
    order_index: int = 0
    parameters: dict[str, Any] = Field(default_factory=dict)

    def to_geometry_component(self) -> GeometryComponent:
        return GeometryComponent(
            name=self.name,
            type=self.component_type,
            component_id=self.component_id,
            structural=self.structural,
            classification=self.classification.value,
            material_id=self.material_id,
            position_m=self.position_m,
            dimensions_m=self.dimensions_m,
            rotation_rad=self.rotation_rad,
            room_id=self.room_id,
            floor_number=self.level if self.level >= 0 else None,
            material_color=self.material_color,
        )


class HouseComponentTree:
    """Canonical parametric component tree for residential buildings."""

    def __init__(self, state: HouseProjectState) -> None:
        self.state = state
        self.components: list[HouseComponent] = []
        self._build_tree()

    def _build_tree(self) -> None:
        state = self.state
        site_w = float(state.site_width_m or (30.0 * 0.3048))
        site_l = float(state.site_length_m or (40.0 * 0.3048))
        b_w = float(state.building_width_m or (site_w * 0.75))
        b_l = float(state.building_length_m or (site_l * 0.70))
        floors = max(1, min(50, state.floors or 2))
        floor_h = float(state.floor_height_m or 3.0)
        roof_type = str(state.roof_type or "pitched").lower()
        palette = {
            "modern_vibrant": {"wall": "#f5f0e6", "accent": "#0f766e", "roof": "#334155", "wood": "#a16207"},
            "warm_luxury": {"wall": "#f3e8d1", "accent": "#9a3412", "roof": "#3f2d20", "wood": "#6b3f24"},
            "contemporary": {"wall": "#f8fafc", "accent": "#64748b", "roof": "#334155", "wood": "#8b5e3c"},
            "tropical": {"wall": "#f5f5e6", "accent": "#166534", "roof": "#9a3412", "wood": "#854d0e"},
        }.get(state.color_palette, {})

        order = 0

        # ── 1. SITE & LANDSCAPING (Decorative) ───────────────────────────────
        self.components.append(
            HouseComponent(
                component_id="site_plot_boundary",
                name="site_boundary",
                component_type="site_plot",
                parent_id="site",
                level=-1,
                structural=False,
                classification=ComponentClassification.DECORATIVE,
                material_id="masonry",
                position_m=(0.0, 0.05, 0.0),
                dimensions_m=(b_w * 1.30, 0.10, b_l * 1.30),
                material_color="#1e293b",
                order_index=order,
            )
        )
        order += 1

        # ── 2. FOUNDATION (Structural) ───────────────────────────────────────
        # Raft slab foundation distributing building loads to soil
        foundation_depth = 0.50  # 500 mm reinforced concrete raft foundation
        foundation_y = 0.0
        self.components.append(
            HouseComponent(
                component_id="foundation_raft",
                name="foundation_raft",
                component_type="foundation",
                parent_id="foundation",
                level=-1,
                structural=True,
                classification=ComponentClassification.STRUCTURAL,
                material_id="reinforced_concrete",
                position_m=(0.0, foundation_y - (foundation_depth / 2), 0.0),
                dimensions_m=(b_w * 1.05, foundation_depth, b_l * 1.05),
                material_color="#334155",
                dependencies=[],
                order_index=order,
                parameters={"thickness_m": foundation_depth, "type": "raft_mat_foundation"},
            )
        )
        order += 1

        # Structural column dimensions (350 mm x 350 mm RC columns)
        col_w = 0.35
        col_h = floor_h - 0.30  # Height between slabs minus beam depth
        cx = (b_w / 2) - (col_w / 2)
        cz = (b_l / 2) - (col_w / 2)
        corner_offsets = [(-cx, cz), (cx, cz), (-cx, -cz), (cx, -cz)]
        corner_names = ["fl_left", "fl_right", "bl_left", "bl_right"]

        # Beam dimensions (300 mm wide x 350 mm deep RC tie beams)
        beam_w = 0.30
        beam_d = 0.35

        for i in range(floors):
            base_y = i * floor_h
            floor_parent_id = f"floor_{i}"

            # ── 3. FLOOR SLABS (Structural) ───────────────────────────────────
            slab_thick = 0.30  # 300 mm two-way RC floor slab
            slab_id = f"slab_level_{i}"
            slab_deps = ["foundation_raft"] if i == 0 else [f"column_l{i-1}_{name}" for name in corner_names]
            self.components.append(
                HouseComponent(
                    component_id=slab_id,
                    name=f"floor_slab_{i+1}",
                    component_type="floor_slab",
                    parent_id=floor_parent_id,
                    level=i,
                    structural=True,
                    classification=ComponentClassification.STRUCTURAL,
                    material_id="reinforced_concrete",
                    position_m=(0.0, base_y + (slab_thick / 2), 0.0),
                    dimensions_m=(b_w * 1.02, slab_thick, b_l * 1.02),
                    material_color="#475569",
                    dependencies=slab_deps,
                    order_index=order,
                    parameters={"slab_thickness_m": slab_thick, "reinforcement_grade": "Fe500"},
                )
            )
            order += 1

            # ── 4. COLUMNS (Structural) ───────────────────────────────────────
            col_y = base_y + slab_thick + (col_h / 2)
            col_ids = []
            for c_idx, ((col_x, col_z), c_name) in enumerate(zip(corner_offsets, corner_names)):
                col_id = f"column_l{i}_{c_name}"
                col_ids.append(col_id)
                self.components.append(
                    HouseComponent(
                        component_id=col_id,
                        name=f"column_fl{i+1}_{c_idx+1}",
                        component_type="column",
                        parent_id=floor_parent_id,
                        level=i,
                        structural=True,
                        classification=ComponentClassification.STRUCTURAL,
                        material_id="reinforced_concrete",
                        position_m=(col_x, col_y, col_z),
                        dimensions_m=(col_w, col_h, col_w),
                        material_color="#334155",
                        dependencies=[slab_id],
                        order_index=order,
                        parameters={"width_m": col_w, "depth_m": col_w, "height_m": col_h},
                    )
                )
                order += 1

            # ── 5. PERIMETER BEAMS (Structural) ───────────────────────────────
            beam_y = base_y + floor_h - (beam_d / 2)
            # Front perimeter beam
            self.components.append(
                HouseComponent(
                    component_id=f"beam_front_l{i}",
                    name=f"beam_front_fl{i+1}",
                    component_type="beam",
                    parent_id=floor_parent_id,
                    level=i,
                    structural=True,
                    classification=ComponentClassification.STRUCTURAL,
                    material_id="reinforced_concrete",
                    position_m=(0.0, beam_y, cz),
                    dimensions_m=(b_w - col_w, beam_d, beam_w),
                    material_color="#3b4252",
                    dependencies=col_ids,
                    order_index=order,
                )
            )
            order += 1
            # Back perimeter beam
            self.components.append(
                HouseComponent(
                    component_id=f"beam_back_l{i}",
                    name=f"beam_back_fl{i+1}",
                    component_type="beam",
                    parent_id=floor_parent_id,
                    level=i,
                    structural=True,
                    classification=ComponentClassification.STRUCTURAL,
                    material_id="reinforced_concrete",
                    position_m=(0.0, beam_y, -cz),
                    dimensions_m=(b_w - col_w, beam_d, beam_w),
                    material_color="#3b4252",
                    dependencies=col_ids,
                    order_index=order,
                )
            )
            order += 1

            # ── 6. STRUCTURAL EXTERIOR WALLS (Structural / Enclosure) ─────────
            wall_h = floor_h - slab_thick
            self.components.append(
                HouseComponent(
                    component_id=f"wall_ext_l{i}",
                    name=f"floor_walls_{i+1}",
                    component_type="wall_volume",
                    parent_id=floor_parent_id,
                    level=i,
                    structural=True,
                    classification=ComponentClassification.STRUCTURAL,
                    material_id="masonry",
                    position_m=(0.0, base_y + slab_thick + (wall_h / 2), 0.0),
                    dimensions_m=(b_w, wall_h, b_l),
                    material_color=palette.get("wall", "#f8fafc"),
                    dependencies=[slab_id],
                    order_index=order,
                )
            )
            order += 1

            # ── 7. WINDOWS (Non-structural glazing) ───────────────────────────
            self.components.append(
                HouseComponent(
                    component_id=f"window_front_left_l{i}",
                    name=f"window_front_{i+1}_left",
                    component_type="window",
                    parent_id=floor_parent_id,
                    level=i,
                    structural=False,
                    classification=ComponentClassification.NON_STRUCTURAL,
                    material_id="glass",
                    position_m=(-b_w * 0.25, base_y + (floor_h * 0.55), (b_l / 2) + 0.05),
                    dimensions_m=(b_w * 0.25, 1.20, 0.10),
                    material_color=palette.get("accent", "#38bdf8"),
                    dependencies=[f"wall_ext_l{i}"],
                    order_index=order,
                )
            )
            order += 1
            self.components.append(
                HouseComponent(
                    component_id=f"window_front_right_l{i}",
                    name=f"window_front_{i+1}_right",
                    component_type="window",
                    parent_id=floor_parent_id,
                    level=i,
                    structural=False,
                    classification=ComponentClassification.NON_STRUCTURAL,
                    material_id="glass",
                    position_m=(b_w * 0.25, base_y + (floor_h * 0.55), (b_l / 2) + 0.05),
                    dimensions_m=(b_w * 0.25, 1.20, 0.10),
                    material_color=palette.get("accent", "#38bdf8"),
                    dependencies=[f"wall_ext_l{i}"],
                    order_index=order,
                )
            )
            order += 1

            # ── 8. BALCONIES (Upper floors) ──────────────────────────────────
            if i >= 1 and state.balcony:
                # Balcony RC cantilever slab (Structural)
                balcony_slab_id = f"balcony_slab_l{i}"
                self.components.append(
                    HouseComponent(
                        component_id=balcony_slab_id,
                        name=f"balcony_fl{i+1}",
                        component_type="balcony",
                        parent_id=floor_parent_id,
                        level=i,
                        structural=True,
                        classification=ComponentClassification.STRUCTURAL,
                        material_id="reinforced_concrete",
                        position_m=(0.0, base_y + 0.30, (b_l / 2) + 0.50),
                        dimensions_m=(b_w * 0.55, 0.20, 1.00),
                        material_color="#64748b",
                        dependencies=[slab_id],
                        order_index=order,
                    )
                )
                order += 1
                # Balcony safety railing (Non-structural glass/steel)
                self.components.append(
                    HouseComponent(
                        component_id=f"balcony_railing_l{i}",
                        name=f"balcony_railing_fl{i+1}",
                        component_type="railing",
                        parent_id=floor_parent_id,
                        level=i,
                        structural=False,
                        classification=ComponentClassification.NON_STRUCTURAL,
                        material_id="structural_steel",
                        position_m=(0.0, base_y + 0.90, (b_l / 2) + 0.95),
                        dimensions_m=(b_w * 0.55, 1.00, 0.05),
                        material_color="#94a3b8",
                        dependencies=[balcony_slab_id],
                        order_index=order,
                    )
                )
                order += 1

            # ── 9. INTERIOR PARTITION WALLS (Non-structural) ─────────────────
            self.components.append(
                HouseComponent(
                    component_id=f"wall_center_l{i}",
                    name=f"wall_center_fl{i+1}",
                    component_type="interior_wall",
                    parent_id=floor_parent_id,
                    level=i,
                    structural=False,
                    classification=ComponentClassification.NON_STRUCTURAL,
                    material_id="masonry",
                    position_m=(0.0, base_y + (wall_h / 2) + 0.15, -b_l * 0.05),
                    dimensions_m=(0.15, wall_h, b_l * 0.70),
                    material_color="#e2e8f0",
                    room_id=f"hallway_{i}",
                    dependencies=[slab_id],
                    order_index=order,
                )
            )
            order += 1
            self.components.append(
                HouseComponent(
                    component_id=f"wall_trans_left_l{i}",
                    name=f"wall_transverse_left_fl{i+1}",
                    component_type="interior_wall",
                    parent_id=floor_parent_id,
                    level=i,
                    structural=False,
                    classification=ComponentClassification.NON_STRUCTURAL,
                    material_id="masonry",
                    position_m=(-b_w * 0.24, base_y + (wall_h / 2) + 0.15, 0.0),
                    dimensions_m=(b_w * 0.46, wall_h, 0.15),
                    material_color="#e2e8f0",
                    room_id=f"left_partition_{i}",
                    dependencies=[slab_id],
                    order_index=order,
                )
            )
            order += 1
            self.components.append(
                HouseComponent(
                    component_id=f"wall_trans_right_l{i}",
                    name=f"wall_transverse_right_fl{i+1}",
                    component_type="interior_wall",
                    parent_id=floor_parent_id,
                    level=i,
                    structural=False,
                    classification=ComponentClassification.NON_STRUCTURAL,
                    material_id="masonry",
                    position_m=(b_w * 0.24, base_y + (wall_h / 2) + 0.15, -b_l * 0.16),
                    dimensions_m=(b_w * 0.46, wall_h, 0.15),
                    material_color="#e2e8f0",
                    room_id=f"right_partition_{i}",
                    dependencies=[slab_id],
                    order_index=order,
                )
            )
            order += 1

            # ── 10. PROCEDURAL INTERIOR FURNITURE (Decorative) ───────────────
            if i == 0:
                # Ground floor living room furniture
                self.components.extend([
                    HouseComponent(
                        component_id="sofa_living_0",
                        name="sofa_living_0",
                        component_type="furniture_sofa",
                        parent_id=floor_parent_id,
                        level=0,
                        structural=False,
                        classification=ComponentClassification.DECORATIVE,
                        material_id="structural_timber",
                        position_m=(-b_w * 0.25, base_y + 0.65, b_l * 0.22),
                        dimensions_m=(2.20, 0.70, 0.90),
                        material_color="#1e3a8a",
                        room_id="living_room_0",
                        order_index=order,
                    ),
                    HouseComponent(
                        component_id="coffee_table_0",
                        name="coffee_table_0",
                        component_type="furniture_table",
                        parent_id=floor_parent_id,
                        level=0,
                        structural=False,
                        classification=ComponentClassification.DECORATIVE,
                        material_id="structural_timber",
                        position_m=(-b_w * 0.25, base_y + 0.45, b_l * 0.08),
                        dimensions_m=(1.10, 0.40, 0.60),
                        material_color="#78350f",
                        room_id="living_room_0",
                        order_index=order + 1,
                    ),
                    HouseComponent(
                        component_id="tv_unit_0",
                        name="tv_unit_0",
                        component_type="furniture_tv_unit",
                        parent_id=floor_parent_id,
                        level=0,
                        structural=False,
                        classification=ComponentClassification.DECORATIVE,
                        material_id="structural_timber",
                        position_m=(-b_w * 0.42, base_y + 0.70, b_l * 0.12),
                        dimensions_m=(0.40, 0.90, 1.60),
                        material_color="#0f172a",
                        room_id="living_room_0",
                        order_index=order + 2,
                    ),
                    HouseComponent(
                        component_id="kitchen_counter_0",
                        name="kitchen_counter_0",
                        component_type="furniture_counter",
                        parent_id=floor_parent_id,
                        level=0,
                        structural=False,
                        classification=ComponentClassification.DECORATIVE,
                        material_id="structural_timber",
                        position_m=(-b_w * 0.28, base_y + 0.60, -b_l * 0.32),
                        dimensions_m=(2.20, 0.85, 0.65),
                        material_color="#475569",
                        room_id="kitchen_dining_0",
                        order_index=order + 3,
                    ),
                    HouseComponent(
                        component_id="dining_table_0",
                        name="dining_table_0",
                        component_type="furniture_table",
                        parent_id=floor_parent_id,
                        level=0,
                        structural=False,
                        classification=ComponentClassification.DECORATIVE,
                        material_id="structural_timber",
                        position_m=(-b_w * 0.22, base_y + 0.60, -b_l * 0.14),
                        dimensions_m=(1.50, 0.75, 0.85),
                        material_color="#92400e",
                        room_id="kitchen_dining_0",
                        order_index=order + 4,
                    ),
                ])
                order += 5

            # Bedroom furniture count follows the explicitly selected requirement.
            for bed_index in range(state.bedrooms):
                bed_floor = bed_index % floors
                if bed_floor != i: continue
                x_offset = -0.22 if bed_index % 2 == 0 else 0.22
                self.components.append(HouseComponent(
                    component_id=f"bed_{bed_index+1}_f{i}", name=f"bedroom_{bed_index+1}_bed",
                    component_type="furniture_bed", parent_id=floor_parent_id, level=i,
                    structural=False, classification=ComponentClassification.DECORATIVE,
                    material_id="structural_timber", position_m=(b_w * x_offset, base_y + 0.30, -b_l * 0.30),
                    dimensions_m=(1.60, 0.45, 2.00), material_color=palette.get("wood", "#854d0e"),
                    room_id=f"bedroom_{bed_index+1}_{i}", order_index=order,
                    parameters={"interior_style": state.interior_style},
                ))
                order += 1

            # ── 11. INTERIOR STAIRCASE (Structural RC staircase) ─────────────
            if i < floors - 1:
                stair_id = f"staircase_flight_l{i}"
                self.components.append(
                    HouseComponent(
                        component_id=stair_id,
                        name=f"staircase_fl{i+1}",
                        component_type="staircase",
                        parent_id="staircase",
                        level=i,
                        structural=True,
                        classification=ComponentClassification.STRUCTURAL,
                        material_id="reinforced_concrete",
                        position_m=(b_w * 0.35, base_y + (floor_h / 2), 0.0),
                        dimensions_m=(1.10, floor_h, 2.80),
                        material_color="#64748b",
                        dependencies=[slab_id],
                        order_index=order,
                    )
                )
                order += 1

        # ── 12. ROOF STRUCTURE (Structural & Architectural) ───────────────────
        roof_base_y = floors * floor_h
        if roof_type in ("pitched", "gable", "hip", "single_slope"):
            roof_h = max(0.3, min(3.0, math.tan(math.radians(state.roof_slope_deg)) * (b_w / 2)))
            overhang = max(0.0, state.roof_overhang_mm / 1000.0)
            self.components.append(
                HouseComponent(
                    component_id=f"roof_structure_{roof_type}",
                    name=f"roof_{roof_type}",
                    component_type=f"roof_{roof_type}",
                    parent_id="roof",
                    level=99,
                    structural=True,
                    classification=ComponentClassification.STRUCTURAL,
                    material_id="reinforced_concrete",
                    position_m=(0.0, roof_base_y + (roof_h / 2), 0.0),
                    dimensions_m=(b_w + 2 * overhang, roof_h, b_l + 2 * overhang),
                    material_color=palette.get("roof", "#b45309"),
                    dependencies=[f"slab_level_{floors-1}"],
                    order_index=order,
                    parameters={"pitch_angle_deg": state.roof_slope_deg, "overhang_mm": state.roof_overhang_mm, "roof_type": roof_type},
                )
            )
            order += 1
        else:
            # Flat terrace roof slab (Structural)
            self.components.append(
                HouseComponent(
                    component_id="roof_slab_flat",
                    name="roof_flat_slab",
                    component_type="roof_slab",
                    parent_id="roof",
                    level=99,
                    structural=True,
                    classification=ComponentClassification.STRUCTURAL,
                    material_id="reinforced_concrete",
                    position_m=(0.0, roof_base_y + 0.15, 0.0),
                    dimensions_m=(b_w * 1.04, 0.30, b_l * 1.04),
                    material_color="#334155",
                    dependencies=[f"slab_level_{floors-1}"],
                    order_index=order,
                    parameters={"roof_type": "flat_terrace"},
                )
            )
            order += 1

        if state.gutters:
            for side, z in (("front", b_l / 2 + state.roof_overhang_mm / 1000), ("rear", -b_l / 2 - state.roof_overhang_mm / 1000)):
                self.components.append(HouseComponent(
                    component_id=f"gutter_{side}", name=f"roof_gutter_{side}", component_type="gutter",
                    parent_id="roof", level=99, structural=False,
                    classification=ComponentClassification.ARCHITECTURAL,
                    material_id="structural_steel", position_m=(0, roof_base_y, z),
                    dimensions_m=(b_w + state.roof_overhang_mm / 500, 0.08, 0.08),
                    material_color=palette.get("accent", "#64748b"), order_index=order,
                    parameters={"rainfall_design_guidance": "concept_only"},
                ))
                order += 1
            # Roof parapet wall (Architectural)
            self.components.append(
                HouseComponent(
                    component_id="roof_parapet",
                    name="roof_parapet_wall",
                    component_type="parapet",
                    parent_id="roof",
                    level=99,
                    structural=False,
                    classification=ComponentClassification.ARCHITECTURAL,
                    material_id="masonry",
                    position_m=(0.0, roof_base_y + 0.75, 0.0),
                    dimensions_m=(b_w * 1.04, 0.90, b_l * 1.04),
                    material_color="#64748b",
                    dependencies=["roof_slab_flat"],
                    order_index=order,
                )
            )
            order += 1

    def get_components(self) -> list[HouseComponent]:
        return self.components

    def get_structural_components(self) -> list[HouseComponent]:
        return [c for c in self.components if c.structural]

    def get_non_structural_components(self) -> list[HouseComponent]:
        return [c for c in self.components if not c.structural]

    def to_geometry_components(self) -> list[GeometryComponent]:
        return [c.to_geometry_component() for c in self.components]
