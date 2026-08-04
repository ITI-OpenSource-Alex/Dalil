import type { Metadata } from "next";
import VerifyEmailStatus from "@/components/auth/VerifyEmailStatus";
import { AuthCard } from "@/components/auth/auth-card";

export const metadata: Metadata = { title: "Verify your email — GOA" };

export default async function VerifyEmailPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;

  return (
    <AuthCard title="Verify your email">
      <VerifyEmailStatus token={token} />
    </AuthCard>
  );
}
