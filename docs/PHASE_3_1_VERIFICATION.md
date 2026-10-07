# Phase 3.1 verification record

Run on 2026-10-07 against the current local project checkout and configured services.

## Initial audit

| Path | Implementation type | Evidence / boundary |
|---|---|---|
| Frontend requirements form | Real UI | `HouseDesignStudio.tsx` posts structured requirements and `use_rag` to the house design options API. The chat prompt itself still follows the older chat path. |
| Requirement extraction and merge | Deterministic | `extract_requirements`, request merge in `main.py`, and `merge_requirements` preserve explicit state; no LLM is used by this planner. |
| Site and room planning | Deterministic estimate | Uses explicit plot/floor/room values and labeled area/setback assumptions. Room rectangles are shelf-packed. No building-code claim. |
| Alternatives | Deterministic templates | Three option templates have distinct structured parameters (roof, palette, ventilation/interior choices); not three independently generated plans. |
| House RAG | Live pgvector retrieval | Uses Ollama `nomic-embed-text` (768 dimensions), PostgreSQL/pgvector, and the indexed local corpus. Retrieved chunks feed a deterministic text predicate in `create_design_options`; they do not reach Ollama because that planner does not call a chat model. |
| Selection and persistence | Real backend | Selection copies option parameters into `HouseProjectState`, writes state/version/geometry/report, then builds a canonical OpenCascade model. Existing API test exercises the route with isolated SQLite. |
| Canonical CAD | Real OpenCascade solids | `build_canonical_house_cad` builds valid box solids for structural components and reports B-Rep topology/metrics. This does not make the roof shells true pitched roof surfaces. |
| Viewer geometry | Analytic presentation components | Viewer components are separate from the canonical solid compound; do not treat them as engineering B-Rep. |
| Room/furniture clashes | Not implemented | Planner reports `furniture_collision_check: NOT_RUN`; no room-wall/door/furniture collision solver exists. |
| Climate | Qualitative/user supplied | No live weather source. Missing values remain unspecified. |
| Browser automation | Manual local browser check only | No Playwright/Puppeteer/Selenium runner is installed/configured. A browser session exposed and helped fix a `ModelInspector` render crash, but did not complete the whole requirements-to-reload scenario. |

## RAG pipeline test

The previously excluded `backend/tests/test_rag_pipeline.py` was run unchanged. It passed **12 tests in 76.68 s** against live local Ollama and PostgreSQL/pgvector. Its external service calls explain why it was excluded from the earlier fast suite; it was not stale or failing. The final full backend suite, including it and the new rectangle validator tests, passed **75 tests in 90.42 s**. Project SQLite state was isolated in a temporary database for that run. The RAG tests themselves exercise the configured external PostgreSQL corpus and local Ollama.

The RAG pipeline test inserts a `unit_test` document without deleting it; retrieval filters `source='unit_test'`, so it cannot become a retrieval result. No change was made to that existing test.

## Live house RAG and A/B evidence

PostgreSQL health: reachable; pgvector enabled; 18 indexed documents and 59 indexed chunks before the temporary marker check.

Same requirement input in both runs: 1,200 sq ft, two floors, three bedrooms, two bathrooms, `rainfall_class=high`.

| Field | RAG disabled | RAG enabled |
|---|---|---|
| Retrieval | Not requested | `FOUND`, pgvector, `nomic-embed-text:latest`, 768 dimensions, top 4, 0.35 similarity threshold, 2,500 ms trace |
| Retrieved source | None | `residential_building_reference.txt`, chunks 50/40/51/44, similarity 0.6487/0.6452/0.6275/0.6062 |
| Context hash | SHA-256 prefix `e3b0c44298fc1c14` (empty context) | SHA-256 prefix `92b0a445b2cc77a1` |
| Climate option roof | gable, 25° slope, 750 mm overhang | Same; these values came from explicit high-rainfall input, not retrieved context |
| Gutters / drainage | false / true | true / true; retrieved chunk text matched the planner's drainage predicate |
| Canonical tree components | 38 | 41 |
| Canonical structural solids | 19 | 19 |
| Canonical B-Rep geometry hash | `cfe98d405f4a4400` | `cfe98d405f4a4400` |
| Canonical B-Rep bounds | Same | Same |

Conclusion: **real retrieval is verified** and retrieved text changes the deterministic option's gutter parameter and component tree. **RAG-to-structural-B-Rep geometry is not verified**: the canonical solid hash, solid count, and bounds do not change. The roof result is not attributable to retrieval because explicit rainfall input already selects gable/25°/750 mm. The current distinction is significant: gutters are non-structural tree components and do not enter the canonical B-Rep compound.

## Temporary real marker check

Indexed `RAG_TEST_MARKER_HOUSE_ABC123` as a one-chunk temporary PostgreSQL document, ran house planning through actual `retrieve()`, and confirmed:

- real retrieval returned document 20 / chunk 64 at similarity 0.8611;
- marker text appeared in the source content consumed by `create_design_options`;
- planner reasoning cited chunk 64 and selected `gutters=true`;
- temporary document was deleted in a `finally` block (PostgreSQL cascade removed its chunk).

This confirms the marker reached the deterministic house planner. It does not show an Ollama planner handoff; there is no such handoff in the current house planner.

## Room rectangle validation

Added deterministic axis-aligned rectangle checks for invalid dimensions, estimated-envelope bounds, and pairwise room overlap. `allocate_rooms` now reports overlap and envelope status separately. Passing living-room, bedroom, and kitchen rectangle fixtures pass; a fixture with a bed/wardrobe intersection and an item outside the envelope reports both error kinds. The first full-suite run exposed that the 30 × 40 ft concept allocation places the staircase beyond the estimated floor envelope; the allocator now reports `boundary_check=ERROR` and `fit_check=WARNING` instead of incorrectly claiming a fit. This is a concept-level room-box check only. Furniture checks in fixtures prove the rectangle function, not that the planner creates real furniture placements. Wall/door and furniture validation remain unimplemented.

## Live project persistence and selection

The local browser chat created project `a4c30d45-9478-43e4-b6ff-341d137bd765`. Readback from the checkout's SQLite store confirmed its plan, house requirements, `options_ready` state, room/site estimates, RAG trace and provenance, version-1 viewer geometry, and version-1 canonical CAD report persisted. The browser's own reload returned to its start screen, so the browser did not demonstrate restoration of that project into the active view.

The live selection endpoint was then called for its `contemporary` option. It returned HTTP 200 with `selected_design_option_id=contemporary`, `roof_type=flat` both in selected state and design feature parameters, `design_revision=1`, model version 2, and a valid 19-solid canonical report. This verifies backend option selection and persistence. Reload restoration into the frontend remains unverified.

## Browser finding and fix

Manual browser run on the local Vite app first submitted a house prompt and caught `TypeError: Cannot read properties of undefined (reading 'toExponential')` in `ModelInspector`. Canonical reports represent unavailable inertia as the string `"Not calculated"`, while the inspector assumed a numeric matrix. The inspector now formats inertia only when a numeric 3×3 matrix exists and omits unavailable thermal expansion. After the fix, the same prompt rendered the house, 47 viewer components, and inspector data including 19 valid canonical solids. The browser test did not finish option generation/reload verification; the browser control timed out while waiting for the live options response.

Observed timings: requirement extraction 6 ms; deterministic planning with RAG disabled 3 ms; canonical CAD generation 600 ms. Live retrieval measured 2.5 s in the A/B run and 3.8 s in the marker run, but a later browser-submitted request persisted a 41.2 s retrieval trace. Treat retrieval latency as variable and a current bottleneck; no optimization was attempted.

## Remaining Phase 3.1 work

- Add a deterministic rectangle/collision validator with passing and intentionally invalid fixtures.
- Make room changes and natural-language interior/roof edits update persisted design state and revision, not only chat text.
- Distinguish structural B-Rep metrics from architectural presentation components in UI labels.
- Improve roof representation: current canonical roof structural component is a box; slope changes its box height, overhang changes its box footprint, but gable and hip do not have their corresponding roof surfaces.
- Add a browser test runner or complete a stable browser-based workflow test and reload verification.
- Consider corpus-grounded RAG A/B tests with documents whose retrieved recommendation can be mapped to an explicit plan decision; current live corpus evidence does not show a structural geometry change.
- Record climate provenance categories consistently (user supplied, RAG derived, external, assumed, unavailable).
