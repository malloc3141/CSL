"use client";

// Integration check for the backend connection (src/lib/csl). Not the product UI:
// it shows every piece of state the server sends, with the existing common components.

import { useState } from "react";
import styled, { useTheme } from "styled-components";
import { Button, Composer, MessageBubble, ProfileImage, TextField } from "@/common/components";
import { createSession, useCslSession } from "@/lib/csl";
import type { Accuracy, Language, Role, StateVersion } from "@/lib/csl";
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

export default function DevPage() {
  const [topic, setTopic] = useState("Why is summer hotter than winter?");
  const [language, setLanguage] = useState<Language>("en");
  const [accessCode, setAccessCode] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const { snapshot, connection, error, actions } = useCslSession(sessionId);

  const start = async () => {
    setCreateError(null);
    try {
      const created = await createSession({ topic, language, accessCode: accessCode || null });
      setSessionId(created.sessionId);
    } catch (cause) {
      setCreateError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  if (!sessionId || !snapshot) {
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
          <TextField id="code" label="Access code (if the server requires one)" value={accessCode} onChange={setAccessCode} />
          <Row>
            <Button onClick={start} disabled={!topic.trim() || Boolean(sessionId)}>
              Start session
            </Button>
            {sessionId ? <Meta>Connecting… ({connection})</Meta> : null}
          </Row>
          {createError ? <ErrorText>Could not create the session: {createError}</ErrorText> : null}
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
          phase: {phase} · status: {status} · socket: {connection} · {snapshot.messages.length} messages
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
        </Row>
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
