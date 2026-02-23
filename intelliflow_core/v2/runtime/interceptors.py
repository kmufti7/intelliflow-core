"""
Interceptor node base class for IntelliFlow v2 workflows.

Interceptors are injection points between workflow edges where
governance checks, kill-switches, or audit hooks can be inserted.

Architecture:
    Step 1 (this file): Define the InterceptorNode ABC.
    Step 2 (future):    Kill-switch guard implements this interface.
    Step 3 (future):    Governance interceptors for audit logging.

Usage:
    class KillSwitchGuard(InterceptorNode):
        @property
        def name(self) -> str:
            return "kill_switch"

        def intercept(self, state: IntelliFlowState) -> IntelliFlowState:
            if self.should_halt(state):
                raise WorkflowHaltedError(...)
            return state
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from intelliflow_core.v2.runtime.state import IntelliFlowState


class InterceptorNode(ABC):
    """
    Abstract base class for interceptor nodes.

    An interceptor sits between workflow edges and can inspect/modify
    state or halt execution. All interceptors must implement:
        - name (property): unique identifier for this interceptor
        - intercept(state): receives state, returns (possibly modified) state

    Kill-switch guard implements this interface in Step 2.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this interceptor, used as the node key in the graph."""
        ...

    @abstractmethod
    def intercept(self, state: IntelliFlowState) -> IntelliFlowState:
        """
        Process the workflow state at this intercept point.

        Args:
            state: Current workflow state (frozen Pydantic model).

        Returns:
            The state to pass to the next node. May be the same instance
            or a new instance via state.model_copy(update={...}).

        Raises:
            NotImplementedError: If called on the ABC directly.
        """
        ...

    def as_node_function(self) -> Callable[[Any], dict[str, Any]]:
        """
        Convert this interceptor to a LangGraph-compatible node function.

        Returns a function that accepts state, calls self.intercept(),
        and returns a dict update for LangGraph's state merge.
        """

        def _node_fn(state: IntelliFlowState) -> dict[str, Any]:
            result = self.intercept(state)
            return result.model_dump()

        _node_fn.__name__ = f"interceptor_{self.name}"
        _node_fn.__qualname__ = f"InterceptorNode.{self.name}"
        return _node_fn
