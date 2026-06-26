import MessageList from "./message-list";
import ChatInput from "./chat-input";

export default function ChatShell() {
  return (
    <main className="min-h-screen flex flex-col bg-[var(--background)] text-[var(--foreground)]">
      <section className="flex-1 p-4 overflow-y-auto">
        <MessageList />
      </section>

      <section className="border-t border-[var(--border)] p-4">
        <ChatInput />
      </section>
    </main>
  );
}
