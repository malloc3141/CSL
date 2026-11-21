import { ChatSession } from "./ChatSession";

// The classroom. Which session it shows comes from the URL (?session=<id>), read in the browser.
export default function ChatPage() {
  return <ChatSession />;
}
