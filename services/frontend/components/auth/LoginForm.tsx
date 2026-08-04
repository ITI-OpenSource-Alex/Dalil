"use client";

import Link from "next/link";
import { ArrowRight, Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { authApi, apiErrorMessage } from "@/lib/api";
import { Alert, Button, Field, Icon, Input } from "@/components/ui";

export default function LoginForm() {
  const router = useRouter();
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
      router.push("/chat");
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
