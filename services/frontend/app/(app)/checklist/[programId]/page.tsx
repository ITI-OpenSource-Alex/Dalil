"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import ChecklistView from "@/components/checklist/ChecklistView";
import { Badge, Button, Heading, PageContainer, Text } from "@/components/ui";

export default function ChecklistPage() {
  const params = useParams<{ programId: string }>();
  const programId = params.programId;

  return (
    <PageContainer size="2xl">
      {/* Back to Checklists, not back to Chat: the checklist now has a home
          of its own, and a user who arrived from an opportunity card should
          land somewhere that lists the rest of their applications. */}
      <Button variant="link" size="sm" asChild className="print-hidden mb-6" leadingIcon={ArrowLeft}>
        <Link href="/checklists">All checklists</Link>
      </Button>

      <div className="mb-8 max-w-3xl">
        <Badge tone="brand" pill className="print-hidden">
          Application Checklist
        </Badge>
        <Heading as="h1" size="xl" className="mt-2">
          Your Step-by-Step Guide
        </Heading>
        <Text size="base" tone="muted" className="print-hidden mt-2" measure>
          Tick items off as you go — progress is saved automatically and shows
          up on your checklists page.
        </Text>
      </div>

      <ChecklistView programId={programId} />
    </PageContainer>
  );
}
