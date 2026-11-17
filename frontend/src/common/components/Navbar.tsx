"use client";

import Link from "next/link";
import { FolderOpen, Languages, UserRound } from "lucide-react";
import styled from "styled-components";

const Navigation = styled.nav`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  min-height: 72px;
  padding: 12px 24px;
  border-bottom: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  background: ${({ theme }) => theme.colors.WHITE};
`;

const Brand = styled(Link)`
  color: ${({ theme }) => theme.colors.GRAY[900]};
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.5px;
  text-decoration: none;

  &:focus-visible {
    outline: 2px solid ${({ theme }) => theme.colors.SLATE[600]};
    outline-offset: 4px;
  }
`;

const Actions = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
`;

const IconButton = styled.button`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  padding: 0;
  border: 0;
  border-radius: ${({ theme }) => theme.round.sm};
  background: transparent;
  color: ${({ theme }) => theme.colors.SLATE[600]};
  cursor: pointer;

  &:hover {
    background: ${({ theme }) => theme.colors.GRAY[100]};
  }

  &:focus-visible {
    outline: 2px solid ${({ theme }) => theme.colors.SLATE[600]};
    outline-offset: 2px;
  }
`;

export type NavbarProps = {
  onProfileClick?: () => void;
  onFilesClick?: () => void;
  onLanguageClick?: () => void;
};

export function Navbar({ onProfileClick, onFilesClick, onLanguageClick }: NavbarProps) {
  return (
    <Navigation aria-label="Main navigation">
      <Brand href="/" aria-label="CSL home">CSL</Brand>
      <Actions>
        <IconButton type="button" aria-label="Files" title="Files" onClick={onFilesClick}>
          <FolderOpen size={22} aria-hidden="true" />
        </IconButton>
        <IconButton type="button" aria-label="Profile" title="Profile" onClick={onProfileClick}>
          <UserRound size={22} aria-hidden="true" />
        </IconButton>
        <IconButton type="button" aria-label="Language" title="Language" onClick={onLanguageClick}>
          <Languages size={22} aria-hidden="true" />
        </IconButton>
      </Actions>
    </Navigation>
  );
}
