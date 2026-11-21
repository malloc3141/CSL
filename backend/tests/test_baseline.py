from __future__ import annotations

import json

import pytest

from app import llm as llm_module
from app.llm import extract_json
from app.orchestrator import SessionRegistry
from app.pipeline.baseline import BaselinePipeline
from helpers import Client

REFERENCE = "REFERENCE-ONLY-FOR-TUTOR"


class FakeLLM:
    def __init__(self):
        self.streams: list[list[dict]] = []
        self.moderator_calls = 0
        # Scripted setup chat: a str for a streamed message, a dict for a JSON reply. Empty = the defaults.
        self.guide: list = []
        self.guide_json_calls: list[str] = []

    async def stream(self, messages, **kwargs):
        self.streams.append(messages)
        if "setup guide" in messages[0]["content"] and self.guide:
            yield self.guide.pop(0)
            return
        for chunk in ("음, ", "그런가요?"):
            yield chunk

    async def complete(self, messages, **kwargs):
        # From the second reply on the setup guide says whether it is done: one JSON call.
        assert "setup guide" in messages[0]["content"] and [m["role"] for m in messages] == ["system", "user"]
        self.guide_json_calls.append(messages)
        reply = self.guide.pop(0) if self.guide else {"message": "그 부분을 살펴볼게요. 교실을 준비할게요.", "done": True}
        return reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)  # str: plain text, no JSON

    async def complete_json(self, messages, **kwargs):
        system, user = messages[0]["content"], messages[-1]["content"]
        if "design a simulated classroom" in system:
            return {
                "focus": "기울기가 무엇을 바꾸는가?",
                "tutor": {"reference": REFERENCE, "key_points": ["각도", "낮 길이"]},
                "peers": [
                    {"name": "민준", "origin": "내 설명에서", "description": "거리라고 생각", "explanation": "가까워져서",
                     "explanation_accuracy": "incorrect", "beliefs": [{"text": "궤도는 타원", "accuracy": "correct"}]},
                    {"name": "서연", "origin": "흔한 오개념", "description": "기울어서 가까워짐", "explanation": "기울어서",
                     "explanation_accuracy": "nonsense", "beliefs": [{"text": "23.5도", "accuracy": "correct"}]},
                    {"name": "extra", "beliefs": []},
                ],
            }
        if "hidden moderator" in system:
            self.moderator_calls += 1
            return {"speaker": "tutor", "invite_user": True}  # always asks for the tutor and an invitation
        assert "track what one simulated student" in system
        if "Student: 민준" not in user:
            return {"changed": False}
        current = json.loads(user.split("Current state:\n")[1].split("\n\nRecent discussion")[0])
        return {
            "changed": True,
            "beliefs": current["beliefs"] + [{"id": "new", "text": f"사실 {len(current['beliefs'])}", "accuracy": "correct"}],
            "explanation": "거리만으로는 부족하다",
            "explanation_accuracy": "partial",
            "open_questions": ["그럼 왜?", "두번째", "세번째"],
        }


@pytest.fixture
def fake_llm():
    fake = FakeLLM()
    previous = llm_module._llm
    llm_module.set_llm(fake)
    yield fake
    llm_module.set_llm(previous)


async def test_baseline_pipeline_flow(settings, store, fake_llm):
    registry = SessionRegistry(settings, store, BaselinePipeline())
    try:
        runner = registry.create("계절", "ko")
        s = runner.session
        c = Client(runner)
        for reply in ("기울어져서요", "햇빛을 더 받아서요"):  # ask -> probe -> closing message
            await c.until("message.completed", lambda d: d["message"]["role"] == "system")
            assert s.phase == "init"
            c.send("init.reply", text=reply)
        ready = await c.until("classroom.ready")
        assert [p["name"] for p in ready["participants"]] == ["Tutor", "민준", "서연"]  # peer_count = 2
        assert ready["states"]["peer2"]["state"]["explanationAccuracy"] is None  # invalid label dropped
        assert s.scratch["baseline"]["tutor"]["reference"] == REFERENCE

        c.send("discussion.start")
        invited = await c.until("user.invited")
        speakers = [m.speaker_id for m in s.transcript]
        assert speakers[0] == "tutor"  # the tutor opens
        assert all(a != b for a, b in zip(speakers, speakers[1:]))  # nobody speaks twice in a row
        assert len(speakers) >= 7 and speakers[-1] == "tutor"  # no invitation before turn 6
        assert s.last_message.id == invited["turnId"] and s.last_message.meta == {"invite": True}

        # peers never see the tutor's reference; the tutor does
        peer_prompts = [m[0]["content"] for m in fake_llm.streams if m[0]["content"].startswith("You are 민준")]
        assert peer_prompts and all(REFERENCE not in p for p in peer_prompts)
        assert any(REFERENCE in m[0]["content"] for m in fake_llm.streams if "You are the tutor" in m[0]["content"])
        # 민준's state grew by one belief per message, ids stay unique, open questions are capped
        state = s.state_of("peer1")
        ids = [b.id for b in state.beliefs]
        assert len(ids) == len(set(ids)) == 1 + len(speakers)
        assert state.open_questions == ["그럼 왜?", "두번째"] and state.explanation_accuracy == "partial"
        assert len(s.state_history("peer2")) == 1

        c.send("user.message", text="기울기 때문에 각도가 달라져요")
        await c.until("message.completed", lambda d: d["message"]["role"] == "user")
        react = (await c.until("message.completed"))["message"]
        feedback = (await c.until("message.completed"))["message"]
        assert react["role"] == "peer" and feedback["role"] == "tutor"
        assert any("has just explained their understanding" in m[0]["content"] for m in fake_llm.streams)
    finally:
        await registry.stop()


def test_extract_json():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"speaker": "peer1", "invite_user": false} hope that helps') == {
        "speaker": "peer1", "invite_user": False}
    with pytest.raises(ValueError):
        extract_json("no json here")
    with pytest.raises(ValueError):
        extract_json("{broken")


async def test_setup_chat_ends_only_on_a_closing_message(settings, store, fake_llm):
    """The classroom is built when the guide says it is done, not after a fixed number of replies."""
    fake_llm.guide = [
        "어떻게 이해하고 있나요?",  # ask
        "왜 그렇게 되나요?",  # probe
        # may close; answers in plain text instead of JSON, and the text asks: the chat goes on
        "말한 '더 받는다'는 게 무엇인지 좀 더 설명해볼까요?",
        # says it is done, but the message ends with a question: the learner is asked, so the chat goes on
        {"message": "좋아요. 조금만 더 설명해볼까요? 😊", "done": True},
        # told to close, still asks for more, without a question mark
        {"message": "그 부분이 어떻게 이어지는지도 말해 주세요.", "done": False},
        # closing message (a question mark in the middle is fine)
        {"message": "기울기가 무엇을 바꾸는가? 이 점을 중심으로 교실을 준비할게요.", "done": True},
    ]
    registry = SessionRegistry(settings, store, BaselinePipeline())
    try:
        runner = registry.create("계절", "ko")
        s = runner.session
        c = Client(runner)
        for n in range(5):
            await c.until("message.completed", lambda d: d["message"]["role"] == "system")
            assert s.phase == "init", n
            c.send("init.reply", text=f"답 {n + 1}")
        await c.until("classroom.ready")
        assert [m.role for m in s.init_transcript] == ["system", "user"] * 5 + ["system"]
        assert s.init_transcript[-1].text.endswith("교실을 준비할게요.")
        # The first question and the first follow-up are streamed and always wait for an answer.
        asked = [m[0]["content"] for m in fake_llm.streams]
        assert len(asked) == 2 and all('"done"' not in system for system in asked)
        # After that the guide chooses; after four replies it is told to close.
        chose = [m[0]["content"] for m in fake_llm.guide_json_calls]
        assert len(chose) == 4 and all('"done": true|false' in system for system in chose)
        assert "(a)" in chose[0] and "(a)" in chose[1]
        assert "(a)" not in chose[2] and "do not ask anything" in chose[2]
        # The chat so far goes in as one block of text (as chat turns the model answers in plain text).
        block = fake_llm.guide_json_calls[0][1]["content"]
        assert "Setup chat so far:\nGuide: 어떻게 이해하고 있나요?\nLearner: 답 1\n" in block and "Learner: 답 2" in block
    finally:
        await registry.stop()
