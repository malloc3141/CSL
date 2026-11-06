"use client";

import { UserRound } from "lucide-react";
import styled from "styled-components";

const Frame = styled.span<{ $color: string; $size: number }>`
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: ${({ $size }) => $size}px;
  height: ${({ $size }) => $size}px;
  border-radius: 50%;
  background: ${({ $color }) => $color};
  color: ${({ theme }) => theme.colors.WHITE};
`;

type ProfileImageProps = {
  color: string;
  size?: number;
};

export function ProfileImage({ color, size = 32 }: ProfileImageProps) {
  const iconSize = Math.round(size * 0.62);

  return (
    <Frame $color={color} $size={size} aria-hidden>
      <UserRound size={iconSize} strokeWidth={2} />
    </Frame>
  );
}
