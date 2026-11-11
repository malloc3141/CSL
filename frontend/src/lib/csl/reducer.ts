import type { ServerEvent, SessionSnapshot } from "./protocol";

/**
 * Applies one server event to the session snapshot and returns the new
 * snapshot. Pure, so it works with useReducer, a store, or in tests.
 * `error` and `pong` do not change the snapshot.
 */
export function applyEvent(state: SessionSnapshot | null, event: ServerEvent): SessionSnapshot | null {
  if (event.type === "session.snapshot") return event.data;
  if (!state) return state;

  switch (event.type) {
    case "phase.changed":
      return event.data.phase === "ended"
        ? { ...state, phase: "ended", activeTurn: null, invitedTurnId: null }
        : { ...state, phase: event.data.phase };

    case "status.changed":
      return {
        ...state,
        status: event.data.status,
        invitedTurnId: event.data.status === "waiting_user" ? state.invitedTurnId : null,
      };

    case "pace.changed":
      return { ...state, pace: event.data.pace };

    case "classroom.ready":
      return {
        ...state,
        participants: event.data.participants,
        focus: event.data.focus,
        states: Object.fromEntries(Object.entries(event.data.states).map(([id, version]) => [id, [version]])),
      };

    case "turn.started":
      return { ...state, activeTurn: { ...event.data, text: "" } };

    case "message.delta": {
      const turn = state.activeTurn;
      if (!turn || turn.turnId !== event.data.turnId) return state;
      return { ...state, activeTurn: { ...turn, text: turn.text + event.data.text } };
    }

    case "message.completed": {
      const message = event.data.message;
      if (state.messages.some((m) => m.id === message.id)) return state;
      return {
        ...state,
        messages: [...state.messages, message],
        activeTurn: state.activeTurn?.turnId === message.id ? null : state.activeTurn,
      };
    }

    case "turn.cancelled":
      return state.activeTurn?.turnId === event.data.turnId ? { ...state, activeTurn: null } : state;

    case "state.updated": {
      const update = event.data.update;
      const versions = state.states[update.agentId] ?? [];
      if (versions.some((v) => v.version === update.version)) return state;
      return { ...state, states: { ...state.states, [update.agentId]: [...versions, update] } };
    }

    case "user.invited":
      return { ...state, status: "waiting_user", invitedTurnId: event.data.turnId };

    default:
      return state;
  }
}
