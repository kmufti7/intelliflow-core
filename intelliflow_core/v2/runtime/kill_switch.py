"""
Kill-switch guard for IntelliFlow v2 workflows.

Deterministic governance enforcement: evaluates all rules against workflow
state and halts execution when any rule fails.

Invariants:
    - Fail-closed: any exception inside a rule's logic() is treated as failure.
    - Collect-all-failures: every rule is evaluated before raising. No short-circuit.
    - State immutability: intercept() never modifies the input state.
    - Zero rules = pass: an empty guard returns state immediately.
"""

from __future__ import annotations

from intelliflow_core.v2.runtime.contracts import GovernanceRule
from intelliflow_core.v2.runtime.exceptions import KillSwitchTriggered
from intelliflow_core.v2.runtime.interceptors import InterceptorNode
from intelliflow_core.v2.runtime.state import IntelliFlowState


class KillSwitchGuard(InterceptorNode):
    """
    Deterministic kill-switch interceptor.

    Evaluates a list of GovernanceRule objects against workflow state.
    If any rule fails (returns False or raises), halts execution via
    KillSwitchTriggered with the full failure set.
    """

    def __init__(self, name: str = "kill_switch_guard") -> None:
        self._name = name
        self._rules: list[GovernanceRule] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def rules(self) -> list[GovernanceRule]:
        """Defensive copy — callers cannot mutate internal rule list."""
        return list(self._rules)

    def add_rule(self, rule: GovernanceRule) -> None:
        """
        Register a governance rule.

        Raises:
            ValueError: If rule_id is duplicate or logic is not callable.
        """
        existing_ids = {r.rule_id for r in self._rules}
        if rule.rule_id in existing_ids:
            raise ValueError(
                f"Duplicate rule_id '{rule.rule_id}'. "
                f"Silent overwrite is a governance violation."
            )
        if not callable(rule.logic):
            raise ValueError(f"Rule '{rule.rule_id}' logic must be callable.")
        self._rules.append(rule)

    def intercept(self, state: IntelliFlowState) -> IntelliFlowState:
        """
        Evaluate all governance rules against the current state.

        Returns state unchanged if all rules pass. Raises KillSwitchTriggered
        with the full failure set if any rule fails.
        """
        if not self._rules:
            return state

        failed: list[GovernanceRule] = []

        for rule in self._rules:
            try:
                result = rule.logic(state)
                if not result:
                    failed.append(rule)
            except Exception:
                # FAIL-CLOSED: any exception = failure
                failed.append(rule)

        if failed:
            raise KillSwitchTriggered(
                failed_rules=failed,
                state_snapshot=state.model_dump(),
            )

        return state
