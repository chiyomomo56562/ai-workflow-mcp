"""MCP entry point for the Phase 0 minimum vertical slice.

The in-memory store is intentionally temporary. Phase 1 replaces it with the
SQLite repository while keeping the tool contracts stable.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from .services import WorkflowService

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


def main() -> None:
    """Run the server over the default MCP transport."""
    mcp.run()


if __name__ == "__main__":
    main()
