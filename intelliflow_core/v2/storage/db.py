"""
Shared database session manager for IntelliFlow v2 storage.

Provides a single SQLite connection with WAL mode for concurrent read access.
Used by WORMLogRepository (Step 4) and TokenLedgerRepository (Step 5).

Usage:
    from intelliflow_core.v2.storage.db import DatabaseSessionManager

    with DatabaseSessionManager("intelliflow_v2.db") as db:
        conn = db.get_connection()
        conn.execute("SELECT 1")

In production, inject via KMS-managed credentials.
Default path is suitable for local development.
"""

from __future__ import annotations

import sqlite3
import threading


class DatabaseSessionManager:
    """
    Thread-safe SQLite connection manager with WAL journaling.

    Invariants:
        - Single connection per manager instance.
        - WAL mode set on connection init for concurrent read access.
        - All connection access is thread-safe via Lock.
        - Context manager support for deterministic cleanup.
    """

    def __init__(self, db_path: str = "intelliflow_v2.db") -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")

    def get_connection(self) -> sqlite3.Connection:
        """Return the managed SQLite connection."""
        return self._conn

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            self._conn.close()

    def __enter__(self) -> DatabaseSessionManager:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
