"use client";

import Link from "next/link";
import { SpeakingSessionSummary } from "@/app/types/speaking";
import { formatSessionDate } from "@/lib/speaking-format";

interface SessionHistoryItemProps {
  session: SpeakingSessionSummary;
}

export default function SessionHistoryItem({
  session,
}: SessionHistoryItemProps) {
  return (
    <Link
      href={`/speaking/history/${session.id}`}
      className="flex items-center justify-between gap-4 rounded-2xl border border-gray-200/80 bg-white p-4 shadow-2xs transition hover:border-emerald-200 hover:bg-emerald-50/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
    >
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-gray-900">
          {session.question_prompt}
        </p>
        <p className="mt-1 text-xs text-gray-400">
          {formatSessionDate(session.created_at)} &bull; {session.question_type}
        </p>
      </div>

      <div className="shrink-0 rounded-xl border border-gray-200/80 bg-[#fbfbfa] px-3 py-1.5 text-center">
        <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400">
          Band
        </p>
        <p className="font-serif text-lg font-bold text-[#0d4d3a]">
          {session.overall_band}
        </p>
      </div>
    </Link>
  );
}
