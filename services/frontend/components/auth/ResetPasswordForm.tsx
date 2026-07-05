"use client";

import Link from "next/link";
import { ArrowLeft, ArrowRight, CheckCircle } from "lucide-react";
import { useState } from "react";
import api from "@/lib/api";

export default function ResetPasswordForm() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      await api.post("/auth/reset-password", { email });
      setSent(true);
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  if (sent) {
    return (
      <div className="flex flex-col items-center gap-4 py-4 text-center">
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-emerald-100">
          <CheckCircle className="h-7 w-7 text-emerald-700" />
        </div>
        <h2 className="text-lg font-semibold text-slate-900">Check your inbox</h2>
        <p className="text-sm leading-6 text-slate-500">
          We&apos;ve sent a password reset link to{" "}
          <span className="font-medium text-slate-700">{email}</span>. It may
          take a minute to arrive.
        </p>
        <Link
          href="/login"
          className="mt-2 inline-flex items-center gap-2 text-sm font-medium text-emerald-700 transition hover:text-emerald-800"
        >
          <ArrowLeft size={14} />
          Back to sign in
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5">
      {/* Email */}
      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="reset-email"
          className="text-sm font-medium text-slate-700"
        >
          Email
        </label>
        <input
          id="reset-email"
          type="email"
          placeholder="you@university.edu"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="rounded-xl border border-slate-200 px-4 py-3 text-sm text-slate-900 placeholder-slate-400 outline-none transition focus:border-emerald-600 focus:ring-2 focus:ring-emerald-100"
        />
      </div>

      {/* Error */}
      {error && (
        <p className="rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-600">
          {error}
        </p>
      )}

      {/* Submit */}
      <button
        type="submit"
        disabled={loading}
        id="reset-submit-btn"
        className="mt-1 inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-700 px-6 py-3.5 text-sm font-semibold text-white transition hover:bg-emerald-800 disabled:opacity-60"
      >
        {loading ? "Sending…" : "Send reset link"}
        {!loading && <ArrowRight size={16} />}
      </button>

      <Link
        href="/login"
        className="inline-flex items-center justify-center gap-2 text-sm text-slate-500 transition hover:text-slate-700"
      >
        <ArrowLeft size={14} />
        Back to sign in
      </Link>
    </form>
  );
}
