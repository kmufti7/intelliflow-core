"""Tests for Token FinOps Tracker — immutable receipt, cost aggregation, model validation."""

from __future__ import annotations

import pytest

from intelliflow_core.v2.runtime.exceptions import TokenLedgerError
from intelliflow_core.v2.storage.db import DatabaseSessionManager
from intelliflow_core.v2.storage.token_ledger import TokenLedgerRepository, _MODEL_PRICING


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_db() -> DatabaseSessionManager:
    """Create an in-memory DatabaseSessionManager for testing."""
    return DatabaseSessionManager(":memory:")


def make_ledger(
    db: DatabaseSessionManager | None = None,
) -> tuple[DatabaseSessionManager, TokenLedgerRepository]:
    """Create a DB + TokenLedgerRepository pair for testing."""
    db = db or make_db()
    return db, TokenLedgerRepository(db)


# ---------------------------------------------------------------------------
# 1. Table creation
# ---------------------------------------------------------------------------

class TestTableCreation:
    def test_token_ledger_table_exists(self) -> None:
        db, _ledger = make_ledger()
        conn = db.get_connection()

        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='token_ledger'"
        ).fetchall()
        assert len(tables) == 1


# ---------------------------------------------------------------------------
# 2. Idempotent init (no truncation)
# ---------------------------------------------------------------------------

class TestIdempotentInit:
    def test_data_persists_across_init_calls(self) -> None:
        db = make_db()
        ledger1 = TokenLedgerRepository(db)
        ledger1.record_invocation(
            trace_id="t-1", model_name="gpt-4o-mini",
            input_tokens=100, output_tokens=50,
            workflow_id="wf-1", module_name="supportflow",
        )

        # Second init on same DB — data must survive
        ledger2 = TokenLedgerRepository(db)
        entries = ledger2.get_ledger()
        assert len(entries) == 1
        assert entries[0]["trace_id"] == "t-1"


# ---------------------------------------------------------------------------
# 3. Cost calculation (input vs output multiplier)
# ---------------------------------------------------------------------------

class TestCostCalculation:
    def test_input_output_token_multiplier(self) -> None:
        _db, ledger = make_ledger()
        # gpt-4o: input $0.0025/1K, output $0.0100/1K
        # 100 input + 50 output → (100/1000)*0.0025 + (50/1000)*0.01 = 0.00025 + 0.0005 = 0.00075
        ledger.record_invocation(
            trace_id="t-calc", model_name="gpt-4o",
            input_tokens=100, output_tokens=50,
            workflow_id="wf-calc", module_name="test",
        )

        entries = ledger.get_ledger()
        assert len(entries) == 1
        assert entries[0]["cost_usd"] == pytest.approx(0.00075)


# ---------------------------------------------------------------------------
# 4. Unknown model raises ValueError
# ---------------------------------------------------------------------------

class TestUnknownModel:
    def test_unknown_model_raises_value_error(self) -> None:
        _db, ledger = make_ledger()

        with pytest.raises(ValueError, match="Unknown model: nonexistent"):
            ledger.record_invocation(
                trace_id="t-bad", model_name="nonexistent",
                input_tokens=10, output_tokens=10,
                workflow_id="wf-bad", module_name="test",
            )


# ---------------------------------------------------------------------------
# 5. Partial workflow — only recorded invocations persist
# ---------------------------------------------------------------------------

class TestPartialWorkflow:
    def test_partial_invocations_all_recorded(self) -> None:
        _db, ledger = make_ledger()

        # Record 3 of a planned 4 invocations
        for i in range(3):
            ledger.record_invocation(
                trace_id="t-partial", model_name="gpt-4o-mini",
                input_tokens=50, output_tokens=20,
                workflow_id="wf-partial", module_name="test",
            )
        # 4th never called — simulate crash/skip

        entries = ledger.get_ledger()
        assert len(entries) == 3


# ---------------------------------------------------------------------------
# 6. Workflow cost aggregation
# ---------------------------------------------------------------------------

class TestWorkflowCostAggregation:
    def test_get_workflow_cost_sums_correctly(self) -> None:
        _db, ledger = make_ledger()

        # 3 invocations for wf-1
        # gpt-4o-mini: input $0.000150/1K, output $0.000600/1K
        for _ in range(3):
            ledger.record_invocation(
                trace_id="t-agg", model_name="gpt-4o-mini",
                input_tokens=1000, output_tokens=500,
                workflow_id="wf-1", module_name="supportflow",
            )
        # Per invocation: (1000/1000)*0.000150 + (500/1000)*0.000600 = 0.000150 + 0.000300 = 0.000450
        # 3x = 0.001350
        assert ledger.get_workflow_cost("wf-1") == pytest.approx(0.001350)


# ---------------------------------------------------------------------------
# 7. Module cost aggregation across workflows
# ---------------------------------------------------------------------------

class TestModuleCostAggregation:
    def test_get_module_cost_across_workflows(self) -> None:
        _db, ledger = make_ledger()

        # Two workflows, same module
        ledger.record_invocation(
            trace_id="t-m1", model_name="gpt-4o-mini",
            input_tokens=1000, output_tokens=500,
            workflow_id="wf-A", module_name="careflow",
        )
        ledger.record_invocation(
            trace_id="t-m2", model_name="gpt-4o-mini",
            input_tokens=1000, output_tokens=500,
            workflow_id="wf-B", module_name="careflow",
        )

        # Each: 0.000450, total: 0.000900
        assert ledger.get_module_cost("careflow") == pytest.approx(0.000900)


# ---------------------------------------------------------------------------
# 8. Trace ID linking
# ---------------------------------------------------------------------------

class TestTraceIdLinking:
    def test_trace_id_matches_expected_value(self) -> None:
        _db, ledger = make_ledger()

        ledger.record_invocation(
            trace_id="abc-123", model_name="gpt-4o-mini",
            input_tokens=10, output_tokens=10,
            workflow_id="wf-link", module_name="test",
        )
        ledger.record_invocation(
            trace_id="other-456", model_name="gpt-4o-mini",
            input_tokens=10, output_tokens=10,
            workflow_id="wf-link", module_name="test",
        )

        filtered = ledger.get_ledger(trace_id="abc-123")
        assert len(filtered) == 1
        assert filtered[0]["trace_id"] == "abc-123"


# ---------------------------------------------------------------------------
# 9. Cost immutable at write time
# ---------------------------------------------------------------------------

class TestCostImmutableAtWriteTime:
    def test_cost_frozen_at_write_time(self) -> None:
        _db, ledger = make_ledger()

        # gpt-4o: 200 input, 100 output
        # (200/1000)*0.0025 + (100/1000)*0.01 = 0.0005 + 0.001 = 0.0015
        ledger.record_invocation(
            trace_id="t-frozen", model_name="gpt-4o",
            input_tokens=200, output_tokens=100,
            workflow_id="wf-frozen", module_name="test",
        )

        entries = ledger.get_ledger()
        assert entries[0]["cost_usd"] == pytest.approx(0.0015)


# ---------------------------------------------------------------------------
# 10. Zero token invocation
# ---------------------------------------------------------------------------

class TestZeroTokenInvocation:
    def test_zero_tokens_records_zero_cost(self) -> None:
        _db, ledger = make_ledger()

        ledger.record_invocation(
            trace_id="t-zero", model_name="gpt-4o",
            input_tokens=0, output_tokens=0,
            workflow_id="wf-zero", module_name="test",
        )

        entries = ledger.get_ledger()
        assert entries[0]["cost_usd"] == 0.0


# ---------------------------------------------------------------------------
# 11. Embedding model (zero output cost)
# ---------------------------------------------------------------------------

class TestEmbeddingModel:
    def test_embedding_model_zero_output_cost(self) -> None:
        _db, ledger = make_ledger()

        # text-embedding-3-small: input $0.000020/1K, output $0.0/1K
        ledger.record_invocation(
            trace_id="t-embed", model_name="text-embedding-3-small",
            input_tokens=1000, output_tokens=0,
            workflow_id="wf-embed", module_name="careflow",
        )

        entries = ledger.get_ledger()
        # (1000/1000)*0.000020 + 0 = 0.000020
        assert entries[0]["cost_usd"] == pytest.approx(0.000020)


# ---------------------------------------------------------------------------
# 12. Pricing drift isolation (immutable receipt proof)
# ---------------------------------------------------------------------------

class TestPricingDriftIsolation:
    def test_pricing_drift_isolation(self) -> None:
        _db, ledger = make_ledger()

        # Record at current pricing
        ledger.record_invocation(
            trace_id="t-drift", model_name="gpt-4o",
            input_tokens=1000, output_tokens=1000,
            workflow_id="wf-drift", module_name="test",
        )

        # Expected: (1000/1000)*0.0025 + (1000/1000)*0.01 = 0.0125
        original_cost = ledger.get_ledger()[0]["cost_usd"]
        assert original_cost == pytest.approx(0.0125)

        # Mutate the pricing dict in-memory (simulates price change)
        original_input = _MODEL_PRICING["gpt-4o"]["input"]
        _MODEL_PRICING["gpt-4o"]["input"] = 999.0
        try:
            # Stored cost must be unchanged — immutable receipt
            stored_cost = ledger.get_ledger()[0]["cost_usd"]
            assert stored_cost == pytest.approx(0.0125)
            assert stored_cost == original_cost
        finally:
            # Restore to avoid polluting other tests
            _MODEL_PRICING["gpt-4o"]["input"] = original_input


# ---------------------------------------------------------------------------
# 13. TokenLedgerError on failure
# ---------------------------------------------------------------------------

class TestTokenLedgerErrorOnFailure:
    def test_broken_db_raises_token_ledger_error(self) -> None:
        db = make_db()
        ledger = TokenLedgerRepository(db)

        # Close the DB to force a write failure
        db.close()

        with pytest.raises(TokenLedgerError):
            ledger.record_invocation(
                trace_id="t-broken", model_name="gpt-4o-mini",
                input_tokens=10, output_tokens=10,
                workflow_id="wf-broken", module_name="test",
            )
