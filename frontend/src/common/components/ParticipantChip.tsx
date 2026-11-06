"use client";

import styled, { useTheme } from "styled-components";
import { peerColor } from "@/styles/peerColors";

export type ParticipantKind = "tutor" | "peer";

const Chip = styled.button<{ $selected: boolean; $bg: string }>`
  border: 1px solid
    ${({ theme, $selected }) => ($selected ? theme.colors.SLATE[600] : theme.colors.GRAY[200])};
  border-radius: ${({ theme }) => theme.round.sm};
  background: ${({ theme, $selected, $bg }) => ($selected ? $bg : theme.colors.WHITE)};
  color: ${({ theme }) => theme.colors.GRAY[900]};
  padding: 6px 10px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
`;

type ParticipantChipProps = {
  name: string;
  kind: ParticipantKind;
  peerIndex?: number;
  selected?: boolean;
  onSelect?: () => void;
};

export function ParticipantChip({
  name,
  kind,
  peerIndex = 0,
  selected = false,
  onSelect,
}: ParticipantChipProps) {
  const theme = useTheme();
  const palette = kind === "tutor" ? theme.colors.BLUE : peerColor(theme, peerIndex);

  return (
    <Chip
      type="button"
      $selected={selected}
      $bg={palette[50]}
      aria-pressed={selected}
      onClick={onSelect}
    >
      {name}
    </Chip>
  );
}
