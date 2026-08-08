"use client";

import Link from "next/link";
import { ArrowRight, Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { authApi, apiErrorMessage } from "@/lib/api";
import { getMyProfile } from "@/lib/profile-api";
import { isProfileComplete } from "@/app/types/profile";
import { Alert, Button, Field, Icon, Input } from "@/components/ui";

/**
 * Where to go after a successful sign-in, when middleware.ts bounced the user
 * here from a protected route.
 *
 * Rejects anything that is not a path-absolute, same-origin destination. The
 * value comes from the query string, so `//evil.example` — which the URL parser
 * happily treats as a host — would otherwise turn the login page into an open
 * redirect, the most convincing kind of phishing hop because the victim really
 * did start on this domain. The same check lives in middleware.ts for the
 * already-signed-in case; both sides have to hold it.
 */
export function safeRedirectTarget(raw: string | null): string | null {
  if (!raw) return null;
  if (!raw.startsWith("/")) return null;
  if (raw.startsWith("//") || raw.startsWith("/\\")) return null;
  return raw;
}

export default function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectTo = safeRedirectTarget(searchParams.get("redirectUrl"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await authApi.login(email, password);
      // New accounts (and any account that never finished the wizard) have
      // a profile row with every field still null (registration creates it
      // upfront, see isProfileComplete's doc comment) -- send them to
      // onboarding instead of dropping them into chat with an empty
      // profile. If the profile check itself fails, fail open to /chat
      // rather than blocking a successful login.
      try {
        const me = await getMyProfile();
        // A destination the user actually asked for wins over both defaults --
        // being bounced to /chat after signing in to reach /opportunities is
        // the whole reason middleware.ts passes redirectUrl along. Onboarding
        // still wins for an unfinished profile: sending someone to a matching
        // page with nothing to match on is a worse landing than the wizard.
        const destination = isProfileComplete(me.profile)
          ? (redirectTo ?? "/chat")
          : "/onboarding";
        router.push(destination);
      } catch {
        router.push(redirectTo ?? "/chat");
      }
    } catch (err) {
      // Surfaces the backend's own message where it has one (e.g. an
      // unverified account) rather than always showing the same generic
      // string regardless of cause.
      setError(apiErrorMessage(err) ?? "Invalid email or password. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5">
      <Field label="Email" required id="login-email">
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

      <Field
        id="login-password"
        label={
          <span className="flex items-center justify-between gap-3">
            Password
            <Link
              href="/forgot-password"
              className="text-sm font-medium text-fg-subtle hover:text-brand-fg"
            >
              Forgot password?
            </Link>
          </span>
        }
        required
      >
        <Input
          type={showPassword ? "text" : "password"}
          name="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
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

      {error && (
        <Alert tone="danger" announce="assertive">
          {error}
        </Alert>
      )}

      <Button
        type="submit"
        id="login-submit-btn"
        size="lg"
        fullWidth
        loading={loading}
        trailingIcon={ArrowRight}
      >
        Sign in
      </Button>
    </form>
  );
}
