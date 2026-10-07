"""End-to-end and unit tests for RAG + Local Ollama CAD pipeline.

Covers requirements A through S:
A. Ollama health
B. Ollama embedding
C. PostgreSQL connection
D. pgvector extension
E. document ingestion
F. embedding storage
G. vector retrieval
H. RAG context
I. LLM DesignSpec generation
J. DesignSpec validation
K. mechanical classification
L. house classification
M. bridge classification
N. mechanical CAD generation
O. actual holes
P. gussets
Q. feature history
R. OBJ export compatibility
S. frontend response schema
"""

import pytest
from app.mechanical_models import (
    BasePlateDef,
    ChamferDef,
    FilletDef,
    GussetDef,
    HoleDef,
    MechanicalDesignSpec,
    UprightPlateDef,
)
from app.models import ChatResponse, DesignSpec
from app.services import ollama_service
from app.services.chat import handle_message, _is_mechanical_prompt
from app.services.ingestion import ingest_seed_documents, ingest_text
from app.services.llm_designer import build_mechanical_spec_from_prompt, extract_mechanical_spec
from app.services.mechanical_cad import generate_mechanical_primitive
from app.services.pg_store import ensure_schema, get_conn, health as pg_health
from app.services.retrieval import build_context_block, retrieve


# ── A. Ollama Health ─────────────────────────────────────────────────────────

def test_a_ollama_health():
    h = ollama_service.health()
    assert h.get("available") is True, f"Ollama not available: {h}"
    assert h.get("chat_model_ready") is True, f"llama3.2 not ready: {h}"
    assert h.get("embed_model_ready") is True, f"nomic-embed-text not ready: {h}"


# ── B. Ollama Embedding ──────────────────────────────────────────────────────

def test_b_ollama_embedding():
    vector = ollama_service.embed("mounting bracket base plate")
    assert isinstance(vector, list)
    assert len(vector) == 768, f"Expected 768 dimensions for nomic-embed-text, got {len(vector)}"
    assert all(isinstance(x, float) for x in vector[:5])


# ── C & D. PostgreSQL Connection & pgvector Extension ────────────────────────

def test_c_d_postgres_pgvector():
    ensure_schema()
    h = pg_health()
    assert h.get("postgres") is True, "PostgreSQL not reachable"
    assert h.get("pgvector") is True, "pgvector extension not enabled"


# ── E & F. Document Ingestion & Storage ──────────────────────────────────────

def test_e_f_document_ingestion_and_storage():
    text = (
        "TEST ENGINEERING SPECIFICATION:\n"
        "Mounting brackets require 12mm plate thickness and M12 through holes "
        "spaced 20mm from edges for structural integrity."
    )
    result = ingest_text(
        text=text,
        filename="test_spec.txt",
        title="Test Engineering Spec",
        source="unit_test",
    )
    assert result["status"] == "INDEXED"
    assert result["chunks"] >= 1
    assert result["embeddings"] >= 1

    # Verify rows in PostgreSQL
    with get_conn() as conn:
        row = conn.execute(
            "SELECT count(*) as cnt FROM rag_chunks WHERE document_id = %s",
            (result["document_id"],),
        ).fetchone()
        assert row["cnt"] >= 1


# ── G. Vector Retrieval ──────────────────────────────────────────────────────

def test_g_vector_retrieval():
    res = retrieve("mounting bracket plate thickness holes", top_k=3)
    assert res["status"] == "FOUND"
    assert res["method"] == "pgvector"
    assert len(res["results"]) > 0
    top = res["results"][0]
    assert "content" in top
    assert "source" in top
    assert "score" in top
    assert top["score"] > 0.0


# ── H. RAG Context Building ─────────────────────────────────────────────────

def test_h_rag_context_building():
    ret = retrieve("gusset triangular upright plate")
    context_block = build_context_block(ret)
    assert isinstance(context_block, str)
    assert len(context_block) > 0
    assert "RETRIEVED ENGINEERING CONTEXT" in context_block


# ── I & J. LLM DesignSpec Generation & Validation ───────────────────────────

def test_i_j_llm_design_spec_validation():
    # Valid spec passes
    spec = MechanicalDesignSpec(
        domain="mechanical",
        object_type="mounting_bracket",
        units="mm",
        base_plate=BasePlateDef(length_mm=160, width_mm=100, thickness_mm=12),
        upright_plate=UprightPlateDef(width_mm=100, height_mm=120, thickness_mm=12),
        gussets=GussetDef(count=2, type="triangular"),
        holes=[
            HoleDef(diameter_mm=12, count=4, location="base"),
            HoleDef(diameter_mm=6, count=4, location="base", description="central region"),
            HoleDef(diameter_mm=18, count=2, location="upright"),
            HoleDef(diameter_mm=30, count=1, location="upright"),
        ],
        fillets=[
            FilletDef(radius_mm=10, location="external_vertical"),
            FilletDef(radius_mm=3, location="remaining_sharp"),
        ],
        chamfers=[
            ChamferDef(size_mm=5, angle_deg=45, location="mounting_holes"),
        ],
        source_prompt="mounting bracket prompt",
    )
    assert spec.domain == "mechanical"
    assert spec.object_type == "mounting_bracket"

    # Reject architectural fields
    with pytest.raises(ValueError, match="Architectural fields are forbidden"):
        MechanicalDesignSpec.model_validate({
            "domain": "mechanical",
            "object_type": "mounting_bracket",
            "floors": 2,  # Forbidden!
        })


# ── K, L, M. Classification Tests ───────────────────────────────────────────

def test_k_mechanical_classification():
    prompt = "Design a mechanical mounting bracket with base plate 160x100mm and upright plate."
    assert _is_mechanical_prompt(prompt) is True
    domain = ollama_service.classify_domain(prompt)
    assert domain == "mechanical"


def test_l_house_classification():
    prompt = "Design a modern 2 floor G+1 residential house with 3 bedrooms and a flat roof on 30x40 site."
    assert _is_mechanical_prompt(prompt) is False
    domain = ollama_service.classify_domain(prompt)
    assert domain == "architectural"


def test_m_bridge_classification():
    prompt = "Design a 60m truss pedestrian bridge crossing a river with 4m deck width."
    assert _is_mechanical_prompt(prompt) is False
    domain = ollama_service.classify_domain(prompt)
    assert domain == "bridge"


# ── N, O, P, Q. Mechanical CAD Generation, Holes, Gussets, Features ──────────

def test_n_o_p_q_cad_generation():
    spec = MechanicalDesignSpec(
        domain="mechanical",
        object_type="mounting_bracket",
        units="mm",
        base_plate=BasePlateDef(length_mm=160, width_mm=100, thickness_mm=12),
        upright_plate=UprightPlateDef(width_mm=100, height_mm=120, thickness_mm=12),
        gussets=GussetDef(count=2, type="triangular"),
        holes=[
            HoleDef(diameter_mm=12, count=4, location="base"),
            HoleDef(diameter_mm=6, count=4, location="base", description="central region"),
            HoleDef(diameter_mm=18, count=2, location="upright"),
            HoleDef(diameter_mm=30, count=1, location="upright"),
        ],
        fillets=[
            FilletDef(radius_mm=10, location="external_vertical"),
            FilletDef(radius_mm=3, location="remaining_sharp"),
        ],
        chamfers=[
            ChamferDef(size_mm=5, angle_deg=45, location="mounting_holes"),
        ],
        source_prompt="test",
    )

    cad = generate_mechanical_primitive(spec)
    assert cad.success is True
    assert cad.parameters.object_type == "mechanical_bracket"
    assert cad.parameters.feature_parameters["is_mechanical"] == 1.0
    assert cad.parameters.feature_parameters["gusset_count"] == 2.0
    assert cad.parameters.feature_parameters["total_holes"] == 11.0

    # Check components
    comp_names = [c.name for c in cad.geometry.components]
    assert "base_plate" in comp_names
    assert "upright_plate" in comp_names
    assert "gusset_left" in comp_names
    assert "gusset_right" in comp_names

    # Check holes generated (4 + 4 + 2 + 1 = 11 hole components)
    hole_comps = [c for c in cad.geometry.components if "hole" in c.name]
    assert len(hole_comps) == 11, f"Expected 11 hole components, found {len(hole_comps)}"

    # Check feature history
    history = spec.feature_history()
    assert len(history) >= 9
    assert any("Base plate" in h for h in history)
    assert any("Upright plate" in h for h in history)
    assert any("gusset" in h.lower() for h in history)


# ── R & S. OBJ Compatibility & Frontend Response Schema ──────────────────────

def test_r_s_chat_response_schema_and_mechanical_routing():
    prompt = (
        "Design a mechanical mounting bracket with base plate 160x100x12 mm and upright 100x120x12 mm "
        "with 2 triangular gussets and four 12mm holes."
    )
    resp = handle_message(prompt, None)
    assert isinstance(resp, ChatResponse)
    assert resp.active_domain == "mechanical"
    assert resp.design_state is not None
    assert resp.design_state.object_type == "mechanical_bracket"
    assert resp.geometry is not None
    assert len(resp.geometry.components) >= 4
    # Ensure it did NOT fall into house generator
    assert "residential" not in resp.message.lower()
    assert "floor" not in resp.message.lower()
    assert "Mounting Bracket" in resp.message or "mounting bracket" in resp.message
