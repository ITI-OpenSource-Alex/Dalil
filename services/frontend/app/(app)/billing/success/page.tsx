"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  CheckCircle2,
  FileText,
  GraduationCap,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { getMyProfile } from "@/lib/profile-api";
import {
  Alert,
  Badge,
  Button,
  Card,
  Heading,
  Icon,
  PageContainer,
  Spinner,
  Text,
} from "@/components/ui";

/* ------------------------------------------------------------------ *
 * /billing/success — where the checkout sends the browser afterwards.
 *
 * The redirect itself proves nothing. This URL is an ordinary GET that anybody
 * can type, and nothing in its query string is verified. The only authority on
 * whether the upgrade happened is the backend, which wrote the tier; this
 * page's job is to wait for that to become visible through GET /api/profile
 * and to say something honest in the meantime.
 *
 * So: poll the profile, bounded, and unlock nothing on our own. That property
 * is the reason this page survives a change of payment provider unaltered --
 * it never believed the redirect in the first place.
 * ------------------------------------------------------------------ */

/** ~15s total. Long enough for a webhook round trip, short enough to not hang. */
const POLL_INTERVAL_MS = 1500;
const MAX_ATTEMPTS = 10;

type Phase = "activating" | "active" | "pending";

export default function BillingSuccessPage() {
  const [phase, setPhase] = useState<Phase>("activating");
  const [attempt, setAttempt] = useState(0);
  const [lastError, setLastError] = useState<string | null>(null);
  // Bumped by "Check again" to restart a finished poll cycle.
  const [cycle, setCycle] = useState(0);
  const cancelled = useRef(false);

  useEffect(() => {
    cancelled.current = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;

    async function poll() {
      if (cancelled.current) return;
      attempts += 1;
      setAttempt(attempts);

      try {
        const user = await getMyProfile();
        if (cancelled.current) return;

        if (user.subscriptionTier === "paid") {
          setPhase("active");
          setLastError(null);
          return;
        }
        setLastError(null);
      } catch (err) {
        if (cancelled.current) return;
        // A transient failure is not a verdict. Keep polling; the message is
        // only surfaced if the whole cycle ends without an answer.
        setLastError(
          err instanceof Error ? err.message : "Could not reach your account.",
        );
      }

      if (attempts >= MAX_ATTEMPTS) {
        setPhase("pending");
        return;
      }
      timer = setTimeout(poll, POLL_INTERVAL_MS);
    }

    setPhase("activating");
    poll();

    return () => {
      cancelled.current = true;
      if (timer) clearTimeout(timer);
    };
  }, [cycle]);

  const checkAgain = useCallback(() => {
    setAttempt(0);
    setCycle((value) => value + 1);
  }, []);

  return (
    <PageContainer size="md">
      <div className="mb-8">
        <Badge tone="brand" pill>
          Billing
        </Badge>
        <Heading as="h1" size="xl" className="mt-2">
          {phase === "active"
            ? "Welcome to Dalil Pro"
            : "Confirming your subscription"}
        </Heading>
      </div>

      {phase === "activating" && (
        <Card>
          <div
            className="flex items-start gap-4"
            aria-busy="true"
            aria-live="polite"
          >
            <Spinner className="mt-1 shrink-0" />
            <div>
              <Text className="font-semibold">
                Activating your subscription…
              </Text>
              <Text size="sm" tone="muted" className="mt-1">
                Your payment went through. We&apos;re confirming it with our
                servers — this usually takes a few seconds. You can stay on
                this page.
              </Text>
              <Text size="sm" tone="subtle" className="mt-3">
                Check {attempt} of {MAX_ATTEMPTS}
              </Text>
            </div>
          </div>
        </Card>
      )}

      {phase === "active" && (
        <div className="space-y-6">
          <Alert
            tone="success"
            icon={CheckCircle2}
            title="Your subscription is active"
            announce="polite"
          >
            Every Dalil Pro feature is unlocked on your account. You can cancel
            or change your payment method any time from your profile.
          </Alert>

          <Card>
            <div className="mb-4 flex items-center gap-2">
              <Icon icon={Sparkles} size="sm" className="text-brand-fg" />
              <Text size="sm" className="font-semibold">
                Start here
              </Text>
            </div>
            <div className="flex flex-wrap gap-3">
              {/* Full document navigations, not <Link>. Every mounted
                  useCurrentUser (the sidebar, the exam landing page) is still
                  holding the Free tier it fetched before checkout, and a
                  client-side transition would carry that stale identity into
                  the destination -- which would show a paywall to somebody who
                  just paid. Same reasoning as the sidebar's logout. */}
              <Button asChild leadingIcon={GraduationCap}>
                <a href="/exam">Take an IELTS exam</a>
              </Button>
              <Button asChild variant="secondary" leadingIcon={FileText}>
                <a href="/cv-review">Review my CV</a>
              </Button>
              <Button asChild variant="secondary">
                <a href="/practice">Practice speaking or writing</a>
              </Button>
            </div>
          </Card>

          <Text size="sm" tone="subtle">
            <Link
              href="/billing/manage"
              className="underline underline-offset-4"
            >
              Manage your subscription
            </Link>{" "}
            any time.
          </Text>
        </div>
      )}

      {phase === "pending" && (
        <div className="space-y-6">
          <Alert
            tone="info"
            title="Still activating"
            announce="polite"
            actions={
              <>
                <Button size="sm" leadingIcon={RefreshCw} onClick={checkAgain}>
                  Check again
                </Button>
                <Button size="sm" variant="secondary" asChild>
                  <a href="/dashboard">Go to dashboard</a>
                </Button>
              </>
            }
          >
            Your payment was received and nothing is wrong with your account.
            Confirmation is taking longer than usual, so Pro features may not
            be available for another minute or two.
          </Alert>

          {lastError && (
            <Text size="sm" tone="subtle">
              Last check failed: {lastError}
            </Text>
          )}

          <Text size="sm" tone="subtle">
            If your plan still shows as Free in an hour, contact support and
            we&apos;ll sort it out.
          </Text>
        </div>
      )}
    </PageContainer>
  );
}
