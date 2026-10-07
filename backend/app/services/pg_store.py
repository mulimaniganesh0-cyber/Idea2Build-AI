"""PostgreSQL + pgvector connection and schema setup.

Manages the connection pool and ensures the rag_documents / rag_chunks
tables exist with a HNSW cosine-similarity index.
"""

import os
from contextlib import contextmanager
from typing import Generator

import psycopg
from psycopg.rows import dict_row

# ── Connection settings ────────────────────────────────────────────────────────
PG_DSN = os.getenv(
    "POSTGRES_DSN",
    "host=localhost port=5432 dbname=ai_cad_engineer_db user=postgres password=db1234",
)

# Embedding vector dimension (nomic-embed-text produces 768-dimensional vectors)
EMBEDDING_DIM = 768

_SCHEMA_SQL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_documents (
    id          SERIAL PRIMARY KEY,
    filename    TEXT NOT NULL,
    title       TEXT NOT NULL,
    source      TEXT,
    document_type TEXT DEFAULT 'engineering_reference',
    metadata    JSONB DEFAULT '{{}}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS rag_chunks (
    id           SERIAL PRIMARY KEY,
    document_id  INTEGER NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
    chunk_index  INTEGER NOT NULL,
    content      TEXT NOT NULL,
    page_number  INTEGER DEFAULT 0,
    metadata     JSONB DEFAULT '{{}}',
    embedding    vector({EMBEDDING_DIM})
);

CREATE INDEX IF NOT EXISTS rag_chunks_embedding_hnsw
    ON rag_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
"""


def _connect() -> psycopg.Connection:
    return psycopg.connect(PG_DSN, row_factory=dict_row)


@contextmanager
def get_conn() -> Generator[psycopg.Connection, None, None]:
    """Context manager that yields an open connection and commits on exit."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_schema() -> None:
    """Create tables and index if they do not already exist."""
    with get_conn() as conn:
        conn.execute(_SCHEMA_SQL)


def health() -> dict:
    """Return database health: connectivity, pgvector presence, and row counts."""
    try:
        with get_conn() as conn:
            # pgvector extension check
            ext = conn.execute(
                "SELECT extname FROM pg_extension WHERE extname = 'vector'"
            ).fetchone()
            docs = conn.execute("SELECT COUNT(*) AS n FROM rag_documents").fetchone()
            chunks = conn.execute("SELECT COUNT(*) AS n FROM rag_chunks").fetchone()
        return {
            "postgres": True,
            "pgvector": ext is not None,
            "indexed_documents": int(docs["n"]) if docs else 0,
            "indexed_chunks": int(chunks["n"]) if chunks else 0,
        }
    except Exception as exc:
        return {"postgres": False, "pgvector": False, "error": str(exc)}
