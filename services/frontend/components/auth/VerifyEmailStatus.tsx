"use client";

import Link from "next/link";
import { ArrowRight, CheckCircle2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { authApi, apiErrorMessage } from "@/lib/api";
import { Button, Icon, Spinner, Text } from "@/components/ui";

type Status = "verifying" | "success" | "error";

/**
 * Lands GET /auth/verify-email/:token (services/user/src/users/auth.controller.ts)
 * on mount. No frontend page previously consumed this endpoint even though
 * registration already triggers the verification email server-side.
 */
export default function VerifyEmailStatus({ token }: { token: string }) {
  const [status, setStatus] = useState<Status>("verifying");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    authApi
      .verifyEmail(token)
      .then(() => {
        if (!cancelled) setStatus("success");
      })
      .catch((err) => {
        if (cancelled) return;
        setMessage(
          apiErrorMessage(err) ??
            "This link has expired or was already used.",
        );
        setStatus("error");
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  if (status === "verifying") {
    return (
      <div className="flex flex-col items-center gap-4 py-4 text-center" role="status">
        <Spinner size="lg" label="Verifying your email" />
        <Text size="sm" tone="muted">
          Verifying your email&hellip;
        </Text>
      </div>
    );
  }

  if (status === "success") {
    return (
      <div className="flex flex-col items-center gap-3 py-2 text-center" role="status">
        <span className="flex h-14 w-14 items-center justify-center rounded-full bg-success-subtle text-success">
          <Icon icon={CheckCircle2} size="lg" />
        </span>
        <p className="text-base font-semibold text-fg">Email verified</p>
        <Text size="sm" tone="muted" className="max-w-xs">
          Your account is confirmed. You&apos;re ready to sign in.
        </Text>
        <Button asChild size="lg" fullWidth trailingIcon={ArrowRight} className="mt-2">
          <Link href="/login">Continue to sign in</Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-3 py-2 text-center" role="alert">
      <span className="flex h-14 w-14 items-center justify-center rounded-full bg-danger-subtle text-danger">
        <Icon icon={XCircle} size="lg" />
      </span>
      <p className="text-base font-semibold text-fg">Verification failed</p>
      <Text size="sm" tone="muted" className="max-w-xs">
        {message}
      </Text>
      <Button asChild variant="secondary" size="lg" fullWidth className="mt-2">
        <Link href="/login">Back to sign in</Link>
      </Button>
    </div>
  );
}
