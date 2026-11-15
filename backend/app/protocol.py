"""Wire protocol shared by the backend, the frontend and the pipelines.

Everything that crosses the WebSocket or REST boundary is defined here. Field
names are snake_case in Python and camelCase on the wire. The TypeScript types
in frontend/src/lib/csl/protocol.ts are generated from this file:

    python scripts/gen_ts.py
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

PROTOCOL_VERSION = 1


class Wire(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    def wire(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


Phase = Literal["init", "building", "ready", "discussion", "ended"]
Status = Literal["running", "paused", "waiting_user"]
Role = Literal["system", "tutor", "peer", "user"]
Channel = Literal["init", "discussion"]
Accuracy = Literal["correct", "partial", "incorrect"]
Language = Literal["ko", "en"]

# Exported as named TypeScript aliases by scripts/gen_ts.py.
NAMED_TYPES = {
    "Phase": Phase,
    "Status": Status,
    "Role": Role,
    "Channel": Channel,
    "Accuracy": Accuracy,
    "Language": Language,
}


# --------------------------------------------------------------------------- domain


class Participant(Wire):
    id: str
    role: Literal["tutor", "peer"]
    name: str
    # 0-based index among peers; the frontend maps it to a colour. None for the tutor.
    peer_index: Optional[int] = None
    # Why this agent exists, shown on the classroom card
    # (e.g. "Generated from your explanation").
    origin: Optional[str] = None
    description: Optional[str] = None


class Belief(Wire):
    id: str
    text: str
    # Optional correctness label. The UI may highlight incorrect items (usability item 4).
    accuracy: Optional[Accuracy] = None


class KnowledgeState(Wire):
    """What the learner sees in the knowledge-state panel for one peer.

    This is a *view*. A pipeline may keep any internal representation (profile
    prompt, belief list, dependency graph) and render it into this shape.
    """

    beliefs: list[Belief] = []
    explanation: str = ""
    explanation_accuracy: Optional[Accuracy] = None
    open_questions: list[str] = []


class StateChange(Wire):
    field: Literal["beliefs", "explanation", "openQuestions"]
    kind: Literal["added", "removed", "modified"]
    before: Optional[str] = None
    after: Optional[str] = None
    belief_id: Optional[str] = None


class StateVersion(Wire):
    agent_id: str
    # 0 is the initial state; each change adds one.
    version: int
    # The message that caused this version (None for the initial state).
    turn_id: Optional[str] = None
    turn_number: Optional[int] = None
    state: KnowledgeState
    changes: list[StateChange] = []
    created_at: float


class Message(Wire):
    # Same id as the turn that produced it (turn.started / message.delta).
    id: str
    channel: Channel
    role: Role
    # Participant id, "user", or "guide" (the initialization agent).
    speaker_id: str
    speaker_name: str
    peer_index: Optional[int] = None
    text: str
    # 1-based position in the discussion; None on the init channel.
    turn_number: Optional[int] = None
    # True when a user message answers the tutor's invitation to explain.
    invited: bool = False
    client_message_id: Optional[str] = None
    # Free-form, pipeline-defined. Forwarded to the frontend untouched.
    meta: dict[str, Any] = {}
    created_at: float


class Pace(Wire):
    # auto=True: the next message appears after a reading gap.
    # auto=False: the next message appears only on control.step.
    auto: bool = True
    # Multiplier on the reading gap. 2.0 is twice as fast.
    speed: float = 1.0


class ActiveTurn(Wire):
    """A message that is being generated right now ("typing…")."""

    turn_id: str
    channel: Channel
    role: Role
    speaker_id: str
    speaker_name: str
    peer_index: Optional[int] = None
    text: str = ""


class SessionSnapshot(Wire):
    protocol_version: int = PROTOCOL_VERSION
    session_id: str
    topic: str
    language: Language
    phase: Phase
    status: Status
    pace: Pace
    participants: list[Participant] = []
    # What the session is built around, decided during initialization.
    focus: Optional[str] = None
    messages: list[Message] = []
    # agent id -> every version of its knowledge state, oldest first.
    states: dict[str, list[StateVersion]] = {}
    active_turn: Optional[ActiveTurn] = None
    # Set while the tutor is waiting for the learner's explanation.
    invited_turn_id: Optional[str] = None
    turn_limit: int
    last_seq: int = 0
    created_at: float


# --------------------------------------------------------------------------- server -> client


class PhaseChanged(Wire):
    phase: Phase
    # "completed" | "turn_limit" | "user" when phase == "ended"
    reason: Optional[str] = None


class StatusChanged(Wire):
    status: Status


class PaceChanged(Wire):
    pace: Pace


class ClassroomReady(Wire):
    participants: list[Participant]
    focus: Optional[str] = None
    states: dict[str, StateVersion]


class MessageDelta(Wire):
    turn_id: str
    text: str


class MessageCompleted(Wire):
    message: Message


class TurnCancelled(Wire):
    turn_id: str
    reason: Literal["interrupted", "error"]


class StateUpdated(Wire):
    update: StateVersion


class UserInvited(Wire):
    turn_id: str


class ErrorEvent(Wire):
    code: str
    message: str
    # True: control.resume (or sending another message) retries.
    recoverable: bool = True


class Empty(Wire):
    pass


SERVER_EVENTS: dict[str, type[Wire]] = {
    "session.snapshot": SessionSnapshot,
    "phase.changed": PhaseChanged,
    "status.changed": StatusChanged,
    "pace.changed": PaceChanged,
    "classroom.ready": ClassroomReady,
    "turn.started": ActiveTurn,
    "message.delta": MessageDelta,
    "message.completed": MessageCompleted,
    "turn.cancelled": TurnCancelled,
    "state.updated": StateUpdated,
    "user.invited": UserInvited,
    "error": ErrorEvent,
    "pong": Empty,
}


# --------------------------------------------------------------------------- client -> server


class TextInput(Wire):
    text: str = Field(max_length=8000)


class UserMessage(Wire):
    text: str = Field(max_length=8000)
    client_message_id: Optional[str] = Field(default=None, max_length=64)


class SetPace(Wire):
    auto: Optional[bool] = None
    speed: Optional[float] = Field(default=None, ge=0.25, le=4.0)


class UiEvent(Wire):
    """Logged only. Use it for interactions the server cannot see, such as
    opening a peer's knowledge-state panel."""

    name: str = Field(max_length=64)
    data: dict[str, Any] = {}


CLIENT_COMMANDS: dict[str, type[Wire]] = {
    "init.reply": TextInput,
    "init.finish": Empty,
    "discussion.start": Empty,
    "user.message": UserMessage,
    "control.pause": Empty,
    "control.resume": Empty,
    "control.step": Empty,
    "control.set_pace": SetPace,
    "session.end": Empty,
    "ui.event": UiEvent,
    "ping": Empty,
}


# --------------------------------------------------------------------------- REST


class CreateSessionRequest(Wire):
    topic: str = Field(min_length=1, max_length=300)
    language: Language = "ko"
    access_code: Optional[str] = None


class CreateSessionResponse(Wire):
    session_id: str
    snapshot: SessionSnapshot


# --------------------------------------------------------------------------- admin REST
# Everything under /api/admin needs "Authorization: Bearer <ADMIN_TOKEN>".


class AdminSessionRow(Wire):
    session_id: str
    topic: str
    created_at: float
    updated_at: float
    phase: Optional[Phase] = None
    message_count: int = 0
    event_count: int = 0
    llm_calls: int = 0
    # USD. Reported by OpenRouter where available, otherwise estimated from list prices.
    cost: float = 0.0
    # Loaded in this process right now (a client is connected or was recently).
    live: bool = False


class AdminSessionDetail(Wire):
    snapshot: SessionSnapshot
    # The pipeline's private state (session.scratch).
    scratch: dict[str, Any]
    live: bool


class UsageBucket(Wire):
    """LLM usage summed over a group of `llm.call` events (one model, one day, or all)."""

    key: str
    calls: int = 0
    errors: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    cost: float = 0.0
    # True if part of `cost` is estimated from list prices (the call reported no cost).
    estimated: bool = False
    # Calls with neither a reported cost nor a known price.
    unpriced_calls: int = 0
    avg_seconds: float = 0.0


class OpenRouterKeyInfo(Wire):
    """GET https://openrouter.ai/api/v1/key for the configured key. Amounts in USD."""

    label: Optional[str] = None
    usage: float = 0.0
    usage_daily: Optional[float] = None
    usage_weekly: Optional[float] = None
    usage_monthly: Optional[float] = None
    limit: Optional[float] = None
    limit_remaining: Optional[float] = None


class UsageReport(Wire):
    total: UsageBucket
    by_model: list[UsageBucket]
    # key = YYYY-MM-DD in the client's time zone (?tzOffset=minutes east of UTC), newest first.
    by_day: list[UsageBucket]
    openrouter: Optional[OpenRouterKeyInfo] = None
    openrouter_error: Optional[str] = None


class ModelConfig(Wire):
    pipeline: str
    # Effective model ids. model_fast is "" when the fast calls use `model`.
    model: str
    model_fast: str
    # Values from backend/.env.
    default_model: str
    default_model_fast: str
    # A runtime override (set from the admin page, stored in SQLite) is active.
    overridden: bool
    api_key_set: bool


class ModelConfigUpdate(Wire):
    # "" means: use the value from backend/.env.
    model: str = Field(default="", max_length=200)
    model_fast: str = Field(default="", max_length=200)


class ModelInfo(Wire):
    """One entry of the OpenRouter model list. Prices in USD per million tokens."""

    id: str
    name: str
    prompt_price: float
    completion_price: float
    context_length: Optional[int] = None


REST_MODELS: list[type[Wire]] = [
    CreateSessionRequest,
    CreateSessionResponse,
    AdminSessionRow,
    AdminSessionDetail,
    UsageReport,
    ModelConfig,
    ModelConfigUpdate,
    ModelInfo,
]
