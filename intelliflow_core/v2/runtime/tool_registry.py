"""
MCP Tool Registry for IntelliFlow v2 workflows.

Static tool catalog with dynamic per-node scoping. Tools are registered
at import time, the registry locks after initialization, and runtime
registration is categorically rejected.

Invariants:
    - Immutable after lock(): no new tools can be registered.
    - Thread-safe: all mutations under threading.Lock.
    - Pydantic-validated: ToolSchema validation happens at register() time.
    - Dynamic scoping: get_tools(allowed_names) returns node-specific subsets.
    - Defensive copies: get_all_tools() returns a copy, not internal state.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict

from intelliflow_core.v2.runtime.exceptions import (
    RegistryLockedError,
    ToolNotFoundError,
)


class ToolSchema(BaseModel):
    """
    Schema for a registered MCP tool.

    Attributes:
        name:         Unique tool identifier.
        description:  Human-readable purpose — required, not optional.
                      Same self-documenting principle as GovernanceRule.
        input_schema: JSON Schema dict describing the tool's expected input.
        callable:     The actual function to invoke.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    description: str
    input_schema: dict[str, Any]
    callable: Callable


class MCPRegistry:
    """
    Static MCP tool catalog with dynamic per-node scoping.

    Tools are registered at import time via explicit register() calls.
    After lock() is called, the registry becomes immutable — any attempt
    to register a new tool raises RegistryLockedError.

    Dynamic scoping: get_tools(allowed_names) returns only the tools
    whose names are in allowed_names, enforcing Least-Privilege Access
    per workflow node.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolSchema] = {}
        self._locked: bool = False
        self._lock = threading.Lock()

    def register(self, tool: ToolSchema) -> None:
        """
        Register a tool in the catalog.

        Raises:
            RegistryLockedError: If the registry has been locked.
            ValueError: If a tool with the same name is already registered.
        """
        with self._lock:
            if self._locked:
                raise RegistryLockedError()
            if tool.name in self._tools:
                raise ValueError(
                    f"Duplicate tool name '{tool.name}'. "
                    f"Silent overwrite is a governance violation."
                )
            self._tools[tool.name] = tool

    def lock(self) -> None:
        """Lock the registry. No new tools can be registered after this."""
        with self._lock:
            self._locked = True

    def is_locked(self) -> bool:
        """Check whether the registry is locked."""
        return self._locked

    def tool_count(self) -> int:
        """Return the number of registered tools."""
        return len(self._tools)

    def get_tools(self, allowed_names: list[str]) -> list[ToolSchema]:
        """
        Return the subset of tools matching allowed_names.

        Enforces Least-Privilege Access: each workflow node receives
        only its authorized tool subset.

        Args:
            allowed_names: List of tool names this node is authorized to use.
                           Empty list returns empty list (not an error).

        Raises:
            ToolNotFoundError: If any name in allowed_names is not registered.
        """
        if not allowed_names:
            return []
        missing = [n for n in allowed_names if n not in self._tools]
        if missing:
            raise ToolNotFoundError(missing)
        return [self._tools[n] for n in allowed_names]

    def get_all_tools(self) -> list[ToolSchema]:
        """Defensive copy — callers cannot mutate internal tool dict."""
        return list(self._tools.values())
