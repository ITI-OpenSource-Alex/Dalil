"use client";

import Link from "next/link";
import { Sparkles } from "lucide-react";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";
import { isProfileComplete } from "@/app/types/profile";
import { DEFAULT_UPGRADE_URL } from "@/lib/subscription";
import { ProfileForm } from "@/components/profile/profile-form";
import Skeleton from "@/components/ui/skeleton";
import {
  Alert,
  Badge,
  Button,
  Card,
  Heading,
  Icon,
  PageContainer,
  Text,
} from "@/components/ui";

export default function ProfilePage() {
  const { user, status, error, retry, patchProfile } = useCurrentUser();

  return (
    <PageContainer size="md">
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
        <div className="space-y-2" aria-busy="true" aria-label="Loading profile">
          <Skeleton />
          <Skeleton />
          <Skeleton />
        </div>
      )}

      {status === "error" && (
        <Alert
          tone="danger"
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
          <Card>
            <Text size="sm" tone="muted" className="mb-4 font-semibold">
              Account
            </Text>
            <dl className="grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
              <ReadOnlyField label="Email" value={user.email} />
              <ReadOnlyField
                label="Subscription"
                value={user.subscriptionTier === "paid" ? "GOA Pro" : "Free plan"}
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

          <Card>
            <div className="mb-4 flex items-center justify-between gap-3">
              <Text size="sm" tone="muted" className="font-semibold">
                Application Profile
              </Text>
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
                void retry();
              }}
            />
          </Card>
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
