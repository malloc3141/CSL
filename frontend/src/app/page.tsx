"use client";

import { useState } from "react";
import styled, { useTheme } from "styled-components";
import {
  MessageBubble,
  Button,
  Composer,
  ParticipantChip,
  ProfileImage,
  Stepper,
  TextField,
} from "@/common/components";
import { peerColor } from "@/styles/peerColors";

const Page = styled.main`
  display: flex;
  justify-content: center;
  padding: 48px 24px;
`;

const Card = styled.section`
  display: flex;
  flex-direction: column;
  gap: 20px;
  width: min(640px, 100%);
  padding: 28px;
  border: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  border-radius: ${({ theme }) => theme.round.md};
  background: ${({ theme }) => theme.colors.WHITE};
`;

const Title = styled.h1`
  margin: 0;
  font-size: 28px;
  font-weight: 700;
`;

const Lead = styled.p`
  margin: 0;
  color: ${({ theme }) => theme.colors.GRAY[900]};
`;

const Row = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
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
`;

const STEPS = ["초기 질문", "학습 방향 설정", "교실 구성"];
const PEERS = ["Peer 1", "Peer 2", "Peer 3", "Peer 4"];

const MESSAGES = [
  {
    role: "tutor" as const,
    speaker: "Tutor",
    text: "여름에는 덥고 겨울에는 추운 이유를 함께 살펴봅시다.",
  },
  {
    role: "peer" as const,
    speaker: "Peer 1",
    peerIndex: 0,
    text: "여름에는 지구가 태양에 가까워져서 더운 거 아닐까요?",
  },
  {
    role: "peer" as const,
    speaker: "Peer 2",
    peerIndex: 1,
    text: "지구와 태양 사이 거리는 여름과 겨울에 크게 다르지 않아요.",
  },
  {
    role: "peer" as const,
    speaker: "Peer 3",
    peerIndex: 2,
    text: "낮의 길이가 달라지는 것과 관련이 있을까요?",
  },
  {
    role: "peer" as const,
    speaker: "Peer 4",
    peerIndex: 3,
    text: "햇빛이 비추는 각도가 다르다고 들었어요.",
  },
  {
    role: "user" as const,
    speaker: "나",
    text: "겨울에는 해가 낮게 떠서 추운 것 같아요.",
  },
];

export default function Home() {
  const theme = useTheme();
  const [topic, setTopic] = useState("여름과 겨울");
  const [draft, setDraft] = useState("");
  const [selected, setSelected] = useState("Peer 1");

  return (
    <Page>
      <Card>
        <div>
          <Title>CSL</Title>
          <Lead>Classroom Simulation for Learning</Lead>
        </div>
        <Stepper steps={STEPS} current={0} />
        <TextField
          id="topic"
          label="학습 주제"
          value={topic}
          onChange={setTopic}
          placeholder="학습 주제를 입력하세요"
        />
        {MESSAGES.map((message) => {
          const own = message.role === "user";
          const color =
            message.role === "tutor"
              ? theme.colors.BLUE[900]
              : message.role === "peer"
                ? peerColor(theme, message.peerIndex)[900]
                : undefined;

          return (
            <ChatLine key={message.speaker} $own={own}>
              {color ? <ProfileImage color={color} /> : null}
              <MessageBubble
                role={message.role}
                speaker={message.speaker}
                peerIndex={message.role === "peer" ? message.peerIndex : undefined}
              >
                {message.text}
              </MessageBubble>
            </ChatLine>
          );
        })}
        <Row>
          <ParticipantChip
            name="Tutor"
            kind="tutor"
            selected={selected === "Tutor"}
            onSelect={() => setSelected("Tutor")}
          />
          {PEERS.map((name, index) => (
            <ParticipantChip
              key={name}
              name={name}
              kind="peer"
              peerIndex={index}
              selected={selected === name}
              onSelect={() => setSelected(name)}
            />
          ))}
        </Row>
        <Composer
          value={draft}
          onChange={setDraft}
          onSubmit={() => setDraft("")}
        />
        <Actions>
          <Button variant="ghost">이전</Button>
          <Button>다음: 학습 방향 설정</Button>
        </Actions>
      </Card>
    </Page>
  );
}
