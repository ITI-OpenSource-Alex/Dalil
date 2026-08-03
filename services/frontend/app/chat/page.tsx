import ChatShell from "@/components/chat/chat-shell";
import { Sidebar } from "@/components/ui/sidebar";

export default function ChatPage() {
  return (
    <div className="flex h-screen overflow-hidden bg-[#FAFBF9]">
      {/* Render Ready App Sidebar */}
      <Sidebar />

      {/* Central Interactive Chat Workspace */}
      <div className="flex-1 flex flex-col min-w-0">
        <ChatShell />
      </div>
    </div>
  );
}