import json

from app.services import llm_designer


RAG_TEST_MARKER = "RAG_TEST_MARKER_ABC123"


def test_retrieved_context_reaches_ollama_generation(monkeypatch):
    """Fail if retrieval/context construction is disconnected from the LLM call."""
    captured = {}
    retrieved = {
        "status": "FOUND",
        "method": "pgvector",
        "results": [
            {
                "content": f"Controlled retrieval fixture: {RAG_TEST_MARKER}",
                "source": "test-fixture.txt",
                "title": "RAG handoff fixture",
                "page": 1,
                "score": 0.99,
            }
        ],
    }

    monkeypatch.setattr(llm_designer.rag, "retrieve", lambda query, top_k: retrieved)

    def fake_generate(*, prompt, **kwargs):
        captured["prompt"] = prompt
        return json.dumps({
            "domain": "mechanical",
            "object_type": "plate",
            "units": "mm",
            "material": "steel",
            "length_mm": 100,
            "width_mm": 50,
            "height_mm": 10,
            "source_prompt": "Create a 100 x 50 x 10 mm plate",
        })

    monkeypatch.setattr(llm_designer.ollama_service, "generate", fake_generate)

    spec, rag_result = llm_designer.build_mechanical_spec_from_prompt(
        "Create a 100 x 50 x 10 mm plate suitable for a test fixture",
        use_rag=True,
    )

    assert rag_result["status"] == "FOUND"
    assert spec.object_type == "plate"
    assert RAG_TEST_MARKER in captured["prompt"], (
        "Retrieved chunk was built but did not reach the Ollama generation prompt"
    )
    assert "test-fixture.txt" in captured["prompt"]


def test_rag_disabled_control_omits_retrieved_context(monkeypatch):
    """The control path must not retrieve or inject context when disabled."""
    captured = {}

    def unexpected_retrieval(*args, **kwargs):
        raise AssertionError("RAG retrieval ran while use_rag=False")

    monkeypatch.setattr(llm_designer.rag, "retrieve", unexpected_retrieval)

    def fake_generate(*, prompt, **kwargs):
        captured["prompt"] = prompt
        return json.dumps({
            "domain": "mechanical",
            "object_type": "plate",
            "units": "mm",
            "material": "steel",
            "length_mm": 100,
            "width_mm": 50,
            "height_mm": 10,
        })

    monkeypatch.setattr(llm_designer.ollama_service, "generate", fake_generate)

    spec, rag_result = llm_designer.build_mechanical_spec_from_prompt(
        "Create a 100 x 50 x 10 mm plate",
        use_rag=False,
    )

    assert spec.object_type == "plate"
    assert rag_result["status"] == "NOT_REQUIRED"
    assert RAG_TEST_MARKER not in captured["prompt"]
    assert "RETRIEVED ENGINEERING CONTEXT" not in captured["prompt"]


def test_explicit_plate_and_hole_dimensions_override_model_values(monkeypatch):
    """A retrieved-context/LLM suggestion must not replace explicit user callouts."""
    from app.services import ollama_service
    from app.services.llm_designer import extract_mechanical_spec

    monkeypatch.setattr(
        ollama_service,
        "generate",
        lambda **kwargs: json.dumps({
            "domain": "mechanical",
            "object_type": "mounting_bracket",
            "units": "mm",
            "material": "steel",
            "base_plate": {"length_mm": 80, "width_mm": 60, "thickness_mm": 5},
            "upright_plate": {"width_mm": 60, "height_mm": 90, "thickness_mm": 5},
            "gussets": {"count": 2, "type": "triangular"},
            "holes": [{"diameter_mm": 8, "count": 4, "location": "base"}],
        }),
    )
    spec = extract_mechanical_spec(
        "Design a bracket with base plate 160 mm by 100 mm by 12 mm, "
        "upright plate 100 mm by 120 mm by 12 mm, and four 12 mm mounting holes."
    )

    assert spec.base_plate is not None
    assert (spec.base_plate.length_mm, spec.base_plate.width_mm, spec.base_plate.thickness_mm) == (160, 100, 12)
    assert spec.upright_plate is not None
    assert (spec.upright_plate.width_mm, spec.upright_plate.height_mm, spec.upright_plate.thickness_mm) == (100, 120, 12)
    assert spec.holes[0].diameter_mm == 12
