# AI-CAD Engineer — Project Status Report

**Last Updated:** September 2026  
**Status:** Operational & Fully Integrated (Production Build & **27 Pytests** Verified)

## Architectural Overview

AI-CAD Engineer is a prompt-to-CAD engineering workspace allowing users to describe design intents in natural language, receive parametric specifications, and render interactive 3D models in a web viewport with standard Wavefront OBJ export.

```
Frontend (React 18 + Vite + Three.js 0.168)
  ├── App.tsx                    # Engineering Workspace (Sidebar Routing, 4-Column Layout, OBJ Downloader)
  ├── ModelViewport.tsx          # Component-based Three.js 3D Viewer, Rotational Meshes & Edge Outline Engine
  ├── api.ts                     # Typed fetch adapter & dev mode logger
  ├── types.ts                   # Shared TypeScript contracts (ViewMode, GeometryComponent with floor_number/room_id)
  ├── utils/exportObj.ts         # Wavefront OBJ exporter using Three.js OBJExporter
  └── styles.css                 # Dark engineering theme design system (with fullscreen viewer styles)
        │ (HTTP REST / JSON)
Backend (FastAPI 0.115 + Pydantic 2.9 + SQLite)
  ├── app/main.py                # FastAPI routes & CORS middleware
  ├── app/models.py              # Pydantic data schemas, BridgeType, HouseProjectState + view_mode/active_floor
  ├── app/services/
  │   ├── house.py               # Residential house workflow, detect_view_mode_intent, detect_furniture_command
  │   ├── bridge.py              # Bridge concept workflow & type normalization
  │   ├── cad.py                 # Parametric geometry engine (Bridges, Multi-Floor Buildings + Full Interior)
  │   ├── chat.py                # Chat adapter & multi-turn state router
  │   ├── orchestrator.py        # Task graph dependency builder
  │   ├── parser.py              # Deterministic NL primitive parser
  │   └── project_store.py       # SQLite project memory & version history
  └── tests/                     # Pytest suite (27 passed)
        ├── test_api.py          # API endpoint tests (10 tests)
        ├── test_bridge_types.py # 5-Bridge type geometry verification tests (6 tests)
        ├── test_house.py        # Multi-floor architectural house, interior, view mode tests (7 tests)
        └── test_parser.py       # NL prompt parser tests (4 tests)
```

## Supported Workflows & Models

1. **Parametric Bridge Systems (5 Distinct Geometry Engines)**:
   - **Beam / Girder (`beam_girder`)**: Straight deck, longitudinal steel box girders, cross beams, pier columns, and concrete abutments.
   - **Truss (`truss`)**: Top and bottom chords, vertical struts, and diagonal web members forming triangular Warren/Pratt panels.
   - **Arch (`arch`)**: Deck, parabolic segmented arch ribs (left & right), vertical cable hangers connecting arch to deck, and heavy concrete abutment bases.
   - **Suspension (`suspension`)**: Deck, twin main towers (pylons) with cross bracing, catenary main suspension cables, vertical hanger cables, and anchorage blocks.
   - **Cable-Stayed (`cable_stayed`)**: Deck, central A-frame/pylon tower, slanted stay cables radiating to deck edges (fan arrangement), and piers.

2. **Parametric Residential House & Multi-Floor Buildings**:
   - **Standard Definition**: `N floors` = `N` physical vertical levels. `G+2` = Ground floor + 2 upper floors = 3 total physical levels.
   - **Floor Extraction**: Supports natural language expressions like `"Make the building 3 floors"`, `"Build a G+2 house"`, `"Add another floor"`, `"Change it to 4 floors"`, `"I want a ground floor and 2 upper floors"`.
   - **Dynamic Floor Geometry**: Generates exact `N` floor slabs at computed elevations (`base_y = i * floor_h`), 4 corner columns per level, floor wall volumes, front window cutouts, upper-floor balconies, entrance door, top roof slab, and site boundary.
   - **Full Procedural Interior**: Interior partition walls (`interior_wall`) dividing rooms, 3-seater sofa, TV unit, coffee table, L-shaped kitchen counter, dining table with chairs, bathrooms with toilet + basin, multi-step staircase, queen/single beds, wardrobes, and study desks. All components are tagged with `floor_number` and `room_id`.
   - **State Persistence**: Conversational updates preserve site dimensions, building footprint, and parameters while updating floor levels and total height.

3. **View Modes (House Only)**:
   - **Exterior**: Full building exterior rendering with roof and facade visible.
   - **Interior**: Exterior walls and roof hidden; interior rooms and furniture illuminated by interior point lights.
   - **Cutaway**: Exterior walls rendered at 25% opacity to reveal interior layout.
   - **Floor Plan**: Top-down orthographic view with exterior walls and roof hidden.
   - **Floor Level Filtering**: Isolate any individual floor level (L0, L1, L2...) from chat or toolbar buttons.
   - **View Mode NLP**: Commands like `"Show the interior"`, `"Show ground floor plan"`, `"Level 1"`, `"Add a sofa to the bedroom"` are detected and applied automatically.

4. **Fullscreen 3D Inspector** (`#viewer` route):
   - Dedicated fullscreen viewer with full toolbar: View Mode buttons, Floor Selectors, Fit, Reset, Grid, Axes, Download OBJ.
   - HUD overlay showing current mode, active floor, model dimensions, and ESC hint.
   - "← Back to Workspace" button and `ESC` key both return to chat.
   - All viewport state (`viewMode`, `activeFloor`) persisted across chat and fullscreen routes.

5. **Mechanical Primitives**:
   - **Objects**: Shaft, box, cube, cylinder, plate, sphere, cone, hole.
   - **Updates**: Resizing length, width, height, diameter live via conversation.

6. **3D Model OBJ Download**:
   - Built-in Wavefront OBJ export via `utils/exportObj.ts` using Three.js `OBJExporter`.
   - Available in both chat viewport toolbar and fullscreen inspector.
   - Generates descriptive filenames (e.g. `cad_house.obj`, `cad_bridge.obj`).

## Root Cause & Fix Summary

1. **Bridge Geometry Issue**:
   - **Root Cause**: CAD generator ignored bridge type and returned generic deck.
   - **Fix**: Implemented 5 parametric geometry engines with 3D rotation (`rotation_rad`) for angled members.

2. **Floor-Count Synchronization Issue**:
   - **Root Cause**:
     1. `is_house_request` missed `"building"`, causing commands like `"Make the building 3 floors"` to fail matching the house pipeline.
     2. `extract_floor_count` lacked regex support for delta additions (`"add another floor"`), transition phrases (`"from 2 to 3 floors"`), and multi-word numbers.
     3. `HouseProjectState` and frontend spec panel did not track normalized `floor_label` (e.g. `G+2`), upper floor counts, and dynamic slab counts.
   - **Fix**:
     1. Implemented robust `parse_floor_expression` handling absolute, G-notation, transition, and relative delta expressions.
     2. Updated `_generate_house_building_geometry` to dynamically construct `N` floor slabs, columns, walls, windows, and balconies with elevation validation.
     3. Updated frontend spec panel to show total floors, G-notation config, floor height, total height.

3. **Fullscreen 3D Inspector Blank Viewport Issue**:
   - **Root Cause**: `ModelViewport` component was not receiving `viewMode`/`activeFloor` props in the fullscreen route; the canvas container had no explicit height, collapsing to 0px; no exit controls existed.
   - **Fix**:
     - Passed `viewMode`, `activeFloor`, `isLoading`, `error` props to fullscreen `ModelViewport`.
     - Added `fullscreen-canvas-container` with `height: calc(100% - 48px)` CSS.
     - Added `fullscreen-header` toolbar with back button, view modes, floor selectors, OBJ export, and exit button.
     - Added ESC key handler (`useEffect`) to return to chat workspace.
     - Added `fullscreen-hud` overlay with mode, floor, dimensions, and ESC hint.

4. **Missing House Interior**:
   - **Root Cause**: `_generate_house_building_geometry` only generated structural exterior elements (slabs, walls, columns, roof). No interior partition walls or furniture were generated.
   - **Fix**:
     - Ground Floor: Living room (sofa, TV unit, coffee table), Kitchen/Dining (L-counter, dining table + chairs), Bathroom (toilet, basin), Staircase.
     - Floor 1: Master bedroom (queen bed, wardrobe, nightstand), Guest bedroom (single bed, desk), Bathroom.
     - Upper Floors: Study (desk, bookshelf), Extra bedroom, Bathroom.
     - All components tagged with `floor_number` and `room_id` for per-floor filtering.
