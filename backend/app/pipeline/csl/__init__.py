"""The CSL pipeline: one class, two owners (HANDOFF section 6).

* knowledge.py (Alex): init_turn, build_classroom, update_states
* discussion.py (Seongho): select_speaker, speak
* prompting.py: cache-friendly request assembly shared by both
"""
from __future__ import annotations

from ...protocol import Message
from ...session import Session
from ..base import Classroom, InitResult, SpeakerDecision, StateUpdate, TextSink
from . import discussion, knowledge


class CslPipeline:
    name = "csl"

    async def init_turn(self, session: Session, out: TextSink) -> InitResult:
        return await knowledge.init_turn(session, out)

    async def build_classroom(self, session: Session) -> Classroom:
        return await knowledge.build_classroom(session)

    async def update_states(self, session: Session, message: Message) -> list[StateUpdate]:
        return await knowledge.update_states(session, message)

    async def select_speaker(self, session: Session) -> SpeakerDecision:
        return await discussion.select_speaker(session)

    async def speak(self, session: Session, decision: SpeakerDecision, out: TextSink) -> None:
        await discussion.speak(session, decision, out)
