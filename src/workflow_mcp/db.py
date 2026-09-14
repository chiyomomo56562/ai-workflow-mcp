"""SQLite connection, migration, and transaction helpers for Phase 1."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from .models import WorkflowState
from .state_machine import is_allowed_transition

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def connect(database: str | Path = ":memory:") -> sqlite3.Connection:
    connection = sqlite3.connect(str(database))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
    for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = migration_path.stem
        if version in applied:
            continue
        with transaction(connection):
            connection.executescript(migration_path.read_text(encoding="utf-8"))
            connection.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)", (version, utc_now()))


@contextmanager
def transaction(connection: sqlite3.Connection) -> Generator[sqlite3.Connection, None, None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()


def validate_payload(payload: object) -> str:
    """Validate and serialize an object-shaped JSON payload."""
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def decode_payload(payload: str) -> dict[str, object]:
    decoded = json.loads(payload)
    if not isinstance(decoded, dict):
        raise ValueError("stored payload must be a JSON object")
    return decoded


def create_workflow(connection: sqlite3.Connection, workflow_id: str, task: str, session_id: str | None = None, project_path: str | None = None) -> dict[str, str]:
    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a non-empty string")
    now = utc_now()
    with transaction(connection):
        connection.execute(
            "INSERT INTO workflow (id, task, session_id, project_path, current_state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (workflow_id, task, session_id, project_path, WorkflowState.DISCOVERY.value, now, now),
        )
        connection.execute(
            "INSERT INTO workflow_event (workflow_id, event_type, from_state, to_state, payload, created_at) VALUES (?, 'WORKFLOW_STARTED', NULL, ?, ?, ?)",
            (workflow_id, WorkflowState.DISCOVERY.value, validate_payload({"task": task}), now),
        )
    return {"workflowId": workflow_id, "state": WorkflowState.DISCOVERY.value}


def get_workflow_status(connection: sqlite3.Connection, workflow_id: str) -> sqlite3.Row | None:
    return connection.execute("SELECT * FROM workflow_status_view WHERE workflow_id = ?", (workflow_id,)).fetchone()


def _insert_artifact(connection: sqlite3.Connection, artifact_id: str, workflow_id: str, artifact_type: str, payload: object, *, plan_version: int | None = None, created_at: str | None = None) -> None:
    connection.execute(
        "INSERT INTO artifact (id, workflow_id, artifact_type, plan_version, payload, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (artifact_id, workflow_id, artifact_type, plan_version, validate_payload(payload), created_at or utc_now()),
    )


def insert_artifact(connection: sqlite3.Connection, artifact_id: str, workflow_id: str, artifact_type: str, payload: object, *, plan_version: int | None = None, created_at: str | None = None) -> None:
    """Insert one validated Artifact atomically when called independently."""
    with transaction(connection):
        _insert_artifact(connection, artifact_id, workflow_id, artifact_type, payload, plan_version=plan_version, created_at=created_at)


def transition_workflow(connection: sqlite3.Connection, workflow_id: str, *, to_state: WorkflowState, event_type: str, artifact: dict[str, object] | None = None, plan_version: int | None = None) -> None:
    """Atomically update state and append optional Artifact plus Event."""
    now = utc_now()
    with transaction(connection):
        row = connection.execute("SELECT current_state FROM workflow WHERE id = ?", (workflow_id,)).fetchone()
        if row is None:
            raise KeyError(f"workflow does not exist: {workflow_id}")
        if not is_allowed_transition(row[0], to_state):
            raise ValueError(f"invalid state transition: {row[0]} -> {to_state.value}")
        if artifact is not None:
            _insert_artifact(connection, str(artifact["id"]), workflow_id, str(artifact["artifact_type"]), artifact["payload"], plan_version=plan_version, created_at=now)
        connection.execute("UPDATE workflow SET current_state = ?, updated_at = ? WHERE id = ?", (to_state.value, now, workflow_id))
        connection.execute(
            "INSERT INTO workflow_event (workflow_id, event_type, from_state, to_state, plan_version, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (workflow_id, event_type, row[0], to_state.value, plan_version, validate_payload(artifact or {}), now),
        )
