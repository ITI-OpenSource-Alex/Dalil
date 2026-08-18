"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Sparkles } from "lucide-react";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";
import { isProfileComplete } from "@/app/types/profile";
import { DEFAULT_UPGRADE_URL } from "@/lib/subscription";
import type { ProfileSectionId } from "@/lib/profile-readiness";
import { ProfileForm } from "@/components/profile/profile-form";
import { ProfileCompletenessCard } from "@/components/profile/profile-completeness-card";
import { OpportunityMatchesSection } from "@/components/profile/opportunity-matches-section";
import { useOpportunityMatches } from "@/components/profile/use-opportunity-matches";
import {
  useProfileTab,
  type ProfileTab,
} from "@/components/profile/use-profile-tab";
import { CvUploadPanel } from "@/components/cv/cv-upload-panel";
import {
  Alert,
  Badge,
  Button,
  Card,
  Heading,
  Icon,
  PageContainer,
  Skeleton,
  Tabs,
  TabsList,
  TabsPanel,
  TabsTrigger,
  Text,
} from "@/components/ui";
import { ExamProgressTab } from "@/components/profile/exam-progress";

/**
 * Profile hub — header → account + matching readiness → Matches | Exam
 * Progress | Edit profile (GOA-029 + GOA-062).
 *
 * The edit form used to sit between the user and the two surfaces that show
 * what the form is *for*. It is now a tab of equal standing, with the meter in
 * the header carrying the "you still owe us X" message the form's inline
 * badge used to.
 */
export default function ProfilePage() {
  // useProfileTab reads useSearchParams, which opts this subtree out of static
  // prerendering and so needs a boundary — same reason exam/results has one.
  return (
    <Suspense fallback={<ProfileSkeleton />}>
      <ProfileHub />
    </Suspense>
  );
}

function ProfileSkeleton() {
  return (
    <PageContainer size="md">
      <div className="space-y-4" aria-busy="true" aria-label="Loading profile">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-28 w-full rounded-card" />
        <Skeleton className="h-28 w-full rounded-card" />
        <Skeleton className="h-64 w-full rounded-card" />
      </div>
    </PageContainer>
  );
}

function ProfileHub() {
  const { user, status, error, retry, patchProfile } = useCurrentUser();
  const { tab, setTab } = useProfileTab();

  const [pendingSection, setPendingSection] = useState<ProfileSectionId | null>(
    null,
  );
  // Bumped on every successful save. useOpportunityMatches re-ranks the next
  // time the Matches tab is shown — not on the save itself, because matching
  // is capped at 20 searches an hour and a form is many saves.
  const [savedAt, setSavedAt] = useState(0);

  const matches = useOpportunityMatches({
    enabled: isProfileComplete(user?.profile ?? null),
    visible: tab === "matches",
    savedAt,
  });

  /** Open the form on the section that owns a missing field, and focus it. */
  const focusSection = useCallback(
    (section: ProfileSectionId) => {
      setTab("edit");
      setPendingSection(section);
    },
    [setTab],
  );

  // Runs after the edit panel has been committed to the DOM, so the anchor the
  // user asked for exists by the time we look for it.
  useEffect(() => {
    if (tab !== "edit" || !pendingSection) return;
    const node = document.getElementById(pendingSection);
    if (!node) return;
    node.scrollIntoView({ behavior: "smooth", block: "start" });
    node
      .querySelector<HTMLElement>(
        "input:not([type='hidden']), select, textarea, button, [tabindex]:not([tabindex='-1'])",
      )
      ?.focus({ preventScroll: true });
    setPendingSection(null);
  }, [tab, pendingSection]);

  return (
    <PageContainer size="md">
      <div className="mb-6">
        <Badge tone="brand" pill>
          Your Profile
        </Badge>
        <Heading as="h1" size="xl" className="mt-2">
          Account &amp; Application Profile
        </Heading>
        <Text size="sm" tone="muted" className="mt-1">
          Everything here feeds programme matching. Keep it current and your
          matches stay current — changes save when you leave a field.
        </Text>
      </div>

      {status === "loading" && (
        <div
          className="space-y-2"
          aria-busy="true"
          aria-label="Loading profile"
        >
          <Skeleton />
          <Skeleton />
          <Skeleton />
        </div>
      )}

      {status === "error" && (
        <Alert
          tone="danger"
          announce="assertive"
          actions={
            <>
              <Button variant="danger" size="sm" onClick={retry}>
                Retry
              </Button>
              <Button variant="link" size="sm" asChild>
                <Link href="/login">Log in again</Link>
              </Button>
            </>
          }
        >
          {error}
        </Alert>
      )}

      {status === "success" && user && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Card>
              <Heading as="h2" size="xs" className="mb-4 text-fg-muted">
                Account
              </Heading>
              <dl className="grid grid-cols-1 gap-4 text-sm">
                <ReadOnlyField label="Email" value={user.email} />
                <ReadOnlyField
                  label="Subscription"
                  value={
                    user.subscriptionTier === "paid" ? "Dalil Pro" : "Free plan"
                  }
                />
              </dl>
              <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-border pt-4">
                <Icon icon={Sparkles} size="sm" className="text-brand-fg" />
                <Text size="sm" tone="muted" className="flex-1">
                  {user.subscriptionTier === "paid"
                    ? "Review your plan or cancel any time."
                    : "IELTS exams, essay scoring and CV review are part of Dalil Pro."}
                </Text>
                <Button size="sm" variant="outline" asChild>
                  <Link
                    href={
                      user.subscriptionTier === "paid"
                        ? "/billing/manage"
                        : DEFAULT_UPGRADE_URL
                    }
                  >
                    {user.subscriptionTier === "paid"
                      ? "Manage subscription"
                      : "See plans"}
                  </Link>
                </Button>
              </div>
            </Card>

            <ProfileCompletenessCard
              profile={user.profile}
              onFix={focusSection}
            />
          </div>

          <Tabs
            value={tab}
            onValueChange={(value) => setTab(value as ProfileTab)}
          >
            <TabsList variant="underline">
              <TabsTrigger value="matches">Matches</TabsTrigger>
              <TabsTrigger value="progress">Exam Progress</TabsTrigger>
              <TabsTrigger value="cv">CV</TabsTrigger>
              <TabsTrigger value="edit">Edit profile</TabsTrigger>
            </TabsList>

            <TabsPanel value="matches">
              <OpportunityMatchesSection
                programs={matches.programs}
                status={matches.status}
                error={matches.error}
                retryAfter={matches.retryAfter}
                onReload={matches.reload}
                onFocusProfile={() => focusSection("profile-section-academic")}
              />
            </TabsPanel>

            <TabsPanel value="progress">
              <ExamProgressTab />
            </TabsPanel>

            <TabsPanel value="cv" className="space-y-4">
              <div>
                <Heading as="h2" size="sm">
                  Your CV
                </Heading>
                <Text size="sm" tone="muted" className="mt-1">
                  Upload it once here. Each programme checklist can then generate
                  recommendations against that programme&apos;s actual requirements.
                </Text>
              </div>
              <CvUploadPanel />
            </TabsPanel>

            <TabsPanel value="edit" className="space-y-6">
              <Card>
                <Heading as="h2" size="xs" className="mb-4 text-fg-muted">
                  Application Profile
                </Heading>
                <ProfileForm
                  profile={user.profile}
                  onOptimisticUser={patchProfile}
                  onSaved={() => setSavedAt((n) => n + 1)}
                  onSaveError={() => {
                    void retry();
                  }}
                />
              </Card>
            </TabsPanel>
          </Tabs>
        </div>
      )}
    </PageContainer>
  );
}

function ReadOnlyField({
  label,
  value,
}: {
  label: string;
  value: string | number | null;
}) {
  return (
    <div>
      <dt className="text-xs text-fg-subtle">{label}</dt>
      <dd className="mt-0.5 text-fg">
        {value === null || value === undefined || value === "" ? "—" : value}
      </dd>
    </div>
  );
}
