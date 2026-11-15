from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import openrouter
from app.llm import LLM, set_model_override
from app.main import create_app
from app.session import Session, current_session
from helpers import fast_mock, make_settings

AUTH = {"Authorization": "Bearer s3cret"}
MODELS = {
    "data": [
        {"id": "a/main", "name": "Main", "pricing": {"prompt": "0.000002", "completion": "0.00001"}, "context_length": 1000},
        {"id": "a/fast", "name": "Fast", "pricing": {"prompt": "0.0000001", "completion": "0.0000005"}},
        {"id": "openrouter/auto", "pricing": {"prompt": "-1", "completion": "-1"}},
    ]
}
KEY = {"data": {"label": "csl", "usage": 1.25, "usage_daily": 0.5, "limit": 40, "limit_remaining": 38.75}}


@pytest.fixture(autouse=True)
def fake_openrouter(monkeypatch):
    calls: list[str] = []

    async def fake_get(url, api_key=None):
        calls.append(url)
        if url.endswith("/models"):
            return MODELS
        if url.endswith("/key"):
            assert api_key == "sk-test"
            return KEY
        raise AssertionError(url)

    monkeypatch.setattr(openrouter, "_get", fake_get)
    monkeypatch.setattr(openrouter, "_models", None)
    set_model_override("", "")
    yield calls
    set_model_override("", "")


def make_app(tmp_path, **kw):
    settings = make_settings(
        tmp_path, admin_token="s3cret", openrouter_api_key="sk-test", openrouter_model="a/main", **kw
    )
    return create_app(settings, fast_mock())


def test_model_override_is_validated_applied_and_persisted(tmp_path):
    with TestClient(make_app(tmp_path)) as http:
        assert http.get("/api/admin/config").status_code == 401
        cfg = http.get("/api/admin/config", headers=AUTH).json()
        assert cfg == {
            "pipeline": "mock", "model": "a/main", "modelFast": "", "defaultModel": "a/main",
            "defaultModelFast": "", "overridden": False, "apiKeySet": True,
        }
        bad = http.put("/api/admin/config", headers=AUTH, json={"model": "nope/x", "modelFast": ""})
        assert bad.status_code == 422
        cfg = http.put("/api/admin/config", headers=AUTH, json={"model": "", "modelFast": "a/fast"}).json()
        assert cfg["model"] == "a/main" and cfg["modelFast"] == "a/fast" and cfg["overridden"]
        models = http.get("/api/admin/models", headers=AUTH).json()
        assert [m["id"] for m in models] == ["a/fast", "a/main", "openrouter/auto"]
        assert models[1]["promptPrice"] == pytest.approx(2.0) and models[2]["promptPrice"] == 0

    set_model_override("", "")  # as after a process restart
    with TestClient(make_app(tmp_path)) as http:
        cfg = http.get("/api/admin/config", headers=AUTH).json()
        assert cfg["modelFast"] == "a/fast" and cfg["overridden"]
        cfg = http.put("/api/admin/config", headers=AUTH, json={}).json()
        assert cfg["modelFast"] == "" and not cfg["overridden"]


def test_usage_sessions_and_history(tmp_path):
    with TestClient(make_app(tmp_path)) as http:
        sid = http.post("/api/sessions", json={"topic": "t"}).json()["sessionId"]
        store = http.app.state.store
        ts = time.time()
        store.log_event(sid, 9001, ts, "llm.call", {"model": "a/main", "seconds": 2.0, "promptTokens": 1000,
                                                   "completionTokens": 100, "cost": 0.5})
        # no reported cost -> estimated from the list price: 1000*2/1M + 100*10/1M = 0.003
        store.log_event(sid, 9002, ts, "llm.call", {"model": "a/main", "seconds": 1.0, "promptTokens": 1000,
                                                   "completionTokens": 100})
        store.log_event(sid, 9003, ts, "llm.call", {"model": "x/unknown", "seconds": 1.0, "promptTokens": 5,
                                                   "completionTokens": 5, "reasoningTokens": 3})
        store.log_event(sid, 9004, ts, "llm.call", {"model": "a/main", "seconds": 0.5, "error": "boom"})
        # Two calls that report prompt-cache figures: 600 of 1000 input tokens read from the cache.
        store.log_event(sid, 9005, ts, "llm.call", {"model": "a/fast", "seconds": 1.0, "promptTokens": 800,
                                                   "completionTokens": 10, "cost": 0.0, "cachedTokens": 600})
        store.log_event(sid, 9006, ts, "llm.call", {"model": "a/fast", "seconds": 1.0, "promptTokens": 200,
                                                   "completionTokens": 10, "cost": 0.0, "cachedTokens": 0,
                                                   "cacheWriteTokens": 150})

        usage = http.get("/api/admin/usage?tzOffset=540", headers=AUTH).json()
        total = usage["total"]
        assert total["calls"] == 6 and total["errors"] == 1 and total["unpricedCalls"] == 1
        assert total["cost"] == pytest.approx(0.503) and total["estimated"]
        assert total["reasoningTokens"] == 3 and total["promptTokens"] == 3005
        # The hit rate only counts calls that reported a cache figure (1000 of the 3005 input tokens).
        assert total["cachedTokens"] == 600 and total["cacheWriteTokens"] == 150
        assert total["cacheMeasuredTokens"] == 1000 and total["cacheHitRate"] == pytest.approx(0.6)
        assert usage["byModel"][0]["key"] == "a/main" and usage["byModel"][0]["calls"] == 3
        assert usage["byModel"][0]["cacheHitRate"] is None and usage["byModel"][0]["cacheMeasuredTokens"] == 0
        assert len(usage["byDay"]) == 1 and len(usage["byDay"][0]["key"]) == 10
        assert usage["openrouter"]["usage"] == 1.25 and usage["openrouter"]["limitRemaining"] == 38.75

        rows = http.get("/api/admin/sessions", headers=AUTH).json()
        assert rows[0]["sessionId"] == sid and rows[0]["llmCalls"] == 6 and rows[0]["live"]
        assert rows[0]["cost"] == pytest.approx(0.503)
        detail = http.get(f"/api/admin/sessions/{sid}", headers=AUTH).json()
        assert detail["live"] and detail["snapshot"]["sessionId"] == sid
        assert http.get("/api/admin/sessions/nope", headers=AUTH).status_code == 404

    # After a restart the session is not in memory; the detail comes from SQLite without restoring it.
    with TestClient(make_app(tmp_path)) as http:
        detail = http.get(f"/api/admin/sessions/{sid}", headers=AUTH).json()
        assert not detail["live"] and detail["snapshot"]["topic"] == "t"
        assert sid not in http.app.state.registry.runners
        assert not http.get("/api/admin/sessions", headers=AUTH).json()[0]["live"]


def test_usage_without_key_skips_openrouter(tmp_path, fake_openrouter):
    app = create_app(make_settings(tmp_path, admin_token="s3cret"), fast_mock())
    with TestClient(app) as http:
        usage = http.get("/api/admin/usage", headers=AUTH).json()
        assert usage["total"]["calls"] == 0 and usage["openrouter"] is None
    assert fake_openrouter == []  # no network call at all


def test_llm_uses_override_and_logs_cost(tmp_path):
    llm = LLM(make_settings(tmp_path, openrouter_model="a/main", openrouter_model_fast="a/fast"))
    assert llm._model(None, fast=True) == "a/fast"
    set_model_override("b/main", "")
    assert llm._model(None, fast=False) == "b/main" and llm._model(None, fast=True) == "a/fast"

    session = Session("s", "t", "ko", 10)
    logged: list[tuple[str, dict]] = []
    session.log = lambda type_, data: logged.append((type_, data))
    token = current_session.set(session)
    try:
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, cost=0.0012,
                                completion_tokens_details=SimpleNamespace(reasoning_tokens=3))
        llm._log("complete", "b/main", time.monotonic(), usage, 20)
        cached = SimpleNamespace(prompt_tokens=900, completion_tokens=5,
                                 prompt_tokens_details=SimpleNamespace(cached_tokens=700, cache_write_tokens=0))
        llm._log("complete", "b/main", time.monotonic(), cached, 20)
        missed = SimpleNamespace(prompt_tokens=900, completion_tokens=5,
                                 prompt_tokens_details=SimpleNamespace(cached_tokens=0, cache_write_tokens=880))
        llm._log("complete", "b/main", time.monotonic(), missed, 20)
    finally:
        current_session.reset(token)
    data = logged[0][1]
    assert data["cost"] == 0.0012 and data["reasoningTokens"] == 3 and data["promptTokens"] == 10
    assert "cachedTokens" not in data  # the provider reported no cache figure
    assert logged[1][1]["cachedTokens"] == 700 and "cacheWriteTokens" not in logged[1][1]
    assert logged[2][1]["cachedTokens"] == 0 and logged[2][1]["cacheWriteTokens"] == 880
