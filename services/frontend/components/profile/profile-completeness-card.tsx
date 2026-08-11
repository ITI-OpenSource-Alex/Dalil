"use client";

import Link from "next/link";
import { Button, Card, Progress, Text } from "@/components/ui";
import { matchReadiness, type ProfileSectionId } from "@/lib/profile-readiness";
import type { UserProfileDetail } from "@/app/types/profile";

/**
 * Matching readiness as a meter plus one button per gap.
 *
 * Replaces the page's binary "Incomplete" badge, which told a user that
 * something was missing without saying what, and sat next to an Alert saying
 * the same thing again.
 */
export function ProfileCompletenessCard({
  profile,
  onFix,
}: {
  profile: UserProfileDetail | null;
  onFix: (section: ProfileSectionId) => void;
}) {
  const { filled, total, missing, ready } = matchReadiness(profile);

  return (
    <Card>
      <Progress
        value={filled}
        max={total}
        label="Matching readiness"
        valueText={`${filled} of ${total} details`}
        showValue
        tone={ready ? "success" : "brand"}
      />

      <Text size="sm" tone="muted" className="mt-3">
        {ready
          ? "Your profile has everything programme matching reads."
          : "Programme matching ranks on these details. The more you add, the better the shortlist."}
      </Text>

      {missing.length > 0 && (
        <>
          <ul className="mt-3 flex flex-wrap gap-2">
            {missing.map((field) => (
              <li key={field.key}>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onFix(field.section)}
                >
                  Add {field.label}
                </Button>
              </li>
            ))}
          </ul>
          <Text size="sm" tone="subtle" className="mt-3">
            Prefer to be walked through it?{" "}
            <Link
              href="/onboarding"
              className="font-medium text-brand-fg underline underline-offset-2"
            >
              Use the guided wizard
            </Link>
          </Text>
        </>
      )}
    </Card>
  );
}
