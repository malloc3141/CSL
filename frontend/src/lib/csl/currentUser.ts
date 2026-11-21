"use client";

// Who is signed in on this browser. Login is a nickname only (backend/app/users.py): it identifies
// the learner and lets them find their sessions again from any browser. It is not access control.
//
//   const user = useCurrentUser();        // undefined while hydrating, null = signed out
//   await signIn("minsu");                // api.ts: creates the user if the nickname is new
//   signOut();
//
// createSession() attaches the signed-in user by itself, and fetchUserSessions(user.userId) lists
// their sessions for a "continue where you left off" screen.

import { useSyncExternalStore } from "react";
import type { User } from "./protocol";

const KEY = "csl.user";
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener); // signed in or out in another tab
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

let cachedRaw: string | null = null;
let cached: User | null = null;

/** The signed-in user, or null. Only call in the browser (event handlers, effects, fetch helpers). */
export function getCurrentUser(): User | null {
  let raw: string | null = null;
  try {
    raw = localStorage.getItem(KEY);
  } catch {
    // storage unavailable: nobody is signed in
  }
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    try {
      const parsed = raw ? (JSON.parse(raw) as Partial<User>) : null;
      cached = parsed && typeof parsed.userId === "string" && typeof parsed.name === "string" ? (parsed as User) : null;
    } catch {
      cached = null;
    }
  }
  return cached;
}

export function setCurrentUser(user: User | null): void {
  try {
    if (user) localStorage.setItem(KEY, JSON.stringify(user));
    else localStorage.removeItem(KEY);
  } catch {
    // storage unavailable: the login cannot be remembered
  }
  listeners.forEach((listener) => listener());
}

export function signOut(): void {
  setCurrentUser(null);
}

/**
 * The signed-in user. `undefined` during server rendering and hydration (not known yet: render a
 * placeholder), `null` when nobody is signed in.
 */
export function useCurrentUser(): User | null | undefined {
  return useSyncExternalStore(subscribe, getCurrentUser, () => undefined);
}
