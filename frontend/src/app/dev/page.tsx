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
  const current = versions[versions.length - 1];
  const { state } = current;
  return (
    <Card>
      <Heading>
        {name} · v{current.version}
        {current.turnNumber ? ` (changed in turn ${current.turnNumber})` : ""}
      </Heading>
      <Meta>Current beliefs</Meta>
      <StateList>
        {state.beliefs.map((belief) => (
          <li key={belief.id}>
            {mark(belief.accuracy)}
            {belief.text}
          </li>
        ))}
      </StateList>
      <Meta>Current explanation</Meta>
      <StateList>
        <li>
          {mark(state.explanationAccuracy)}
          {state.explanation}
        </li>
      </StateList>
      {state.openQuestions.length > 0 ? (
        <>
          <Meta>Open questions</Meta>
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

function when(seconds: number) {
  return new Date(seconds * 1000).toLocaleString("en-US", {
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
  const sessionId = useCurrentSessionId();
  if (sessionId === undefined) {
    return (
      <Page>
        <Card>
          <Meta>Loading…</Meta>
        </Card>
      </Page>
    );
  }
  if (sessionId === null) return <StartForm />;
  return <SessionView key={sessionId} sessionId={sessionId} />;
}

function StartForm() {
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
        <Heading>Backend connection check</Heading>
        <TextField id="topic" label="Topic" value={topic} onChange={setTopic} />
        <Row>
          <Meta>Discussion language</Meta>
          <select
            value={language}
            onChange={(event) => setLanguage(event.target.value as Language)}
            aria-label="Discussion language"
          >
            <option value="en">English</option>
            <option value="ko">Korean</option>
          </select>
        </Row>
        <Row>
          <Meta>Agents</Meta>
          <select value={pipeline} onChange={(event) => setPipeline(event.target.value)} aria-label="Agents">
            <option value="">Server default{health ? ` (${health.pipeline})` : ""}</option>
            {named.map((name) => (
              <option key={name} value={name}>
                {name}
                {(health ? health.freePipelines.includes(name) : name === "mock") ? " (scripted, free)" : ""}
              </option>
            ))}
          </select>
        </Row>
        {pipeline === "mock" ? (
          <Meta>
            The mock replays a fixed scenario (&quot;Why is summer hotter than winter?&quot;) and ignores the topic. It
            makes no LLM calls and needs no access code.
          </Meta>
        ) : null}
        {free ? null : (
          <TextField
            id="code"
            label="Access code (if the server requires one)"
            value={accessCode}
            onChange={setAccessCode}
          />
        )}
        <Row>
          <Button onClick={start} disabled={busy || !topic.trim()}>
            {busy ? "Starting…" : "Start session"}
          </Button>
        </Row>
        {createError ? <ErrorText>Could not create the session: {createError}</ErrorText> : null}
      </Card>

      <Side>
        <Card>
          <Heading>Account</Heading>
          {user ? (
            <>
              <Row>
                <Meta style={{ flex: 1 }}>
                  Signed in as <b>{user.name}</b>
                </Meta>
                <Button variant="ghost" onClick={signOut}>
                  Sign out
                </Button>
              </Row>
              <Meta>Sessions you start now are kept under this nickname and can be continued from any browser.</Meta>
            </>
          ) : (
            <>
              <TextField id="nickname" label="Nickname (optional on this page)" value={nickname} onChange={setNickname} />
              <Row>
                <Button onClick={login} disabled={signingIn || nickname.trim().length < 2}>
                  {signingIn ? "Signing in…" : "Sign in"}
                </Button>
              </Row>
              {loginError ? <ErrorText>Could not sign in: {loginError}</ErrorText> : null}
              <Meta>
                No password. A new nickname creates an account; a known one signs in to it. Without signing in, a
                session is only remembered in this browser.
              </Meta>
            </>
          )}
        </Card>

        {user && mySessions ? (
          <Card>
            <Heading>My sessions</Heading>
            {mySessions.length === 0 ? <Meta>None yet. Start one on the left.</Meta> : null}
            {mySessions.map((item) => (
              <Row key={item.sessionId}>
                <Meta style={{ flex: 1 }}>
                  {item.topic} · {item.pipeline ?? "?"} · {item.phase}
                  {item.phase === "discussion" ? ` (${item.status})` : ""} · {item.messageCount} messages ·{" "}
                  {when(item.updatedAt)}
                </Meta>
                <Button variant="ghost" onClick={() => setCurrentSessionId(item.sessionId)}>
                  {item.phase === "ended" ? "View" : "Resume"}
                </Button>
              </Row>
            ))}
          </Card>
        ) : null}

        {recent.length > 0 ? (
          <Card>
            <Heading>Sessions started in this browser (not signed in)</Heading>
            {recent.map((item) => (
              <Row key={item.sessionId}>
                <Meta style={{ flex: 1 }}>
                  {item.topic} · {item.pipeline || "?"} · {when(item.createdAt)}
                </Meta>
                <Button variant="ghost" onClick={() => setCurrentSessionId(item.sessionId)}>
                  Resume
                </Button>
                <Button variant="ghost" onClick={() => forgetSession(item.sessionId)}>
                  Forget
                </Button>
              </Row>
            ))}
            <Meta>
              This list is kept in this browser only. A session can also be reopened with its link (the address of
              this page while the session is open).
            </Meta>
          </Card>
        ) : null}
      </Side>
    </Page>
  );
}

function SessionView({ sessionId }: { sessionId: string }) {
  const [draft, setDraft] = useState("");
  const { snapshot, connection, error, actions } = useCslSession(sessionId);
  // Leaving closes the socket; the server pauses the discussion and keeps the session.
  const leave = () => setCurrentSessionId(null);

  if (!snapshot) {
    const missing = connection === "closed";
    return (
      <Page>
        <Card>
          <Heading>{missing ? "This session cannot be opened" : "Connecting…"}</Heading>
          <Meta>
            {missing
              ? `Session ${sessionId} does not exist on this server (or this page's origin is not allowed).`
              : `Session ${sessionId} · socket: ${connection}`}
          </Meta>
          <Row>
            <Button
              onClick={() => {
                if (missing) forgetSession(sessionId);
                leave();
              }}
            >
              {missing ? "Start a new session" : "Leave"}
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
          pipeline: {snapshot.pipeline || "?"} · phase: {phase} · status: {status} · socket: {connection} · {snapshot.messages.length} messages
        </Meta>
        {snapshot.focus ? <Meta>focus: {snapshot.focus}</Meta> : null}
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
            text={activeTurn.text || "Typing…"}
          />
        ) : null}
        {phase === "building" ? <Meta>Building the classroom…</Meta> : null}
        {snapshot.invitedTurnId ? <Meta>The tutor is waiting for your explanation. (Resume = skip)</Meta> : null}

        {canType ? (
          <Composer
            value={draft}
            onChange={setDraft}
            onSubmit={submit}
            placeholder={phase === "init" ? "Reply to the guide…" : "Join the discussion…"}
          />
        ) : null}

        <Row>
          {phase === "init" ? (
            <Button variant="ghost" onClick={actions.finishInit}>
              Skip setup
            </Button>
          ) : null}
          {phase === "ready" ? <Button onClick={actions.startDiscussion}>Start discussion</Button> : null}
          {phase === "discussion" ? (
            <>
              {status === "running" ? (
                <Button variant="ghost" onClick={actions.pause}>
                  Pause
                </Button>
              ) : (
                <Button onClick={actions.resume}>Resume</Button>
              )}
              <Button variant="ghost" onClick={actions.step}>
                Next message
              </Button>
              <Button variant="ghost" onClick={() => actions.setPace({ auto: !pace.auto })}>
                Auto advance: {pace.auto ? "on" : "off"}
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
                End
              </Button>
            </>
          ) : null}
          {phase === "building" && error ? <Button onClick={actions.resume}>Retry</Button> : null}
          <span style={{ flex: 1 }} />
          <Button variant={phase === "ended" ? "primary" : "ghost"} onClick={leave}>
            {phase === "ended" ? "New session" : "Leave session"}
          </Button>
        </Row>
        <Meta>
          {phase === "ended"
            ? "This session has ended."
            : "Leaving does not end the session: it pauses, and this page's link or the list on the start page reopens it."}
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
