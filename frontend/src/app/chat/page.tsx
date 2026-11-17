import { Suspense } from "react";
import { ChatSession } from "./ChatSession";

type ChatPageProps = {
  searchParams: Promise<{ topic?: string | string[] }>;
};

export default function ChatPage({ searchParams }: ChatPageProps) {
  return (
    <Suspense fallback={<p role="status">Loading study session…</p>}>
      <ChatContent searchParams={searchParams} />
    </Suspense>
  );
}

async function ChatContent({
  searchParams,
}: ChatPageProps) {
  const params = await searchParams;
  const topic = typeof params.topic === "string" ? params.topic.trim() : "";

  return <ChatSession key={topic} topic={topic || "Study session"} />;
}
