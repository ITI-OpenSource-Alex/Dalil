"use client";

import { useRouter } from "next/navigation";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";
import { ProfileCompletenessCard } from "@/components/profile/profile-completeness-card";
import type { ProfileSectionId } from "@/lib/profile-readiness";
import { Card, Skeleton } from "@/components/ui";

/** Matching readiness — same meter as the profile page header, so the
 *  dashboard and profile never disagree about what still blocks matching. */
export function ProgressWidget() {
  const { user, status } = useCurrentUser();
  const router = useRouter();

  if (status === "loading" || status === "idle") {
    return (
      <Card>
        <Skeleton className="h-4 w-32" />
        <Skeleton className="mt-4 h-2 w-full" />
      </Card>
    );
  }

  if (status === "error" || !user) return null;

  function goFixSection(_section: ProfileSectionId) {
    router.push("/profile?tab=edit");
  }

  return (
    <ProfileCompletenessCard profile={user.profile} onFix={goFixSection} />
  );
}
