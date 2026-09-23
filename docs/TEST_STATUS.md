# AI-CAD Engineer — Test & Verification Status Report

**Last Verified:** September 2026 (Session: Interior + Fullscreen Viewer)  
**Test Coverage:** Backend (**27 / 27 passed**), Frontend (Production Build Succeeded)

## Test Execution Results

### 1. Backend Automated Tests (Pytest)

Command executed:
`cd backend; $env:PYTHONPATH="."; .\.venv\Scripts\pytest.exe -v`

```text
============================= test session starts =============================
platform win32 -- Python 3.13.15, pytest-8.4.2, pluggy-1.6.0
rootdir: D:\AI-CAD-Engineer\backend
plugins: anyio-4.15.1
collected 27 items

tests/test_api.py::test_health PASSED                                    [  3%]
tests/test_api.py::test_parse_endpoint PASSED                            [  7%]
tests/test_api.py::test_project_analysis_is_versioned PASSED             [ 11%]
tests/test_api.py::test_chat_creates_and_updates_a_model PASSED          [ 14%]
tests/test_api.py::test_chat_generates_a_shaft PASSED                    [ 18%]
tests/test_api.py::test_chat_creates_cube_and_modifies_all_edges PASSED  [ 22%]
tests/test_api.py::test_create_is_not_mistaken_for_modify_when_project_exists PASSED [ 25%]
tests/test_api.py::test_cylinder_generation_contract PASSED              [ 29%]
tests/test_api.py::test_bridge_context_is_not_sent_to_primitive_handler PASSED [ 33%]
tests/test_api.py::test_bridge_concept_and_deck_width_update PASSED      [ 37%]
tests/test_bridge_types.py::test_beam_girder_bridge_generation PASSED    [ 40%]
tests/test_bridge_types.py::test_truss_bridge_generation PASSED          [ 44%]
tests/test_bridge_types.py::test_arch_bridge_generation PASSED           [ 48%]
tests/test_bridge_types.py::test_suspension_bridge_generation PASSED     [ 51%]
tests/test_bridge_types.py::test_cable_stayed_bridge_generation PASSED   [ 55%]
tests/test_bridge_types.py::test_all_bridge_geometries_are_distinct PASSED [ 59%]
tests/test_house.py::test_is_house_request_detection PASSED              [ 62%]
tests/test_house.py::test_extract_site_and_floors PASSED                 [ 66%]
tests/test_house.py::test_floor_parsing_variations PASSED                [ 70%]
tests/test_house.py::test_building_geometry_slab_count_and_elevations PASSED [ 74%]
tests/test_house.py::test_chat_multi_turn_conversational_modifications PASSED [ 77%]
tests/test_house.py::test_house_interior_procedural_components PASSED    [ 81%]
tests/test_house.py::test_view_mode_and_furniture_chat_intents PASSED    [ 85%]
tests/test_parser.py::test_parses_metric_box PASSED                      [ 88%]
tests/test_parser.py::test_rejects_missing_unit PASSED                   [ 92%]
tests/test_parser.py::test_rejects_unsupported_object PASSED             [ 96%]
tests/test_parser.py::test_parses_steel_shaft PASSED                     [100%]

======================== 27 passed, 2 warnings in 0.87s ========================
```

---

### 2. Frontend Automated Build (TypeScript + Vite)

Command executed:
`cd frontend; npm run build`

```text
> ai-cad-engineer-web@0.1.0 build
> tsc.cmd -b && vite.cmd build

vite v5.4.21 building for production...
transforming...
✓ 37 modules transformed.
rendering chunks...
dist/index.html                   0.45 kB │ gzip:   0.29 kB
dist/assets/index-BSMaY2Bn.css   16.84 kB │ gzip:   3.71 kB
dist/assets/index-DWr94aBH.js   679.31 kB │ gzip: 181.44 kB
✓ built in 2.05s
```

---

### 3. House Floor Count & Multi-Turn Verification Matrix

| Step | User Prompt | Detected Floors | Floor Config | Slab Count | Total Height | Status |
|---|---|---|---|---|---|---|
| **Turn 1** | `"Design a house for a 30x40 site with 2 floors"` | 2 | G+1 | 2 slabs | 7.2 m | ✅ **VERIFIED** |
| **Turn 2** | `"Make the building 3 floors"` | 3 | G+2 | 3 slabs | 10.2 m | ✅ **VERIFIED** |
| **Turn 3** | `"Add another floor"` | 4 | G+3 | 4 slabs | 13.2 m | ✅ **VERIFIED** |
| **Turn 4** | `"Change it to 2 floors"` | 2 | G+1 | 2 slabs | 7.2 m | ✅ **VERIFIED** |

---

### 4. Bridge Type Geometry Verification Matrix

| Bridge Type | Test Prompt | Generated Components | Rotational Members | Bounding Box & Status |
|---|---|---|---|---|
| **Beam / Girder** | `"Design a 50 m beam bridge, 3m wide"` | `deck`, `left_girder`, `right_girder`, `left_abutment`, `right_abutment`, `cross_beam_1..6`, `center_pier` | No | VERIFIED (`beam_girder`) |
| **Truss** | `"Design a 50 m truss bridge, 3m wide"` | `deck`, `bottom_chord_left/right`, `top_chord_left/right`, `truss_vertical_1..7`, `truss_diagonal_1..6`, `left_pier`, `right_pier` | Yes (`rotation_rad`) | VERIFIED (`truss`) |
| **Arch** | `"Design a 50 m arch bridge with arch height of 8m"` | `deck`, `arch_rib_left_segment_1..16`, `arch_rib_right_segment_1..16`, `vertical_hanger_left/right_1..14`, `left_arch_abutment`, `right_arch_abutment` | Yes (`rotation_rad`) | VERIFIED (`arch`) |
| **Suspension** | `"Design a 50 m suspension bridge with tower height of 12m"` | `deck`, `left_tower_leg_front/back`, `right_tower_leg_front/back`, `tower_cross_beam`, `main_cable_left/right_seg_1..16`, `hanger_cable_left/right`, `left/right_anchorage`, `backstay_cable` | Yes (`rotation_rad`) | VERIFIED (`suspension`) |
| **Cable-Stayed** | `"Design a 50 m cable-stayed bridge with tower height of 12m"` | `deck`, `main_pylon_left/right`, `pylon_top_cross_beam`, `pylon_foundation_pier`, `left/right_end_pier`, `stay_cable_pos/neg_left/right_1..6` | Yes (`rotation_rad`) | VERIFIED (`cable_stayed`) |

---

### 5. Interior Generation Test Matrix

| Component Type | Test | Status |
|---|---|---|
| `interior_wall` | Partition walls dividing rooms on each floor | ✅ PASS |
| `furniture_sofa` | 3-seater sofa in ground floor living room | ✅ PASS |
| `furniture_bed` | Queen/single beds on upper floors | ✅ PASS |
| `furniture_counter` | L-shaped kitchen counter on ground floor | ✅ PASS |
| `furniture_table` | Dining table + study desks | ✅ PASS |
| `furniture_chair` | Dining chairs | ✅ PASS |
| `furniture_sanitary` | Toilet + wash basin in each bathroom | ✅ PASS |
| `staircase` | 6-step staircase for multi-storey houses | ✅ PASS |
| `floor_number` metadata | All interior comps tagged with floor level | ✅ PASS |
| `room_id` metadata | All interior comps tagged with room ID | ✅ PASS |

---

### 6. View Mode & Chat Intent Test Matrix

| User Command | Expected Result | Status |
|---|---|---|
| `"Show the interior layout"` | `view_mode = "interior"` | ✅ PASS |
| `"Show ground floor only"` | `active_floor = 0` | ✅ PASS |
| `"Show level 1 floor plan"` | `active_floor = 1, view_mode = "floor_plan"` | ✅ PASS |
| `"Add a desk to the bedroom"` | Desk component added to geometry | ✅ PASS |

---

### 7. Fullscreen 3D Inspector

| Feature | Status |
|---|---|
| Fullscreen viewer route (`#viewer`) | ✅ IMPLEMENTED |
| "← Back to Workspace" button | ✅ IMPLEMENTED |
| ESC key exits fullscreen | ✅ IMPLEMENTED |
| View Mode buttons (Exterior / Interior / Cutaway / Floor Plan) | ✅ IMPLEMENTED |
| Floor selector buttons (All / L0 / L1 / ...) | ✅ IMPLEMENTED |
| Camera controls (Fit, Reset, Grid, Axes) | ✅ IMPLEMENTED |
| "💾 Download OBJ" — Wavefront OBJ export | ✅ IMPLEMENTED |
| HUD overlay (mode, floor, dimensions, ESC hint) | ✅ IMPLEMENTED |
| `viewMode` and `activeFloor` passed to `ModelViewport` | ✅ IMPLEMENTED |
| Canvas fills entire viewport (no blank screen) | ✅ IMPLEMENTED |
