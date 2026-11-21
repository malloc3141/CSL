import { getCurrentUser, setCurrentUser, signOut } from "./currentUser";
import type {
  CreateSessionRequest,
  CreateSessionResponse,
  Health,
  LoginResponse,
  SessionSnapshot,
  SessionSummary,
  User,
} from "./protocol";

/** Backend origin, e.g. https://api.example.com. Set NEXT_PUBLIC_CSL_API_URL in .env.local. */
export const API_URL = (process.env.NEXT_PUBLIC_CSL_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export function sessionSocketUrl(sessionId: string): string {
  return `${API_URL.replace(/^http/, "ws")}/ws/sessions/${sessionId}`;
}

/** A request the server answered with an error. `message` is the server's `detail`. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : `HTTP ${response.status}`;
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

/** The stored login points at a user the server does not know (any more): forget it. */
function forgetUnknownUser(cause: unknown): never {
  if (cause instanceof ApiError && cause.status === 404 && /unknown user/i.test(cause.message)) signOut();
  throw cause;
}

/**
 * Create a session. If someone is signed in (useCurrentUser), the session is recorded as theirs;
 * pass `userId: null` to create one without a user.
 */
export async function createSession(request: CreateSessionRequest): Promise<CreateSessionResponse> {
  const userId = request.userId === undefined ? (getCurrentUser()?.userId ?? null) : request.userId;
  const response = await fetch(`${API_URL}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...request, userId }),
  });
  return readJson<CreateSessionResponse>(response).catch(forgetUnknownUser);
}

/** The server's default pipeline and the pipelines a session can ask for by name. */
export async function fetchHealth(): Promise<Health> {
  return readJson<Health>(await fetch(`${API_URL}/api/health`, { cache: "no-store" }));
}

export async function fetchSession(sessionId: string): Promise<SessionSnapshot> {
  return readJson<SessionSnapshot>(await fetch(`${API_URL}/api/sessions/${sessionId}`));
}

/**
 * Sign in with a nickname (2 to 20 characters). A new nickname creates the user; a known one signs
 * in as that user. The result is remembered in this browser (useCurrentUser).
 */
export async function signIn(name: string): Promise<LoginResponse> {
  const response = await fetch(`${API_URL}/api/users/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  const result = await readJson<LoginResponse>(response);
  setCurrentUser(result.user);
  return result;
}

/** Every session the user created while signed in, newest first. */
export async function fetchUserSessions(userId: User["userId"]): Promise<SessionSummary[]> {
  const response = await fetch(`${API_URL}/api/users/${encodeURIComponent(userId)}/sessions`, { cache: "no-store" });
  return readJson<SessionSummary[]>(response).catch(forgetUnknownUser);
}
