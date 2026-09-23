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

