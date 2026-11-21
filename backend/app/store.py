"""SQLite persistence: an append-only event log, the latest session snapshot, and the users.

The event log is what you analyse after the deployment (who did what, when).
The snapshot is what lets a session survive a server restart.
`users` holds the nicknames learners sign in with; `sessions.user_id` says whose a session is.
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
    payload TEXT NOT NULL,
    user_id TEXT
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
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL,
    last_login_at REAL NOT NULL
);
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
        # Databases created before users existed: add the column (existing rows keep NULL = no user).
        if "user_id" not in {row[1] for row in self._db.execute("PRAGMA table_info(sessions)")}:
            self._db.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT")
        self._db.execute("CREATE INDEX IF NOT EXISTS sessions_user ON sessions (user_id)")
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

    def save_session(
        self, session_id: str, topic: str, created_at: float, payload: str, user_id: Optional[str] = None
    ) -> None:
        self._queue.put_nowait(("session", (session_id, topic, created_at, time.time(), payload, user_id)))

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
                        "INSERT INTO sessions (id, topic, created_at, updated_at, payload, user_id) "
                        "VALUES (?,?,?,?,?,?) "
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
            "(SELECT COUNT(*) FROM events e WHERE e.session_id = s.id), "
            "json_extract(s.payload, '$.snapshot.phase'), "
            "json_extract(s.payload, '$.snapshot.pipeline'), "
            "json_array_length(s.payload, '$.snapshot.messages'), "
            "s.user_id, u.name "
            "FROM sessions s LEFT JOIN users u ON u.id = s.user_id ORDER BY s.created_at DESC",
        )
        return [
            {
                "sessionId": r[0],
                "topic": r[1],
                "createdAt": r[2],
                "updatedAt": r[3],
                "eventCount": r[4],
                "phase": r[5],
                "pipeline": r[6] or None,
                "messageCount": r[7] or 0,
                "userId": r[8],
                "userName": r[9],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------ users (nickname login)

    def _login(self, user_id: str, name: str, key: str, now: float) -> tuple[tuple, bool]:
        assert self._db is not None
        with self._lock:
            cursor = self._db.execute(
                "INSERT OR IGNORE INTO users (id, name, name_key, created_at, last_login_at) VALUES (?,?,?,?,?)",
                (user_id, name, key, now, now),
            )
            created = cursor.rowcount == 1
            if not created:
                self._db.execute("UPDATE users SET last_login_at = ? WHERE name_key = ?", (now, key))
            row = self._db.execute("SELECT id, name, created_at FROM users WHERE name_key = ?", (key,)).fetchone()
            self._db.commit()
        return row, created

    async def login_user(self, user_id: str, name: str, key: str) -> tuple[dict[str, Any], bool]:
        """The user with this nickname key, created with `user_id` and `name` if the key is new."""
        row, created = await asyncio.to_thread(self._login, user_id, name, key, time.time())
        return {"userId": row[0], "name": row[1], "createdAt": row[2]}, created

    async def get_user(self, user_id: str) -> Optional[dict[str, Any]]:
        rows = await asyncio.to_thread(self._query, "SELECT id, name, created_at FROM users WHERE id = ?", (user_id,))
        return {"userId": rows[0][0], "name": rows[0][1], "createdAt": rows[0][2]} if rows else None

    async def list_user_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """Sessions of one user, newest first, with what a "continue" list needs."""
        await self.flush()
        rows = await asyncio.to_thread(
            self._query,
            "SELECT id, topic, created_at, updated_at, "
            "json_extract(payload, '$.snapshot.language'), "
            "json_extract(payload, '$.snapshot.pipeline'), "
            "json_extract(payload, '$.snapshot.phase'), "
            "json_extract(payload, '$.snapshot.status'), "
            "json_array_length(payload, '$.snapshot.messages') "
            "FROM sessions WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        return [
            {
                "sessionId": r[0],
                "topic": r[1],
                "createdAt": r[2],
                "updatedAt": r[3],
                "language": r[4],
                "pipeline": r[5] or None,
                "phase": r[6],
                "status": r[7],
                "messageCount": r[8] or 0,
            }
            for r in rows
        ]

    async def llm_calls(self) -> list[tuple[str, float, dict[str, Any]]]:
        """Every `llm.call` event as (session_id, ts, data), oldest first."""
        await self.flush()
        rows = await asyncio.to_thread(
            self._query, "SELECT session_id, ts, data FROM events WHERE type = 'llm.call' ORDER BY ts"
        )
        return [(r[0], r[1], json.loads(r[2])) for r in rows]

    # ------------------------------------------------------------------ runtime config (admin page)

    async def get_config(self, key: str) -> Optional[str]:
        rows = await asyncio.to_thread(self._query, "SELECT value FROM config WHERE key = ?", (key,))
        return rows[0][0] if rows else None

    async def set_config(self, key: str, value: str) -> None:
        await asyncio.to_thread(self._execute, "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))

    def _execute(self, sql: str, args: tuple = ()) -> None:
        assert self._db is not None
        with self._lock:
            self._db.execute(sql, args)
            self._db.commit()

    async def list_events(self, session_id: str) -> list[dict[str, Any]]:
        await self.flush()
        rows = await asyncio.to_thread(
            self._query, "SELECT seq, ts, type, data FROM events WHERE session_id = ? ORDER BY seq", (session_id,)
        )
        return [{"seq": r[0], "ts": r[1], "type": r[2], "data": json.loads(r[3])} for r in rows]
