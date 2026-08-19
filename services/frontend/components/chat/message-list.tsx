"use client";
import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { Message, Opportunity } from "./chat-shell";
import { GraduationCap, MapPin, Calendar } from "lucide-react";
import TypingIndicator from "./typing-indicator";
import MessageBubble from "./message-bubble";
import SourcesFootnote from "./sources-footnote";
import { cn } from "@/lib/cn";

interface MessageListProps {
  messages: Message[];
  isTyping: boolean;
  /** Initials for the user avatar, from the signed-in account. */
  userInitials?: string;
  compact?: boolean;
}

export default function MessageList({
  messages,
  isTyping,
  userInitials,
  compact = false,
}: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  // The typing indicator and the streaming placeholder's blinking cursor both
  // signal "assistant is working". Showing both at once looks like two
  // separate assistants responding. The indicator is suppressed whenever the
  // message list already contains a streaming placeholder — its cursor is the
  // visual indicator.
  const hasStreamingMessage = messages.some(
    (m) => m.role === "assistant" && m.isStreaming,
  );
  const showTypingIndicator = isTyping && !hasStreamingMessage;

  return (
    <div className={cn("mx-auto max-w-4xl", compact ? "space-y-4" : "space-y-6")}>
      <AnimatePresence initial={false}>
        {messages.map((msg) => {
          const isUser = msg.role === "user";
          // Sources/opportunities are only ever set on assistant messages
          // (see the "match_results"/"sources" cases in handleChatEvent in
          // chat-shell.tsx) -- guarded here too so a user message can never
          // render a left-aligned attachment block underneath it.
          const hasAttachments =
            !isUser &&
            ((msg.sources?.length ?? 0) > 0 ||
              (msg.opportunities?.length ?? 0) > 0);

          return (
            <motion.div
              key={msg.id}
              layout
              initial={{ opacity: 0, y: 16, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 0.3, ease: "easeOut" }}
              className="flex flex-col gap-2"
            >
              <div className={`flex gap-4 ${isUser ? "justify-end" : "justify-start"}`}>
                <MessageBubble
                  role={msg.role}
                  content={msg.content}
                  isStreaming={msg.isStreaming}
                  userInitials={userInitials}
                />
              </div>

              {hasAttachments && (
                // ml-12 = avatar width (w-8 = 32px) + the row's gap-4 (16px),
                // so attachments align with the bubble's start rather than
                // the avatar. max-w-3xl is deliberately wider than the
                // bubble's max-w-[75%] -- the two-column opportunity card
                // grid needs more room than that constraint allows.
                <div className={cn("max-w-3xl space-y-2", !compact && "ml-12")}>
                  {msg.sources && msg.sources.length > 0 && (
                    <SourcesFootnote sources={msg.sources} />
                  )}

                  {msg.opportunities && msg.opportunities.length > 0 && (
                    <div className={cn("grid grid-cols-1 gap-3", !compact && "md:grid-cols-2")}>
                      {msg.opportunities.map((opp, idx) => (
                        <OpportunityCard key={idx} opp={opp} index={idx} />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </motion.div>
          );
        })}
      </AnimatePresence>

      {/* Typing Indicator — suppressed when a streaming placeholder is already visible */}
      <AnimatePresence>{showTypingIndicator && <TypingIndicator />}</AnimatePresence>

      <div ref={endRef} />
    </div>
  );
}

// Opportunity Matching Card UI Component
function OpportunityCard({
  opp,
  index = 0,
}: {
  opp: Opportunity;
  index?: number;
}) {
  // opp.result.score is already 0-100 (services/rag/app/services/scoring.py) --
  // do not multiply by 100 again, that's what previously produced "NaN% Match"
  // (there was no flat `confidence` field on the real payload at all).
  const confidencePercent = Math.round(opp.result.score);
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: index * 0.06, ease: "easeOut" }}
      className="bg-surface border border-border rounded-xl p-4 shadow-sm flex flex-col justify-between"
    >
      <div>
        <div className="flex justify-between items-start gap-2">
          <h4 className="font-semibold text-sm text-brand-fg line-clamp-1">
            {opp.programName}
          </h4>
          <span className="text-[10px] font-bold text-success-fg bg-success-subtle px-2 py-0.5 rounded-md shrink-0">
            {confidencePercent}% Match
          </span>
        </div>
        <div className="space-y-1.5 mt-3 text-xs text-fg-muted">
          <p className="flex items-center gap-1.5">
            <GraduationCap size={13} className="text-fg-subtle" aria-hidden="true" />
            <span className="line-clamp-1">{opp.university}</span>
          </p>
          <p className="flex items-center gap-1.5">
            <MapPin size={13} className="text-fg-subtle" aria-hidden="true" />
            <span>{opp.country}</span>
          </p>
          <p className="flex items-center gap-1.5">
            <Calendar size={13} className="text-fg-subtle" aria-hidden="true" />
            {/* RAG returns null for a programme with no published deadline
                (scoring.py), which rendered here as "Deadline: null". */}
            <span>
              {opp.deadline
                ? `Deadline: ${opp.deadline}`
                : "No published deadline"}
            </span>
          </p>
        </div>
      </div>
      {/* Confidence Indicator Bar */}
      <div className="mt-4">
        <div className="w-full bg-canvas-inset h-1.5 rounded-full overflow-hidden">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${confidencePercent}%` }}
            transition={{
              duration: 0.6,
              delay: 0.2 + index * 0.06,
              ease: "easeOut",
            }}
            className="bg-success h-full rounded-full"
          />
        </div>
      </div>
      {/* GOA-035 entry point: generates/opens this program's application checklist. */}
      <Link
        href={`/checklist/${encodeURIComponent(opp.programId)}`}
        className="mt-3 inline-block text-center rounded-full bg-brand px-3 py-1.5 text-[11px] font-semibold text-fg-on-brand transition hover:bg-brand-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
      >
        Get Checklist
      </Link>
    </motion.div>
  );
}
