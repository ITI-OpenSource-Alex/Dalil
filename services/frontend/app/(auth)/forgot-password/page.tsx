import type { Metadata } from "next";
import ForgotPasswordForm from "@/components/auth/ForgotPasswordForm";
import { AuthCard } from "@/components/auth/auth-card";

export const metadata: Metadata = { title: "Forgot password — GOA" };

export default function ForgotPasswordPage() {
  return (
    <AuthCard
      title="Forgot your password?"
      subtitle="Enter your email and we'll send you a reset link."
    >
      <ForgotPasswordForm />
    </AuthCard>
  );
}
