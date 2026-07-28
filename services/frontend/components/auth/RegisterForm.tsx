"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";

// POST /users only takes {email, password} (services/user/src/users/dto/
// create-user.dto.ts) and does not log the caller in -- registering and
// authenticating are two separate calls, so this redirects to /login on
// success rather than assuming a session exists afterward.
export default function RegisterForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      await api.post("/users", { email, password });
      router.push("/login");
    } catch (err) {
      const message =
        (axiosMessage(err) as string | undefined) ??
        "Could not create an account. Please try again.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5">
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="register-email"
          className="text-sm font-medium text-slate-700"
        >
          Email
        </label>
        <input
          id="register-email"
          type="email"
          placeholder="you@university.edu"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="rounded-xl border border-slate-200 px-4 py-3 text-sm text-slate-900 placeholder-slate-400 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-100"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="register-password"
          className="text-sm font-medium text-slate-700"
        >
          Password
        </label>
        <input
          id="register-password"
          type="password"
          placeholder="At least 6 characters"
          required
          minLength={6}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="rounded-xl border border-slate-200 px-4 py-3 text-sm text-slate-900 placeholder-slate-400 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-100"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="register-confirm-password"
          className="text-sm font-medium text-slate-700"
        >
          Confirm password
        </label>
        <input
          id="register-confirm-password"
          type="password"
          placeholder="Re-enter your password"
          required
          minLength={6}
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          className="rounded-xl border border-slate-200 px-4 py-3 text-sm text-slate-900 placeholder-slate-400 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-100"
        />
      </div>

      {error && (
        <p className="rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-600">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={loading}
        id="register-submit-btn"
        className="mt-1 inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-700 px-6 py-3.5 text-sm font-semibold text-white transition hover:bg-emerald-800 disabled:opacity-60"
      >
        {loading ? "Creating account…" : "Create account"}
        {!loading && <ArrowRight size={16} />}
      </button>

      <p className="text-center text-sm text-slate-500">
        Already have an account?{" "}
        <Link
          href="/login"
          className="font-medium text-emerald-700 transition hover:text-emerald-800"
        >
          Sign in
        </Link>
      </p>
    </form>
  );
}

function axiosMessage(err: unknown): string | undefined {
  if (
    typeof err === "object" &&
    err !== null &&
    "response" in err &&
    typeof (err as { response?: unknown }).response === "object"
  ) {
    const data = (err as { response?: { data?: unknown } }).response?.data;
    if (
      typeof data === "object" &&
      data !== null &&
      "message" in data &&
      typeof (data as { message?: unknown }).message === "string"
    ) {
      return (data as { message: string }).message;
    }
  }
  return undefined;
}
