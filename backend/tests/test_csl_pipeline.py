"""CSL pipeline: discussion flow on a fake LLM, and the request layout the prompt cache depends on."""
from __future__ import annotations

import json

import pytest

from app import llm as llm_module
from app.orchestrator import SessionRegistry
from app.pipeline.csl import CslPipeline
from app.pipeline.csl.prompting import STRIDE, build_messages, cache_breakpoints
from app.protocol import Message
from helpers import Client

REFERENCE = "REFERENCE-ONLY-FOR-TUTOR"


def _role(messages) -> str:
    return messages[0]["content"][1]["text"].split("\n", 1)[0] if isinstance(messages[0]["content"], list) else ""


class FakeLLM:
    """Answers the knowledge side (baseline prompts, plain strings) and the discussion side (block lists)."""

    def __init__(self):
        self.discussion_calls: list[list[dict]] = []  # every request built by prompting.build_messages

    async def stream(self, messages, **kwargs):
        if isinstance(messages[0]["content"], list):
            self.discussion_calls.append(messages)
        for chunk in ("음, ", "그런가요?"):
            yield chunk

    async def complete(self, messages, **kwargs):
        assert _role(messages) == "ROLE: hidden moderator. You only decide who speaks next; nobody sees your output."
        self.discussion_calls.append(messages)
        allowed = "Invitation allowed now: yes" in messages[1]["content"][-1]["text"]
        return json.dumps({"speaker": "tutor", "invite_user": allowed})

    async def complete_json(self, messages, **kwargs):
        system, user = messages[0]["content"], messages[-1]["content"]
        if "design a simulated classroom" in system:
            return {
                "focus": "기울기가 무엇을 바꾸는가?",
                "tutor": {"reference": REFERENCE, "key_points": ["각도", "낮 길이"]},
                "peers": [
                    {"name": "민준", "beliefs": [{"text": "궤도는 타원", "accuracy": "correct"}], "explanation": "가까워져서"},
                    {"name": "서연", "beliefs": [{"text": "23.5도", "accuracy": "correct"}], "explanation": "기울어서"},
                ],
            }
        assert "track what one simulated student" in system
        if "Student: 민준" not in user:
            return {"changed": False}
        return {"changed": True, "beliefs": [{"id": "new", "text": f"사실 {len(user)}"}], "explanation": "바뀜"}


@pytest.fixture
def fake_llm():
    fake = FakeLLM()
    previous = llm_module._llm
    llm_module.set_llm(fake)
    yield fake
    llm_module.set_llm(previous)


def _texts(messages) -> list[str]:
    return [b["text"] for b in messages[1]["content"]]


async def test_csl_discussion_flow_and_cache_layout(settings, store, fake_llm):
    registry = SessionRegistry(settings, store, CslPipeline())
    try:
        runner = registry.create("계절", "ko")
        s = runner.session
        c = Client(runner)
        for reply in ("기울어져서요", "햇빛을 더 받아서요"):
            await c.until("message.completed", lambda d: d["message"]["role"] == "system")
            c.send("init.reply", text=reply)
        await c.until("classroom.ready")
        c.send("discussion.start")
        await c.until("user.invited")

        speakers = [m.speaker_id for m in s.transcript]
        assert speakers[0] == "tutor"
        assert all(a != b for a, b in zip(speakers, speakers[1:]))
        assert len(speakers) >= 7 and speakers[-1] == "tutor"  # no invitation before turn 6
        assert s.last_message.meta == {"invite": True}

        c.send("user.message", text="기울기 때문에 각도가 달라져요")
        await c.until("message.completed", lambda d: d["message"]["role"] == "user")
        react = (await c.until("message.completed"))["message"]
        feedback = (await c.until("message.completed"))["message"]
        assert react["role"] == "peer" and feedback["role"] == "tutor"

        calls = fake_llm.discussion_calls
        assert len(calls) >= 10
        # Hidden reference: only in the tutor's role block, never in anything a peer or the moderator gets.
        for m in calls:
            role, flat = _role(m), json.dumps(m, ensure_ascii=False)
            assert (REFERENCE in flat) == (role == "ROLE: the tutor."), role
        # Learner messages are rendered with the learner label and the invitation note.
        assert any("[T" in t and "나 (answering the tutor's invitation): 기울기" in t for t in _texts(calls[-1]))

        # The cache invariants: one session block for every call; per role, an identical system message, and
        # each request's transcript blocks are an exact prefix of the next request's.
        assert len({json.dumps(m[0]["content"][0], ensure_ascii=False) for m in calls}) == 1
        by_role: dict[str, list] = {}
        for m in calls:
            by_role.setdefault(_role(m), []).append(m)
        assert len(by_role) == 3  # moderator, peer, tutor
        for role, reqs in by_role.items():
            for prev, cur in zip(reqs, reqs[1:]):
                assert prev[0] == cur[0], role
                before = _texts(prev)[:-1]  # without the per-call tail
                if before != ["(The discussion has not started yet.)"]:
                    assert _texts(cur)[: len(before)] == before, role
        for m in calls:
            assert cache_breakpoints(m) <= 4
            assert "cache_control" not in m[1]["content"][-1]  # the tail is never cached
            # Persona and state go in the tail, so all peers share the cached part.
            assert all(name not in m[0]["content"][1]["text"] for name in ("민준", "서연", "궤도는 타원"))
    finally:
        await registry.stop()


def _msg(i: int) -> Message:
    return Message(id=f"m{i}", channel="discussion", role="peer", speaker_id="peer1", speaker_name="민준",
                   text=f"발언 {i}", turn_number=i, created_at=0.0)


def test_breakpoints_stay_within_limit_and_on_stable_positions():
    for n in (0, 1, STRIDE - 1, STRIDE, STRIDE + 1, 2 * STRIDE + 3, 60):
        msgs = build_messages("S", "R", [_msg(i + 1) for i in range(n)], "ko", "tail")
        blocks = msgs[1]["content"]
        cached = [i for i, b in enumerate(blocks) if "cache_control" in b]
        assert cache_breakpoints(msgs) <= 4
        assert "cache_control" not in blocks[-1]
        if n:
            assert cached[-1] == n - 1  # the last message
        if n > STRIDE:
            stride_point = ((n - 1) // STRIDE) * STRIDE - 1
            assert stride_point in cached and (stride_point + 1) % STRIDE == 0
    # Rendering depends only on the message: the same message renders the same in a longer transcript.
    short = build_messages("S", "R", [_msg(1), _msg(2)], "ko", "a")[1]["content"]
    long = build_messages("S", "R", [_msg(1), _msg(2), _msg(3)], "ko", "b")[1]["content"]
    assert short[0]["text"] == long[0]["text"] == "[T1] 민준: 발언 1"
