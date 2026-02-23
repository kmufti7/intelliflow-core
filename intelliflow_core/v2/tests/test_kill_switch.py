"""
Tests for IntelliFlow v2 Kill-Switch Guard.

Test coverage:
    1. All rules pass — state returned unchanged
    2. One rule fails — KillSwitchTriggered raised
    3. Multiple rules fail — all failures collected (no short-circuit)
    4. Kill-switch in workflow — WorkflowResult.kill_switch_triggered
    5. Zero rules — passes through
    6. State snapshot matches input state
    7. Fail-closed — exception in rule logic treated as failure
    8. State immutability — returned state is same object
"""

import pytest

from intelliflow_core.v2.runtime.contracts import GovernanceRule, WorkflowResult
from intelliflow_core.v2.runtime.exceptions import KillSwitchTriggered
from intelliflow_core.v2.runtime.kill_switch import KillSwitchGuard
from intelliflow_core.v2.runtime.state import IntelliFlowState
from intelliflow_core.v2.runtime.workflow import Workflow


# --- Test fixtures ---


class GuardTestState(IntelliFlowState):
    """State subclass for kill-switch tests."""

    score: float = 0.0
    label: str = ""


def passthrough_node(state: GuardTestState) -> dict:
    """Node that passes state through unchanged."""
    return {}


# --- Test 1: All rules pass ---


class TestAllRulesPass:
    """When all governance rules return True, state passes through."""

    def test_all_rules_pass(self) -> None:
        guard = KillSwitchGuard()
        guard.add_rule(
            GovernanceRule(
                rule_id="always_pass",
                description="Always passes",
                logic=lambda s: True,
            )
        )
        state = GuardTestState(score=0.5)
        result = guard.intercept(state)
        assert result is state


# --- Test 2: One rule fails ---


class TestOneRuleFails:
    """When a single rule returns False, KillSwitchTriggered is raised."""

    def test_one_rule_fails(self) -> None:
        guard = KillSwitchGuard()
        failing_rule = GovernanceRule(
            rule_id="score_check",
            description="Score must be below threshold",
            logic=lambda s: s.score < 1.0,
        )
        guard.add_rule(failing_rule)

        state = GuardTestState(score=5.0)
        with pytest.raises(KillSwitchTriggered) as exc_info:
            guard.intercept(state)

        assert failing_rule in exc_info.value.failed_rules
        assert len(exc_info.value.failed_rules) == 1


# --- Test 3: Multiple rules fail — collect all ---


class TestCollectAllFailures:
    """All rules are evaluated; no short-circuit on first failure."""

    def test_multiple_rules_fail_collects_all(self) -> None:
        guard = KillSwitchGuard()

        rule_a = GovernanceRule(
            rule_id="rule_a",
            description="Always passes",
            logic=lambda s: True,
        )
        rule_b = GovernanceRule(
            rule_id="rule_b",
            description="Always fails",
            logic=lambda s: False,
        )
        rule_c = GovernanceRule(
            rule_id="rule_c",
            description="Also fails",
            logic=lambda s: False,
        )

        guard.add_rule(rule_a)
        guard.add_rule(rule_b)
        guard.add_rule(rule_c)

        state = GuardTestState()
        with pytest.raises(KillSwitchTriggered) as exc_info:
            guard.intercept(state)

        failed = exc_info.value.failed_rules
        assert len(failed) == 2
        assert rule_b in failed
        assert rule_c in failed
        assert rule_a not in failed


# --- Test 4: Kill-switch in workflow returns WorkflowResult ---


class TestKillSwitchInWorkflow:
    """Full integration: kill-switch halts workflow, returns WorkflowResult."""

    def test_kill_switch_in_workflow_returns_result(self) -> None:
        guard = KillSwitchGuard()
        guard.add_rule(
            GovernanceRule(
                rule_id="block_all",
                description="Blocks everything",
                logic=lambda s: False,
            )
        )

        wf = Workflow(state_schema=GuardTestState)
        wf.add_interceptor_slot("guard", guard)
        wf.add_node("process", passthrough_node)
        wf.add_edge("__start__", "guard")
        wf.add_edge("guard", "process")
        wf.add_edge("process", "__end__")
        wf.compile()

        result = wf.run(GuardTestState(score=1.0))

        assert isinstance(result, WorkflowResult)
        assert result.success is False
        assert result.kill_switch_triggered is True
        assert result.state is None
        assert result.failed_rules is not None
        assert len(result.failed_rules) == 1
        assert result.error_message is not None


# --- Test 5: Zero rules passes ---


class TestZeroRules:
    """A guard with no rules always passes."""

    def test_zero_rules_passes(self) -> None:
        guard = KillSwitchGuard()
        state = GuardTestState(score=99.9)
        result = guard.intercept(state)
        assert result is state


# --- Test 6: State snapshot matches ---


class TestStateSnapshot:
    """KillSwitchTriggered carries an accurate state snapshot."""

    def test_state_snapshot_matches(self) -> None:
        guard = KillSwitchGuard()
        guard.add_rule(
            GovernanceRule(
                rule_id="fail",
                description="Always fails",
                logic=lambda s: False,
            )
        )

        state = GuardTestState(score=3.14, label="test")
        with pytest.raises(KillSwitchTriggered) as exc_info:
            guard.intercept(state)

        assert exc_info.value.state_snapshot == state.model_dump()


# --- Test 7: Fail-closed — exception in rule logic ---


class TestFailClosed:
    """Exceptions inside rule logic are treated as failures, not propagated."""

    def test_fail_closed_exception_in_rule(self) -> None:
        guard = KillSwitchGuard()
        guard.add_rule(
            GovernanceRule(
                rule_id="crasher",
                description="Rule that crashes",
                logic=lambda s: 1 / 0,  # ZeroDivisionError
            )
        )

        state = GuardTestState()
        with pytest.raises(KillSwitchTriggered) as exc_info:
            guard.intercept(state)

        assert len(exc_info.value.failed_rules) == 1
        assert exc_info.value.failed_rules[0].rule_id == "crasher"


# --- Test 8: State immutability ---


class TestStateImmutability:
    """intercept() returns the exact same state object (identity check)."""

    def test_immutability_state_unchanged(self) -> None:
        guard = KillSwitchGuard()
        guard.add_rule(
            GovernanceRule(
                rule_id="pass",
                description="Always passes",
                logic=lambda s: True,
            )
        )

        state = GuardTestState(score=1.0, label="original")
        result = guard.intercept(state)
        assert result is state  # Same object identity
