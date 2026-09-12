"""
Pod state persistence for crash recovery.

Stores are injected explicitly; nothing is opened at import time and no pod
restores state unless it is handed a store. The default for simulation and
tests is the in-memory store.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, Optional, Protocol

from orchestration.config import PersistenceSettings


class StateStore(Protocol):
    def save_state(self, pod_id: str, state: dict) -> None: ...

    def load_state(self, pod_id: str) -> Optional[dict]: ...


class InMemoryStateStore:
    def __init__(self) -> None:
        self._data: Dict[str, str] = {}

    def save_state(self, pod_id: str, state: dict) -> None:
        self._data[pod_id] = json.dumps(state)

    def load_state(self, pod_id: str) -> Optional[dict]:
        raw = self._data.get(pod_id)
        return json.loads(raw) if raw else None


class SQLiteStateStore:
    """Single-table SQLite persistence keyed by pod id."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else Path(__file__).parent / "state.sqlite"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_db()

    def _ensure_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS order_state (
                    pod_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def save_state(self, pod_id: str, state: dict) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO order_state (pod_id, state_json, ts) "
                "VALUES (?, ?, CURRENT_TIMESTAMP)",
                (pod_id, json.dumps(state)),
            )

    def load_state(self, pod_id: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT state_json FROM order_state WHERE pod_id = ?", (pod_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None


class RedisStateStore:
    def __init__(self, url: str = "redis://localhost:6379/0") -> None:
        try:
            import redis  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("redis-py is not installed") from exc
        self.client = redis.from_url(url)

    @staticmethod
    def _key(pod_id: str) -> str:
        return f"order_state:{pod_id}"

    def save_state(self, pod_id: str, state: dict) -> None:
        self.client.set(self._key(pod_id), json.dumps(state))

    def load_state(self, pod_id: str) -> Optional[dict]:
        raw = self.client.get(self._key(pod_id))
        return json.loads(raw) if raw else None


def get_state_store(settings: Optional[PersistenceSettings] = None) -> StateStore:
    settings = settings or PersistenceSettings()
    backend = settings.backend.lower()
    if backend == "sqlite":
        return SQLiteStateStore(settings.sqlite_path)
    if backend == "redis":
        return RedisStateStore(settings.redis_url)
    return InMemoryStateStore()
