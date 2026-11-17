"use client";

import { useState } from "react";
import styled, { useTheme } from "styled-components";
import { Composer, MessageBubble, Navbar, ProfileImage } from "@/common/components";

const Screen = styled.div`
  display: flex;
  flex-direction: column;
  min-height: 100dvh;
  background: ${({ theme }) => theme.colors.WHITE};
`;

const Main = styled.main`
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 24px;
  width: 100%;
  max-width: 1040px;
  margin: 0 auto;
  padding: 32px clamp(24px, 6vw, 88px);
`;

const Title = styled.h1`
  margin: 0;
  font-size: 28px;
  overflow-wrap: anywhere;
`;

const Messages = styled.div`
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 20px;
  overflow-wrap: anywhere;
`;

const ChatLine = styled.div<{ $own?: boolean }>`
  display: flex;
  align-items: flex-end;
  justify-content: ${({ $own }) => $own ? "flex-end" : "flex-start"};
  gap: 8px;
`;

export function ChatSession({ topic }: { topic: string }) {
  const theme = useTheme();
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<string[]>([]);

  return (
    <Screen>
      <Navbar />
      <Main>
        <Title>{topic}</Title>
        <Messages role="log" aria-label="Study conversation" aria-live="polite">
          <ChatLine>
            <ProfileImage color={theme.colors.BLUE[900]} />
            <MessageBubble role="tutor" speaker="Tutor">
              Let’s explore {topic}. What do you think explains it?
            </MessageBubble>
          </ChatLine>
          {messages.map((message, index) => (
            <ChatLine key={index} $own>
              <MessageBubble role="user" speaker="You">{message}</MessageBubble>
            </ChatLine>
          ))}
        </Messages>
        <Composer
          value={draft}
          onChange={setDraft}
          onSubmit={() => {
            if (!draft.trim()) return;
            setMessages((current) => [...current, draft.trim()]);
            setDraft("");
          }}
        />
      </Main>
    </Screen>
  );
}
