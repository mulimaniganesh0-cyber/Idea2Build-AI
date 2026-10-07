# RAG → AI → CAD integration audit

Audit date: 2026-10-07  
Target: `D:\AI-CAD-Engineer`

## Architecture and actual request path

The frontend's `sendChatMessage` in `frontend/src/api.ts` posts to `POST /api/chat`. `backend/app/main.py::chat` calls `app.services.chat.handle_message`, then stores the conversation and any returned geometry/design data.

`handle_message` routes new prompts. Mechanical prompts reach `_handle_mechanical` → `build_mechanical_spec_from_prompt` → `retrieval.retrieve` → `build_context_block` → `extract_mechanical_spec` → Ollama `/api/chat` structured JSON → Pydantic `MechanicalDesignSpec` → `generate_mechanical_primitive`. That builder returns deterministic parametric viewer components and also calls `build_canonical_mechanical_cad` to create build123d/OpenCASCADE solids. The canonical B-Rep return value is currently discarded by `generate_mechanical_primitive`; its exceptions are swallowed, and the chat response contains the separate parametric viewer geometry. This means B-Rep creation was proven directly, but it is not yet authoritative for the returned mechanical geometry/export path.

Bridge, house, and ordinary primitive prompts use separate deterministic paths. They do not call RAG or Ollama structured extraction. House models have a separate canonical build123d/OpenCASCADE API; bridge output is viewer component geometry. The overall application therefore does not route every engineering design domain through RAG → AI → CAD.

## Retrieval and database evidence

Direct PostgreSQL checks returned:

- Database: `ai_cad_engineer_db`; PostgreSQL 18.3.
- pgvector 0.8.6; HNSW cosine index `rag_chunks_embedding_hnsw` with `m=16`, `ef_construction=64`.
- 16 documents, 57 chunks, 0 NULL embeddings. Stored vectors are 768-dimensional.
- Embedding model: `nomic-embed-text:latest`; chat model: `llama3.2:latest`; both were ready in Ollama.
- Retrieval defaults: top-k 5, cosine similarity floor 0.35.

The corpus contains 10 synthetic test records (`test_spec.txt` repeated 9 times and `test_doc.txt` once), as well as duplicate engineering-reference chunks. Retrieval now excludes those known test fixture records without deleting them, and collapses duplicate chunk text before top-k ranking. Results expose document ID, chunk ID, rank, source, page, score, and content. A live query returned five unique bracket-handbook chunks; scores were about 0.75–0.85.

## Trace and context consumption

A retrieval trace carries a UUID, embedding model/dimension, top-k, threshold, and duration. The same trace ID reaches the Ollama generation call. Sanitized `RAG_TRACE` and `OLLAMA_TRACE` logs include chunk/source counts, context character count, context SHA-256, model, JSON-mode request, response status/size, and duration; document text is not logged. The chat API returns the retrieval trace and provenance, and the Model Inspector displays the trace, embedding details, source rank, document/chunk IDs, score, and source text.

The marker regression uses `RAG_TEST_MARKER_ABC123` and observes the prompt passed to the Ollama adapter. It fails if retrieval/context formatting is disconnected from generation. A separate control asserts `use_rag=False` performs no retrieval and injects no context. Both are adapter tests with controlled boundaries; they are not represented as live model evidence.

## Live influence test

A real Ollama A/B used the same request: “Design a steel mounting bracket with a 160 mm by 100 mm base plate, a 100 mm by 120 mm upright, two triangular gussets, and four base through-holes. Choose plate thickness and hole size using the retrieved engineering guidance.” The RAG run retrieved only `mechanical_design_handbook.txt` after fixture exclusion. The trace showed 768-dimension query embeddings, 5 unique chunks, a 1,576-character context block with SHA-256, and a successful structured response from `llama3.2:latest`.

| Output | RAG enabled | RAG disabled |
|---|---:|---:|
| Base plate | 160 × 100 × 12 mm | 160 × 100 × 5 mm |
| Upright | 100 × 120 × 12 mm | 100 × 120 × 5 mm |
| Four base holes | Ø9 mm | Ø10 mm |
| Viewer components | 8 | 8 |
| OpenCASCADE solids / faces | 4 / 36 | 4 / 40 |
| B-Rep volume | 399,012.74 mm³ | 166,886.78 mm³ |
| B-Rep mass | 3.1323 kg | 1.3101 kg |

The four returned solids in the RAG case each reported `is_valid=true`. This is direct evidence that retrieved engineering guidance changed unspecified structured CAD parameters and those parameters reached the deterministic geometry builders. It does not establish engineering adequacy, strength, or code compliance.

Explicit-dimension precedence is enforced after LLM parsing for clear three-value base-plate/upright-plate callouts and explicit hole callouts. A regression supplied deliberately conflicting LLM dimensions and verified that the user's 160 × 100 × 12 mm base, 100 × 120 × 12 mm upright, and four Ø12 mm holes won.

## API and scenario checks

`GET /api/v1/health` returned `status=ok`, with PostgreSQL, pgvector, Ollama, and both configured models ready; corpus counts were 16 / 57. A live `POST /api/chat` mechanical request returned HTTP 200 with `FOUND`, real retrieved sources, document/chunk IDs, and a trace linked to a successful Ollama JSON response. A final API contract check used live retrieval with a stubbed LLM to verify that fixture sources are excluded and explicit dimensions plus provenance reach the response.

Using a disposable SQLite project store, FastAPI scenario requests returned HTTP 200 for a 50 mm cube, a 3-floor house, a 10 m truss bridge, a 50 m truss bridge, and a 30 m truss bridge. The 3-floor house's canonical CAD endpoint returned `CAD_VALID` / `PASS` with 20 solids, 120 faces, 240 edges, and 160 vertices. Bridge chat responses exposed viewer geometry, not validated structural B-Reps. Temporary project databases were removed; the existing SQLite database was backed up and restored around tests.

## Tests and runtime

- Backend suite excluding the live ingestion module: 45 passed, 4 dependency/deprecation warnings.
- Safe RAG pipeline subset: 10 passed, 2 deselected. The excluded ingestion test writes duplicate fixtures into the live PostgreSQL corpus; the other excluded helper test writes to the persistent project store. Live retrieval, Ollama generation, influence, health, and API paths were exercised separately.
- Frontend `npm run build`: passed (TypeScript and Vite production build).
- Browser E2E / console inspection: not run; the frontend package defines build/dev/preview scripts but no browser-test script.
- Measured query embedding plus retrieval: about 3.65 s in the clean-corpus A/B. Ollama generation took about 75.1 s for the RAG case and 87.7 s for the no-RAG case. A live API generation took about 66.2 s. These are single-run measurements, not benchmarks.

## Changes

- Retrieval deduplication, exclusion of the known synthetic test rows, vector-dimension checking, trace metadata, and chunk provenance.
- Sanitized correlated retrieval/Ollama logs with context hash and structured-response metadata.
- Explicit dimension reconciliation and regression coverage for RAG handoff, RAG-off control, and dimension precedence.
- API response and Model Inspector now expose retrieval trace and source identifiers.
- No database migration and no corpus rows were deleted or added by this task.

The target checkout already had user changes before this work began. Those changes were preserved.

## RAG versus training

RAG retrieves indexed documents at inference time and supplies their text as context. No model fine-tuning was performed; model weights were not changed.

## Final stage status

| Stage | Status | Evidence |
|---|---|---|
| User prompt / frontend endpoint | VERIFIED | Frontend call to `POST /api/chat`; live API returned 200 |
| Intent/domain | PARTIAL | Mechanical route integrates RAG; bridge/house/primitive routes bypass it |
| Query embedding | VERIFIED | Live Ollama embedding, `nomic-embed-text:latest`, 768 dimensions |
| pgvector retrieval | VERIFIED | Live cosine search, threshold 0.35, top-k 5, HNSW; duplicate/test rows handled |
| Retrieved text/context | VERIFIED | Actual handbook chunks and context hash observed |
| Context reaches Ollama | VERIFIED | Shared trace ID and successful live Ollama JSON call; marker regression added |
| Structured CAD parameters | VERIFIED for mechanical | Ollama JSON validated as `MechanicalDesignSpec`; explicit callouts reconciled |
| CAD parameter consumption | VERIFIED for mechanical | A/B changed dimensions and holes; viewer and B-Rep builders received specs |
| OpenCASCADE geometry | PARTIAL | Mechanical solids valid in direct builder, but B-Rep is discarded from API geometry; house B-Rep API passed |
| Knowledge provenance / Model Inspector | VERIFIED for mechanical | API trace and source IDs shown in inspector |
| RAG-disabled control | VERIFIED at service/test level | Live A/B and explicit `use_rag=False` control; no public API toggle |
| Negative ignored-context test | VERIFIED as regression | `RAG_TEST_MARKER_ABC123` assertion added |
| RAG influence | VERIFIED for mechanical | Clean-corpus live A/B produced different unspecified dimensions and hole sizes |
| Browser test / console | NOT VERIFIED | No browser test run |
| Bridge RAG → AI → CAD | NOT VERIFIED | Current bridge route bypasses RAG/Ollama extraction |

OVERALL STATUS: PARTIAL

The mechanical RAG → Ollama → structured CAD parameter path is proven and instrumented. The project-wide acceptance remains partial because bridge/house/primitive routing is not integrated with RAG, the mechanical API still returns viewer components instead of the canonical B-Rep, and browser E2E verification was not run.
