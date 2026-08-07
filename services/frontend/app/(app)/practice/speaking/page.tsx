"use client";

import Link from "next/link";
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
    <PageContainer size="lg">
      <div className="mb-8 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Badge tone="brand" pill>
            Speaking Practice
          </Badge>
          <Heading as="h1" size="xl" className="mt-2">
            IELTS Speaking
          </Heading>
          <Text size="sm" tone="muted" className="mt-1">
            Answer a Part 2 prompt out loud and get scored on fluency,
            lexical range, grammar and pronunciation.
          </Text>
        </div>
        <Button variant="secondary" size="sm" leadingIcon={History} asChild className="shrink-0">
          <Link href="/practice/speaking/history">View history</Link>
        </Button>
      </div>

      <SpeakingPracticePanel />
    </PageContainer>
  );
}
