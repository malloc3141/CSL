"use client";

import { useI18n } from "@/i18n";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, ChevronDown, CornerDownLeft } from "lucide-react";
import { ClassroomOverview } from "@/common/components/ClassroomOverview";
import type { OverviewParticipant } from "@/common/components/ClassroomOverview";
import styled, { keyframes, useTheme } from "styled-components";
import {
  MessageBubble,
  Button,
  Composer,
  ProfileImage,
  Stepper,
  TextField,
  Navbar,
  LoginCard,
} from "@/common/components";
import {
  createSession,
  fetchHealth,
  setCurrentSessionId,
  useCslSession,
  useCurrentSessionId,
  useCurrentUser,
} from "@/lib/csl";
import type { Language, Phase } from "@/lib/csl";

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
  flex: 1;
  gap: 20px;
  width: 100%;
  min-width: 0;
  max-width: 1040px;
  margin: 0 auto;
  padding-inline: clamp(0px, 4vw, 64px);
`;

const Title = styled.h1`
  margin: 0;
  font-size: 28px;
  font-weight: 700;
  overflow-wrap: anywhere;
`;

const Direction = styled.p`
  margin: 0;
  color: ${({ theme }) => theme.colors.SLATE[600]};
  line-height: 1.7;
`;

const spin = keyframes`
  to { transform: rotate(360deg); }
`;

const Loading = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  padding-block: 16px;
  color: ${({ theme }) => theme.colors.GRAY[500]};
  font-size: 14px;

  &::before {
    content: "";
    width: 24px;
    height: 24px;
    flex-shrink: 0;
    border: 3px solid ${({ theme }) => theme.colors.GRAY[200]};
    border-top-color: ${({ theme }) => theme.colors.SLATE[600]};
    border-radius: 50%;
    animation: ${spin} 1s linear infinite;
  }

  @media (prefers-reduced-motion: reduce) {
    &::before { animation: none; }
  }
`;

const Progress = styled.div`
  padding-inline: 12px;
`;

const TopicForm = styled.form`
  display: flex;
  align-items: flex-end;
  gap: 12px;

  > label {
    flex: 1;
    min-width: 0;
  }

  input {
    min-width: 0;
    width: 100%;
  }

  > button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    min-height: 43px;
    flex-shrink: 0;
  }
`;

const InitTranscript = styled.div`
  display: flex;
  flex-direction: column;
  gap: 20px;
  flex: none;
  height: clamp(240px, 48dvh, 480px);
  overflow-y: auto;

  > * {
    flex-shrink: 0;
  }
`;

const ChatLine = styled.div<{ $own?: boolean }>`
  display: flex;
  align-items: flex-end;
  justify-content: ${({ $own }) => ($own ? "flex-end" : "flex-start")};
  gap: 8px;
`;

const Actions = styled.div`
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: auto;
  padding-top: 32px;

  > button {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }
`;

const Header = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;

  > span {
    flex-shrink: 0;
    color: ${({ theme }) => theme.colors.GRAY[500]};
    font-size: 13px;
  }
`;

const ErrorNote = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  color: ${({ theme }) => theme.colors.ROSE[900]};
  font-size: 14px;
`;

const LanguageField = styled.label`
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  font-weight: 600;

  select {
    appearance: none;
    padding: 8px 36px 8px 12px;
    border: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
    border-radius: ${({ theme }) => theme.round.sm};
    background: ${({ theme }) => theme.colors.WHITE};
    color: inherit;
    font: inherit;
  }
`;

const LanguageSelect = styled.span`
  position: relative;
  display: inline-flex;
  align-items: center;

  svg {
    position: absolute;
    inset-inline-end: 12px;
    pointer-events: none;
  }
`;

const CodeField = styled.div`
  max-width: 320px;
`;

const ACCESS_CODE_KEY = "csl.accessCode";

function readAccessCode(): string {
  try {
    return localStorage.getItem(ACCESS_CODE_KEY) ?? "";
  } catch {
    return "";
  }
}

function rememberAccessCode(code: string) {
  try {
    localStorage.setItem(ACCESS_CODE_KEY, code);
  } catch {
    // storage unavailable: the code has to be typed again next time
  }
}

// The three steps follow the session's phase on the server:
//   Initial question   = "init"      the topic, then the setup chat with the guide
//   Learning direction = "building"  the classroom is being created
//   Classroom setup    = "ready"     the participants; "Start learning session" opens /chat
// The session id is kept in the URL (?session=<id>), so a reload returns to the same step.
export default function Home() {
  const { t } = useI18n();
  const router = useRouter();
  const theme = useTheme();
  // Signing in comes first: every session started here belongs to a user (undefined = not known yet).
  const user = useCurrentUser();
  const sessionId = useCurrentSessionId();
  const { snapshot, connection, error, actions } = useCslSession(sessionId ?? null);
  const { t: discussionT } = useI18n(snapshot?.language);
  const [topic, setTopic] = useState("");
  const [discussionLanguage, setDiscussionLanguage] = useState<Language | "">("");
  const [draft, setDraft] = useState("");
  const [accessCode, setAccessCode] = useState("");
  const [needsCode, setNeedsCode] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  // A step the learner went back to; forgotten as soon as the session moves to another phase.
  const [manual, setManual] = useState<{ phase: Phase | null; step: number } | null>(null);

  const transcript = useRef<HTMLDivElement>(null);
  const phase = snapshot?.phase ?? null;
  const phaseStep = phase === "building" ? 1 : phase === "init" || phase === null ? 0 : 2;
  const step = manual && manual.phase === phase ? Math.min(manual.step, phaseStep) : phaseStep;

  useLayoutEffect(() => {
    // Next.js preserves this page's state when it hides the route during navigation.
    return () => {
      setTopic("");
      setDiscussionLanguage("");
      setDraft("");
      setCreateError(null);
      setManual(null);
    };
  }, [sessionId]);

  useEffect(() => {
    const element = transcript.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [snapshot, step, user]);

  useEffect(() => {
    let alive = true;
    fetchHealth().then(
      (health) => {
        if (!alive || !health.accessCodeRequired) return;
        setNeedsCode(true);
        setAccessCode(readAccessCode());
      },
      () => {}, // the server will say so if a code was needed
    );
    return () => {
      alive = false;
    };
  }, []);

  // The discussion itself happens on the classroom page.
  useEffect(() => {
    if (sessionId && (phase === "discussion" || phase === "ended")) {
      router.replace(`/chat?session=${encodeURIComponent(sessionId)}`);
    }
  }, [phase, sessionId, router]);

  if (!user) {
    return (
      <Screen>
        <Navbar />
        <Page>
          {user === null ? (
            <LoginCard description={t("loginStart")} />
          ) : null}
        </Page>
      </Screen>
    );
  }

  const goTo = (next: number) => {
    if (next >= 0 && next <= phaseStep) setManual({ phase, step: next });
  };

  const shownTopic = snapshot?.topic ?? topic.trim();
  const missing = Boolean(sessionId) && !snapshot && connection === "closed";
  const opening = Boolean(sessionId) && !snapshot && !missing;
  const initMessages = snapshot ? snapshot.messages.filter((message) => message.channel === "init") : [];
  const typing = snapshot?.activeTurn?.channel === "init" ? snapshot.activeTurn : null;

  const start = async () => {
    const value = topic.trim();
    if (!discussionLanguage || !value || creating) return;
    setCreating(true);
    setCreateError(null);
    try {
      // /?pipeline=mock runs the scripted scenario (free, no access code): for trying the UI.
      const pipeline = new URLSearchParams(window.location.search).get("pipeline");
      const code = accessCode.trim();
      const created = await createSession({
        topic: value,
        language: discussionLanguage,
        accessCode: code || null,
        pipeline: pipeline || null,
      });
      if (code) rememberAccessCode(code);
      setCurrentSessionId(created.sessionId);
    } catch (cause) {
      setCreateError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setCreating(false);
    }
  };

  const overview: OverviewParticipant[] | undefined = snapshot
    ? [
        ...snapshot.participants
          .filter((participant) => participant.role === "peer")
          .map((participant) => {
            const initial = snapshot.states[participant.id]?.[0]?.state.explanation;
            return {
              name: participant.name,
              peerIndex: participant.peerIndex ?? 0,
              basis: participant.origin ?? t("peerBasis"),
              belief: initial ? `“${initial}”` : (participant.description ?? ""),
              note: participant.description ?? undefined,
            };
          }),
        ...snapshot.participants
          .filter((participant) => participant.role === "tutor")
          .map((participant) => ({
            name: participant.name,
            peerIndex: null,
            basis: discussionT("tutorBasis"),
            belief: discussionT("tutorBelief"),
            note: discussionT("tutorNote"),
          })),
      ]
    : undefined;

  const problem = error ? (
    <ErrorNote role="alert">
      {error.message}
      <Button variant="ghost" onClick={actions.resume}>
        {t("tryAgain")}
      </Button>
    </ErrorNote>
  ) : null;

  // What "Next" does on the step the session is actually at.
  const atCurrent = step === phaseStep;
  const nextDisabled = !atCurrent
    ? false
    : !sessionId
      ? creating || !discussionLanguage || !topic.trim()
      : phase === "init"
        ? connection !== "open"
        : phase !== "ready" || connection !== "open";
  const next = () => {
    if (!atCurrent) return goTo(step + 1);
    if (!sessionId) return void start();
    if (phase === "init") return void actions.finishInit(); // skip the rest of the setup chat
    if (phase === "ready") actions.startDiscussion();
  };

  return (
    <Screen>
      <Navbar />
      <Page>
        <Card>
          <Header>
            <Title>{t("setupTitle")}</Title>
            <span>{step + 1} / 3</span>
          </Header>
          <Progress>
            <Stepper steps={[t("initialQuestion"), t("learningDirection"), t("classroomSetup")]} current={step} onStepClick={goTo} />
          </Progress>
          {missing ? (
            <ErrorNote role="alert">
              {t("openError")}
              <Button variant="ghost" onClick={() => setCurrentSessionId(null)}>
                {t("startOver")}
              </Button>
            </ErrorNote>
          ) : opening ? (
            <Loading role="status">{t("openingSession")}</Loading>
          ) : step === 0 ? (
            <>
              {sessionId ? null : (
                <>
                  <LanguageField>
                    {t("discussionLanguage")}
                    <LanguageSelect>
                      <select
                        value={discussionLanguage}
                        onChange={(event) => setDiscussionLanguage(event.target.value === "ko" ? "ko" : "en")}
                        disabled={creating}
                      >
                        <option value="" disabled>{t("chooseDiscussionLanguage")}</option>
                        <option value="en">{t("english")}</option>
                        <option value="ko">{t("korean")}</option>
                      </select>
                      <ChevronDown size={16} aria-hidden="true" />
                    </LanguageSelect>
                  </LanguageField>
                  {discussionLanguage ? (
                    <TopicForm
                      onSubmit={(event) => {
                        event.preventDefault();
                        void start();
                      }}
                    >
                      <TextField
                        id="topic"
                        label={t("topic")}
                        value={topic}
                        onChange={setTopic}
                        placeholder={t("topicPlaceholder")}
                      />
                      <Button
                        type="submit"
                        aria-label={t("enterTopic")}
                        title={t("enterTopic")}
                        disabled={creating || !topic.trim()}
                      >
                        <CornerDownLeft size={20} aria-hidden="true" />
                      </Button>
                    </TopicForm>
                  ) : null}
                  {discussionLanguage && needsCode ? (
                    <CodeField>
                      <TextField id="access-code" label={t("accessCode")} value={accessCode} onChange={setAccessCode} />
                    </CodeField>
                  ) : null}
                  {creating ? <Loading role="status">{t("startingSession")}</Loading> : null}
                  {createError ? <ErrorNote role="alert">{t("startError", { error: createError })}</ErrorNote> : null}
                </>
              )}
              {sessionId ? (
                <InitTranscript ref={transcript} role="region" aria-label={t("initialMessages")} tabIndex={0}>
                  {shownTopic ? (
                    <ChatLine $own>
                      <MessageBubble role="user" speaker={t("you")}>
                        {shownTopic}
                      </MessageBubble>
                    </ChatLine>
                  ) : null}
                  {initMessages.map((message) => {
                    const own = message.role === "user";
                    return (
                      <ChatLine key={message.id} $own={own}>
                        {own ? null : <ProfileImage color={theme.colors.BLUE[900]} />}
                        <MessageBubble role={own ? "user" : "system"} speaker={own ? t("you") : message.speakerName}>
                          {message.text}
                        </MessageBubble>
                      </ChatLine>
                    );
                  })}
                  {typing ? (
                    <ChatLine>
                      <ProfileImage color={theme.colors.BLUE[900]} />
                      <MessageBubble role="system" speaker={typing.speakerName}>
                        {typing.text || "…"}
                      </MessageBubble>
                    </ChatLine>
                  ) : null}
                </InitTranscript>
              ) : null}
              {problem}
              {sessionId ? (
                <Composer
                  value={draft}
                  onChange={setDraft}
                  placeholder={t("replyGuide")}
                  disabled={phase !== "init" || connection !== "open"}
                  onSubmit={() => {
                    actions.replyInit(draft.trim());
                    setDraft("");
                  }}
                />
              ) : null}
            </>
          ) : step === 2 ? (
            <ClassroomOverview
              topic={shownTopic || t("defaultTopic")}
              participants={overview}
              discussionLanguage={snapshot?.language}
            />
          ) : (
            <div>
              <h2>{shownTopic}</h2>
              <Direction>
                {t("learningDirection")}: {snapshot?.focus ?? t("defaultDirection", { topic: shownTopic || t("defaultTopic") })}
              </Direction>
              {phase === "building" ? (
                (problem ?? <Loading role="status">{t("preparingClassroom")}</Loading>)
              ) : (
                <Direction role="status">{t("classroomReady")}</Direction>
              )}
            </div>
          )}
          <Actions>
            <Button variant="ghost" disabled={step === 0} onClick={() => goTo(step - 1)}>
              <ArrowLeft size={16} aria-hidden="true" />
              {t("back")}
            </Button>
            <Button
              disabled={nextDisabled}
              title={atCurrent && phase === "init" ? t("skipSetup") : undefined}
              onClick={next}
            >
              {step >= 2 ? t("startLearning") : t("next")}
              <ArrowRight size={16} aria-hidden="true" />
            </Button>
          </Actions>
        </Card>
      </Page>
    </Screen>
  );
}
