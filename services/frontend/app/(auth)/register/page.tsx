import type { Metadata } from "next";
import RegisterForm from "@/components/auth/RegisterForm";
import { AuthCard } from "@/components/auth/auth-card";

export const metadata: Metadata = { title: "Create your account — Dalil" };

export default function RegisterPage() {
  return (
    <AuthCard
      title="Create your account"
      subtitle="Start closing the gap to your target band."
    >
      <RegisterForm />
    </AuthCard>
  );
}
