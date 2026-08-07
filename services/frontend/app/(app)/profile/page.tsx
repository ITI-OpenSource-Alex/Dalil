"use client";

import { useState } from "react";
import Link from "next/link";
import { CheckCircle2, Pencil, Sparkles } from "lucide-react";
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
  const { user, status, error, retry } = useCurrentUser();
  const [editing, setEditing] = useState(false);
  const [justSaved, setJustSaved] = useState(false);

  async function handleSaved() {
    setEditing(false);
    setJustSaved(true);
    // Refetch rather than patching local state from the form's own values: the
    // server is the authority on what was actually stored (it coerces types
    // and ignores unknown fields), and showing the submitted values instead
    // would quietly hide a partial write.
    await retry();
  }

  return (
    <PageContainer size="md">
      <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <Badge tone="brand" pill>
            Your Profile
          </Badge>
          <Heading as="h1" size="xl" className="mt-2">
            Account &amp; Application Profile
          </Heading>
          <Text size="sm" tone="muted" className="mt-1">
            Everything here feeds programme matching. Keep it current and your
            matches stay current.
          </Text>
        </div>

        {status === "success" && user && !editing && (
          <Button leadingIcon={Pencil} onClick={() => setEditing(true)}>
            Edit profile
          </Button>
        )}
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
          {justSaved && !editing && (
            <Alert tone="success" announce="polite" icon={CheckCircle2}>
              Profile saved. Your programme matches will use it from now on.
            </Alert>
          )}

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
              {!editing && !isProfileComplete(user.profile) && (
                <Badge tone="warning" size="sm" pill>
                  Incomplete
                </Badge>
              )}
            </div>

            {editing ? (
              <ProfileForm
                profile={user.profile}
                onCancel={() => setEditing(false)}
                onSaved={handleSaved}
              />
            ) : (
              <>
                {!isProfileComplete(user.profile) && (
                  <Alert tone="info" announce="none" className="mb-4">
                    Your application profile is incomplete, so programme
                    matching has little to work with.
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button size="sm" onClick={() => setEditing(true)}>
                        Fill it in here
                      </Button>
                      <Button size="sm" variant="secondary" asChild>
                        <Link href="/onboarding">Use the guided wizard</Link>
                      </Button>
                    </div>
                  </Alert>
                )}

                <dl className="grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
                  <ReadOnlyField
                    label="Degree level"
                    value={user.profile?.degreeLevel ?? null}
                  />
                  <ReadOnlyField
                    label="Field of study"
                    value={user.profile?.fieldOfStudy ?? null}
                  />
                  <ReadOnlyField
                    label="GPA"
                    value={
                      user.profile?.gpa != null
                        ? `${user.profile.gpa} / ${user.profile.gpaScale}`
                        : null
                    }
                  />
                  <ReadOnlyField
                    label="ECTS credits"
                    value={user.profile?.ects ?? null}
                  />
                  <ReadOnlyField
                    label="IELTS overall band"
                    value={
                      user.profile?.ieltsScore != null
                        ? user.profile.ieltsScore.toFixed(1)
                        : null
                    }
                  />
                  <ReadOnlyField
                    label="Work experience"
                    value={
                      user.profile?.workExperienceYears != null
                        ? `${user.profile.workExperienceYears} years`
                        : null
                    }
                  />
                  <ReadOnlyField
                    label="Extracurriculars"
                    value={
                      user.profile?.extracurricularsScore != null
                        ? `${user.profile.extracurricularsScore} / 10`
                        : null
                    }
                  />
                  <ReadOnlyField
                    label="Target countries"
                    value={
                      user.profile?.targetCountries.length
                        ? user.profile.targetCountries.join(", ")
                        : null
                    }
                  />
                </dl>
              </>
            )}
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
