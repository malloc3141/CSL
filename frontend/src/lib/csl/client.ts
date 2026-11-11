import { sessionSocketUrl } from "./api";
import type { ClientCommand, ErrorEvent, ServerEvent, SessionSnapshot } from "./protocol";
import { applyEvent } from "./reducer";

export type ConnectionState = "idle" | "connecting" | "open" | "reconnecting" | "closed";

export interface SessionClientState {
  /** null until the first snapshot arrives. */
  snapshot: SessionSnapshot | null;
  connection: ConnectionState;
  /** Last error event from the server; cleared when the session moves on. */
  error: ErrorEvent | null;
}

export const IDLE_STATE: SessionClientState = { snapshot: null, connection: "idle", error: null };

const CLEARS_ERROR = new Set<ServerEvent["type"]>([
  "session.snapshot",
  "turn.started",
  "message.completed",
  "classroom.ready",
  "phase.changed",
]);

/**
 * One WebSocket to one session. Reconnects with backoff; after every
 * (re)connect the server sends a full snapshot, so no events are missed.
 * Framework-free: subscribe() / getState() fit React's useSyncExternalStore.
 */
export class SessionClient {
  private state: SessionClientState = { ...IDLE_STATE };
  private listeners = new Set<() => void>();
  private socket: WebSocket | null = null;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private attempt = 0;
  private stopped = true;

  constructor(readonly sessionId: string) {}

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getState = (): SessionClientState => this.state;

  connect(): void {
    if (!this.stopped) return;
    this.stopped = false;
    this.attempt = 0;
    this.update({ connection: "connecting" });
    this.open();
  }

  close(): void {
    this.stopped = true;
    clearTimeout(this.timer);
    const socket = this.socket;
    this.socket = null;
    socket?.close();
    this.update({ connection: "closed" });
  }

  /** Returns false if the socket is not open (the command is dropped). */
  send(command: ClientCommand): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify(command));
    return true;
  }

  clearError(): void {
    if (this.state.error) this.update({ error: null });
  }

  private update(patch: Partial<SessionClientState>): void {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }

  private open(): void {
    const socket = new WebSocket(sessionSocketUrl(this.sessionId));
    this.socket = socket;
    socket.onopen = () => {
      this.attempt = 0;
      this.update({ connection: "open" });
    };
    socket.onmessage = (message) => {
      this.receive(JSON.parse(message.data as string) as ServerEvent);
    };
    socket.onclose = (event) => {
      if (this.socket !== socket) return;
      this.socket = null;
      if (this.stopped) return;
      if (event.code === 4403 || event.code === 4404) {
        // origin not allowed / no such session: retrying will not help
        this.stopped = true;
        this.update({ connection: "closed" });
        return;
      }
      this.attempt += 1;
      this.update({ connection: "reconnecting" });
      this.timer = setTimeout(() => this.open(), Math.min(500 * 2 ** this.attempt, 8000));
    };
  }

  private receive(event: ServerEvent): void {
    if (event.type === "pong") return;
    if (event.type === "error") {
      this.update({ error: event.data });
      return;
    }
    const snapshot = applyEvent(this.state.snapshot, event);
    const error = CLEARS_ERROR.has(event.type) ? null : this.state.error;
    if (snapshot !== this.state.snapshot || error !== this.state.error) this.update({ snapshot, error });
  }
}
