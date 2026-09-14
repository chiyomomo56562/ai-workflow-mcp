"""Application service for the Phase 0 in-memory workflow slice."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from .models import Workflow, WorkflowState


class WorkflowService:
    def __init__(self) -> None:
        self._workflows: dict[str, Workflow] = {}

    def start(
        self,
        task: str,
        session_id: str | None = None,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        workflow_id = str(uuid4())
        workflow = Workflow(workflow_id, task, WorkflowState.DISCOVERY, session_id, project_path)
        self._workflows[workflow_id] = workflow
        return {"ok": True, "workflowId": workflow_id, "state": workflow.state.value}

    def status(self, workflow_id: str) -> dict[str, Any]:
        workflow = self._workflows.get(workflow_id)
        if workflow is None:
            return {
                "ok": False,
                "error": {"code": "WORKFLOW_NOT_FOUND", "message": "Workflow does not exist."},
            }
        return {
            "ok": True,
            "workflowId": workflow.workflow_id,
            "state": workflow.state.value,
            "planVersion": None,
            "approvedPlanVersion": None,
            "latestArtifacts": {
                "contextId": None,
                "planId": None,
                "approvalId": None,
                "implementationId": None,
                "reviewId": None,
            },
        }

