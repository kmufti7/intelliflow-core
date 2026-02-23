"""
Shared state schema for IntelliFlow v2 workflows.

All v2 workflow state must inherit from IntelliFlowState.
State is frozen by default — use model_copy(update={...}) to create
modified copies for state transitions.

Example:
    class MyWorkflowState(IntelliFlowState):
        patient_id: str
        a1c_value: float | None = None

    state = MyWorkflowState(
        workflow_id=uuid4(),
        step_name="intake",
        patient_id="P-001",
    )
    updated = state.model_copy(update={"step_name": "analysis", "a1c_value": 8.2})
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class IntelliFlowState(BaseModel):
    """
    Base state for all IntelliFlow v2 workflows.

    Required fields:
        workflow_id: Unique identifier for this workflow execution.
        step_name:   Current step/node name in the workflow.
        timestamp:   When this state snapshot was created.
        metadata:    Arbitrary key-value pairs for extensibility.
        trace_id:    WORM audit trail correlation ID (UUID4, auto-generated).

    Frozen by default. To update, use:
        new_state = state.model_copy(update={"step_name": "next_step"})
    """

    model_config = ConfigDict(frozen=True)

    workflow_id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier for this workflow execution",
    )
    step_name: str = Field(
        default="__start__",
        description="Current step/node name in the workflow",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this state snapshot was created (UTC)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary key-value pairs for extensibility",
    )
    trace_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="WORM audit trail correlation ID for this workflow execution",
    )
