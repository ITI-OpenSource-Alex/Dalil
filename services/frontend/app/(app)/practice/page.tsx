"use client";

import Link from "next/link";
import { ArrowRight, AudioLines, History, PenSquare } from "lucide-react";
import { Badge, Button, Card, Heading, Icon, PageContainer, Text } from "@/components/ui";

/**
 * Practice's landing page -- the section this replaces (chat's toolbar
 * buttons) had no page of its own at all. Mirrors /exam's card-grid pattern:
 * one entry point per skill, each linking straight into its practice page
 * and its history.
 */
export default function PracticePage() {
  return (
    <PageContainer size="lg">
      <div className="mb-8">
        <Badge tone="brand" pill>
          Practice
        </Badge>
        <Heading as="h1" size="xl" className="mt-2">
          IELTS Practice
        </Heading>
        <Text size="sm" tone="muted" className="mt-1">
          Free-form Speaking and Writing practice with instant AI feedback --
          separate from the timed IELTS Exam.
        </Text>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <PracticeCard
          icon={AudioLines}
          title="Speaking Practice"
          description="Answer a Part 2 prompt out loud and get scored on fluency, lexical range, grammar and pronunciation."
          practiceHref="/practice/speaking"
          historyHref="/practice/speaking/history"
        />
        <PracticeCard
          icon={PenSquare}
          title="Writing Practice"
          description="Write or paste an essay and get per-criterion band feedback with inline highlights."
          practiceHref="/practice/writing"
          historyHref="/practice/writing/history"
        />
      </div>
    </PageContainer>
  );
}

function PracticeCard({
  icon,
  title,
  description,
  practiceHref,
  historyHref,
}: {
  icon: typeof AudioLines;
  title: string;
  description: string;
  practiceHref: string;
  historyHref: string;
}) {
  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-start gap-3">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-brand-muted text-brand-fg">
          <Icon icon={icon} size="md" />
        </span>
        <div>
          <Heading as="h2" size="md">
            {title}
          </Heading>
          <Text size="sm" tone="muted" className="mt-1">
            {description}
          </Text>
        </div>
      </div>

      <div className="mt-auto flex flex-wrap gap-2">
        <Button trailingIcon={ArrowRight} asChild>
          <Link href={practiceHref}>Start practicing</Link>
        </Button>
        <Button variant="secondary" leadingIcon={History} asChild>
          <Link href={historyHref}>View history</Link>
        </Button>
      </div>
    </Card>
  );
}
