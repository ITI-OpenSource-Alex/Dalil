"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  ListChecks,
  Plus,
  Trash2,
  UserPen,
} from "lucide-react";
import {
  forgetChecklist,
  progressPercent,
  readChecklistIndex,
  type ChecklistIndexEntry,
} from "@/lib/checklist-index";
import {
  ProfileNotReadyError,
  searchOpportunities,
  type MatchedProgram,
} from "@/lib/opportunities-api";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";
import { isProfileComplete } from "@/app/types/profile";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Heading,
  PageContainer,
  Progress,
  Skeleton,
  Text,
} from "@/components/ui";

/**
 * Application checklists as a place of their own.
 *
 * A checklist was previously reachable only by clicking "Get Checklist" on an
 * opportunity card inside a chat message — so the thing a user is meant to
 * work through over several weeks lived inside a transcript that scrolls away.
 *
 * "Your checklists" comes from the local index (lib/checklist-index.ts,
 * which explains why that is client-side); "Start a new one" comes from the
 * same matcher the Opportunities page uses, so a user with no checklists yet
 * still lands on something actionable rather than an empty screen.
 */
export default function ChecklistsPage() {
  const { user, status: profileStatus } = useCurrentUser();
  const [entries, setEntries] = useState<ChecklistIndexEntry[]>([]);
  const [restored, setRestored] = useState(false);

  const [programs, setPrograms] = useState<MatchedProgram[]>([]);
  const [programsStatus, setProgramsStatus] = useState<
    "idle" | "loading" | "success" | "error"
  >("idle");
  const requestRef = useRef<AbortController | null>(null);

  const profileComplete = isProfileComplete(user?.profile ?? null);

  // localStorage is read in an effect, not during render: the server has none,
  // and seeding useState from it is a hydration mismatch.
  useEffect(() => {
    setEntries(readChecklistIndex());
    setRestored(true);
  }, []);

  const loadPrograms = useCallback(async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;

    setProgramsStatus("loading");
    try {
      const results = await searchOpportunities(controller.signal);
      if (controller.signal.aborted) return;
      setPrograms(results);
      setProgramsStatus("success");
    } catch (err) {
      if (controller.signal.aborted) return;
      // A failure here costs the "start a new one" suggestions and nothing
      // else, so it degrades to a quiet empty section rather than an alert
      // that implies the user's existing checklists are affected.
      setProgramsStatus(err instanceof ProfileNotReadyError ? "idle" : "error");
    }
  }, []);

  useEffect(() => {
    if (profileStatus === "loading" || profileStatus === "idle") return;
    if (!profileComplete) return;
    void loadPrograms();
    return () => requestRef.current?.abort();
  }, [profileStatus, profileComplete, loadPrograms]);

  const started = useMemo(
    () => new Set(entries.map((e) => e.programId)),
    [entries],
  );

  const suggestions = useMemo(
    () =>
      programs
        // Blocked programmes are excluded: a checklist for something the user
        // is not currently eligible for is busywork, and the Opportunities
        // page already explains what would change that.
        .filter((p) => !p.result.blocked_by && !started.has(p.programId))
        .slice(0, 6),
    [programs, started],
  );

  function handleRemove(programId: string) {
    forgetChecklist(programId);
    setEntries(readChecklistIndex());
  }

  return (
    <PageContainer size="2xl">
      <div className="mb-8">
        <Badge tone="brand" pill>
          Checklists
        </Badge>
        <Heading as="h1" size="xl" className="mt-2">
          Your application checklists
        </Heading>
        <Text size="sm" tone="muted" className="mt-1">
          One step-by-step plan per programme — documents, deadlines, language
          requirements and the financial proof each country asks for.
        </Text>
      </div>

      {!restored && (
        <div className="space-y-3" aria-busy="true" aria-label="Loading checklists">
          <Skeleton className="h-24 w-full" shape="block" />
          <Skeleton className="h-24 w-full" shape="block" />
        </div>
      )}

      {restored && entries.length === 0 && (
        <>
          {!profileComplete && profileStatus === "success" ? (
            <EmptyState
              icon={UserPen}
              title="Finish your profile to build a checklist"
              description="A checklist is generated per programme, and we need your academic background to pick programmes worth applying to."
              actions={
                <>
                  <Button asChild>
                    <Link href="/onboarding">Complete onboarding</Link>
                  </Button>
                  <Button variant="secondary" asChild>
                    <Link href="/profile">Edit profile</Link>
                  </Button>
                </>
              }
            />
          ) : (
            <EmptyState
              icon={ListChecks}
              title="No checklists yet"
              description="Pick a programme below — or from Opportunities — and we'll generate its full application checklist."
              actions={
                <Button asChild>
                  <Link href="/opportunities">Browse opportunities</Link>
                </Button>
              }
            />
          )}
        </>
      )}

      {restored && entries.length > 0 && (
        <ul className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {entries.map((entry) => {
            const percent = progressPercent(entry);
            const complete = entry.totalItems > 0 && percent === 100;
            return (
              <li key={entry.programId} className="flex">
                <Card className="flex w-full flex-col gap-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h2 className="truncate text-sm font-bold text-fg">
                        {entry.programName}
                      </h2>
                      <Text size="sm" tone="muted" className="mt-0.5 truncate">
                        {[entry.university, entry.country]
                          .filter(Boolean)
                          .join(" · ") || "Programme checklist"}
                      </Text>
                    </div>
                    {complete && (
                      <Badge tone="success" size="sm" pill className="shrink-0">
                        Complete
                      </Badge>
                    )}
                  </div>

                  <div>
                    <Progress
                      value={entry.completedItems}
                      max={Math.max(1, entry.totalItems)}
                      label={`${entry.programName} progress`}
                      valueText={`${entry.completedItems} of ${entry.totalItems} done`}
                    />
                    <Text size="sm" tone="subtle" className="mt-1.5">
                      {entry.totalItems > 0
                        ? `${entry.completedItems} of ${entry.totalItems} steps done`
                        : "Open to generate the steps"}
                      {" · Last opened "}
                      {new Date(entry.lastOpenedAt).toLocaleDateString()}
                    </Text>
                  </div>

                  <div className="mt-auto flex flex-wrap items-center gap-2 pt-1">
                    <Button size="sm" trailingIcon={ArrowRight} asChild>
                      <Link href={`/checklist/${encodeURIComponent(entry.programId)}`}>
                        {entry.totalItems > 0 ? "Continue" : "Open checklist"}
                      </Link>
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      leadingIcon={Trash2}
                      onClick={() => handleRemove(entry.programId)}
                      // "Remove from this list", not "delete": the checklist
                      // and its ticked items stay on the server, and saying
                      // otherwise would be a lie about a destructive action.
                      title="Remove from this list — the checklist itself is kept"
                    >
                      Remove
                    </Button>
                  </div>
                </Card>
              </li>
            );
          })}
        </ul>
      )}

      {restored && profileComplete && (
        <section className="mt-10">
          <Heading as="h2" size="md">
            Start a new checklist
          </Heading>
          <Text size="sm" tone="muted" className="mt-1 mb-4">
            From the programmes you currently qualify for.
          </Text>

          {programsStatus === "loading" && (
            <div
              aria-busy="true"
              aria-label="Loading suggested programmes"
              className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3"
            >
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-24 w-full" shape="block" />
              ))}
            </div>
          )}

          {programsStatus === "success" && suggestions.length === 0 && (
            <Text size="sm" tone="subtle">
              You already have a checklist for every programme you currently
              qualify for.{" "}
              <Button variant="link" size="sm" asChild>
                <Link href="/opportunities">Browse all opportunities</Link>
              </Button>
            </Text>
          )}

          {programsStatus === "error" && (
            <Text size="sm" tone="subtle">
              Couldn&apos;t load programme suggestions just now.{" "}
              <Button variant="link" size="sm" onClick={() => void loadPrograms()}>
                Try again
              </Button>
            </Text>
          )}

          {suggestions.length > 0 && (
            <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {suggestions.map((program) => (
                <li key={program.programId} className="flex">
                  <Card className="flex w-full flex-col gap-3">
                    <div className="min-w-0">
                      <h3 className="truncate text-sm font-semibold text-fg">
                        {program.programName}
                      </h3>
                      <Text size="sm" tone="muted" className="mt-0.5 truncate">
                        {program.university} · {program.country}
                      </Text>
                    </div>
                    <Button size="sm" variant="secondary" leadingIcon={Plus} asChild className="mt-auto self-start">
                      <Link href={`/checklist/${encodeURIComponent(program.programId)}`}>
                        Build checklist
                      </Link>
                    </Button>
                  </Card>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </PageContainer>
  );
}
