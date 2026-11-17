"use client";

import { useEffect, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";
import styled from "styled-components";
import { Button, Composer, MessageBubble, Navbar } from "@/common/components";
import { peerColor } from "@/styles/peerColors";

const Screen = styled.div`
  display: flex;
  flex-direction: column;
  height: 100dvh;
  background: ${({ theme }) => theme.colors.WHITE};
`;

const Classroom = styled.main`
  display: grid;
  grid-template-columns: 150px minmax(0, 1fr) 300px;
  grid-template-rows: auto minmax(0, 1fr);
  flex: 1;
  min-height: 0;
  @media (max-width: 1000px) {
    grid-template-columns: 130px minmax(0, 1fr) 240px;
  }
  @media (max-width: 760px) {
    grid-template-columns: 110px minmax(0, 1fr);
    grid-template-rows: auto minmax(320px, 1fr) auto;
    overflow-y: auto;
  }
`;

const Sidebar = styled.aside`
  grid-row: 1 / -1;
  padding: 20px 12px;
  border-right: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  background: ${({ theme }) => theme.colors.GRAY[100]};
  h2 { margin: 0 0 24px; font-size: 16px; }
  h3 { margin: 0 0 12px; font-size: 14px; }
`;

const Participants = styled.div`
  display: flex;
  flex-direction: column;
  gap: 8px;
`;

const Participant = styled.button<{ $index: number; $selected: boolean }>`
  padding: 12px;
  border: 1px solid ${({ theme, $selected }) => $selected ? theme.colors.SLATE[600] : theme.colors.GRAY[200]};
  border-radius: ${({ theme }) => theme.round.sm};
  background: ${({ theme, $index }) => $index < 0 ? theme.colors.BLUE[50] : peerColor(theme, $index)[50]};
  color: ${({ theme }) => theme.colors.GRAY[900]};
  text-align: left;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  &:focus-visible {
    outline: 2px solid ${({ theme }) => theme.colors.SLATE[600]};
    outline-offset: 2px;
  }
`;

const Goal = styled.header`
  grid-column: 2 / -1;
  padding: 18px 24px;
  border-bottom: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  h1 { margin: 0 0 8px; font-size: 16px; }
  p { margin: 0; font-size: 15px; overflow-wrap: anywhere; }
`;

const Conversation = styled.section`
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  padding: 20px 24px 16px;
  gap: 20px;
  @media (max-width: 760px) { padding: 16px 12px; }
`;

const Controls = styled.div`
  display: flex;
  justify-content: flex-end;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  button { display: inline-flex; align-items: center; gap: 8px; }
`;

const Status = styled.span<{ $paused: boolean }>`
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: ${({ theme, $paused }) => $paused ? theme.colors.GRAY[500] : theme.colors.GREEN[700]};
  font-size: 13px;
  font-weight: 600;
  &::before {
    content: "";
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: currentColor;
  }
`;

const Messages = styled.div`
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-wrap: anywhere;
`;

const MessageList = styled.div`
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  min-height: 100%;
  gap: 20px;
  padding: 4px;
`;

const ChatLine = styled.div<{ $own?: boolean }>`
  display: flex;
  justify-content: ${({ $own }) => $own ? "flex-end" : "flex-start"};
`;

const Understanding = styled.aside`
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
  padding: 20px;
  border-left: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
  background: #f8f5df;
  h2 { margin: 0 0 20px; font-size: 16px; }
  h3 { margin: 0 0 16px; font-size: 16px; }
  h4 { margin: 20px 0 8px; font-size: 13px; }
  p { margin: 0; font-size: 14px; line-height: 1.6; }
  @media (max-width: 760px) {
    grid-column: 2;
    min-height: 180px;
    border-top: 1px solid ${({ theme }) => theme.colors.GRAY[200]};
    border-left: 0;
  }
`;

const EmptyState = styled.p`
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: ${({ theme }) => theme.colors.SLATE[600]};
`;

const PARTICIPANTS = [
  { name: "Tutor", index: -1, belief: "Help the classroom compare explanations and test them against evidence.", question: "What evidence would help us decide which explanation is strongest?" },
  { name: "Peer 1", index: 0, belief: "An everyday explanation might account for the topic. This initial idea still needs testing.", question: "Does this explanation work in every case?" },
  { name: "Peer 2", index: 1, belief: "Another factor may be responsible. Comparing alternative explanations could help us understand.", question: "How could we test an alternative explanation?" },
];

export function ChatSession({ topic }: { topic: string }) {
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<string[]>([]);
  const [paused, setPaused] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const participant = selected === null ? null : PARTICIPANTS[selected];

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "nearest" });
  }, [messages]);

  return (
    <Screen>
      <Navbar />
      <Classroom>
        <Sidebar aria-label="Classroom participants">
          <h2>Classroom</h2>
          <h3>Participants</h3>
          <Participants>
            {PARTICIPANTS.map((person, index) => (
              <Participant key={person.name} type="button" $index={person.index} $selected={selected === index}
                aria-pressed={selected === index} onClick={() => setSelected(index)}>
                {person.name}
              </Participant>
            ))}
          </Participants>
        </Sidebar>
        <Goal>
          <h1>Learning goal</h1>
          <p>{topic}</p>
        </Goal>
        <Conversation aria-label="Study conversation">
          <Controls>
            <Status $paused={paused} role="status">{paused ? "Paused" : "In progress"}</Status>
            <Button variant="ghost" onClick={() => setPaused((current) => !current)}>
              {paused ? "Resume discussion" : "Pause discussion"}
              {paused ? <Play size={16} aria-hidden="true" /> : <Pause size={16} aria-hidden="true" />}
            </Button>
          </Controls>
          <Messages role="log" aria-label="Messages" aria-live="polite">
            <MessageList>
              <ChatLine>
                <MessageBubble role="peer" peerIndex={0} speaker="1 · Peer 1">
                  Could a simple, everyday explanation help us understand {topic}?
                </MessageBubble>
              </ChatLine>
              {messages.map((message, index) => (
                <ChatLine key={index} $own>
                  <MessageBubble role="user" speaker={`${index + 2} · You`}>{message}</MessageBubble>
                </ChatLine>
              ))}
              <div ref={bottom} />
            </MessageList>
          </Messages>
          <Composer value={draft} onChange={setDraft} placeholder="Join the discussion…"
            onSubmit={() => {
              if (!draft.trim()) return;
              setMessages((current) => [...current, draft.trim()]);
              setDraft("");
            }} />
        </Conversation>
        <Understanding aria-label="Participant understanding">
          <h2>Understanding</h2>
          {participant ? (
            <div aria-live="polite">
              <h3>{participant.name}</h3>
              <h4>Current understanding</h4>
              <p>{participant.belief}</p>
              <h4>Open question</h4>
              <p>{participant.question}</p>
            </div>
          ) : (
            <EmptyState>Select a participant on the left to view their understanding here.</EmptyState>
          )}
        </Understanding>
      </Classroom>
    </Screen>
  );
}
