"""Document ingestion pipeline.

Accepts plain text (and basic text-file uploads), chunks the content,
embeds each chunk with nomic-embed-text, and stores it in PostgreSQL/pgvector.
"""

import re

from app.services import ollama_service
from app.services.pg_store import get_conn

_CHUNK_SIZE = 400      # characters per chunk
_CHUNK_OVERLAP = 80   # overlap between consecutive chunks


def _chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks of approximately _CHUNK_SIZE characters,
    preferring sentence/paragraph boundaries.
    """
    # Normalize whitespace
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    # Split on paragraph or sentence boundary first
    segments: list[str] = []
    paragraphs = text.split("\n\n")
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) <= _CHUNK_SIZE:
            segments.append(para)
        else:
            # Sentence-level split inside long paragraphs
            sentences = re.split(r"(?<=[.!?])\s+", para)
            current = ""
            for sent in sentences:
                if len(current) + len(sent) + 1 <= _CHUNK_SIZE:
                    current = f"{current} {sent}".strip() if current else sent
                else:
                    if current:
                        segments.append(current)
                    current = sent
            if current:
                segments.append(current)

    if not segments:
        return []

    # Apply overlap: carry _CHUNK_OVERLAP chars from previous chunk into next
    result: list[str] = [segments[0]]
    for seg in segments[1:]:
        tail = result[-1][-_CHUNK_OVERLAP:] if len(result[-1]) > _CHUNK_OVERLAP else result[-1]
        result.append(f"{tail} {seg}".strip())
    return result


def ingest_text(
    text: str,
    filename: str,
    title: str,
    source: str | None = None,
    document_type: str = "engineering_reference",
) -> dict:
    """Chunk, embed, and store a text document.

    Returns:
        {"status": "INDEXED" | "FAILED" | "OCR_REQUIRED", "document_id": int, "chunks": int}
    """
    if not text or not text.strip():
        return {"status": "OCR_REQUIRED", "document_id": None, "chunks": 0, "embeddings": 0}

    chunks = _chunk_text(text)
    if not chunks:
        return {"status": "OCR_REQUIRED", "document_id": None, "chunks": 0, "embeddings": 0}

    try:
        with get_conn() as conn:
            row = conn.execute(
                """
                INSERT INTO rag_documents (filename, title, source, document_type)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (filename, title, source or filename, document_type),
            ).fetchone()
            doc_id = row["id"]

            embedded = 0
            for idx, chunk in enumerate(chunks):
                try:
                    vector = ollama_service.embed(chunk)
                except RuntimeError:
                    # Skip the chunk if embedding fails but continue
                    continue

                vector_literal = f"[{','.join(str(v) for v in vector)}]"
                conn.execute(
                    """
                    INSERT INTO rag_chunks (document_id, chunk_index, content, page_number, embedding)
                    VALUES (%s, %s, %s, %s, %s::vector)
                    """,
                    (doc_id, idx, chunk, 0, vector_literal),
                )
                embedded += 1

        return {
            "status": "INDEXED",
            "document_id": doc_id,
            "chunks": len(chunks),
            "embeddings": embedded,
        }
    except Exception as exc:
        return {"status": "FAILED", "error": str(exc), "document_id": None, "chunks": 0, "embeddings": 0}


def ingest_seed_documents() -> list[dict]:
    """Insert built-in engineering reference knowledge on first startup."""
    _SEED = [
        {
            "filename": "mechanical_design_handbook.txt",
            "title": "Mechanical Design Reference — Brackets and Plates",
            "source": "Internal Engineering Reference",
            "content": (
                "MOUNTING BRACKET DESIGN GUIDELINES\n\n"
                "A mounting bracket is a structural component that transfers load from one member to another. "
                "Typical materials are structural steel (S235/S275), stainless steel, or aluminium alloys.\n\n"
                "BASE PLATE: The base plate provides the primary contact area with the mounting surface. "
                "Minimum thickness is typically 8–15 mm for steel brackets under moderate loads. "
                "Through-holes for M8 to M12 fasteners (Ø9–13 mm clearance) are positioned at 20 mm from corners.\n\n"
                "UPRIGHT PLATE: The upright (vertical) plate transfers vertical and horizontal loads to the base. "
                "Thickness should match the base plate (10–15 mm). Height is determined by the supported component clearance.\n\n"
                "GUSSETS: Triangular or rectangular gussets reinforce the perpendicular joint between base and upright. "
                "For a 100×120 mm upright, two symmetrical triangular gussets of approximately 60×80 mm provide adequate stiffness. "
                "Gussets are welded or integrated as a single-piece casting/extrusion.\n\n"
                "FILLET WELDS: All internal perpendicular joints should be fillet-welded with throat size ≥ 6 mm for structural applications.\n\n"
                "HOLES: Through-holes must maintain minimum edge distance ≥ 1.5×diameter from any free edge.\n\n"
                "FILLETS (MACHINED): External vertical edges of brackets are typically filleted at R6–R12 mm to reduce stress concentration. "
                "Sharp internal edges receive R2–R4 mm fillets.\n\n"
                "CHAMFERS: Chamfers of 2–5 mm × 45° are applied to major fastener-hole entries to allow washer seating.\n\n"
                "MINIMUM WALL THICKNESS: For steel, minimum wall thickness is 6 mm; for precision brackets, 8–12 mm is standard.\n\n"
                "PARAMETRIC DESIGN: When generating a parametric model, the feature history must record:\n"
                "  1. Base plate extrusion\n  2. Upright plate extrusion\n  3. Gusset(s)\n  4. Boolean hole operations\n  5. Fillets\n  6. Chamfers"
            ),
        },
        {
            "filename": "engineering_tolerances.txt",
            "title": "Engineering Tolerances and Fits Reference",
            "source": "Internal Engineering Reference",
            "content": (
                "DIMENSIONAL TOLERANCES\n\n"
                "General machining tolerances per ISO 2768:\n"
                "Fine (f): ±0.05 mm for dimensions ≤ 30 mm; ±0.1 mm for 30–120 mm\n"
                "Medium (m): ±0.1 mm for ≤ 30 mm; ±0.2 mm for 30–120 mm\n"
                "Coarse (c): ±0.2 mm for ≤ 30 mm; ±0.5 mm for 30–120 mm\n\n"
                "HOLE TOLERANCES: Preferred hole basis system. H7 for precision fits (clearance), H8 for general fits.\n"
                "For Ø12 mm holes: H7 gives +0/+0.018 mm tolerance.\n"
                "For Ø6 mm holes: H7 gives +0/+0.012 mm tolerance.\n"
                "For Ø18 mm holes: H7 gives +0/+0.021 mm tolerance.\n"
                "For Ø30 mm holes: H7 gives +0/+0.025 mm tolerance.\n\n"
                "SURFACE FINISH: Ra 3.2 μm for general machined surfaces. Ra 1.6 μm for seating surfaces.\n\n"
                "THREAD STANDARDS: ISO metric threads (M-series). Preferred sizes: M6, M8, M10, M12, M16.\n\n"
                "MATERIAL STANDARDS: Structural steel S235JR (yield 235 MPa), S275JR (yield 275 MPa). "
                "Stainless 304 (yield 205 MPa), 316 (yield 205 MPa). Aluminium 6061-T6 (yield 276 MPa)."
            ),
        },
        {
            "filename": "bridge_engineering_reference.txt",
            "title": "Bridge Engineering — Preliminary Design Parameters",
            "source": "Internal Engineering Reference",
            "content": (
                "BRIDGE PRELIMINARY DESIGN\n\n"
                "BEAM/GIRDER BRIDGES: Economical spans 10–50 m. Deck slab typically 200–300 mm RC slab. "
                "Steel I-girder depth ≈ span/20 to span/25.\n\n"
                "TRUSS BRIDGES: Economical spans 50–200 m. Truss depth ≈ span/8 to span/12. "
                "Panel spacing approximately 5–8 m.\n\n"
                "ARCH BRIDGES: Rise/span ratio typically 0.15–0.25. Suitable for 50–300 m spans over valleys or rivers.\n\n"
                "SUSPENSION BRIDGES: Economical for spans 300–2000 m. Main cable sag ≈ span/10. "
                "Tower height ≈ sag + clearance + 10–15 m for cable anchorage.\n\n"
                "CABLE-STAYED BRIDGES: Economical spans 200–1000 m. Tower height ≈ 0.2×span above deck. "
                "Back-stay cables extend to anchorage blocks on approach embankments.\n\n"
                "PEDESTRIAN BRIDGE: Minimum clear width 3 m. Live load 5 kPa. Handrail height 1.0–1.2 m. "
                "Vibration serviceability must be checked per EN 1990 or relevant code.\n\n"
                "DESIGN LOADS: Dead load (self-weight), live load, wind load, seismic load. "
                "All loads must be combined per relevant code (AASHTO, EN 1991, IS 875)."
            ),
        },
        {
            "filename": "residential_building_reference.txt",
            "title": "Residential Building — Architectural and Structural Reference",
            "source": "Internal Engineering Reference",
            "content": (
                "RESIDENTIAL BUILDING DESIGN\n\n"
                "FLOOR HEIGHT: Standard residential floor-to-floor height is 3.0–3.2 m (10 ft). "
                "Commercial buildings typically 3.5–4.0 m per floor.\n\n"
                "SETBACK RULES: Building setback from plot boundary typically 1.5–2.0 m front, 1.0–1.5 m sides, 1.0 m rear. "
                "Check local municipal bylaws.\n\n"
                "STRUCTURAL SYSTEM: RCC frame with brick infill is common in South Asia. "
                "Column size typically 230×300 mm or 300×300 mm for residential. "
                "Beam depth ≈ span/12 to span/15.\n\n"
                "G+1 BUILDING: Ground floor + 1 upper floor. Total structural height ≈ 7.0–7.5 m. "
                "Foundation: Isolated footings or strip foundation depending on soil condition.\n\n"
                "G+2 BUILDING: Ground + 2 upper floors. Total height ≈ 10–11 m. "
                "Pile foundation may be required in weak soil zones.\n\n"
                "ROOF TYPES: Flat RCC slab (common in urban India) or pitched/sloped roof (traditional). "
                "Flat roof slope ≥ 1:50 for drainage.\n\n"
                "MATERIALS: Concrete M20 minimum grade. Steel Fe415/Fe500. "
                "Brick IS:1077 (clay), AAC blocks for lighter construction."
            ),
        },
    ]

    results = []
    with get_conn() as conn:
        for seed in _SEED:
            # Skip if already ingested (same filename)
            existing = conn.execute(
                "SELECT id FROM rag_documents WHERE filename = %s", (seed["filename"],)
            ).fetchone()
            if existing:
                results.append({"filename": seed["filename"], "status": "already_indexed"})
                continue

        # Outside the context manager re-ingest each new document
    for seed in _SEED:
        with get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM rag_documents WHERE filename = %s", (seed["filename"],)
            ).fetchone()
            if existing:
                continue

        result = ingest_text(
            text=seed["content"],
            filename=seed["filename"],
            title=seed["title"],
            source=seed["source"],
            document_type="engineering_reference",
        )
        results.append({"filename": seed["filename"], **result})

    return results
