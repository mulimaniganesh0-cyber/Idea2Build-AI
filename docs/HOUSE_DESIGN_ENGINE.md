# House Design Engine API and data flow

## Endpoints

### `POST /api/house/design-options`

Request:

```json
{
  "requirements": {
    "project_id": null,
    "plot_width": 30,
    "plot_length": 40,
    "plot_unit": "ft",
    "floors": 2,
    "bedrooms": 3,
    "bathrooms": 2,
    "style": "modern",
    "interior_style": "modern_luxury",
    "color_palette": "modern_vibrant",
    "climate": {}
  },
  "use_rag": true
}
```

Returns targeted clarification when plot dimensions/area, floors, or bedrooms are missing; otherwise returns requirement data, site analysis, room allocations, options, design reasoning, and RAG provenance.

### `POST /api/house/design-options/select`

Accepts `{ "project_id": "…", "option_id": "modern_tropical" }`. The selected option is applied to house state, saved as a new project/design revision, and used to regenerate viewer components plus canonical house B-Rep report and parametric JSON.

## Deterministic modules

- `backend/app/services/house_design.py`: request schemas, explicit extraction, site analysis, room-area allocation/packing, option generation, palette values, and RAG-based decision mapping.
- `backend/app/services/house.py`: existing natural-language house updates, now supporting roof/style/room-count requirements and design revisions.
- `backend/app/services/house_tree.py`: canonical component tree colors, bedroom furniture counts, balcony choices, parameterized roof dimensions, and optional gutters.
- `backend/app/services/cad.py`: selected-option viewer component generation (presentation geometry).
- `backend/app/services/house_cad.py`: actual OpenCascade structural solid generation and properties.

The House Design Studio form is in `frontend/src/HouseDesignStudio.tsx`. It calls the planning and selection APIs. Model Inspector displays persisted requirements, room allocation, site assumptions, B-Rep metrics, knowledge, and design reasoning.

## Known incomplete engineering work

- Room rectangles are not yet consumed by the scene generator to lay out walls, doors, or windows; their packed fit is not a full architectural collision analysis.
- Furniture collision checks are explicitly NOT_RUN.
- Bathroom/bedroom counts affect decorative viewer objects; room-by-room functional plans, lighting, and detailed furniture placement remain limited.
- Roof type changes currently alter the selected primitive massing, slope, and overhang parameters; the B-Rep roof is not yet a true gable/hip shell.
- The 3D floor-plan view is not yet driven from the same room rectangle records.
- A browser automation suite is not configured, so UI interactions and browser console/network acceptance remain unverified.
