from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from app.config import Settings
from app.orchestrator import Connection, SessionRunner
from app.pipeline.mock import MockPipeline
from app.protocol import CLIENT_COMMANDS


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = dict(
        pipeline="mock",
        database_path=str(tmp_path / "csl.db"),
        mock_chunk_delay=0,
        pace_base_seconds=0,
        pace_seconds_per_char=0,
        turn_timeout_seconds=5,
        cors_origins="http://localhost:3000",
        access_code="",
        admin_token="",
        debug=False,
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


def fast_mock() -> MockPipeline:
    pipeline = MockPipeline()
    pipeline.delay = 0
    return pipeline


class Client:
    """A fake WebSocket client attached straight to a runner."""

    def __init__(self, runner: SessionRunner):
        self.runner = runner
        self.conn = Connection()
        self.events: list[dict[str, Any]] = []
        runner.attach(self.conn)

    def send(self, type_: str, **data: Any) -> None:
        self.runner.submit(type_, CLIENT_COMMANDS[type_].model_validate(data))

    async def next(self, timeout: float = 3.0) -> dict[str, Any]:
        event = await asyncio.wait_for(self.conn.queue.get(), timeout)
        assert event is not None, "connection closed"
        self.events.append(event)
        return event

    async def until(self, type_: str, pred: Callable[[dict], bool] = lambda d: True, timeout: float = 5.0) -> dict:
        async def scan() -> dict:
            while True:
                event = await self.next(timeout)
                if event["type"] == type_ and pred(event["data"]):
                    return event["data"]

        return await asyncio.wait_for(scan(), timeout)

    async def quiet(self, type_: str, seconds: float = 0.3) -> bool:
        """True if no event of this type arrives within `seconds`."""
        try:
            await self.until(type_, timeout=seconds)
            return False
        except asyncio.TimeoutError:
            return True

    def of(self, type_: str) -> list[dict]:
        return [e["data"] for e in self.events if e["type"] == type_]

    def close(self) -> None:
        self.runner.detach(self.conn)


async def to_discussion(client: Client, *, start: bool = True) -> None:
    """Drive a mock session through init and classroom building."""
    await client.until("message.completed")
    client.send("init.reply", text="자전축이 기울어져 있어서 여름엔 햇빛을 더 많이 받으니까요.")
    await client.until("classroom.ready")
    await client.until("phase.changed", lambda d: d["phase"] == "ready")
    if start:
        client.send("discussion.start")
        await client.until("phase.changed", lambda d: d["phase"] == "discussion")
