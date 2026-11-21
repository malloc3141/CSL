"""A session can ask for a registered pipeline by name, whatever PIPELINE the server runs."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.orchestrator import SessionRegistry
from app.pipeline import FREE_PIPELINES, SESSION_PIPELINES, Pipeline, make_pipeline
from app.pipeline.mock import MockPipeline
from helpers import make_settings


class FakeDefault(MockPipeline):
    """Stands in for the server's real pipeline (e.g. baseline) without any LLM."""

    name = "fake"

    def __init__(self) -> None:
        super().__init__()
        self.delay = 0


class Other(FakeDefault):
    """Stands in for a teammate's pipeline registered in SESSION_PIPELINES."""

    name = "other-internal-name"


@pytest.fixture
def registered(monkeypatch):
    monkeypatch.setitem(SESSION_PIPELINES, "other", "test_session_pipeline:Other")
    monkeypatch.setitem(SESSION_PIPELINES, "broken", "no_such_module_anywhere:Nope")


def test_every_registered_pipeline_loads():
    assert "mock" in SESSION_PIPELINES and FREE_PIPELINES <= set(SESSION_PIPELINES)
    for name in SESSION_PIPELINES:
        assert isinstance(make_pipeline(name), Pipeline), name
    with pytest.raises(ValueError):
        make_pipeline("not-registered")


def test_session_on_a_named_pipeline(tmp_path, registered):
    settings = make_settings(tmp_path, access_code="kaist", admin_token="s3cret")
    with TestClient(create_app(settings, FakeDefault())) as http:
        health = http.get("/api/health").json()
        assert health["pipeline"] == "fake" and health["freePipelines"] == ["mock"]
        assert health["accessCodeRequired"] is True  # this server was started with an access code
        assert health["sessionPipelines"] == list(SESSION_PIPELINES) and "other" in health["sessionPipelines"]

        # Only pipelines without LLM calls skip the access code.
        assert http.post("/api/sessions", json={"topic": "x"}).status_code == 403
        assert http.post("/api/sessions", json={"topic": "x", "pipeline": "other"}).status_code == 403
        assert http.post("/api/sessions", json={"topic": "x", "pipeline": "nope", "accessCode": "kaist"}).status_code == 422
        broken = http.post("/api/sessions", json={"topic": "x", "pipeline": "broken", "accessCode": "kaist"})
        assert broken.status_code == 500 and "no_such_module" not in broken.text  # details stay in the log

        mock = http.post("/api/sessions", json={"topic": "x", "pipeline": "mock"})
        assert mock.status_code == 200, mock.text  # no access code needed
        mock_id = mock.json()["sessionId"]
        assert mock.json()["snapshot"]["pipeline"] == "mock"

        real = http.post("/api/sessions", json={"topic": "x", "accessCode": "kaist"}).json()
        assert real["snapshot"]["pipeline"] == "fake"
        by_name = http.post("/api/sessions", json={"topic": "x", "pipeline": "fake", "accessCode": "kaist"}).json()
        other = http.post("/api/sessions", json={"topic": "x", "pipeline": "other", "accessCode": "kaist"}).json()
        assert other["snapshot"]["pipeline"] == "other"  # the registered name, not the class's own

        runners = http.app.state.registry.runners
        assert type(runners[mock_id].pipeline) is MockPipeline and runners[mock_id].pipeline.delay == 0
        assert isinstance(runners[real["sessionId"]].pipeline, FakeDefault)
        assert runners[by_name["sessionId"]].pipeline is runners[real["sessionId"]].pipeline
        assert type(runners[other["sessionId"]].pipeline) is Other
        assert len(runners) == 4  # the rejected requests created nothing

        # The mock session really runs: the guide's first message arrives.
        with http.websocket_connect(f"/ws/sessions/{mock_id}") as ws:
            snapshot = ws.receive_json()
            assert snapshot["type"] == "session.snapshot" and snapshot["data"]["pipeline"] == "mock"
            if not snapshot["data"]["messages"]:  # with no delay the message may already be in the snapshot
                for _ in range(200):
                    if ws.receive_json()["type"] == "message.completed":
                        break
                else:
                    raise AssertionError("no message from the mock session")

        rows = {r["sessionId"]: r for r in http.get("/api/admin/sessions", headers={"Authorization": "Bearer s3cret"}).json()}
        assert rows[mock_id]["pipeline"] == "mock" and rows[real["sessionId"]]["pipeline"] == "fake"
        assert rows[other["sessionId"]]["pipeline"] == "other"


async def test_restored_session_keeps_its_pipeline(settings, store, monkeypatch):
    monkeypatch.setitem(SESSION_PIPELINES, "other", "test_session_pipeline:Other")
    first = SessionRegistry(settings, store, FakeDefault())
    mock_id = first.create("x", "en", "mock").session.id
    real_id = first.create("x", "en").session.id
    other_id = first.create("x", "en", "other").session.id
    gone_id = first.create("x", "en", "other").session.id
    await first.stop()

    second = SessionRegistry(settings, store, FakeDefault())
    try:
        mock = await second.get(mock_id)
        real = await second.get(real_id)
        other = await second.get(other_id)
        assert mock is not None and real is not None and other is not None
        assert mock.session.pipeline == "mock" and type(mock.pipeline) is MockPipeline
        assert real.session.pipeline == "fake" and isinstance(real.pipeline, FakeDefault)
        assert other.session.pipeline == "other" and type(other.pipeline) is Other

        # A pipeline that is not registered any more: the server's PIPELINE takes the session over.
        monkeypatch.delitem(SESSION_PIPELINES, "other")
        second._named.clear()
        gone = await second.get(gone_id)
        assert gone is not None and gone.pipeline is second.pipeline and gone.session.pipeline == "fake"
        assert second.pipeline_for("") is second.pipeline and second.pipeline_for(None) is second.pipeline
        with pytest.raises(KeyError):
            second.pipeline_for("other")
    finally:
        await second.stop()
