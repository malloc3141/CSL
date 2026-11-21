"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, CornerDownLeft } from "lucide-react";
import { ClassroomOverview } from "@/common/components/ClassroomOverview";
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
import { useCurrentUser } from "@/lib/csl";
import { peerColor } from "@/styles/peerColors";

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

const STEPS = ["Initial question", "Learning direction", "Classroom setup"];

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
  const router = useRouter();
  const theme = useTheme();
  const [topic, setTopic] = useState("");
  const [submittedTopic, setSubmittedTopic] = useState("");
  const [draft, setDraft] = useState("");
  const [step, setStep] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  // Signing in comes first: every session started here belongs to a user (undefined = not known yet).
  const user = useCurrentUser();

  useEffect(() => {
    if (step !== 1) return;

    const timer = window.setTimeout(() => setIsLoading(false), 3000);
    return () => window.clearTimeout(timer);
  }, [step]);

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
            <Stepper
              steps={STEPS}
              current={step}
              onStepClick={(nextStep) => {
                if (nextStep === step) return;
                setSubmittedTopic(topic.trim());
                setIsLoading(nextStep === 1);
                setStep(nextStep);
              }}
            />
          </Progress>
          {step === 0 ? (
            <>
          <TopicForm
            onSubmit={(event) => {
              event.preventDefault();
              if (topic.trim()) setSubmittedTopic(topic.trim());
            }}
          >
            <TextField
              id="topic"
              label="Topic"
              value={topic}
              onChange={setTopic}
              placeholder="Enter a topic to learn"
            />
            <Button type="submit" aria-label="Enter topic" title="Enter topic" disabled={!topic.trim()}>
              <CornerDownLeft size={20} aria-hidden="true" />
            </Button>
          </TopicForm>
          {submittedTopic ? (
            <ChatLine $own>
              <MessageBubble role="user" speaker="You">
                {submittedTopic}
              </MessageBubble>
            </ChatLine>
          ) : null}
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
                  peerIndex={
                    message.role === "peer" ? message.peerIndex : undefined
                  }
                >
                  {message.text}
                </MessageBubble>
              </ChatLine>
            );
          })}
          <Composer
            value={draft}
            onChange={setDraft}
            onSubmit={() => setDraft("")}
          />
            </>
          ) : step === 2 ? (
            <ClassroomOverview topic={submittedTopic || "your topic"} />
          ) : (
            <div>
              <h2>{submittedTopic}</h2>
              <Direction>
                Learning direction: explore {submittedTopic || "your topic"} through explanations,
                questions, and discussion with your classroom.
              </Direction>
              {isLoading ? (
                <Loading role="status">Preparing your classroom…</Loading>
              ) : (
                <Direction role="status">Your classroom is ready.</Direction>
              )}
            </div>
          )}
          <Actions>
            <Button variant="ghost" disabled={step === 0} onClick={() => setStep((current) => Math.max(0, current - 1))}>
              <ArrowLeft size={16} aria-hidden="true" />
              Back
            </Button>
              <Button
                disabled={isLoading || !topic.trim()}
                onClick={() => {
                  if (step === 2) {
                    router.push(`/chat?topic=${encodeURIComponent(submittedTopic || topic.trim())}`);
                    return;
                  }
                  if (step === 0) {
                    setSubmittedTopic(topic.trim());
                    setIsLoading(true);
                  }
                  setStep((current) => Math.min(current + 1, 2));
                }}
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
