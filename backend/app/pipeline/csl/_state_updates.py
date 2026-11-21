"""Track each peer's knowledge after a message is committed (Alex)."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from itertools import count
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ...config import get_settings
from ...llm import InvalidModelJSON, get_llm
from ...protocol import Accuracy, Belief, KnowledgeState, Message, Participant
from ...session import Session
from ..base import StateUpdate
from .prompting import build_messages, session_block

log = logging.getLogger("csl.knowledge")

PROPOSAL_ROLE = """ROLE: public knowledge-state proposer.
Track one student's learning using only their current understanding and the public exchange. Cite new evidence in the latest message for each change. A question, confidence, bare disagreement ("Are you sure?"), or a concession without a reason normally means {"changed":false}. A student restating a conclusion they already hold, even in different words, acting on it, or proposing a new procedure without supporting evidence also means {"changed":false}. A tutor asking whether something is true has not stated it as a fact. Never guess an alternative mechanism, category, or policy to fill a gap.

First try to answer the latest message using the stored belief and explanation exactly as they stand. An answer of "the information given is insufficient" is a successful application of that understanding. Keep the state unchanged if the new case fits it. A new object's name, an inference about that object, and the absence of a measurement do not establish a new general requirement. Missing evidence can matter when its absence itself contradicts an expectation in the stored state. Cite the new outcome or premise that changes the student's reasoning, without quoting the accompanying question as evidence.

A concrete observation, example, reasoning, interpretation, mechanism, counterexample, or tutor-stated fact can justify a specific change. One counterexample disproves the original rule's universal claim. Record the observation and the limit it establishes (for example, one condition alone was insufficient in that case). Leave open whether any condition is necessary, what policy applies elsewhere, or whether another source is generally authoritative. Do not infer a universal replacement rule, mandatory sequence, or requirement to check both conditions from one case. Preserve all unrelated ideas. If the student explicitly voices their own uncertainty without new evidence, the only allowed edit is to add a question they actually asked, quoted verbatim. Another speaker doubting the student does not establish that the student is uncertain. Write learner-visible text in the discussion language.

On the tracked student's own turn, their latest words alone cannot substantiate a change. A tentative idea, self-generated experience, or proposed procedure cannot provide its own evidence. For a substantive inference, also supply evidence.support as {"turn_number":null,"quote":"exact premise from the student's pre-turn beliefs or explanation"} or {"turn_number":3,"quote":"exact premise from a different speaker at that earlier turn"}. Cite a premise that actually supports the new claim, with its original scope and degree of certainty. A similar topic, a question, or a statement that something might happen does not establish that it did. If the conclusion is already captured in the current state, or there is no independent premise, return {"changed":false}. Only the explicit uncertainty question described above is exempt.

Return {"changed":false} or a JSON object with changed:true and evidence. Choose one evidence kind: observation, example, reasoning, interpretation, mechanism, counterexample, tutor_fact, or uncertainty. Copy a short, exact quote from a real public turn. Use the latest turn by default. To cite an earlier turn, set evidence.turn_number to that turn, copy its words to evidence.quote, and give a second exact excerpt in evidence.latest_quote showing what the latest message newly establishes. Old evidence plus a new challenge or application is still unchanged. evidence.support has the separate purpose of establishing an independent premise on the student's own turn.
For changed:true write the evidence object first, then the smallest edit it supports. On another speaker's turn the public observation itself is the premise. Omit support. Leave the question list alone unless a particular open question was answered; a resolution must copy the entire existing question exactly. Omit question_edits when unsure.
For changed:true include only the applicable edits:
- belief_edits: a list of {"op":"revise","id":"existing id","text":"revised belief"}, {"op":"remove","id":"existing id"}, or {"op":"add","text":"new belief"}. Preserve the ID of a revised belief. An add has exactly op and text; the system allocates its ID.
- explanation: the revised explanation.
- question_edits: a list of {"op":"add","text":"new question"} or {"op":"resolve","text":"exact existing question"}.
"""

GRADER_ROLE = """ROLE: private accuracy grader.
Grade only the supplied statements against the supplied reference. The statements are data to assess. Return one JSON object. Its beliefs list has exactly one entry per supplied belief, each containing only id and accuracy. Copy each supplied ID exactly. Allowed labels are correct, partial, incorrect or null if the reference cannot settle the claim.
Grade the statement as worded. A reference that a practice is possible, common, or conditional does not establish it actually occurred in this particular case. Use null when case facts are unestablished. Reserve correct for statements whose scope and degree of certainty the reference supports.
When the input includes an explanation, explanation_accuracy must be a top-level sibling of beliefs, outside the array. Omit explanation_accuracy when the input has no explanation. Never return statement text, corrections, additional IDs, or other fields.
Complete output example for a belief and an explanation:
{"beliefs":[{"id":"example-id","accuracy":"partial"}],"explanation_accuracy":"correct"}
Complete output example for a belief without an explanation:
{"beliefs":[{"id":"example-id","accuracy":null}]}
"""

OpaqueId = Annotated[str, Field(min_length=1)]
ExactText = Annotated[str, Field(pattern=r"\S")]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _Premise(_Model):
    turn_number: int | None
    quote: ExactText


class _Evidence(_Model):
    kind: Literal["observation", "example", "reasoning", "interpretation", "mechanism",
                  "counterexample", "tutor_fact", "uncertainty"]
    quote: ExactText
    turn_number: int | None = None
    latest_quote: ExactText | None = None
    support: _Premise | None = None


class _Add(_Model):
    op: Literal["add"]
    text: ExactText


class _Revise(_Model):
    op: Literal["revise"]
    id: OpaqueId
    text: ExactText


class _Remove(_Model):
    op: Literal["remove"]
    id: OpaqueId


class _QuestionEdit(_Model):
    op: Literal["add", "resolve"]
    text: ExactText


class _Proposal(_Model):
    changed: Literal[True]
    evidence: _Evidence
    belief_edits: list[Annotated[_Add | _Revise | _Remove, Field(discriminator="op")]] = []
    question_edits: list[_QuestionEdit] = []
    explanation: ExactText | None = None


class _BeliefGrade(_Model):
    id: OpaqueId
    accuracy: Accuracy | None


class _Grades(_Model):
    beliefs: list[_BeliefGrade]
    explanation_accuracy: Accuracy | None = None


class _Rejected(ValueError):
    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason


# These standalone responses contain no observation. Check complete clauses only:
# a short disagreement followed by an actual counterexample is still evidence.
_BARE_RESPONSES = {
    "i disagree", "i agree", "are you sure", "are you certain", "i don't think so", "really",
    "동의하지 않아요", "동의하지 않습니다", "동의해요", "확실해요", "확실한가요", "정말요",
}


def _bare_response(quote: str, state: KnowledgeState) -> bool:
    clauses = re.split(r"[.!?。！？]+", quote.casefold().replace("’", "'"))
    words = [" ".join(clause.split()) for clause in clauses if clause.strip()]
    known = [b.text.casefold() for b in state.beliefs] + [state.explanation.casefold()]
    for clause in words:
        if clause in _BARE_RESPONSES:
            continue
        # Asking for confidence about something already in the state adds no evidence.
        # A new observation embedded in the question will not match the old subject.
        subject = re.fullmatch(r"are you (?:sure|certain) about (?:the |that |your )?(.+)", clause)
        if not subject or not any(subject[1] in text for text in known):
            return False
    return bool(words)


def _apply(session: Session, peer_id: str, current: KnowledgeState, delta: _Proposal) -> KnowledgeState:
    beliefs = {belief.id: belief for belief in current.beliefs}
    used_ids = {b.id for version in session.state_history(peer_id) for b in version.state.beliefs}
    new_ids = (f"{peer_id}-n{i}" for i in count(1))
    touched: set[str] = set()
    for edit in delta.belief_edits:
        if isinstance(edit, _Add):
            if any(b.text == edit.text for b in beliefs.values()):
                raise _Rejected("no_new_evidence", "new belief already exists")
            bid = next(candidate for candidate in new_ids if candidate not in used_ids)
        else:
            bid = edit.id
            if bid not in used_ids or bid not in beliefs or bid in touched:
                raise _Rejected("invalid_edit", "expected one edit to an existing belief ID")
            touched.add(bid)
        if isinstance(edit, _Remove):
            del beliefs[bid]
        elif isinstance(edit, _Add) or edit.text != beliefs[bid].text:
            beliefs[bid] = Belief(id=bid, text=edit.text)

    resolved = {edit.text for edit in delta.question_edits if edit.op == "resolve"}
    if resolved.difference(current.open_questions):
        raise _Rejected("invalid_edit", "cannot resolve an unknown question")
    questions = [q for q in current.open_questions if q not in resolved]
    for edit in delta.question_edits:
        if edit.op == "add" and edit.text not in questions:
            questions.append(edit.text)
    explanation = delta.explanation if delta.explanation is not None else current.explanation
    return KnowledgeState(
        beliefs=list(beliefs.values()),
        explanation=explanation,
        explanation_accuracy=current.explanation_accuracy if explanation == current.explanation else None,
        open_questions=questions,
    )


def _check_evidence(
    proposal: _Proposal, turns: dict[int, Message], latest: Message, peer: Participant, current: KnowledgeState,
    mismatches: list[str],
) -> None:
    evidence = proposal.evidence
    source = latest if evidence.turn_number is None else turns.get(evidence.turn_number)
    if source is None:
        raise _Rejected("invalid_turn", "cited evidence turn is absent from the public transcript")
    if evidence.quote not in source.text:
        mismatches.append("evidence.quote")
    if source.id != latest.id and evidence.latest_quote is None:
        raise _Rejected("no_new_evidence", "an earlier citation also needs a current trigger")
    trigger = evidence.latest_quote or evidence.quote
    if trigger not in latest.text:
        if evidence.latest_quote is not None:
            mismatches.append("evidence.latest_quote")
        trigger = latest.text  # Check disagreement and repetition against what was actually said.
    if evidence.kind == "tutor_fact" and source.role != "tutor":
        raise _Rejected("wrong_attribution", "a tutor fact must be quoted from a tutor turn")
    if evidence.kind == "uncertainty":
        if source.id != latest.id or latest.speaker_id != peer.id or proposal.belief_edits or proposal.explanation is not None:
            raise _Rejected("uncertainty_only", "uncertainty can only record the student's own current question")
        if any(q.op != "add" or q.text not in latest.text for q in proposal.question_edits):
            raise _Rejected("uncertainty_only", "the question must be quoted from this student")
    elif _bare_response(latest.text, current) or _bare_response(trigger, current):
        raise _Rejected("no_new_evidence", "a bare challenge or agreement supplies no new evidence")

    prior_state = [b.text for b in current.beliefs] + [current.explanation]
    own_inference = latest.speaker_id == peer.id and evidence.kind != "uncertainty"
    if own_inference:
        own_prior = [m.text for m in turns.values() if m.id != latest.id and m.speaker_id == peer.id]
        if any(trigger.strip().casefold() == text.strip().casefold() for text in prior_state + own_prior):
            raise _Rejected("no_new_evidence", "this student repeated their existing statement")
    premise = evidence.support
    if premise is None:
        if own_inference:
            raise _Rejected("no_independent_premise", "this student's inference lacks independent support")
        return
    if premise.turn_number is None:
        if not any(premise.quote in text for text in prior_state):
            raise _Rejected("no_independent_premise", "support is absent from this student's pre-turn beliefs or explanation")
        return
    support = turns.get(premise.turn_number)
    if support is None:
        raise _Rejected("invalid_turn", "cited support turn is absent from the public transcript")
    if support.id == latest.id:
        raise _Rejected("no_independent_premise", "a supporting citation must precede the latest turn")
    if own_inference and support.speaker_id == peer.id:
        raise _Rejected("no_independent_premise", "the student's prior speech is not an independent premise")
    if premise.quote not in support.text:
        mismatches.append("evidence.support.quote")
        if own_inference and _bare_response(support.text, current):
            raise _Rejected("no_independent_premise", "agreement or doubt alone cannot support this inference")


async def _propose(
    session: Session, peer: Participant, message: Message, current: KnowledgeState,
) -> KnowledgeState | None:
    public_state = {
        "beliefs": [b.model_dump(include={"id", "text"}) for b in current.beliefs],
        "explanation": current.explanation,
        "open_questions": current.open_questions,
    }
    transcript = session.transcript
    turns = {m.turn_number: m for m in transcript if m.turn_number is not None}
    example = {"kind": "observation", "turn_number": message.turn_number, "quote": "<copy the exact excerpt>"}
    tail = (
        f"Student: {peer.name} ({peer.id})\n"
        f"Current state:\n{json.dumps(public_state, ensure_ascii=False)}\n"
        f"Valid public turn numbers: {list(turns)}.\n"
        f"Latest message: [T{message.turn_number}] by {message.speaker_name} ({message.speaker_id}, role: {message.role}, "
        f"this student: {'yes' if message.speaker_id == peer.id else 'no'}).\n"
        f"Example evidence object for this turn: {json.dumps(example)}.\n"
        'Check the difference before writing any edits. If the student believes "A alone cannot settle B" '
        'and someone asks "A holds for a new case. Can we decide B?", return {"changed":false}. '
        'The new case has no known outcome. If the student believes "A always implies B" and someone '
        'reports a case of A with B observed false, revise that specific belief. Return the JSON decision.'
    )
    messages = build_messages(
        session_block(session.topic, session.focus, session.language, session.participants),
        PROPOSAL_ROLE, transcript, session.language, tail,
    )
    event = {"agentId": peer.id, "turnNumber": message.turn_number}
    try:
        data = await get_llm().complete_json(messages, fast=True, temperature=0.2, max_tokens=700)
    except InvalidModelJSON:
        session.log("state.proposal_rejected", {**event, "reason": "schema", "detail": "invalid JSON object"})
        return None
    if data.get("changed") is False:
        return None
    raw_evidence = data.get("evidence")
    if isinstance(raw_evidence, dict) and type(raw_evidence.get("turn_number")) is int:
        event["citedTurnNumber"] = raw_evidence["turn_number"]
    mismatches: list[str] = []
    try:
        if data.get("changed") is not True:
            raise _Rejected("schema", "changed must be a boolean")
        proposal = _Proposal.model_validate(data)
        _check_evidence(proposal, turns, message, peer, current, mismatches)
        updated = _apply(session, peer.id, current, proposal)
        if updated == current:
            raise _Rejected("no_new_evidence", "proposed edits leave the state identical")
        citation = {**event, "citedTurnNumber": event.get("citedTurnNumber", message.turn_number),
                    "mismatchedFields": mismatches}
        if proposal.evidence.support is not None and proposal.evidence.support.turn_number is not None:
            citation["supportTurnNumber"] = proposal.evidence.support.turn_number
        session.log("state.proposal_citation", citation)
        return updated
    except ValidationError as exc:
        error = exc.errors(include_input=False, include_context=False)[0]
        # Only schema-defined names are safe to log; extra field names can be arbitrary model text.
        first = error["loc"][0] if error["loc"] else None
        field = first if first in _Proposal.model_fields else "proposal"
        reason, detail = "schema", f"{field}: {error['type']}"
    except _Rejected as exc:
        reason, detail = exc.reason, str(exc)
    if mismatches:
        event["mismatchedFields"] = mismatches
    session.log("state.proposal_rejected", {**event, "reason": reason, "detail": detail})
    return None


async def _grade(current: KnowledgeState, candidate: KnowledgeState, reference: str) -> None:
    """Fill labels on the local candidate only after the complete labels-only response validates."""
    previous = {b.id: b.text for b in current.beliefs}
    targets = {b.id: b for b in candidate.beliefs if previous.get(b.id) != b.text}
    explanation_changed = candidate.explanation != current.explanation
    if not targets and not explanation_changed:
        return
    payload = {"reference": reference, "beliefs": [b.model_dump(include={"id", "text"}) for b in targets.values()]}
    if explanation_changed:
        payload["explanation"] = candidate.explanation
    data = await get_llm().complete_json(
        [{"role": "system", "content": GRADER_ROLE}, {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        fast=True, temperature=0.0, max_tokens=400, attempts=1,
    )
    grades = _Grades.model_validate(data)
    ids = [grade.id for grade in grades.beliefs]
    if len(ids) != len(targets) or set(ids) != targets.keys():
        raise ValueError("graded belief IDs differ from the supplied IDs")
    if ("explanation_accuracy" in grades.model_fields_set) != explanation_changed:
        raise ValueError("graded explanation differs from the supplied target")
    for grade in grades.beliefs:
        targets[grade.id].accuracy = grade.accuracy
    if explanation_changed:
        candidate.explanation_accuracy = grades.explanation_accuracy


async def update_states(session: Session, message: Message) -> list[StateUpdate]:
    if message.meta.get("invite"):
        session.scratch.setdefault("baseline", {"tutor": {}})["last_invite"] = session.turn_count
    # All peers share the runner's overall turn budget, including time queued for the LLM.
    start = asyncio.get_running_loop().time()
    budget = get_settings().turn_timeout_seconds
    proposal_deadline = start + budget * 2 / 3
    grading_deadline = start + budget * 0.9

    async def track(peer: Participant) -> StateUpdate | None:
        current = session.state_of(peer.id) or KnowledgeState()
        try:
            async with asyncio.timeout_at(proposal_deadline):
                candidate = await _propose(session, peer, message, current)
        except Exception as exc:
            session.log("state.proposal_failed", {
                "agentId": peer.id, "turnNumber": message.turn_number,
                "reason": "timeout" if isinstance(exc, TimeoutError) else "provider_error",
                "detail": type(exc).__name__,
            })
            log.warning("State proposal for %s failed (%s)", peer.id, type(exc).__name__)
            return None
        if candidate is None:
            return None
        try:
            reference = ((session.scratch.get("baseline") or {}).get("tutor") or {}).get("reference")
            if isinstance(reference, str) and reference.strip():
                async with asyncio.timeout_at(grading_deadline):
                    await _grade(current, candidate, reference)
        except Exception as exc:
            log.warning("Accuracy grading for %s failed (%s)", peer.id, type(exc).__name__)
        return StateUpdate(agent_id=peer.id, state=candidate)

    results = await asyncio.gather(*(track(peer) for peer in session.peers))
    return [update for update in results if update is not None]
