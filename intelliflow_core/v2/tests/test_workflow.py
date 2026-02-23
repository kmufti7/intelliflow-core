"""
Tests for IntelliFlow v2 Workflow wrapper.

Test coverage:
    1. Workflow rejects non-Pydantic state at construction
    2. Workflow accepts valid IntelliFlowState subclass
    3. Interceptor slot is registered and callable
    4. run() returns Pydantic state object, not raw dict
    5. run() raises WorkflowNotCompiledError before compile()
    6. add_node() rejects unannotated functions
    7. Interceptor pass-through slot works correctly
"""

import pytest
from uuid import uuid4

from pydantic import BaseModel

from intelliflow_core.v2.runtime.exceptions import (
    InvalidStateSchemaError,
    WorkflowNotCompiledError,
)
from intelliflow_core.v2.runtime.interceptors import InterceptorNode
from intelliflow_core.v2.runtime.state import IntelliFlowState
from intelliflow_core.v2.runtime.workflow import Workflow


# --- Test fixtures ---


class SampleState(IntelliFlowState):
    """Concrete state subclass for testing."""

    value: str = ""
    counter: int = 0


class SampleInterceptor(InterceptorNode):
    """Concrete interceptor for testing."""

    @property
    def name(self) -> str:
        return "test_interceptor"

    def intercept(self, state: IntelliFlowState) -> IntelliFlowState:
        return state.model_copy(update={"metadata": {"intercepted": True}})


def sample_node(state: SampleState) -> dict:
    """A properly annotated node function."""
    return {"value": "processed", "step_name": "done"}


def increment_node(state: SampleState) -> dict:
    """Node that increments counter."""
    return {"counter": state.counter + 1}


# --- Test 1: Reject non-Pydantic state ---


class TestWorkflowStateValidation:
    """Tests for state schema validation at construction time."""

    def test_rejects_non_pydantic_dict(self) -> None:
        """Workflow rejects plain dict as state schema."""
        with pytest.raises(InvalidStateSchemaError):
            Workflow(state_schema=dict)

    def test_rejects_non_pydantic_class(self) -> None:
        """Workflow rejects arbitrary class as state schema."""

        class NotPydantic:
            pass

        with pytest.raises(InvalidStateSchemaError):
            Workflow(state_schema=NotPydantic)

    def test_rejects_string(self) -> None:
        """Workflow rejects non-type as state schema."""
        with pytest.raises(InvalidStateSchemaError):
            Workflow(state_schema="not a type")  # type: ignore[arg-type]

    def test_rejects_instance_instead_of_class(self) -> None:
        """Workflow rejects a Pydantic instance (must pass the class)."""
        with pytest.raises(InvalidStateSchemaError):
            Workflow(state_schema=SampleState())  # type: ignore[arg-type]


# --- Test 2: Accept valid IntelliFlowState subclass ---


class TestWorkflowAcceptsValidState:
    """Tests for valid state schema acceptance."""

    def test_accepts_intelliflow_state_subclass(self) -> None:
        """Workflow accepts a proper IntelliFlowState subclass."""
        wf = Workflow(state_schema=SampleState)
        assert wf.state_schema is SampleState

    def test_accepts_base_intelliflow_state(self) -> None:
        """Workflow accepts IntelliFlowState directly."""
        wf = Workflow(state_schema=IntelliFlowState)
        assert wf.state_schema is IntelliFlowState

    def test_accepts_plain_base_model(self) -> None:
        """Workflow accepts any Pydantic BaseModel subclass."""

        class PlainModel(BaseModel):
            x: int = 0

        wf = Workflow(state_schema=PlainModel)
        assert wf.state_schema is PlainModel


# --- Test 3: Interceptor slot registration ---


class TestInterceptorSlots:
    """Tests for interceptor slot registration and callable behavior."""

    def test_slot_registered_with_interceptor(self) -> None:
        """Interceptor slot is registered with a concrete interceptor."""
        wf = Workflow(state_schema=SampleState)
        interceptor = SampleInterceptor()
        wf.add_interceptor_slot("guard", interceptor)
        assert "guard" in wf.interceptor_slots
        assert wf.interceptor_slots["guard"] is interceptor

    def test_slot_registered_without_interceptor(self) -> None:
        """Interceptor slot can be reserved without an interceptor (None)."""
        wf = Workflow(state_schema=SampleState)
        wf.add_interceptor_slot("future_guard")
        assert "future_guard" in wf.interceptor_slots
        assert wf.interceptor_slots["future_guard"] is None

    def test_interceptor_as_node_function_callable(self) -> None:
        """InterceptorNode.as_node_function() returns a callable."""
        interceptor = SampleInterceptor()
        node_fn = interceptor.as_node_function()
        assert callable(node_fn)

    def test_interceptor_as_node_function_executes(self) -> None:
        """InterceptorNode.as_node_function() correctly processes state."""
        interceptor = SampleInterceptor()
        node_fn = interceptor.as_node_function()
        state = SampleState(value="test")
        result = node_fn(state)
        assert isinstance(result, dict)
        assert result["metadata"] == {"intercepted": True}


# --- Test 4: run() returns Pydantic state ---


class TestWorkflowRun:
    """Tests for run() returning Pydantic state objects."""

    def test_run_returns_pydantic_state(self) -> None:
        """run() returns a WorkflowResult wrapping a Pydantic state."""
        wf = Workflow(state_schema=SampleState)
        wf.add_node("process", sample_node)
        wf.add_edge("__start__", "process")
        wf.add_edge("process", "__end__")
        wf.compile()

        result = wf.run(SampleState(value="input"))
        assert result.success is True
        assert result.kill_switch_triggered is False
        assert isinstance(result.state, SampleState)
        assert result.state.value == "processed"
        assert result.state.step_name == "done"

    def test_run_preserves_workflow_id(self) -> None:
        """run() preserves the workflow_id through execution."""
        wf_id = uuid4()
        wf = Workflow(state_schema=SampleState)
        wf.add_node("process", sample_node)
        wf.add_edge("__start__", "process")
        wf.add_edge("process", "__end__")
        wf.compile()

        result = wf.run(SampleState(workflow_id=wf_id, value="input"))
        assert result.success is True
        assert isinstance(result.state, SampleState)
        assert result.state.workflow_id == wf_id


# --- Test 5: Guard rails ---


class TestWorkflowGuardRails:
    """Tests for error conditions and guard rails."""

    def test_run_before_compile_raises(self) -> None:
        """run() raises WorkflowNotCompiledError if compile() not called."""
        wf = Workflow(state_schema=SampleState)
        with pytest.raises(WorkflowNotCompiledError):
            wf.run(SampleState())

    def test_add_node_rejects_unannotated_function(self) -> None:
        """add_node() raises ValueError for functions without type annotations."""
        wf = Workflow(state_schema=SampleState)

        def bad_node(state):  # No annotation
            return {"value": "bad"}

        with pytest.raises(ValueError, match="type annotations"):
            wf.add_node("bad", bad_node)
