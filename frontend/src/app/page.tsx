"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, CornerDownLeft } from "lucide-react";
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
import type { Phase } from "@/lib/csl";

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

const CodeField = styled.div`
  max-width: 320px;
`;

const STEPS = ["Initial question", "Learning direction", "Classroom setup"];

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
  const router = useRouter();
  const theme = useTheme();
  // Signing in comes first: every session started here belongs to a user (undefined = not known yet).
  const user = useCurrentUser();
  const sessionId = useCurrentSessionId();
  const { snapshot, connection, error, actions } = useCslSession(sessionId ?? null);
  const [topic, setTopic] = useState("");
  const [draft, setDraft] = useState("");
  const [accessCode, setAccessCode] = useState("");
  const [needsCode, setNeedsCode] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  // A step the learner went back to; forgotten as soon as the session moves to another phase.
  const [manual, setManual] = useState<{ phase: Phase | null; step: number } | null>(null);

  const phase = snapshot?.phase ?? null;

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
            <LoginCard description="Enter a nickname to start a learning session. Your sessions are kept under it, so you can leave and continue later, from any browser." />
          ) : null}
        </Page>
      </Screen>
    );
  }

  const phaseStep = phase === "building" ? 1 : phase === "init" || phase === null ? 0 : 2;
  const step = manual && manual.phase === phase ? Math.min(manual.step, phaseStep) : phaseStep;
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
    if (!value || creating) return;
    setCreating(true);
    setCreateError(null);
    try {
      // /?pipeline=mock runs the scripted scenario (free, no access code): for trying the UI.
      const pipeline = new URLSearchParams(window.location.search).get("pipeline");
      const code = accessCode.trim();
      const created = await createSession({ topic: value, accessCode: code || null, pipeline: pipeline || null });
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
              basis: participant.origin ?? "A way of thinking about this topic",
              belief: initial ? `“${initial}”` : (participant.description ?? ""),
              note: participant.description ?? undefined,
            };
          }),
        ...snapshot.participants
          .filter((participant) => participant.role === "tutor")
          .map((participant) => ({
            name: participant.name,
            peerIndex: null,
            basis: "Discussion guidance and explanation checking",
            belief: "“What evidence would help us test these explanations?”",
            note: "Helps compare assumptions and evidence to build understanding.",
          })),
      ]
    : undefined;

  const problem = error ? (
    <ErrorNote role="alert">
      {error.message}
      <Button variant="ghost" onClick={actions.resume}>
        Try again
      </Button>
    </ErrorNote>
  ) : null;

  // What "Next" does on the step the session is actually at.
  const atCurrent = step === phaseStep;
  const nextDisabled = !atCurrent
    ? false
    : !sessionId
      ? creating || !topic.trim()
      : phase === "init"
        ? connection !== "open"
        : phase !== "ready";
  const next = () => {
    if (!atCurrent) return goTo(step + 1);
    if (!sessionId) return void start();
    if (phase === "init") return void actions.finishInit(); // skip the rest of the setup chat
    if (phase === "ready") router.push(`/chat?session=${encodeURIComponent(sessionId)}`);
  };

  return (
    <Screen>
      <Navbar />
      <Page>
        <Card>
          <Header>
            <Title>Learning session preparation</Title>
            <span>{step + 1} / 3</span>
          </Header>
          <Progress>
            <Stepper steps={STEPS} current={step} onStepClick={goTo} />
          </Progress>
          {missing ? (
            <ErrorNote role="alert">
              This session could not be opened.
              <Button variant="ghost" onClick={() => setCurrentSessionId(null)}>
                Start over
              </Button>
            </ErrorNote>
          ) : opening ? (
            <Loading role="status">Opening your session…</Loading>
          ) : step === 0 ? (
            <>
              {sessionId ? null : (
                <>
                  <TopicForm
                    onSubmit={(event) => {
                      event.preventDefault();
                      void start();
                    }}
                  >
                    <TextField
                      id="topic"
                      label="Topic"
                      value={topic}
                      onChange={setTopic}
                      placeholder="Enter a topic to learn"
                    />
                    <Button
                      type="submit"
                      aria-label="Enter topic"
                      title="Enter topic"
                      disabled={creating || !topic.trim()}
                    >
                      <CornerDownLeft size={20} aria-hidden="true" />
                    </Button>
                  </TopicForm>
                  {needsCode ? (
                    <CodeField>
                      <TextField id="access-code" label="Access code" value={accessCode} onChange={setAccessCode} />
                    </CodeField>
                  ) : null}
                  {creating ? <Loading role="status">Starting your session…</Loading> : null}
                  {createError ? <ErrorNote role="alert">Could not start the session: {createError}</ErrorNote> : null}
                </>
              )}
              {sessionId && shownTopic ? (
                <ChatLine $own>
                  <MessageBubble role="user" speaker="You">
                    {shownTopic}
                  </MessageBubble>
                </ChatLine>
              ) : null}
              {initMessages.map((message) => {
                const own = message.role === "user";
                return (
                  <ChatLine key={message.id} $own={own}>
                    {own ? null : <ProfileImage color={theme.colors.BLUE[900]} />}
                    <MessageBubble role={own ? "user" : "system"} speaker={own ? "You" : message.speakerName}>
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
              {problem}
              {sessionId ? (
                <Composer
                  value={draft}
                  onChange={setDraft}
                  placeholder="Reply to the guide…"
                  disabled={phase !== "init" || connection !== "open"}
                  onSubmit={() => {
                    actions.replyInit(draft.trim());
                    setDraft("");
                  }}
                />
              ) : null}
            </>
          ) : step === 2 ? (
            <ClassroomOverview topic={shownTopic || "your topic"} participants={overview} />
          ) : (
            <div>
              <h2>{shownTopic}</h2>
              <Direction>
                Learning direction:{" "}
                {snapshot?.focus ??
                  `explore ${shownTopic || "your topic"} through explanations, questions, and discussion with your classroom.`}
              </Direction>
              {phase === "building" ? (
                (problem ?? <Loading role="status">Preparing your classroom…</Loading>)
              ) : (
                <Direction role="status">Your classroom is ready.</Direction>
              )}
            </div>
          )}
          <Actions>
            <Button variant="ghost" disabled={step === 0} onClick={() => goTo(step - 1)}>
              <ArrowLeft size={16} aria-hidden="true" />
              Back
            </Button>
            <Button
              disabled={nextDisabled}
              title={atCurrent && phase === "init" ? "Skip the rest of the setup chat" : undefined}
              onClick={next}
            >
              {step >= 2 ? "Start learning session" : "Next"}
              {step >= 2 ? <ArrowRight size={16} aria-hidden="true" /> : null}
            </Button>
          </Actions>
        </Card>
      </Page>
    </Screen>
  );
}
