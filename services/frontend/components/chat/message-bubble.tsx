"use client";

import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";
import StreamingMessage from "./streaming-message";

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
  intent?: string;
}

export default function MessageBubble({
  role,
  content,
  isStreaming = false,
  intent,
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

          {!isUser && intent && (
            <motion.span
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25 }}
              className="inline-flex items-center gap-1 mt-3 text-[10px] font-medium bg-[#F0F5F1] text-[#2C623C] px-2 py-0.5 rounded-full"
            >
              <Sparkles size={10} />
              Route: {intent}
            </motion.span>
          )}
        </motion.div>
      </div>

      {/* User Avatar */}
      {isUser && (
        <div className="w-8 h-8 rounded-full bg-[#E5E9E4] flex items-center justify-center text-[#2F4432] text-xs font-semibold shrink-0">
          LA
        </div>
      )}
    </>
  );
}
