"use client";

import { useEffect, useRef, useState } from "react";
import type { ReactNode, Ref } from "react";
import { X } from "lucide-react";
import styled from "styled-components";
import { Button } from "@/common/components";
import { useI18n } from "@/i18n";
import type { Accuracy, KnowledgeState, Language, Participant, StateChange, StateVersion } from "@/lib/csl";
import { ChatCheckbox, ChatEmptyState } from "./ChatStyles";

const Understanding = styled.aside`
  grid-column: 3;
  grid-row: 2;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  padding: 20px;
  border-left: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  background: #f8f5df;
  &[hidden] { display: none; }
  h3 { margin: 0 0 16px; font-size: 16px; }
  h4 { display: flex; align-items: center; flex-wrap: wrap; margin: 20px 0 8px; font-size: 13px; }
  p { margin: 0; font-size: 14px; line-height: 1.6; }
  li + li { margin-top: 4px; }
  ul { margin: 0; padding-left: 18px; font-size: 14px; line-height: 1.6; }
  @media (max-width: 760px) {
    grid-column: 2;
    grid-row: 3;
    min-height: 180px;
    border-top: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
    border-left: 0;
  }
`;

const ClampBox = styled.div<{ $lines: number; $open: boolean }>`
  font-size: 14px;
  line-height: 1.6;
  overflow-wrap: anywhere;
  ${({ $lines, $open }) =>
    !$open &&
    `display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: ${$lines}; overflow: hidden;`}
`;

const MoreButton = styled.button`
  display: block;
  margin-top: 2px;
  padding: 0;
  border: 0;
  background: none;
  color: ${({ theme }) => theme.colors.SLATE[600]};
  font-size: 12px;
  font-weight: 600;
  text-decoration: underline;
  cursor: pointer;
`;

const ChangeTag = styled.span`
  margin-right: 6px;
  color: ${({ theme }) => theme.colors.SLATE[600]};
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
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

const AccuracyTag = styled.span<{ $accuracy: Accuracy; $lead?: boolean }>`
  display: inline-block;
  margin: ${({ $lead }) => ($lead ? "0 6px 0 0" : "0 0 0 6px")};
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
  ins::before { content: "+ "; color: ${({ theme }) => theme.colors.SLATE[600]}; font-weight: 600; }
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

const CHANGED_FIELD = {
  explanation: "understanding",
  beliefs: "belief",
  openQuestions: "openQuestion",
} as const satisfies Record<StateChange["field"], string>;
const CHANGED_KIND = { added: "added", removed: "dropped", modified: "revised" } as const;
// More beliefs than this are folded behind "Show n more" (the ones that just changed always stay visible).
const BELIEFS_SHOWN = 4;

function Mark({ accuracy, show, lead }: { accuracy: Accuracy | null; show: boolean; lead?: boolean }) {
  const { t } = useI18n();
  return show && accuracy ? (
    <AccuracyTag $accuracy={accuracy} $lead={lead}>
      {t(accuracy)}
    </AccuracyTag>
  ) : null;
}

// Long text is cut after a few lines, with "Show more" only when something is actually cut off
// (which depends on the panel's width, so it is measured rather than guessed from the length).
function Clamp({ lines, children }: { lines: number; children: ReactNode }) {
  const { t } = useI18n();
  const box = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [cut, setCut] = useState(false);
  useEffect(() => {
    const element = box.current;
    if (!element || open) return;
    const observer = new ResizeObserver(() => setCut(element.scrollHeight > element.clientHeight + 1));
    observer.observe(element);
    return () => observer.disconnect();
  }, [open]);
  return (
    <>
      <ClampBox ref={box} $lines={lines} $open={open}>
        {children}
      </ClampBox>
      {cut || open ? (
        <MoreButton type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
          {t(open ? "showLess" : "showMore")}
        </MoreButton>
      ) : null}
    </>
  );
}

function sentences(text: string): string[] {
  return text
    .split(/(?<=[.!?。！？]["'”’)\]]?)\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
}

// What a revision took out and put in, without repeating what stayed: whole sentences first, and
// when one sentence was reworded, only the part of it that differs (with a couple of words around it).
function diffText(before: string, after: string): { removed: string[]; added: string[] } {
  const old = sentences(before);
  const next = sentences(after);
  const removed = old.filter((sentence) => !next.includes(sentence));
  const added = next.filter((sentence) => !old.includes(sentence));
  if (removed.length !== 1 || added.length !== 1) return { removed, added };
  const a = removed[0].split(" ");
  const b = added[0].split(" ");
  let head = 0;
  while (head < a.length && head < b.length && a[head] === b[head]) head += 1;
  let tail = 0;
  while (tail < a.length - head && tail < b.length - head && a[a.length - 1 - tail] === b[b.length - 1 - tail]) {
    tail += 1;
  }
  if (head + tail < 8) return { removed, added };
  const middle = (words: string[]) => {
    if (words.length - head - tail <= 0) return null; // nothing of its own: the other side only grew
    const from = Math.max(0, head - 2);
    const to = words.length - Math.max(0, tail - 2);
    return `${from > 0 ? "… " : ""}${words.slice(from, to).join(" ")}${to < words.length ? " …" : ""}`;
  };
  const was = middle(a);
  const now = middle(b);
  return { removed: was ? [was] : [], added: now ? [now] : [] };
}

// One entry of "What changed in turn N": only the wording that left and the wording that came in.
function changeLines(change: StateChange): { removed: string[]; added: string[] } {
  if (change.before && change.after) return diffText(change.before, change.after);
  return { removed: change.before ? [change.before] : [], added: change.after ? [change.after] : [] };
}

function StateBody({
  state,
  label,
  showAccuracy,
  changes = [],
}: {
  state: KnowledgeState;
  label: string;
  showAccuracy: boolean;
  changes?: StateChange[];
}) {
  const { t } = useI18n();
  const [allBeliefs, setAllBeliefs] = useState(false);
  // Beliefs that the latest change added or reworded: tagged, and never folded away.
  const changed = new Map(
    changes.flatMap((change) =>
      change.field === "beliefs" && change.beliefId && change.kind !== "removed" && change.before !== change.after
        ? [[change.beliefId, change.kind] as const]
        : [],
    ),
  );
  const foldable = state.beliefs.length > BELIEFS_SHOWN;
  const unchanged = state.beliefs.filter((belief) => !changed.has(belief.id));
  const kept = unchanged.slice(0, Math.max(0, BELIEFS_SHOWN - (state.beliefs.length - unchanged.length)));
  const shown =
    !foldable || allBeliefs
      ? state.beliefs
      : state.beliefs.filter((belief) => changed.has(belief.id) || kept.includes(belief));
  const folded = state.beliefs.length - shown.length;
  return (
    <>
      <h4>
        {label}
        <Mark accuracy={state.explanationAccuracy} show={showAccuracy} />
      </h4>
      <Clamp key={state.explanation} lines={5}>
        {state.explanation || "—"}
      </Clamp>
      {state.beliefs.length > 0 ? (
        <>
          <h4>{t("beliefs")}</h4>
          <ul>
            {shown.map((belief) => (
              <li key={belief.id}>
                <Clamp key={belief.text} lines={3}>
                  <Mark accuracy={belief.accuracy} show={showAccuracy} lead />
                  {changed.has(belief.id) ? (
                    <ChangeTag>{t(CHANGED_KIND[changed.get(belief.id) ?? "modified"])}</ChangeTag>
                  ) : null}
                  {belief.text}
                </Clamp>
              </li>
            ))}
          </ul>
          {folded > 0 || (foldable && allBeliefs) ? (
            <MoreButton type="button" aria-expanded={allBeliefs} onClick={() => setAllBeliefs(!allBeliefs)}>
              {allBeliefs ? t("showFewerBeliefs") : t("showMoreBeliefs", { count: folded })}
            </MoreButton>
          ) : null}
        </>
      ) : null}
    </>
  );
}

type UnderstandingPanelProps = {
  panelRef: Ref<HTMLElement>;
  open: boolean;
  person: Participant | null;
  discussionLanguage?: Language;
  versions?: StateVersion[];
  showAccuracy: boolean;
  pauseOnPanel: boolean;
  onClose: () => void;
  onJumpTo: (turnId: string | null) => void;
  onShowAccuracyChange: (showAccuracy: boolean) => void;
  onPauseOnPanelChange: (pauseOnPanel: boolean) => void;
};

export function UnderstandingPanel({
  panelRef, open, person, discussionLanguage, versions, showAccuracy, pauseOnPanel,
  onClose, onJumpTo, onShowAccuracyChange, onPauseOnPanelChange,
}: UnderstandingPanelProps) {
  const { t } = useI18n();
  const { t: discussionT } = useI18n(discussionLanguage);
  const current = versions?.[versions.length - 1];
  const earlier = versions ? versions.slice(0, -1).reverse() : [];
  // A change that only re-graded the accuracy has no wording to show.
  const changed = (current?.changes ?? [])
    .map((change) => ({ change, ...changeLines(change) }))
    .filter(({ removed, added }) => removed.length + added.length > 0);

  return (
    <Understanding ref={panelRef} aria-label={t("participantUnderstanding")} hidden={!open}>
      <PanelHeader>
        <h2>{t("understanding")}</h2>
        <Button type="button" variant="ghost" aria-label={t("closeUnderstanding")} onClick={onClose}>
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
                <TurnLink type="button" onClick={() => onJumpTo(current.turnId)}>
                  {t("updatedAfterTurn", { turn: current.turnNumber ?? "?" })}
                </TurnLink>
              )}
              <StateBody
                key={current.version}
                state={current.state}
                label={t("currentUnderstanding")}
                showAccuracy={showAccuracy}
                changes={current.changes}
              />
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
              {changed.length > 0 ? (
                <>
                  <h4>{t("changedInTurn", { turn: current.turnNumber ?? "?" })}</h4>
                  <Changes>
                    {changed.map(({ change, removed, added }, index) => (
                      <li key={index}>
                        <strong>
                          {t(CHANGED_FIELD[change.field])} {t(CHANGED_KIND[change.kind])}
                        </strong>
                        {removed.map((line) => (
                          <del key={line}>{line}</del>
                        ))}
                        {added.map((line) => (
                          <ins key={line}>{line}</ins>
                        ))}
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
                        <TurnLink type="button" onClick={() => onJumpTo(version.turnId)}>
                          {t("afterTurn", { turn: version.turnNumber ?? "?" })}
                        </TurnLink>
                      )}
                      <StateBody state={version.state} label={t("understanding")} showAccuracy={showAccuracy} />
                    </Earlier>
                  ))}
                </History>
              ) : null}
            </>
          ) : (
            <>
              <h4>{discussionT("role")}</h4>
              <p>{person.description ?? discussionT("tutorRole")}</p>
            </>
          )}
        </div>
      ) : (
        <ChatEmptyState>{t("selectParticipant")}</ChatEmptyState>
      )}
      <Options>
        <ChatCheckbox>
          <input
            type="checkbox"
            checked={showAccuracy}
            onChange={(event) => onShowAccuracyChange(event.target.checked)}
          />
          {t("markAccuracy")}
        </ChatCheckbox>
        <ChatCheckbox>
          <input
            type="checkbox"
            checked={pauseOnPanel}
            onChange={(event) => onPauseOnPanelChange(event.target.checked)}
          />
          {t("pauseOnPanel")}
        </ChatCheckbox>
      </Options>
    </Understanding>
  );
}
