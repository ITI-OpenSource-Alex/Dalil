"use client";

import Link from "next/link";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";
import Skeleton from "@/components/ui/skeleton";
import { Alert, Badge, Button, Card, Heading, PageContainer, Text } from "@/components/ui";

export default function ProfilePage() {
  const { user, status, error, retry } = useCurrentUser();

  return (
    <PageContainer size="md">
      <div className="mb-8">
        <Badge tone="brand" pill>
          Your Profile
        </Badge>
        <Heading as="h1" size="xl" className="mt-2">
          Account & Application Profile
        </Heading>
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
            <dl className="grid grid-cols-2 gap-4 text-sm">
              <Field label="Email" value={user.email} />
              <Field
                label="Subscription"
                value={user.subscriptionTier === "paid" ? "Paid" : "Free"}
              />
            </dl>
          </Card>

          <Card>
            <Text size="sm" tone="muted" className="mb-4 font-semibold">
              Application Profile
            </Text>
            {!user.profile && (
              <Alert tone="info" announce="none" className="mb-4">
                Your application profile is incomplete.
                <div className="mt-3">
                  <Button size="sm" asChild>
                    <Link href="/onboarding">Complete Profile</Link>
                  </Button>
                </div>
              </Alert>
            )}
            {user.profile ? (
              <dl className="grid grid-cols-2 gap-4 text-sm">
                <Field label="Degree level" value={user.profile.degreeLevel} />
                <Field
                  label="GPA"
                  value={
                    user.profile.gpa !== null
                      ? `${user.profile.gpa} / ${user.profile.gpaScale}`
                      : null
                  }
                />
                <Field label="IELTS score" value={user.profile.ieltsScore} />
                <Field label="Field of study" value={user.profile.fieldOfStudy} />
                <Field label="ECTS credits" value={user.profile.ects} />
                <Field
                  label="Work experience"
                  value={
                    user.profile.workExperienceYears !== null
                      ? `${user.profile.workExperienceYears} years`
                      : null
                  }
                />
                <Field
                  label="Target countries"
                  value={
                    user.profile.targetCountries.length > 0
                      ? user.profile.targetCountries.join(", ")
                      : null
                  }
                />
              </dl>
            ) : (
              <Text size="sm" tone="muted">
                No application profile on file yet.
              </Text>
            )}
          </Card>
        </div>
      )}
    </PageContainer>
  );
}

function Field({
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
