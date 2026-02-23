"""
WORM (Write-Once, Read-Many) audit log repository.

Provides tamper-evident, append-only logging for IntelliFlow v2 governance events.
Each entry is chained via HMAC-SHA256 — without the secret key, the chain cannot
be mathematically forged. SQLite BEFORE UPDATE/DELETE triggers enforce Write-Once
immutability at the database layer.

Invariants:
    - First entry: prev_hash = "GENESIS"
    - Each subsequent entry: prev_hash = previous entry's entry_hash
    - entry_hash = HMAC-SHA256(key, prev_hash|event_type|payload|timestamp)
    - UPDATE and DELETE are physically rejected by SQLite triggers
    - Any write failure raises WORMStorageError (fail-closed)

Secret key:
    In production, inject via KMS (e.g., AWS Secrets Manager, Azure Key Vault).
    Default key "dev-insecure-key-replace-in-production" prevents chain
    recalculation attacks only when the key is unknown to the attacker.
    Set via environment variable INTELLIFLOW_WORM_KEY.

Event types:
    WORKFLOW_START, WORKFLOW_END, TOOL_EXECUTED, KILL_SWITCH_TRIGGERED
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone

from intelliflow_core.v2.runtime.exceptions import WORMStorageError
from intelliflow_core.v2.storage.db import DatabaseSessionManager

_WORM_KEY_ENV = "INTELLIFLOW_WORM_KEY"
_DEFAULT_KEY = "dev-insecure-key-replace-in-production"
_GENESIS = "GENESIS"


class WORMLogRepository:
    """Append-only audit log with HMAC-SHA256 hash chain and SQLite trigger enforcement."""

    def __init__(self, db_manager: DatabaseSessionManager) -> None:
        self._db = db_manager
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create worm_log table and BEFORE UPDATE/DELETE triggers if not exists."""
        conn = self._db.get_connection()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS worm_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                entry_hash TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS worm_no_update
            BEFORE UPDATE ON worm_log
            BEGIN
                SELECT RAISE(ABORT, 'WORM violation: updates forbidden');
            END
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS worm_no_delete
            BEFORE DELETE ON worm_log
            BEGIN
                SELECT RAISE(ABORT, 'WORM violation: deletes forbidden');
            END
            """
        )
        conn.commit()

    def _get_key(self) -> bytes:
        """Return HMAC key from environment or default."""
        return os.environ.get(_WORM_KEY_ENV, _DEFAULT_KEY).encode("utf-8")

    def _compute_hash(
        self,
        prev_hash: str,
        event_type: str,
        payload_json: str,
        timestamp_str: str,
    ) -> str:
        """Compute HMAC-SHA256 for a log entry."""
        msg = f"{prev_hash}|{event_type}|{payload_json}|{timestamp_str}"
        return hmac.new(self._get_key(), msg.encode("utf-8"), hashlib.sha256).hexdigest()

    def _get_last_hash(self) -> str:
        """Return the entry_hash of the most recent log entry, or GENESIS."""
        conn = self._db.get_connection()
        row = conn.execute(
            "SELECT entry_hash FROM worm_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else _GENESIS

    def log_event(self, trace_id: str, event_type: str, payload: dict) -> None:
        """
        Append an event to the WORM log.

        Args:
            trace_id:   Workflow execution correlation ID.
            event_type: One of WORKFLOW_START, WORKFLOW_END, TOOL_EXECUTED,
                        KILL_SWITCH_TRIGGERED.
            payload:    Arbitrary event data (serialized to JSON).

        Raises:
            WORMStorageError: On any write failure (fail-closed).
        """
        try:
            payload_json = json.dumps(payload, sort_keys=True, default=str)
            timestamp_str = datetime.now(timezone.utc).isoformat()
            prev_hash = self._get_last_hash()
            entry_hash = self._compute_hash(prev_hash, event_type, payload_json, timestamp_str)

            conn = self._db.get_connection()
            conn.execute(
                """
                INSERT INTO worm_log (trace_id, event_type, payload, prev_hash, entry_hash, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (trace_id, event_type, payload_json, prev_hash, entry_hash, timestamp_str),
            )
            conn.commit()
        except WORMStorageError:
            raise
        except Exception as e:
            raise WORMStorageError(original_error=e) from e

    def get_chain(self) -> list[dict]:
        """Return all log entries in insertion order as a list of dicts."""
        conn = self._db.get_connection()
        cursor = conn.execute(
            "SELECT id, trace_id, event_type, payload, prev_hash, entry_hash, timestamp "
            "FROM worm_log ORDER BY id ASC"
        )
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def verify_chain(self) -> bool:
        """
        Verify the integrity of the entire hash chain.

        Returns True if all entries are untampered. Returns False if any
        entry_hash does not match recomputation, or if prev_hash linkage
        is broken.
        """
        chain = self.get_chain()
        if not chain:
            return True

        expected_prev = _GENESIS
        for entry in chain:
            if entry["prev_hash"] != expected_prev:
                return False
            recomputed = self._compute_hash(
                entry["prev_hash"],
                entry["event_type"],
                entry["payload"],
                entry["timestamp"],
            )
            if recomputed != entry["entry_hash"]:
                return False
            expected_prev = entry["entry_hash"]

        return True
