"use client";

import { Pause, Play, SkipForward } from "lucide-react";
import styled from "styled-components";
import { Button, ButtonLink } from "@/common/components";
import { useI18n } from "@/i18n";
import type { ConnectionState, Pace, Phase, SetPace } from "@/lib/csl";
import { ChatCheckbox } from "./ChatStyles";

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

const SPEEDS = [0.5, 1, 1.5, 2];

type DiscussionControlsProps = {
  phase: Phase | null;
  pace: Pace | null;
  connection: ConnectionState;
  hasSnapshot: boolean;
  hasActiveTurn: boolean;
  ended: boolean;
  waiting: boolean;
  running: boolean;
  onSetPace: (pace: SetPace) => void;
  onStep: () => void;
  onPause: () => void;
  onResume: () => void;
};

export function DiscussionControls({
  phase, pace, connection, hasSnapshot, hasActiveTurn, ended, waiting, running,
  onSetPace, onStep, onPause, onResume,
}: DiscussionControlsProps) {
  const { t } = useI18n();
  const statusLabel = !hasSnapshot
    ? t("opening")
    : ended
      ? t("finished")
      : connection !== "open"
        ? t("reconnecting")
        : waiting
          ? t("waitingExplanation")
          : running
            ? pace && !pace.auto && !hasActiveTurn
              ? t("nextToContinue")
              : t("inProgress")
            : phase === "ready"
              ? t("starting")
              : t("paused");

  return (
    <Controls>
      {phase === "discussion" && pace ? (
        <ControlGroup role="group" aria-label={t("pace")}>
          <ChatCheckbox title={t("autoAdvanceHint")}>
            <input
              type="checkbox"
              checked={pace.auto}
              onChange={(event) => onSetPace({ auto: event.target.checked })}
            />
            {t("autoAdvance")}
          </ChatCheckbox>
          {SPEEDS.map((speed) => (
            <Speed
              key={speed}
              type="button"
              $on={pace.speed === speed}
              aria-pressed={pace.speed === speed}
              disabled={!pace.auto}
              title={t("speedHint")}
              onClick={() => onSetPace({ speed })}
            >
              {speed}×
            </Speed>
          ))}
          <Button variant="ghost" disabled={connection !== "open"} onClick={onStep}>
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
          <ButtonLink variant="ghost" href="/">
            {t("newSession")}
          </ButtonLink>
        ) : running ? (
          <Button variant="ghost" onClick={onPause}>
            {t("pauseDiscussion")}
            <Pause size={16} aria-hidden="true" />
          </Button>
        ) : (
          <Button variant="ghost" disabled={!hasSnapshot || connection !== "open"} onClick={onResume}>
            {waiting ? t("skipForNow") : t("resumeDiscussion")}
            <Play size={16} aria-hidden="true" />
          </Button>
        )}
      </ControlGroup>
    </Controls>
  );
}
