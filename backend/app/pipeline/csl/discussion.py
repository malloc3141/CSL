"""Discussion dynamics: who speaks next (select_speaker) and what they say (speak).

Turn allocation follows the pilot's choice (researches/turn_allocation: centralized selection, S03): a
hidden moderator picks the next speaker from the public discussion. The pilot's weakness of S03 was that
questions went unanswered, so the moderator also names the open question the chosen speaker should take
up (`respond_to`), says when the discussion is going in circles (`stalled`) and when it has done its job
(`wrap_up`). It still only points; it never says what anyone should believe or answer.

All of this is read fresh from the full transcript on every call, so nothing has to be stored between
turns: neither method may change anything (base.py), because the server may throw a prepared turn away.
Rule-based shortcuts handle the learner's messages and the closing, as before.

Every LLM call is assembled by prompting.build_messages so the session block, the role block and the
transcript prefix are byte-identical from one call to the next, and the prompt cache can serve them.
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
from .prompting import LANG, USER_LABEL, build_messages, session_block

log = logging.getLogger("csl.discussion")

# ---------------------------------------------------------------- role blocks (static per session)

MODERATOR_ROLE = """ROLE: hidden moderator. You only decide who speaks next; nobody sees your output.

Key points the discussion should eventually reach (do not reveal them): {key_points}

How to choose:
- Peers carry the discussion: they question and build on each other. If the last message asked a specific participant something, pick that participant.
- Keep track of questions. A question is open until someone has actually answered it with a reason (agreeing, repeating it or saying "good question" is not an answer). Prefer giving the turn to the participant an open question was addressed to, or to a student who can take up an open question nobody was asked by name.
- Prefer a student whose view has not been examined yet over one who just repeated themselves.
- Pick the tutor only when a question was left unanswered for several turns, the students are reinforcing a wrong idea together, two conflicting explanations are not being examined, or the discussion is going in circles.
- Never pick the participant who spoke last.
- invite_user may be true only together with the tutor: the students have reached the edge of a key idea but cannot make the connection, so the tutor will ask the learner to explain it. The instruction below says whether an invitation is allowed right now.

Also report:
- respond_to: the turn number of the open question the chosen speaker should answer first, or null. Only a question that was addressed to that speaker or to everyone, and that has not been answered yet.
- stalled: true if the last several messages mostly repeat the same point or the same question without new reasons.
- wrap_up: true only if the students have between them reached the key points and the learner has had a chance to explain, so the tutor can close the discussion.

Output a single JSON object and nothing else:
{{"speaker": "<participant id>", "respond_to": <turn number or null>, "stalled": true|false, "wrap_up": true|false, "invite_user": true|false}}"""

PEER_ROLE = """ROLE: one of the students. The instruction after the discussion says which student you are and gives that student's current understanding.

Stay strictly inside that understanding. Reason from it, defend it, or doubt it when someone gives you a concrete reason. Never state a fact or mechanism that is neither in your understanding nor already said in the discussion. You may be wrong without knowing it.
If someone asked you something and it has not been answered yet, answer it first, or say why you cannot answer it yet.
Do not repeat a question you or others already asked; if you are still stuck on it, say what exactly blocks you or try a guess.

Write only your next message: 1-3 sentences, in the discussion language, conversational, no lists. Start directly with what you say: no name, no "[T..]" label, no "Name:" prefix (those labels only mark messages in the record above)."""

TUTOR_ROLE = """ROLE: the tutor.

Reference explanation (for your eyes only, never recite it):
{reference}
Key points: {key_points}

You listen while the students make progress. When you step in, address one specific error or contradiction with a single fact or a small thought experiment, then hand the question back. Never give the full explanation.

Write only your next message: 2-4 sentences, in the discussion language, no lists. Start directly with what you say: no name, no "[T..]" label, no "Name:" prefix."""

TUTOR_DIRECTIVES = {
    "open": "Open the discussion with one focused question about the focus.",
    "invite": "The students are close. Say in one sentence what they have worked out, then ask the learner to explain the missing connection to them. Add that a complete or correct answer is not expected.",
    "feedback": "The learner has just explained their understanding. Say specifically which part is right, and which connection is missing or wrong and why, without supplying the full answer. Then invite them to refine it or let the students pick it up.",
    "answer": "The learner has just said something. If it is a question, answer it briefly and accurately and hand back to the students. If they want to move on or change direction, steer the discussion that way.",
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
# The tutor does not step in to unstick twice within this many messages.
UNSTICK_GAP = 4
# After the tutor speaks, this many peer messages come before the moderator may pick the tutor again
# (the pilot's rule; on the live server the tutor otherwise took every other turn). The learner rules
# (feedback / answer) and closing are exempt.
PEERS_BETWEEN_TUTOR = 2


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

def moderator_request(session: Session, can_invite: bool) -> list[dict[str, Any]]:
    transcript = session.transcript
    counts = {p.id: sum(1 for m in transcript if m.speaker_id == p.id) for p in session.participants}
    tail = (
        f"Messages so far per participant: {json.dumps(counts, ensure_ascii=False)}\n"
        f"Last speaker (cannot be picked): {transcript[-1].speaker_id if transcript else 'none'}\n"
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
    who = USER_LABEL.get(session.language, "You") if target.role == "user" else target.speaker_name
    return (
        f"Before anything else, take up the open question in [T{target.turn_number}] from {who}: answer it from "
        "your own understanding, or say honestly why you cannot answer it yet."
    )


def speak_request(session: Session, decision: SpeakerDecision) -> list[dict[str, Any]]:
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
        state = session.state_of(agent.id) or KnowledgeState()
        lines = [PEER_DIRECTIVES.get(decision.directive or "", ""), respond]
        extra = "\n".join(x for x in lines if x)
        tail = (
            f"You are {agent.name} ({agent.id}). This is everything you currently believe about the topic; "
            f"you know nothing beyond it and what was said above.\n{_state_text(state)}\n\n"
            f"{extra + chr(10) if extra else ''}"
            f"Write {agent.name}'s next message, in {lang}."
        )
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


def _strip_names(session: Session, agent_id: str) -> list[str]:
    agent = session.participant(agent_id)
    if agent is None:
        return []
    return [agent.name, agent.id]


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

    can_invite = turn >= INVITE_MIN_TURN and turn - last_invite(session) >= INVITE_GAP
    data: dict[str, Any] = {}
    try:
        # Plain completion + our own JSON parsing, so the request has the same shape as every other call
        # (a response_format field could change how the provider renders the prompt).
        text = await get_llm().complete(
            moderator_request(session, can_invite), fast=True, temperature=0.2, max_tokens=150
        )
        data = extract_json(text)
    except Exception as exc:  # the discussion must go on; rotate instead
        log.warning("moderator failed, rotating: %r", exc)

    if _flag(data.get("wrap_up")) and turn >= WRAP_UP_MIN_TURN and last.role != "tutor":
        return SpeakerDecision(agent_id="tutor", directive="close", meta={"closing": True})

    speaker = data.get("speaker")
    if session.participant(speaker or "") is None or speaker == last.speaker_id:
        speaker = rotate(session, last.speaker_id)
    if speaker == "tutor" and _peers_since_tutor(transcript) < PEERS_BETWEEN_TUTOR:
        speaker = rotate(session, last.speaker_id)  # give the students room first
    invite = _flag(data.get("invite_user")) and can_invite and speaker == "tutor"

    directive: Optional[str] = "invite" if invite else None
    tutor_recently = any(m.role == "tutor" for m in transcript[-UNSTICK_GAP:])
    if not invite and _flag(data.get("stalled")) and not tutor_recently:
        speaker, directive = "tutor", "unstick"

    meta: dict[str, Any] = {"invite": True} if invite else {}
    if directive == "unstick":
        meta["unstick"] = True  # visible in the event log and to the frontend
    target = _by_turn(session, data.get("respond_to"))
    if target is not None and target.speaker_id != speaker and directive != "unstick":
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


async def speak(session: Session, decision: SpeakerDecision, out: TextSink) -> None:
    sink = _PrefixStripper(out, _strip_names(session, decision.agent_id or ""))
    async for chunk in get_llm().stream(speak_request(session, decision), temperature=0.8, max_tokens=400):
        await sink.write(chunk)
    await sink.flush()


__all__ = ["select_speaker", "speak", "moderator_request", "speak_request", "rotate", "USER_LABEL"]
