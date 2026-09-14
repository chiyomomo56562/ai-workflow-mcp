"""Phase 0 models for the minimum workflow vertical slice."""

from dataclasses import dataclass
from enum import StrEnum


class WorkflowState(StrEnum):
    DISCOVERY = "DISCOVERY"
    WAITING_CONTEXT_INPUT = "WAITING_CONTEXT_INPUT"
    PLANNING = "PLANNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    IMPLEMENTING = "IMPLEMENTING"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"


@dataclass(frozen=True, slots=True)
class Workflow:
    workflow_id: str
    task: str
    state: WorkflowState = WorkflowState.DISCOVERY
    session_id: str | None = None
    project_path: str | None = None
