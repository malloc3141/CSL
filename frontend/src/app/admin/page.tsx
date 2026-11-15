"use client";

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
  { id: "usage", label: "Usage" },
  { id: "model", label: "Models" },
  { id: "sessions", label: "Sessions" },
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
            <Heading>CSL Admin</Heading>
            <Label htmlFor="admin-token">
              Admin token (ADMIN_TOKEN in backend/.env on the server)
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
                {busy ? "Checking…" : "Sign in"}
              </Button>
            </Row>
            {error ? <ErrorText>{error}</ErrorText> : null}
            <Meta>The token is kept only in the sessionStorage of this tab and is gone when the tab closes.</Meta>
          </Card>
        </Narrow>
      </Page>
    );
  }

  return (
    <Page>
      <Card>
        <Row>
          <Heading>CSL Admin</Heading>
          <span style={{ flex: 1 }} />
          {TABS.map((t) => (
            <Button key={t.id} variant={tab === t.id ? "primary" : "ghost"} onClick={() => setTab(t.id)}>
              {t.label}
            </Button>
          ))}
          <Button variant="ghost" onClick={signOut}>
            Sign out
          </Button>
        </Row>
        <Meta>
          Pipeline {config.pipeline} · main {config.model || "(not set)"} · fast {config.modelFast || "(same as main)"}
          {config.overridden ? " · overridden from the admin page" : ""}
        </Meta>
      </Card>

      {tab === "usage" ? <UsageTab token={token} apiKeySet={config.apiKeySet} /> : null}
      {tab === "model" ? <ModelTab token={token} config={config} onChange={setConfig} /> : null}
      {tab === "sessions" ? <SessionsTab token={token} /> : null}
    </Page>
  );
}
