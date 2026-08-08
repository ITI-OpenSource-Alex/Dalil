"use client";

import Link from "next/link";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";
import { Button, Card, Progress, Skeleton, Text } from "@/components/ui";
import type { UserProfileDetail } from "@/app/types/profile";

/** The same fields onboarding actually collects (buildProfilePayload,
 *  app/onboarding/page.tsx) and isProfileComplete checks -- this widget is a
 *  finer-grained view of the same signal, not a separate metric invented for
 *  the Dashboard. */
const TRACKED_FIELDS: { key: keyof UserProfileDetail; label: string }[] = [
  { key: "degreeLevel", label: "Degree level" },
  { key: "fieldOfStudy", label: "Field of study" },
  { key: "gpa", label: "GPA" },
  { key: "ieltsScore", label: "IELTS score" },
  { key: "targetCountries", label: "Target countries" },
];

function filledCount(profile: UserProfileDetail | null): number {
  if (!profile) return 0;
  return TRACKED_FIELDS.reduce((count, field) => {
    const value = profile[field.key];
    const filled = Array.isArray(value) ? value.length > 0 : value !== null;
    return filled ? count + 1 : count;
  }, 0);
}

/** "Overall progress" -- how much of the application profile is filled in.
 *  A real, derived number rather than a placeholder: onboarding and the
 *  profile page both write these same fields. */
export function ProgressWidget() {
  const { user, status } = useCurrentUser();

  if (status === "loading" || status === "idle") {
    return (
      <Card>
        <Skeleton className="h-4 w-32" />
        <Skeleton className="mt-4 h-2 w-full" />
      </Card>
    );
  }

  if (status === "error" || !user) return null;

  const filled = filledCount(user.profile);
  const total = TRACKED_FIELDS.length;

  return (
    <Card>
      <div className="mb-1 flex items-center justify-between gap-3">
        <Text size="sm" tone="muted" className="font-semibold">
          Profile completeness
        </Text>
        {filled < total && (
          <Button variant="link" size="sm" asChild>
            <Link href="/profile">Finish it</Link>
          </Button>
        )}
      </div>
      <Progress
        value={filled}
        max={total}
        label="Profile completeness"
        valueText={`${filled} of ${total} fields`}
        showValue
        tone={filled === total ? "success" : "brand"}
      />
    </Card>
  );
}
