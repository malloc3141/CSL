"use client";

import { useI18n } from "@/i18n";
import { useState } from "react";
import { ArrowRight } from "lucide-react";
import styled from "styled-components";
import { signIn } from "@/lib/csl";
import { Button } from "./Button";
import { TextField } from "./TextField";

const Card = styled.form`
  display: flex;
  flex-direction: column;
  gap: 20px;
  width: 100%;
  max-width: 440px;
  margin: 48px auto 0;
  padding: 32px;
  border: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  border-radius: ${({ theme }) => theme.round.md};
  background: ${({ theme }) => theme.colors.WHITE};

  > button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }
`;

const Title = styled.h1`
  margin: 0;
  font-size: 28px;
  font-weight: 700;
`;

const Description = styled.p`
  margin: 0;
  color: ${({ theme }) => theme.colors.GRAY[500]};
  font-size: 14px;
  line-height: 1.7;
`;

const ErrorText = styled.p`
  margin: 0;
  color: ${({ theme }) => theme.colors.ROSE[900]};
  font-size: 14px;
`;

export type LoginCardProps = {
  title?: string;
  description?: string;
  /** Called after a successful sign-in. The signed-in user is also available from useCurrentUser(). */
  onSignedIn?: () => void;
};

/**
 * Nickname sign-in. There is no password: a new nickname creates the user, a known one signs in as
 * that user (see backend/app/users.py).
 */
export function LoginCard({
  title,
  description,
  onSignedIn,
}: LoginCardProps) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ready = name.trim().length >= 2;

  return (
    <Card
      onSubmit={async (event) => {
        event.preventDefault();
        if (!ready || busy) return;
        setBusy(true);
        setError(null);
        try {
          await signIn(name);
          onSignedIn?.();
        } catch (cause) {
          setError(cause instanceof Error ? cause.message : String(cause));
          setBusy(false);
        }
      }}
    >
      <Title>{title ?? t("signIn")}</Title>
      <Description>{description ?? t("loginDefault")}</Description>
      <TextField id="nickname" label={t("nickname")} value={name} onChange={setName} placeholder={t("nicknameLength")} />
      {error ? <ErrorText role="alert">{error}</ErrorText> : null}
      <Button type="submit" disabled={!ready || busy}>
        {busy ? t("signingIn") : t("continue")}
        {busy ? null : <ArrowRight size={16} aria-hidden="true" />}
      </Button>
      <Description>{t("noPassword")}</Description>
    </Card>
  );
}
