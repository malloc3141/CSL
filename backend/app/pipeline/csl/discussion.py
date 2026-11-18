"""Discussion dynamics: who speaks next (select_speaker) and what they say (speak).

Turn allocation follows the pilot's choice (researches/turn_allocation: centralized selection, S03): a
hidden moderator picks the next speaker from the public discussion. Rule-based shortcuts handle the
learner's messages, as in the baseline.

Every LLM call is assembled by prompting.build_messages so the session block, the role block and the
transcript prefix are byte-identical from one call to the next, and the prompt cache can serve them.
The full transcript is sent (no sliding window): at MAX_TURNS=60 it stays a few thousand tokens.

Neither method may change anything (base.py): the server may throw a prepared turn away.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from ...llm import extract_json, get_llm
from ...protocol import KnowledgeState
from ...session import Session
from ..base import SpeakerDecision, TextSink
from .prompting import LANG, USER_LABEL, build_messages, session_block

log = logging.getLogger("csl.discussion")

# ---------------------------------------------------------------- role blocks (static per session)

MODERATOR_ROLE = """ROLE: hidden moderator. You only decide who speaks next; nobody sees your output.

Key points the discussion should eventually reach (do not reveal them): {key_points}

How to choose:
- Peers carry the discussion: they question and build on each other. If the last message asked a specific participant something, pick that participant.
- Prefer a student whose view has not been examined yet, or one who was asked something earlier that is still unanswered.
- Pick the tutor only when a question was left unanswered, the students are reinforcing a wrong idea together, two conflicting explanations are not being examined, or the discussion is going in circles.
- Never pick the participant who spoke last.
- invite_user may be true only together with the tutor: the students have reached the edge of a key idea but cannot make the connection, so the tutor will ask the learner to explain it. The instruction below says whether an invitation is allowed right now.

Output a single JSON object and nothing else: {{"speaker": "<participant id>", "invite_user": true|false}}"""

PEER_ROLE = """ROLE: one of the students. The instruction after the discussion says which student you are and gives that student's current understanding.

Stay strictly inside that understanding. Reason from it, defend it, or doubt it when someone gives you a concrete reason. Never state a fact or mechanism that is neither in your understanding nor already said in the discussion. You may be wrong without knowing it.
If someone asked you something and it has not been answered yet, answer it first, or say why you cannot answer it yet.

Write only your next message: 1-3 sentences, in the discussion language, conversational, no name prefix, no turn label, no lists. React to what was just said: ask, challenge, concede one specific point, or try out an idea."""

TUTOR_ROLE = """ROLE: the tutor.

Reference explanation (for your eyes only, never recite it):
{reference}
Key points: {key_points}

You listen while the students make progress. When you step in, address one specific error or contradiction with a single fact or a small thought experiment, then hand the question back. Never give the full explanation.

Write only your next message: 2-4 sentences, in the discussion language, no name prefix, no turn label, no lists."""

TUTOR_DIRECTIVES = {
    "open": "Open the discussion with one focused question about the focus.",
    "invite": "The students are close. Say in one sentence what they have worked out, then ask the learner to explain the missing connection to them. Add that a complete or correct answer is not expected.",
    "feedback": "The learner has just explained their understanding. Say specifically which part is right, and which connection is missing or wrong and why, without supplying the full answer. Then invite them to refine it or let the students pick it up.",
    "answer": "The learner has just said something. If it is a question, answer it briefly and accurately and hand back to the students. If they want to move on or change direction, steer the discussion that way.",
}
PEER_DIRECTIVES = {
    "react": "The learner has just spoken: respond to them directly from your own understanding (restate what you took from it, or question an assumption or a missing step).",
}

INVITE_MIN_TURN = 6
INVITE_GAP = 8


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


# ---------------------------------------------------------------- requests (pure: also used by tests)

def moderator_request(session: Session, can_invite: bool) -> list[dict[str, Any]]:
    transcript = session.transcript
    counts = {p.id: sum(1 for m in transcript if m.speaker_id == p.id) for p in session.participants}
    tail = (
        f"Messages so far per participant: {json.dumps(counts, ensure_ascii=False)}\n"
        f"Last speaker (cannot be picked): {transcript[-1].speaker_id if transcript else 'none'}\n"
        f"Invitation allowed now: {'yes' if can_invite else 'no, invite_user must be false'}\n"
        "Who speaks next? Output the JSON object only."
    )
    role = MODERATOR_ROLE.format(key_points=_key_points(session))
    return build_messages(_session_block(session), role, transcript, session.language, tail)


def speak_request(session: Session, decision: SpeakerDecision) -> list[dict[str, Any]]:
    agent = session.participant(decision.agent_id or "")
    if agent is None:
        raise ValueError(f"unknown speaker {decision.agent_id!r}")
    lang = LANG[session.language]
    if agent.role == "tutor":
        notes = tutor_notes(session)
        role = TUTOR_ROLE.format(
            reference=notes.get("reference") or "(use your own knowledge of the topic)",
            key_points=_key_points(session),
        )
        directive = TUTOR_DIRECTIVES.get(decision.directive or "", "")
        tail = f"{directive}\nWrite the tutor's next message, in {lang}.".lstrip()
    else:
        role = PEER_ROLE
        state = session.state_of(agent.id) or KnowledgeState()
        directive = PEER_DIRECTIVES.get(decision.directive or "", "")
        tail = (
            f"You are {agent.name} ({agent.id}). This is everything you currently believe about the topic; "
            f"you know nothing beyond it and what was said above.\n{_state_text(state)}\n\n"
            f"{directive + chr(10) if directive else ''}"
            f"Write {agent.name}'s next message, in {lang}."
        )
    return build_messages(_session_block(session), role, session.transcript, session.language, tail)


# ---------------------------------------------------------------- pipeline methods

async def select_speaker(session: Session) -> SpeakerDecision:
    transcript = session.transcript
    if not transcript:
        return SpeakerDecision(agent_id="tutor", directive="open")
    last = transcript[-1]
    if last.role == "user":
        # A peer reacts to the learner first, then the tutor responds.
        return SpeakerDecision(agent_id=rotate(session, None), directive="react")
    if len(transcript) >= 2 and transcript[-2].role == "user" and last.role == "peer":
        return SpeakerDecision(agent_id="tutor", directive="feedback" if transcript[-2].invited else "answer")

    turn = len(transcript)
    can_invite = turn >= INVITE_MIN_TURN and turn - last_invite(session) >= INVITE_GAP
    speaker: Optional[str] = None
    invite = False
    try:
        # Plain completion + our own JSON parsing, so the request has the same shape as every other call
        # (a response_format field could change how the provider renders the prompt).
        text = await get_llm().complete(
            moderator_request(session, can_invite), fast=True, temperature=0.2, max_tokens=100
        )
        data = extract_json(text)
        speaker = data.get("speaker")
        invite = bool(data.get("invite_user"))
    except Exception as exc:  # the discussion must go on; rotate instead
        log.warning("moderator failed, rotating: %r", exc)
    if session.participant(speaker or "") is None or speaker == last.speaker_id:
        speaker = rotate(session, last.speaker_id)
    invite = invite and can_invite and speaker == "tutor"
    return SpeakerDecision(
        agent_id=speaker,
        invite_user=invite,
        directive="invite" if invite else None,
        meta={"invite": True} if invite else {},
    )


async def speak(session: Session, decision: SpeakerDecision, out: TextSink) -> None:
    async for chunk in get_llm().stream(speak_request(session, decision), temperature=0.8, max_tokens=400):
        await out.write(chunk)


__all__ = ["select_speaker", "speak", "moderator_request", "speak_request", "rotate", "USER_LABEL"]
