"""Cache-friendly request assembly shared by every agent call in a CSL session.

Claude's prompt cache (also through OpenRouter) is a prefix match keyed at the end of blocks that carry
`cache_control`. A byte change anywhere invalidates everything after it, and a block that grows (the
whole transcript in one string) never matches the previous request. So every call is built in the same
order, most stable first:

    system  [0] session block   topic, focus, roster, language, transcript format     <- cache
            [1] role block      what this kind of call does (static for the session)  <- cache
    user    [T1] ... [Tn]       one block per discussion message, rendered once, append-only
                                (a breakpoint every STRIDE messages and on the last one)
            tail                everything that changes per call: the speaker's own state, directive,
                                counts, the instruction for this call. Never cached.

Rules that keep the cache valid (researches/context_caching/README.md, section 4):
* Nothing that changes during a session goes into the session or role block (no state, no turn
  counts, no directive, no time).
* Persona and state of a peer go in the tail, so all peers share one cache lane per role.
* Hidden information (the tutor's reference) goes only in the tutor's role block, never in the
  session block that peers also receive.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from ...protocol import Message, Participant

CACHE: dict[str, str] = {"type": "ephemeral"}
# Claude allows 4 breakpoints: session block, role block, a fixed stride point and the last message.
# The stride point keeps a read position that does not move for STRIDE messages, so a role that has
# been silent for a while (Claude looks back at most 20 blocks) still finds an earlier entry.
STRIDE = 15

LANG = {"ko": "Korean (natural spoken 존댓말, '-요' endings)", "en": "English"}
USER_LABEL = {"ko": "학습자", "en": "Learner"}

SESSION_BLOCK = """This is a simulated study discussion in a learning app. A tutor and students with incomplete, partly wrong understanding discuss one topic. A learner watches and may join in at any time; their messages are labelled "{user}". When you speak to the learner, address them directly in the second person. In Korean never name or title the learner at all (no "학습자", "학습자님", "당신"): Korean drops the subject, so write e.g. "이번에는 직접 설명해 주실래요?" or "방금 말해 준 것처럼". Never credit their idea to someone else. Never write the label "{user}" or a turn label such as "[T13]" in a message. The discussion exists so the learner notices gaps in their own understanding.

Topic: {topic}
Focus: {focus}
Language of the discussion: {lang}

Participants:
{roster}

The discussion so far is given as one block per message, oldest first, in the form
[T<turn>] <speaker>: <text>
"[T7] {user} (answering the tutor's invitation): ..." marks a learner message that answers the tutor's request to explain. The instruction for this call comes after the last message."""


def session_block(topic: str, focus: Optional[str], language: str, participants: Sequence[Participant]) -> str:
    roster = "\n".join(
        f"- {p.id}: {p.name} ({'tutor' if p.role == 'tutor' else 'student'})" for p in participants
    )
    return SESSION_BLOCK.format(
        topic=topic, focus=focus or topic, lang=LANG.get(language, language), roster=roster,
        user=USER_LABEL.get(language, "Learner"),
    )


def render_message(m: Message, language: str) -> str:
    """One discussion message as it appears in every prompt. Must depend only on the message itself."""
    name = USER_LABEL.get(language, m.speaker_name) if m.role == "user" else m.speaker_name
    note = " (answering the tutor's invitation)" if m.role == "user" and m.invited else ""
    number = m.turn_number if m.turn_number is not None else "?"
    return f"[T{number}] {name}{note}: {m.text}"


def _text(text: str, cached: bool = False) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "text", "text": text}
    if cached:
        block["cache_control"] = dict(CACHE)
    return block


def build_messages(
    session_text: str,
    role_text: str,
    transcript: Sequence[Message],
    language: str,
    tail: str,
) -> list[dict[str, Any]]:
    """The chat-completions `messages` for one agent call, in cache order."""
    lines = [render_message(m, language) for m in transcript]
    last = len(lines) - 1
    stride = (last // STRIDE) * STRIDE - 1 if last >= STRIDE else -1  # last block of the latest full stride
    blocks = [_text(line, cached=i in (last, stride)) for i, line in enumerate(lines)]
    if not blocks:
        blocks = [_text("(The discussion has not started yet.)")]
    blocks.append(_text(tail))
    return [
        {"role": "system", "content": [_text(session_text, cached=True), _text(role_text, cached=True)]},
        {"role": "user", "content": blocks},
    ]


def cache_breakpoints(messages: list[dict[str, Any]]) -> int:
    return sum(
        1 for msg in messages for block in msg["content"] if isinstance(block, dict) and "cache_control" in block
    )
