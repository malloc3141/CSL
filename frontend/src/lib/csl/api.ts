import type { CreateSessionRequest, CreateSessionResponse, SessionSnapshot } from "./protocol";

/** Backend origin, e.g. https://api.example.com. Set NEXT_PUBLIC_CSL_API_URL in .env.local. */
export const API_URL = (process.env.NEXT_PUBLIC_CSL_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export function sessionSocketUrl(sessionId: string): string {
  return `${API_URL.replace(/^http/, "ws")}/ws/sessions/${sessionId}`;
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export async function createSession(request: CreateSessionRequest): Promise<CreateSessionResponse> {
  const response = await fetch(`${API_URL}/api/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  return readJson<CreateSessionResponse>(response);
}

export async function fetchSession(sessionId: string): Promise<SessionSnapshot> {
  return readJson<SessionSnapshot>(await fetch(`${API_URL}/api/sessions/${sessionId}`));
}
