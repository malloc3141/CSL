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

const STEPS = ["Initial question", "Learning direction", "Classroom setup"];
const PEERS = ["Peer 1", "Peer 2", "Peer 3", "Peer 4"];

const MESSAGES = [
  {
    role: "tutor" as const,
    speaker: "Tutor",
    text: "Let's look at why it is hot in summer and cold in winter.",
  },
  {
    role: "peer" as const,
    speaker: "Peer 1",
    peerIndex: 0,
    text: "Isn't it hot in summer because the Earth gets closer to the Sun?",
  },
  {
    role: "peer" as const,
    speaker: "Peer 2",
    peerIndex: 1,
    text: "The distance between the Earth and the Sun is not that different in summer and winter.",
  },
  {
    role: "peer" as const,
    speaker: "Peer 3",
    peerIndex: 2,
    text: "Could it have to do with the length of the day?",
  },
  {
    role: "peer" as const,
    speaker: "Peer 4",
    peerIndex: 3,
    text: "I heard the angle of the sunlight is different.",
  },
  {
    role: "user" as const,
    speaker: "You",
    text: "I think winter is cold because the Sun stays low in the sky.",
  },
];

export default function Home() {
  const theme = useTheme();
  const [topic, setTopic] = useState("Summer and winter");
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
          label="Topic"
          value={topic}
          onChange={setTopic}
          placeholder="Enter a topic to learn"
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
          <Button variant="ghost">Back</Button>
          <Button>Next: learning direction</Button>
        </Actions>
      </Card>
    </Page>
  );
}
