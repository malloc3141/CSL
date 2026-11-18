"""Setup chat and knowledge states (Alex).

Placeholder: delegates to the baseline unchanged until the real implementation lands here.
Contract with discussion.py (HANDOFF section 6):
* the tutor's hidden notes {"reference", "key_points"} live in scratch["baseline"]["tutor"];
* the turn of the last invitation lives in scratch["baseline"]["last_invite"] (set in update_states).
If these keys move, update discussion.tutor_notes / discussion.last_invite in the same change.

To share the discussion's prompt cache, state-update calls can be built with
prompting.build_messages (same session block and transcript blocks, own role block, state in the tail).
"""
from __future__ import annotations

from ...protocol import Message
from ...session import Session
from ..base import Classroom, InitResult, StateUpdate, TextSink
from ..baseline import BaselinePipeline

_baseline = BaselinePipeline()


async def init_turn(session: Session, out: TextSink) -> InitResult:
    return await _baseline.init_turn(session, out)


async def build_classroom(session: Session) -> Classroom:
    return await _baseline.build_classroom(session)


async def update_states(session: Session, message: Message) -> list[StateUpdate]:
    return await _baseline.update_states(session, message)
