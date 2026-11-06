"use client";

import styled, { useTheme } from "styled-components";
import { peerColor } from "@/styles/peerColors";

export type BubbleRole = "system" | "tutor" | "peer" | "user";

const Wrap = styled.div<{ $alignEnd: boolean }>`
  display: flex;
  flex-direction: column;
  align-items: ${({ $alignEnd }) => ($alignEnd ? "flex-end" : "flex-start")};
  gap: 4px;
  max-width: 440px;
`;

const Speaker = styled.span`
  color: ${({ theme }) => theme.colors.GRAY[900]};
  font-size: 12px;
  font-weight: 600;
`;

const Body = styled.p<{ $bg: string }>`
  margin: 0;
  padding: 10px 12px;
  border-radius: ${({ theme }) => theme.round.md};
  background: ${({ $bg }) => $bg};
  color: ${({ theme }) => theme.colors.GRAY[900]};
  font-size: 14px;
  line-height: 1.5;
`;

type BubbleProps = {
  role: BubbleRole;
  speaker?: string;
  peerIndex?: number;
  children: React.ReactNode;
};

export function MessageBubble({ role, speaker, peerIndex = 0, children }: BubbleProps) {
  const theme = useTheme();
  const palette =
    role === "peer"
      ? peerColor(theme, peerIndex)
      : role === "user"
        ? theme.colors.GREEN
        : theme.colors.BLUE;

  return (
    <Wrap $alignEnd={role === "user"}>
      {speaker ? <Speaker>{speaker}</Speaker> : null}
      <Body $bg={palette[50]}>
        {children}
      </Body>
    </Wrap>
  );
}
