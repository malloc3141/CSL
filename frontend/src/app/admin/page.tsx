"use client";

import { LanguageButton } from "@/common/components/Navbar";
import { useI18n } from "@/i18n";
// Admin page: LLM usage and cost, runtime model switch, session history.
// Talks to /api/admin/* (backend/app/admin.py) with the server's ADMIN_TOKEN.

import { useCallback, useEffect, useState } from "react";
import styled from "styled-components";
import { Button } from "@/common/components";
import { AdminAuthError, adminApi } from "@/lib/csl";
import type { ModelConfig } from "@/lib/csl";
import { ModelTab } from "./ModelTab";
import { SessionsTab } from "./SessionsTab";
import { UsageTab } from "./UsageTab";
import { Card, ErrorText, Heading, Input, Label, Meta, Row, errorMessage } from "./ui";

const TOKEN_KEY = "csl.adminToken";
const TABS = [
  { id: "usage", label: "usage" },
  { id: "model", label: "models" },
  { id: "sessions", label: "sessions" },
] as const;
type Tab = (typeof TABS)[number]["id"];

const Page = styled.main`
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px 16px;
`;

const Narrow = styled.form`
  max-width: 420px;
  margin: 10vh auto 0;
`;

function readToken(): string {
  try {
    return sessionStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

function writeToken(token: string | null) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // storage unavailable: the token lives only in memory for this page view
  }
}

export default function AdminPage() {
  const { t } = useI18n();
  const [token, setToken] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [config, setConfig] = useState<ModelConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<Tab>("usage");

  const signIn = useCallback(async (candidate: string) => {
    setBusy(true);
    setError(null);
    try {
      const cfg = await adminApi.config(candidate);
      writeToken(candidate);
      setToken(candidate);
      setConfig(cfg);
    } catch (cause) {
      if (cause instanceof AdminAuthError) writeToken(null);
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    const saved = readToken();
    if (!saved) return;
    adminApi.config(saved).then(
      (cfg) => {
        setToken(saved);
        setConfig(cfg);
      },
      () => writeToken(null),
    );
  }, []);

  const signOut = () => {
    writeToken(null);
    setToken(null);
    setConfig(null);
    setDraft("");
  };

  if (!token || !config) {
    return (
      <Page>
        <Narrow
          onSubmit={(event) => {
            event.preventDefault();
            if (draft.trim()) void signIn(draft.trim());
          }}
        >
          <Card>
            <Row>
              <Heading>{t("admin")}</Heading>
              <LanguageButton />
            </Row>
            <Label htmlFor="admin-token">
              {t("adminToken")}
              <Input
                id="admin-token"
                type="password"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                autoComplete="current-password"
              />
            </Label>
            <Row>
              <Button type="submit" disabled={busy || !draft.trim()}>
                {busy ? t("checking") : t("signIn")}
              </Button>
            </Row>
            {error ? <ErrorText>{error}</ErrorText> : null}
            <Meta>{t("tokenStorage")}</Meta>
          </Card>
        </Narrow>
      </Page>
    );
  }

  return (
    <Page>
      <Card>
        <Row>
          <Heading>{t("admin")}</Heading>
          <span style={{ flex: 1 }} />
          <LanguageButton />
          {TABS.map((item) => (
            <Button key={item.id} variant={tab === item.id ? "primary" : "ghost"} onClick={() => setTab(item.id)}>
              {t(item.label)}
            </Button>
          ))}
          <Button variant="ghost" onClick={signOut}>
            {t("signOut")}
          </Button>
        </Row>
        <Meta>
          {t("modelSummary", { pipeline: config.pipeline, main: config.model || t("notSet"), fast: config.modelFast || t("sameAsMain") })}
          {config.overridden ? t("overridden") : ""}
        </Meta>
      </Card>

      {tab === "usage" ? <UsageTab token={token} apiKeySet={config.apiKeySet} /> : null}
      {tab === "model" ? <ModelTab token={token} config={config} onChange={setConfig} /> : null}
      {tab === "sessions" ? <SessionsTab token={token} /> : null}
    </Page>
  );
}
