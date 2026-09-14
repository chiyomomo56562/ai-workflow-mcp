"""State transition rules shared by the persistence and domain layers."""

from .models import WorkflowState


TERMINAL_STATES = frozenset({WorkflowState.COMPLETED})

ALLOWED_TRANSITIONS = {
    (WorkflowState.DISCOVERY, WorkflowState.PLANNING),
    (WorkflowState.DISCOVERY, WorkflowState.WAITING_CONTEXT_INPUT),
    (WorkflowState.WAITING_CONTEXT_INPUT, WorkflowState.DISCOVERY),
    (WorkflowState.PLANNING, WorkflowState.WAITING_APPROVAL),
    (WorkflowState.WAITING_APPROVAL, WorkflowState.IMPLEMENTING),
    (WorkflowState.IMPLEMENTING, WorkflowState.REVIEWING),
    (WorkflowState.REVIEWING, WorkflowState.COMPLETED),
    (WorkflowState.REVIEWING, WorkflowState.IMPLEMENTING),
    (WorkflowState.REVIEWING, WorkflowState.DISCOVERY),
}


def can_start() -> bool:
    """Return whether a new workflow may be created."""
    return True


def initial_state() -> WorkflowState:
    return WorkflowState.DISCOVERY


def is_allowed_transition(from_state: WorkflowState | str, to_state: WorkflowState | str) -> bool:
    return (WorkflowState(from_state), WorkflowState(to_state)) in ALLOWED_TRANSITIONS
