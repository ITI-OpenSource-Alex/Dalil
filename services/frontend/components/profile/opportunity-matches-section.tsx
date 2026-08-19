"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, RefreshCw, SearchX, UserPen } from "lucide-react";
import { type MatchedProgram } from "@/lib/opportunities-api";
import type { MatchesStatus } from "./use-opportunity-matches";
import { OpportunityCard } from "@/components/opportunities/opportunity-card";
import { OpportunityDetailModal } from "@/components/opportunities/opportunity-detail-modal";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  Heading,
  Skeleton,
  Text,
} from "@/components/ui";

/**
 * Compact matches strip for the profile hub.
 *
 * Same fetch + error vocabulary as /opportunities, without sort/filter chrome.
 * Incomplete profiles get a CTA back to the application form rather than a
 * search that cannot usefully run.
 */
export function OpportunityMatchesSection({
  programs,
  status,
  error,
  retryAfter,
  onReload,
  onFocusProfile,
}: {
  programs: MatchedProgram[];
  status: MatchesStatus;
  error: string | null;
  retryAfter: string | null;
  onReload: () => void;
  onFocusProfile?: () => void;
}) {
  const [selected, setSelected] = useState<MatchedProgram | null>(null);

  return (
    <section className="space-y-4" aria-labelledby="opportunity-matches-heading">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Heading as="h2" size="sm" id="opportunity-matches-heading">
            Opportunity matches
          </Heading>
          <Text size="sm" tone="muted" className="mt-1">
            Top programmes ranked against your current profile.
          </Text>
        </div>
        {status === "success" && programs.length > 0 && (
          <Button size="sm" variant="ghost" trailingIcon={ArrowRight} asChild>
            <Link href="/opportunities">View all</Link>
          </Button>
        )}
      </div>

      {status === "profile-incomplete" && (
        <EmptyState
          icon={UserPen}
          size="sm"
          bordered
          title="Finish your profile to see matches"
          description="Matching needs your degree, GPA, credits or IELTS band before it can rank programmes."
          actions={
            onFocusProfile ? (
              <Button size="sm" onClick={onFocusProfile}>
                Complete application profile
              </Button>
            ) : (
              <Button size="sm" asChild>
                <Link href="#application-profile">Complete application profile</Link>
              </Button>
            )
          }
        />
      )}

      {status === "syncing" && (
        <Alert
          tone="info"
          announce="polite"
          title="Your profile is still syncing"
          actions={
            <Button size="sm" onClick={onReload}>
              Try again
            </Button>
          }
        >
          You saved it a moment ago and matching hasn&apos;t picked it up yet.
          This usually takes a few seconds.
        </Alert>
      )}

      {status === "rate-limited" && (
        <Alert
          tone="warning"
          announce="polite"
          title="You have reached this hour's matching limit"
        >
          Programme matching is capped at 20 searches an hour per account.
          {retryAfter
            ? ` Try again in about ${retryAfter}.`
            : " Try again shortly."}
        </Alert>
      )}

      {status === "error" && error && (
        <Alert
          tone="danger"
          announce="assertive"
          actions={
            <Button variant="danger" size="sm" onClick={onReload}>
              Try again
            </Button>
          }
        >
          {error}
        </Alert>
      )}

      {status === "loading" && (
        <div
          aria-busy="true"
          aria-label="Finding programmes that match your profile"
          className="grid grid-cols-1 gap-4 sm:grid-cols-2"
        >
          {[0, 1, 2, 3].map((i) => (
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
          size="sm"
          bordered
          title="No programmes matched yet"
          description="Widen your target countries or adjust your academic details — then refresh matches."
          actions={
            <>
              {onFocusProfile && (
                <Button size="sm" variant="secondary" onClick={onFocusProfile}>
                  Adjust profile
                </Button>
              )}
              <Button size="sm" leadingIcon={RefreshCw} onClick={onReload}>
                Refresh matches
              </Button>
            </>
          }
        />
      )}

      {status === "success" && programs.length > 0 && (
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {programs.map((program) => (
            <li key={program.programId} className="flex">
              <OpportunityCard program={program} onOpen={setSelected} />
            </li>
          ))}
        </ul>
      )}

      <OpportunityDetailModal
        program={selected}
        open={!!selected}
        onOpenChange={(open) => !open && setSelected(null)}
      />
    </section>
  );
}
