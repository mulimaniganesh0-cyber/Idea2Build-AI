# Intelligent House Design Engine

## Audit and baseline

Baseline on 2026-10-07: 54 backend tests passed (the state-mutating `test_rag_pipeline.py` was excluded); the run used a temporary SQLite database. The frontend already had a procedural house viewer, a persistent project store, Postgres/pgvector retrieval, and a build123d/OpenCascade house B-Rep generator with STEP/STL/OBJ export APIs.

| Area | Classification | Evidence / limit |
|---|---|---|
| Requirement parsing | DETERMINISTIC | `house_design.extract_requirements` records values found explicitly in text. |
| House viewer | DETERMINISTIC / PRESENTATION | Backend parametric component response rendered by Three.js; this is not the engineering-solid authority. |
| House engineering solid | REAL | `house_cad.build_canonical_house_cad` builds and validates OpenCascade solids for structural components. |
| Project persistence | REAL | SQLite project, design, geometry, parametric, CAD report and house-state JSON records. |
| Knowledge retrieval | REAL, conditional | PostgreSQL/pgvector `retrieve`; only called for explicit climate inputs in the House Design Studio. |
| Retrieval-to-decision | DETERMINISTIC, conditional | Retrieved rainfall/roof/drainage/gutter evidence can enable gutter geometry and is recorded with source IDs. |
| Location climate service | NOT AVAILABLE | A place name is stored; no weather provider/geocoder is configured, so no climate values are inferred. |
| Browser E2E | NOT VERIFIED | No browser automation runner is configured in the frontend package. |

## Workflow

1. The House Design Studio sends structured requirements to `POST /api/house/design-options`.
2. Missing plot size, floor count, or bedroom count returns only targeted clarification questions.
3. The deterministic site planner reports plot area and an estimated footprint. Its 75% × 70% footprint factor is explicitly a concept allowance, not a legal setback.
4. The room planner produces per-floor areas and shelf-packed concept rectangles, with a fit/overlap report. It explicitly reports furniture-collision validation as NOT_RUN.
5. Three design option records have different roof, palette, ventilation, and interior parameters. Their option hashes are stored in the project house state.
6. Selection through `POST /api/house/design-options/select` stores the selected option, increments the project/design revision, regenerates the viewer components, builds canonical house B-Rep data, and persists the report and parametric document.

## Requirements and persistence

`HouseRequirements` accepts plot dimensions or area, built-up area, floors, bedrooms, bathrooms, parking, kitchen type, balcony, terrace, architecture/interior style, palette, location, orientation, qualitative user-provided climate conditions, special rooms, budget category, constraints, and preferences. Unknown values stay absent. Existing project prompt facts and previously submitted structured values are merged with subsequent Studio requests.

The existing SQLite `house_states` row stores requirements, site analysis, room allocation, alternatives, selection, reasoning, knowledge provenance, and revision data as JSON. Design and geometry revisions use existing project/design/geometry/parametric/CAD-report tables. No separate migration was needed.

## Geometry boundary

Selecting an option changes house feature parameters and presentation components such as roof dimensions/type, overhang, colors, bedroom/bathroom furniture counts, balcony, parking, gutters, and downpipes. The canonical house CAD builder creates real OpenCascade solids for its structural components and reports actual kernel metrics. It currently approximates roof forms as parametric box solids; it does not create construction-grade gable/hip roof shells. Room rectangles are planning data and are not yet the source of the viewer's wall/door/window layout.

## Safety and estimates

Room area and footprint results are concept-planning estimates. Setbacks are NOT_SPECIFIED; no local regulation is inferred or claimed. Location-specific rainfall and temperature are NOT_AVAILABLE unless supplied as a qualitative user requirement or supported by retrieved material. No structural, code, wind, earthquake, foundation, or drainage compliance is claimed.
