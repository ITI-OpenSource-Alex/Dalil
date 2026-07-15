"use client";

import { motion } from "framer-motion";

interface StreamingMessageProps {
  content: string;
  isStreaming?: boolean;
}

export default function StreamingMessage({
  content,
  isStreaming = false,
}: StreamingMessageProps) {
  return (
    <div className="relative">
      <p className="leading-relaxed whitespace-pre-wrap wrap-break-word">
        {content}

        {isStreaming && (
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 1, 0] }}
            transition={{
              duration: 1,
              repeat: Infinity,
              ease: "easeInOut",
            }}
            className="inline-block w-0.5 h-5 bg-emerald-700 ml-0.5 align-middle"
          />
        )}
      </p>
    </div>
  );
}
