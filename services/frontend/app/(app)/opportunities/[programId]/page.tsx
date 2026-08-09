"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ExternalLink, ListChecks } from "lucide-react";
import { getOpportunity, type MatchedProgram } from "@/lib/opportunities-api";
import {
  Alert,
  Badge,
  Button,
  Card,
  Heading,
  PageContainer,
  Skeleton,
  Text,
} from "@/components/ui";

function value(value: unknown) {
  if (value === null || value === undefined || value === "")
    return "Not published";
  return String(value);
}

function FactTree({ value: item }: { value: unknown }) {
  if (item === null || item === undefined) return null;
  if (Array.isArray(item))
    return (
      <ul className="list-disc pl-5">
        {item.map((entry, index) => (
          <li key={index}>
            <FactTree value={entry} />
          </li>
        ))}
      </ul>
    );
  if (typeof item === "object")
    return (
      <dl className="space-y-1">
        {Object.entries(item as Record<string, unknown>).map(([key, entry]) => (
          <div key={key}>
            <dt className="inline font-medium capitalize">
              {key.replaceAll("_", " ")}:{" "}
            </dt>
            <dd className="inline">
              <FactTree value={entry} />
            </dd>
          </div>
        ))}
      </dl>
    );
  return <>{String(item)}</>;
}

export default function ProgrammeDetailPage() {
  const params = useParams<{ programId: string }>();
  const [program, setProgram] = useState<MatchedProgram | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getOpportunity(params.programId)
      .then(setProgram)
      .catch(() => setError("We couldn't load this programme right now."));
  }, [params.programId]);

  if (error)
    return (
      <PageContainer size="lg">
        <Alert tone="danger">{error}</Alert>
      </PageContainer>
    );
  if (!program)
    return (
      <PageContainer size="lg">
        <Skeleton shape="block" className="h-96 w-full" />
      </PageContainer>
    );

  const requirements = program.requirements ?? {
    minEcts: null,
    minGpa: null,
    minIelts: null,
    degreeLevel: null,
    minWorkExperience: null,
  };
  const scoreBreakdown = program.result.score_breakdown;
  const limitedScore =
    program.result.requirements_evaluated === 0 ||
    scoreBreakdown?.confidence === "limited" ||
    scoreBreakdown?.confidence === "insufficient";
  return (
    <PageContainer size="lg">
      <Button variant="link" size="sm" asChild>
        <Link href="/opportunities">← Back to opportunities</Link>
      </Button>
      <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <Badge tone="brand" pill>
            {program.country}
          </Badge>
          <Heading as="h1" size="xl" className="mt-2">
            {program.programName}
          </Heading>
          <Text tone="muted">{program.university}</Text>
        </div>
        <Button leadingIcon={ListChecks} asChild>
          <Link href={`/checklist/${encodeURIComponent(program.programId)}`}>
            Build my checklist
          </Link>
        </Button>
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <Card>
          <Heading as="h2" size="md">
            Programme requirements
          </Heading>
          <dl className="mt-4 space-y-2">
            {Object.entries(requirements).map(([key, entry]) => (
              <div
                key={key}
                className="flex justify-between gap-4 border-b border-border py-2"
              >
                <dt className="capitalize text-fg-muted">
                  {key.replace(/([A-Z])/g, " $1")}
                </dt>
                <dd className="font-medium">{value(entry)}</dd>
              </div>
            ))}
          </dl>
          {program.sourceUrl && (
            <Button
              className="mt-5"
              variant="secondary"
              trailingIcon={ExternalLink}
              asChild
            >
              <a
                href={program.sourceUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open source programme listing
              </a>
            </Button>
          )}
        </Card>
        <Card>
          <Heading as="h2" size="md">
            Your programme fit
          </Heading>
          {limitedScore ? (
            <Text className="mt-2 font-semibold">
              Not enough structured academic data for a reliable fit score.
            </Text>
          ) : program.result.blocked_by ? (
            <Text className="mt-2 font-semibold">
              You do not currently meet a published minimum requirement.
            </Text>
          ) : (
            <>
              <Text className="mt-2 text-3xl font-bold">
                {Math.round(program.result.score)}% fit
              </Text>
              <Text size="sm" tone="muted">
                {program.result.requirements_met ?? 0} of{" "}
                {program.result.requirements_evaluated} published requirements
                currently met.
              </Text>
              {scoreBreakdown?.requirement_headroom_points !== null &&
                scoreBreakdown?.requirement_headroom_points !== undefined && (
                  <Text size="sm" tone="muted" className="mt-1">
                    {Math.round(scoreBreakdown.eligibility_points)} eligibility
                    + {Math.round(scoreBreakdown.requirement_headroom_points)}
                    {" requirement headroom + "}
                    {Math.round(scoreBreakdown.subject_points ?? 0)}
                    {" subject fit + "}
                    {Math.round(scoreBreakdown.destination_points ?? 0)}
                    {" destination fit"}
                  </Text>
                )}
            </>
          )}
          <div className="mt-4 space-y-2">
            {Object.entries(program.result.gap_report ?? {}).length === 0 ? (
              <Text size="sm">
                You meet every published requirement we can verify.
              </Text>
            ) : (
              Object.entries(program.result.gap_report ?? {})
                .filter(([key]) => key !== "financial")
                .map(([key, entry]) => (
                  <div
                    key={key}
                    className="rounded-control bg-canvas-subtle p-3"
                  >
                    <Text size="sm" className="font-semibold capitalize">
                      {key.replaceAll("_", " ")}
                    </Text>
                    <Text size="sm" tone="muted">
                      {typeof entry === "object" && entry && "message" in entry
                        ? String((entry as { message: unknown }).message)
                        : String(entry)}
                    </Text>
                  </div>
                ))
            )}
          </div>
        </Card>
      </div>

      <section className="mt-6">
        <Heading as="h2" size="md">
          Visa requirements for {program.country}
        </Heading>
        <Text size="sm" tone="muted" className="mt-1 mb-4">
          Source-backed government or embassy information. Always verify before
          applying.
        </Text>
        {(program.visaRequirements?.length ?? 0) === 0 ? (
          <Alert tone="info">
            No verified visa information is available yet.
          </Alert>
        ) : (
          <div className="space-y-4">
            {program.visaRequirements?.map((visa, index) => (
              <Card key={`${visa.issuing_body}-${index}`}>
                <Heading as="h3" size="sm">
                  {visa.visa_type}
                </Heading>
                <Text size="sm" tone="muted">
                  {visa.issuing_body}
                </Text>
                <div className="mt-3 text-sm">
                  <FactTree value={visa.requirements} />
                </div>
                {visa.proof_of_funds && (
                  <div className="mt-4">
                    <Text size="sm" className="font-semibold">
                      Proof of funds
                    </Text>
                    <div className="mt-1 text-sm text-fg-muted">
                      <FactTree value={visa.proof_of_funds} />
                    </div>
                  </div>
                )}
                {visa.source_url && (
                  <a
                    href={visa.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-4 inline-block text-sm text-brand-fg underline"
                  >
                    Official visa source
                  </a>
                )}
              </Card>
            ))}
          </div>
        )}
      </section>
    </PageContainer>
  );
}
