"""In-memory state of one learning session.

Pipelines receive a Session and read from it. They must not append messages or
states themselves: the orchestrator does that from what they return. The one
place a pipeline may write is `session.scratch`.
"""
from __future__ import annotations

import contextvars
import json
import time
import uuid
from typing import Any, Callable, Optional

from .protocol import (
    ActiveTurn,
    KnowledgeState,
    Language,
    Message,
    Pace,
    Participant,
    Phase,
    SessionSnapshot,
    StateVersion,
    Status,
)

# Set by the orchestrator so that helpers (e.g. the LLM wrapper) can attribute
# their logs to the session they run for.
current_session: contextvars.ContextVar[Optional["Session"]] = contextvars.ContextVar(
    "current_session", default=None
)


def new_id() -> str:
    return uuid.uuid4().hex


class Session:
    def __init__(self, session_id: str, topic: str, language: Language, turn_limit: int):
        self.id = session_id
        self.topic = topic
        self.language: Language = language
        self.turn_limit = turn_limit
        # Name of the pipeline running this session (set by the registry; see SessionRegistry.pipeline_for).
        self.pipeline = ""
        # The signed-in learner who created the session (users.id), or None for a session without a user.
        self.user_id: Optional[str] = None
        self.phase: Phase = "init"
        self.status: Status = "running"
        self.pace = Pace()
        self.participants: list[Participant] = []
        self.focus: Optional[str] = None
        self.messages: list[Message] = []
        self.states: dict[str, list[StateVersion]] = {}
        self.active_turn: Optional[ActiveTurn] = None
        self.invited_turn_id: Optional[str] = None
        self.created_at = time.time()
        self.seq = 0
        # Private to the pipeline. Must stay JSON-serializable: it is persisted
        # with the session and restored after a server restart.
        self.scratch: dict[str, Any] = {}
        # Installed by the orchestrator: log(type, data) appends to the event log
        # without broadcasting to the client.
        self.log: Callable[[str, dict[str, Any]], None] = lambda _type, _data: None

    # ------------------------------------------------------------------ read helpers

    @property
    def transcript(self) -> list[Message]:
        """Discussion messages, oldest first (agents and the learner)."""
        return [m for m in self.messages if m.channel == "discussion"]

    @property
    def init_transcript(self) -> list[Message]:
        """The initialization chat between the guide and the learner."""
        return [m for m in self.messages if m.channel == "init"]

    @property
    def turn_count(self) -> int:
        return sum(1 for m in self.messages if m.channel == "discussion")

    @property
    def last_message(self) -> Optional[Message]:
        t = self.transcript
        return t[-1] if t else None

    @property
    def peers(self) -> list[Participant]:
        return [p for p in self.participants if p.role == "peer"]

    @property
    def tutor(self) -> Optional[Participant]:
        return next((p for p in self.participants if p.role == "tutor"), None)

    def participant(self, agent_id: str) -> Optional[Participant]:
        return next((p for p in self.participants if p.id == agent_id), None)

    def state_of(self, agent_id: str) -> Optional[KnowledgeState]:
        """Current knowledge state of an agent (a copy; mutate freely)."""
        versions = self.states.get(agent_id)
        return versions[-1].state.model_copy(deep=True) if versions else None

    def state_history(self, agent_id: str) -> list[StateVersion]:
        return list(self.states.get(agent_id, []))

    # ------------------------------------------------------------------ snapshot / persistence

    def snapshot(self) -> SessionSnapshot:
        return SessionSnapshot(
            session_id=self.id,
            topic=self.topic,
            language=self.language,
            pipeline=self.pipeline,
            user_id=self.user_id,
            phase=self.phase,
            status=self.status,
            pace=self.pace,
            participants=self.participants,
            focus=self.focus,
            messages=self.messages,
            states=self.states,
            active_turn=self.active_turn,
            invited_turn_id=self.invited_turn_id,
            turn_limit=self.turn_limit,
            last_seq=self.seq,
            created_at=self.created_at,
        )

    def dump(self) -> str:
        return json.dumps(
            {"snapshot": self.snapshot().wire(), "scratch": self.scratch},
            ensure_ascii=False,
            default=str,
        )

    @classmethod
    def restore(cls, raw: str) -> "Session":
        payload = json.loads(raw)
        snap = SessionSnapshot.model_validate(payload["snapshot"])
        s = cls(snap.session_id, snap.topic, snap.language, snap.turn_limit)
        s.pipeline = snap.pipeline
        s.user_id = snap.user_id
        s.phase = snap.phase
        s.status = snap.status
        s.pace = snap.pace
        s.participants = snap.participants
        s.focus = snap.focus
        s.messages = snap.messages
        s.states = snap.states
        s.invited_turn_id = snap.invited_turn_id
        s.created_at = snap.created_at
        s.seq = snap.last_seq
        s.scratch = payload.get("scratch") or {}
        # Whatever was being generated when the process stopped is gone.
        s.active_turn = None
        if s.phase == "discussion" and s.status == "running":
            s.status = "paused"
        return s
