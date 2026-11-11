// AUTO-GENERATED from backend/app/protocol.py by backend/scripts/gen_ts.py. Do not edit.

export const PROTOCOL_VERSION = 1;

export type Phase = "init" | "building" | "ready" | "discussion" | "ended";
export type Status = "running" | "paused" | "waiting_user";
export type Role = "system" | "tutor" | "peer" | "user";
export type Channel = "init" | "discussion";
export type Accuracy = "correct" | "partial" | "incorrect";
export type Language = "ko" | "en";

export interface SessionSnapshot {
  protocolVersion: number;
  sessionId: string;
  topic: string;
  language: Language;
  phase: Phase;
  status: Status;
  pace: Pace;
  participants: Participant[];
  focus: string | null;
  messages: Message[];
  states: Record<string, StateVersion[]>;
  activeTurn: ActiveTurn | null;
  invitedTurnId: string | null;
  turnLimit: number;
  lastSeq: number;
  createdAt: number;
}

export interface PhaseChanged {
  phase: Phase;
  reason: string | null;
}

export interface StatusChanged {
  status: Status;
}

export interface PaceChanged {
  pace: Pace;
}

export interface ClassroomReady {
  participants: Participant[];
  focus: string | null;
  states: Record<string, StateVersion>;
}

export interface ActiveTurn {
  turnId: string;
  channel: Channel;
  role: Role;
  speakerId: string;
  speakerName: string;
  peerIndex: number | null;
  text: string;
}

export interface MessageDelta {
  turnId: string;
  text: string;
}

export interface MessageCompleted {
  message: Message;
}

export interface TurnCancelled {
  turnId: string;
  reason: "interrupted" | "error";
}

export interface StateUpdated {
  update: StateVersion;
}

export interface UserInvited {
  turnId: string;
}

export interface ErrorEvent {
  code: string;
  message: string;
  recoverable: boolean;
}

export type Empty = Record<string, never>;

export interface TextInput {
  text: string;
}

export interface UserMessage {
  text: string;
  clientMessageId?: string | null;
}

export interface SetPace {
  auto?: boolean | null;
  speed?: number | null;
}

export interface UiEvent {
  name: string;
  data?: Record<string, unknown>;
}

export interface CreateSessionRequest {
  topic: string;
  language?: Language;
  accessCode?: string | null;
}

export interface CreateSessionResponse {
  sessionId: string;
  snapshot: SessionSnapshot;
}

export interface Pace {
  auto: boolean;
  speed: number;
}

export interface Participant {
  id: string;
  role: "tutor" | "peer";
  name: string;
  peerIndex: number | null;
  origin: string | null;
  description: string | null;
}

export interface Message {
  id: string;
  channel: Channel;
  role: Role;
  speakerId: string;
  speakerName: string;
  peerIndex: number | null;
  text: string;
  turnNumber: number | null;
  invited: boolean;
  clientMessageId: string | null;
  meta: Record<string, unknown>;
  createdAt: number;
}

export interface StateVersion {
  agentId: string;
  version: number;
  turnId: string | null;
  turnNumber: number | null;
  state: KnowledgeState;
  changes: StateChange[];
  createdAt: number;
}

export interface KnowledgeState {
  beliefs: Belief[];
  explanation: string;
  explanationAccuracy: Accuracy | null;
  openQuestions: string[];
}

export interface StateChange {
  field: "beliefs" | "explanation" | "openQuestions";
  kind: "added" | "removed" | "modified";
  before: string | null;
  after: string | null;
  beliefId: string | null;
}

export interface Belief {
  id: string;
  text: string;
  accuracy: Accuracy | null;
}

/** Everything the server sends over the WebSocket. `seq` is null for events that are not logged. */
export type ServerEvent =
  | { type: "session.snapshot"; seq: number | null; ts: number; data: SessionSnapshot }
  | { type: "phase.changed"; seq: number | null; ts: number; data: PhaseChanged }
  | { type: "status.changed"; seq: number | null; ts: number; data: StatusChanged }
  | { type: "pace.changed"; seq: number | null; ts: number; data: PaceChanged }
  | { type: "classroom.ready"; seq: number | null; ts: number; data: ClassroomReady }
  | { type: "turn.started"; seq: number | null; ts: number; data: ActiveTurn }
  | { type: "message.delta"; seq: number | null; ts: number; data: MessageDelta }
  | { type: "message.completed"; seq: number | null; ts: number; data: MessageCompleted }
  | { type: "turn.cancelled"; seq: number | null; ts: number; data: TurnCancelled }
  | { type: "state.updated"; seq: number | null; ts: number; data: StateUpdated }
  | { type: "user.invited"; seq: number | null; ts: number; data: UserInvited }
  | { type: "error"; seq: number | null; ts: number; data: ErrorEvent }
  | { type: "pong"; seq: number | null; ts: number; data: Empty };

/** Everything the client may send over the WebSocket. */
export type ClientCommand =
  | { type: "init.reply"; data: TextInput }
  | { type: "init.finish"; data?: Empty }
  | { type: "discussion.start"; data?: Empty }
  | { type: "user.message"; data: UserMessage }
  | { type: "control.pause"; data?: Empty }
  | { type: "control.resume"; data?: Empty }
  | { type: "control.step"; data?: Empty }
  | { type: "control.set_pace"; data: SetPace }
  | { type: "session.end"; data?: Empty }
  | { type: "ui.event"; data: UiEvent }
  | { type: "ping"; data?: Empty };
