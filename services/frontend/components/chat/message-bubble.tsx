"use client";

import { motion } from "framer-motion";
import StreamingMessage from "./streaming-message";

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
  /** Initials for the user avatar, derived from the signed-in account. */
  userInitials?: string;
}

/*
 * The "Route: RAG" chip that used to render under every assistant reply is
 * gone. `intent` is the supervisor's internal classification label -- the name
 * of the downstream service the message was dispatched to -- and putting it on
 * screen told the user nothing they could act on while exposing the shape of
 * the backend. It is still carried on the Message and still traced to
 * Langfuse; it is simply not something the reader is shown.
 *
 * The user avatar's hardcoded "LA" (a leftover from the "Lina Ahmadi" demo
 * persona, BUG-047) is likewise replaced by the real account's initials.
 */
export default function MessageBubble({
  role,
  content,
  isStreaming = false,
  userInitials,
}: MessageBubbleProps) {
  const isUser = role === "user";

  return (
    <>
      {/* Assistant Avatar */}
      {!isUser && (
        <div
          className="w-8 h-8 rounded-full bg-brand flex items-center justify-center text-fg-on-brand text-xs font-semibold shrink-0"
          aria-hidden="true"
        >
          G
        </div>
      )}

      <div
        className={`flex min-w-0 flex-col gap-2 ${
          isUser ? "max-w-[82%]" : "max-w-[calc(100%_-_3rem)]"
        }`}
      >
        <motion.div
          data-testid={`${role}-message`}
          layout
          className={`rounded-2xl px-4 py-3 text-sm shadow-sm ${
            isUser
              ? "bg-brand-subtle text-brand-fg rounded-tr-none border border-brand-border"
              : "bg-surface text-fg rounded-tl-none border border-border"
          }`}
        >
          <StreamingMessage
            content={content}
            isStreaming={isStreaming}
            markdown={!isUser}
          />
        </motion.div>
      </div>

      {/* User Avatar */}
      {isUser && (
        <div
          className="w-8 h-8 rounded-full bg-canvas-inset flex items-center justify-center text-brand-fg text-xs font-semibold shrink-0"
          aria-hidden="true"
        >
          {userInitials || "You"}
        </div>
      )}
    </>
  );
}
