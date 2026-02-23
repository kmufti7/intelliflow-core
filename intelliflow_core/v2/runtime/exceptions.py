"""v2-specific exceptions for IntelliFlow Core."""

from __future__ import annotations


class V2WorkflowError(Exception):
    """Base exception for all v2 workflow errors."""


class InvalidStateSchemaError(V2WorkflowError):
    """Raised when a non-Pydantic BaseModel is provided as state schema."""

    def __init__(self, provided_type: type) -> None:
        self.provided_type = provided_type
        super().__init__(
            f"State schema must be a Pydantic BaseModel subclass, "
            f"got {provided_type.__name__}. "
            f"Hint: define your state as class MyState(IntelliFlowState): ..."
        )


class InterceptorNotImplementedError(V2WorkflowError):
    """Raised when an interceptor's intercept() method is called without implementation."""

    def __init__(self, interceptor_name: str) -> None:
        self.interceptor_name = interceptor_name
        super().__init__(
            f"Interceptor '{interceptor_name}' has not implemented intercept(). "
            f"Kill-switch guard implements this interface in Step 2."
        )


class WorkflowNotCompiledError(V2WorkflowError):
    """Raised when run() is called before compile()."""

    def __init__(self) -> None:
        super().__init__(
            "Workflow must be compiled before running. Call workflow.compile() first."
        )


class KillSwitchTriggered(V2WorkflowError):
    """Raised when one or more governance rules fail during kill-switch evaluation."""

    def __init__(
        self,
        failed_rules: list,
        state_snapshot: dict,
    ) -> None:
        self.failed_rules = failed_rules
        self.state_snapshot = state_snapshot
        rule_ids = ", ".join(r.rule_id for r in failed_rules)
        super().__init__(
            f"Kill-switch triggered: {len(failed_rules)} rule(s) failed [{rule_ids}]"
        )


class RegistryLockedError(V2WorkflowError):
    """Raised when register() is called after the registry is locked."""

    def __init__(self) -> None:
        super().__init__(
            "Registry is locked. Tools must be registered before lock() is called. "
            "Runtime tool registration is categorically rejected for audit safety."
        )


class ToolNotFoundError(V2WorkflowError):
    """Raised when get_tools() requests a tool name not in the registry."""

    def __init__(self, missing_names: list[str]) -> None:
        self.missing_names = missing_names
        super().__init__(
            f"Tool(s) not found in registry: {', '.join(missing_names)}. "
            f"All tools must be registered before lock()."
        )


class WORMStorageError(V2WorkflowError):
    """Raised when WORM audit log write fails — execution halted for compliance."""

    def __init__(self, original_error: Exception) -> None:
        self.original_error = original_error
        super().__init__(
            f"WORM log write failed — execution halted for compliance. "
            f"Original error: {original_error}"
        )


class TokenLedgerError(V2WorkflowError):
    """Raised when token ledger write fails — execution continues but cost is untracked."""

    def __init__(self, original_error: Exception) -> None:
        self.original_error = original_error
        super().__init__(
            f"Token ledger write failed — cost untracked. "
            f"Original error: {original_error}"
        )
