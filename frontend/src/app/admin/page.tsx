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
  { id: "usage", label: "사용량" },
  { id: "model", label: "모델" },
  { id: "sessions", label: "대화 이력" },
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
            <Heading>CSL 관리자</Heading>
            <Label htmlFor="admin-token">
              관리자 토큰 (서버 backend/.env의 ADMIN_TOKEN)
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
                {busy ? "확인 중…" : "들어가기"}
              </Button>
            </Row>
            {error ? <ErrorText>{error}</ErrorText> : null}
            <Meta>토큰은 이 탭의 sessionStorage에만 보관되고, 탭을 닫으면 지워집니다.</Meta>
          </Card>
        </Narrow>
      </Page>
    );
  }

  return (
    <Page>
      <Card>
        <Row>
          <Heading>CSL 관리자</Heading>
          <span style={{ flex: 1 }} />
          {TABS.map((t) => (
            <Button key={t.id} variant={tab === t.id ? "primary" : "ghost"} onClick={() => setTab(t.id)}>
              {t.label}
            </Button>
          ))}
          <Button variant="ghost" onClick={signOut}>
            나가기
          </Button>
        </Row>
        <Meta>
          파이프라인 {config.pipeline} · 메인 {config.model || "(미설정)"} · 보조 {config.modelFast || "(메인과 동일)"}
          {config.overridden ? " · 관리자 페이지에서 변경됨" : ""}
        </Meta>
      </Card>

      {tab === "usage" ? <UsageTab token={token} apiKeySet={config.apiKeySet} /> : null}
      {tab === "model" ? <ModelTab token={token} config={config} onChange={setConfig} /> : null}
      {tab === "sessions" ? <SessionsTab token={token} /> : null}
    </Page>
  );
}
