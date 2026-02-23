"""Tests for MCP Tool Registry — static catalog + dynamic scoping."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from intelliflow_core.v2.runtime.exceptions import (
    RegistryLockedError,
    ToolNotFoundError,
)
from intelliflow_core.v2.runtime.tool_registry import MCPRegistry, ToolSchema


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_tool(name: str = "test_tool", desc: str = "A test tool") -> ToolSchema:
    """Factory for valid ToolSchema instances."""
    return ToolSchema(
        name=name,
        description=desc,
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        callable=lambda x: x,
    )


# ---------------------------------------------------------------------------
# 1. Successful registration
# ---------------------------------------------------------------------------

class TestSuccessfulRegistration:
    def test_register_and_count(self) -> None:
        registry = MCPRegistry()
        registry.register(make_tool("tool_a", "First tool"))
        registry.register(make_tool("tool_b", "Second tool"))
        assert registry.tool_count() == 2


# ---------------------------------------------------------------------------
# 2. Duplicate name rejection
# ---------------------------------------------------------------------------

class TestDuplicateNameRejection:
    def test_duplicate_name_raises_value_error(self) -> None:
        registry = MCPRegistry()
        registry.register(make_tool("dup_tool"))
        with pytest.raises(ValueError, match="Duplicate tool name"):
            registry.register(make_tool("dup_tool", "Different description"))


# ---------------------------------------------------------------------------
# 3. Registry locks
# ---------------------------------------------------------------------------

class TestRegistryLocks:
    def test_lock_sets_locked_state(self) -> None:
        registry = MCPRegistry()
        registry.lock()
        assert registry.is_locked() is True


# ---------------------------------------------------------------------------
# 4. Register after lock raises RegistryLockedError
# ---------------------------------------------------------------------------

class TestRegisterAfterLockRaises:
    def test_register_after_lock(self) -> None:
        registry = MCPRegistry()
        registry.register(make_tool("before_lock"))
        registry.lock()
        with pytest.raises(RegistryLockedError):
            registry.register(make_tool("after_lock"))


# ---------------------------------------------------------------------------
# 5. get_tools returns correct subset
# ---------------------------------------------------------------------------

class TestGetToolsSubset:
    def test_returns_requested_tools_only(self) -> None:
        registry = MCPRegistry()
        registry.register(make_tool("alpha", "Alpha tool"))
        registry.register(make_tool("beta", "Beta tool"))
        registry.register(make_tool("gamma", "Gamma tool"))
        registry.lock()

        result = registry.get_tools(["alpha", "gamma"])
        names = [t.name for t in result]
        assert names == ["alpha", "gamma"]
        assert len(result) == 2


# ---------------------------------------------------------------------------
# 6. get_tools with unknown name raises ToolNotFoundError
# ---------------------------------------------------------------------------

class TestGetToolsUnknownName:
    def test_unknown_tool_raises(self) -> None:
        registry = MCPRegistry()
        registry.register(make_tool("known_tool"))
        registry.lock()

        with pytest.raises(ToolNotFoundError) as exc_info:
            registry.get_tools(["known_tool", "phantom"])
        assert "phantom" in exc_info.value.missing_names


# ---------------------------------------------------------------------------
# 7. get_all_tools returns complete catalog
# ---------------------------------------------------------------------------

class TestGetAllTools:
    def test_returns_all_registered(self) -> None:
        registry = MCPRegistry()
        registry.register(make_tool("x", "Tool X"))
        registry.register(make_tool("y", "Tool Y"))
        registry.register(make_tool("z", "Tool Z"))
        registry.lock()

        all_tools = registry.get_all_tools()
        assert len(all_tools) == 3
        names = {t.name for t in all_tools}
        assert names == {"x", "y", "z"}


# ---------------------------------------------------------------------------
# 8. is_locked state before and after lock
# ---------------------------------------------------------------------------

class TestIsLockedState:
    def test_unlocked_then_locked(self) -> None:
        registry = MCPRegistry()
        assert registry.is_locked() is False
        registry.lock()
        assert registry.is_locked() is True


# ---------------------------------------------------------------------------
# 9. ToolSchema requires description field
# ---------------------------------------------------------------------------

class TestDescriptionRequired:
    def test_missing_description_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            ToolSchema(
                name="no_desc",
                input_schema={"type": "object"},
                callable=lambda x: x,
            )


# ---------------------------------------------------------------------------
# 10. ToolSchema input_schema field
# ---------------------------------------------------------------------------

class TestInputSchemaField:
    def test_valid_input_schema_accepted(self) -> None:
        tool = ToolSchema(
            name="schema_tool",
            description="Tool with schema",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            callable=lambda x: x,
        )
        assert tool.input_schema["type"] == "object"
        assert "query" in tool.input_schema["properties"]


# ---------------------------------------------------------------------------
# 11. Scoped isolation — no cross-contamination between nodes
# ---------------------------------------------------------------------------

class TestScopedIsolation:
    def test_node_scoping_is_independent(self) -> None:
        registry = MCPRegistry()
        registry.register(make_tool("search", "Search tool"))
        registry.register(make_tool("write", "Write tool"))
        registry.register(make_tool("delete", "Delete tool"))
        registry.lock()

        node_a_tools = registry.get_tools(["search", "write"])
        node_b_tools = registry.get_tools(["write", "delete"])

        node_a_names = {t.name for t in node_a_tools}
        node_b_names = {t.name for t in node_b_tools}

        assert node_a_names == {"search", "write"}
        assert node_b_names == {"write", "delete"}
        assert "delete" not in node_a_names
        assert "search" not in node_b_names


# ---------------------------------------------------------------------------
# 12. Empty allowed_names returns empty list
# ---------------------------------------------------------------------------

class TestEmptyAllowedNames:
    def test_empty_list_returns_empty(self) -> None:
        registry = MCPRegistry()
        registry.register(make_tool("some_tool"))
        registry.lock()

        result = registry.get_tools([])
        assert result == []
