"use client";

import { useI18n } from "@/i18n";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { CSSProperties, KeyboardEvent, PointerEvent } from "react";
import { useRouter } from "next/navigation";
import styled from "styled-components";
import { Button, ButtonLink, Navbar } from "@/common/components";
import { useCslSession, useCurrentSessionId } from "@/lib/csl";
import type { SessionSnapshot } from "@/lib/csl";
import { ChatParticipants } from "@/features/chat/components/ChatParticipants";
import { ChatConversation } from "@/features/chat/components/ChatConversation";
import { DiscussionControls } from "@/features/chat/components/DiscussionControls";
import { UnderstandingPanel } from "@/features/chat/components/UnderstandingPanel";
import { ChatEmptyState } from "@/features/chat/components/ChatStyles";
import { SetupDetailsDialog } from "@/features/chat/components/SetupDetailsDialog";

// The understanding panel can be dragged wider or narrower (its left edge), within these limits.
const PANEL_MIN = 240;
const PANEL_MAX_VW = 60;
const PANEL_STEP = 24;

const Screen = styled.div`
  display: flex;
  flex-direction: column;
  height: 100dvh;
  background: ${({ theme }) => theme.colors.WHITE};
`;

const Classroom = styled.main<{ $panelOpen: boolean }>`
  display: grid;
  /* --panel-width is set once the learner has dragged the panel's edge; until then the defaults apply. */
  grid-template-columns: 150px minmax(0, 1fr) ${({ $panelOpen }) =>
    $panelOpen && `clamp(${PANEL_MIN}px, var(--panel-width, 300px), ${PANEL_MAX_VW}vw)`};
  grid-template-rows: auto minmax(0, 1fr);
  flex: 1;
  min-height: 0;
  @media (max-width: 1000px) {
    grid-template-columns: 130px minmax(0, 1fr) ${({ $panelOpen }) =>
      $panelOpen && `clamp(${PANEL_MIN}px, var(--panel-width, 240px), ${PANEL_MAX_VW}vw)`};
  }
  @media (max-width: 760px) {
    grid-template-columns: 110px minmax(0, 1fr);
    grid-template-rows: auto minmax(320px, 1fr) ${({ $panelOpen }) => $panelOpen && "auto"};
    overflow-y: auto;
  }
`;

const Goal = styled.header`
  grid-column: 2 / -1;
  padding: 18px 24px;
  border-bottom: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  & > div {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px 16px;
    margin-bottom: 8px;
  }
  h1 { margin: 0; font-size: 16px; }
  & > p { margin: 0; font-size: 15px; overflow-wrap: anywhere; }
`;

// Sits on the panel's left border, in the same grid cell, so it stays put while the panel scrolls.
const Resizer = styled.div`
  grid-column: 3;
  grid-row: 2;
  justify-self: start;
  z-index: 1;
  width: 11px;
  margin-left: -5px;
  cursor: col-resize;
  touch-action: none;
  &::after {
    content: "";
    display: block;
    width: 3px;
    height: 100%;
    margin: 0 auto;
    background: transparent;
    transition: background 0.15s;
  }
  &:hover::after,
  &:focus-visible::after,
  &[data-dragging="true"]::after {
    background: ${({ theme }) => theme.colors.SLATE[600]};
  }
  &:focus-visible { outline: none; }
  @media (max-width: 760px) { display: none; }
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

// What this browser remembers about how the learner likes to read the classroom.
type Prefs = { showAccuracy: boolean; pauseOnPanel: boolean; panelWidth: number | null };
const PREFS_KEY = "csl.classroomPrefs";
const DEFAULT_PREFS: Prefs = { showAccuracy: true, pauseOnPanel: false, panelWidth: null };

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

const noSubscription = () => () => {};
// False on the server and while hydrating: what depends on this browser's storage waits for it.
function useHydrated() {
  return useSyncExternalStore(noSubscription, () => true, () => false);
}

// The classroom runs on the session named in the URL (?session=<id>). Leaving the page pauses the
// discussion on the server; opening the same link (or "Continue" on My page) picks it up again.
export default function ChatPage() {
  const { t } = useI18n();
  const router = useRouter();
  const sessionId = useCurrentSessionId();
  const { snapshot, connection, error, actions } = useCslSession(sessionId ?? null);
  const [draft, setDraft] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const [prefs, setPrefs] = useState<Prefs>(readPrefs);
  // The panel width while its edge is being dragged; it becomes a preference when the drag ends.
  const [dragWidth, setDragWidth] = useState<number | null>(null);
  const hydrated = useHydrated();
  const classroom = useRef<HTMLElement>(null);
  const panel = useRef<HTMLElement>(null);
  // The state version of each participant the learner has looked at; a newer one shows a dot in the list.
  const [seen, setSeen] = useState<Record<string, number> | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const setupDialog = useRef<HTMLDialogElement>(null);

  const phase = snapshot?.phase ?? null;
  const status = snapshot?.status ?? null;
  const messages = snapshot ? snapshot.messages.filter((message) => message.channel === "discussion") : [];
  const active = snapshot?.activeTurn?.channel === "discussion" ? snapshot.activeTurn : null;
  const messageCount = messages.length;
  const activeText = active?.text ?? null;

  useEffect(() => {
    if (!setupDialog.current?.open) bottom.current?.scrollIntoView({ block: "nearest" });
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
          <ChatEmptyState>
            {sessionId === null ? t("noSession") : t("openError")}
          </ChatEmptyState>
          <ButtonLink href="/">{t("startLearningLink")}</ButtonLink>
        </Fallback>
      </Screen>
    );
  }

  const participants = snapshot?.participants ?? [];
  const person = participants.find((participant) => participant.id === selected) ?? null;
  const versions = person && snapshot ? snapshot.states[person.id] : undefined;
  const pace = snapshot?.pace ?? null;

  const ended = phase === "ended";
  const waiting = status === "waiting_user";
  const running = phase === "discussion" && status === "running" && connection === "open";

  const versionOf = (id: string) => {
    const all = snapshot?.states[id];
    return all?.[all.length - 1]?.version ?? 0;
  };

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

  // The panel is the rightmost column: its width is the distance from the pointer to the classroom's right edge.
  const panelWidth = hydrated ? (dragWidth ?? prefs.panelWidth) : null;
  const limitWidth = (width: number) =>
    Math.round(Math.min(Math.max(width, PANEL_MIN), (window.innerWidth * PANEL_MAX_VW) / 100));
  const widthAt = (clientX: number) =>
    limitWidth((classroom.current?.getBoundingClientRect().right ?? window.innerWidth) - clientX);
  const startDrag = (event: PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragWidth(widthAt(event.clientX));
  };
  const drag = (event: PointerEvent<HTMLDivElement>) => {
    if (dragWidth !== null) setDragWidth(widthAt(event.clientX));
  };
  const endDrag = () => {
    if (dragWidth === null) return;
    setPref({ panelWidth: dragWidth });
    setDragWidth(null);
  };
  const nudgePanel = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const width = panel.current?.getBoundingClientRect().width ?? 300;
    setPref({ panelWidth: limitWidth(width + (event.key === "ArrowLeft" ? PANEL_STEP : -PANEL_STEP)) });
  };

  // "Updated after turn N" in the panel leads to the message that caused the change.
  const jumpTo = (turnId: string | null) => {
    if (!turnId) return;
    document.getElementById(`turn-${turnId}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
    setFlash(turnId);
    window.setTimeout(() => setFlash((shown) => (shown === turnId ? null : shown)), 2500);
    actions.track("state.jump", { turnId });
  };

  return (
    <Screen>
      <Navbar />
      <Classroom
        ref={classroom}
        $panelOpen={panelOpen}
        style={panelWidth ? ({ "--panel-width": `${panelWidth}px` } as CSSProperties) : undefined}
      >
        <ChatParticipants
          participants={participants}
          selected={selected}
          seen={seen}
          versionOf={versionOf}
          onSelect={(id) => openPanel(id, "list")}
        />
        <Goal>
          <div>
            <h1>{t("learningGoal")}</h1>
            {snapshot && (
              <Button variant="ghost" aria-haspopup="dialog" onClick={() => setupDialog.current?.showModal()}>
                {t("viewSetupDetails")}
              </Button>
            )}
          </div>
          <p>{snapshot?.focus ?? snapshot?.topic ?? "…"}</p>
          {snapshot && <SetupDetailsDialog dialogRef={setupDialog} snapshot={snapshot} />}
        </Goal>
        <ChatConversation
          messages={messages}
          active={active}
          snapshot={snapshot}
          flash={flash}
          bottom={bottom}
          errorMessage={error?.message}
          draft={draft}
          waiting={waiting}
          canSend={Boolean(snapshot) && !ended && connection === "open"}
          onOpenUnderstanding={(id) => openPanel(id, "message")}
          onDraftChange={setDraft}
          onSubmit={() => {
            if (!draft.trim()) return;
            actions.say(draft.trim());
            setDraft("");
          }}
        >
          <DiscussionControls
            phase={phase}
            pace={pace}
            connection={connection}
            hasSnapshot={Boolean(snapshot)}
            hasActiveTurn={Boolean(active)}
            ended={ended}
            waiting={waiting}
            running={running}
            onSetPace={actions.setPace}
            onStep={actions.step}
            onPause={actions.pause}
            onResume={actions.resume}
          />
        </ChatConversation>
        {panelOpen ? (
          <Resizer
            role="separator"
            aria-orientation="vertical"
            aria-label={t("resizePanel")}
            title={t("resizePanel")}
            tabIndex={0}
            data-dragging={dragWidth !== null}
            onPointerDown={startDrag}
            onPointerMove={drag}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
            onDoubleClick={() => setPref({ panelWidth: null })}
            onKeyDown={nudgePanel}
          />
        ) : null}
        <UnderstandingPanel
          panelRef={panel}
          open={panelOpen}
          person={person}
          versions={versions}
          showAccuracy={prefs.showAccuracy}
          pauseOnPanel={prefs.pauseOnPanel}
          onClose={closePanel}
          onJumpTo={jumpTo}
          onShowAccuracyChange={(showAccuracy) => setPref({ showAccuracy })}
          onPauseOnPanelChange={(pauseOnPanel) => setPref({ pauseOnPanel })}
        />
      </Classroom>
    </Screen>
  );
}
