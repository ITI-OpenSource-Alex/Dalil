import type { Metadata } from "next";
import Link from "next/link";
import LoginForm from "@/components/auth/LoginForm";
import { AuthCard } from "@/components/auth/auth-card";

export const metadata: Metadata = { title: "Sign in — GOA" };

export default function LoginPage() {
  return (
    <AuthCard title="Welcome back" subtitle="Pick up exactly where you left off.">
      <LoginForm />

      <p className="mt-6 text-center text-sm text-fg-muted">
        New to GOA?{" "}
        <Link href="/register" className="font-medium text-brand-fg hover:text-brand-active">
          Create an account
        </Link>
      </p>
    </AuthCard>
  );
}
