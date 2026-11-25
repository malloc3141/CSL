"use client";

import type { ReactNode, Ref } from "react";
import styled from "styled-components";
import { Composer, MessageBubble } from "@/common/components";
import { useI18n } from "@/i18n";
import type { ActiveTurn, Message, SessionSnapshot } from "@/lib/csl";

const Conversation = styled.section`
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  padding: 20px 24px 16px;
  gap: 20px;
  @media (max-width: 760px) { padding: 16px 12px; }
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

const ChatLine = styled.div<{ $own?: boolean; $flash?: boolean }>`
  display: flex;
  justify-content: ${({ $own }) => $own ? "flex-end" : "flex-start"};
  border-radius: ${({ theme }) => theme.round.md};
  outline: 2px solid ${({ theme, $flash }) => $flash ? theme.colors.SLATE[600] : "transparent"};
  outline-offset: 4px;
  transition: outline-color 0.3s;
`;

const Stack = styled.div<{ $own?: boolean }>`
  display: flex;
  flex-direction: column;
  align-items: ${({ $own }) => $own ? "flex-end" : "flex-start"};
  gap: 6px;
`;

// Under a message: whose understanding changed because of it. Opens that participant's panel.
const StateChip = styled.button`
  padding: 0;
  border: 0;
  background: none;
  color: ${({ theme }) => theme.colors.SLATE[600]};
  font-size: 12px;
  font-weight: 600;
  text-decoration: underline;
  cursor: pointer;
`;

const Notice = styled.p`
  margin: 0;
  color: ${({ theme }) => theme.colors.ROSE[900]};
  font-size: 13px;
`;

type ChatConversationProps = {
  children: ReactNode;
  messages: Message[];
  active: ActiveTurn | null;
  snapshot: SessionSnapshot | null;
  flash: string | null;
  bottom: Ref<HTMLDivElement>;
  errorMessage?: string;
  draft: string;
  waiting: boolean;
  canSend: boolean;
  onOpenUnderstanding: (id: string) => void;
  onDraftChange: (draft: string) => void;
  onSubmit: () => void;
};

export function ChatConversation({
  children, messages, active, snapshot, flash, bottom, errorMessage, draft, waiting, canSend,
  onOpenUnderstanding, onDraftChange, onSubmit,
}: ChatConversationProps) {
  const { t } = useI18n();
  const participants = snapshot?.participants ?? [];
  // Which participants changed their understanding because of which message.
  const changedBy = new Map<string, string[]>();
  for (const [id, all] of Object.entries(snapshot?.states ?? {})) {
    for (const version of all) {
      if (version.version > 0 && version.turnId) {
        changedBy.set(version.turnId, [...(changedBy.get(version.turnId) ?? []), id]);
      }
    }
  }

  return (
    <Conversation aria-label={t("studyConversation")}>
      {children}
      {errorMessage !== undefined ? <Notice role="alert">{errorMessage} {t("resumeHint")}</Notice> : null}
      <Messages role="log" aria-label={t("messages")} aria-live="polite">
        <MessageList>
          {messages.map((message) => (
            <ChatLine
              key={message.id}
              id={`turn-${message.id}`}
              $own={message.role === "user"}
              $flash={flash === message.id}
            >
              <Stack $own={message.role === "user"}>
                <MessageBubble
                  role={message.role}
                  peerIndex={message.peerIndex ?? 0}
                  speaker={`${message.turnNumber ?? ""} · ${message.speakerName}`}
                >
                  {message.text}
                </MessageBubble>
                {(changedBy.get(message.id) ?? []).map((id) => (
                  <StateChip key={id} type="button" onClick={() => onOpenUnderstanding(id)}>
                    {t("understandingChanged", { name: participants.find((participant) => participant.id === id)?.name ?? id })}
                  </StateChip>
                ))}
              </Stack>
            </ChatLine>
          ))}
          {active ? (
            <ChatLine>
              <MessageBubble role={active.role} peerIndex={active.peerIndex ?? 0} speaker={active.speakerName}>
                {active.text || "…"}
              </MessageBubble>
            </ChatLine>
          ) : null}
          <div ref={bottom} />
        </MessageList>
      </Messages>
      <Composer
        value={draft}
        onChange={onDraftChange}
        placeholder={waiting ? t("explainUnderstanding") : t("joinDiscussion")}
        disabled={!canSend}
        onSubmit={onSubmit}
      />
    </Conversation>
  );
}
