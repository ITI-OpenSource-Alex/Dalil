"use client";

import Link from "next/link";
import { Sparkles } from "lucide-react";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";
import { isProfileComplete } from "@/app/types/profile";
import { DEFAULT_UPGRADE_URL } from "@/lib/subscription";
import { ProfileForm } from "@/components/profile/profile-form";
import { OpportunityMatchesSection } from "@/components/profile/opportunity-matches-section";
import { CvUploadPanel } from "@/components/cv/cv-upload-panel";
import Skeleton from "@/components/ui/skeleton";
import {
  Alert,
  Badge,
  Button,
  Card,
  Heading,
  Icon,
  PageContainer,
  Tabs,
  TabsList,
  TabsPanel,
  TabsTrigger,
  Text,
} from "@/components/ui";
import { ExamProgressTab } from "@/components/profile/exam-progress";

/**
 * Profile hub — header → account → always-on ProfileForm → CV →
 * Opportunities | Exam Progress tabs (GOA-029 + GOA-062).
 * Autosave status lives in the form; hard load failures use the page Alert.
 */
export default function ProfilePage() {
  const { user, status, error, retry, patchProfile } = useCurrentUser();

  const focusApplicationProfile = () => {
    const section = document.getElementById("application-profile");
    section?.scrollIntoView({ behavior: "smooth", block: "start" });
    section?.focus({ preventScroll: true });
    const firstField = section?.querySelector<HTMLElement>(
      "input:not([type='hidden']), select, textarea, button, [tabindex]:not([tabindex='-1'])",
    );
    firstField?.focus({ preventScroll: true });
  };

  return (
    <PageContainer size="md">
      {/* 1. Header */}
      <div className="mb-8">
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

      {/* Page-level Alert for hard load failures only */}
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
        <div className="space-y-8">
          {/* 2. Account card — read-only */}
          <Card>
            <Heading as="h2" size="xs" className="mb-4 text-fg-muted">
              Account
            </Heading>
            <dl className="grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
              <ReadOnlyField label="Email" value={user.email} />
              <ReadOnlyField
                label="Subscription"
                value={
                  user.subscriptionTier === "paid" ? "GOA Pro" : "Free plan"
                }
              />
            </dl>
            {user.subscriptionTier !== "paid" && (
              <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-border pt-4">
                <Icon icon={Sparkles} size="sm" className="text-brand-fg" />
                <Text size="sm" tone="muted" className="flex-1">
                  IELTS exams, essay scoring and CV review are part of GOA Pro.
                </Text>
                <Button size="sm" variant="outline" asChild>
                  <Link href={DEFAULT_UPGRADE_URL}>See plans</Link>
                </Button>
              </div>
            )}
          </Card>

          {/* 3. Application profile — always ProfileForm (no Edit/Cancel/Save) */}
          <Card
            id="application-profile"
            tabIndex={-1}
            className="scroll-mt-6 outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
          >
            <div className="mb-4 flex items-center justify-between gap-3">
              <Heading as="h2" size="xs" className="text-fg-muted">
                Application Profile
              </Heading>
              {!isProfileComplete(user.profile) && (
                <Badge tone="warning" size="sm" pill>
                  Incomplete
                </Badge>
              )}
            </div>

            {!isProfileComplete(user.profile) && (
              <Alert tone="info" announce="none" className="mb-4">
                Your application profile is incomplete, so programme matching
                has little to work with. Fill in the fields below, or{" "}
                <Link
                  href="/onboarding"
                  className="font-medium text-brand-fg underline underline-offset-2"
                >
                  use the guided wizard
                </Link>
                .
              </Alert>
            )}

            <ProfileForm
              profile={user.profile}
              onOptimisticUser={patchProfile}
              onSaveError={() => {
                // Hard autosave failure: resync from server (rolls form back).
                void retry();
              }}
            />
          </Card>

          {/* 4. CV upload */}
          <section className="space-y-3" aria-labelledby="profile-cv-heading">
            <div>
              <Heading as="h2" size="sm" id="profile-cv-heading">
                CV
              </Heading>
              <Text size="sm" tone="muted" className="mt-1">
                Upload or replace your CV here. AI review stays on the CV Review
                page.
              </Text>
            </div>
            <CvUploadPanel showReviewLink />
          </section>

          {/* 5. Opportunities | Exam Progress */}
          <section className="space-y-4" aria-label="Profile tabs">
            <Tabs defaultValue="opportunities">
              <TabsList variant="underline">
                <TabsTrigger value="opportunities">Opportunities</TabsTrigger>
                <TabsTrigger value="exam-progress">Exam Progress</TabsTrigger>
              </TabsList>
              <TabsPanel value="opportunities" className="pt-4">
                <OpportunityMatchesSection
                  profileComplete={isProfileComplete(user.profile)}
                  onFocusProfile={focusApplicationProfile}
                />
              </TabsPanel>
              <TabsPanel value="exam-progress" className="pt-4">
                <ExamProgressTab />
              </TabsPanel>
            </Tabs>
          </section>
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
