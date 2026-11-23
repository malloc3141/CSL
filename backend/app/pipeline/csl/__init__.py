"""The CSL pipeline: one class, two owners (HANDOFF section 6).

* knowledge.py (Alex): init_turn, build_classroom, update_states
* discussion.py (Seongho): select_speaker, speak
* prompting.py: cache-friendly request assembly shared by both

CslShortenPipeline ("csl-shorten") is the same pipeline with the prompt changes of 2026-11-23 switched on:
shorter knowledge states, peers that state and hold their own view and do not end every message on what
they cannot tell, a tutor opening that gives nothing away, a stricter setup chat. It exists so those
changes can be tried on the deployed server next to "csl" (pick it under "Agents" on /dev, or open the
start page as /?pipeline=csl-shorten).
"""
from __future__ import annotations

from ...protocol import Message
from ...session import Session
from ..base import Classroom, InitResult, SpeakerDecision, StateUpdate, TextSink
from . import discussion, knowledge


class CslPipeline:
    name = "csl"
    shorten = False  # True in CslShortenPipeline: each module then picks its "*_SHORTEN" / strict texts

    async def init_turn(self, session: Session, out: TextSink) -> InitResult:
        return await knowledge.init_turn(session, out, shorten=self.shorten)

    async def build_classroom(self, session: Session) -> Classroom:
        return await knowledge.build_classroom(session, shorten=self.shorten)

    async def update_states(self, session: Session, message: Message) -> list[StateUpdate]:
        return await knowledge.update_states(session, message, shorten=self.shorten)

    async def select_speaker(self, session: Session) -> SpeakerDecision:
        return await discussion.select_speaker(session)

    async def speak(self, session: Session, decision: SpeakerDecision, out: TextSink) -> None:
        await discussion.speak(session, decision, out, shorten=self.shorten)


class CslShortenPipeline(CslPipeline):
    name = "csl-shorten"
    shorten = True
