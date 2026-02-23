"""
Append-only token accounting for LLM invocations.

Records input/output token counts and calculates cost at write time (immutable
receipt pattern — stored cost_usd is never recalculated on read). This is
financial telemetry, not compliance audit: no WORM hash-chaining, no SQLite
triggers.

Pricing:
    Static dict with Azure OpenAI rates (per 1K tokens). Override at runtime
    via INTELLIFLOW_TOKEN_PRICING_JSON env var (JSON string). In production,
    inject via KMS (e.g., AWS Secrets Manager, Azure Key Vault).

DLM:
    token_ledger table is append-only with no TTL. Production deployments
    need a Data Lifecycle Management policy (e.g., 90-day archival to cold
    storage) to prevent unbounded disk growth.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from intelliflow_core.v2.runtime.exceptions import TokenLedgerError
from intelliflow_core.v2.storage.db import DatabaseSessionManager

_TOKEN_PRICING_ENV = "INTELLIFLOW_TOKEN_PRICING_JSON"

# Azure OpenAI rates per 1K tokens (USD).
_MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 0.0025, "output": 0.0100},
    "gpt-4o-mini": {"input": 0.000150, "output": 0.000600},
    "text-embedding-3-small": {"input": 0.000020, "output": 0.0},
}


class TokenLedgerRepository:
    """Append-only token accounting with cost calculated at write time."""

    def __init__(self, db_manager: DatabaseSessionManager) -> None:
        self._db = db_manager
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create token_ledger table if not exists. Never truncates."""
        conn = self._db.get_connection()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS token_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                model_name TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                cost_usd REAL NOT NULL,
                workflow_id TEXT NOT NULL,
                module_name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

    def _get_pricing(self) -> dict[str, dict[str, float]]:
        """Return pricing dict from env var override or static default."""
        env_val = os.environ.get(_TOKEN_PRICING_ENV)
        if env_val:
            return json.loads(env_val)
        return _MODEL_PRICING

    def _calculate_cost(
        self,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """
        Calculate cost in USD for a single LLM invocation.

        Args:
            model_name: Must match a key in the pricing dict.
            input_tokens: Number of input tokens consumed.
            output_tokens: Number of output tokens generated.

        Raises:
            ValueError: If model_name is not in the pricing dict.
        """
        pricing = self._get_pricing()
        if model_name not in pricing:
            available = ", ".join(sorted(pricing.keys()))
            raise ValueError(
                f"Unknown model: {model_name}. "
                f"Available models: {available}"
            )
        rates = pricing[model_name]
        return (input_tokens / 1000) * rates["input"] + (output_tokens / 1000) * rates["output"]

    def record_invocation(
        self,
        trace_id: str,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        workflow_id: str,
        module_name: str,
    ) -> None:
        """
        Append a token consumption record to the ledger.

        Cost is calculated at write time and stored as an immutable receipt.

        Args:
            trace_id:      Workflow execution correlation ID.
            model_name:    LLM model identifier (must be in pricing dict).
            input_tokens:  Number of input tokens consumed.
            output_tokens: Number of output tokens generated.
            workflow_id:   Workflow instance identifier.
            module_name:   Module name (e.g., "supportflow", "careflow").

        Raises:
            ValueError: If model_name is unknown.
            TokenLedgerError: On any storage write failure.
        """
        cost_usd = self._calculate_cost(model_name, input_tokens, output_tokens)
        try:
            created_at = datetime.now(timezone.utc).isoformat()
            conn = self._db.get_connection()
            conn.execute(
                """
                INSERT INTO token_ledger
                    (trace_id, model_name, input_tokens, output_tokens, cost_usd,
                     workflow_id, module_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (trace_id, model_name, input_tokens, output_tokens, cost_usd,
                 workflow_id, module_name, created_at),
            )
            conn.commit()
        except TokenLedgerError:
            raise
        except Exception as e:
            raise TokenLedgerError(original_error=e) from e

    def get_workflow_cost(self, workflow_id: str) -> float:
        """Return aggregate cost in USD for a workflow."""
        conn = self._db.get_connection()
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) FROM token_ledger WHERE workflow_id = ?",
            (workflow_id,),
        ).fetchone()
        return row[0]

    def get_module_cost(self, module_name: str) -> float:
        """Return aggregate cost in USD for a module across all workflows."""
        conn = self._db.get_connection()
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) FROM token_ledger WHERE module_name = ?",
            (module_name,),
        ).fetchone()
        return row[0]

    def get_ledger(self, trace_id: str | None = None) -> list[dict]:
        """Return ledger entries as a list of dicts, optionally filtered by trace_id."""
        conn = self._db.get_connection()
        if trace_id:
            cursor = conn.execute(
                "SELECT id, trace_id, model_name, input_tokens, output_tokens, "
                "cost_usd, workflow_id, module_name, created_at "
                "FROM token_ledger WHERE trace_id = ? ORDER BY id ASC",
                (trace_id,),
            )
        else:
            cursor = conn.execute(
                "SELECT id, trace_id, model_name, input_tokens, output_tokens, "
                "cost_usd, workflow_id, module_name, created_at "
                "FROM token_ledger ORDER BY id ASC"
            )
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
