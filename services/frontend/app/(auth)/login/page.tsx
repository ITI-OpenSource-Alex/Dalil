import type { Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";
import LoginForm from "@/components/auth/LoginForm";
import { AuthCard } from "@/components/auth/auth-card";
import { Skeleton } from "@/components/ui";

export const metadata: Metadata = { title: "Sign in — GOA" };

export default function LoginPage() {
  return (
    <AuthCard title="Welcome back" subtitle="Pick up exactly where you left off.">
      {/* LoginForm reads ?redirectUrl with useSearchParams, which opts the
          subtree out of static prerendering. The boundary keeps that local to
          the form instead of making the whole route dynamic. */}
      <Suspense
        fallback={
          <div className="flex flex-col gap-5" aria-busy="true" aria-label="Loading sign-in form">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-11 w-full" />
          </div>
        }
      >
        <LoginForm />
      </Suspense>

      <p className="mt-6 text-center text-sm text-fg-muted">
        New to GOA?{" "}
        <Link href="/register" className="font-medium text-brand-fg hover:text-brand-active">
          Create an account
        </Link>
      </p>
    </AuthCard>
  );
}
