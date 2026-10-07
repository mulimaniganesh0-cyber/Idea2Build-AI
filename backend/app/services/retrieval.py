"""RAG retrieval service — embed the query and search pgvector.

Returns ranked chunks with source metadata and similarity scores.
"""

import logging
import time
from uuid import uuid4

from app.services import ollama_service
from app.services.pg_store import EMBEDDING_DIM, get_conn

logger = logging.getLogger(__name__)

_SIMILARITY_THRESHOLD = 0.35  # cosine similarity floor


def retrieve(query: str, top_k: int = 5) -> dict:
    """Embed *query* with nomic-embed-text and run a cosine similarity search.

    Returns:
        {
            "status": "FOUND" | "NO_RELEVANT_CONTEXT",
            "method": "pgvector",
            "results": [{"content": ..., "source": ..., "page": ..., "score": ...}]
        }
    """
    started = time.perf_counter()
    trace_id = str(uuid4())
    trace = {
        "trace_id": trace_id,
        "embedding_model": ollama_service.EMBED_MODEL,
        "embedding_dimension": None,
        "requested_top_k": top_k,
        "similarity_threshold": _SIMILARITY_THRESHOLD,
    }
    try:
        vector = ollama_service.embed(query)
    except RuntimeError as exc:
        trace["duration_ms"] = round((time.perf_counter() - started) * 1000)
        logger.warning("RAG_TRACE %s", {**trace, "status": "ERROR", "stage": "embedding"})
        return {
            "status": "ERROR",
            "method": "pgvector",
            "trace": trace,
            "error": f"Embedding failed: {exc}",
            "results": [],
        }

    trace["embedding_dimension"] = len(vector)
    if len(vector) != EMBEDDING_DIM:
        trace["duration_ms"] = round((time.perf_counter() - started) * 1000)
        logger.warning("RAG_TRACE %s", {**trace, "status": "ERROR", "stage": "embedding_dimension"})
        return {
            "status": "ERROR",
            "method": "pgvector",
            "trace": trace,
            "error": f"Embedding dimension {len(vector)} does not match pgvector dimension {EMBEDDING_DIM}",
            "results": [],
        }

    vector_literal = f"[{','.join(str(v) for v in vector)}]"

    try:
        with get_conn() as conn:
            rows = conn.execute(
                """
                WITH scored AS (
                    SELECT
                        d.id AS document_id,
                        c.id AS chunk_id,
                        c.content,
                        c.page_number,
                        d.filename AS source,
                        d.title,
                        1 - (c.embedding <=> %s::vector) AS score
                    FROM rag_chunks c
                    JOIN rag_documents d ON d.id = c.document_id
                    WHERE 1 - (c.embedding <=> %s::vector) >= %s
                      AND lower(COALESCE(d.source, '')) <> 'unit_test'
                      AND lower(d.filename) NOT IN ('test_spec.txt', 'test_doc.txt')
                      AND lower(d.title) NOT IN ('test engineering spec', 'test doc')
                ), deduplicated AS (
                    SELECT DISTINCT ON (content) *
                    FROM scored
                    ORDER BY content, score DESC, chunk_id ASC
                )
                SELECT * FROM deduplicated
                ORDER BY score DESC, chunk_id ASC
                LIMIT %s
                """,
                (vector_literal, vector_literal, _SIMILARITY_THRESHOLD, top_k),
            ).fetchall()
    except Exception as exc:
        return {
            "status": "ERROR",
            "method": "pgvector",
            "trace": trace,
            "error": f"pgvector search failed: {exc}",
            "results": [],
        }

    trace["duration_ms"] = round((time.perf_counter() - started) * 1000)
    if not rows:
        logger.info("RAG_TRACE %s", {**trace, "status": "NO_RELEVANT_CONTEXT", "retrieved_chunks": 0})
        return {"status": "NO_RELEVANT_CONTEXT", "method": "pgvector", "trace": trace, "results": []}

    results = [
        {
            "document_id": row["document_id"],
            "chunk_id": row["chunk_id"],
            "rank": rank,
            "content": row["content"],
            "source": row["source"],
            "title": row["title"],
            "page": row["page_number"],
            "score": round(float(row["score"]), 4),
        }
        for rank, row in enumerate(rows, 1)
    ]
    logger.info("RAG_TRACE %s", {**trace, "status": "FOUND", "retrieved_chunks": len(results)})
    return {"status": "FOUND", "method": "pgvector", "trace": trace, "results": results}


def build_context_block(retrieval_result: dict) -> str:
    """Format RAG results into a string block for injection into the LLM prompt."""
    if retrieval_result["status"] != "FOUND":
        return ""
    lines = ["RETRIEVED ENGINEERING CONTEXT:"]
    for i, r in enumerate(retrieval_result["results"], 1):
        lines.append(
            f"\n[Source {i}: {r['source']} — page {r['page']} — similarity {r['score']}]\n"
            f"{r['content']}"
        )
    return "\n".join(lines)
