"""Exercise committed-message state tracking with controlled per-student judgments."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app import llm as llm_module
from app.main import create_app
from app.orchestrator import Connection, SessionRunner
from app.pipeline.csl import CslPipeline
from app.pipeline.csl import _state_updates
from app.protocol import Belief, KnowledgeState, Message, Participant, StateVersion
from app.session import Session


LEGACY_ID = " old/catalog-rule:7d310 "
QUESTION = "Does the date tell me when the object was made?"
EVIDENCE = "The card labels 1975 as the cataloging date for a ledger written in 1902."
REVISED_RULE = "A cataloging date can be later than the date the object was made."


@pytest.fixture
def classroom():
    session = Session("class", "How should we read the archive cards?", "en", 60)
    session.participants = [
        Participant(id="tutor", name="Tutor", role="tutor"),
        Participant(id="peer1", name="Ada", role="peer"),
        Participant(id="peer2", name="Kai", role="peer"),
    ]
    session.scratch = {"baseline": {"tutor": {"reference": "PRIVATE-REFERENCE"}, "last_invite": 0}}
    state = KnowledgeState(
        beliefs=[
            Belief(id=LEGACY_ID, text="The date on a card always says when the object was made.", accuracy="incorrect"),
            Belief(id="other/key:42", text="  A title helps me find a related card.  ", accuracy=None),
        ],
        explanation="I read the card's date as the object's date.",
        explanation_accuracy="incorrect",
        open_questions=[QUESTION],
    )
    earlier = state.model_copy(deep=True)
    earlier.beliefs.append(Belief(id="peer1-n1", text="Previously withdrawn belief"))
    session.states["peer1"] = [
        StateVersion(agent_id="peer1", version=0, state=earlier, created_at=0.0),
        StateVersion(agent_id="peer1", version=1, state=state, created_at=1.0),
    ]
    session.states["peer2"] = [
        StateVersion(agent_id="peer2", version=0, created_at=0.0,
                     state=KnowledgeState(explanation="KAI-PRIVATE-EXPLANATION")),
    ]
    return Session.restore(session.dump())


def commit(session, text, *, speaker="user", meta=None):
    participant = session.participant(speaker)
    turn = session.turn_count + 1
    message = Message(
        id=f"turn-{turn}", channel="discussion", turn_number=turn,
        role=participant.role if participant else "user", speaker_id=speaker,
        speaker_name=participant.name if participant else "Learner",
        text=text, meta=meta or {}, created_at=float(turn),
    )
    session.messages.append(message)
    return message


@pytest.fixture
def tracker(monkeypatch):
    class Tracker:
        def __init__(self):
            self.by_student = {}
            self.calls = {}
            self.graded = []
            self.grade = self.default_grade

        async def default_grade(self, payload):
            return {
                "beliefs": [{"id": b["id"], "accuracy": "partial" if b["id"] == LEGACY_ID else "correct"}
                            for b in payload["beliefs"]],
                **({"explanation_accuracy": "correct"} if "explanation" in payload else {}),
            }

        async def complete_json(self, messages, **kwargs):
            assert kwargs["fast"] is True
            if messages[0]["content"] == _state_updates.GRADER_ROLE:
                payload = json.loads(messages[-1]["content"])
                self.graded.append(payload)
                return await self.grade(payload)
            assert messages[0]["content"][1]["text"] == _state_updates.PROPOSAL_ROLE
            tail = messages[-1]["content"][-1]["text"]
            peer_id = next(pid for pid, name in (("peer1", "Ada"), ("peer2", "Kai"))
                           if f"Student: {name} ({pid})" in tail)
            self.calls[peer_id] = messages
            reply = self.by_student.get(peer_id, {"changed": False})
            if isinstance(reply, Exception):
                raise reply
            if callable(reply):
                return await reply()
            return reply

    fake = Tracker()
    monkeypatch.setattr(llm_module, "_llm", fake)
    return fake


def proposal(**edits):
    return {"changed": True, "evidence": {"kind": "counterexample", "quote": EVIDENCE}, **edits}


def test_hosted_transfer_proposal_accepts_its_turn_number():
    # Captured message 7. Parsing is separate from the proposer's learning-vs-application judgment.
    captured = {
        "changed": True,
        "evidence": {"kind": "counterexample", "turn_number": 7, "quote": (
            "Booklet P42 also has a round sticker, but we cannot see its card. Can we decide whether to display it?"
        )},
        "belief_edits": [{"op": "revise", "id": "permission", "text": (
            "A round sticker alone does not guarantee that a booklet is cleared for the display table, "
            "and without the catalog card, we cannot confirm display permission even if the sticker is present."
        )}],
        "explanation": (
            "The round sticker might be part of the process, but it's not the final decision—if the catalog card "
            "says 'Display permission declined,' then the booklet shouldn't go on the display table even with a "
            "round sticker. Now, if we can't see the catalog card, we can't confirm whether permission was granted, "
            "so we can't decide to display it based on the sticker alone."
        ),
        "question_edits": [],
    }
    assert _state_updates._Proposal.model_validate(captured).model_dump(exclude_unset=True) == captured


@pytest.mark.parametrize("paraphrased", [False, True])
async def test_prior_citation_with_fresh_observation_revises_the_target_belief(classroom, tracker, paraphrased):
    first = commit(classroom, EVIDENCE, speaker="tutor")
    text = "I disagree. This second ledger was written decades before its catalog date too."
    latest = commit(classroom, text)
    source_excerpt = "The ledger predates its cataloging in 1975." if paraphrased else first.text
    latest_excerpt = "The second ledger was also made before cataloging." if paraphrased else latest.text
    events = []
    classroom.log = lambda kind, data: events.append((kind, data))
    tracker.by_student["peer1"] = proposal(
        evidence={"kind": "counterexample", "turn_number": first.turn_number,
                  "quote": source_excerpt, "latest_quote": latest_excerpt},
        belief_edits=[{"op": "revise", "id": LEGACY_ID, "text": REVISED_RULE}],
    )
    [update] = await CslPipeline().update_states(classroom, latest)
    assert update.state.beliefs == [Belief(id=LEGACY_ID, text=REVISED_RULE, accuracy="partial"),
                                   classroom.state_of("peer1").beliefs[1]]
    assert len(tracker.graded) == 1
    [(kind, citation)] = events
    assert kind == "state.proposal_citation"
    assert (citation["agentId"], citation["citedTurnNumber"], citation["turnNumber"]) == ("peer1", 1, 2)
    expected_mismatches = {"evidence.quote", "evidence.latest_quote"} if paraphrased else set()
    assert set(citation["mismatchedFields"]) == expected_mismatches
    assert all(text not in json.dumps(citation) for text in (
        first.text, latest.text, source_excerpt, latest_excerpt, "PRIVATE-REFERENCE",
    ))


async def test_external_observation_can_contradict_a_peers_own_quoted_prediction(classroom, tracker):
    prediction = commit(classroom, "I expect the ledger and catalog entry to have the same date.", speaker="peer1")
    latest = commit(classroom, EVIDENCE)
    tracker.by_student["peer1"] = proposal(
        evidence={"kind": "counterexample", "turn_number": latest.turn_number, "quote": EVIDENCE,
                  "support": {"turn_number": prediction.turn_number, "quote": prediction.text}},
        belief_edits=[{"op": "revise", "id": LEGACY_ID, "text": REVISED_RULE}],
    )
    [update] = await CslPipeline().update_states(classroom, latest)
    assert update.state.beliefs[0].text == REVISED_RULE and len(tracker.graded) == 1


async def test_doubt_about_an_existing_claim_cannot_supply_a_counterexample(classroom, tracker):
    latest = commit(classroom, "I disagree. Are you sure about the date on a card?")
    # The model cited just the topic of the challenge as though it were an observation.
    tracker.by_student["peer1"] = proposal(
        evidence={"kind": "counterexample", "turn_number": latest.turn_number, "quote": "the date on a card"},
        belief_edits=[{"op": "revise", "id": LEGACY_ID, "text": REVISED_RULE}],
    )
    events = []
    classroom.log = lambda kind, data: events.append((kind, data))
    assert await CslPipeline().update_states(classroom, latest) == []
    assert not tracker.graded and events[0][1]["reason"] == "no_new_evidence"


@pytest.mark.parametrize(("citation", "reason"), [
    ({"turn_number": 2, "quote": EVIDENCE}, "invalid_turn"),  # hole in the saved transcript
    ({"turn_number": 4, "quote": EVIDENCE}, "invalid_turn"),
    ({"turn_number": 1, "quote": "A fabricated quote.", "latest_quote": "I disagree."}, "no_new_evidence"),
    ({"turn_number": 1, "quote": EVIDENCE, "latest_quote": "Another observation."}, "no_new_evidence"),
    ({"turn_number": 1, "quote": EVIDENCE}, "no_new_evidence"),
    ({"turn_number": 1, "quote": EVIDENCE, "latest_quote": "I disagree."}, "no_new_evidence"),
    ({"turn_number": 3, "quote": "I disagree.", "unknown_field": "PRIVATE-MODEL-DRAFT"}, "schema"),
])
async def test_bad_citations_have_specific_reasons_and_keep_the_state(classroom, tracker, citation, reason):
    commit(classroom, EVIDENCE, speaker="tutor")
    latest = commit(classroom, "I disagree.")
    latest.turn_number = 3
    events = []
    classroom.log = lambda kind, data: events.append((kind, data))
    tracker.by_student["peer1"] = proposal(
        evidence={"kind": "counterexample", **citation},
        belief_edits=[{"op": "revise", "id": LEGACY_ID, "text": REVISED_RULE}],
    )
    before = classroom.dump()
    assert await CslPipeline().update_states(classroom, latest) == []
    assert classroom.dump() == before and not tracker.graded
    prompt = tracker.calls["peer1"][-1]["content"][-1]["text"]
    assert "[1, 3]" in prompt and "[T3]" in prompt
    assert '"turn_number": 3' in prompt
    [(kind, data)] = events  # peer2's ordinary unchanged decision is silent
    assert kind == "state.proposal_rejected" and data["reason"] == reason
    assert (data["agentId"], data["turnNumber"], data["citedTurnNumber"]) == ("peer1", 3, citation["turn_number"])
    assert "PRIVATE-MODEL-DRAFT" not in json.dumps(data)
    assert "PRIVATE-REFERENCE" not in json.dumps(data)
    assert EVIDENCE not in json.dumps(data)


async def test_tutor_fact_role_must_match_the_cited_message(classroom, tracker):
    earlier = commit(classroom, EVIDENCE)
    latest = commit(classroom, "This second ledger also predates the date printed on its card.", speaker="tutor")
    events = []
    classroom.log = lambda kind, data: events.append((kind, data))
    tracker.by_student["peer1"] = proposal(
        evidence={"kind": "tutor_fact", "turn_number": earlier.turn_number, "quote": earlier.text,
                  "latest_quote": latest.text},
        explanation=REVISED_RULE,
    )
    assert await CslPipeline().update_states(classroom, latest) == []
    [(kind, data)] = events
    assert kind == "state.proposal_rejected" and data["reason"] == "wrong_attribution"
    assert not tracker.graded


async def test_provider_failure_has_a_separate_event_from_an_edit_rejection(classroom, tracker):
    events = []
    classroom.log = lambda kind, data: events.append((kind, data))
    tracker.by_student["peer1"] = RuntimeError("private provider detail")
    assert await CslPipeline().update_states(classroom, commit(classroom, EVIDENCE)) == []
    [(kind, data)] = events
    assert kind == "state.proposal_failed"
    assert data["agentId"] == "peer1" and data["turnNumber"] == 1
    assert "private provider detail" not in json.dumps(data)


async def test_citation_and_rejection_logs_are_admin_only(classroom, tracker, settings):
    settings.admin_token = "test-admin"
    app = create_app(settings, CslPipeline())
    async with app.router.lifespan_context(app):
        runner = SessionRunner(classroom, CslPipeline(), app.state.store, settings)
        connection = Connection()
        runner.attach(connection)
        assert connection.queue.get_nowait()["type"] == "session.snapshot"
        first = commit(classroom, "The inscription on this card is barely legible.", speaker="peer1")
        latest = commit(classroom, "Perhaps this date means every card in the batch was revised.", speaker="peer1")
        tracker.by_student["peer1"] = proposal(
            evidence={"kind": "interpretation", "turn_number": first.turn_number, "quote": first.text,
                      "latest_quote": latest.text},
            explanation="The cards in the batch were all revised.",
        )
        await runner._apply_state_updates(latest)
        assert connection.queue.empty() and not tracker.graded
        fact = commit(classroom, EVIDENCE, speaker="tutor")
        paraphrase = "The ledger was written in 1902 but only cataloged in 1975."
        tracker.by_student["peer1"] = proposal(
            evidence={"kind": "tutor_fact", "quote": paraphrase}, explanation=REVISED_RULE,
        )
        await runner._apply_state_updates(fact)
        assert connection.queue.get_nowait()["type"] == "state.updated"
        assert connection.queue.empty()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            url = f"/api/admin/sessions/{classroom.id}/events"
            assert (await http.get(url)).status_code == 401
            response = await http.get(url, headers={"Authorization": "Bearer test-admin"})
            response.raise_for_status()
            [event] = [e for e in response.json() if e["type"] == "state.proposal_rejected"]
            assert event["data"]["reason"] == "no_independent_premise"
            assert event["data"]["citedTurnNumber"] == first.turn_number
            assert latest.text not in json.dumps(event)
            [citation] = [e["data"] for e in response.json() if e["type"] == "state.proposal_citation"]
            assert citation["citedTurnNumber"] == citation["turnNumber"] == fact.turn_number
            assert citation["mismatchedFields"] == ["evidence.quote"]
            assert all(text not in json.dumps(citation) for text in (fact.text, paraphrase, "PRIVATE-REFERENCE"))


async def test_counterexample_revises_one_legacy_belief_without_replacing_its_neighbors(classroom, tracker):
    message = commit(classroom, EVIDENCE)
    current = classroom.state_of("peer1")
    tracker.by_student["peer1"] = proposal(belief_edits=[
        {"op": "revise", "id": LEGACY_ID, "text": REVISED_RULE},
        {"op": "add", "text": "The archive recorded this item in 1975."},
    ])
    before = classroom.dump()
    [update] = await CslPipeline().update_states(classroom, message)
    assert classroom.dump() == before  # the runner owns version creation
    assert update.agent_id == "peer1"
    revised, untouched, added = update.state.beliefs
    assert revised == Belief(id=LEGACY_ID, text=REVISED_RULE, accuracy="partial")
    assert untouched == current.beliefs[1]
    used = {belief.id for version in classroom.state_history("peer1") for belief in version.state.beliefs}
    assert added.text == "The archive recorded this item in 1975." and added.id not in used
    assert update.state.explanation == current.explanation
    assert update.state.explanation_accuracy == current.explanation_accuracy
    assert update.state.open_questions == current.open_questions
    assert tracker.graded == [{
        "reference": "PRIVATE-REFERENCE",
        "beliefs": [{"id": LEGACY_ID, "text": REVISED_RULE}, {"id": added.id, "text": added.text}],
    }]
    # A retry on the same restored history assigns the same new ID.
    [retry] = await CslPipeline().update_states(Session.restore(before), message)
    assert retry.state == update.state


async def test_bare_disagreement_does_not_reuse_an_earlier_counterexample(classroom, tracker):
    commit(classroom, EVIDENCE, speaker="tutor")
    message = commit(classroom, "I disagree.")
    tracker.by_student["peer1"] = proposal(
        belief_edits=[{"op": "remove", "id": LEGACY_ID}],
    )
    before = classroom.dump()
    assert await CslPipeline().update_states(classroom, message) == []
    assert classroom.dump() == before
    assert tracker.calls.keys() == {"peer1", "peer2"}
    assert not tracker.graded
    for peer_id, request in tracker.calls.items():
        assert "PRIVATE-REFERENCE" not in json.dumps(request)
        assert "accuracy" not in json.dumps(request)
        transcript = [block["text"] for block in request[-1]["content"][:-1]]
        assert len(transcript) == 2 and transcript[-1].endswith(message.text)
        assert (LEGACY_ID in json.dumps(request)) == (peer_id == "peer1")
        assert ("KAI-PRIVATE-EXPLANATION" in json.dumps(request)) == (peer_id == "peer2")


@pytest.mark.parametrize("bad_reply", [
    RuntimeError("provider unavailable"),
    {"changed": True, "belief_edits": [{"op": "remove", "id": LEGACY_ID}]},
    proposal(belief_edits=[{"op": "remove", "id": "unknown"}]),
    proposal(evidence={"kind": "tutor_fact", "quote": EVIDENCE}, explanation="I now agree."),
    proposal(evidence={"kind": "disagreement", "quote": EVIDENCE}, explanation="I now agree."),
    proposal(explanation=REVISED_RULE, explanation_accuracy="correct"),
    proposal(belief_edits=[{"op": "add", "text": REVISED_RULE, "accuracy": "partial"}]),
    proposal(belief_edits=[{"op": "add", "id": LEGACY_ID, "text": REVISED_RULE}]),
    proposal(question_edits=[{"op": "resolve", "text": "Who prepared the ink?"}]),
    proposal(belief_edits=[{"op": "revise", "id": LEGACY_ID,
                            "text": "The date on a card always says when the object was made."}]),
])
async def test_invalid_failed_or_identical_updates_do_not_hide_other_peer_changes(classroom, tracker, bad_reply):
    tracker.by_student["peer1"] = bad_reply
    question = "Who chose the date shown on this card?"
    tracker.by_student["peer2"] = proposal(question_edits=[{"op": "add", "text": question}])
    [update] = await CslPipeline().update_states(classroom, commit(classroom, EVIDENCE))
    assert update.agent_id == "peer2"
    assert update.state.open_questions == [question]
    assert update.state.explanation == "KAI-PRIVATE-EXPLANATION"
    assert not tracker.graded


async def test_tutor_fact_resolves_only_the_named_gap_and_updates_invitation(classroom, tracker):
    current = classroom.states["peer1"][-1].state
    question = "What does the first column identify?"
    current.open_questions = [question, "  Who donated the ledger?  "]
    fact = "The first column records the date of cataloging."
    message = commit(classroom, fact, speaker="tutor", meta={"invite": True})
    tracker.by_student["peer1"] = proposal(
        evidence={"kind": "tutor_fact", "quote": fact},
        question_edits=[{"op": "resolve", "text": question}],
        explanation=fact,
    )
    [update] = await CslPipeline().update_states(classroom, message)
    assert update.state.explanation == fact and update.state.explanation_accuracy == "correct"
    assert update.state.open_questions == ["  Who donated the ledger?  "]
    assert update.state.beliefs == current.beliefs
    assert classroom.scratch["baseline"]["last_invite"] == message.turn_number


async def test_one_contradicted_belief_can_be_withdrawn_while_the_mechanism_stays_open(classroom, tracker):
    classroom.states["peer1"][-1].state.open_questions.append("Who assigned the catalog number?")
    current = classroom.state_of("peer1")
    question = "Where is the original creation date recorded?"
    tracker.by_student["peer1"] = proposal(
        belief_edits=[{"op": "remove", "id": LEGACY_ID}],
        explanation="I need to check what event a card's date describes.",
        question_edits=[{"op": "add", "text": question}],
    )
    [update] = await CslPipeline().update_states(classroom, commit(classroom, EVIDENCE, speaker="peer2"))
    assert update.state.beliefs == [current.beliefs[1]]
    assert update.state.open_questions == [*current.open_questions, question]
    assert update.state.explanation == "I need to check what event a card's date describes."


async def test_removal_only_preserves_the_remaining_label_and_skips_grading(classroom, tracker):
    classroom.states["peer1"][-1].state.beliefs[1].accuracy = "correct"
    current = classroom.state_of("peer1")
    tracker.by_student["peer1"] = proposal(belief_edits=[{"op": "remove", "id": LEGACY_ID}])
    [update] = await CslPipeline().update_states(classroom, commit(classroom, EVIDENCE))
    assert update.state.beliefs == current.beliefs[1:]
    assert not tracker.graded


@pytest.mark.parametrize("paraphrased", [False, True])
async def test_reasoned_interpretation_can_be_recorded_with_no_accuracy_label(classroom, tracker, paraphrased):
    premise = "Both cards have the same initial."
    earlier = commit(classroom, premise, speaker="tutor")
    reasoning = "The two cards use the same initial, so I would check whether they refer to one collection."
    interpretation = "I use repeated initials as a lead when comparing cards."
    source_excerpt = "The initials on the cards match." if paraphrased else premise
    events = []
    classroom.log = lambda kind, data: events.append((kind, data))
    tracker.by_student["peer1"] = proposal(
        evidence={"kind": "reasoning", "quote": reasoning,
                  "support": {"turn_number": earlier.turn_number, "quote": source_excerpt}},
        belief_edits=[{"op": "add", "text": interpretation}],
        explanation=interpretation,
    )
    async def indeterminate(payload):
        return {"beliefs": [{"id": b["id"], "accuracy": None} for b in payload["beliefs"]], "explanation_accuracy": None}

    tracker.grade = indeterminate
    current = classroom.state_of("peer1")
    [update] = await CslPipeline().update_states(classroom, commit(classroom, reasoning, speaker="peer1"))
    assert update.state.beliefs[:-1] == current.beliefs
    assert update.state.beliefs[-1].text == interpretation and update.state.beliefs[-1].accuracy is None
    [(kind, citation)] = events
    assert kind == "state.proposal_citation"
    assert citation["citedTurnNumber"] == citation["turnNumber"] == 2
    assert citation["supportTurnNumber"] == earlier.turn_number
    assert set(citation["mismatchedFields"]) == ({"evidence.support.quote"} if paraphrased else set())
    assert update.state.explanation == interpretation and update.state.explanation_accuracy is None


@pytest.mark.parametrize("invalid_grade", [
    {"beliefs": [{"id": LEGACY_ID, "accuracy": "correct", "explanation_accuracy": "partial"}]},
    {"beliefs": [{"id": LEGACY_ID, "accuracy": "correct", "text": "shelf B"}], "explanation_accuracy": "correct"},
    {"beliefs": [{"id": "other/key:42", "accuracy": "correct"}], "explanation_accuracy": "correct"},
    {"beliefs": [{"id": LEGACY_ID, "accuracy": "correct"}] * 2, "explanation_accuracy": "correct"},
    {"beliefs": [], "explanation_accuracy": "correct"},
    {"beliefs": [{"id": LEGACY_ID, "accuracy": "correct"}], "explanation_accuracy": "shelf B"},
    {"beliefs": [{"id": LEGACY_ID, "accuracy": "correct"}], "explanation": "shelf B"},
    RuntimeError("provider failure"),
])
async def test_unusable_grade_keeps_all_public_content_and_clears_stale_labels(classroom, tracker, invalid_grade):
    async def fail(payload):
        if isinstance(invalid_grade, Exception):
            raise invalid_grade
        return invalid_grade

    current = classroom.state_of("peer1")
    tracker.grade = fail
    tracker.by_student["peer1"] = proposal(
        belief_edits=[{"op": "revise", "id": LEGACY_ID, "text": REVISED_RULE}], explanation=REVISED_RULE,
    )
    [update] = await CslPipeline().update_states(classroom, commit(classroom, EVIDENCE))
    assert update.state.beliefs == [Belief(id=LEGACY_ID, text=REVISED_RULE), current.beliefs[1]]
    assert update.state.explanation == REVISED_RULE and update.state.explanation_accuracy is None
    assert "shelf B" not in update.state.model_dump_json()


async def test_missing_reference_leaves_new_content_ungraded(classroom, tracker):
    del classroom.scratch["baseline"]["tutor"]["reference"]
    tracker.by_student["peer1"] = proposal(belief_edits=[{"op": "add", "text": EVIDENCE}])
    [update] = await CslPipeline().update_states(classroom, commit(classroom, EVIDENCE))
    assert update.state.beliefs[-1].text == EVIDENCE and update.state.beliefs[-1].accuracy is None
    assert not tracker.graded


@pytest.mark.parametrize("paraphrased", [False, True])
async def test_exact_self_repetition_does_not_bootstrap_a_change(classroom, tracker, paraphrased):
    belief = classroom.state_of("peer1").beliefs[0].text
    excerpt = "The card always gives its creation date." if paraphrased else belief
    tracker.by_student["peer1"] = proposal(
        evidence={"kind": "reasoning", "quote": excerpt,
                  "support": {"turn_number": None, "quote": belief}},
        belief_edits=[{"op": "remove", "id": LEGACY_ID}],
        explanation="The card actually locates a shelf.",
    )
    assert await CslPipeline().update_states(classroom, commit(classroom, belief, speaker="peer1")) == []
    assert not tracker.graded


@pytest.mark.parametrize("support", [
    None,
    {"turn_number": 1, "quote": "I've wondered whether staff share a habit."},  # own earlier statement
    {"turn_number": 2, "quote": "Everyone here shares a habit."},  # actual message only disagreed
    {"turn_number": 8, "quote": "Everyone here shares a habit."},  # attributed turn does not exist
    {"turn_number": 3, "quote": "Maybe the staff share a habit."},  # this turn
    {"turn_number": None, "quote": QUESTION},  # a question in memory is not a factual premise
])
async def test_own_speculation_requires_independent_public_support(classroom, tracker, support):
    commit(classroom, "I've wondered whether staff share a habit.", speaker="peer1")
    commit(classroom, "I disagree.", speaker="tutor")
    observation = "Both cards are signed."
    guess = "Maybe the staff share a habit."
    message = commit(classroom, f"{observation} {guess}", speaker="peer1")
    evidence = {"kind": "interpretation", "quote": guess}
    if support is not None:
        evidence["support"] = support
    tracker.by_student["peer1"] = proposal(
        evidence=evidence, belief_edits=[{"op": "add", "text": "The staff all share the same habit."}],
    )
    question = "Who signed these two cards?"
    tracker.by_student["peer2"] = proposal(
        evidence={"kind": "observation", "quote": observation}, question_edits=[{"op": "add", "text": question}],
    )
    [update] = await CslPipeline().update_states(classroom, message)
    assert update.agent_id == "peer2" and update.state.open_questions == [question]
    assert not tracker.graded


async def test_student_can_infer_from_their_existing_reasoning(classroom, tracker):
    premise = "A title helps me find a related card."
    reasoning = "Since titles help me find related cards, I can try the same title in the next drawer."
    tracker.by_student["peer1"] = proposal(
        evidence={"kind": "reasoning", "quote": reasoning, "support": {"turn_number": None, "quote": premise}},
        explanation=reasoning,
    )
    [update] = await CslPipeline().update_states(classroom, commit(classroom, reasoning, speaker="peer1"))
    assert update.state.explanation == reasoning
    assert update.state.beliefs == classroom.state_of("peer1").beliefs


async def test_only_the_peer_who_voiced_uncertainty_can_record_their_actual_question(classroom, tracker):
    question = "Why do you think the card records a different date?"
    spoken = "I'm not sure. " + question
    tracker.by_student["peer2"] = tracker.by_student["peer1"] = proposal(
        evidence={"kind": "uncertainty", "quote": "I'm not sure."},
        question_edits=[{"op": "add", "text": question}],
    )
    current = classroom.state_of("peer1")
    message = commit(classroom, spoken, speaker="peer1")
    [update] = await CslPipeline().update_states(classroom, message)
    assert update.agent_id == "peer1" and update.state.open_questions == [*current.open_questions, question]
    assert update.state.beliefs == current.beliefs and update.state.explanation == current.explanation
    for additional in [
        {"explanation": "The date identifies shelf B."},
        {"belief_edits": [{"op": "remove", "id": LEGACY_ID}]},
        {"question_edits": [{"op": "add", "text": "Could it be shelf B?"}]},
        {"question_edits": [{"op": "resolve", "text": QUESTION}]},
    ]:
        tracker.by_student["peer1"] = proposal(
            evidence={"kind": "uncertainty", "quote": "I'm not sure."}, **additional,
        )
        assert await CslPipeline().update_states(classroom, message) == []
    assert not tracker.graded


async def test_reference_swap_never_changes_the_next_public_proposal_request(classroom, tracker):
    public_requests = []
    states = []
    for reference, grade in [("shelf B", "incorrect"), ("bin 4", "partial")]:
        session = Session.restore(classroom.dump())
        session.scratch["baseline"]["tutor"] = {"reference": reference, "key_points": ["secret point"]}
        tracker.by_student["peer1"] = proposal(explanation=REVISED_RULE)

        async def grade_explanation(payload):
            assert payload == {"beliefs": [], "reference": reference, "explanation": REVISED_RULE}
            return {"beliefs": [], "explanation_accuracy": grade}

        tracker.grade = grade_explanation
        [update] = await CslPipeline().update_states(session, commit(session, EVIDENCE))
        states.append(update.state)
        initial_request = tracker.calls["peer1"]
        session.states["peer1"].append(StateVersion(agent_id="peer1", version=2, state=update.state, created_at=3.0))
        tracker.by_student.clear()
        assert await CslPipeline().update_states(session, commit(session, "Are you sure?")) == []
        public_requests.append([initial_request, tracker.calls["peer1"]])
        assert all(secret not in json.dumps(public_requests[-1]) for secret in ("shelf B", "bin 4", "secret point"))
    assert public_requests[0] == public_requests[1]
    assert states[0].model_dump(exclude={"explanation_accuracy"}) == states[1].model_dump(exclude={"explanation_accuracy"})
    assert [state.explanation_accuracy for state in states] == ["incorrect", "partial"]


async def test_stalled_grader_preserves_public_changes_and_other_peers_grades(classroom, tracker, monkeypatch):
    monkeypatch.setattr(_state_updates.get_settings(), "turn_timeout_seconds", 0.12)
    blocked = asyncio.Event()
    cancelled = asyncio.Event()

    async def grade(payload):
        if payload["beliefs"][0]["id"] == LEGACY_ID:
            try:
                await blocked.wait()
            finally:
                cancelled.set()
        return await tracker.default_grade(payload)

    tracker.grade = grade
    tracker.by_student["peer1"] = proposal(belief_edits=[{"op": "revise", "id": LEGACY_ID, "text": REVISED_RULE}])
    tracker.by_student["peer2"] = proposal(belief_edits=[{"op": "add", "text": EVIDENCE}])
    first, second = await asyncio.wait_for(CslPipeline().update_states(classroom, commit(classroom, EVIDENCE)), 1)
    assert cancelled.is_set()
    assert first.state.beliefs[0] == Belief(id=LEGACY_ID, text=REVISED_RULE)
    assert second.state.beliefs[-1].accuracy == "correct"


async def test_stalled_proposer_does_not_lose_another_peers_update(classroom, tracker, monkeypatch):
    monkeypatch.setattr(_state_updates.get_settings(), "turn_timeout_seconds", 0.12)
    tracker.by_student["peer1"] = asyncio.Event().wait
    tracker.by_student["peer2"] = proposal(explanation=REVISED_RULE)
    [update] = await asyncio.wait_for(CslPipeline().update_states(classroom, commit(classroom, EVIDENCE)), 1)
    assert update.agent_id == "peer2" and update.state.explanation_accuracy == "correct"


async def test_external_cancellation_propagates_while_grading(classroom, tracker):
    started = asyncio.Event()

    async def wait(payload):
        started.set()
        await asyncio.Event().wait()

    tracker.grade = wait
    tracker.by_student["peer1"] = proposal(explanation=REVISED_RULE)
    task = asyncio.create_task(CslPipeline().update_states(classroom, commit(classroom, EVIDENCE)))
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
