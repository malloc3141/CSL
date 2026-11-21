"""Trace committed learner/peer turn pairs through the ordinary CSL runner."""
from __future__ import annotations

import json

from app import llm
from app.orchestrator import SessionRunner
from app.pipeline.csl import CslPipeline
from app.protocol import Belief, KnowledgeState, Participant, StateVersion, UserMessage
from app.session import Session


ORIGINAL = "A circle sticker grants display permission."
REVISED = "A circle sticker alone cannot establish display permission."
UNRELATED = Belief(id="catalog-code", text="The catalog code identifies a booklet.")
EVIDENCE = "K17 has a circle sticker and its signed card says display permission was declined."
LEARNER_TURNS = (
    "K17 has a circle sticker. Is it cleared for display?",
    "I disagree. Are you sure?",
    EVIDENCE,
    "P42 also has a circle sticker, but its card is missing. Can it go on display?",
)


class ClassroomModel:
    """Supply one warranted edit and let the speaker read the actual response prompt."""

    def __init__(self):
        self.public_calls = []
        self.grading_calls = []

    async def complete(self, messages, **kwargs):
        self.public_calls.append(messages)
        assert messages[0]["content"][1]["text"].startswith("ROLE: neutral situation reader.")
        return "The learner is examining this booklet's display permission."

    async def stream(self, messages, **kwargs):
        self.public_calls.append(messages)
        tail = messages[-1]["content"][-1]["text"]
        assert "The learner is examining this booklet's display permission." in tail
        if REVISED in tail:
            yield REVISED
        else:
            assert ORIGINAL in tail
            yield ORIGINAL

    async def complete_json(self, messages, **kwargs):
        system = messages[0]["content"]
        if isinstance(system, str):
            assert system.startswith("ROLE: private accuracy grader.")
            self.grading_calls.append(json.loads(messages[-1]["content"]))
            return {"beliefs": [{"id": "display", "accuracy": "correct"}], "explanation_accuracy": "correct"}
        self.public_calls.append(messages)
        assert system[1]["text"].startswith("ROLE: public knowledge-state proposer.")
        latest = messages[-1]["content"][-2]["text"]
        if not latest.endswith(EVIDENCE):
            return {"changed": False}
        return {
            "changed": True,
            "evidence": {"kind": "counterexample", "quote": EVIDENCE},
            "belief_edits": [{"op": "revise", "id": "display", "text": REVISED}],
            "explanation": REVISED,
        }


async def test_hidden_reference_swap_keeps_the_same_four_turn_trajectory(settings, store, monkeypatch):
    references = ("Indigo-73 binding batch", "Ochre-29 printing batch")
    public_runs = []
    for reference in references:
        fake = ClassroomModel()
        monkeypatch.setattr(llm, "_llm", fake)
        session = Session(reference[:5], "How do volunteers decide what to display?", "en", 60)
        session.phase = "discussion"
        session.participants = [
            Participant(id="tutor", name="Tutor", role="tutor"),
            Participant(id="peer1", name="Mira", role="peer"),
        ]
        session.scratch = {"baseline": {"tutor": {"reference": reference}}}
        initial = KnowledgeState(beliefs=[Belief(id="display", text=ORIGINAL, accuracy="incorrect"), UNRELATED],
                                 explanation=ORIGINAL, explanation_accuracy="incorrect")
        session.states["peer1"] = [StateVersion(agent_id="peer1", version=0, state=initial, created_at=0)]
        runner = SessionRunner(session, CslPipeline(), store, settings)
        versions, replies = [], []
        for turn in LEARNER_TURNS:
            await runner._handle_discussion_command("user.message", UserMessage(text=turn))
            versions.append(session.states["peer1"][-1].version)
            await runner._agent_turn()
            assert session.last_message.role == "peer"
            replies.append(session.last_message.text)
            versions.append(session.states["peer1"][-1].version)

        assert replies == [ORIGINAL, ORIGINAL, REVISED, REVISED]
        assert versions == [0, 0, 0, 0, 1, 1, 1, 1]
        change = session.states["peer1"][-1]
        assert change.turn_id == session.transcript[4].id
        assert change.state.beliefs == [Belief(id="display", text=REVISED, accuracy="correct"), UNRELATED]
        assert change.state.explanation == REVISED and change.state.open_questions == []
        assert fake.grading_calls == [{
            "reference": reference, "beliefs": [{"id": "display", "text": REVISED}], "explanation": REVISED,
        }]
        observed = json.dumps([fake.public_calls, replies, change.state.wire()])
        assert all(label not in observed for label in references)
        public_runs.append(fake.public_calls)
    assert public_runs[0] == public_runs[1]
