"""Small SQLite-backed project-memory store for the MVP.

This can later be swapped for PostgreSQL without changing the project-plan API.
"""

import json
import sqlite3
from pathlib import Path

from app.models import BridgeProjectState, HouseProjectState, ProjectPlan

_DATABASE = Path(__file__).resolve().parents[2] / "data" / "projects.db"


def _connection() -> sqlite3.Connection:
    _DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(_DATABASE)
    connection.execute("CREATE TABLE IF NOT EXISTS project_versions (project_id TEXT NOT NULL, version INTEGER NOT NULL, plan_json TEXT NOT NULL, PRIMARY KEY(project_id, version))")
    connection.execute("CREATE TABLE IF NOT EXISTS design_versions (project_id TEXT NOT NULL, version INTEGER NOT NULL, design_json TEXT NOT NULL, PRIMARY KEY(project_id, version))")
    connection.execute("CREATE TABLE IF NOT EXISTS bridge_states (project_id TEXT PRIMARY KEY, state_json TEXT NOT NULL)")
    connection.execute("CREATE TABLE IF NOT EXISTS house_states (project_id TEXT PRIMARY KEY, state_json TEXT NOT NULL)")
    connection.execute("CREATE TABLE IF NOT EXISTS geometry_versions (project_id TEXT NOT NULL, version INTEGER NOT NULL, geometry_json TEXT NOT NULL, PRIMARY KEY(project_id, version))")
    connection.execute("CREATE TABLE IF NOT EXISTS parametric_versions (project_id TEXT NOT NULL, version INTEGER NOT NULL, parametric_json TEXT NOT NULL, PRIMARY KEY(project_id, version))")
    connection.execute("CREATE TABLE IF NOT EXISTS cad_reports (project_id TEXT NOT NULL, version INTEGER NOT NULL, report_json TEXT NOT NULL, PRIMARY KEY(project_id, version))")
    connection.execute("CREATE TABLE IF NOT EXISTS conversation_messages (project_id TEXT NOT NULL, sequence INTEGER NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(project_id, sequence))")
    # Phase 5.5 — Engineering Loads and Supports
    connection.execute("""
        CREATE TABLE IF NOT EXISTS engineering_loads (
            load_id TEXT PRIMARY KEY,
            model_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            model_revision TEXT NOT NULL,
            geometry_hash TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'FORCE',
            magnitude REAL NOT NULL,
            unit TEXT NOT NULL DEFAULT 'N',
            direction_x REAL NOT NULL DEFAULT 0.0,
            direction_y REAL NOT NULL DEFAULT 0.0,
            direction_z REAL NOT NULL DEFAULT -1.0,
            component_id TEXT NOT NULL,
            face_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS engineering_supports (
            support_id TEXT PRIMARY KEY,
            model_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            model_revision TEXT NOT NULL,
            geometry_hash TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'FIXED',
            component_id TEXT NOT NULL,
            face_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
    return connection


def save(plan: ProjectPlan) -> ProjectPlan:
    with _connection() as connection:
        connection.execute("INSERT INTO project_versions(project_id, version, plan_json) VALUES (?, ?, ?)", (plan.project_id, plan.version, plan.model_dump_json()))
    return plan


def latest(project_id: str) -> ProjectPlan | None:
    with _connection() as connection:
        row = connection.execute("SELECT plan_json FROM project_versions WHERE project_id = ? ORDER BY version DESC LIMIT 1", (project_id,)).fetchone()
    return ProjectPlan.model_validate(json.loads(row[0])) if row else None


def history(project_id: str) -> list[ProjectPlan]:
    with _connection() as connection:
        rows = connection.execute("SELECT plan_json FROM project_versions WHERE project_id = ? ORDER BY version", (project_id,)).fetchall()
    return [ProjectPlan.model_validate(json.loads(row[0])) for row in rows]


def save_design(project_id: str, version: int, design_json: str) -> None:
    with _connection() as connection:
        connection.execute("INSERT INTO design_versions(project_id, version, design_json) VALUES (?, ?, ?)", (project_id, version, design_json))


def latest_design(project_id: str) -> tuple[int, str] | None:
    with _connection() as connection:
        return connection.execute("SELECT version, design_json FROM design_versions WHERE project_id = ? ORDER BY version DESC LIMIT 1", (project_id,)).fetchone()


def save_bridge_state(state: BridgeProjectState) -> BridgeProjectState:
    with _connection() as connection:
        connection.execute("INSERT OR REPLACE INTO bridge_states(project_id, state_json) VALUES (?, ?)", (state.project_id, state.model_dump_json()))
    return state


def get_bridge_state(project_id: str) -> BridgeProjectState | None:
    with _connection() as connection:
        row = connection.execute("SELECT state_json FROM bridge_states WHERE project_id = ?", (project_id,)).fetchone()
    return BridgeProjectState.model_validate_json(row[0]) if row else None


def save_house_state(state: HouseProjectState) -> HouseProjectState:
    with _connection() as connection:
        connection.execute("INSERT OR REPLACE INTO house_states(project_id, state_json) VALUES (?, ?)", (state.project_id, state.model_dump_json()))
    return state


def get_house_state(project_id: str) -> HouseProjectState | None:
    with _connection() as connection:
        row = connection.execute("SELECT state_json FROM house_states WHERE project_id = ?", (project_id,)).fetchone()
    return HouseProjectState.model_validate_json(row[0]) if row else None



def save_geometry(project_id: str, version: int, geometry_json: str) -> None:
    with _connection() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO geometry_versions(project_id, version, geometry_json) VALUES (?, ?, ?)",
            (project_id, version, geometry_json),
        )


def latest_geometry(project_id: str) -> tuple[int, str] | None:
    with _connection() as connection:
        return connection.execute(
            "SELECT version, geometry_json FROM geometry_versions WHERE project_id = ? ORDER BY version DESC LIMIT 1",
            (project_id,),
        ).fetchone()


def save_parametric(project_id: str, version: int, parametric_json: str) -> None:
    with _connection() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO parametric_versions(project_id, version, parametric_json) VALUES (?, ?, ?)",
            (project_id, version, parametric_json),
        )


def latest_parametric(project_id: str) -> tuple[int, str] | None:
    with _connection() as connection:
        return connection.execute(
            "SELECT version, parametric_json FROM parametric_versions WHERE project_id = ? ORDER BY version DESC LIMIT 1",
            (project_id,),
        ).fetchone()


def save_cad_report(project_id: str, version: int, report_json: str) -> None:
    with _connection() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO cad_reports(project_id, version, report_json) VALUES (?, ?, ?)",
            (project_id, version, report_json),
        )


def latest_cad_report(project_id: str) -> tuple[int, str] | None:
    with _connection() as connection:
        return connection.execute(
            "SELECT version, report_json FROM cad_reports WHERE project_id = ? ORDER BY version DESC LIMIT 1",
            (project_id,),
        ).fetchone()


def save_conversation_turn(project_id: str, user_text: str, assistant_text: str) -> None:
    from datetime import datetime, timezone

    with _connection() as connection:
        start = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) FROM conversation_messages WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
        now = datetime.now(timezone.utc).isoformat()
        connection.executemany(
            "INSERT INTO conversation_messages(project_id, sequence, role, text, created_at) VALUES (?, ?, ?, ?, ?)",
            [
                (project_id, start + 1, "user", user_text, now),
                (project_id, start + 2, "assistant", assistant_text, now),
            ],
        )


def get_conversation(project_id: str) -> list[dict]:
    with _connection() as connection:
        rows = connection.execute(
            "SELECT role, text, created_at FROM conversation_messages WHERE project_id = ? ORDER BY sequence",
            (project_id,),
        ).fetchall()
    return [{"role": row[0], "text": row[1], "timestamp": row[2]} for row in rows]


def list_projects(limit: int = 50) -> list[ProjectPlan]:
    with _connection() as connection:
        rows = connection.execute(
            "SELECT p.plan_json FROM project_versions p "
            "JOIN (SELECT project_id, MAX(version) AS version FROM project_versions GROUP BY project_id) latest "
            "ON p.project_id = latest.project_id AND p.version = latest.version "
            "ORDER BY p.rowid DESC LIMIT ?",
            (max(1, min(limit, 100)),),
        ).fetchall()
    return [ProjectPlan.model_validate(json.loads(row[0])) for row in rows]


# ── Engineering Loads ───────────────────────────────────────────────────────

def save_engineering_load(row: dict) -> None:
    """Insert or replace an engineering load record."""
    with _connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO engineering_loads
               (load_id, model_id, project_id, model_revision, geometry_hash,
                type, magnitude, unit, direction_x, direction_y, direction_z,
                component_id, face_id, status, created_at, updated_at)
               VALUES (:load_id,:model_id,:project_id,:model_revision,:geometry_hash,
                       :type,:magnitude,:unit,:direction_x,:direction_y,:direction_z,
                       :component_id,:face_id,:status,:created_at,:updated_at)""",
            row,
        )


def get_engineering_loads(model_id: str) -> list[dict]:
    """Return all ACTIVE loads for a model ordered by created_at."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM engineering_loads WHERE model_id=? AND status='ACTIVE' ORDER BY created_at",
            (model_id,),
        ).fetchall()
        cols = [c[1] for c in conn.execute("PRAGMA table_info(engineering_loads)").fetchall()]
    return [dict(zip(cols, r)) for r in rows]


def delete_engineering_load(load_id: str) -> bool:
    """Soft-delete a load by setting status=DELETED. Returns True if found."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    with _connection() as conn:
        cur = conn.execute(
            "UPDATE engineering_loads SET status='DELETED', updated_at=? WHERE load_id=? AND status='ACTIVE'",
            (now, load_id),
        )
    return cur.rowcount > 0


# ── Engineering Supports ────────────────────────────────────────────────────

def save_engineering_support(row: dict) -> None:
    """Insert or replace an engineering support record."""
    with _connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO engineering_supports
               (support_id, model_id, project_id, model_revision, geometry_hash,
                type, component_id, face_id, status, created_at, updated_at)
               VALUES (:support_id,:model_id,:project_id,:model_revision,:geometry_hash,
                       :type,:component_id,:face_id,:status,:created_at,:updated_at)""",
            row,
        )


def get_engineering_supports(model_id: str) -> list[dict]:
    """Return all ACTIVE supports for a model ordered by created_at."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM engineering_supports WHERE model_id=? AND status='ACTIVE' ORDER BY created_at",
            (model_id,),
        ).fetchall()
        cols = [c[1] for c in conn.execute("PRAGMA table_info(engineering_supports)").fetchall()]
    return [dict(zip(cols, r)) for r in rows]


def delete_engineering_support(support_id: str) -> bool:
    """Soft-delete a support. Returns True if found."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    with _connection() as conn:
        cur = conn.execute(
            "UPDATE engineering_supports SET status='DELETED', updated_at=? WHERE support_id=? AND status='ACTIVE'",
            (now, support_id),
        )
    return cur.rowcount > 0