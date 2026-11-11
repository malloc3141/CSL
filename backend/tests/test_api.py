from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from helpers import fast_mock, make_settings


def recv_until(ws, type_, pred=lambda d: True, limit=500):
    for _ in range(limit):
        event = ws.receive_json()
        if event["type"] == type_ and pred(event["data"]):
            return event["data"]
    raise AssertionError(f"no {type_} within {limit} events")


def send(ws, type_, **data):
    ws.send_json({"type": type_, "data": data})


def test_rest_and_websocket_flow(tmp_path):
    app = create_app(make_settings(tmp_path, admin_token="s3cret"), fast_mock())
    with TestClient(app) as http:
        assert http.get("/api/health").json()["pipeline"] == "mock"
        assert http.post("/api/sessions", json={"topic": "  "}).status_code == 422
        created = http.post("/api/sessions", json={"topic": "여름은 왜 더운가", "language": "ko"}).json()
        sid = created["sessionId"]
        assert created["snapshot"]["phase"] == "init" and created["snapshot"]["protocolVersion"] == 1

        with http.websocket_connect(f"/ws/sessions/{sid}") as ws:
            snap = ws.receive_json()
            assert snap["type"] == "session.snapshot" and snap["data"]["sessionId"] == sid
            if not snap["data"]["messages"]:
                recv_until(ws, "message.completed")
            ws.send_text("not json")
            assert recv_until(ws, "error")["code"] == "bad_command"
            send(ws, "nope")
            assert recv_until(ws, "error")["code"] == "bad_command"
            send(ws, "ping")
            recv_until(ws, "pong")
            send(ws, "init.reply", text="자전축이 기울어져서요")
            ready = recv_until(ws, "classroom.ready")
            assert [p["name"] for p in ready["participants"]] == ["Tutor", "Peer 1", "Peer 2"]
            assert ready["states"]["peer1"]["version"] == 0
            send(ws, "control.set_pace", auto=False)  # step by step, so the question lands after turn 1
            send(ws, "discussion.start")
            first = recv_until(ws, "message.completed", lambda d: d["message"]["channel"] == "discussion")
            assert first["message"]["speakerId"] == "peer1" and first["message"]["peerIndex"] == 0
            send(ws, "user.message", text="자전축이 기울어졌다는 게 무슨 뜻이에요?")  # plays the lo-fi aside
            recv_until(ws, "message.completed", lambda d: d["message"]["role"] == "user")
            aside = recv_until(ws, "message.completed", lambda d: d["message"]["role"] == "tutor")
            assert aside["message"]["meta"]["mock"]["key"] == "Q2"
            send(ws, "control.set_pace", auto=True)
            recv_until(ws, "user.invited")

        # a second connection gets everything in the snapshot
        with http.websocket_connect(f"/ws/sessions/{sid}") as ws:
            snap = ws.receive_json()["data"]
            assert snap["status"] == "waiting_user" and snap["invitedTurnId"]
            assert len([m for m in snap["messages"] if m["channel"] == "discussion"]) == 18
        assert http.get(f"/api/sessions/{sid}").json()["phase"] == "discussion"
        assert http.get("/api/sessions/unknown").status_code == 404

        with pytest.raises(WebSocketDisconnect) as closed:
            with http.websocket_connect("/ws/sessions/unknown") as ws:
                ws.receive_json()
        assert closed.value.code == 4404
        with pytest.raises(WebSocketDisconnect) as closed:
            with http.websocket_connect(f"/ws/sessions/{sid}", headers={"origin": "https://evil.example"}) as ws:
                ws.receive_json()
        assert closed.value.code == 4403

        assert http.get("/api/admin/sessions").status_code == 401
        auth = {"Authorization": "Bearer s3cret"}
        assert http.get("/api/admin/sessions", headers=auth).json()[0]["sessionId"] == sid
        events = http.get(f"/api/admin/sessions/{sid}/events", headers=auth).json()
        assert any(e["type"] == "client.user.message" for e in events)


def test_access_code_capacity_and_admin_off(tmp_path):
    app = create_app(make_settings(tmp_path, access_code="kaist", max_active_sessions=1), fast_mock())
    with TestClient(app) as http:
        assert http.post("/api/sessions", json={"topic": "x"}).status_code == 403
        assert http.post("/api/sessions", json={"topic": "x", "accessCode": "kaist"}).status_code == 200
        assert http.post("/api/sessions", json={"topic": "x", "accessCode": "kaist"}).status_code == 503
        assert http.get("/api/admin/sessions").status_code == 404


def test_typescript_protocol_is_up_to_date():
    root = Path(__file__).resolve().parents[1]
    if not (root.parent / "frontend").exists():
        pytest.skip("frontend not checked out next to backend")
    result = subprocess.run([sys.executable, "scripts/gen_ts.py", "--check"], cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
