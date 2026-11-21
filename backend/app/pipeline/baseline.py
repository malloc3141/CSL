"""Reference pipeline on OpenRouter. A working placeholder, not the final design.

It makes the system run end to end with real models, and shows one way to
implement each Pipeline method. Replace it piece by piece:

* setup chat: ask -> probe -> more follow-ups if the guide needs them -> closing message;
  the classroom is built only after a message that asks the learner nothing
* knowledge state: "persistent belief list" (one JSON update per peer per message)
* turn allocation: reactions to the learner are rule-based; otherwise a hidden
  moderator call picks the next speaker ("centralized selection")
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from ..config import get_settings
from ..llm import extract_json, get_llm
from ..protocol import Belief, KnowledgeState, Message, Participant
from ..session import Session
from .base import Classroom, InitResult, PipelineError, SpeakerDecision, StateUpdate, TextSink

log = logging.getLogger("csl.baseline")

LANG = {"ko": "Korean (natural spoken 존댓말, '-요' endings)", "en": "English"}
ACCURACY = {"correct", "partial", "incorrect"}

INIT_SYSTEM = """You are the setup guide of a learning app. In the app, simulated classmates with incomplete understanding discuss a topic so that the learner notices gaps in their own understanding. You are running a short setup chat before the discussion.
Write in {lang}. Be brief: 1-3 sentences. Never explain the topic, never say whether the learner is right, never hint at the answer.

{stage}"""

_CLOSING = "in one sentence state the specific point the session will be built around (the part of their explanation that most needs examining). Then say you are setting up the classroom. This is the last message of the setup chat and the learner cannot reply to it: do not ask anything, do not invite them to explain more, and do not end with a question."

INIT_STAGES = {
    "ask": 'The learner entered this topic: "{topic}". If it is broad, narrow it to one concrete why/how question and say which one you picked. Then ask the learner to explain what they currently understand about it in one or two sentences. Tell them a complete or correct answer is not expected.',
    "probe": 'Topic: "{topic}". Ask exactly one short follow-up question about the vaguest or weakest link in the learner\'s explanation ("what exactly do you mean by ...", "why does that follow?").',
    "decide": (
        'Topic: "{topic}". Write ONE of these two messages. '
        "(a) If you still cannot tell what the learner thinks the mechanism is, ask exactly one more short follow-up question about the vaguest or weakest link in their explanation. End the message with that question. "
        "(b) Otherwise close the setup chat: " + _CLOSING
    ),
    "close": 'Topic: "{topic}". Close the setup chat: ' + _CLOSING,
}

# The setup chat is ask -> probe -> (more follow-ups if the guide needs them) -> closing message.
# After INIT_MIN_REPLIES learner replies the guide may close; from INIT_MAX_REPLIES on it is told to.
INIT_MIN_REPLIES = 2
INIT_MAX_REPLIES = 4

# From the point where the guide may close, it says itself whether its message ends the chat.
# (Appended after the stage text is formatted: the braces are literal.)
INIT_VERDICT = """

Answer with a single JSON object and nothing else: {"message": "<the message the learner reads>", "done": true|false}
"done" is about the message you just wrote. true: it closes the setup chat and asks or requests nothing from the learner. false: it asks them a question or asks them to explain, describe or add anything, in any wording, with or without a question mark."""

# A question mark with nothing but punctuation / emoji after it: the message ends by asking.
_ENDS_WITH_QUESTION = re.compile(r"[?？][^\w?？]*$")


def ends_with_question(text: str) -> bool:
    return bool(_ENDS_WITH_QUESTION.search(text.strip()))

CLASSROOM_SYSTEM = """You design a simulated classroom for one learner. Output a single JSON object and nothing else.

Schema:
{{
  "focus": "one sentence: the question the session is built around",
  "tutor": {{
    "reference": "the correct explanation, 4-8 sentences",
    "key_points": ["the ideas a full explanation must connect"],
    "pitfalls": ["wrong turns the discussion is likely to take"]
  }},
  "peers": [
    {{
      "name": "a short given name",
      "origin": "short phrase: where this peer's thinking comes from, e.g. 'From your explanation' or 'From a common misconception'",
      "description": "one sentence for the peer's card: what this student thinks",
      "beliefs": [{{"text": "a fact this student accepts", "accuracy": "correct|partial|incorrect"}}],
      "explanation": "{explanation}",
      "explanation_accuracy": "correct|partial|incorrect",
      "open_questions": []
    }}
  ]
}}

Rules:
- Create exactly {n} peers. They are students with incomplete understanding and each holds a DIFFERENT mental model.
- Build at least one peer from the weakest point of the learner's own explanation. Build the others from misconceptions that are common for this topic.
- Do not turn into a misconception anything the learner explained clearly and correctly.
- No peer starts with the complete correct explanation. 2-4 beliefs each. Peers start confident, so open_questions is usually empty.
- Every string the learner will read (focus, peers) is in {lang}. The tutor block may be in any language."""

MODERATOR_SYSTEM = """You are the hidden moderator of a simulated study discussion. You only decide who speaks next. Output a single JSON object: {{"speaker": "<id>", "invite_user": true|false}}

Participants:
{roster}

Rules:
- Peers carry the discussion: they question and build on each other. If the last message asked a specific participant something, pick that participant.
- Pick the tutor only when a question was left unanswered, the peers are reinforcing a wrong idea together, two conflicting explanations are not being examined, or the discussion is going in circles.
- Never pick the participant who spoke last.
- invite_user may be true only together with the tutor: the peers have reached the edge of a key idea but cannot make the connection, so the tutor will ask the learner to explain it. {invite_rule}"""

PEER_SYSTEM = """You are {name}, a student in a small study discussion. Topic: {topic}. Focus: {focus}
Others in the discussion: {others}. The learner ("{user}") may join in at any time.

This is everything you currently believe about the topic. You know nothing beyond it.
Beliefs:
{beliefs}
Your current explanation: {explanation}
Questions you are stuck on: {questions}

Stay strictly inside this understanding. Reason from it, defend it, or doubt it when someone gives you a concrete reason. Never state a fact or mechanism that is neither in it nor already said in the discussion. You may be wrong without knowing it.

Write your next message: 1-3 sentences, in {lang}, conversational, no name prefix, no lists. React to what was just said: ask, challenge, concede one specific point, or try out an idea. {directive}"""

TUTOR_SYSTEM = """You are the tutor of a small study discussion. Topic: {topic}. Focus: {focus}
Students: {others}. The learner ("{user}") may join in at any time.

Reference explanation (for your eyes only, never recite it):
{reference}
Key points: {key_points}

You listen while the students make progress. When you step in, address one specific error or contradiction with a single fact or a small thought experiment, then hand the question back. Never give the full explanation.

Write your next message: 2-4 sentences, in {lang}, no name prefix, no lists. {directive}"""

TUTOR_DIRECTIVES = {
    "open": "Open the discussion with one focused question about the focus above.",
    "invite": "The students are close. Say in one sentence what they have worked out, then ask the learner to explain the missing connection to them. Add that a complete or correct answer is not expected.",
    "feedback": "The learner has just explained their understanding. Say specifically which part is right, and which connection is missing or wrong and why, without supplying the full answer. Then invite them to refine it or let the students pick it up.",
    "answer": "The learner has just said something. If it is a question, answer it briefly and accurately and hand back to the students. If they want to move on or change direction, steer the discussion that way.",
}
PEER_DIRECTIVES = {
    "react": "The learner has just spoken: respond to them directly from your own understanding (restate what you took from it, or question an assumption or a missing step).",
}

STATE_SYSTEM = """You track what one simulated student believes during a study discussion. Update the student's knowledge state after the latest message. Output a single JSON object and nothing else.

Rules:
- Change only what the latest message gives this student a concrete reason to change. Hearing a claim is not accepting it: an unsupported claim from a classmate may at most raise an open question; a fact stated by the tutor is accepted as a belief. If the student is the speaker, record what they just conceded, proposed or asked.
- Students move in small steps. Never jump to the complete correct explanation, and keep the remaining gap explicit in "explanation" ("... but cannot yet explain ...").
- Keep the id of every belief you keep. Give new beliefs the id "new".
- Label each belief and the explanation as correct, partial or incorrect, judged against the reference.
- open_questions: at most 2, only what this student is actually stuck on now.
- All text in {lang}.

If nothing changes, output {{"changed": false}}. Otherwise output:
{{"changed": true, "beliefs": [{{"id": "...", "text": "...", "accuracy": "correct|partial|incorrect"}}], "explanation": "...", "explanation_accuracy": "correct|partial|incorrect", "open_questions": ["..."]}}"""


def _accuracy(value: Any) -> Any:
    return value if value in ACCURACY else None


def _render(messages: list[Message], limit: int = 30) -> str:
    return "\n".join(f"{m.speaker_name}: {m.text}" for m in messages[-limit:]) or "(nothing yet)"


class BaselinePipeline:
    name = "baseline"

    def __init__(self) -> None:
        self.settings = get_settings()

    def _scratch(self, session: Session) -> dict[str, Any]:
        return session.scratch.setdefault("baseline", {"tutor": {}, "last_invite": 0})

    # ------------------------------------------------------------------ init chat

    async def init_turn(self, session: Session, out: TextSink) -> InitResult:
        transcript = session.init_transcript
        replies = sum(1 for m in transcript if m.role == "user")
        if replies == 0:
            stage = "ask"
        elif replies < INIT_MIN_REPLIES:
            stage = "probe"
        else:
            stage = "decide" if replies < INIT_MAX_REPLIES else "close"
        may_close = stage in ("decide", "close")
        system = INIT_SYSTEM.format(
            lang=LANG[session.language], stage=INIT_STAGES[stage].format(topic=session.topic)
        ) + (INIT_VERDICT if may_close else "")
        if not may_close:  # the first question and the first follow-up: always answered by the learner
            messages = [{"role": "system", "content": system}]
            if not transcript:
                messages.append({"role": "user", "content": session.topic})
            for m in transcript:
                messages.append({"role": "user" if m.role == "user" else "assistant", "content": m.text})
            async for chunk in get_llm().stream(messages, temperature=0.5, max_tokens=300):
                await out.write(chunk)
            return InitResult(done=False)
        # The guide says whether this message ends the chat, so the system does what the learner reads:
        # a request for more waits for the answer, and the classroom is built only after a closing message.
        # (One JSON call: this message arrives whole instead of streaming.)
        # The chat goes in as one block of text, not as chat turns: given its own earlier plain-text
        # turns, the model keeps writing plain text and ignores the JSON instruction (seen on
        # claude-haiku-5.5, 2026-11-21).
        chat = "\n".join(f"{'Learner' if m.role == 'user' else 'Guide'}: {m.text}" for m in transcript)
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": f"Topic: {session.topic}\n\nSetup chat so far:\n{chat}\n\n"
                "Write the guide's next message. Reply with the JSON object only.",
            },
        ]
        raw = (await get_llm().complete(messages, temperature=0.5, max_tokens=400, json_mode=True)).strip()
        try:
            data = extract_json(raw)
        except ValueError:
            if not raw or raw.startswith(("{", "`")):
                raise PipelineError("the setup guide returned neither a message nor valid JSON") from None
            # Plain text after all: show it, and let the text decide whether it was the closing message.
            await out.write(raw)
            return InitResult(done=not ends_with_question(raw))
        text = str(data.get("message") or "").strip()
        if not text:
            raise PipelineError("the setup guide returned no message")
        await out.write(text)
        # Belt and braces: a message that ends with a question is never the last one, whatever "done" says.
        return InitResult(done=data.get("done") in (True, "true") and not ends_with_question(text))

    # ------------------------------------------------------------------ classroom

    async def build_classroom(
        self, session: Session, *,
        explanation: str = "this student's current explanation, 1-3 sentences, including what they cannot explain",
        peer_rules: str = "",
    ) -> Classroom:
        n = self.settings.peer_count
        system = CLASSROOM_SYSTEM.format(n=n, lang=LANG[session.language], explanation=explanation)
        if peer_rules:
            system += "\n" + peer_rules
        data = await get_llm().complete_json(
            [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": f"Topic: {session.topic}\n\nSetup chat:\n{_render(session.init_transcript)}",
                },
            ],
            temperature=0.6,
        )
        peers = [p for p in data.get("peers") or [] if isinstance(p, dict)][:n]
        if not peers:
            raise PipelineError("classroom generation returned no peers")
        participants = [Participant(id="tutor", role="tutor", name="Tutor")]
        states: dict[str, KnowledgeState] = {}
        for i, p in enumerate(peers):
            pid = f"peer{i + 1}"
            participants.append(
                Participant(
                    id=pid,
                    role="peer",
                    name=str(p.get("name") or f"Peer {i + 1}")[:20],
                    origin=p.get("origin"),
                    description=p.get("description"),
                )
            )
            states[pid] = KnowledgeState(
                beliefs=[
                    Belief(id=f"{pid}-b{j + 1}", text=str(b.get("text", "")), accuracy=_accuracy(b.get("accuracy")))
                    for j, b in enumerate(p.get("beliefs") or [])
                    if isinstance(b, dict) and b.get("text")
                ],
                explanation=str(p.get("explanation") or ""),
                explanation_accuracy=_accuracy(p.get("explanation_accuracy")),
                open_questions=[str(q) for q in p.get("open_questions") or []][:2],
            )
        tutor = data.get("tutor") if isinstance(data.get("tutor"), dict) else {}
        self._scratch(session)["tutor"] = tutor
        return Classroom(participants=participants, states=states, focus=data.get("focus"))

    # ------------------------------------------------------------------ turn allocation

    def _rotate(self, session: Session, exclude: str | None) -> str:
        """Fallback: the peer who has been silent the longest."""
        spoken = [m.speaker_id for m in session.transcript]
        peers = [p.id for p in session.peers if p.id != exclude] or [p.id for p in session.peers]
        return min(peers, key=lambda pid: max((i for i, s in enumerate(spoken) if s == pid), default=-1))

    async def select_speaker(self, session: Session) -> SpeakerDecision:
        transcript = session.transcript
        sc = self._scratch(session)
        if not transcript:
            return SpeakerDecision(agent_id="tutor", directive="open")
        last = transcript[-1]
        if last.role == "user":
            # A peer reacts to the learner first, then the tutor responds.
            return SpeakerDecision(agent_id=self._rotate(session, None), directive="react")
        if len(transcript) >= 2 and transcript[-2].role == "user" and last.role == "peer":
            return SpeakerDecision(agent_id="tutor", directive="feedback" if transcript[-2].invited else "answer")

        turn = len(transcript)
        can_invite = turn >= 6 and turn - sc["last_invite"] >= 8
        roster = "\n".join(
            f"- {p.id}: {p.name} ({'tutor' if p.role == 'tutor' else 'student'})" for p in session.participants
        )
        invite_rule = "" if can_invite else "It is too early for that now: invite_user must be false."
        tutor = sc.get("tutor") or {}
        try:
            data = await get_llm().complete_json(
                [
                    {"role": "system", "content": MODERATOR_SYSTEM.format(roster=roster, invite_rule=invite_rule)},
                    {
                        "role": "user",
                        "content": f"Focus: {session.focus}\nKey points the discussion should reach: "
                        f"{json.dumps(tutor.get('key_points') or [], ensure_ascii=False)}\n\n"
                        f"Discussion so far:\n{_render(transcript, 12)}\n\nWho speaks next?",
                    },
                ],
                fast=True,
                temperature=0.2,
                max_tokens=100,
            )
            speaker = data.get("speaker")
            invite = bool(data.get("invite_user"))
        except Exception as exc:
            log.warning("moderator failed, rotating: %r", exc)
            speaker, invite = None, False
        if session.participant(speaker or "") is None or speaker == last.speaker_id:
            speaker = self._rotate(session, last.speaker_id)
        invite = invite and can_invite and speaker == "tutor"
        return SpeakerDecision(
            agent_id=speaker,
            invite_user=invite,
            directive="invite" if invite else None,
            meta={"invite": True} if invite else {},
        )

    # ------------------------------------------------------------------ utterances

    async def speak(self, session: Session, decision: SpeakerDecision, out: TextSink) -> None:
        agent = session.participant(decision.agent_id or "")
        assert agent is not None
        lang = LANG[session.language]
        user = "나" if session.language == "ko" else "You"
        others = ", ".join(p.name for p in session.participants if p.id != agent.id and p.role == "peer")
        if agent.role == "tutor":
            tutor = self._scratch(session).get("tutor") or {}
            system = TUTOR_SYSTEM.format(
                topic=session.topic,
                focus=session.focus or session.topic,
                others=others,
                user=user,
                reference=tutor.get("reference") or "(use your own knowledge of the topic)",
                key_points=json.dumps(tutor.get("key_points") or [], ensure_ascii=False),
                lang=lang,
                directive=TUTOR_DIRECTIVES.get(decision.directive or "", ""),
            )
        else:
            state = session.state_of(agent.id) or KnowledgeState()
            system = PEER_SYSTEM.format(
                name=agent.name,
                topic=session.topic,
                focus=session.focus or session.topic,
                others=(others + ", Tutor").lstrip(", "),
                user=user,
                beliefs="\n".join(f"- {b.text}" for b in state.beliefs) or "- (none)",
                explanation=state.explanation or "(none yet)",
                questions="; ".join(state.open_questions) or "(none)",
                lang=lang,
                directive=PEER_DIRECTIVES.get(decision.directive or "", ""),
            )
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": f"Discussion so far:\n{_render(session.transcript)}\n\nWrite {agent.name}'s next message.",
            },
        ]
        async for chunk in get_llm().stream(messages, temperature=0.8, max_tokens=400):
            await out.write(chunk)

    # ------------------------------------------------------------------ knowledge states

    async def _update_peer(self, session: Session, peer: Participant, message: Message) -> StateUpdate | None:
        current = session.state_of(peer.id) or KnowledgeState()
        tutor = self._scratch(session).get("tutor") or {}
        data = await get_llm().complete_json(
            [
                {"role": "system", "content": STATE_SYSTEM.format(lang=LANG[session.language])},
                {
                    "role": "user",
                    "content": f"Student: {peer.name}\n"
                    f"Reference explanation: {tutor.get('reference') or '(use your own knowledge)'}\n\n"
                    f"Current state:\n{json.dumps(current.model_dump(), ensure_ascii=False)}\n\n"
                    f"Recent discussion:\n{_render(session.transcript[:-1], 6)}\n\n"
                    f"Latest message, by {message.speaker_name}"
                    f"{' (this student)' if message.speaker_id == peer.id else ''}:\n{message.text}",
                },
            ],
            fast=True,
            temperature=0.2,
            max_tokens=700,
        )
        if not data.get("changed"):
            return None
        known = {b.id for b in current.beliefs}
        beliefs: list[Belief] = []
        fresh = len(session.state_history(peer.id)) * 10
        for b in data.get("beliefs") or []:
            if not isinstance(b, dict) or not b.get("text"):
                continue
            bid = b.get("id")
            if bid not in known or any(x.id == bid for x in beliefs):
                fresh += 1
                bid = f"{peer.id}-n{fresh}"
            beliefs.append(Belief(id=bid, text=str(b["text"]), accuracy=_accuracy(b.get("accuracy"))))
        state = KnowledgeState(
            beliefs=beliefs or current.beliefs,
            explanation=str(data.get("explanation") or current.explanation),
            explanation_accuracy=_accuracy(data.get("explanation_accuracy")) or current.explanation_accuracy,
            open_questions=[str(q) for q in data.get("open_questions") or []][:2],
        )
        return StateUpdate(agent_id=peer.id, state=state)

    async def update_states(self, session: Session, message: Message) -> list[StateUpdate]:
        if message.meta.get("invite"):
            self._scratch(session)["last_invite"] = session.turn_count
        results = await asyncio.gather(
            *(self._update_peer(session, p, message) for p in session.peers), return_exceptions=True
        )
        updates: list[StateUpdate] = []
        for peer, result in zip(session.peers, results):
            if isinstance(result, BaseException):
                log.warning("state update for %s failed: %r", peer.id, result)
            elif result is not None:
                updates.append(result)
        return updates
