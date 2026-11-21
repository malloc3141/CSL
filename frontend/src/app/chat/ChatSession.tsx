"use client";

import { useI18n } from "@/i18n";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Pause, Play, SkipForward, X } from "lucide-react";
import styled from "styled-components";
import { Button, Composer, MessageBubble, Navbar } from "@/common/components";
import { useCslSession, useCurrentSessionId } from "@/lib/csl";
import type { Accuracy, KnowledgeState, SessionSnapshot, StateChange } from "@/lib/csl";
import { peerColor } from "@/styles/peerColors";

const Screen = styled.div`
  display: flex;
  flex-direction: column;
  height: 100dvh;
  background: ${({ theme }) => theme.colors.WHITE};
`;

const Classroom = styled.main<{ $panelOpen: boolean }>`
  display: grid;
  grid-template-columns: 150px minmax(0, 1fr) ${({ $panelOpen }) => $panelOpen && "300px"};
  grid-template-rows: auto minmax(0, 1fr);
  flex: 1;
  min-height: 0;
  @media (max-width: 1000px) {
    grid-template-columns: 130px minmax(0, 1fr) ${({ $panelOpen }) => $panelOpen && "240px"};
  }
  @media (max-width: 760px) {
    grid-template-columns: 110px minmax(0, 1fr);
    grid-template-rows: auto minmax(320px, 1fr) ${({ $panelOpen }) => $panelOpen && "auto"};
    overflow-y: auto;
  }
`;

const Sidebar = styled.aside`
  grid-row: 1 / -1;
  padding: 20px 12px;
  border-right: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  background: ${({ theme }) => theme.colors.GRAY[100]};
  h2 { margin: 0 0 24px; font-size: 16px; }
  h3 { margin: 0 0 12px; font-size: 14px; }
`;

const Participants = styled.div`
  display: flex;
  flex-direction: column;
  gap: 8px;
`;

const Participant = styled.button<{ $index: number; $selected: boolean }>`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 12px;
  border: 1px solid ${({ theme, $selected }) => $selected ? theme.colors.SLATE[600] : theme.colors.GRAY[200]};
  border-radius: ${({ theme }) => theme.round.sm};
  background: ${({ theme, $index }) => $index < 0 ? theme.colors.BLUE[50] : peerColor(theme, $index)[50]};
  color: ${({ theme }) => theme.colors.GRAY[900]};
  text-align: left;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  &:focus-visible {
    outline: 2px solid ${({ theme }) => theme.colors.SLATE[600]};
    outline-offset: 2px;
  }
`;

const Goal = styled.header`
  grid-column: 2 / -1;
  padding: 18px 24px;
  border-bottom: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  h1 { margin: 0 0 8px; font-size: 16px; }
  p { margin: 0; font-size: 15px; overflow-wrap: anywhere; }
`;

const Conversation = styled.section`
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  padding: 20px 24px 16px;
  gap: 20px;
  @media (max-width: 760px) { padding: 16px 12px; }
`;

const Controls = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px 16px;
  button { display: inline-flex; align-items: center; gap: 8px; }
`;

const ControlGroup = styled.div<{ $end?: boolean }>`
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-left: ${({ $end }) => $end ? "auto" : "0"};
  font-size: 13px;
`;

const Check = styled.label`
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: ${({ theme }) => theme.colors.GRAY[900]};
  font-size: 13px;
  cursor: pointer;
  input { margin: 0; }
`;

const Speed = styled.button<{ $on: boolean }>`
  padding: 6px 8px;
  border: 1px solid ${({ theme, $on }) => $on ? theme.colors.SLATE[600] : theme.colors.GRAY[200]};
  border-radius: ${({ theme }) => theme.round.sm};
  background: ${({ theme, $on }) => $on ? theme.colors.SLATE[600] : theme.colors.WHITE};
  color: ${({ theme, $on }) => $on ? theme.colors.WHITE : theme.colors.GRAY[900]};
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  &:disabled { cursor: not-allowed; opacity: 0.5; }
`;

const Status = styled.span<{ $paused: boolean }>`
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: ${({ theme, $paused }) => $paused ? theme.colors.GRAY[500] : theme.colors.GREEN[700]};
  font-size: 13px;
  font-weight: 600;
  &::before {
    content: "";
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: currentColor;
  }
`;

const Messages = styled.div`
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-wrap: anywhere;
`;

const MessageList = styled.div`
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  min-height: 100%;
  gap: 20px;
  padding: 4px;
`;

const ChatLine = styled.div<{ $own?: boolean; $flash?: boolean }>`
  display: flex;
  justify-content: ${({ $own }) => $own ? "flex-end" : "flex-start"};
  border-radius: ${({ theme }) => theme.round.md};
  outline: 2px solid ${({ theme, $flash }) => $flash ? theme.colors.SLATE[600] : "transparent"};
  outline-offset: 4px;
  transition: outline-color 0.3s;
`;

const Stack = styled.div<{ $own?: boolean }>`
  display: flex;
  flex-direction: column;
  align-items: ${({ $own }) => $own ? "flex-end" : "flex-start"};
  gap: 6px;
`;

// Under a message: whose understanding changed because of it. Opens that participant's panel.
const StateChip = styled.button`
  padding: 0;
  border: 0;
  background: none;
  color: ${({ theme }) => theme.colors.SLATE[600]};
  font-size: 12px;
  font-weight: 600;
  text-decoration: underline;
  cursor: pointer;
`;

const Dot = styled.span`
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: ${({ theme }) => theme.colors.SLATE[600]};
`;

const Understanding = styled.aside`
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
  padding: 20px;
  border-left: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  background: #f8f5df;
  &[hidden] { display: none; }
  h3 { margin: 0 0 16px; font-size: 16px; }
  h4 { margin: 20px 0 8px; font-size: 13px; }
  p { margin: 0; font-size: 14px; line-height: 1.6; }
  ul { margin: 0; padding-left: 18px; font-size: 14px; line-height: 1.6; }
  @media (max-width: 760px) {
    grid-column: 2;
    min-height: 180px;
    border-top: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
    border-left: 0;
  }
`;

const PanelHeader = styled.header`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 20px;

  h2 { margin: 0; font-size: 16px; }
  button { display: inline-flex; align-items: center; padding: 6px; }
`;

const PanelNote = styled.p`
  && {
    margin-bottom: 12px;
    color: ${({ theme }) => theme.colors.SLATE[600]};
    font-size: 12px;
  }
`;

const TurnLink = styled.button`
  padding: 0;
  border: 0;
  background: none;
  color: ${({ theme }) => theme.colors.BLUE[900]};
  font-size: 13px;
  font-weight: 600;
  text-align: left;
  text-decoration: underline;
  cursor: pointer;
`;

const AccuracyTag = styled.span<{ $accuracy: Accuracy }>`
  display: inline-block;
  margin-left: 6px;
  padding: 0 6px;
  border: 1px solid currentColor;
  border-radius: ${({ theme }) => theme.round.sm};
  background: ${({ theme, $accuracy }) =>
    theme.colors[$accuracy === "incorrect" ? "ROSE" : $accuracy === "partial" ? "YELLOW" : "GREEN"][50]};
  color: ${({ theme, $accuracy }) =>
    theme.colors[$accuracy === "incorrect" ? "ROSE" : $accuracy === "partial" ? "YELLOW" : "GREEN"][900]};
  font-size: 11px;
  font-weight: 600;
  line-height: 1.6;
  white-space: nowrap;
`;

const Changes = styled.ul`
  && { padding-left: 0; list-style: none; }
  li + li { margin-top: 10px; }
  strong { display: block; font-size: 12px; }
  del { display: block; color: ${({ theme }) => theme.colors.GRAY[500]}; }
  ins { display: block; text-decoration: none; }
`;

const History = styled.details`
  margin-top: 20px;
  summary { font-size: 13px; font-weight: 600; cursor: pointer; }
`;

const Earlier = styled.div`
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  h4 { margin-top: 12px; }
`;

const Options = styled.div`
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: auto;
  padding-top: 16px;
`;

const EmptyState = styled.p`
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: ${({ theme }) => theme.colors.SLATE[600]};
`;

const Notice = styled.p`
  margin: 0;
  color: ${({ theme }) => theme.colors.ROSE[900]};
  font-size: 13px;
`;

const Fallback = styled.main`
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 24px;
`;

const SPEEDS = [0.5, 1, 1.5, 2];

const CHANGED_FIELD = {
  explanation: "understanding",
  beliefs: "belief",
  openQuestions: "openQuestion",
} as const satisfies Record<StateChange["field"], string>;
const CHANGED_KIND = { added: "added", removed: "dropped", modified: "revised" } as const;

// What this browser remembers about how the learner likes to read the classroom.
type Prefs = { showAccuracy: boolean; pauseOnPanel: boolean };
const PREFS_KEY = "csl.classroomPrefs";
const DEFAULT_PREFS: Prefs = { showAccuracy: true, pauseOnPanel: false };

function readPrefs(): Prefs {
  try {
    return { ...DEFAULT_PREFS, ...(JSON.parse(localStorage.getItem(PREFS_KEY) ?? "{}") as Partial<Prefs>) };
  } catch {
    return DEFAULT_PREFS; // no storage (or the server render): the defaults
  }
}

function latestVersions(snapshot: SessionSnapshot): Record<string, number> {
  return Object.fromEntries(
    Object.entries(snapshot.states).map(([id, versions]) => [id, versions[versions.length - 1]?.version ?? 0]),
  );
}

function Mark({ accuracy, show }: { accuracy: Accuracy | null; show: boolean }) {
  const { t } = useI18n();
  return show && accuracy ? <AccuracyTag $accuracy={accuracy}>{t(accuracy)}</AccuracyTag> : null;
}

function StateBody({ state, label, showAccuracy }: { state: KnowledgeState; label: string; showAccuracy: boolean }) {
  const { t } = useI18n();
  return (
    <>
      <h4>{label}</h4>
      <p>
        {state.explanation || "—"}
        <Mark accuracy={state.explanationAccuracy} show={showAccuracy} />
      </p>
      {state.beliefs.length > 0 ? (
        <>
          <h4>{t("beliefs")}</h4>
          <ul>
            {state.beliefs.map((belief) => (
              <li key={belief.id}>
                {belief.text}
                <Mark accuracy={belief.accuracy} show={showAccuracy} />
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </>
  );
}

// The classroom runs on the session named in the URL (?session=<id>). Leaving the page pauses the
// discussion on the server; opening the same link (or "Continue" on My page) picks it up again.
export function ChatSession() {
  const { t } = useI18n();
  const router = useRouter();
  const sessionId = useCurrentSessionId();
  const { snapshot, connection, error, actions } = useCslSession(sessionId ?? null);
  const [draft, setDraft] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const [prefs, setPrefs] = useState<Prefs>(readPrefs);
  // The state version of each participant the learner has looked at; a newer one shows a dot in the list.
  const [seen, setSeen] = useState<Record<string, number> | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const phase = snapshot?.phase ?? null;
  const status = snapshot?.status ?? null;
  const messages = snapshot ? snapshot.messages.filter((message) => message.channel === "discussion") : [];
  const active = snapshot?.activeTurn?.channel === "discussion" ? snapshot.activeTurn : null;
  const messageCount = messages.length;
  const activeText = active?.text ?? null;

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "nearest" });
  }, [messageCount, activeText]);

  // A session that is still being set up belongs on the start page.
  useEffect(() => {
    if (sessionId && (phase === "init" || phase === "building" || phase === "ready")) {
      router.replace(`/?session=${encodeURIComponent(sessionId)}`);
    }
  }, [phase, sessionId, router]);

  // Whatever had already changed when the page opened is not news.
  if (snapshot && seen === null) setSeen(latestVersions(snapshot));

  if (sessionId === null || (sessionId && !snapshot && connection === "closed")) {
    return (
      <Screen>
        <Navbar />
        <Fallback>
          <EmptyState>
            {sessionId === null ? t("noSession") : t("openError")}
          </EmptyState>
          <Button onClick={() => router.push("/")}>{t("startLearningLink")}</Button>
        </Fallback>
      </Screen>
    );
  }

  const participants = snapshot?.participants ?? [];
  const person = participants.find((participant) => participant.id === selected) ?? null;
  const versions = person && snapshot ? snapshot.states[person.id] : undefined;
  const current = versions?.[versions.length - 1];
  const earlier = versions ? versions.slice(0, -1).reverse() : [];
  const pace = snapshot?.pace ?? null;

  const ended = phase === "ended";
  const waiting = status === "waiting_user";
  const running = phase === "discussion" && status === "running" && connection === "open";

  const versionOf = (id: string) => {
    const all = snapshot?.states[id];
    return all?.[all.length - 1]?.version ?? 0;
  };
  // Which participants changed their understanding because of which message.
  const changedBy = new Map<string, string[]>();
  for (const [id, all] of Object.entries(snapshot?.states ?? {})) {
    for (const version of all) {
      if (version.version > 0 && version.turnId) {
        changedBy.set(version.turnId, [...(changedBy.get(version.turnId) ?? []), id]);
      }
    }
  }

  const setPref = (change: Partial<Prefs>) => {
    const next = { ...prefs, ...change };
    setPrefs(next);
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify(next));
    } catch {
      // storage unavailable: the choice lasts until the page is closed
    }
    actions.track("prefs.change", change);
  };

  const openPanel = (id: string, from: "list" | "message") => {
    setSeen({ ...(seen ?? {}), ...(selected ? { [selected]: versionOf(selected) } : {}), [id]: versionOf(id) });
    setSelected(id);
    setPanelOpen(true);
    actions.track("panel.open", { agentId: id, from });
    if (prefs.pauseOnPanel && running) actions.pause();
  };

  const closePanel = () => {
    if (selected) setSeen((previous) => ({ ...previous, [selected]: versionOf(selected) }));
    setSelected(null);
    setPanelOpen(false);
  };

  // "Updated after turn N" in the panel leads to the message that caused the change.
  const jumpTo = (turnId: string | null) => {
    if (!turnId) return;
    document.getElementById(`turn-${turnId}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    setFlash(turnId);
    window.setTimeout(() => setFlash((shown) => (shown === turnId ? null : shown)), 2500);
    actions.track("state.jump", { turnId });
  };
  const statusLabel = !snapshot
    ? t("opening")
    : ended
      ? t("finished")
      : connection !== "open"
        ? t("reconnecting")
        : waiting
          ? t("waitingExplanation")
          : running
            ? pace && !pace.auto && !active
              ? t("nextToContinue")
              : t("inProgress")
            : phase === "ready"
              ? t("starting")
              : t("paused");

  return (
    <Screen>
      <Navbar />
      <Classroom $panelOpen={panelOpen}>
        <Sidebar aria-label={t("classroomParticipants")}>
          <h2>{t("classroom")}</h2>
          <h3>{t("participants")}</h3>
          <Participants>
            {participants.map((participant) => (
              <Participant
                key={participant.id}
                type="button"
                $index={participant.role === "tutor" ? -1 : (participant.peerIndex ?? 0)}
                $selected={selected === participant.id}
                aria-pressed={selected === participant.id}
                onClick={() => openPanel(participant.id, "list")}
              >
                {participant.name}
                {participant.id !== selected && versionOf(participant.id) > (seen?.[participant.id] ?? 0) ? (
                  <Dot role="img" aria-label={t("updatedLower")} title={t("updated")} />
                ) : null}
              </Participant>
            ))}
          </Participants>
        </Sidebar>
        <Goal>
          <h1>{t("learningGoal")}</h1>
          <p>{snapshot?.focus ?? snapshot?.topic ?? "…"}</p>
        </Goal>
        <Conversation aria-label={t("studyConversation")}>
          <Controls>
            {phase === "discussion" && pace ? (
              <ControlGroup role="group" aria-label={t("pace")}>
                <Check title={t("autoAdvanceHint")}>
                  <input
                    type="checkbox"
                    checked={pace.auto}
                    onChange={(event) => actions.setPace({ auto: event.target.checked })}
                  />
                  {t("autoAdvance")}
                </Check>
                {SPEEDS.map((speed) => (
                  <Speed
                    key={speed}
                    type="button"
                    $on={pace.speed === speed}
                    aria-pressed={pace.speed === speed}
                    disabled={!pace.auto}
                    title={t("speedHint")}
                    onClick={() => actions.setPace({ speed })}
                  >
                    {speed}×
                  </Speed>
                ))}
                <Button variant="ghost" disabled={connection !== "open"} onClick={actions.step}>
                  {t("nextMessage")}
                  <SkipForward size={16} aria-hidden="true" />
                </Button>
              </ControlGroup>
            ) : null}
            <ControlGroup $end>
            <Status $paused={!running} role="status">
              {statusLabel}
            </Status>
            {ended ? (
              <Button variant="ghost" onClick={() => router.push("/")}>
                {t("newSession")}
              </Button>
            ) : running ? (
              <Button variant="ghost" onClick={actions.pause}>
                {t("pauseDiscussion")}
                <Pause size={16} aria-hidden="true" />
              </Button>
            ) : (
              <Button variant="ghost" disabled={!snapshot || connection !== "open"} onClick={actions.resume}>
                {waiting ? t("skipForNow") : t("resumeDiscussion")}
                <Play size={16} aria-hidden="true" />
              </Button>
            )}
            </ControlGroup>
          </Controls>
          {error ? <Notice role="alert">{error.message} {t("resumeHint")}</Notice> : null}
          <Messages role="log" aria-label={t("messages")} aria-live="polite">
            <MessageList>
              {messages.map((message) => (
                <ChatLine
                  key={message.id}
                  id={`turn-${message.id}`}
                  $own={message.role === "user"}
                  $flash={flash === message.id}
                >
                  <Stack $own={message.role === "user"}>
                    <MessageBubble
                      role={message.role}
                      peerIndex={message.peerIndex ?? 0}
                      speaker={`${message.turnNumber ?? ""} · ${message.speakerName}`}
                    >
                      {message.text}
                    </MessageBubble>
                    {(changedBy.get(message.id) ?? []).map((id) => (
                      <StateChip key={id} type="button" onClick={() => openPanel(id, "message")}>
                        {t("understandingChanged", { name: participants.find((participant) => participant.id === id)?.name ?? id })}
                      </StateChip>
                    ))}
                  </Stack>
                </ChatLine>
              ))}
              {active ? (
                <ChatLine>
                  <MessageBubble role={active.role} peerIndex={active.peerIndex ?? 0} speaker={active.speakerName}>
                    {active.text || "…"}
                  </MessageBubble>
                </ChatLine>
              ) : null}
              <div ref={bottom} />
            </MessageList>
          </Messages>
          <Composer
            value={draft}
            onChange={setDraft}
            placeholder={waiting ? t("explainUnderstanding") : t("joinDiscussion")}
            disabled={!snapshot || ended || connection !== "open"}
            onSubmit={() => {
              if (!draft.trim()) return;
              actions.say(draft.trim());
              setDraft("");
            }}
          />
        </Conversation>
        <Understanding aria-label={t("participantUnderstanding")} hidden={!panelOpen}>
          <PanelHeader>
            <h2>{t("understanding")}</h2>
            <Button type="button" variant="ghost" aria-label={t("closeUnderstanding")} onClick={closePanel}>
              <X size={18} aria-hidden="true" />
            </Button>
          </PanelHeader>
          {person ? (
            <div aria-live="polite">
              <h3>{person.name}</h3>
              {current ? (
                <>
                  <PanelNote>
                    {t("peerNotice")}
                  </PanelNote>
                  {current.version === 0 ? (
                    <p>{t("initialUnchanged")}</p>
                  ) : (
                    <TurnLink type="button" onClick={() => jumpTo(current.turnId)}>
                      {t("updatedAfterTurn", { turn: current.turnNumber ?? "?" })}
                    </TurnLink>
                  )}
                  <StateBody state={current.state} label={t("currentUnderstanding")} showAccuracy={prefs.showAccuracy} />
                  <h4>{t("openQuestion")}</h4>
                  {current.state.openQuestions.length > 0 ? (
                    <ul>
                      {current.state.openQuestions.map((question) => (
                        <li key={question}>{question}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>{t("noQuestions")}</p>
                  )}
                  {current.changes.length > 0 ? (
                    <>
                      <h4>{t("changedInTurn", { turn: current.turnNumber ?? "?" })}</h4>
                      <Changes>
                        {current.changes.map((change, index) => (
                          <li key={index}>
                            <strong>
                              {t(CHANGED_FIELD[change.field])} {t(CHANGED_KIND[change.kind])}
                            </strong>
                            {change.before ? <del>{change.before}</del> : null}
                            {change.after ? <ins>{change.after}</ins> : null}
                          </li>
                        ))}
                      </Changes>
                    </>
                  ) : null}
                  {earlier.length > 0 ? (
                    <History>
                      <summary>{t("earlierUnderstanding", { count: earlier.length })}</summary>
                      {earlier.map((version) => (
                        <Earlier key={version.version}>
                          {version.version === 0 ? (
                            <p>
                              <strong>{t("initialUnderstanding")}</strong>
                            </p>
                          ) : (
                            <TurnLink type="button" onClick={() => jumpTo(version.turnId)}>
                              {t("afterTurn", { turn: version.turnNumber ?? "?" })}
                            </TurnLink>
                          )}
                          <StateBody state={version.state} label={t("understanding")} showAccuracy={prefs.showAccuracy} />
                        </Earlier>
                      ))}
                    </History>
                  ) : null}
                </>
              ) : (
                <>
                  <h4>{t("role")}</h4>
                  <p>{person.description ?? t("tutorRole")}</p>
                </>
              )}
            </div>
          ) : (
            <EmptyState>{t("selectParticipant")}</EmptyState>
          )}
          <Options>
            <Check>
              <input
                type="checkbox"
                checked={prefs.showAccuracy}
                onChange={(event) => setPref({ showAccuracy: event.target.checked })}
              />
              {t("markAccuracy")}
            </Check>
            <Check>
              <input
                type="checkbox"
                checked={prefs.pauseOnPanel}
                onChange={(event) => setPref({ pauseOnPanel: event.target.checked })}
              />
              {t("pauseOnPanel")}
            </Check>
          </Options>
        </Understanding>
      </Classroom>
    </Screen>
  );
}
