"use client";

import Link from "next/link";
import { ArrowRight, CheckCircle2, Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { authApi, apiErrorMessage } from "@/lib/api";
import { Alert, Button, Field, Icon, Input } from "@/components/ui";

// POST /users only takes {email, password} (services/user/src/users/dto/
// create-user.dto.ts) and does not log the caller in -- registering and
// authenticating are two separate calls, so this redirects to /login on
// success rather than assuming a session exists afterward. Registration also
// triggers a verification email server-side (users.service.ts).
export default function RegisterForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<{ password?: string; confirmPassword?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

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
      await authApi.register(email, password);
      setDone(true);
      setTimeout(() => router.push("/login"), 1400);
    } catch (err) {
      setFormError(apiErrorMessage(err) ?? "Could not create an account. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  if (done) {
    return (
      <div className="flex flex-col items-center gap-3 py-4 text-center" role="status">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-success-subtle text-success">
          <Icon icon={CheckCircle2} size="lg" />
        </span>
        <p className="text-base font-semibold text-fg">Account created</p>
        <p className="text-sm leading-6 text-fg-muted">
          Taking you to sign in&hellip;
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-5">
      <Field label="Email" required id="register-email">
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
        label="Password"
        required
        hint="At least 6 characters."
        error={fieldErrors.password}
        id="register-password"
      >
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
              className="pointer-events-auto rounded-chip p-1 text-fg-subtle transition-colors duration-120 ease-out hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
            >
              <Icon icon={showPassword ? EyeOff : Eye} size="sm" />
            </button>
          }
        />
      </Field>

      <Field
        label="Confirm password"
        required
        error={fieldErrors.confirmPassword}
        id="register-confirm-password"
      >
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

      <Button
        type="submit"
        id="register-submit-btn"
        size="lg"
        fullWidth
        loading={loading}
        trailingIcon={ArrowRight}
      >
        Create account
      </Button>

      <p className="text-center text-sm text-fg-muted">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-brand-fg hover:text-brand-active">
          Sign in
        </Link>
      </p>
    </form>
  );
}
