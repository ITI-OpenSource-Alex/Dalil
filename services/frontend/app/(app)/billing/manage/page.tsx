"use client";

import { useState } from "react";
import Link from "next/link";
import { CheckCircle2, Sparkles } from "lucide-react";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";
import {
  billingEnabled,
  cancelSubscription,
  isBillingAuthError,
  isBillingConflictError,
  isBillingUnavailableError,
} from "@/lib/billing-api";
import { PRO_PRICE_LABEL, planForTier } from "@/lib/pricing-plans";
import Skeleton from "@/components/ui/skeleton";
import {
  Alert,
  Badge,
  Button,
  Card,
  Heading,
  Icon,
  Modal,
  ModalContent,
  PageContainer,
  Text,
} from "@/components/ui";

/* ------------------------------------------------------------------ *
 * /billing/manage — GOA-039's "manage subscription".
 *
 * With no payment provider there is no hosted portal to link out to, so this
 * page is the portal: current plan, what it includes, and how to cancel. The
 * cancellation itself is a server call; this page never edits the tier and
 * re-reads it afterwards rather than assuming the result.
 * ------------------------------------------------------------------ */

export default function ManageSubscriptionPage() {
  const { user, status, error, retry } = useCurrentUser();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [cancelled, setCancelled] = useState(false);

  const isPaid = status === "success" && user?.subscriptionTier === "paid";
  const plan = planForTier(user?.subscriptionTier ?? "free");

  async function cancel() {
    if (busy) return;
    setBusy(true);
    setActionError(null);
    try {
      await cancelSubscription();
      setConfirming(false);
      setCancelled(true);
      // The server is the authority on what the tier now is.
      await retry();
    } catch (err) {
      if (
        isBillingConflictError(err) ||
        isBillingUnavailableError(err) ||
        isBillingAuthError(err)
      ) {
        setActionError(err.message);
      } else {
        setActionError(
          err instanceof Error && err.message
            ? err.message
            : "We couldn't cancel your subscription. Please try again.",
        );
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageContainer size="md">
      <div className="mb-8">
        <Badge tone="brand" pill>
          Billing
        </Badge>
        <Heading as="h1" size="xl" className="mt-2">
          Manage subscription
        </Heading>
      </div>

      {status === "loading" && (
        <div className="space-y-2" aria-busy="true" aria-label="Loading your plan">
          <Skeleton />
          <Skeleton />
        </div>
      )}

      {status === "error" && (
        <Alert
          tone="danger"
          actions={
            <Button variant="danger" size="sm" onClick={retry}>
              Retry
            </Button>
          }
        >
          {error ?? "We couldn't load your plan."}
        </Alert>
      )}

      {status === "success" && user && (
        <div className="space-y-6">
          {cancelled && !isPaid && (
            <Alert tone="success" icon={CheckCircle2} announce="polite">
              Your subscription has been cancelled. You&apos;re back on the Free
              plan and Pro features are no longer available.
            </Alert>
          )}

          {actionError && (
            <Alert tone="danger" onDismiss={() => setActionError(null)}>
              {actionError}
            </Alert>
          )}

          <Card>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <Text size="sm" tone="muted" className="font-semibold">
                  Current plan
                </Text>
                <div className="mt-1 flex items-center gap-2">
                  <Icon icon={Sparkles} size="sm" className="text-brand-fg" />
                  <Heading as="h2" size="md">
                    {plan.name}
                  </Heading>
                </div>
                <Text size="sm" tone="muted" className="mt-1">
                  {isPaid ? PRO_PRICE_LABEL : "Free forever"}
                </Text>
              </div>
              {isPaid && (
                <Badge tone="success" size="md">
                  Active
                </Badge>
              )}
            </div>

            <ul className="mt-6 space-y-2">
              {plan.features.map((feature) => (
                <li key={feature} className="flex items-start gap-2.5">
                  <Icon
                    icon={CheckCircle2}
                    size="xs"
                    className="mt-1 shrink-0 text-success-fg"
                  />
                  <Text as="span" size="sm" tone="muted">
                    {feature}
                  </Text>
                </li>
              ))}
            </ul>

            <div className="mt-6 flex flex-wrap gap-3 border-t border-border pt-5">
              {isPaid ? (
                <Button
                  variant="outline"
                  onClick={() => setConfirming(true)}
                  disabled={!billingEnabled()}
                >
                  Cancel subscription
                </Button>
              ) : (
                <Button asChild>
                  <Link href="/pricing">Upgrade to Dalil Pro</Link>
                </Button>
              )}
              <Button variant="ghost" asChild>
                <Link href="/profile">Back to profile</Link>
              </Button>
            </div>
          </Card>

          <Text size="sm" tone="subtle">
            Billing for this project is simulated for demonstration purposes. No
            payment is taken and no card details are stored.
          </Text>
        </div>
      )}

      <Modal open={confirming} onOpenChange={setConfirming}>
        <ModalContent
          title="Cancel Dalil Pro?"
          description="You'll lose access to IELTS exams, AI scoring, speaking practice and CV review."
          size="sm"
          footer={
            <>
              <Button variant="ghost" onClick={() => setConfirming(false)}>
                Keep my plan
              </Button>
              <Button
                variant="danger"
                onClick={cancel}
                loading={busy}
                loadingLabel="Cancelling your subscription"
              >
                Cancel subscription
              </Button>
            </>
          }
        >
          <Text size="sm" tone="muted">
            Your profile, matched programmes and checklists stay exactly as they
            are — those are part of the Free plan.
          </Text>
        </ModalContent>
      </Modal>
    </PageContainer>
  );
}
