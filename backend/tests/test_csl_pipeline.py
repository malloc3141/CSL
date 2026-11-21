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

REFERENCE = "PRIVATE-TUTOR-REFERENCE"
PROPOSER = "ROLE: public knowledge-state proposer."
GRADER = "ROLE: private accuracy grader."
EXTRACTOR = "ROLE: neutral situation reader."
SITUATION = "이 상황에서 기울기를 어떻게 해석할지 묻고 있어요."
LEARNER_EVIDENCE = "기울기 때문에 각도가 달라져요"
NEW_BELIEF = "기울면 햇빛이 들어오는 각도가 달라져요."


def _role(messages) -> str:
    system = messages[0]["content"]
    return (system[1]["text"] if isinstance(system, list) else system).split("\n", 1)[0]


class FakeLLM:
    """Record block requests and supply responses for one classroom discussion."""

    def __init__(self):
        self.discussion_calls: list[list[dict]] = []  # every request built by prompting.build_messages
        self.grading_calls: list[dict] = []

    async def stream(self, messages, **kwargs):
        if isinstance(messages[0]["content"], list):
            self.discussion_calls.append(messages)
        for chunk in ("음, ", "그런가요?"):
            yield chunk

    async def complete(self, messages, **kwargs):
        if isinstance(messages[0]["content"], str):  # the setup chat's closing message (baseline, plain strings)
            return json.dumps({"message": "교실을 준비할게요.", "done": True})
        self.discussion_calls.append(messages)
        if _role(messages) == EXTRACTOR:
            return SITUATION
        assert _role(messages).startswith("ROLE: hidden moderator.")
        allowed = "Invitation allowed now: yes" in messages[1]["content"][-1]["text"]
        return json.dumps({"speaker": "tutor", "invite_user": allowed})

    async def complete_json(self, messages, **kwargs):
        if _role(messages).startswith("You design a simulated classroom"):
            return {
                "focus": "기울기가 무엇을 바꾸는가?",
                "tutor": {"reference": REFERENCE, "key_points": ["각도", "낮 길이"]},
                "peers": [
                    {"name": "민준", "origin": "학습자의 설명", "description": "거리에 주목해요",
                     "beliefs": [{"text": "태양에 가까워지면 여름이 돼요", "accuracy": "incorrect"}],
                     "explanation": "지구가 가까워져서요", "explanation_accuracy": "incorrect"},
                    {"name": "서연", "origin": "다른 설명", "description": "낮의 길이에 주목해요",
                     "beliefs": [{"text": "낮이 길면 땅이 오래 데워져요", "accuracy": "correct"}],
                     "explanation": "햇빛을 오래 받아서요", "explanation_accuracy": "partial"},
                ],
            }
        if _role(messages) == GRADER:
            payload = json.loads(messages[-1]["content"])
            self.grading_calls.append(payload)
            return {"beliefs": [{"id": b["id"], "accuracy": "correct"} for b in payload["beliefs"]]}
        assert _role(messages) == PROPOSER
        self.discussion_calls.append(messages)
        user = messages[-1]["content"]
        latest_turn, tail = user[-2]["text"], user[-1]["text"]
        if "Student: 민준" not in tail or not latest_turn.endswith(LEARNER_EVIDENCE):
            return {"changed": False}
        return {
            "changed": True,
            "evidence": {"kind": "mechanism", "quote": LEARNER_EVIDENCE},
            "belief_edits": [{"op": "add", "text": NEW_BELIEF}],
        }


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

        c.send("user.message", text=LEARNER_EVIDENCE)
        learner = (await c.until("message.completed", lambda d: d["message"]["role"] == "user"))["message"]
        update = (await c.until("state.updated"))["update"]
        assert (update["agentId"], update["version"], update["turnId"]) == ("peer1", 1, learner["id"])
        assert [(ch["field"], ch["kind"]) for ch in update["changes"]] == [("beliefs", "added")]
        added = update["state"]["beliefs"][-1]
        assert (added["text"], added["accuracy"]) == (NEW_BELIEF, "correct")
        assert fake_llm.grading_calls == [{
            "reference": REFERENCE,
            "beliefs": [{"id": added["id"], "text": NEW_BELIEF}],
        }]
        assert len(s.state_history("peer2")) == 1
        react = (await c.until("message.completed"))["message"]
        feedback = (await c.until("message.completed"))["message"]
        assert react["role"] == "peer" and feedback["role"] == "tutor"

        calls = fake_llm.discussion_calls
        assert len(calls) >= 10
        for m in calls:
            role, flat = _role(m), json.dumps(m, ensure_ascii=False)
            assert (REFERENCE in flat) == (role == "ROLE: the tutor."), role
            is_peer = role.startswith("ROLE: one of the students.")
            assert (SITUATION in _texts(m)[-1]) == is_peer
            assert SITUATION not in json.dumps(m[0], ensure_ascii=False)
            assert all(SITUATION not in block for block in _texts(m)[:-1])
            if role == EXTRACTOR:
                for private in ("거리에 주목해요", "태양에 가까워지면 여름이 돼요", "낮이 길면 땅이 오래 데워져요"):
                    assert private not in flat
        # Learner messages are rendered with the learner label and the invitation note.
        assert any("[T" in t and "학습자 (answering the tutor's invitation): 기울기" in t for t in _texts(calls[-1]))

        # The cache invariants: one session block for every call; per role, an identical system message, and
        # each request's transcript blocks are an exact prefix of the next request's.
        assert len({json.dumps(m[0]["content"][0], ensure_ascii=False) for m in calls}) == 1
        by_role: dict[str, list] = {}
        for m in calls:
            by_role.setdefault(_role(m), []).append(m)
        assert len(by_role) == 5 and {PROPOSER, EXTRACTOR} <= by_role.keys()
        peer_requests = next(reqs for role, reqs in by_role.items() if role.startswith("ROLE: one of the students."))
        assert len(by_role[EXTRACTOR]) == len(peer_requests)
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
            assert all(name not in m[0]["content"][1]["text"] for name in ("민준", "서연", "태양에 가까워지면"))
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


# ---------------------------------------------------------------- discussion rules on a hand-built session

from app.pipeline.csl import discussion  # noqa: E402
from app.protocol import Participant  # noqa: E402
from app.session import Session  # noqa: E402

SPEAKERS = {"tutor": ("tutor", "Tutor"), "peer1": ("peer", "Marcus"), "peer2": ("peer", "Priya"), "user": ("user", "You")}


def make_session(speakers: list[str], turn_limit: int = 60, closing_last: bool = False) -> Session:
    s = Session("s1", "Why is summer hotter?", "en", turn_limit)
    s.participants = [
        Participant(id="tutor", role="tutor", name="Tutor"),
        Participant(id="peer1", role="peer", name="Marcus", peer_index=0),
        Participant(id="peer2", role="peer", name="Priya", peer_index=1),
    ]
    for i, sid in enumerate(speakers, start=1):
        role, name = SPEAKERS[sid]
        meta = {"closing": True} if closing_last and i == len(speakers) else {}
        s.messages.append(Message(id=f"m{i}", channel="discussion", role=role, speaker_id=sid, speaker_name=name,
                                  text=f"message {i}?", turn_number=i, meta=meta, created_at=0.0))
    return s


class ModeratorLLM:
    def __init__(self, reply: dict):
        self.reply = reply
        self.streamed: list = []

    async def complete(self, messages, **kwargs):
        return json.dumps(self.reply)

    async def stream(self, messages, **kwargs):
        self.streamed.append(messages)
        for chunk in self.reply.get("chunks", ["ok"]):
            yield chunk


@pytest.fixture
def moderator(monkeypatch):
    def install(reply: dict) -> ModeratorLLM:
        fake = ModeratorLLM(reply)
        monkeypatch.setattr(llm_module, "_llm", fake)
        return fake
    return install


ROTATION = ["tutor", "peer1", "peer2", "peer1", "peer2", "peer1", "peer2"]


async def test_moderator_points_the_speaker_at_an_open_question(moderator):
    s = make_session(ROTATION)  # T5 is Priya's (peer2) question, T6 Marcus's
    moderator({"speaker": "peer1", "respond_to": 5, "tutor": "none", "wrap_up": False, "invite_user": False})
    d = await discussion.select_speaker(s)
    assert d.agent_id == "peer1" and d.meta == {"respondTo": 5}
    tail = discussion.speak_request(s, d)[1]["content"][-1]["text"]
    assert "[T5] from Priya" in tail and tail.startswith("You are Marcus")

    # Nobody is told to answer their own question, and a made-up turn number is ignored.
    moderator({"speaker": "peer1", "respond_to": 6})
    assert (await discussion.select_speaker(s)).meta == {}
    moderator({"speaker": "peer1", "respond_to": 99})
    assert (await discussion.select_speaker(s)).meta == {}

    # A question one student already took up is not handed to the next one as well.
    s.messages[-1].meta = {"respondTo": 5}
    moderator({"speaker": "peer1", "respond_to": 5})
    assert (await discussion.select_speaker(s)).meta == {}


async def test_tutor_steps_in_only_with_a_reason(moderator):
    # Two students since the tutor, but the moderator sees no reason: the students keep going.
    moderator({"speaker": "peer1", "tutor": "none"})
    d = await discussion.select_speaker(make_session(ROTATION))
    assert (d.agent_id, d.directive) == ("peer1", None)
    # Picking the tutor as a speaker is not how the tutor gets in.
    moderator({"speaker": "tutor"})
    assert (await discussion.select_speaker(make_session(ROTATION))).agent_id in ("peer1", "peer2")


@pytest.mark.parametrize("reason, directive", [
    ("stagnation", "unstick"), ("off_topic", "refocus"), ("missing_information", "inform"),
])
async def test_each_reason_gives_the_tutor_its_instruction(moderator, reason, directive):
    moderator({"speaker": "peer1", "tutor": reason, "respond_to": 5})
    d = await discussion.select_speaker(make_session(ROTATION))
    assert (d.agent_id, d.directive, d.meta) == ("tutor", directive, {"intervention": reason})
    assert discussion.TUTOR_DIRECTIVES[directive] in discussion.speak_request(make_session(ROTATION), d)[1]["content"][-1]["text"]


async def test_wrap_up_then_end(moderator):
    long = ["tutor"] + ["peer1", "peer2"] * 8  # 17 messages, past WRAP_UP_MIN_TURN
    moderator({"speaker": "peer1", "wrap_up": True})
    d = await discussion.select_speaker(make_session(long))
    assert (d.agent_id, d.directive, d.meta) == ("tutor", "close", {"closing": True})
    # Too early to close: the moderator's wish is ignored.
    assert (await discussion.select_speaker(make_session(ROTATION))).directive != "close"
    # After the closing message the discussion ends, unless the learner spoke after it.
    assert (await discussion.select_speaker(make_session(long + ["tutor"], closing_last=True))).end
    d = await discussion.select_speaker(make_session(long + ["tutor", "user"], closing_last=False))
    assert not d.end and d.directive == "react"


async def test_tutor_closes_just_before_the_turn_limit(moderator):
    moderator({"speaker": "peer1"})
    d = await discussion.select_speaker(make_session(ROTATION, turn_limit=len(ROTATION) + 1))
    assert (d.agent_id, d.directive) == ("tutor", "close")


class Sink:
    def __init__(self):
        self.text = ""

    async def write(self, chunk: str) -> None:
        self.text += chunk


@pytest.mark.parametrize("chunks, expected", [
    (["Mar", "cus: I think ", "so."], "I think so."),
    (["[T3] Marcus", ":", " hi"], "hi"),
    (["peer1: hi"], "hi"),
    (["Marcus thinks so"], "Marcus thinks so"),  # the name, but not a label
    (["Mark my words"], "Mark my words"),
    (["I agree, Marcus: it's the angle."], "I agree, Marcus: it's the angle."),
    (["M"], "M"),  # short reply still gets out on flush
])
async def test_name_prefix_is_stripped_only_at_the_start(moderator, chunks, expected):
    fake = moderator({"chunks": chunks})
    s = make_session(ROTATION)
    out = Sink()
    await discussion.speak(s, discussion.SpeakerDecision(agent_id="peer1"), out)
    assert out.text == expected and fake.streamed


async def test_students_get_two_turns_after_the_tutor(moderator):
    # One student since the tutor: a reason to step in is not enough yet, and the request says so.
    moderator({"speaker": "peer2", "tutor": "stagnation", "respond_to": 8, "invite_user": True})
    s = make_session(ROTATION + ["tutor", "peer1"])
    d = await discussion.select_speaker(s)
    assert d.agent_id == "peer2" and d.meta == {"respondTo": 8} and not d.invite_user
    assert "Tutor may step in now: no" in discussion.moderator_request(s, False, False)[1]["content"][-1]["text"]
    d = await discussion.select_speaker(make_session(ROTATION + ["tutor", "peer1", "peer2"]))
    assert d.agent_id == "tutor" and d.directive == "invite"  # an invitation outranks the intervention
