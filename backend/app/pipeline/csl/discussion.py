"""Discussion dynamics: who speaks next (select_speaker) and what they say (speak).

Turn allocation follows the pilot's choice (researches/turn_allocation: centralized selection, S03): a
hidden moderator picks the next speaker from the public discussion. The pilot's weakness of S03 was that
questions went unanswered, so the moderator also names the open question the chosen speaker should take
up (`respond_to`) and says when it has done its job (`wrap_up`). It still only points; it never says
what anyone should believe or answer.

The tutor is not a speaker candidate, as in the pilot: the moderator picks among the students and,
separately, judges whether the tutor has a reason to step in (`tutor`: off_topic / stagnation /
missing_information, or none). A wrong answer, a productive disagreement or a question the students have
not had a chance to answer is not a reason. PEERS_BETWEEN_TUTOR is only a lower bound, not a trigger.

All of this is read fresh from the full transcript on every call, so nothing has to be stored between
turns: neither method may change anything (base.py), because the server may throw a prepared turn away.
Rule-based shortcuts handle the learner's messages and the closing, as before.

Before a peer speaks, a neutral reader identifies the situation in the public exchange. The
result and that peer's current understanding go in the private tail of the response request.
Every discussion request uses prompting.build_messages. The session block is shared across roles.
Within a role, the system blocks are stable and the rendered transcript grows by appending turns.
The full transcript is sent (no sliding window): at MAX_TURNS=60 it stays a few thousand tokens.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from ...llm import extract_json, get_llm
from ...protocol import KnowledgeState, Message
from ...session import Session
from ..base import SpeakerDecision, TextSink
from . import knowledge
from ._peer_speech import PeerSpeechSink
from .prompting import LANG, USER_LABEL, build_messages, session_block

log = logging.getLogger("csl.discussion")

# ---------------------------------------------------------------- role blocks (static per session)

MODERATOR_ROLE = """ROLE: hidden moderator. You only decide who speaks next; nobody sees your output.

Key points the discussion should eventually reach (do not reveal them): {key_points}

1. speaker: the student who speaks next (never the tutor, never the one who spoke last).
- Students carry the discussion: they question and build on each other. If the last message asked a specific student something, pick that student.
- Keep track of questions. A question is open until someone has actually answered it with a reason (agreeing, repeating it or saying "good question" is not an answer). Prefer the student an open question was addressed to, or one who can take up an open question nobody was asked by name.
- Prefer a student whose view has not been examined yet over one who just repeated themselves.

2. respond_to: the turn number of the open question that student should answer first, or null. Only a question addressed to that student or to everyone, not yet answered, and not already taken up by someone else.

3. tutor: whether the tutor, who is watching, should step in now instead. Usually "none": the tutor is a supporter, not a competitor for turns.
- "off_topic": the discussion has drifted away from the focus.
- "stagnation": for several turns the students have repeated the same point or question without new reasons.
- "missing_information": the students need a fact they cannot work out from what they know or what was said.
- Not a reason on its own: the last answer was wrong, the students disagree productively, or a question has not yet had a chance to be answered by the students. Let them work.
- The instruction below says whether the tutor may step in right now; if not, tutor must be "none".

4. invite_user: true only if the students have reached the edge of a key idea but cannot make the connection, so the tutor will ask the learner to explain it. The instruction below says whether an invitation is allowed right now.

5. wrap_up: true only if the students have between them reached the key points and the learner has had a chance to explain, so the tutor can close the discussion.

Output a single JSON object and nothing else:
{{"speaker": "<student id>", "respond_to": <turn number or null>, "tutor": "none"|"off_topic"|"stagnation"|"missing_information", "invite_user": true|false, "wrap_up": true|false}}"""

PEER_ROLE = """ROLE: one of the students. The instruction after the discussion says which student you are and gives that student's current understanding.

Use only your assigned understanding and the public discussion as factual premises. You can work out a prediction from them. An outside fact, date, or measurement you happen to know is unavailable to this student unless a premise supplies it.
You are a student discussing the case. People mentioned in the topic are people you are reasoning about. You took part in an event only if your assigned understanding or the public discussion explicitly says you did. When a belief has no stated source, give your own judgment in the first person singular: "I think that applies here." If challenged, "That was my assumption. What makes you doubt it?" You may be wrong without knowing it.
Treat a group's habits, a previous decision, and a firsthand observation as distinct factual claims. Only mention one when you can point to where that history was supplied, with the original speaker correctly attributed. Framing an invented account as an assumption still invents an account.
An active belief is still yours, even when someone challenges it. Reason from your current understanding. You can acknowledge an observation, explain what you would predict, or ask how the two fit together. Do not declare your belief wrong or adopt someone else's explanation unless your supplied understanding already reflects that specific revision.
If someone asked you something and it has not been answered yet, answer it first, or say why you cannot answer it yet.
If you are still stuck on a question that was already asked, say exactly what information is missing.

Write only your next message: 1-3 sentences, in the discussion language, conversational, no lists. Start directly with what you say: no name, no "[T..]" label, no "Name:" prefix (those labels only mark messages in the record above)."""

TUTOR_ROLE = """ROLE: the tutor.

Reference explanation (for your eyes only, never recite it):
{reference}
Key points: {key_points}

You listen while the students make progress. When you step in, address one specific error or contradiction with a single fact or a small thought experiment, then hand the question back to the students. Ask the learner something only when your instruction below says so. Never give the full explanation.

Write only your next message: 2-4 sentences, in the discussion language, no lists. Start directly with what you say: no name, no "[T..]" label, no "Name:" prefix."""

TUTOR_DIRECTIVES = {
    "open": "Open the discussion with one focused question about the focus.",
    "invite": "The students are close. Say in one sentence what they have worked out, then ask the learner to explain the missing connection to them. Add that a complete or correct answer is not expected.",
    "feedback": "The learner has just explained their understanding. Say specifically which part is right, and which connection is missing or wrong and why, without supplying the full answer. Then invite them to refine it or let the students pick it up.",
    "answer": "The learner has just said something. If it is a question, answer it briefly and accurately and hand back to the students. If they want to move on or change direction, steer the discussion that way.",
    "refocus": "The discussion has drifted from the focus. In one sentence connect what was just said back to the focus, then ask one concrete question that brings the students back to it, addressed to one student by name.",
    "inform": "The students need a fact they cannot work out themselves. Give exactly that one fact or clue, as briefly as possible and without explaining what follows from it, then ask one student by name what it changes in their thinking.",
    "unstick": "The discussion is going in circles. Name the point the students keep returning to in one short phrase, then move them forward with one new fact or a small thought experiment that bears on exactly that point, or turn them to a key point nobody has examined yet. End with a question to one student by name.",
    "close": "Close the discussion. In 2-3 sentences, say what the students worked out together, and leave the learner one open question worth thinking about on their own. Do not recite the full explanation. Thank everyone in a few words.",
}
PEER_DIRECTIVES = {
    "react": "The learner has just spoken: respond to them directly from your own understanding (restate what you took from it, or question an assumption or a missing step).",
}

INVITE_MIN_TURN = 6
INVITE_GAP = 8
# The moderator may ask to close only after this many discussion messages.
WRAP_UP_MIN_TURN = 16
# After the tutor speaks, at least this many student messages come before the tutor may step in again
# (the pilot's rule). A lower bound only: whether the tutor steps in is the moderator's judgment.
# The learner rules (feedback / answer) and closing are exempt.
PEERS_BETWEEN_TUTOR = 2
# The moderator's reasons for the tutor to step in, and the tutor's instruction for each.
INTERVENTIONS = {"off_topic": "refocus", "stagnation": "unstick", "missing_information": "inform"}


# ---------------------------------------------------------------- helpers

def tutor_notes(session: Session) -> dict[str, Any]:
    """The tutor's hidden notes written by build_classroom (knowledge side).

    Contract with knowledge.py: {"reference": str, "key_points": [str]} under scratch["baseline"]["tutor"]
    for now (the baseline's key). Change both sides together.
    """
    notes = (session.scratch.get("baseline") or {}).get("tutor")
    return notes if isinstance(notes, dict) else {}


def last_invite(session: Session) -> int:
    return int((session.scratch.get("baseline") or {}).get("last_invite") or 0)


def _key_points(session: Session) -> str:
    return json.dumps(tutor_notes(session).get("key_points") or [], ensure_ascii=False)


def _session_block(session: Session) -> str:
    return session_block(session.topic, session.focus, session.language, session.participants)


def _state_text(state: KnowledgeState) -> str:
    beliefs = "\n".join(f"- {b.text}" for b in state.beliefs) or "- (none)"
    return (
        f"Beliefs:\n{beliefs}\n"
        f"Current explanation: {state.explanation or '(none yet)'}\n"
        f"Questions you are stuck on: {'; '.join(state.open_questions) or '(none)'}"
    )


def rotate(session: Session, exclude: Optional[str]) -> str:
    """Fallback: the peer who has been silent the longest."""
    spoken = [m.speaker_id for m in session.transcript]
    peers = [p.id for p in session.peers if p.id != exclude] or [p.id for p in session.peers]
    return min(peers, key=lambda pid: max((i for i, s in enumerate(spoken) if s == pid), default=-1))


def _by_turn(session: Session, turn: Any) -> Optional[Message]:
    if isinstance(turn, bool) or not isinstance(turn, int):
        return None
    return next((m for m in session.transcript if m.turn_number == turn), None)


def _flag(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() == "true")


# ---------------------------------------------------------------- requests (pure: also used by tests)

def moderator_request(session: Session, can_invite: bool, tutor_allowed: bool = True) -> list[dict[str, Any]]:
    transcript = session.transcript
    counts = {p.id: sum(1 for m in transcript if m.speaker_id == p.id) for p in session.participants}
    tail = (
        f"Messages so far per participant: {json.dumps(counts, ensure_ascii=False)}\n"
        f"Last speaker (cannot be picked): {transcript[-1].speaker_id if transcript else 'none'}\n"
        f"Tutor may step in now: {'yes' if tutor_allowed else 'no, tutor must be none'}\n"
        f"Invitation allowed now: {'yes' if can_invite else 'no, invite_user must be false'}\n"
        f"Closing allowed now: {'yes' if len(transcript) >= WRAP_UP_MIN_TURN else 'no, wrap_up must be false'}\n"
        "Who speaks next? Output the JSON object only."
    )
    role = MODERATOR_ROLE.format(key_points=_key_points(session))
    return build_messages(_session_block(session), role, transcript, session.language, tail)


def _respond_to_text(session: Session, decision: SpeakerDecision) -> str:
    target = _by_turn(session, decision.meta.get("respondTo"))
    if target is None:
        return ""
    who = USER_LABEL.get(session.language, "Learner") if target.role == "user" else target.speaker_name
    return (
        f"Before anything else, take up the open question in [T{target.turn_number}] from {who}: answer it from "
        "your own understanding, or say honestly why you cannot answer it yet."
    )


def speak_request(
    session: Session, decision: SpeakerDecision, *, peer_context: str | None = None
) -> list[dict[str, Any]]:
    agent = session.participant(decision.agent_id or "")
    if agent is None:
        raise ValueError(f"unknown speaker {decision.agent_id!r}")
    lang = LANG[session.language]
    respond = _respond_to_text(session, decision)
    if agent.role == "tutor":
        notes = tutor_notes(session)
        role = TUTOR_ROLE.format(
            reference=notes.get("reference") or "(use your own knowledge of the topic)",
            key_points=_key_points(session),
        )
        lines = [TUTOR_DIRECTIVES.get(decision.directive or "", ""), respond]
        tail = "\n".join(x for x in lines if x) + f"\nWrite the tutor's next message, in {lang}."
        tail = tail.lstrip()
    else:
        role = PEER_ROLE
        if peer_context is None:
            peer_context = _state_text(session.state_of(agent.id) or KnowledgeState())
        lines = [
            f"You are {agent.name} ({agent.id}).",
            peer_context,
            PEER_DIRECTIVES.get(decision.directive or "", ""),
            respond,
            f"Write {agent.name}'s reply in {lang}. Give your judgment about this case in one short sentence. "
            "Add a reason from your supplied beliefs, an attributed piece of evidence, or a question if needed. "
            "If the reply mentions a past experience or habit, use a direct quotation of the source words "
            "that establish it. Otherwise leave the account of past behavior out.",
        ]
        tail = "\n".join(line for line in lines if line)
    return build_messages(_session_block(session), role, session.transcript, session.language, tail)


# ---------------------------------------------------------------- output clean-up

class _PrefixStripper:
    """Drops a leading "[T12] Name:" / "Name:" the model sometimes copies from the transcript format.

    Streams everything else unchanged: it holds back only the first few characters until it can tell.
    """

    def __init__(self, out: TextSink, names: list[str]):
        self.out = out
        self.names = sorted({n for n in names if n}, key=len, reverse=True)
        alternatives = "|".join(re.escape(n) for n in self.names)
        self.pattern = re.compile(rf"^\s*(?:\[T\d+\]\s*)?(?:{alternatives})\s*[:：]\s*") if alternatives else None
        self.limit = max((len(n) for n in names), default=0) + 12
        self.buffer = ""
        self.done = self.pattern is None
        self.skip_space = False

    async def write(self, chunk: str) -> None:
        if self.done:
            if self.skip_space:  # the label ended a chunk: drop the space that follows it
                chunk = chunk.lstrip()
                self.skip_space = not chunk
            if chunk:
                await self.out.write(chunk)
            return
        self.buffer += chunk
        match = self.pattern.match(self.buffer)  # type: ignore[union-attr]
        if match:
            rest = self.buffer[match.end():]
            self.done = True
            self.skip_space = not rest
            if rest:
                await self.out.write(rest)
            return
        if len(self.buffer) >= self.limit or not self._could_still_match():
            await self.flush()

    def _could_still_match(self) -> bool:
        """False as soon as the held-back text can no longer become "[Tn] Name:"."""
        head = re.sub(r"^\[T\d+\]\s*", "", self.buffer.lstrip())
        if re.fullmatch(r"\[T?\d*", head):
            return True  # still inside a "[T12]" label
        head = head.rstrip()
        # "Name" may still be arriving ("Mar"), or be complete and followed by spaces before the colon.
        return any(n.startswith(head) or head == n for n in self.names)

    async def flush(self) -> None:
        if not self.done:
            self.done = True
            if self.buffer:
                await self.out.write(self.buffer)


# ---------------------------------------------------------------- pipeline methods

async def select_speaker(session: Session) -> SpeakerDecision:
    transcript = session.transcript
    if not transcript:
        return SpeakerDecision(agent_id="tutor", directive="open")
    last = transcript[-1]
    if last.role == "tutor" and last.meta.get("closing"):
        # The tutor closed the discussion and the learner did not add anything: end it.
        return SpeakerDecision(end=True)
    if last.role == "user":
        # A peer reacts to the learner first, then the tutor responds.
        return SpeakerDecision(agent_id=rotate(session, None), directive="react")
    if len(transcript) >= 2 and transcript[-2].role == "user" and last.role == "peer":
        return SpeakerDecision(agent_id="tutor", directive="feedback" if transcript[-2].invited else "answer")

    turn = len(transcript)
    if turn >= session.turn_limit - 1:
        # One message left before the server stops the session: let the tutor close it properly.
        return SpeakerDecision(agent_id="tutor", directive="close", meta={"closing": True})

    tutor_allowed = _peers_since_tutor(transcript) >= PEERS_BETWEEN_TUTOR
    can_invite = tutor_allowed and turn >= INVITE_MIN_TURN and turn - last_invite(session) >= INVITE_GAP
    data: dict[str, Any] = {}
    try:
        # Plain completion + our own JSON parsing, so the request has the same shape as every other call
        # (a response_format field could change how the provider renders the prompt).
        text = await get_llm().complete(
            moderator_request(session, can_invite, tutor_allowed), fast=True, temperature=0.2, max_tokens=150
        )
        data = extract_json(text)
    except Exception as exc:  # the discussion must go on; rotate instead
        log.warning("moderator failed, rotating: %r", exc)

    if _flag(data.get("wrap_up")) and turn >= WRAP_UP_MIN_TURN and last.role != "tutor":
        return SpeakerDecision(agent_id="tutor", directive="close", meta={"closing": True})

    speaker = data.get("speaker")
    agent = session.participant(speaker or "")
    if agent is None or agent.role != "peer" or speaker == last.speaker_id:
        speaker = rotate(session, last.speaker_id)

    invite = _flag(data.get("invite_user")) and can_invite
    reason = data.get("tutor") if tutor_allowed else None
    directive: Optional[str] = None
    meta: dict[str, Any] = {}
    if invite:
        speaker, directive, meta = "tutor", "invite", {"invite": True}
    elif reason in INTERVENTIONS:
        speaker, directive = "tutor", INTERVENTIONS[reason]
        meta["intervention"] = reason  # visible in the event log: why the tutor stepped in

    target = _by_turn(session, data.get("respond_to"))
    if (
        target is not None
        and target.speaker_id != speaker
        and directive in (None, "invite")
        and not _already_taken_up(transcript, target.turn_number)
    ):
        meta["respondTo"] = target.turn_number
    return SpeakerDecision(agent_id=speaker, invite_user=invite, directive=directive, meta=meta)


def _peers_since_tutor(transcript: list[Message]) -> int:
    """Peer messages since the tutor last spoke (all of them if the tutor never did)."""
    count = 0
    for m in reversed(transcript):
        if m.role == "tutor":
            return count
        count += m.role == "peer"
    return count


def _already_taken_up(transcript: list[Message], turn: Optional[int]) -> bool:
    """True when a later message was already pointed at this question.

    Without this the moderator sends every student in turn to the same tutor question and they
    give near-identical answers (live session, 2026-11-18: T10-T12 all answered T9).
    """
    return any((m.meta or {}).get("respondTo") == turn for m in transcript)


async def speak(session: Session, decision: SpeakerDecision, out: TextSink) -> None:
    agent = session.participant(decision.agent_id or "")
    if agent is None:
        raise ValueError(f"unknown speaker {decision.agent_id!r}")
    peer_context = None
    if agent.role == "peer":
        peer_context = await knowledge.prepare_peer_context(
            session, agent.id, respond_to=decision.meta.get("respondTo")
        )
    request = speak_request(session, decision, peer_context=peer_context)
    peer_sink = PeerSpeechSink(session, agent.id, out) if agent.role == "peer" else None
    sink = _PrefixStripper(peer_sink or out, [agent.name, agent.id])
    async for chunk in get_llm().stream(request, temperature=0.8, max_tokens=400):
        await sink.write(chunk)
    await sink.flush()
    if peer_sink is not None:
        await peer_sink.flush()


__all__ = ["select_speaker", "speak", "moderator_request", "speak_request", "rotate", "USER_LABEL"]
