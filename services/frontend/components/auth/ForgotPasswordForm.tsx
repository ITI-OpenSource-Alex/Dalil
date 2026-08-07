"use client";

import Link from "next/link";
import { ArrowLeft, ArrowRight, MailCheck } from "lucide-react";
import { useRef, useState } from "react";
import { authApi } from "@/lib/api";
import { Button, Field, Icon, Input, Text } from "@/components/ui";

const RESEND_COOLDOWN_SECONDS = 30;

/**
 * The "send me a reset link" step, at POST /auth/forgot-password. Distinct
 * from ResetPasswordForm, which is the token-confirm step at
 * POST /auth/reset-password -- the two were previously conflated under one
 * route calling the wrong endpoint (see docs/FRONTEND-REDESIGN-PLAN.md §16.1).
 */
export default function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const cooldownTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  function startCooldown() {
    setCooldown(RESEND_COOLDOWN_SECONDS);
    cooldownTimer.current = setInterval(() => {
      setCooldown((prev) => {
        if (prev <= 1 && cooldownTimer.current) {
          clearInterval(cooldownTimer.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }

  async function submitRequest() {
    setLoading(true);
    try {
      await authApi.forgotPassword(email);
    } finally {
      // The backend intentionally doesn't reveal whether the address exists
      // (email enumeration protection) -- so a request failure and a request
      // for an unknown address look identical to the user by design. There is
      // nothing more specific and honest to show here than "if it exists".
      setLoading(false);
      setSent(true);
      startCooldown();
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    void submitRequest();
  }

  if (sent) {
    return (
      <div className="flex flex-col items-center gap-4 py-2 text-center" role="status">
        <span className="flex h-14 w-14 items-center justify-center rounded-full bg-brand-muted text-brand-fg">
          <Icon icon={MailCheck} size="lg" />
        </span>
        <div>
          <p className="text-base font-semibold text-fg">Check your inbox</p>
          <Text size="sm" tone="muted" className="mt-1.5">
            If an account exists for{" "}
            <span className="font-medium text-fg">{email}</span>, we&apos;ve
            sent a link to reset your password. It may take a minute to
            arrive.
          </Text>
        </div>

        <Button
          variant="secondary"
          size="sm"
          disabled={cooldown > 0}
          loading={loading}
          onClick={() => void submitRequest()}
        >
          {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend link"}
        </Button>

        <Link
          href="/login"
          className="mt-1 inline-flex items-center gap-2 text-sm font-medium text-brand-fg hover:text-brand-active"
        >
          <Icon icon={ArrowLeft} size="xs" />
          Back to sign in
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5">
      <Field label="Email" required hint="We'll send a reset link to this address.">
        <Input
          type="email"
          name="email"
          autoComplete="email"
          placeholder="you@university.edu"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </Field>

      <Button type="submit" size="lg" fullWidth loading={loading} trailingIcon={ArrowRight}>
        Send reset link
      </Button>

      <Link
        href="/login"
        className="inline-flex items-center justify-center gap-2 text-sm text-fg-muted hover:text-fg"
      >
        <Icon icon={ArrowLeft} size="xs" />
        Back to sign in
      </Link>
    </form>
  );
}
