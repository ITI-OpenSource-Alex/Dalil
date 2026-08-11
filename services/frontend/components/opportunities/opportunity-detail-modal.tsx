"use client";

import Link from "next/link";
import { ArrowRight, ExternalLink, ListChecks } from "lucide-react";
import { Button, Modal, ModalContent, Text } from "@/components/ui";
import { type MatchedProgram } from "@/lib/opportunities-api";
import { AskDalilButton } from "@/components/chat/ask-dalil-button";
import { programmeAdvicePrompt } from "@/lib/dalil-prompts";

const REQUIREMENT_ROWS: {
  key: keyof NonNullable<MatchedProgram["requirements"]>;
  label: string;
}[] = [
  { key: "minIelts", label: "Min IELTS" },
  { key: "minGpa", label: "Min GPA" },
  { key: "minEcts", label: "Min ECTS" },
  { key: "degreeLevel", label: "Degree level" },
  { key: "minWorkExperience", label: "Work experience (years)" },
  { key: "requiredCitizenship", label: "Citizenship restriction" },
];

const GAP_LABELS: Record<string, string> = {
  ielts: "IELTS",
  gpa: "GPA",
  work_experience: "Work experience",
  degree_level: "Degree level",
  financial: "Financial / visa",
  llm_feedback: "Feedback",
};

function displayValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

function gapLabel(key: string): string {
  return GAP_LABELS[key] ?? key.replace(/_/g, " ");
}

/** Object-shaped gaps expose `message`; otherwise stringify. */
function gapMessage(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "object" && !Array.isArray(value)) {
    const message = (value as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
    return null;
  }
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return String(value);
  }
  return null;
}

function financialLines(
  value: unknown,
): { message: string; sourceUrl?: string }[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (item === null || item === undefined) return [];
    if (typeof item === "string" || typeof item === "number") {
      return [{ message: String(item) }];
    }
    if (typeof item !== "object") return [];
    const record = item as Record<string, unknown>;
    const message =
      typeof record.message === "string"
        ? record.message
        : [record.country, record.issuing_body].filter(Boolean).join(" — ");
    if (!message) return [];
    const sourceUrl =
      typeof record.source_url === "string"
        ? record.source_url
        : typeof record.sourceUrl === "string"
          ? record.sourceUrl
          : undefined;
    return [{ message, sourceUrl }];
  });
}

export function OpportunityDetailModal({
  program,
  open,
  onOpenChange,
}: {
  program: MatchedProgram | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  if (!program) return null;

  const requirements = program.requirements;
  const gapEntries = Object.entries(program.result.gap_report ?? {});

  return (
    <Modal open={open} onOpenChange={onOpenChange}>
      <ModalContent
        title={program.programName}
        description={`${program.university} · ${program.country}`}
        size="lg"
        footer={
          <>
            <Button
              size="sm"
              variant="secondary"
              trailingIcon={ExternalLink}
              asChild
            >
              <Link
                href={`/opportunities/${encodeURIComponent(program.programId)}`}
              >
                Full programme details
              </Link>
            </Button>
            <AskDalilButton
              size="sm"
              variant="ghost"
              trailingIcon={ArrowRight}
              prompt={programmeAdvicePrompt(program)}
              onBeforeOpen={() => onOpenChange(false)}
            />
            <Button size="sm" leadingIcon={ListChecks} asChild>
              <Link
                href={`/checklist/${encodeURIComponent(program.programId)}`}
                onClick={() => onOpenChange(false)}
              >
                Apply
              </Link>
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-6">
          <section>
            <Text size="sm" className="mb-3 font-semibold text-fg">
              Requirements
            </Text>
            <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {REQUIREMENT_ROWS.map(({ key, label }) => (
                <div
                  key={key}
                  className="flex items-baseline justify-between gap-3 rounded-control bg-canvas-subtle px-3 py-2"
                >
                  <dt>
                    <Text size="sm" tone="muted">
                      {label}
                    </Text>
                  </dt>
                  <dd>
                    <Text size="sm" className="font-medium text-fg">
                      {displayValue(requirements?.[key])}
                    </Text>
                  </dd>
                </div>
              ))}
            </dl>
          </section>

          {program.sourceUrl && (
            <section>
              <Text size="sm" className="mb-2 font-semibold text-fg">
                Scraped programme source
              </Text>
              <a
                href={program.sourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-brand-fg underline underline-offset-2"
              >
                View the source listing
              </a>
            </section>
          )}

          <section>
            <Text size="sm" className="mb-2 font-semibold text-fg">
              Student visa requirements
            </Text>
            {(program.visaRequirements?.length ?? 0) === 0 ? (
              <Text size="sm" tone="muted">
                No verified visa record is available for this country yet.
              </Text>
            ) : (
              <ul className="space-y-2">
                {program.visaRequirements?.map((visa, index) => (
                  <li
                    key={`${visa.issuing_body}-${index}`}
                    className="rounded-control border border-border p-3"
                  >
                    <Text size="sm" className="font-semibold">
                      {visa.visa_type} · {visa.issuing_body}
                    </Text>
                    {visa.processing_days_min !== null && (
                      <Text size="sm" tone="muted">
                        Processing: {visa.processing_days_min}–
                        {visa.processing_days_max ?? visa.processing_days_min}{" "}
                        days
                      </Text>
                    )}
                    {visa.source_url && (
                      <a
                        href={visa.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-1 inline-block text-sm text-brand-fg underline"
                      >
                        Official visa source
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <Text size="sm" className="mb-3 font-semibold text-fg">
              Gap report
            </Text>
            {gapEntries.length === 0 ? (
              <Text size="sm" tone="muted">
                No gaps identified against your profile.
              </Text>
            ) : (
              <ul className="flex flex-col gap-2">
                {gapEntries.map(([key, value]) => {
                  if (key === "financial") {
                    const lines = financialLines(value);
                    if (lines.length === 0) return null;
                    return (
                      <li
                        key={key}
                        className="rounded-control border border-border bg-surface px-3 py-2.5"
                      >
                        <Text
                          size="sm"
                          className="mb-1.5 font-semibold text-fg"
                        >
                          {gapLabel(key)}
                        </Text>
                        <ul className="flex flex-col gap-2">
                          {lines.map((line, index) => (
                            <li key={`${key}-${index}`}>
                              <Text size="sm" tone="muted">
                                {line.message}
                              </Text>
                              {line.sourceUrl && (
                                <a
                                  href={line.sourceUrl}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="mt-1 inline-block text-sm text-brand-fg underline underline-offset-2 focus-visible:rounded-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
                                >
                                  Official source
                                </a>
                              )}
                            </li>
                          ))}
                        </ul>
                      </li>
                    );
                  }

                  const message = gapMessage(value);
                  if (!message) return null;

                  return (
                    <li
                      key={key}
                      className="rounded-control border border-border bg-surface px-3 py-2.5"
                    >
                      <Text size="sm" className="mb-0.5 font-semibold text-fg">
                        {gapLabel(key)}
                      </Text>
                      <Text size="sm" tone="muted">
                        {message}
                      </Text>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      </ModalContent>
    </Modal>
  );
}
