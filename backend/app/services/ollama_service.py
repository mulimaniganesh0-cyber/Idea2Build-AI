"""Direct Ollama HTTP API integration.

Uses the local Ollama instance at http://localhost:11434.
Does NOT fall back to hallucinated output — returns a clear error instead.
"""

import json
import logging
import os
import time

import httpx

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest")
CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "llama3.2:latest")
logger = logging.getLogger(__name__)
_TIMEOUT = 120.0  # seconds


def health() -> dict:
    """Return Ollama health: which models are available and whether the service is up."""
    try:
        resp = httpx.get(f"{OLLAMA_BASE}/api/tags", timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        models = [m["name"] for m in data.get("models", [])]
        return {
            "available": True,
            "models": models,
            "chat_model_ready": CHAT_MODEL in models,
            "embed_model_ready": EMBED_MODEL in models,
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def embed(text: str) -> list[float]:
    """Embed *text* using nomic-embed-text via Ollama /api/embed.

    Returns a list of floats (dimension 768 for nomic-embed-text).
    Raises RuntimeError if Ollama is unavailable.
    """
    try:
        resp = httpx.post(
            f"{OLLAMA_BASE}/api/embed",
            json={"model": EMBED_MODEL, "input": text},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        # /api/embed returns {"embeddings": [[...], ...]}
        embeddings = data.get("embeddings") or data.get("embedding")
        if not embeddings:
            raise RuntimeError(f"No embeddings in Ollama response: {data}")
        # Accept both list-of-lists (batch) and flat list (single)
        if isinstance(embeddings[0], list):
            return embeddings[0]
        return embeddings
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Ollama embed HTTP error {exc.response.status_code}: {exc.response.text}") from exc
    except Exception as exc:
        raise RuntimeError(f"Ollama embed failed: {exc}") from exc


def generate(
    prompt: str,
    system_prompt: str | None = None,
    *,
    temperature: float = 0.1,
    format_json: bool = True,
    rag_trace: dict | None = None,
) -> str:
    """Send a prompt to llama3.2 via Ollama /api/chat.

    Returns the raw string content of the assistant reply.
    Raises RuntimeError if Ollama is unavailable or the call fails.
    """
    started = time.perf_counter()
    rag_trace = rag_trace or {}
    trace_id = rag_trace.get("trace_id")
    logger.info("OLLAMA_TRACE %s", {
        "trace_id": trace_id,
        "model": CHAT_MODEL,
        "rag_context_present": bool(rag_trace.get("context_present")),
        "rag_source_count": int(rag_trace.get("source_count", 0)),
        "rag_context_characters": int(rag_trace.get("context_characters", 0)),
        "rag_context_sha256": rag_trace.get("context_sha256"),
        "structured_output": format_json,
        "stage": "request_started",
    })
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload: dict = {
        "model": CHAT_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if format_json:
        payload["format"] = "json"

    try:
        resp = httpx.post(
            f"{OLLAMA_BASE}/api/chat",
            json=payload,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("message", {}).get("content", "")
        if not content:
            raise RuntimeError(f"Empty content in Ollama response: {data}")
        logger.info("OLLAMA_TRACE %s", {
            "trace_id": trace_id,
            "model": CHAT_MODEL,
            "rag_context_present": bool(rag_trace.get("context_present")),
            "rag_source_count": int(rag_trace.get("source_count", 0)),
            "structured_output": format_json,
            "response_received": True,
            "response_characters": len(content),
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "stage": "response_received",
        })
        return content
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Ollama chat HTTP error {exc.response.status_code}: {exc.response.text}") from exc
    except Exception as exc:
        raise RuntimeError(f"Ollama chat failed: {exc}") from exc


def classify_domain(user_message: str) -> str:
    """Use llama3.2 to classify the engineering domain of a prompt.

    Returns one of: 'mechanical', 'architectural', 'bridge', 'general'.
    Falls back to keyword heuristics if Ollama fails.
    """
    system = (
        "You are an engineering domain classifier. "
        "Given a CAD or engineering prompt, classify it into exactly ONE domain. "
        'Return ONLY valid JSON like: {"domain": "mechanical"}\n'
        "Valid domains: mechanical, architectural, bridge, general\n"
        "mechanical: brackets, shafts, gears, plates, holes, fillets, chamfers, machine parts, fixtures\n"
        "architectural: houses, buildings, floors, rooms, residential, G+1, G+2, villas, apartments\n"
        "bridge: bridges, spans, decks, trusses, arches, flyovers, overpasses\n"
        "general: anything else"
    )
    try:
        raw = generate(user_message, system_prompt=system, temperature=0.0, format_json=True)
        data = json.loads(raw)
        domain = str(data.get("domain", "general")).lower()
        if domain in ("mechanical", "architectural", "bridge", "general"):
            return domain
    except Exception:
        pass
    # Deterministic safety-layer fallback
    return _keyword_classify(user_message)


def _keyword_classify(message: str) -> str:
    lower = message.lower()
    _MECHANICAL = {
        "bracket", "mounting bracket", "shaft", "gear", "bearing", "gearbox",
        "plate", "upright", "gusset", "flange", "coupling", "bolt", "fixture",
        "machine part", "counterbore", "countersink", "fillet", "chamfer",
        "rib", "boss", "through-hole", "through hole",
    }
    _BRIDGE = {"bridge", "overpass", "flyover", "span", "truss", "deck"}
    _ARCHITECTURAL = {
        "house", "villa", "home", "residential", "duplex", "apartment",
        "cottage", "bungalow", "building", "interior", "bedroom", "kitchen",
        "bathroom", "g+1", "g+2", "g+3", "g+4", "g+5",
    }
    for kw in _MECHANICAL:
        if kw in lower:
            return "mechanical"
    for kw in _BRIDGE:
        if kw in lower:
            return "bridge"
    for kw in _ARCHITECTURAL:
        if kw in lower:
            return "architectural"
    return "general"
