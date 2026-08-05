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
        <div className="w-8 h-8 rounded-full bg-[#0E3D23] flex items-center justify-center text-white text-xs font-semibold shrink-0">
          G
        </div>
      )}

      <div className="flex flex-col gap-2 max-w-[75%]">
        <motion.div
          data-testid={`${role}-message`}
          layout
          className={`rounded-2xl px-4 py-3 text-sm shadow-sm ${
            isUser
              ? "bg-[#E6F4EA] text-[#0A2E1A] rounded-tr-none border border-[#CCEADA]"
              : "bg-white text-[#1D291E] rounded-tl-none border border-[#EBEFEA]"
          }`}
        >
          <StreamingMessage content={content} isStreaming={isStreaming} />
        </motion.div>
      </div>

      {/* User Avatar */}
      {isUser && (
        <div className="w-8 h-8 rounded-full bg-[#E5E9E4] flex items-center justify-center text-[#2F4432] text-xs font-semibold shrink-0">
          {userInitials || "You"}
        </div>
      )}
    </>
  );
}
