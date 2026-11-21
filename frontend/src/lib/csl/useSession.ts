"use client";

import { useEffect, useMemo, useSyncExternalStore } from "react";
import { IDLE_STATE, SessionClient } from "./client";
import type { SessionClientState } from "./client";
import type { Language, SetPace } from "./protocol";

const subscribeNothing = () => () => {};
const getIdleState = (): SessionClientState => IDLE_STATE;

/**
 * Live state of one session plus the commands the learner can send.
 *
 *   const { snapshot, connection, error, actions } = useCslSession(sessionId);
 *   snapshot.messages / snapshot.activeTurn / snapshot.states / snapshot.status ...
 *   actions.say("..."), actions.pause(), actions.setPace({ speed: 2 }) ...
 */
export function useCslSession(sessionId: string | null) {
  const client = useMemo(() => (sessionId ? new SessionClient(sessionId) : null), [sessionId]);

  useEffect(() => {
    client?.connect();
    return () => client?.close();
  }, [client]);

  const state = useSyncExternalStore(
    client ? client.subscribe : subscribeNothing,
    client ? client.getState : getIdleState,
    getIdleState,
  );

  const actions = useMemo(
    () => ({
      /** Initialization chat: answer the guide. */
      replyInit: (text: string) => client?.send({ type: "init.reply", data: { text } }),
      /** Skip the rest of the initialization chat and build the classroom. */
      finishInit: () => client?.send({ type: "init.finish" }),
      startDiscussion: (language?: Language) => client?.send({ type: "discussion.start", data: { language } }),
      /** Say something in the discussion. Allowed at any time; interrupts the agents. */
      say: (text: string, clientMessageId?: string) =>
        client?.send({ type: "user.message", data: { text, clientMessageId } }),
      pause: () => client?.send({ type: "control.pause" }),
      /** Continue after a pause or an error, or pass on the tutor's invitation. */
      resume: () => client?.send({ type: "control.resume" }),
      /** Show the next message now (the only way forward when pace.auto is false). */
      step: () => client?.send({ type: "control.step" }),
      setPace: (pace: SetPace) => client?.send({ type: "control.set_pace", data: pace }),
      end: () => client?.send({ type: "session.end" }),
      /** Log a UI interaction the server cannot see, e.g. track("panel.open", { agentId }). */
      track: (name: string, data: Record<string, unknown> = {}) =>
        client?.send({ type: "ui.event", data: { name, data } }),
      clearError: () => client?.clearError(),
    }),
    [client],
  );

  return { ...state, actions };
}
