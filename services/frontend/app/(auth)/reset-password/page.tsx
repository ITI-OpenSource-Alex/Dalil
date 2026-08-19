import type { Metadata } from "next";
import ResetPasswordForm from "@/components/auth/ResetPasswordForm";
import { AuthCard } from "@/components/auth/auth-card";

export const metadata: Metadata = { title: "Reset password — Dalil" };

export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;

  return (
    <AuthCard title="Set a new password" subtitle="Choose a new password for your account.">
      <ResetPasswordForm token={token ?? null} />
    </AuthCard>
  );
}
