"""Small SQLite-backed project-memory store for the MVP.

This can later be swapped for PostgreSQL without changing the project-plan API.
"""

import json
import sqlite3
from pathlib import Path

from app.models import ProjectPlan

_DATABASE = Path(__file__).resolve().parents[2] / "data" / "projects.db"


def _connection() -> sqlite3.Connection:
    _DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(_DATABASE)
    connection.execute("CREATE TABLE IF NOT EXISTS project_versions (project_id TEXT NOT NULL, version INTEGER NOT NULL, plan_json TEXT NOT NULL, PRIMARY KEY(project_id, version))")
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

