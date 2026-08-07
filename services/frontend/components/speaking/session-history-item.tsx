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
      href={`/practice/speaking/history/${session.id}`}
      className="flex items-center justify-between gap-4 rounded-2xl border border-border bg-surface p-4 shadow-2xs transition hover:border-brand-border hover:bg-brand-subtle focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
    >
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-fg">
          {session.question_prompt}
        </p>
        <p className="mt-1 text-xs text-fg-subtle">
          {formatSessionDate(session.created_at)} &bull; {session.question_type}
        </p>
      </div>

      <div className="shrink-0 rounded-xl border border-border bg-canvas-subtle px-3 py-1.5 text-center">
        <p className="text-[10px] font-bold uppercase tracking-widest text-fg-subtle">
          Band
        </p>
        <p className="font-serif text-lg font-bold text-brand-fg">
          {session.overall_band}
        </p>
      </div>
    </Link>
  );
}
