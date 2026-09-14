"""MCP entry point for the Phase 0 minimum vertical slice.

The in-memory store is intentionally temporary. Phase 1 replaces it with the
SQLite repository while keeping the tool contracts stable.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from mcp.server.mcpserver import MCPServer

from .services import WorkflowService
from .models import ReviewVerdict
from .state_machine import TransitionContext, TransitionError

from .spec_loader import load_spec


SPEC = load_spec()
mcp = MCPServer("workflow-mcp", version="0.1.0")
_service = WorkflowService()


def _validation_error(message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": "VALIDATION_ERROR", "message": message}}


@mcp.tool()
def workflow_start(
    task: str,
    session_id: str | None = None,
    project_path: str | None = None,
) -> dict[str, Any]:
    """Create a workflow in DISCOVERY state."""
    if not isinstance(task, str) or not task.strip():
        return _validation_error("task must be a non-empty string")

    return _service.start(task, session_id, project_path)


@mcp.tool()
def workflow_status(workflow_id: str) -> dict[str, Any]:
    """Read the current state of a workflow."""
    if not isinstance(workflow_id, str) or not workflow_id.strip():
        return _validation_error("workflow_id must be a non-empty string")

    return _service.status(workflow_id)


def _command_error(error: Exception) -> dict[str, Any]:
    code = getattr(error, "code", "INVALID_ARTIFACT")
    return {"ok": False, "error": {"code": getattr(code, "value", code), "message": str(error)}}


def _run(command: str, workflow_id: str, context: TransitionContext, *, artifact: dict[str, object] | None = None, event_type: str, plan_version: int | None = None, current_plan_version: int | None = None, approved_plan_version: int | None = None, clear_approved_plan_version: bool = False) -> dict[str, Any]:
    try:
        return _service.command(command, workflow_id, context=context, artifact=artifact, event_type=event_type, plan_version=plan_version, current_plan_version=current_plan_version, approved_plan_version=approved_plan_version, clear_approved_plan_version=clear_approved_plan_version)
    except (KeyError, ValueError) as error:
        return _command_error(error)


@mcp.tool()
def submit_context(workflow_id: str, context: dict[str, object]) -> dict[str, Any]:
    return _run("submit_context", workflow_id, TransitionContext(context_artifact=context), artifact={"id": context.get("id"), "artifact_type": "CONTEXT", "payload": context}, event_type="DISCOVERY_COMPLETED")


@mcp.tool()
def request_user_context(workflow_id: str, reason: str, requested_context: list[str]) -> dict[str, Any]:
    payload = {"id": str(uuid4()), "workflowId": workflow_id, "reason": reason, "requestedContext": requested_context, "createdAt": "runtime"}
    return _run("request_user_context", workflow_id, TransitionContext(reason=reason, requested_context=requested_context), artifact={"id": payload["id"], "artifact_type": "USER_CONTEXT_REQUEST", "payload": payload}, event_type="USER_CONTEXT_REQUIRED")


@mcp.tool()
def provide_user_context(workflow_id: str, content: str) -> dict[str, Any]:
    payload = {"id": str(uuid4()), "workflowId": workflow_id, "content": content, "createdAt": "runtime"}
    return _run("provide_user_context", workflow_id, TransitionContext(user_content=content), artifact={"id": payload["id"], "artifact_type": "USER_CONTEXT_RESPONSE", "payload": payload}, event_type="CONTEXT_PROVIDED")


@mcp.tool()
def submit_plan(workflow_id: str, plan: dict[str, object]) -> dict[str, Any]:
    status = _service.status(workflow_id)
    version = (status.get("planVersion") or 0) + 1 if status.get("ok") else None
    normalized = {**plan, "version": version}
    return _run("submit_plan", workflow_id, TransitionContext(plan_artifact=normalized), artifact={"id": normalized.get("id"), "artifact_type": "PLAN", "payload": normalized}, event_type="PLAN_CREATED", plan_version=version, current_plan_version=version, clear_approved_plan_version=True)


@mcp.tool()
def approve_plan(workflow_id: str, plan_version: int) -> dict[str, Any]:
    status = _service.status(workflow_id)
    current = status.get("planVersion") if status.get("ok") else None
    approval = {"id": f"approval-{workflow_id}-{plan_version}", "workflowId": workflow_id, "planVersion": plan_version, "approved": True, "approvedAt": "runtime"}
    return _run("approve_plan", workflow_id, TransitionContext(current_plan_version=current, requested_plan_version=plan_version, explicit_user_approval=True), artifact={"id": approval["id"], "artifact_type": "APPROVAL", "payload": approval}, event_type="PLAN_APPROVED", plan_version=plan_version, approved_plan_version=plan_version)


@mcp.tool()
def require_context(workflow_id: str, reason: str, needed_context: list[str]) -> dict[str, Any]:
    payload = {"id": str(uuid4()), "workflowId": workflow_id, "reason": reason, "neededContext": needed_context, "createdAt": "runtime"}
    return _run("require_context", workflow_id, TransitionContext(reason=reason, needed_context=needed_context), artifact={"id": payload["id"], "artifact_type": "CONTEXT_REQUIREMENT", "payload": payload}, event_type="CONTEXT_REQUIRED", clear_approved_plan_version=True)


@mcp.tool()
def complete_implementation(workflow_id: str, implementation: dict[str, object]) -> dict[str, Any]:
    status = _service.status(workflow_id)
    current = status.get("planVersion") if status.get("ok") else None
    approved = status.get("approvedPlanVersion") if status.get("ok") else None
    version = implementation.get("planVersion")
    return _run("complete_implementation", workflow_id, TransitionContext(current_plan_version=current, approved_plan_version=approved, requested_plan_version=version if isinstance(version, int) else None, implementation_artifact=implementation), artifact={"id": implementation.get("id"), "artifact_type": "IMPLEMENTATION", "payload": implementation}, event_type="IMPLEMENTATION_COMPLETED", plan_version=version if isinstance(version, int) else None)


@mcp.tool()
def submit_review(workflow_id: str, review: dict[str, object]) -> dict[str, Any]:
    status = _service.status(workflow_id)
    current = status.get("planVersion") if status.get("ok") else None
    verdict = review.get("verdict")
    return _run("submit_review", workflow_id, TransitionContext(current_plan_version=current, requested_plan_version=review.get("planVersion") if isinstance(review.get("planVersion"), int) else None, review_verdict=verdict if isinstance(verdict, str) else None, review_artifact=review), artifact={"id": review.get("id"), "artifact_type": "REVIEW", "payload": review}, event_type={"passed": "REVIEW_PASSED", "fix_required": "REVIEW_FIX_REQUIRED", "context_required": "REVIEW_CONTEXT_REQUIRED"}.get(str(verdict), "REVIEW_PASSED"), plan_version=current if isinstance(current, int) else None)


def main() -> None:
    """Run the server over the default MCP transport."""
    mcp.run()


if __name__ == "__main__":
    main()
