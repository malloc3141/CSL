"use client";

import styled from "styled-components";
import { useI18n } from "@/i18n";
import type { Participant as SessionParticipant } from "@/lib/csl";
import { peerColor } from "@/styles/peerColors";

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

const Dot = styled.span`
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: ${({ theme }) => theme.colors.SLATE[600]};
`;

type ChatParticipantsProps = {
  participants: SessionParticipant[];
  selected: string | null;
  seen: Record<string, number> | null;
  versionOf: (id: string) => number;
  onSelect: (id: string) => void;
};

export function ChatParticipants({ participants, selected, seen, versionOf, onSelect }: ChatParticipantsProps) {
  const { t } = useI18n();

  return (
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
            onClick={() => onSelect(participant.id)}
          >
            {participant.name}
            {participant.id !== selected && versionOf(participant.id) > (seen?.[participant.id] ?? 0) ? (
              <Dot role="img" aria-label={t("updatedLower")} title={t("updated")} />
            ) : null}
          </Participant>
        ))}
      </Participants>
    </Sidebar>
  );
}
