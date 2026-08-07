"use client";

import Link from "next/link";
import { ArrowRight, CheckCircle2, Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { authApi, apiErrorMessage } from "@/lib/api";
import { Alert, Button, Field, Icon, Input } from "@/components/ui";

/**
 * The token-confirm step: reads `token` from the URL and calls
 * POST /auth/reset-password with { token, newPassword } (the DTO at
 * services/user/src/users/dto/reset-password.dto.ts). Previously no page in
 * the app consumed this endpoint at all.
 */
export default function ResetPasswordForm({ token }: { token: string | null }) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<{ password?: string; confirmPassword?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  if (!token) {
    return (
      <Alert tone="danger" announce="none" title="This link is invalid">
        Password reset links are single-use and only valid for a limited
        time. Request a new one to continue.
        <div className="mt-3">
          <Link
            href="/forgot-password"
            className="inline-flex items-center gap-1.5 text-sm font-semibold text-danger-fg hover:underline"
          >
            Request a new link
            <Icon icon={ArrowRight} size="xs" />
          </Link>
        </div>
      </Alert>
    );
  }

  if (done) {
    return (
      <div className="flex flex-col items-center gap-3 py-4 text-center" role="status">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-success-subtle text-success">
          <Icon icon={CheckCircle2} size="lg" />
        </span>
        <p className="text-base font-semibold text-fg">Password updated</p>
        <p className="text-sm leading-6 text-fg-muted">Taking you to sign in&hellip;</p>
      </div>
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);

    const nextFieldErrors: typeof fieldErrors = {};
    if (password.length < 6) {
      nextFieldErrors.password = "Password must be at least 6 characters.";
    }
    if (password !== confirmPassword) {
      nextFieldErrors.confirmPassword = "Passwords do not match.";
    }
    setFieldErrors(nextFieldErrors);
    if (Object.keys(nextFieldErrors).length > 0) return;

    setLoading(true);
    try {
      await authApi.resetPassword(token as string, password);
      setDone(true);
      setTimeout(() => router.push("/login"), 1400);
    } catch (err) {
      const message = apiErrorMessage(err);
      // A 400/401 here almost always means the token expired or was already
      // used -- distinguishing that from a generic failure is worth doing
      // since the fix ("request a new link") is different from "try again".
      setFormError(
        message ??
          "This link has expired or was already used. Request a new one and try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-5">
      <Field label="New password" required hint="At least 6 characters." error={fieldErrors.password}>
        <Input
          type={showPassword ? "text" : "password"}
          name="password"
          autoComplete="new-password"
          required
          minLength={6}
          value={password}
          onChange={(e) => {
            setPassword(e.target.value);
            if (fieldErrors.password) setFieldErrors((prev) => ({ ...prev, password: undefined }));
          }}
          trailing={
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              className="rounded-chip p-1 text-fg-subtle transition-colors duration-120 ease-out hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
            >
              <Icon icon={showPassword ? EyeOff : Eye} size="sm" />
            </button>
          }
        />
      </Field>

      <Field label="Confirm new password" required error={fieldErrors.confirmPassword}>
        <Input
          type={showPassword ? "text" : "password"}
          name="confirmPassword"
          autoComplete="new-password"
          required
          minLength={6}
          value={confirmPassword}
          onChange={(e) => {
            setConfirmPassword(e.target.value);
            if (fieldErrors.confirmPassword)
              setFieldErrors((prev) => ({ ...prev, confirmPassword: undefined }));
          }}
        />
      </Field>

      {formError && (
        <Alert tone="danger" announce="assertive">
          {formError}
        </Alert>
      )}

      <Button type="submit" size="lg" fullWidth loading={loading} trailingIcon={ArrowRight}>
        Update password
      </Button>
    </form>
  );
}
