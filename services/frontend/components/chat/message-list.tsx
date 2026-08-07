"use client";
import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { Message, Opportunity } from "./chat-shell";
import { GraduationCap, MapPin, Calendar } from "lucide-react";
import TypingIndicator from "./typing-indicator";
import MessageBubble from "./message-bubble";
import SourcesFootnote from "./sources-footnote";
import EvaluationBreakdown from "@/components/speaking/evaluation-breakdown";

interface MessageListProps {
  messages: Message[];
  isTyping: boolean;
}

export default function MessageList({ messages, isTyping }: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <AnimatePresence initial={false}>
        {messages.map((msg) => {
          const isUser = msg.role === "user";
          // Sources/opportunities/evaluation are only ever set on assistant
          // messages (see the "match_results"/"sources" cases in
          // handleChatEvent and the speaking onEvaluation handler in
          // chat-shell.tsx) -- guarded here too so a user message can never
          // render a left-aligned attachment block underneath it.
          const hasAttachments =
            !isUser &&
            ((msg.sources?.length ?? 0) > 0 ||
              (msg.opportunities?.length ?? 0) > 0 ||
              !!msg.evaluation);

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
                  intent={msg.intent}
                  isStreaming={msg.isStreaming}
                />
              </div>

              {hasAttachments && (
                // ml-12 = avatar width (w-8 = 32px) + the row's gap-4 (16px),
                // so attachments align with the bubble's start rather than
                // the avatar. max-w-3xl is deliberately wider than the
                // bubble's max-w-[75%] -- the two-column opportunity card
                // grid needs more room than that constraint allows.
                <div className="ml-12 max-w-3xl space-y-2">
                  {msg.sources && msg.sources.length > 0 && (
                    <SourcesFootnote sources={msg.sources} />
                  )}

                  {msg.opportunities && msg.opportunities.length > 0 && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {msg.opportunities.map((opp, idx) => (
                        <OpportunityCard key={idx} opp={opp} index={idx} />
                      ))}
                    </div>
                  )}

                  {msg.evaluation && (
                    <motion.div
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{
                        duration: 0.4,
                        delay: 0.1,
                        ease: "easeOut",
                      }}
                    >
                      <EvaluationBreakdown
                        overallBand={msg.evaluation.overallScore}
                        criteria={msg.evaluation.criteria}
                        feedback={msg.evaluation.feedback}
                      />
                    </motion.div>
                  )}
                </div>
              )}
            </motion.div>
          );
        })}
      </AnimatePresence>

      {/* Typing Indicator */}
      <AnimatePresence>{isTyping && <TypingIndicator />}</AnimatePresence>

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
      className="bg-white border border-[#E4EAE4] rounded-xl p-4 shadow-sm flex flex-col justify-between"
    >
      <div>
        <div className="flex justify-between items-start gap-2">
          <h4 className="font-semibold text-sm text-[#0D3820] line-clamp-1">
            {opp.programName}
          </h4>
          <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md shrink-0">
            {confidencePercent}% Match
          </span>
        </div>
        <div className="space-y-1.5 mt-3 text-xs text-[#526053]">
          <p className="flex items-center gap-1.5">
            <GraduationCap size={13} className="text-[#899C8B]" />
            <span className="line-clamp-1">{opp.university}</span>
          </p>
          <p className="flex items-center gap-1.5">
            <MapPin size={13} className="text-[#899C8B]" />
            <span>{opp.country}</span>
          </p>
          <p className="flex items-center gap-1.5">
            <Calendar size={13} className="text-[#899C8B]" />
            <span>Deadline: {opp.deadline}</span>
          </p>
        </div>
      </div>
      {/* Confidence Indicator Bar */}
      <div className="mt-4">
        <div className="w-full bg-[#F0F3EF] h-1.5 rounded-full overflow-hidden">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${confidencePercent}%` }}
            transition={{
              duration: 0.6,
              delay: 0.2 + index * 0.06,
              ease: "easeOut",
            }}
            className="bg-emerald-600 h-full rounded-full"
          />
        </div>
      </div>
      {/* GOA-035 entry point: generates/opens this program's application checklist. */}
      <Link
        href={`/checklist/${opp.programId}`}
        className="mt-3 inline-block text-center rounded-full bg-[#0D3820] px-3 py-1.5 text-[11px] font-semibold text-white transition hover:bg-[#0a2c19]"
      >
        Get Checklist
      </Link>
    </motion.div>
  );
}
