"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  RefreshCw,
  SearchX,
  SlidersHorizontal,
  Target,
  UserPen,
} from "lucide-react";
import {
  ProfileNotReadyError,
  matchTone,
  searchOpportunities,
  type MatchTone,
  type MatchedProgram,
} from "@/lib/opportunities-api";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";
import { isProfileComplete } from "@/app/types/profile";
import { useUpgradePrompt } from "@/components/subscription/upgrade-dialog";
import { OpportunityCard } from "@/components/opportunities/opportunity-card";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  Heading,
  Icon,
  PageContainer,
  Select,
  Skeleton,
  Text,
} from "@/components/ui";

type Status = "loading" | "success" | "error" | "profile-incomplete" | "syncing";
type SortKey = "match" | "deadline";
type Filter = "all" | "eligible" | MatchTone;

/**
 * Opportunity search as a place, not as a side effect of a chat turn.
 *
 * The Gateway has exposed POST /api/opportunities/query since GOA-132, but the
 * only way to reach it was to say something to the assistant that its LLM
 * classifier happened to route to OPPORTUNITY_SEARCH — so the product's core
 * feature was reachable only probabilistically, the results vanished as soon
 * as the conversation moved on, and there was no way to sort or filter them.
 * The sidebar acknowledged this with an "In Chat" badge pointing at /chat.
 */
export default function OpportunitiesPage() {
  const { user, status: profileStatus, retry: retryProfile } = useCurrentUser();
  const upgrade = useUpgradePrompt();

  const [programs, setPrograms] = useState<MatchedProgram[]>([]);
  const [status, setStatus] = useState<Status>("loading");
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState<SortKey>("match");
  const [filter, setFilter] = useState<Filter>("all");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // Guards against the in-flight request of a previous search resolving after
  // a newer one and overwriting it — and against React's development
  // double-effect issuing two searches on mount.
  const requestRef = useRef<AbortController | null>(null);

  const profileComplete = isProfileComplete(user?.profile ?? null);

  const load = useCallback(async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;

    setStatus("loading");
    setError(null);

    try {
      const results = await searchOpportunities(controller.signal);
      if (controller.signal.aborted) return;
      setPrograms(results);
      setLastUpdated(new Date());
      setStatus("success");
    } catch (err) {
      if (controller.signal.aborted) return;
      if (err instanceof ProfileNotReadyError) {
        setStatus("syncing");
        return;
      }
      // Opportunity search is a free-tier route, so this should not fire --
      // but if the policy ever changes, the user gets the upgrade dialog
      // rather than a raw 403 body, like everywhere else.
      if (upgrade.handle(err)) {
        setStatus("error");
        setError(null);
        return;
      }
      setError(
        "We couldn't reach programme matching just now. Your profile is unchanged — try again in a moment.",
      );
      setStatus("error");
    }
  }, [upgrade]);

  useEffect(() => {
    if (profileStatus === "loading" || profileStatus === "idle") return;
    if (!profileComplete) {
      setStatus("profile-incomplete");
      return;
    }
    void load();
    return () => requestRef.current?.abort();
  }, [profileStatus, profileComplete, load]);

  const visible = useMemo(() => {
    const filtered = programs.filter((p) => {
      if (filter === "all") return true;
      if (filter === "eligible") return !p.result.blocked_by;
      return matchTone(p) === filter;
    });

    return [...filtered].sort((a, b) => {
      if (sort === "deadline") {
        // Programmes with no published deadline sort last rather than being
        // treated as "due at epoch", which is what a naive Date compare does.
        if (!a.deadline && !b.deadline) return 0;
        if (!a.deadline) return 1;
        if (!b.deadline) return -1;
        return a.deadline.localeCompare(b.deadline);
      }
      return b.result.score - a.result.score;
    });
  }, [programs, filter, sort]);

  const eligibleCount = programs.filter((p) => !p.result.blocked_by).length;

  return (
    <PageContainer size="2xl">
      <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <Badge tone="brand" pill>
            Opportunities
          </Badge>
          <Heading as="h1" size="xl" className="mt-2">
            Programmes matched to your profile
          </Heading>
          <Text size="sm" tone="muted" className="mt-1">
            Ranked against your degree, GPA, credits, IELTS band and target
            countries. Update any of those and the ranking changes.
          </Text>
        </div>

        {status === "success" && (
          <div className="flex flex-col items-end gap-1">
            <Button
              variant="secondary"
              leadingIcon={RefreshCw}
              onClick={() => void load()}
            >
              Refresh matches
            </Button>
            {lastUpdated && (
              <Text size="sm" tone="subtle">
                Updated {lastUpdated.toLocaleTimeString()}
              </Text>
            )}
          </div>
        )}
      </div>

      {status === "profile-incomplete" && (
        <EmptyState
          icon={UserPen}
          title="Finish your profile to see matches"
          description="Matching compares your degree, GPA, credits and IELTS band against each programme's entry requirements. Without them there is nothing to compare."
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
      )}

      {status === "syncing" && (
        <Alert
          tone="info"
          announce="polite"
          title="Your profile is still syncing"
          actions={
            <Button size="sm" onClick={() => void load()}>
              Try again
            </Button>
          }
        >
          You saved it a moment ago and matching hasn&apos;t picked it up yet.
          This usually takes a few seconds.
        </Alert>
      )}

      {status === "error" && error && (
        <Alert
          tone="danger"
          announce="assertive"
          actions={
            <>
              <Button variant="danger" size="sm" onClick={() => void load()}>
                Try again
              </Button>
              <Button variant="link" size="sm" onClick={retryProfile}>
                Reload profile
              </Button>
            </>
          }
        >
          {error}
        </Alert>
      )}

      {status === "loading" && (
        <div
          aria-busy="true"
          aria-label="Finding programmes that match your profile"
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3"
        >
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <Card key={i} className="flex flex-col gap-4">
              <Skeleton className="h-5 w-3/4" />
              <Skeleton shape="text" lines={3} />
              <Skeleton className="h-1.5 w-full" />
              <Skeleton className="h-9 w-32" />
            </Card>
          ))}
        </div>
      )}

      {status === "success" && programs.length === 0 && (
        <EmptyState
          icon={SearchX}
          title="No programmes matched yet"
          description="Our catalogue is Europe-first today. Widening your target countries — or relaxing a target degree level — is usually what opens it up."
          actions={
            <>
              <Button asChild>
                <Link href="/profile">Adjust your targets</Link>
              </Button>
              <Button variant="secondary" asChild>
                <Link href="/chat">Ask GOA for advice</Link>
              </Button>
            </>
          }
        />
      )}

      {status === "success" && programs.length > 0 && (
        <>
          <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
            <Text size="sm" tone="muted">
              <span className="font-semibold text-fg">{programs.length}</span>{" "}
              {programs.length === 1 ? "programme" : "programmes"} found,{" "}
              <span className="font-semibold text-fg">{eligibleCount}</span> you
              currently qualify for.
            </Text>

            <div className="flex flex-wrap items-end gap-3">
              <label className="flex items-center gap-2 text-sm text-fg-muted">
                <Icon icon={SlidersHorizontal} size="xs" />
                <span className="sr-only sm:not-sr-only">Show</span>
                <Select
                  selectSize="sm"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value as Filter)}
                  className="w-44"
                  aria-label="Filter programmes"
                >
                  <option value="all">All programmes</option>
                  <option value="eligible">Ones I qualify for</option>
                  <option value="strong">Strong matches</option>
                  <option value="possible">Possible matches</option>
                  <option value="stretch">Stretch</option>
                  <option value="blocked">Requirement not met</option>
                </Select>
              </label>

              <label className="flex items-center gap-2 text-sm text-fg-muted">
                <span className="sr-only sm:not-sr-only">Sort by</span>
                <Select
                  selectSize="sm"
                  value={sort}
                  onChange={(e) => setSort(e.target.value as SortKey)}
                  className="w-40"
                  aria-label="Sort programmes"
                >
                  <option value="match">Best match</option>
                  <option value="deadline">Earliest deadline</option>
                </Select>
              </label>
            </div>
          </div>

          {visible.length === 0 ? (
            <EmptyState
              icon={SearchX}
              size="sm"
              bordered
              title="Nothing matches that filter"
              description="Every programme found is outside the category you selected."
              actions={
                <Button size="sm" variant="secondary" onClick={() => setFilter("all")}>
                  Show all programmes
                </Button>
              }
            />
          ) : (
            <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {visible.map((program) => (
                <li key={program.programId} className="flex">
                  <OpportunityCard program={program} />
                </li>
              ))}
            </ul>
          )}

          <div className="mt-8 flex items-start gap-3 rounded-panel border border-border bg-canvas-subtle p-4">
            <Icon icon={Target} size="sm" className="mt-0.5 shrink-0 text-fg-subtle" />
            <Text size="sm" tone="muted">
              Match percentages weigh your profile against each programme&apos;s
              stated minimums. They are a starting point for a conversation with
              the university, not an admissions decision — always verify
              requirements on the official programme page before applying.
            </Text>
          </div>
        </>
      )}
    </PageContainer>
  );
}
