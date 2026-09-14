"""Small state-machine foundation used by the Phase 0 service layer."""

from .models import WorkflowState


TERMINAL_STATES = frozenset({WorkflowState.COMPLETED})


def can_start() -> bool:
    """Return whether a new workflow may be created."""
    return True


def initial_state() -> WorkflowState:
    return WorkflowState.DISCOVERY

