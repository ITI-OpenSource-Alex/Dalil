"use client";

import { Suspense } from "react";
import Link from "next/link";
import { History } from "lucide-react";
import WritingPracticePanel from "@/components/practice/writing-practice-panel";
import { Badge, Button, Heading, PageContainer, Skeleton, Text } from "@/components/ui";

// WritingPracticePanel reads useSearchParams() (for the ?essayId= deep link
// from Chat), which opts the page into client-side rendering during
// prerendering and requires a Suspense boundary -- same reason
// app/(app)/exam/results/page.tsx has one.
export default function WritingPracticePage() {
  return (
    <PageContainer size="lg">
      <div className="mb-8 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Badge tone="brand" pill>
            Writing Practice
          </Badge>
          <Heading as="h1" size="xl" className="mt-2">
            IELTS Writing
          </Heading>
          <Text size="sm" tone="muted" className="mt-1">
            Write or paste an essay below and get per-criterion band feedback.
          </Text>
        </div>
        <Button variant="secondary" size="sm" leadingIcon={History} asChild className="shrink-0">
          <Link href="/practice/writing/history">View history</Link>
        </Button>
      </div>

      <Suspense
        fallback={
          <div className="space-y-4" aria-busy="true" aria-label="Loading Writing Practice">
            <Skeleton className="h-64 w-full rounded-card" />
          </div>
        }
      >
        <WritingPracticePanel />
      </Suspense>
    </PageContainer>
  );
}
