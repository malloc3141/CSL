"use client";

// Integration check for the backend connection (src/lib/csl). Not the product UI:
// it shows every piece of state the server sends, with the existing common components.

import { useEffect, useState } from "react";
import styled, { useTheme } from "styled-components";
import { Button, Composer, MessageBubble, ProfileImage, TextField } from "@/common/components";
import {
  createSession,
  fetchHealth,
  fetchUserSessions,
  forgetSession,
  rememberSession,
  setCurrentSessionId,
  signIn,
  signOut,
  useCslSession,
  useCurrentSessionId,
  useCurrentUser,
  useRecentSessions,
} from "@/lib/csl";
import type { Accuracy, Health, Language, Role, SessionSummary, StateVersion } from "@/lib/csl";
import { LanguageButton } from "@/common/components/Navbar";
import { useI18n } from "@/i18n";
import { peerColor } from "@/styles/peerColors";

const Page = styled.main`
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 16px;
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px;
`;

const Card = styled.section`
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 20px;
  border: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  border-radius: ${({ theme }) => theme.round.md};
  background: ${({ theme }) => theme.colors.WHITE};
`;

const Side = styled.div`
  display: flex;
  flex-direction: column;
  gap: 16px;
`;

const Row = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
`;

const Meta = styled.p`
  margin: 0;
  color: ${({ theme }) => theme.colors.GRAY[500]};
  font-size: 13px;
`;

const ErrorText = styled.p`
  margin: 0;
  color: ${({ theme }) => theme.colors.ROSE[900]};
  font-size: 13px;
`;

const ChatLine = styled.div<{ $own: boolean }>`
  display: flex;
  align-items: flex-end;
  justify-content: ${({ $own }) => ($own ? "flex-end" : "flex-start")};
  gap: 8px;
`;

const Heading = styled.h2`
  margin: 0;
  font-size: 15px;
`;

const StateList = styled.ul`
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
`;

const ACCURACY_MARK: Record<Accuracy, string> = { correct: "○", partial: "△", incorrect: "✕" };

function mark(accuracy: Accuracy | null) {
  return accuracy ? `${ACCURACY_MARK[accuracy]} ` : "";
}

function Line(props: { role: Role; speaker: string; peerIndex: number | null; text: string }) {
  const theme = useTheme();
  const { role, speaker, peerIndex, text } = props;
  const color =
    role === "user" ? null : role === "peer" ? peerColor(theme, peerIndex ?? 0)[900] : theme.colors.BLUE[900];
  return (
    <ChatLine $own={role === "user"}>
      {color ? <ProfileImage color={color} /> : null}
      <MessageBubble role={role} speaker={speaker} peerIndex={peerIndex ?? 0}>
        {text}
      </MessageBubble>
    </ChatLine>
  );
}

function StatePanel({ name, versions }: { name: string; versions: StateVersion[] }) {
  const { t } = useI18n();
  const current = versions[versions.length - 1];
  const { state } = current;
  return (
    <Card>
      <Heading>
        {name} · v{current.version}
        {current.turnNumber ? ` (${t("changedTurn", { turn: current.turnNumber })})` : ""}
      </Heading>
      <Meta>{t("currentBeliefs")}</Meta>
      <StateList>
        {state.beliefs.map((belief) => (
          <li key={belief.id}>
            {mark(belief.accuracy)}
            {belief.text}
          </li>
        ))}
      </StateList>
      <Meta>{t("currentExplanation")}</Meta>
      <StateList>
        <li>
          {mark(state.explanationAccuracy)}
          {state.explanation}
        </li>
      </StateList>
      {state.openQuestions.length > 0 ? (
        <>
          <Meta>{t("openQuestions")}</Meta>
          <StateList>
            {state.openQuestions.map((question) => (
              <li key={question}>{question}</li>
            ))}
          </StateList>
        </>
      ) : null}
    </Card>
  );
}

function when(seconds: number, locale: string) {
  return new Date(seconds * 1000).toLocaleString(locale, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

// The session id lives in the URL (?session=<id>), so a reload or the back button returns to the
// same session. See src/lib/csl/browserSession.ts.
export default function DevPage() {
  const { t } = useI18n();
  const sessionId = useCurrentSessionId();
  if (sessionId === undefined) {
    return (
      <Page>
        <Card>
          <Meta>{t("loading")}</Meta>
        </Card>
      </Page>
    );
  }
  return (
    <>
      <LanguageButton />
      {sessionId === null ? <StartForm /> : <SessionView key={sessionId} sessionId={sessionId} />}
    </>
  );
}

function StartForm() {
  const { locale, t } = useI18n();
  const [topic, setTopic] = useState("Why is summer hotter than winter?");
  const [language, setLanguage] = useState<Language>("en");
  // "" = the server's default pipeline; otherwise a name from health.sessionPipelines.
  const [pipeline, setPipeline] = useState("");
  const [accessCode, setAccessCode] = useState("");
  const [health, setHealth] = useState<Health | null>(null);
  const [busy, setBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const recent = useRecentSessions();

  // Signing in is optional on this page. Signed in, new sessions are recorded as the user's and the
  // list of their sessions comes from the server (any browser); otherwise only this browser remembers.
  const user = useCurrentUser();
  const userId = user?.userId ?? null;
  const [nickname, setNickname] = useState("");
  const [signingIn, setSigningIn] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [mine, setMine] = useState<{ userId: string; sessions: SessionSummary[] } | null>(null);
  const mySessions = mine && mine.userId === userId ? mine.sessions : null;

  useEffect(() => {
    if (!userId) return;
    let alive = true;
    fetchUserSessions(userId).then(
      (sessions) => {
        if (alive) setMine({ userId, sessions });
      },
      () => {}, // an unknown user is signed out by fetchUserSessions itself
    );
    return () => {
      alive = false;
    };
  }, [userId]);

  const login = async () => {
    setSigningIn(true);
    setLoginError(null);
    try {
      await signIn(nickname);
      setNickname("");
    } catch (cause) {
      setLoginError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSigningIn(false);
    }
  };

  useEffect(() => {
    let alive = true;
    fetchHealth().then(
      (value) => {
        if (alive) setHealth(value);
      },
      () => {}, // the selector falls back to "server default" and "mock"
    );
    return () => {
      alive = false;
    };
  }, []);

  const named = health ? health.sessionPipelines.filter((name) => name !== health.pipeline) : ["mock"];
  const free = health ? health.freePipelines.includes(pipeline) : pipeline === "mock";

  const start = async () => {
    setBusy(true);
    setCreateError(null);
    try {
      const created = await createSession({
        topic,
        language,
        accessCode: free ? null : accessCode || null,
        pipeline: pipeline || null,
      });
      const { snapshot } = created;
      // A signed-in user's session is in their list on the server; a guest's is remembered here.
      if (!snapshot.userId) {
        rememberSession({
          sessionId: created.sessionId,
          topic: snapshot.topic,
          pipeline: snapshot.pipeline,
          createdAt: snapshot.createdAt,
        });
      }
      setCurrentSessionId(created.sessionId);
    } catch (cause) {
      setCreateError(cause instanceof Error ? cause.message : String(cause));
      setBusy(false);
    }
  };

  return (
    <Page>
      <Card>
        <Heading>{t("connectionCheck")}</Heading>
        <TextField id="topic" label={t("topic")} value={topic} onChange={setTopic} />
        <Row>
          <Meta>{t("discussionLanguage")}</Meta>
          <select
            value={language}
            onChange={(event) => setLanguage(event.target.value as Language)}
            aria-label={t("discussionLanguage")}
          >
            <option value="en">{t("english")}</option>
            <option value="ko">{t("korean")}</option>
          </select>
        </Row>
        <Row>
          <Meta>{t("agents")}</Meta>
          <select value={pipeline} onChange={(event) => setPipeline(event.target.value)} aria-label={t("agents")}>
            <option value="">{t("serverDefault")}{health ? ` (${health.pipeline})` : ""}</option>
            {named.map((name) => (
              <option key={name} value={name}>
                {name}
                {(health ? health.freePipelines.includes(name) : name === "mock") ? t("freeScripted") : ""}
              </option>
            ))}
          </select>
        </Row>
        {pipeline === "mock" ? (
          <Meta>
            {t("mockNote")}
          </Meta>
        ) : null}
        {free ? null : (
          <TextField
            id="code"
            label={t("optionalAccess")}
            value={accessCode}
            onChange={setAccessCode}
          />
        )}
        <Row>
          <Button onClick={start} disabled={busy || !topic.trim()}>
            {busy ? t("starting") : t("startSession")}
          </Button>
        </Row>
        {createError ? <ErrorText>{t("createFailed")} {createError}</ErrorText> : null}
      </Card>

      <Side>
        <Card>
          <Heading>{t("account")}</Heading>
          {user ? (
            <>
              <Row>
                <Meta style={{ flex: 1 }}>
                  {t("signedInAs", { name: user.name })}
                </Meta>
                <Button variant="ghost" onClick={signOut}>
                  {t("signOut")}
                </Button>
              </Row>
              <Meta>{t("accountNote")}</Meta>
            </>
          ) : (
            <>
              <TextField id="nickname" label={t("optionalNickname")} value={nickname} onChange={setNickname} />
              <Row>
                <Button onClick={login} disabled={signingIn || nickname.trim().length < 2}>
                  {signingIn ? t("signingIn") : t("signIn")}
                </Button>
              </Row>
              {loginError ? <ErrorText>{t("loginFailed")} {loginError}</ErrorText> : null}
              <Meta>
                {t("devLoginNote")}
              </Meta>
            </>
          )}
        </Card>

        {user && mySessions ? (
          <Card>
            <Heading>{t("mySessions")}</Heading>
            {mySessions.length === 0 ? <Meta>{t("startOnLeft")}</Meta> : null}
            {mySessions.map((item) => (
              <Row key={item.sessionId}>
                <Meta style={{ flex: 1 }}>
                  {item.topic} · {item.pipeline ?? "?"} · {item.phase}
                  {item.phase === "discussion" ? ` (${item.status})` : ""} · {t("messageCount", { count: item.messageCount })} ·{" "}
                  {when(item.updatedAt, locale)}
                </Meta>
                <Button variant="ghost" onClick={() => setCurrentSessionId(item.sessionId)}>
                  {item.phase === "ended" ? t("view") : t("resume")}
                </Button>
              </Row>
            ))}
          </Card>
        ) : null}

        {recent.length > 0 ? (
          <Card>
            <Heading>{t("browserSessions")}</Heading>
            {recent.map((item) => (
              <Row key={item.sessionId}>
                <Meta style={{ flex: 1 }}>
                  {item.topic} · {item.pipeline || "?"} · {when(item.createdAt, locale)}
                </Meta>
                <Button variant="ghost" onClick={() => setCurrentSessionId(item.sessionId)}>
                  {t("resume")}
                </Button>
                <Button variant="ghost" onClick={() => forgetSession(item.sessionId)}>
                  {t("forget")}
                </Button>
              </Row>
            ))}
            <Meta>
              {t("browserSessionsNote")}
            </Meta>
          </Card>
        ) : null}
      </Side>
    </Page>
  );
}

function SessionView({ sessionId }: { sessionId: string }) {
  const { t } = useI18n();
  const [draft, setDraft] = useState("");
  const { snapshot, connection, error, actions } = useCslSession(sessionId);
  // Leaving closes the socket; the server pauses the discussion and keeps the session.
  const leave = () => setCurrentSessionId(null);

  if (!snapshot) {
    const missing = connection === "closed";
    return (
      <Page>
        <Card>
          <Heading>{missing ? t("devOpenError") : t("connecting")}</Heading>
          <Meta>
            {missing
              ? t("missingSession", { id: sessionId })
              : t("connectingSession", { id: sessionId, connection })}
          </Meta>
          <Row>
            <Button
              onClick={() => {
                if (missing) forgetSession(sessionId);
                leave();
              }}
            >
              {missing ? t("startNew") : t("leave")}
            </Button>
          </Row>
        </Card>
      </Page>
    );
  }

  const { phase, status, pace, activeTurn } = snapshot;
  const channel = phase === "init" || phase === "building" ? "init" : "discussion";
  const messages = snapshot.messages.filter((message) => message.channel === channel);
  const peers = snapshot.participants.filter((participant) => participant.role === "peer");
  const canType = phase === "init" || phase === "discussion";

  const submit = () => {
    if (phase === "init") actions.replyInit(draft);
    else actions.say(draft);
    setDraft("");
  };

  return (
    <Page>
      <Card>
        <Meta>
          {t("sessionStatus", { pipeline: snapshot.pipeline || "?", phase, status, connection, count: snapshot.messages.length })}
        </Meta>
        {snapshot.focus ? <Meta>{t("focusLabel")} {snapshot.focus}</Meta> : null}
        {error ? (
          <ErrorText>
            {error.code}: {error.message}
          </ErrorText>
        ) : null}

        {phase === "ready"
          ? snapshot.participants.map((participant) => (
              <Meta key={participant.id}>
                <b>{participant.name}</b> — {participant.origin} / {participant.description}
              </Meta>
            ))
          : null}

        {messages.map((message) => (
          <Line
            key={message.id}
            role={message.role}
            speaker={message.turnNumber ? `${message.turnNumber}. ${message.speakerName}` : message.speakerName}
            peerIndex={message.peerIndex}
            text={message.text}
          />
        ))}
        {activeTurn && activeTurn.channel === channel ? (
          <Line
            role={activeTurn.role}
            speaker={activeTurn.speakerName}
            peerIndex={activeTurn.peerIndex}
            text={activeTurn.text || t("typing")}
          />
        ) : null}
        {phase === "building" ? <Meta>{t("buildingClassroom")}</Meta> : null}
        {snapshot.invitedTurnId ? <Meta>{t("tutorWaiting")}</Meta> : null}

        {canType ? (
          <Composer
            value={draft}
            onChange={setDraft}
            onSubmit={submit}
            placeholder={phase === "init" ? t("replyGuide") : t("joinDiscussion")}
          />
        ) : null}

        <Row>
          {phase === "init" ? (
            <Button variant="ghost" onClick={actions.finishInit}>
              {t("skipSetupShort")}
            </Button>
          ) : null}
          {phase === "ready" ? <Button onClick={() => actions.startDiscussion()}>{t("startDiscussion")}</Button> : null}
          {phase === "discussion" ? (
            <>
              {status === "running" ? (
                <Button variant="ghost" onClick={actions.pause}>
                  {t("pause")}
                </Button>
              ) : (
                <Button onClick={actions.resume}>{t("resume")}</Button>
              )}
              <Button variant="ghost" onClick={actions.step}>
                {t("nextMessage")}
              </Button>
              <Button variant="ghost" onClick={() => actions.setPace({ auto: !pace.auto })}>
                {t("autoAdvanceLabel")} {pace.auto ? t("on") : t("off")}
              </Button>
              {[0.5, 1, 2].map((speed) => (
                <Button
                  key={speed}
                  variant={pace.speed === speed ? "primary" : "ghost"}
                  onClick={() => actions.setPace({ speed })}
                >
                  {speed}x
                </Button>
              ))}
              <Button variant="ghost" onClick={actions.end}>
                {t("end")}
              </Button>
            </>
          ) : null}
          {phase === "building" && error ? <Button onClick={actions.resume}>{t("retry")}</Button> : null}
          <span style={{ flex: 1 }} />
          <Button variant={phase === "ended" ? "primary" : "ghost"} onClick={leave}>
            {phase === "ended" ? t("newSession") : t("leaveSession")}
          </Button>
        </Row>
        <Meta>
          {phase === "ended"
            ? t("sessionEnded")
            : t("leaveHint")}
        </Meta>
      </Card>

      <div>
        {peers.map((peer) =>
          snapshot.states[peer.id] ? (
            <StatePanel key={peer.id} name={peer.name} versions={snapshot.states[peer.id]} />
          ) : null,
        )}
      </div>
    </Page>
  );
}
