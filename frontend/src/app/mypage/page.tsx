"use client";

import { useI18n } from "@/i18n";
// My page: who is signed in, and their sessions, to continue one that was left midway.
// Sessions come from the server (GET /api/users/{id}/sessions), so the list is the same in every browser.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Plus } from "lucide-react";
import styled, { useTheme } from "styled-components";
import { Button, LoginCard, Navbar, ProfileImage } from "@/common/components";
import { fetchUserSessions, signOut, useCurrentUser } from "@/lib/csl";
import type { SessionSummary } from "@/lib/csl";

const Screen = styled.div`
  display: flex;
  flex-direction: column;
  min-height: 100dvh;
  background: ${({ theme }) => theme.colors.WHITE};
`;

const Page = styled.main`
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 32px;
  padding: 16px 24px 24px;
  border-top: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
`;

const Card = styled.section`
  display: flex;
  flex-direction: column;
  gap: 20px;
  width: 100%;
  min-width: 0;
  max-width: 1040px;
  margin: 0 auto;
  padding-inline: clamp(0px, 4vw, 64px);
`;

const Header = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
`;

const Title = styled.h1`
  margin: 0;
  font-size: 28px;
  font-weight: 700;
`;

const Profile = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  border-radius: ${({ theme }) => theme.round.md};

  > strong {
    flex: 1;
    min-width: 0;
    font-size: 18px;
    overflow-wrap: anywhere;
  }
`;

const SectionTitle = styled.h2`
  margin: 12px 0 0;
  font-size: 20px;
`;

const Note = styled.p`
  margin: 0;
  color: ${({ theme }) => theme.colors.GRAY[500]};
  font-size: 14px;
  line-height: 1.7;
`;

const List = styled.ul`
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
`;

const Item = styled.li`
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  border-radius: ${({ theme }) => theme.round.md};

  > div {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }

  strong {
    font-size: 16px;
    overflow-wrap: anywhere;
  }

  > button {
    display: inline-flex;
    align-items: center;
    flex-shrink: 0;
    gap: 8px;
  }

  @media (max-width: 560px) {
    flex-direction: column;
    align-items: stretch;
  }
`;

const Status = styled.span<{ $done: boolean }>`
  align-self: flex-start;
  padding: 2px 10px;
  border-radius: ${({ theme }) => theme.round.sm};
  background: ${({ theme, $done }) => ($done ? theme.colors.GRAY[100] : theme.colors.BLUE[50])};
  color: ${({ theme, $done }) => ($done ? theme.colors.GRAY[500] : theme.colors.BLUE[900])};
  font-size: 12px;
  font-weight: 600;
`;

const Actions = styled.div`
  display: flex;
  gap: 8px;

  > button {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }
`;

const PHASE_LABEL = {
  init: "phaseInit",
  building: "phaseBuilding",
  ready: "phaseReady",
  discussion: "phaseDiscussion",
  ended: "finished",
} as const;

function when(seconds: number, locale: string) {
  return new Date(seconds * 1000).toLocaleString(locale, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export default function MyPage() {
  const { locale, t } = useI18n();
  const router = useRouter();
  const theme = useTheme();
  const user = useCurrentUser();
  const userId = user?.userId ?? null;
  const [loaded, setLoaded] = useState<{ userId: string; sessions: SessionSummary[] | null } | null>(null);
  const sessions = loaded && loaded.userId === userId ? loaded.sessions : undefined;

  useEffect(() => {
    if (!userId) return;
    let alive = true;
    fetchUserSessions(userId).then(
      (list) => {
        if (alive) setLoaded({ userId, sessions: list });
      },
      () => {
        if (alive) setLoaded({ userId, sessions: null });
      },
    );
    return () => {
      alive = false;
    };
  }, [userId]);

  if (!user) {
    return (
      <Screen>
        <Navbar />
        <Page>
          {user === null ? <LoginCard description={t("loginSessions")} /> : null}
        </Page>
      </Screen>
    );
  }

  return (
    <Screen>
      <Navbar />
      <Page>
        <Card>
          <Header>
            <Title>{t("myPage")}</Title>
          </Header>
          <Profile>
            <ProfileImage color={theme.colors.SLATE[600]} size={40} />
            <strong>{user.name}</strong>
            <Button variant="ghost" onClick={signOut}>
              {t("signOut")}
            </Button>
          </Profile>

          <SectionTitle>{t("mySessions")}</SectionTitle>
          {sessions === undefined ? <Note role="status">{t("loadingSessions")}</Note> : null}
          {sessions === null ? <Note role="alert">{t("sessionsError")}</Note> : null}
          {sessions && sessions.length === 0 ? <Note>{t("noSessions")}</Note> : null}
          {sessions && sessions.length > 0 ? (
            <List>
              {sessions.map((session) => {
                const done = session.phase === "ended";
                const path = session.phase === "discussion" || done ? "/chat" : "/";
                const href = `${path}?session=${encodeURIComponent(session.sessionId)}`;
                return (
                  <Item key={session.sessionId}>
                    <div>
                      <strong>{session.topic}</strong>
                      <Status $done={done}>{session.phase ? t(PHASE_LABEL[session.phase]) : t("unknown")}</Status>
                      <Note>
                        {t("sessionActivity", { count: session.messageCount, date: when(session.updatedAt, locale) })}
                      </Note>
                    </div>
                    <Button variant={done ? "ghost" : "primary"} onClick={() => router.push(href)}>
                      {done ? t("view") : t("continue")}
                      <ArrowRight size={16} aria-hidden="true" />
                    </Button>
                  </Item>
                );
              })}
            </List>
          ) : null}
          <Actions>
            <Button variant={sessions && sessions.length > 0 ? "ghost" : "primary"} onClick={() => router.push("/")}>
              <Plus size={16} aria-hidden="true" />
              {t("startNew")}
            </Button>
          </Actions>
        </Card>
      </Page>
    </Screen>
  );
}
