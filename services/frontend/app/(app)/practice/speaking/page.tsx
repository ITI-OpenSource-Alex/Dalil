"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { History } from "lucide-react";
import SpeakingPracticePanel from "@/components/practice/speaking-practice-panel";
import { Badge, Button, Heading, PageContainer, Text } from "@/components/ui";

/**
 * Speaking Practice, standalone. Previously this route (/speaking) only
 * linked out to Chat, where the mic and live transcript actually lived --
 * "Sessions run in Chat" was the whole page. SpeakingPracticePanel now runs
 * the session directly here; Chat becomes an optional deep-link into this
 * page rather than the only place the feature works.
 */
export default function SpeakingPracticePage() {
  return (
    <Suspense
      fallback={
        <PageContainer size="lg">
          <Text tone="muted">Loading speaking exam…</Text>
        </PageContainer>
      }
    >
      <SpeakingPageContent />
    </Suspense>
  );
}

function SpeakingPageContent() {
  const searchParams = useSearchParams();
  const examSessionId =
    searchParams.get("mode") === "exam" ? searchParams.get("session") : null;
  const examMode = Boolean(examSessionId);
  return (
    <PageContainer size="lg">
      <div className="mb-8 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Badge tone="brand" pill>
            {examMode ? "Speaking Exam" : "Speaking Practice"}
          </Badge>
          <Heading as="h1" size="xl" className="mt-2">
            {examMode ? "IELTS Speaking Exam" : "IELTS Speaking"}
          </Heading>
          <Text size="sm" tone="muted" className="mt-1">
            {examMode
              ? "Complete all three timed parts. Your transcript and official result are saved to Exam history."
              : "Complete a full interview and get scored on fluency, lexical range, grammar and pronunciation."}
          </Text>
        </div>
        {!examMode && (
          <Button
            variant="secondary"
            size="sm"
            leadingIcon={History}
            asChild
            className="shrink-0"
          >
            <Link href="/practice/speaking/history">View history</Link>
          </Button>
        )}
      </div>

      <SpeakingPracticePanel
        mode={examMode ? "exam" : "practice"}
        examSessionId={examSessionId ?? undefined}
      />
    </PageContainer>
  );
}
