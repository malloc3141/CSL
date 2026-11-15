// Client for the admin API (backend/app/admin.py). Every call needs the server's ADMIN_TOKEN.

import { API_URL } from "./api";
import type {
  AdminSessionDetail,
  AdminSessionRow,
  ModelConfig,
  ModelConfigUpdate,
  ModelInfo,
  UsageReport,
} from "./protocol";

/** One row of the event log (`events` table). `data` is the event payload as stored. */
export interface AdminEvent {
  seq: number;
  ts: number;
  type: string;
  data: Record<string, unknown>;
}

/** The token was rejected (401) or the admin API is off on the server (ADMIN_TOKEN empty -> 404). */
export class AdminAuthError extends Error {}

async function adminFetch<T>(token: string, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}/api/admin${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (response.status === 401) throw new AdminAuthError("Wrong admin token.");
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    if (response.status === 404 && body?.detail === "Not Found") {
      throw new AdminAuthError("The admin API is off: ADMIN_TOKEN is not set on the server.");
    }
    throw new Error(typeof body?.detail === "string" ? body.detail : `HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export const adminApi = {
  config: (token: string) => adminFetch<ModelConfig>(token, "/config"),
  updateConfig: (token: string, update: ModelConfigUpdate) =>
    adminFetch<ModelConfig>(token, "/config", { method: "PUT", body: JSON.stringify(update) }),
  models: (token: string, refresh = false) =>
    adminFetch<ModelInfo[]>(token, `/models${refresh ? "?refresh=true" : ""}`),
  /** tzOffset: minutes east of UTC, so that `byDay` uses the viewer's dates. */
  usage: (token: string, tzOffset = -new Date().getTimezoneOffset()) =>
    adminFetch<UsageReport>(token, `/usage?tzOffset=${tzOffset}`),
  sessions: (token: string) => adminFetch<AdminSessionRow[]>(token, "/sessions"),
  session: (token: string, sessionId: string) =>
    adminFetch<AdminSessionDetail>(token, `/sessions/${encodeURIComponent(sessionId)}`),
  events: (token: string, sessionId: string) =>
    adminFetch<AdminEvent[]>(token, `/sessions/${encodeURIComponent(sessionId)}/events`),
};
