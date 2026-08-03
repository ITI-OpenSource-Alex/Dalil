import LoginForm from "@/components/auth/LoginForm";
import Link from "next/link";

export default function LoginPage() {
  return (
    <div className="relative flex min-h-screen items-center justify-center bg-gradient-to-br from-emerald-100 via-amber-50 to-orange-100 px-4">
      {/* Logo */}
      <Link href="/" className="absolute left-6 top-6 flex items-center gap-2 text-xl font-bold text-slate-900 md:left-10 md:top-10">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-700 text-sm font-bold text-white">G</span>
        goa
      </Link>

      <div className="w-full max-w-sm">
        {/* Heading */}
        <div className="mb-6 text-center">
          <h1 className="text-3xl font-bold tracking-tight text-slate-900">Welcome back</h1>
          <p className="mt-2 text-slate-500">Pick up exactly where you left off.</p>
        </div>

        {/* Card */}
        <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
          <LoginForm />

          <p className="mt-6 text-center text-sm text-slate-500">
            New to GOA?{" "}
            <Link href="/register" className="font-medium text-emerald-700 transition hover:text-emerald-800">
              Create an account
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
