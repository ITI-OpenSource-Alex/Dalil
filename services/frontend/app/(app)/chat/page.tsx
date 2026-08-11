"use client";

import { Suspense, useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useDalilChat } from "@/components/chat/dalil-chat-provider";

function LegacyChatRedirect() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { openChat, openWithPrompt } = useDalilChat();
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;

    const prompt = searchParams.get("ask")?.trim();
    if (prompt) openWithPrompt(prompt);
    else openChat();

    // Keep old bookmarks and external links working without preserving a
    // second full-page chat destination in the information architecture.
    router.replace("/dashboard");
  }, [openChat, openWithPrompt, router, searchParams]);

  return <p className="sr-only">Opening Dalil chat…</p>;
}

export default function ChatPage() {
  return (
    <Suspense fallback={<p className="sr-only">Opening Dalil chat…</p>}>
      <LegacyChatRedirect />
    </Suspense>
  );
}
