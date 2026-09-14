"""Application service for the Phase 1 workflow persistence slice."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from .db import connect, create_workflow, get_workflow_status, initialize


class WorkflowService:
    def __init__(self, database: str = "workflow-mcp.sqlite3") -> None:
        self.connection = connect(database)
        initialize(self.connection)

    def start(self, task: str, session_id: str | None = None, project_path: str | None = None) -> dict[str, Any]:
        if not isinstance(task, str) or not task.strip():
            return {"ok": False, "error": {"code": "VALIDATION_ERROR", "message": "task must be a non-empty string"}}
        return {"ok": True, **create_workflow(self.connection, str(uuid4()), task, session_id, project_path)}

    def status(self, workflow_id: str) -> dict[str, Any]:
        row = get_workflow_status(self.connection, workflow_id)
        if row is None:
            return {"ok": False, "error": {"code": "WORKFLOW_NOT_FOUND", "message": "Workflow does not exist."}}
        return {
            "ok": True,
            "workflowId": row["workflow_id"],
            "state": row["current_state"],
            "planVersion": row["current_plan_version"],
            "approvedPlanVersion": row["approved_plan_version"],
            "latestArtifacts": {"contextId": row["latest_context_id"], "planId": row["latest_plan_id"], "approvalId": row["latest_approval_id"], "implementationId": row["latest_implementation_id"], "reviewId": row["latest_review_id"]},
        }
