"""SQLite persistence: an append-only event log plus the latest session snapshot.

The event log is what you analyse after the deployment (who did what, when).
The snapshot is what lets a session survive a server restart.
Writes are queued and flushed by one background task so that the event loop
never waits on disk.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    ts REAL NOT NULL,
    type TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (session_id, seq)
);
CREATE INDEX IF NOT EXISTS events_type ON events (type);
"""


class Store:
    def __init__(self, path: str):
        self.path = path
        self._db: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        self._queue: asyncio.Queue[tuple[str, tuple]] = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        self._db.commit()
        self._task = asyncio.create_task(self._writer(), name="store-writer")

    async def stop(self) -> None:
        await self.flush()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._db:
            self._db.close()
            self._db = None

    # ------------------------------------------------------------------ writes (non-blocking)

    def log_event(self, session_id: str, seq: int, ts: float, type_: str, data: dict[str, Any]) -> None:
        self._queue.put_nowait(
            ("event", (session_id, seq, ts, type_, json.dumps(data, ensure_ascii=False, default=str)))
        )

    def save_session(self, session_id: str, topic: str, created_at: float, payload: str) -> None:
        self._queue.put_nowait(("session", (session_id, topic, created_at, time.time(), payload)))

    async def flush(self) -> None:
        await self._queue.join()

    async def _writer(self) -> None:
        while True:
            batch = [await self._queue.get()]
            while not self._queue.empty():
                batch.append(self._queue.get_nowait())
            try:
                await asyncio.to_thread(self._write, batch)
            except Exception:  # pragma: no cover - disk errors must not kill the writer
                import logging

                logging.getLogger("csl.store").exception("failed to write %d rows", len(batch))
            finally:
                for _ in batch:
                    self._queue.task_done()

    def _write(self, batch: list[tuple[str, tuple]]) -> None:
        assert self._db is not None
        with self._lock:
            for kind, row in batch:
                if kind == "event":
                    self._db.execute(
                        "INSERT OR REPLACE INTO events (session_id, seq, ts, type, data) VALUES (?,?,?,?,?)", row
                    )
                else:
                    self._db.execute(
                        "INSERT INTO sessions (id, topic, created_at, updated_at, payload) VALUES (?,?,?,?,?) "
                        "ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at, payload=excluded.payload",
                        row,
                    )
            self._db.commit()

    # ------------------------------------------------------------------ reads

    def _query(self, sql: str, args: tuple = ()) -> list[tuple]:
        assert self._db is not None
        with self._lock:
            return self._db.execute(sql, args).fetchall()

    async def load_session(self, session_id: str) -> Optional[str]:
        await self.flush()
        rows = await asyncio.to_thread(self._query, "SELECT payload FROM sessions WHERE id = ?", (session_id,))
        return rows[0][0] if rows else None

    async def list_sessions(self) -> list[dict[str, Any]]:
        await self.flush()
        rows = await asyncio.to_thread(
            self._query,
            "SELECT s.id, s.topic, s.created_at, s.updated_at, "
            "(SELECT COUNT(*) FROM events e WHERE e.session_id = s.id) "
            "FROM sessions s ORDER BY s.created_at DESC",
        )
        return [
            {"sessionId": r[0], "topic": r[1], "createdAt": r[2], "updatedAt": r[3], "eventCount": r[4]}
            for r in rows
        ]

    async def list_events(self, session_id: str) -> list[dict[str, Any]]:
        await self.flush()
        rows = await asyncio.to_thread(
            self._query, "SELECT seq, ts, type, data FROM events WHERE session_id = ? ORDER BY seq", (session_id,)
        )
        return [{"seq": r[0], "ts": r[1], "type": r[2], "data": json.loads(r[3])} for r in rows]
