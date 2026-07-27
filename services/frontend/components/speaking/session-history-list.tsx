"use client";

import { SpeakingSessionSummary } from "@/app/types/speaking";
import SessionHistoryItem from "./session-history-item";

interface SessionHistoryListProps {
  sessions: SpeakingSessionSummary[];
}

export default function SessionHistoryList({
  sessions,
}: SessionHistoryListProps) {
  return (
    <div className="space-y-3">
      {sessions.map((session) => (
        <SessionHistoryItem key={session.id} session={session} />
      ))}
    </div>
  );
}
