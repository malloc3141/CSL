"use client";

// Which session this browser tab is in, without a login.
//
// * The current session id lives in the URL (?session=<id>): a reload, the back button or a shared
//   link all lead back to the same session. The server keeps every session and sends the full
//   snapshot on connect, so the id is all a page has to remember.
// * The sessions this browser started are listed in localStorage, so that a page can offer
//   "continue where you left off" after the tab was closed.
//
//   const sessionId = useCurrentSessionId();          // undefined | null | "<id>"
//   const { snapshot, actions } = useCslSession(sessionId ?? null);
//   setCurrentSessionId(created.sessionId);            // after createSession()
//   setCurrentSessionId(null);                         // leave (the session pauses and can be resumed)

import { useSyncExternalStore } from "react";

const PARAM = "session";
const RECENT_KEY = "csl.recentSessions";
const RECENT_MAX = 8;

export interface RecentSession {
  sessionId: string;
  topic: string;
  pipeline: string;
  /** Seconds since the epoch (snapshot.createdAt). */
  createdAt: number;
}

const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("popstate", listener); // back / forward
  window.addEventListener("storage", listener); // the list changed in another tab
  return () => {
    listeners.delete(listener);
    window.removeEventListener("popstate", listener);
    window.removeEventListener("storage", listener);
  };
}

function readId(): string | null {
  return new URLSearchParams(window.location.search).get(PARAM);
}

/** Put a session id in the URL (new history entry), or remove it with null. */
export function setCurrentSessionId(sessionId: string | null): void {
  const url = new URL(window.location.href);
  if (sessionId) url.searchParams.set(PARAM, sessionId);
  else url.searchParams.delete(PARAM);
  window.history.pushState(null, "", url);
  notify();
}

/**
 * The session id in the URL. `undefined` during server rendering and hydration (not known yet:
 * render a placeholder), `null` when the URL names no session.
 */
export function useCurrentSessionId(): string | null | undefined {
  return useSyncExternalStore(subscribe, readId, () => undefined);
}

const NONE: RecentSession[] = [];
let recentRaw: string | null = null;
let recent: RecentSession[] = NONE;

function readRecent(): RecentSession[] {
  let raw: string | null = null;
  try {
    raw = localStorage.getItem(RECENT_KEY);
  } catch {
    // storage unavailable: no list
  }
  if (raw !== recentRaw) {
    recentRaw = raw;
    try {
      const parsed: unknown = raw ? JSON.parse(raw) : [];
      recent = Array.isArray(parsed) ? (parsed as RecentSession[]) : NONE;
    } catch {
      recent = NONE;
    }
  }
  return recent;
}

function writeRecent(list: RecentSession[]): void {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, RECENT_MAX)));
  } catch {
    // storage unavailable: nothing is remembered
  }
  notify();
}

/** Add a session to this browser's list (newest first). Call it after createSession(). */
export function rememberSession(session: RecentSession): void {
  writeRecent([session, ...readRecent().filter((item) => item.sessionId !== session.sessionId)]);
}

export function forgetSession(sessionId: string): void {
  writeRecent(readRecent().filter((item) => item.sessionId !== sessionId));
}

/** Sessions this browser started, newest first. Empty during server rendering. */
export function useRecentSessions(): RecentSession[] {
  return useSyncExternalStore(subscribe, readRecent, () => NONE);
}
