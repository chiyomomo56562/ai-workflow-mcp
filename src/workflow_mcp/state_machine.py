"""Pure workflow transition rules and guards."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

from .models import ErrorCode, ReviewVerdict, WorkflowState

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
    (WorkflowState.PLANNING, WorkflowState.DISCOVERY),
    (WorkflowState.WAITING_APPROVAL, WorkflowState.DISCOVERY),
    (WorkflowState.IMPLEMENTING, WorkflowState.DISCOVERY),
}


class TransitionError(ValueError):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class TransitionContext:
    current_plan_version: int | None = None
    approved_plan_version: int | None = None
    requested_plan_version: int | None = None
    explicit_user_approval: bool = False
    implementation_within_scope: bool = True
    review_verdict: ReviewVerdict | str | None = None
    context_artifact: Mapping[str, object] | None = None
    user_content: str | None = None
    plan_artifact: Mapping[str, object] | None = None
    implementation_artifact: Mapping[str, object] | None = None
    review_artifact: Mapping[str, object] | None = None
    reason: str | None = None
    requested_context: list[str] | None = None
    needed_context: list[str] | None = None


@dataclass(frozen=True, slots=True)
class Transition:
    command: str
    from_state: WorkflowState
    to_state: WorkflowState
    effects: tuple[str, ...] = ()


def can_start() -> bool:
    return True


def initial_state() -> WorkflowState:
    return WorkflowState.DISCOVERY


def is_allowed_transition(from_state: WorkflowState | str, to_state: WorkflowState | str) -> bool:
    try:
        pair = (WorkflowState(from_state), WorkflowState(to_state))
    except ValueError:
        return False
    return pair in ALLOWED_TRANSITIONS


def _require_state(current: WorkflowState, expected: WorkflowState | tuple[WorkflowState, ...]) -> None:
    expected_states = expected if isinstance(expected, tuple) else (expected,)
    if current not in expected_states:
        raise TransitionError(ErrorCode.INVALID_STATE_TRANSITION, f"command is not allowed from {current.value}")


def _require_mapping(value: Mapping[str, object] | None, name: str, required: tuple[str, ...]) -> None:
    if value is None or any(key not in value for key in required):
        raise TransitionError(ErrorCode.INVALID_ARTIFACT, f"{name} is missing required fields")


def _require_nonempty(value: object, name: str) -> None:
    if value is None or (isinstance(value, str) and not value.strip()) or (isinstance(value, (list, tuple)) and not value):
        raise TransitionError(ErrorCode.INVALID_ARTIFACT, f"{name} must not be empty")


def _require_string_list(value: object, name: str) -> None:
    _require_nonempty(value, name)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise TransitionError(ErrorCode.INVALID_ARTIFACT, f"{name} must contain non-empty strings")


def transition(command: str, current_state: WorkflowState | str, context: TransitionContext | None = None) -> Transition:
    current = WorkflowState(current_state)
    ctx = context or TransitionContext()

    if command == "submit_context":
        _require_state(current, WorkflowState.DISCOVERY)
        _require_mapping(ctx.context_artifact, "ContextArtifact", ("id", "workflowId", "sources", "missingContext", "uncertainContext", "implementationRules", "createdAt"))
        return Transition(command, current, WorkflowState.PLANNING, ("store_context",))
    if command == "request_user_context":
        _require_state(current, WorkflowState.DISCOVERY)
        _require_nonempty(ctx.reason, "reason")
        _require_string_list(ctx.requested_context, "requestedContext")
        return Transition(command, current, WorkflowState.WAITING_CONTEXT_INPUT, ("store_context_requirement",))
    if command == "provide_user_context":
        _require_state(current, WorkflowState.WAITING_CONTEXT_INPUT)
        _require_nonempty(ctx.user_content, "content")
        return Transition(command, current, WorkflowState.DISCOVERY, ("store_user_context",))
    if command == "submit_plan":
        _require_state(current, WorkflowState.PLANNING)
        if ctx.plan_artifact is not None:
            _require_mapping(ctx.plan_artifact, "PlanArtifact", ("id", "workflowId", "version", "goal", "scope", "steps", "runtimeFlow", "tests", "assumptions", "risks", "createdAt"))
            for field in ("goal", "scope", "steps", "runtimeFlow", "tests"):
                _require_nonempty(ctx.plan_artifact.get(field), f"plan.{field}")
            tests = ctx.plan_artifact.get("tests")
            _require_mapping(tests if isinstance(tests, Mapping) else None, "plan.tests", ("happyPath", "edgeCases", "failurePaths"))
            for field in ("happyPath", "edgeCases", "failurePaths"):
                _require_nonempty(tests[field], f"plan.tests.{field}")  # type: ignore[index]
        else:
            raise TransitionError(ErrorCode.INVALID_ARTIFACT, "PlanArtifact is required")
        return Transition(command, current, WorkflowState.WAITING_APPROVAL, ("increment_plan_version", "invalidate_approval", "store_plan"))
    if command == "approve_plan":
        _require_state(current, WorkflowState.WAITING_APPROVAL)
        if ctx.current_plan_version is None:
            raise TransitionError(ErrorCode.PLAN_NOT_FOUND, "no current plan exists")
        if ctx.requested_plan_version != ctx.current_plan_version:
            raise TransitionError(ErrorCode.PLAN_VERSION_MISMATCH, "plan version does not match current plan")
        if not ctx.explicit_user_approval:
            raise TransitionError(ErrorCode.APPROVAL_REQUIRED, "explicit user approval is required")
        return Transition(command, current, WorkflowState.IMPLEMENTING, ("store_approval", "set_approved_plan_version"))
    if command == "require_context":
        _require_state(current, (WorkflowState.PLANNING, WorkflowState.WAITING_APPROVAL, WorkflowState.IMPLEMENTING, WorkflowState.REVIEWING))
        _require_nonempty(ctx.reason, "reason")
        _require_string_list(ctx.needed_context, "neededContext")
        return Transition(command, current, WorkflowState.DISCOVERY, ("store_context_requirement", "invalidate_approval"))
    if command == "complete_implementation":
        _require_state(current, WorkflowState.IMPLEMENTING)
        _require_mapping(ctx.implementation_artifact, "ImplementationArtifact", ("id", "workflowId", "planVersion", "changedFiles", "testsRun", "deviations", "result", "createdAt"))
        _require_nonempty(ctx.implementation_artifact.get("changedFiles"), "implementation.changedFiles")
        _require_nonempty(ctx.implementation_artifact.get("testsRun"), "implementation.testsRun")
        if ctx.implementation_artifact.get("planVersion") != ctx.current_plan_version:
            raise TransitionError(ErrorCode.PLAN_VERSION_MISMATCH, "implementation plan version does not match")
        if ctx.current_plan_version is None:
            raise TransitionError(ErrorCode.PLAN_NOT_FOUND, "no current plan exists")
        if ctx.approved_plan_version != ctx.current_plan_version:
            raise TransitionError(ErrorCode.PLAN_NOT_APPROVED, "current plan is not approved")
        if ctx.requested_plan_version != ctx.current_plan_version:
            raise TransitionError(ErrorCode.PLAN_VERSION_MISMATCH, "implementation plan version does not match")
        return Transition(command, current, WorkflowState.REVIEWING, ("store_implementation",))
    if command == "submit_review":
        _require_state(current, WorkflowState.REVIEWING)
        _require_mapping(ctx.review_artifact, "ReviewArtifact", ("id", "workflowId", "planVersion", "verdict", "planCompliance", "implementationRuleCompliance", "testCompliance", "scopeCompliance", "requirementCoverage", "createdAt"))
        if ctx.current_plan_version is not None and ctx.review_artifact.get("planVersion") != ctx.current_plan_version:
            raise TransitionError(ErrorCode.PLAN_VERSION_MISMATCH, "review plan version does not match")
        if ctx.review_verdict is None:
            raise TransitionError(ErrorCode.REVIEW_VERDICT_INVALID, "review verdict is required")
        try:
            verdict = ReviewVerdict(ctx.review_verdict)
        except ValueError as exc:
            raise TransitionError(ErrorCode.REVIEW_VERDICT_INVALID, "invalid review verdict") from exc
        if verdict is ReviewVerdict.PASSED:
            return Transition(command, current, WorkflowState.COMPLETED, ("store_review",))
        if verdict is ReviewVerdict.FIX_REQUIRED:
            if not ctx.implementation_within_scope:
                raise TransitionError(ErrorCode.CONTEXT_NOT_SUFFICIENT, "fix is outside approved plan scope")
            return Transition(command, current, WorkflowState.IMPLEMENTING, ("store_review", "keep_approval"))
        return Transition(command, current, WorkflowState.DISCOVERY, ("store_review", "invalidate_approval"))
    raise TransitionError(ErrorCode.INVALID_STATE_TRANSITION, f"unknown command: {command}")
