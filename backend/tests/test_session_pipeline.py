"""A session can ask for the scripted mock whatever PIPELINE the server runs (frontend development)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.orchestrator import SessionRegistry
from app.pipeline.mock import MockPipeline
from helpers import make_settings


class FakeDefault(MockPipeline):
    """Stands in for the server's real pipeline (e.g. baseline) without any LLM."""

    name = "fake"

    def __init__(self) -> None:
        super().__init__()
        self.delay = 0


def test_mock_session_on_a_non_mock_server(tmp_path):
    settings = make_settings(tmp_path, access_code="kaist", admin_token="s3cret")
    with TestClient(create_app(settings, FakeDefault())) as http:
        health = http.get("/api/health").json()
        assert health["pipeline"] == "fake" and health["sessionPipelines"] == ["mock"]

        assert http.post("/api/sessions", json={"topic": "x"}).status_code == 403
        assert http.post("/api/sessions", json={"topic": "x", "pipeline": "baseline"}).status_code == 422

        mock = http.post("/api/sessions", json={"topic": "x", "pipeline": "mock"})
        assert mock.status_code == 200, mock.text  # no access code needed
        mock_id = mock.json()["sessionId"]
        assert mock.json()["snapshot"]["pipeline"] == "mock"

        real = http.post("/api/sessions", json={"topic": "x", "accessCode": "kaist"}).json()
        assert real["snapshot"]["pipeline"] == "fake"

        runners = http.app.state.registry.runners
        assert type(runners[mock_id].pipeline) is MockPipeline and runners[mock_id].pipeline.delay == 0
        assert isinstance(runners[real["sessionId"]].pipeline, FakeDefault)

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


async def test_restored_session_keeps_its_pipeline(settings, store):
    first = SessionRegistry(settings, store, FakeDefault())
    mock_id = first.create("x", "en", "mock").session.id
    real_id = first.create("x", "en").session.id
    await first.stop()

    second = SessionRegistry(settings, store, FakeDefault())
    try:
        mock = await second.get(mock_id)
        real = await second.get(real_id)
        assert mock is not None and real is not None
        assert mock.session.pipeline == "mock" and type(mock.pipeline) is MockPipeline
        assert real.session.pipeline == "fake" and isinstance(real.pipeline, FakeDefault)
        # Sessions stored before per-session pipelines ("") and unknown names get the server's PIPELINE.
        assert second.pipeline_for("") is second.pipeline and second.pipeline_for("baseline") is second.pipeline
    finally:
        await second.stop()
