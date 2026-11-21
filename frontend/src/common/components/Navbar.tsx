"use client";

import { useI18n } from "@/i18n";
import { useTransition } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Languages, UserRound } from "lucide-react";
import styled from "styled-components";
import { useCurrentUser } from "@/lib/csl";

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

const ProfileButton = styled(IconButton)`
  width: auto;
  min-width: 44px;
  gap: 8px;
  padding-inline: 10px;
`;

const UserName = styled.span`
  max-width: 160px;
  overflow: hidden;
  color: ${({ theme }) => theme.colors.GRAY[900]};
  font-size: 14px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

export type NavbarProps = {
  /** Default: open My page (which asks for a nickname when nobody is signed in). */
  onProfileClick?: () => void;
  onLanguageClick?: () => void;
};

export function LanguageButton({ onClick }: { onClick?: () => void }) {
  const { locale, setLocale, t } = useI18n();
  const [pending, startTransition] = useTransition();
  const switchLanguage = () => startTransition(() => setLocale(locale === "en" ? "ko" : "en"));

  return (
    <IconButton
      type="button"
      aria-label={t("switchLanguage")}
      title={t("switchLanguage")}
      onClick={onClick ?? switchLanguage}
      disabled={pending}
    >
      <Languages size={22} aria-hidden="true" />
    </IconButton>
  );
}

export function Navbar({ onProfileClick, onLanguageClick }: NavbarProps) {
  const { t } = useI18n();
  const router = useRouter();
  const user = useCurrentUser();
  const profileLabel = user ? t("myPageUser", { name: user.name }) : t("signIn");

  return (
    <Navigation aria-label={t("navigation")}>
      <Brand href="/" aria-label={t("home")}>CSL</Brand>
      <Actions>
        <ProfileButton
          type="button"
          aria-label={profileLabel}
          title={profileLabel}
          onClick={onProfileClick ?? (() => router.push("/mypage"))}
        >
          <UserRound size={22} aria-hidden="true" />
          {user ? <UserName>{user.name}</UserName> : null}
        </ProfileButton>
        <LanguageButton onClick={onLanguageClick} />
      </Actions>
    </Navigation>
  );
}
