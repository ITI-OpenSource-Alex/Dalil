"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import ChecklistView from "@/components/checklist/ChecklistView";
import { Badge, Button, Heading, PageContainer } from "@/components/ui";

export default function ChecklistPage() {
  const params = useParams<{ programId: string }>();
  const programId = params.programId;

  return (
    <PageContainer size="md">
      <Button variant="link" size="sm" asChild className="print-hidden mb-6">
        <Link href="/chat">&larr; Back to Chat</Link>
      </Button>

      <div className="mb-6">
        <Badge tone="brand" pill className="print-hidden">
          Application Checklist
        </Badge>
        <Heading as="h1" size="xl" className="mt-2">
          Your Step-by-Step Guide
        </Heading>
      </div>

      <ChecklistView programId={programId} />
    </PageContainer>
  );
}
