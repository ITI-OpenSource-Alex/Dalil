import ResetPasswordForm from "@/components/auth/ResetPasswordForm";
import Link from "next/link";

export default function ResetPasswordPage() {
  return (
    <div className="relative flex min-h-screen items-center justify-center bg-gradient-to-br from-emerald-100 via-amber-50 to-orange-100 px-4">
      {/* Logo */}
      <Link
        href="/"
        className="absolute left-6 top-6 flex items-center gap-2 text-xl font-bold text-slate-900 md:left-10 md:top-10"
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-700 text-sm font-bold text-white">
          G
        </span>
        goa
      </Link>

      <div className="w-full max-w-sm">
        {/* Heading */}
        <div className="mb-6 text-center">
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">
            Reset your password
          </h1>
          <p className="mt-2 text-slate-500">
            Enter your email and we&apos;ll send you a reset link.
          </p>
        </div>

        {/* Card */}
        <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
          <ResetPasswordForm />
        </div>
      </div>
    </div>
  );
}
