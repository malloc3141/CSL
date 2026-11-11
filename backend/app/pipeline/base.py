"""The contract between the serving layer and the agent pipeline.

Implement `Pipeline` and point the PIPELINE environment variable at your class
("package.module:ClassName"). docs/PIPELINE.md walks through it.

Rules that keep the system consistent:

* Read from `session`; never append to `session.messages` or `session.states`.
  Return values instead and the orchestrator applies them.
* `select_speaker` and `speak` may be called for a turn that is later thrown
  away (the learner interrupted, or the turn was prefetched and discarded).
  They must not change anything. Keep bookkeeping in `update_states`, which is
  called exactly once for every message that actually entered the discussion.
* `session.scratch` is yours. Keep it JSON-serializable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

from ..protocol import KnowledgeState, Message, Participant, StateChange
from ..session import Session


class PipelineError(Exception):
    """Raise this for failures the learner can retry (bad LLM output etc.)."""


class TextSink(Protocol):
    async def write(self, text: str) -> None:
        """Send the next chunk of the utterance. Call once with the whole text
        if you do not stream."""


@dataclass
class InitResult:
    # True once the initialization chat has what it needs; the orchestrator
    # then calls build_classroom.
    done: bool


@dataclass
class Classroom:
    # One tutor and the peers. Peers get colours by `peer_index` (assigned in
    # list order if you leave it None).
    participants: list[Participant]
    # Initial knowledge state per peer id.
    states: dict[str, KnowledgeState]
    # One line shown to the learner: what the session is built around.
    focus: Optional[str] = None


@dataclass
class SpeakerDecision:
    agent_id: Optional[str] = None
    # After this utterance, stop and wait for the learner's explanation.
    invite_user: bool = False
    # End the discussion instead of producing another turn.
    end: bool = False
    # Passed through to `speak` (e.g. "respond to the learner's question").
    directive: Optional[str] = None
    # Passed through to `speak` and stored on the resulting Message.meta.
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class StateUpdate:
    agent_id: str
    # The complete new state (not a patch). Identical to the current one = no-op.
    state: KnowledgeState
    # Leave None and the orchestrator computes the diff shown in the panel.
    changes: Optional[list[StateChange]] = None


@runtime_checkable
class Pipeline(Protocol):
    name: str

    async def init_turn(self, session: Session, out: TextSink) -> InitResult:
        """Write the guide's next message of the initialization chat.

        Called first with an empty `session.init_transcript`, then again after
        every learner reply. Return InitResult(done=True) with a closing line
        when you have enough to build the classroom.
        """

    async def build_classroom(self, session: Session) -> Classroom:
        """Create the tutor, the peers and each peer's initial knowledge state
        from `session.topic` and `session.init_transcript`."""

    async def select_speaker(self, session: Session) -> SpeakerDecision:
        """Decide who speaks next, given `session.transcript`.

        The last message may be the learner's (role == "user"): they can
        interject at any time, and `message.invited` tells you whether they
        were answering the tutor's invitation.
        """

    async def speak(self, session: Session, decision: SpeakerDecision, out: TextSink) -> None:
        """Write the utterance of `decision.agent_id` to `out`."""

    async def update_states(self, session: Session, message: Message) -> list[StateUpdate]:
        """Called exactly once after `message` was added to the discussion
        (agent or learner). Return the peers whose knowledge state changed."""
