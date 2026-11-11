"use client";

// Integration check for the backend connection (src/lib/csl). Not the product UI:
// it shows every piece of state the server sends, with the existing common components.

import { useState } from "react";
import styled, { useTheme } from "styled-components";
import { Button, Composer, MessageBubble, ProfileImage, TextField } from "@/common/components";
import { createSession, useCslSession } from "@/lib/csl";
import type { Accuracy, Role, StateVersion } from "@/lib/csl";
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
        {current.turnNumber ? ` (${current.turnNumber}턴에서 변경)` : ""}
      </Heading>
      <Meta>현재 믿음</Meta>
      <StateList>
        {state.beliefs.map((belief) => (
          <li key={belief.id}>
            {mark(belief.accuracy)}
            {belief.text}
          </li>
        ))}
      </StateList>
      <Meta>현재 설명</Meta>
      <StateList>
        <li>
          {mark(state.explanationAccuracy)}
          {state.explanation}
        </li>
      </StateList>
      {state.openQuestions.length > 0 ? (
        <>
          <Meta>현재 의문</Meta>
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
  const [topic, setTopic] = useState("여름은 왜 겨울보다 더운가?");
  const [accessCode, setAccessCode] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const { snapshot, connection, error, actions } = useCslSession(sessionId);

  const start = async () => {
    setCreateError(null);
    try {
      const created = await createSession({ topic, language: "ko", accessCode: accessCode || null });
      setSessionId(created.sessionId);
    } catch (cause) {
      setCreateError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  if (!sessionId || !snapshot) {
    return (
      <Page>
        <Card>
          <Heading>백엔드 연동 확인</Heading>
          <TextField id="topic" label="학습 주제" value={topic} onChange={setTopic} />
          <TextField id="code" label="접근 코드 (서버에 설정한 경우)" value={accessCode} onChange={setAccessCode} />
          <Row>
            <Button onClick={start} disabled={!topic.trim() || Boolean(sessionId)}>
              세션 시작
            </Button>
            {sessionId ? <Meta>연결 중… ({connection})</Meta> : null}
          </Row>
          {createError ? <ErrorText>세션을 만들지 못했습니다: {createError}</ErrorText> : null}
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
            text={activeTurn.text || "입력 중…"}
          />
        ) : null}
        {phase === "building" ? <Meta>교실 구성 중…</Meta> : null}
        {snapshot.invitedTurnId ? <Meta>Tutor가 설명을 기다리고 있습니다. (계속 = 넘어가기)</Meta> : null}

        {canType ? (
          <Composer
            value={draft}
            onChange={setDraft}
            onSubmit={submit}
            placeholder={phase === "init" ? "가이드에게 답하기…" : "대화에 참여해 보세요…"}
          />
        ) : null}

        <Row>
          {phase === "init" ? (
            <Button variant="ghost" onClick={actions.finishInit}>
              초기화 건너뛰기
            </Button>
          ) : null}
          {phase === "ready" ? <Button onClick={actions.startDiscussion}>토론 시작</Button> : null}
          {phase === "discussion" ? (
            <>
              {status === "running" ? (
                <Button variant="ghost" onClick={actions.pause}>
                  일시정지
                </Button>
              ) : (
                <Button onClick={actions.resume}>계속</Button>
              )}
              <Button variant="ghost" onClick={actions.step}>
                다음 발언
              </Button>
              <Button variant="ghost" onClick={() => actions.setPace({ auto: !pace.auto })}>
                자동 진행: {pace.auto ? "켜짐" : "꺼짐"}
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
                종료
              </Button>
            </>
          ) : null}
          {phase === "building" && error ? <Button onClick={actions.resume}>다시 시도</Button> : null}
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
