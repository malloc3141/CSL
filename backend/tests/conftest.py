from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from app.config import Settings
from app.orchestrator import SessionRegistry
from app.store import Store
from helpers import fast_mock, make_settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest_asyncio.fixture
async def store(settings: Settings):
    s = Store(settings.database_path)
    await s.start()
    yield s
    await s.stop()


@pytest_asyncio.fixture
async def registry(settings: Settings, store: Store):
    r = SessionRegistry(settings, store, fast_mock())
    yield r
    await r.stop()
