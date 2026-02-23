"""
IntelliFlow Core v2 — LangGraph-based workflow runtime.

Strangler Fig migration: v1 (intelliflow_core.*) remains unchanged.
v2 is an opt-in sub-package requiring Python >=3.10 and langgraph>=0.2.

Usage:
    from intelliflow_core.v2 import Workflow, IntelliFlowState, InterceptorNode
"""

from __future__ import annotations

import sys

if sys.version_info < (3, 10):
    raise RuntimeError(
        "intelliflow_core.v2 requires Python >=3.10 (LangGraph requirement). "
        "v1 (intelliflow_core.*) still supports Python >=3.9."
    )

from intelliflow_core.v2.runtime.contracts import GovernanceRule, WorkflowResult
from intelliflow_core.v2.runtime.exceptions import (
    InterceptorNotImplementedError,
    InvalidStateSchemaError,
    KillSwitchTriggered,
    RegistryLockedError,
    TokenLedgerError,
    ToolNotFoundError,
    V2WorkflowError,
    WORMStorageError,
    WorkflowNotCompiledError,
)
from intelliflow_core.v2.runtime.interceptors import InterceptorNode
from intelliflow_core.v2.runtime.kill_switch import KillSwitchGuard
from intelliflow_core.v2.runtime.state import IntelliFlowState
from intelliflow_core.v2.runtime.tool_registry import MCPRegistry, ToolSchema
from intelliflow_core.v2.runtime.workflow import Workflow
from intelliflow_core.v2.storage import DatabaseSessionManager, TokenLedgerRepository, WORMLogRepository

__all__ = [
    "Workflow",
    "IntelliFlowState",
    "InterceptorNode",
    "GovernanceRule",
    "WorkflowResult",
    "KillSwitchGuard",
    "MCPRegistry",
    "ToolSchema",
    "V2WorkflowError",
    "InvalidStateSchemaError",
    "InterceptorNotImplementedError",
    "KillSwitchTriggered",
    "RegistryLockedError",
    "ToolNotFoundError",
    "WORMStorageError",
    "WorkflowNotCompiledError",
    "DatabaseSessionManager",
    "TokenLedgerRepository",
    "WORMLogRepository",
    "TokenLedgerError",
]
