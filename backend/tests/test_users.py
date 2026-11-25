"""Nickname login: users, whose a session is, and finding one's sessions again."""
from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from app.main import create_app
from app.store import Store
from helpers import fast_mock, make_settings

AUTH = {"Authorization": "Bearer s3cret"}


def login(http, name):
    return http.post("/api/users/login", json={"name": name})


def test_login_creates_a_user_once(tmp_path):
    with TestClient(create_app(make_settings(tmp_path), fast_mock())) as http:
        first = login(http, "  Minsu   Kim ").json()
        assert first["created"] and first["user"]["name"] == "Minsu Kim"
        user_id = first["user"]["userId"]

        # Same nickname in another spelling of case and spaces: the same user, not a new one.
        again = login(http, "minsu kim").json()
        assert not again["created"] and again["user"]["userId"] == user_id
        assert again["user"]["name"] == "Minsu Kim"  # as first typed
        assert login(http, "민수").json()["user"]["userId"] != user_id

        for bad in ("a", "   ", "x" * 21, "tab\tname\x00"):
            assert login(http, bad).status_code == 422, bad

        assert http.get(f"/api/users/{user_id}").json()["name"] == "Minsu Kim"
        assert http.get("/api/users/nope").status_code == 404
        assert http.get("/api/users/nope/sessions").status_code == 404


def test_sessions_belong_to_the_user_who_created_them(tmp_path):
    settings = make_settings(tmp_path, admin_token="s3cret")
    with TestClient(create_app(settings, fast_mock())) as http:
        ana = login(http, "ana").json()["user"]["userId"]
        ben = login(http, "ben").json()["user"]["userId"]

        assert http.post("/api/sessions", json={"topic": "x", "userId": "nope"}).status_code == 404
        first = http.post("/api/sessions", json={"topic": "first", "userId": ana}).json()
        assert first["snapshot"]["userId"] == ana
        second = http.post("/api/sessions", json={"topic": "second", "userId": ana, "language": "ko"}).json()
        other = http.post("/api/sessions", json={"topic": "ben's", "userId": ben}).json()
        guest = http.post("/api/sessions", json={"topic": "guest"}).json()
        assert guest["snapshot"]["userId"] is None

        # Play the first one into the discussion, then leave it: this is the session to come back to.
        with http.websocket_connect(f"/ws/sessions/{first['sessionId']}") as ws:
            ws.send_json({"type": "init.finish"})
            for _ in range(500):
                if ws.receive_json()["type"] == "classroom.ready":
                    break
            ws.send_json({"type": "control.set_pace", "data": {"auto": False}})  # one message, then wait
            ws.send_json({"type": "discussion.start"})
            for _ in range(500):
                event = ws.receive_json()
                if event["type"] == "message.completed" and event["data"]["message"]["channel"] == "discussion":
                    break

        mine = http.get(f"/api/users/{ana}/sessions").json()
        assert [s["topic"] for s in mine] == ["second", "first"]  # newest first, only ana's
        assert mine[0]["language"] == "ko" and mine[0]["phase"] == "init"
        assert mine[1]["sessionId"] == first["sessionId"] and mine[1]["phase"] == "discussion"
        assert mine[0]["messageCount"] == 0
        assert mine[1]["messageCount"] == 1
        assert [s["sessionId"] for s in http.get(f"/api/users/{ben}/sessions").json()] == [other["sessionId"]]

        rows = {r["sessionId"]: r for r in http.get("/api/admin/sessions", headers=AUTH).json()}
        assert rows[first["sessionId"]]["userName"] == "ana" and rows[first["sessionId"]]["userId"] == ana
        assert rows[guest["sessionId"]]["userName"] is None

        events = http.get(f"/api/admin/sessions/{second['sessionId']}/events", headers=AUTH).json()
        assert events[0]["type"] == "session.created" and events[0]["data"]["userId"] == ana

    # After a restart: the same nickname finds the same sessions, and a restored one is still theirs.
    with TestClient(create_app(settings, fast_mock())) as http:
        assert login(http, "ANA").json()["user"]["userId"] == ana
        mine = http.get(f"/api/users/{ana}/sessions").json()
        assert [s["topic"] for s in mine] == ["second", "first"] and mine[1]["phase"] == "discussion"
        restored = http.get(f"/api/sessions/{first['sessionId']}").json()
        assert restored["userId"] == ana and restored["phase"] == "discussion"
        assert restored["status"] == "paused"  # comes back paused, with everything that was said
        assert len(restored["messages"]) >= 2
        assert mine[0]["messageCount"] == 0
        assert mine[1]["messageCount"] == 1


async def test_database_from_before_users_is_upgraded(tmp_path):
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, topic TEXT NOT NULL, created_at REAL NOT NULL,"
        " updated_at REAL NOT NULL, payload TEXT NOT NULL);"
        "INSERT INTO sessions VALUES ('s1', 'kept', 1.0, 2.0, '{\"snapshot\": {\"phase\": \"ended\", \"messages\": []}}');"
    )
    old.commit()
    old.close()

    store = Store(path)
    await store.start()
    try:
        rows = await store.list_sessions()
        assert rows[0]["sessionId"] == "s1" and rows[0]["topic"] == "kept" and rows[0]["userId"] is None
        user, created = await store.login_user("u1", "ana", "ana")
        assert created and user["userId"] == "u1"
        store.save_session("s2", "new", 3.0, '{"snapshot": {"phase": "init", "messages": []}}', "u1")
        assert [s["sessionId"] for s in await store.list_user_sessions("u1")] == ["s2"]
    finally:
        await store.stop()

    # Starting again on the upgraded file changes nothing.
    store = Store(path)
    await store.start()
    try:
        assert len(await store.list_sessions()) == 2
    finally:
        await store.stop()
