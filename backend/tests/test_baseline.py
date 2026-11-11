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

    async def stream(self, messages, **kwargs):
        self.streams.append(messages)
        for chunk in ("음, ", "그런가요?"):
            yield chunk

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
        for reply in ("기울어져서요", "햇빛을 더 받아서요"):  # ask -> probe -> close
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
