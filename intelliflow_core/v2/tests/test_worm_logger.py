"""Tests for WORM audit log — HMAC-SHA256 hash chain, SQLite triggers, fail-closed."""

from __future__ import annotations

import sqlite3
from uuid import uuid4

import pytest

from intelliflow_core.v2.runtime.contracts import GovernanceRule, WorkflowResult
from intelliflow_core.v2.runtime.exceptions import WORMStorageError
from intelliflow_core.v2.runtime.kill_switch import KillSwitchGuard
from intelliflow_core.v2.runtime.state import IntelliFlowState
from intelliflow_core.v2.runtime.workflow import Workflow
from intelliflow_core.v2.storage.db import DatabaseSessionManager
from intelliflow_core.v2.storage.worm_logger import WORMLogRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class WORMTestState(IntelliFlowState):
    """Minimal state for WORM integration tests."""
    value: str = ""


def passthrough_node(state: WORMTestState) -> dict:
    """Node that passes state through unchanged."""
    return {"value": "processed", "step_name": "done"}


def make_db() -> DatabaseSessionManager:
    """Create an in-memory DatabaseSessionManager for testing."""
    return DatabaseSessionManager(":memory:")


def make_worm(db: DatabaseSessionManager | None = None) -> tuple[DatabaseSessionManager, WORMLogRepository]:
    """Create a DB + WORM pair for testing."""
    db = db or make_db()
    return db, WORMLogRepository(db)


# ---------------------------------------------------------------------------
# 1. WORM table creation
# ---------------------------------------------------------------------------

class TestWORMTableCreation:
    def test_table_and_triggers_exist(self) -> None:
        db, _worm = make_worm()
        conn = db.get_connection()

        # Table exists
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='worm_log'"
        ).fetchall()
        assert len(tables) == 1

        # Triggers exist
        triggers = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'worm_%'"
        ).fetchall()
        trigger_names = {t[0] for t in triggers}
        assert "worm_no_update" in trigger_names
        assert "worm_no_delete" in trigger_names


# ---------------------------------------------------------------------------
# 2. Trigger blocks UPDATE
# ---------------------------------------------------------------------------

class TestTriggerBlocksUpdate:
    def test_update_raises_operational_error(self) -> None:
        db, worm = make_worm()
        worm.log_event("trace-1", "WORKFLOW_START", {"test": True})

        conn = db.get_connection()
        with pytest.raises(sqlite3.IntegrityError, match="WORM violation"):
            conn.execute("UPDATE worm_log SET event_type = 'TAMPERED' WHERE id = 1")


# ---------------------------------------------------------------------------
# 3. Trigger blocks DELETE
# ---------------------------------------------------------------------------

class TestTriggerBlocksDelete:
    def test_delete_raises_operational_error(self) -> None:
        db, worm = make_worm()
        worm.log_event("trace-1", "WORKFLOW_START", {"test": True})

        conn = db.get_connection()
        with pytest.raises(sqlite3.IntegrityError, match="WORM violation"):
            conn.execute("DELETE FROM worm_log WHERE id = 1")


# ---------------------------------------------------------------------------
# 4. Genesis entry
# ---------------------------------------------------------------------------

class TestGenesisEntry:
    def test_first_entry_has_genesis_prev_hash(self) -> None:
        _db, worm = make_worm()
        worm.log_event("trace-1", "WORKFLOW_START", {"first": True})

        chain = worm.get_chain()
        assert len(chain) == 1
        assert chain[0]["prev_hash"] == "GENESIS"


# ---------------------------------------------------------------------------
# 5. Hash chain links
# ---------------------------------------------------------------------------

class TestHashChainLinks:
    def test_second_entry_prev_hash_equals_first_entry_hash(self) -> None:
        _db, worm = make_worm()
        worm.log_event("trace-1", "WORKFLOW_START", {"step": 1})
        worm.log_event("trace-1", "WORKFLOW_END", {"step": 2})

        chain = worm.get_chain()
        assert len(chain) == 2
        assert chain[1]["prev_hash"] == chain[0]["entry_hash"]


# ---------------------------------------------------------------------------
# 6. Chain verification pass
# ---------------------------------------------------------------------------

class TestChainVerificationPass:
    def test_verify_chain_true_on_untampered_log(self) -> None:
        _db, worm = make_worm()
        worm.log_event("trace-1", "WORKFLOW_START", {"a": 1})
        worm.log_event("trace-1", "TOOL_EXECUTED", {"b": 2})
        worm.log_event("trace-1", "WORKFLOW_END", {"c": 3})

        assert worm.verify_chain() is True


# ---------------------------------------------------------------------------
# 7. Chain verification fail (tampered)
# ---------------------------------------------------------------------------

class TestChainVerificationFail:
    def test_verify_chain_false_after_tamper(self) -> None:
        db, worm = make_worm()
        worm.log_event("trace-1", "WORKFLOW_START", {"original": True})
        worm.log_event("trace-1", "WORKFLOW_END", {"original": True})

        # Bypass trigger to tamper with entry_hash
        conn = db.get_connection()
        conn.execute("DROP TRIGGER worm_no_update")
        conn.execute("UPDATE worm_log SET entry_hash = 'TAMPERED' WHERE id = 1")
        conn.commit()

        assert worm.verify_chain() is False


# ---------------------------------------------------------------------------
# 8. WORMStorageError on failure
# ---------------------------------------------------------------------------

class TestWORMStorageErrorOnFailure:
    def test_broken_db_raises_worm_storage_error(self) -> None:
        db = make_db()
        worm = WORMLogRepository(db)

        # Close the DB to force a write failure
        db.close()

        with pytest.raises(WORMStorageError):
            worm.log_event("trace-broken", "WORKFLOW_START", {"should": "fail"})


# ---------------------------------------------------------------------------
# 9. Workflow START + END logged
# ---------------------------------------------------------------------------

class TestWorkflowStartEndLogged:
    def test_workflow_run_logs_start_and_end(self) -> None:
        db, worm = make_worm()

        wf = Workflow(state_schema=WORMTestState, worm_logger=worm)
        wf.add_node("process", passthrough_node)
        wf.add_edge("__start__", "process")
        wf.add_edge("process", "__end__")
        wf.compile()

        state = WORMTestState(value="input")
        result = wf.run(state)

        assert result.success is True

        chain = worm.get_chain()
        event_types = [e["event_type"] for e in chain]
        assert "WORKFLOW_START" in event_types
        assert "WORKFLOW_END" in event_types


# ---------------------------------------------------------------------------
# 10. Kill-switch event logged
# ---------------------------------------------------------------------------

class TestKillSwitchEventLogged:
    def test_kill_switch_triggered_logged_to_worm(self) -> None:
        db, worm = make_worm()

        guard = KillSwitchGuard()
        guard.add_rule(GovernanceRule(
            rule_id="always_fail",
            description="Rule that always fails for testing",
            logic=lambda state: False,
        ))

        wf = Workflow(state_schema=WORMTestState, worm_logger=worm)
        wf.add_node("process", passthrough_node)
        wf.add_interceptor_slot("pre_check", guard)
        wf.add_edge("__start__", "pre_check")
        wf.add_edge("pre_check", "process")
        wf.add_edge("process", "__end__")
        wf.compile()

        state = WORMTestState(value="input")
        result = wf.run(state)

        assert result.success is False
        assert result.kill_switch_triggered is True

        chain = worm.get_chain()
        event_types = [e["event_type"] for e in chain]
        assert "WORKFLOW_START" in event_types
        assert "KILL_SWITCH_TRIGGERED" in event_types


# ---------------------------------------------------------------------------
# 11. TOOL_EXECUTED logged
# ---------------------------------------------------------------------------

class TestToolExecutedLogged:
    def test_tool_executed_event_in_chain(self) -> None:
        _db, worm = make_worm()

        trace_id = str(uuid4())
        worm.log_event(trace_id, "TOOL_EXECUTED", {
            "tool_name": "search",
            "node": "agent",
            "input": {"query": "test"},
        })

        chain = worm.get_chain()
        assert len(chain) == 1
        assert chain[0]["event_type"] == "TOOL_EXECUTED"
        assert chain[0]["trace_id"] == trace_id


# ---------------------------------------------------------------------------
# 12. Trace ID propagation
# ---------------------------------------------------------------------------

class TestTraceIdPropagation:
    def test_all_entries_share_same_trace_id(self) -> None:
        db, worm = make_worm()

        wf = Workflow(state_schema=WORMTestState, worm_logger=worm)
        wf.add_node("process", passthrough_node)
        wf.add_edge("__start__", "process")
        wf.add_edge("process", "__end__")
        wf.compile()

        state = WORMTestState(value="input")
        result = wf.run(state)

        assert result.success is True

        chain = worm.get_chain()
        assert len(chain) >= 2
        trace_ids = {e["trace_id"] for e in chain}
        assert len(trace_ids) == 1
        assert state.trace_id in trace_ids
