"""
Data contracts for IntelliFlow v2 workflows.

GovernanceRule — defines a single compliance rule for kill-switch evaluation.
WorkflowResult — structured return payload from Workflow.run().
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from intelliflow_core.v2.runtime.state import IntelliFlowState


@dataclass
class GovernanceRule:
    """
    A single governance rule evaluated by the kill-switch guard.

    Attributes:
        rule_id:     Unique identifier for this rule.
        description: Human-readable compliance rationale — required, not optional.
        logic:       Callable that accepts IntelliFlowState and returns bool.
                     True = pass, False = fail. Exceptions are treated as failures
                     (fail-closed).
    """

    rule_id: str
    description: str
    logic: Callable[[IntelliFlowState], bool]


@dataclass
class WorkflowResult:
    """
    Structured return payload from Workflow.run().

    Replaces raw exception propagation with a graceful result object.
    Callers inspect success/kill_switch_triggered instead of catching exceptions.

    Attributes:
        success:              True if workflow completed normally.
        state:                Final Pydantic state on success, None on kill-switch halt.
        kill_switch_triggered: True if a kill-switch guard halted execution.
        failed_rules:         List of GovernanceRule objects that failed (if kill-switch).
        error_message:        Human-readable error description (if any).
    """

    success: bool
    state: IntelliFlowState | None
    kill_switch_triggered: bool
    failed_rules: list[GovernanceRule] | None
    error_message: str | None
