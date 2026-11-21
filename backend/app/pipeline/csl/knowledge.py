"""Setup, peer knowledge, and the State-first context used to prepare a peer reply."""
from __future__ import annotations

import asyncio
import logging

from ...config import get_settings
from ...llm import get_llm
from ...protocol import KnowledgeState
from ...session import Session
from ..base import Classroom, InitResult, TextSink
from ..baseline import BaselinePipeline
from ._state_updates import update_states
from .prompting import build_messages, session_block

__all__ = ["init_turn", "build_classroom", "prepare_peer_context", "update_states"]

log = logging.getLogger(__name__)
_setup = BaselinePipeline()
EXTRACTION_TIMEOUT_SECONDS = 8.0

CLASSROOM_PEER_RULES = """- Give each peer one coherent mental model. Accurate and mistaken beliefs can coexist when they fit together. For the same circumstances, every belief, the card description, and the explanation must agree on what happens and why.
- Write the explanation in the peer's own voice, showing how they think it works. Leave out any built-in rebuttal, counterexample, or hint at the correct answer that the peer would not infer from their own beliefs.
- Leave open_questions empty unless the peer has a genuinely neutral question. Asking it should make sense to someone who holds these beliefs."""

EXTRACTOR_ROLE = """ROLE: neutral situation reader.
Identify what the exchange asks a participant to address, in one or two sentences in the discussion
language. Use only the public topic and discussion. Preserve attribution, conditions, and uncertainty.
When someone asks whether a claim is true, say that the speaker asks whether it is true, and stop
there. Attribute guesses and beliefs to the person expressing them. Never turn the premise of a
question or an unverified claim into a fact. Do not answer, assess correctness, or add background."""


async def init_turn(session: Session, out: TextSink) -> InitResult:
    return await _setup.init_turn(session, out)


async def build_classroom(session: Session) -> Classroom:
    return await _setup.build_classroom(
        session,
        explanation="how this student currently thinks it works, in their own words, in 1-3 sentences",
        peer_rules=CLASSROOM_PEER_RULES,
    )


async def prepare_peer_context(session: Session, peer_id: str, *, respond_to: int | None = None) -> str:
    """Return the private, uncached section for the selected peer's response prompt.

    Call from async peer speech before building the streaming request. The extractor sees only
    public information. Neither the extracted situation nor the returned section is persisted.
    """
    peer = session.participant(peer_id)
    if peer is None or peer.role != "peer":
        raise ValueError(f"unknown peer {peer_id!r}")

    transcript = session.transcript
    target = transcript[-1] if transcript else None
    if type(respond_to) is int:
        target = next((m for m in transcript if m.turn_number == respond_to), target)
    focus = "the latest exchange" if transcript else "the opening topic and focus"
    if target and target.turn_number is not None:
        focus = f"[T{target.turn_number}]"
    request = build_messages(
        session_block(session.topic, session.focus, session.language, session.participants),
        EXTRACTOR_ROLE, transcript, session.language, f"Describe what is at issue in {focus}, in context.",
    )
    situation = ""
    try:
        budget = min(EXTRACTION_TIMEOUT_SECONDS, get_settings().turn_timeout_seconds / 4)
        async with asyncio.timeout(budget):
            situation = (await get_llm().complete(request, fast=True, temperature=0.0, max_tokens=120)).strip()
        if not situation:
            log.warning("Empty situation extraction for session %s", session.id)
    except Exception as exc:
        log.warning("Situation extraction failed for session %s: %r", session.id, exc)

    state = session.state_of(peer_id) or KnowledgeState()
    beliefs = "\n".join(f"- {b.text}" for b in state.beliefs) or "(none recorded)"
    questions = "\n".join(f"- {q}" for q in state.open_questions) or "(none recorded)"
    grounding = f"Situation under discussion: {situation}" if situation else f"Respond to {focus} in context."
    return (
        f"{grounding}\nBeliefs:\n{beliefs}\nCurrent explanation: {state.explanation or '(none recorded)'}\n"
        f"Open questions:\n{questions}\n"
        "For this reply, speak from the beliefs and explanation above. Use them to make a prediction "
        "or explain your reasoning. If a public observation is hard to reconcile, acknowledge what "
        "was observed and ask how it fits. You can attribute a competing idea to its speaker. "
        "Only express a changed view as your own if your current understanding already supports "
        "that specific change. If two of your recorded ideas pull in different directions, say what "
        "you are unsure how to reconcile. Use the text of your belief as your reason if that is "
        "all you have. Only describe an event "
        "or group practice if you can quote the words that establish it and attribute it to its source."
    )
