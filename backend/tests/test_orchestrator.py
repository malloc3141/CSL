from __future__ import annotations

import asyncio

from app.orchestrator import SessionRegistry, diff_states
from app.pipeline.base import PipelineError
from app.protocol import Belief, KnowledgeState

from helpers import Client, fast_mock, make_settings, to_discussion


async def test_mock_scenario_end_to_end(registry: SessionRegistry):
    runner = registry.create("여름은 왜 더운가", "ko")
    c = Client(runner)
    assert (await c.next())["type"] == "session.snapshot"
    await to_discussion(c)
    s = runner.session
    assert [p.id for p in s.participants] == ["tutor", "peer1", "peer2"]
    assert [p.peer_index for p in s.participants] == [None, 0, 1]

    invited = await c.until("user.invited")
    assert s.status == "waiting_user" and s.turn_count == 15
    assert s.invited_turn_id == invited["turnId"] == s.last_message.id
    # the 16 scripted changes arrive as 9 versioned updates
    assert len(c.of("state.updated")) == 9
    assert [v.version for v in s.states["peer1"]] == [0, 1, 2, 3, 4, 5]
    assert [v.version for v in s.states["peer2"]] == [0, 1, 2, 3, 4]
    first = s.states["peer1"][1]
    assert first.turn_number == 3 and {ch.field for ch in first.changes} == {"beliefs", "explanation", "openQuestions"}
    # every delta belongs to a turn that was announced first, and adds up to the message
    for m in c.of("message.completed"):
        m = m["message"]
        if m["role"] != "user":
            text = "".join(d["text"] for d in c.of("message.delta") if d["turnId"] == m["id"])
            assert text.strip() == m["text"]

    c.send("user.message", text="자전축이 기울어져서 햇빛이 더 수직에 가까운 각도로 들어오고 낮도 길어져요.")
    user = await c.until("message.completed", lambda d: d["message"]["role"] == "user")
    assert user["message"]["invited"] is True and user["message"]["turnNumber"] == 16
    ended = await c.until("phase.changed", lambda d: d["phase"] == "ended")
    assert ended["reason"] == "completed"
    assert s.turn_count == 19  # branch A: two peers and the tutor react
    assert s.state_of("peer1").explanation_accuracy == "correct"
    assert s.snapshot().active_turn is None


async def test_partial_explanation_invites_again(registry: SessionRegistry):
    runner = registry.create("x", "en")
    c = Client(runner)
    await to_discussion(c)
    await c.until("user.invited")
    c.send("user.message", text="The days are longer in summer.")  # branch B2
    await c.until("user.invited")
    assert runner.session.status == "waiting_user"
    assert "longer" in runner.session.state_of("peer1").explanation
    c.send("control.resume")  # the learner passes: nothing is left in the script
    assert (await c.until("phase.changed", lambda d: d["phase"] == "ended"))["reason"] == "completed"


class SlowFirst(type(fast_mock())):
    """First utterance hangs after one chunk, so a learner message can interrupt it."""

    def __init__(self):
        super().__init__()
        self.delay = 0
        self.calls = 0

    async def speak(self, session, decision, out):
        self.calls += 1
        if self.calls == 1:
            await out.write("여름에는 ")
            await asyncio.sleep(30)
        await super().speak(session, decision, out)


async def test_learner_interrupts_a_visible_turn(settings, store):
    registry = SessionRegistry(settings, store, SlowFirst())
    try:
        runner = registry.create("x", "ko")
        c = Client(runner)
        await to_discussion(c)
        started = await c.until("turn.started")
        await c.until("message.delta")
        assert runner.session.active_turn.text == "여름에는 "
        c.send("user.message", text="잠깐만요, 질문이 있어요.", client_message_id="m1")
        cancelled = await c.until("turn.cancelled")
        assert cancelled == {"turnId": started["turnId"], "reason": "interrupted"}
        user = (await c.until("message.completed"))["message"]
        assert user["role"] == "user" and user["clientMessageId"] == "m1" and user["invited"] is False
        reply = (await c.until("message.completed"))["message"]
        assert reply["role"] == "tutor" and reply["turnNumber"] == 2
        # the interrupted scripted turn was not lost
        replay = (await c.until("message.completed"))["message"]
        assert replay["speakerId"] == "peer1" and replay["meta"]["mock"]["key"] == "1"
    finally:
        await registry.stop()


async def test_manual_pace_and_step(registry: SessionRegistry):
    runner = registry.create("x", "ko")
    c = Client(runner)
    await to_discussion(c, start=False)
    c.send("control.set_pace", auto=False)
    assert (await c.until("pace.changed"))["pace"]["auto"] is False
    c.send("discussion.start")
    assert (await c.until("message.completed"))["message"]["turnNumber"] == 1  # the first one comes by itself
    assert await c.quiet("turn.started")
    c.send("control.step")
    assert (await c.until("message.completed"))["message"]["turnNumber"] == 2
    assert await c.quiet("turn.started")
    c.send("control.set_pace", auto=True)
    assert (await c.until("message.completed"))["message"]["turnNumber"] == 3


async def test_pause_holds_the_next_turn(tmp_path, store):
    settings = make_settings(tmp_path, pace_base_seconds=0.15)
    registry = SessionRegistry(settings, store, fast_mock())
    try:
        runner = registry.create("x", "ko")
        c = Client(runner)
        await to_discussion(c)
        await c.until("message.completed")
        c.send("control.pause")
        assert (await c.until("status.changed"))["status"] == "paused"
        assert await c.quiet("turn.started", 0.5)
        c.send("control.set_pace", speed=2.0)
        c.send("control.resume")
        assert (await c.until("status.changed"))["status"] == "running"
        assert (await c.until("message.completed"))["message"]["turnNumber"] == 2
    finally:
        await registry.stop()


async def test_disconnect_pauses_and_reconnect_resumes(tmp_path, store):
    settings = make_settings(tmp_path, pace_base_seconds=0.05)
    registry = SessionRegistry(settings, store, fast_mock())
    try:
        runner = registry.create("x", "ko")
        c = Client(runner)
        await to_discussion(c)
        await c.until("message.completed")
        c.close()
        await asyncio.sleep(0.4)
        assert runner.session.status == "paused"
        turns = runner.session.turn_count
        await asyncio.sleep(0.3)
        assert runner.session.turn_count == turns  # nothing is generated for an empty room
        c2 = Client(runner)
        snap = (await c2.next())["data"]
        assert snap["status"] == "paused" and len(snap["messages"]) == len(runner.session.messages)
        assert (await c2.until("status.changed"))["status"] == "running"
        await c2.until("message.completed")
    finally:
        await registry.stop()


async def test_session_survives_restart(settings, store):
    first = SessionRegistry(settings, store, fast_mock())
    runner = first.create("x", "en")
    c = Client(runner)
    await to_discussion(c, start=False)
    c.send("discussion.start", language="ko")
    started = await c.until("phase.changed", lambda d: d["phase"] == "discussion")
    assert started["language"] == "ko"
    await c.until("message.completed", lambda d: d["message"]["turnNumber"] == 3)
    sid = runner.session.id
    await first.stop()

    second = SessionRegistry(settings, store, fast_mock())
    try:
        assert await second.get("nope") is None
        restored = await second.get(sid)
        s = restored.session
        assert s.phase == "discussion" and s.status == "paused" and s.turn_count >= 3
        assert s.language == "ko"
        assert s.scratch["mock"]["cursor"] == s.turn_count
        before = s.turn_count
        c2 = Client(restored)
        c2.send("control.resume")
        nxt = (await c2.until("message.completed"))["message"]
        assert nxt["turnNumber"] == before + 1 and nxt["meta"]["mock"]["key"] == str(before + 1)
        assert nxt["text"] == fast_mock().fx["turns"][before]["text"]["ko"]
    finally:
        await second.stop()


class Flaky(type(fast_mock())):
    def __init__(self):
        super().__init__()
        self.delay = 0
        self.fail = 1

    async def speak(self, session, decision, out):
        if self.fail:
            self.fail -= 1
            raise PipelineError("model returned nothing")
        await super().speak(session, decision, out)

    async def build_classroom(self, session):
        if session.scratch.pop("fail_build", True):
            session.scratch["fail_build"] = False
            raise RuntimeError("secret internal detail")
        return await super().build_classroom(session)


async def test_pipeline_errors_pause_and_retry(settings, store):
    registry = SessionRegistry(settings, store, Flaky())
    try:
        runner = registry.create("x", "ko")
        c = Client(runner)
        await c.until("message.completed")
        c.send("init.reply", text="기울어져서요")
        err = await c.until("error")
        assert err["code"] == "pipeline_error" and "secret" not in err["message"]
        c.send("control.resume")
        await c.until("phase.changed", lambda d: d["phase"] == "ready")
        c.send("discussion.start")
        err = await c.until("error")
        assert "model returned nothing" in err["message"] and err["recoverable"] is True
        assert (await c.until("status.changed"))["status"] == "paused"
        assert await c.quiet("turn.started")  # no retry storm
        c.send("control.resume")
        assert (await c.until("message.completed"))["message"]["turnNumber"] == 1
    finally:
        await registry.stop()


async def test_turn_limit_and_invalid_commands(tmp_path, store):
    registry = SessionRegistry(make_settings(tmp_path, max_turns=3), store, fast_mock())
    try:
        runner = registry.create("x", "ko")
        c = Client(runner)
        await c.until("message.completed")
        c.send("user.message", text="아직 토론 전인데요")
        assert (await c.until("error"))["code"] == "invalid_command"
        c.send("init.finish")
        await c.until("phase.changed", lambda d: d["phase"] == "ready")
        c.send("discussion.start")
        ended = await c.until("phase.changed", lambda d: d["phase"] == "ended")
        assert ended["reason"] == "turn_limit" and runner.session.turn_count == 3
        c.send("user.message", text="끝났나요?")
        assert (await c.until("error"))["code"] == "invalid_command"
    finally:
        await registry.stop()


async def test_event_log_records_commands_and_ui_events(registry: SessionRegistry, store):
    runner = registry.create("x", "ko")
    c = Client(runner)
    await to_discussion(c)
    c.send("ui.event", name="panel.open", data={"agentId": "peer1"})
    await c.until("message.completed")
    events = await store.list_events(runner.session.id)
    types = [e["type"] for e in events]
    assert types[0] == "session.created"
    assert "client.ui.event" in types and "client.init.reply" in types and "turn.started" in types
    assert "message.delta" not in types
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert (await store.list_sessions())[0]["sessionId"] == runner.session.id


def test_diff_states():
    a = KnowledgeState(beliefs=[Belief(id="1", text="x"), Belief(id="2", text="y")], explanation="old",
                       open_questions=["q1"])
    b = KnowledgeState(beliefs=[Belief(id="1", text="x!"), Belief(id="3", text="z")], explanation="new",
                       open_questions=["q2"])
    kinds = sorted((c.field, c.kind) for c in diff_states(a, b))
    assert kinds == [("beliefs", "added"), ("beliefs", "modified"), ("beliefs", "removed"),
                     ("explanation", "modified"), ("openQuestions", "added"), ("openQuestions", "removed")]
    assert diff_states(a, a) == []
