import { ChatSession } from "./ChatSession";

export default async function ChatPage({
  searchParams,
}: {
  searchParams: Promise<{ topic?: string | string[] }>;
}) {
  const params = await searchParams;
  const topic = typeof params.topic === "string" ? params.topic.trim() : "";

  return <ChatSession key={topic} topic={topic || "Study session"} />;
}
