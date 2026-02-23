"""
LangGraph workflow wrapper for IntelliFlow v2.

Provides a thin, opinionated wrapper around LangGraph's StateGraph that:
1. Enforces Pydantic BaseModel state schemas at construction time
2. Supports interceptor slots for governance hook points
3. Guarantees Pydantic-in / Pydantic-out via run()

Usage:
    from intelliflow_core.v2 import Workflow, IntelliFlowState

    class MyState(IntelliFlowState):
        value: str = ""

    def my_node(state: MyState) -> dict:
        return {"value": "processed", "step_name": "done"}

    wf = Workflow(state_schema=MyState)
    wf.add_node("process", my_node)
    wf.add_edge("__start__", "process")
    wf.add_edge("process", "__end__")
    wf.compile()

    result = wf.run(MyState(value="input"))
    assert isinstance(result, MyState)
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, Type

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from intelliflow_core.v2.runtime.contracts import WorkflowResult
from intelliflow_core.v2.runtime.exceptions import (
    InvalidStateSchemaError,
    KillSwitchTriggered,
    WORMStorageError,
    WorkflowNotCompiledError,
)
from intelliflow_core.v2.runtime.interceptors import InterceptorNode
from intelliflow_core.v2.runtime.state import IntelliFlowState

# TYPE_CHECKING import to avoid circular dependency at runtime
TYPE_CHECKING = False
if TYPE_CHECKING:
    from intelliflow_core.v2.storage.worm_logger import WORMLogRepository

# Type alias for node functions
NodeFunction = Callable[[Any], dict[str, Any]]


class Workflow:
    """
    Thin wrapper around LangGraph StateGraph with Pydantic enforcement.

    Guarantees:
        - State schema must be a Pydantic BaseModel subclass
        - run() accepts and returns Pydantic state, never raw dicts
        - Interceptor slots can be registered for future governance hooks
        - All node functions must have type annotations
    """

    def __init__(
        self,
        state_schema: Type[BaseModel],
        worm_logger: WORMLogRepository | None = None,
    ) -> None:
        """
        Initialize a new Workflow.

        Args:
            state_schema: A Pydantic BaseModel subclass (must inherit from BaseModel).
            worm_logger:  Optional WORMLogRepository for tamper-evident audit logging.
                          If None, no WORM logging occurs (preserves backward compat).

        Raises:
            InvalidStateSchemaError: If state_schema is not a BaseModel subclass.
        """
        if not (isinstance(state_schema, type) and issubclass(state_schema, BaseModel)):
            raise InvalidStateSchemaError(
                state_schema if isinstance(state_schema, type) else type(state_schema)
            )

        self._state_schema: Type[BaseModel] = state_schema
        self._graph_builder: StateGraph = StateGraph(state_schema)
        self._compiled_graph = None
        self._interceptor_slots: dict[str, InterceptorNode | None] = {}
        self._nodes: list[str] = []
        self._edges: list[tuple[str, str]] = []
        self._worm_logger = worm_logger

    @property
    def state_schema(self) -> Type[BaseModel]:
        """The Pydantic state schema for this workflow."""
        return self._state_schema

    @property
    def interceptor_slots(self) -> dict[str, InterceptorNode | None]:
        """Registry of named interceptor slots (name -> interceptor or None)."""
        return dict(self._interceptor_slots)

    def add_node(self, name: str, fn: NodeFunction) -> None:
        """
        Add a processing node to the workflow.

        Args:
            name: Unique name for this node.
            fn:   A callable that accepts state and returns a dict of updates.
                  Must have type annotations on its parameters.

        Raises:
            ValueError: If the node function lacks type annotations.
        """
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        if params and params[0].annotation is inspect.Parameter.empty:
            raise ValueError(
                f"Node function '{name}' must have type annotations. "
                f"Expected: def {name}(state: {self._state_schema.__name__}) -> dict"
            )

        self._graph_builder.add_node(name, fn)
        self._nodes.append(name)

    def add_edge(self, source: str, target: str) -> None:
        """
        Add a directed edge between two nodes.

        Use "__start__" for the graph entry point and "__end__" for terminal nodes.
        These map to LangGraph's START and END sentinels.

        Args:
            source: Source node name (or "__start__").
            target: Target node name (or "__end__").
        """
        src = START if source == "__start__" else source
        tgt = END if target == "__end__" else target

        self._graph_builder.add_edge(src, tgt)
        self._edges.append((source, target))

    def add_interceptor_slot(
        self,
        slot_name: str,
        interceptor: InterceptorNode | None = None,
    ) -> None:
        """
        Register a named interceptor slot in the workflow.

        An interceptor slot is a hook point between edges where governance
        checks can be injected. If an InterceptorNode is provided, it is
        registered immediately. If None, the slot is reserved for later
        population (e.g., kill-switch in Step 2).

        Args:
            slot_name:    Unique name for this interceptor slot.
            interceptor:  Optional InterceptorNode to register now.
        """
        self._interceptor_slots[slot_name] = interceptor

    def compile(self) -> None:
        """
        Compile the workflow graph.

        Injects interceptor slots as nodes, then compiles the underlying
        LangGraph StateGraph. Must be called before run().

        Interceptor slots with a registered InterceptorNode are injected
        as real processing nodes. Slots with None become pass-throughs.
        """
        for slot_name, interceptor in self._interceptor_slots.items():
            if interceptor is not None:
                node_fn = interceptor.as_node_function()
            else:
                def _make_passthrough(name: str) -> NodeFunction:
                    def _passthrough(state: Any) -> dict[str, Any]:
                        return {}
                    _passthrough.__name__ = f"slot_{name}"
                    return _passthrough

                node_fn = _make_passthrough(slot_name)

            if slot_name not in self._nodes:
                self._graph_builder.add_node(slot_name, node_fn)
                self._nodes.append(slot_name)

        self._compiled_graph = self._graph_builder.compile()

    def run(self, state: BaseModel) -> WorkflowResult:
        """
        Execute the compiled workflow with the given initial state.

        Accepts a Pydantic state, runs the graph, and returns a WorkflowResult.
        Kill-switch halts are captured gracefully — never raw exceptions to caller.

        Args:
            state: Initial state (must be an instance of this workflow's state_schema).

        Returns:
            WorkflowResult with success/failure status, final state, and any
            kill-switch details.

        Raises:
            WorkflowNotCompiledError: If compile() has not been called.
            InvalidStateSchemaError:  If state is not an instance of the state_schema.
        """
        if self._compiled_graph is None:
            raise WorkflowNotCompiledError()

        if not isinstance(state, self._state_schema):
            raise InvalidStateSchemaError(type(state))

        input_dict = state.model_dump()

        try:
            # WORM: log workflow start
            if self._worm_logger:
                try:
                    self._worm_logger.log_event(
                        trace_id=state.trace_id,
                        event_type="WORKFLOW_START",
                        payload={
                            "workflow_id": str(state.workflow_id),
                            "trace_id": state.trace_id,
                            "step_name": state.step_name,
                        },
                    )
                except WORMStorageError as worm_err:
                    return WorkflowResult(
                        success=False,
                        state=None,
                        kill_switch_triggered=False,
                        failed_rules=None,
                        error_message=str(worm_err),
                    )

            result_dict = self._compiled_graph.invoke(input_dict)
            final_state = self._state_schema(**result_dict)

            # WORM: log workflow end (success)
            if self._worm_logger:
                try:
                    self._worm_logger.log_event(
                        trace_id=state.trace_id,
                        event_type="WORKFLOW_END",
                        payload={
                            "workflow_id": str(state.workflow_id),
                            "trace_id": state.trace_id,
                            "success": True,
                        },
                    )
                except WORMStorageError as worm_err:
                    return WorkflowResult(
                        success=False,
                        state=None,
                        kill_switch_triggered=False,
                        failed_rules=None,
                        error_message=str(worm_err),
                    )

            return WorkflowResult(
                success=True,
                state=final_state,
                kill_switch_triggered=False,
                failed_rules=None,
                error_message=None,
            )
        except KillSwitchTriggered as e:
            # WORM: log kill-switch event
            if self._worm_logger:
                try:
                    self._worm_logger.log_event(
                        trace_id=state.trace_id,
                        event_type="KILL_SWITCH_TRIGGERED",
                        payload={
                            "trace_id": state.trace_id,
                            "failed_rules": [r.rule_id for r in e.failed_rules],
                            "state_snapshot": e.state_snapshot,
                        },
                    )
                except WORMStorageError as worm_err:
                    return WorkflowResult(
                        success=False,
                        state=None,
                        kill_switch_triggered=False,
                        failed_rules=None,
                        error_message=str(worm_err),
                    )

            return WorkflowResult(
                success=False,
                state=None,
                kill_switch_triggered=True,
                failed_rules=e.failed_rules,
                error_message=str(e),
            )
