import unittest

from workflow_mcp.models import ArtifactType, ErrorCode, ReviewVerdict, WorkflowState
from workflow_mcp.state_machine import TransitionContext, TransitionError, is_allowed_transition, transition


class StateMachineTests(unittest.TestCase):
    @staticmethod
    def review(verdict: str) -> dict[str, object]:
        return {"id": "r1", "workflowId": "w1", "planVersion": 1, "verdict": verdict, "planCompliance": {}, "implementationRuleCompliance": {}, "testCompliance": {}, "scopeCompliance": {}, "requirementCoverage": {}, "createdAt": "now"}

    def test_happy_path_commands(self) -> None:
        context = {key: [] for key in ("sources", "missingContext", "uncertainContext", "implementationRules")}
        context.update({"id": "c1", "workflowId": "w1", "createdAt": "now"})
        plan = {"id": "p1", "workflowId": "w1", "version": 1, "goal": "goal", "scope": {"included": ["x"]}, "steps": [{"id": "1"}], "runtimeFlow": ["flow"], "tests": {"happyPath": [{"id": "h"}], "edgeCases": [{"id": "e"}], "failurePaths": [{"id": "f"}]}, "assumptions": [], "risks": [], "createdAt": "now"}
        implementation = {"id": "i1", "workflowId": "w1", "planVersion": 1, "changedFiles": ["x"], "testsRun": [{"command": "test", "result": "passed"}], "deviations": [], "result": "completed", "createdAt": "now"}
        review = {"id": "r1", "workflowId": "w1", "planVersion": 1, "verdict": "passed", "planCompliance": {}, "implementationRuleCompliance": {}, "testCompliance": {}, "scopeCompliance": {}, "requirementCoverage": {}, "createdAt": "now"}
        self.assertEqual(transition("submit_context", WorkflowState.DISCOVERY, TransitionContext(context_artifact=context)).to_state, WorkflowState.PLANNING)
        self.assertEqual(
            transition("submit_plan", WorkflowState.PLANNING, TransitionContext(plan_artifact=plan)).to_state,
            WorkflowState.WAITING_APPROVAL,
        )
        self.assertEqual(
            transition(
                "approve_plan",
                WorkflowState.WAITING_APPROVAL,
                TransitionContext(current_plan_version=1, requested_plan_version=1, explicit_user_approval=True),
            ).to_state,
            WorkflowState.IMPLEMENTING,
        )
        self.assertEqual(
            transition(
                "complete_implementation",
                WorkflowState.IMPLEMENTING,
                TransitionContext(current_plan_version=1, approved_plan_version=1, requested_plan_version=1, implementation_artifact=implementation),
            ).to_state,
            WorkflowState.REVIEWING,
        )
        self.assertEqual(
            transition("submit_review", WorkflowState.REVIEWING, TransitionContext(review_verdict=ReviewVerdict.PASSED, current_plan_version=1, review_artifact=review)).to_state,
            WorkflowState.COMPLETED,
        )

    def test_context_and_review_branches(self) -> None:
        self.assertEqual(transition("request_user_context", "DISCOVERY", TransitionContext(reason="need input", requested_context=["choice"])).to_state, WorkflowState.WAITING_CONTEXT_INPUT)
        self.assertEqual(transition("provide_user_context", "WAITING_CONTEXT_INPUT", TransitionContext(user_content="provided")).to_state, WorkflowState.DISCOVERY)
        for state in (WorkflowState.PLANNING, WorkflowState.WAITING_APPROVAL, WorkflowState.IMPLEMENTING, WorkflowState.REVIEWING):
            self.assertEqual(transition("require_context", state, TransitionContext(reason="need detail", needed_context=["detail"])).to_state, WorkflowState.DISCOVERY)
        self.assertEqual(transition("submit_review", "REVIEWING", TransitionContext(current_plan_version=1, review_verdict="fix_required", review_artifact=self.review("fix_required"))).to_state, WorkflowState.IMPLEMENTING)
        self.assertEqual(transition("submit_review", "REVIEWING", TransitionContext(current_plan_version=1, review_verdict="context_required", review_artifact=self.review("context_required"))).to_state, WorkflowState.DISCOVERY)

    def test_guards_and_terminal_state(self) -> None:
        with self.assertRaises(TransitionError) as invalid:
            transition("approve_plan", "DISCOVERY")
        self.assertEqual(invalid.exception.code, ErrorCode.INVALID_STATE_TRANSITION)

        with self.assertRaises(TransitionError) as approval:
            transition("approve_plan", "WAITING_APPROVAL", TransitionContext(current_plan_version=1, requested_plan_version=1))
        self.assertEqual(approval.exception.code, ErrorCode.APPROVAL_REQUIRED)

        with self.assertRaises(TransitionError) as mismatch:
            transition("complete_implementation", "IMPLEMENTING", TransitionContext(current_plan_version=2, approved_plan_version=1, requested_plan_version=2, implementation_artifact={"id": "i1", "workflowId": "w1", "planVersion": 2, "changedFiles": ["x"], "testsRun": [{"command": "t", "result": "passed"}], "deviations": [], "result": "completed", "createdAt": "now"}))
        self.assertEqual(mismatch.exception.code, ErrorCode.PLAN_NOT_APPROVED)

        with self.assertRaises(TransitionError):
            transition("submit_review", "REVIEWING", TransitionContext(current_plan_version=1, review_verdict="unknown", review_artifact=self.review("unknown")))
        with self.assertRaises(TransitionError):
            transition("submit_context", "COMPLETED")

    def test_transition_table_and_enums(self) -> None:
        self.assertTrue(is_allowed_transition("REVIEWING", "COMPLETED"))
        self.assertFalse(is_allowed_transition("DISCOVERY", "COMPLETED"))
        self.assertEqual(ArtifactType.PLAN.value, "PLAN")
        self.assertEqual(ReviewVerdict.FIX_REQUIRED.value, "fix_required")

    def test_every_command_rejects_every_forbidden_state(self) -> None:
        commands = {
            "submit_context": {WorkflowState.DISCOVERY},
            "request_user_context": {WorkflowState.DISCOVERY},
            "provide_user_context": {WorkflowState.WAITING_CONTEXT_INPUT},
            "submit_plan": {WorkflowState.PLANNING},
            "approve_plan": {WorkflowState.WAITING_APPROVAL},
            "require_context": {WorkflowState.PLANNING, WorkflowState.WAITING_APPROVAL, WorkflowState.IMPLEMENTING, WorkflowState.REVIEWING},
            "complete_implementation": {WorkflowState.IMPLEMENTING},
            "submit_review": {WorkflowState.REVIEWING},
        }
        for command, allowed_states in commands.items():
            for state in WorkflowState:
                if state in allowed_states:
                    continue
                with self.assertRaises(TransitionError) as error:
                    transition(command, state)
                self.assertEqual(error.exception.code, ErrorCode.INVALID_STATE_TRANSITION, (command, state))

    def test_context_request_guards(self) -> None:
        for command, context in (
            ("request_user_context", TransitionContext(reason="", requested_context=["x"])),
            ("request_user_context", TransitionContext(reason="why", requested_context=[])),
            ("require_context", TransitionContext(reason="", needed_context=["x"])),
            ("require_context", TransitionContext(reason="why", needed_context=[""])),
        ):
            state = WorkflowState.DISCOVERY if command == "request_user_context" else WorkflowState.PLANNING
            with self.assertRaises(TransitionError) as error:
                transition(command, state, context)
            self.assertEqual(error.exception.code, ErrorCode.INVALID_ARTIFACT)
