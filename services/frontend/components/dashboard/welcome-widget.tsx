"use client";

import Link from "next/link";
import { AlertCircle } from "lucide-react";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";
import { isProfileComplete } from "@/app/types/profile";
import { emailGreetingName } from "@/lib/user-display";
import { Badge, Button, Card, Heading, Skeleton, Text } from "@/components/ui";

/** Dashboard's first widget: who you are and whether anything needs attention. */
export function WelcomeWidget() {
  const { user, status } = useCurrentUser();

  if (status === "loading" || status === "idle") {
    return (
      <Card>
        <Skeleton className="h-6 w-56" />
        <Skeleton className="mt-3 h-4 w-72" />
      </Card>
    );
  }

  if (status === "error" || !user) {
    return (
      <Card>
        <Heading as="h1" size="xl">
          Welcome back
        </Heading>
      </Card>
    );
  }

  const complete = isProfileComplete(user.profile);

  return (
    <Card className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <Badge tone="brand" pill>
          {user.subscriptionTier === "paid" ? "GOA Pro" : "Free plan"}
        </Badge>
        <Heading as="h1" size="xl" className="mt-2">
          Welcome back, {emailGreetingName(user.email)}
        </Heading>
        <Text size="sm" tone="muted" className="mt-1">
          Here&apos;s where your IELTS prep and applications stand today.
        </Text>
      </div>
      {!complete && (
        <Button variant="secondary" leadingIcon={AlertCircle} asChild>
          <Link href="/onboarding">Complete your profile</Link>
        </Button>
      )}
    </Card>
  );
}
