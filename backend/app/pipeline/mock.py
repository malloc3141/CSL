"""Scripted pipeline: replays the Studio 3 lo-fi scenario
("Why is summer hotter than winter?") without any LLM call.

It exists so that the frontend can be built and the serving layer tested
before the real pipeline is ready. It ignores the session topic.

* 15 scripted turns with the knowledge-state changes SC-01..SC-16.
* Turn 15 invites the learner to explain. The reply is matched by keyword to
  one of the four lo-fi branches (A both / B1 angle / B2 day length / C neither).
  Every branch except A invites the learner to try again.
* Any other learner message gets a canned tutor reply, then the script goes on.
  Asking about the axial tilt before turn 5 plays the lo-fi aside (Q2, Q3).
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..protocol import Belief, KnowledgeState, Message, Participant
from ..session import Session
from .base import Classroom, InitResult, SpeakerDecision, StateUpdate, TextSink

FIXTURE = Path(__file__).parent / "fixtures" / "seasons.json"

ANGLE = re.compile(r"각도|비스듬|수직|똑바로|고도|높이|면적|모여|angle|direct|slant|perpendicular|concentrat|area", re.I)
DAY = re.compile(r"낮|일조|오래|길어|늦게|day ?length|daylight|longer|hours", re.I)
TILT = re.compile(r"자전축|기울|axis|axial|tilt", re.I)


class MockPipeline:
    name = "mock"

    def __init__(self) -> None:
        self.fx: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.delay = get_settings().mock_chunk_delay

    # ------------------------------------------------------------------ helpers

    async def _type(self, out: TextSink, text: str) -> None:
        for chunk in re.findall(r"\S+\s*", text):
            await out.write(chunk)
            if self.delay:
                await asyncio.sleep(self.delay)

    def _scratch(self, session: Session) -> dict[str, Any]:
        return session.scratch.setdefault("mock", {"cursor": 0, "queue": [], "finished": False, "aside": False})

    def _next(self, session: Session) -> tuple[str, dict[str, Any]] | None:
        """The turn that should be spoken next: ("queue" | "script", turn)."""
        sc = self._scratch(session)
        if sc["queue"]:
            return "queue", sc["queue"][0]
        if not sc["finished"] and sc["cursor"] < len(self.fx["turns"]):
            return "script", self.fx["turns"][sc["cursor"]]
        return None

    def _apply(self, session: Session, changes: list[Any]) -> list[StateUpdate]:
        lang = session.language
        states: dict[str, KnowledgeState] = {}
        for ch in changes:
            key = ch if isinstance(ch, str) else None
            ch = self.fx["stateChanges"][ch] if isinstance(ch, str) else ch
            state = states.get(ch["agent"]) or session.state_of(ch["agent"])
            if state is None:
                continue
            if ch["field"] == "beliefs":
                state.beliefs.append(
                    Belief(id=f"{ch['agent']}-{key or len(state.beliefs) + 1}", text=ch["add"][lang], accuracy="correct")
                )
            elif ch["field"] == "explanation":
                state.explanation = ch["after"][lang]
                state.explanation_accuracy = ch.get("accuracy")
            else:
                state.open_questions = [ch["after"][lang]]
            states[ch["agent"]] = state
        return [StateUpdate(agent_id=a, state=s) for a, s in states.items()]

    # ------------------------------------------------------------------ Pipeline

    async def init_turn(self, session: Session, out: TextSink) -> InitResult:
        replied = any(m.role == "user" for m in session.init_transcript)
        await self._type(out, self.fx["init"]["closing" if replied else "question"][session.language])
        return InitResult(done=replied)

    async def build_classroom(self, session: Session) -> Classroom:
        lang = session.language
        await asyncio.sleep(self.delay * 20)
        participants = [
            Participant(id=p["id"], role=p["role"], name=p["name"], origin=p["origin"][lang],
                        description=p["description"][lang])
            for p in self.fx["participants"]
        ]
        states = {
            agent: KnowledgeState(
                beliefs=[Belief(id=f"{agent}-b{i + 1}", text=b[lang], accuracy="correct")
                         for i, b in enumerate(init["beliefs"])],
                explanation=init["explanation"][lang],
                explanation_accuracy="incorrect",
            )
            for agent, init in self.fx["initialStates"].items()
        }
        return Classroom(participants=participants, states=states, focus=self.fx["focus"][lang])

    async def select_speaker(self, session: Session) -> SpeakerDecision:
        nxt = self._next(session)
        if nxt is None:
            return SpeakerDecision(end=True)
        source, turn = nxt
        return SpeakerDecision(
            agent_id=turn["speaker"],
            invite_user=bool(turn.get("inviteUser")),
            meta={"mock": {"source": source, "key": turn.get("key")}},
        )

    async def speak(self, session: Session, decision: SpeakerDecision, out: TextSink) -> None:
        nxt = self._next(session)
        assert nxt is not None
        await self._type(out, nxt[1]["text"][session.language])

    async def update_states(self, session: Session, message: Message) -> list[StateUpdate]:
        sc = self._scratch(session)
        if message.role == "user":
            if message.invited:
                angle, day = ANGLE.search(message.text), DAY.search(message.text)
                branch = "A" if angle and day else "B1" if angle else "B2" if day else "C"
                turns = [dict(t) for t in self.fx["branches"][branch]["turns"]]
                turns[0]["changes"] = self.fx["branches"][branch]["changes"]
                sc["queue"] = turns
                session.log("mock.branch", {"branch": branch})
            elif not sc["aside"] and sc["cursor"] <= 4 and TILT.search(message.text):
                sc["aside"] = True
                sc["queue"] = [dict(t) for t in self.fx["aside"]] + sc["queue"]
            else:
                sc["queue"].insert(0, {"speaker": "tutor", "text": self.fx["interjectionReply"]})
            return []

        source = (message.meta.get("mock") or {}).get("source")
        if source == "queue" and sc["queue"]:
            turn = sc["queue"].pop(0)
            if turn.get("end"):
                sc["finished"] = True
        elif source == "script":
            turn = self.fx["turns"][sc["cursor"]]
            sc["cursor"] += 1
        else:
            return []
        return self._apply(session, turn.get("changes") or [])
