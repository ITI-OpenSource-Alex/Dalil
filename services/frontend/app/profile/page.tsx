"use client";

import Link from "next/link";
import { Sidebar } from "@/components/ui/sidebar";
import { useCurrentUser } from "@/app/hooks/useCurrentUser";
import Skeleton from "@/components/ui/skeleton";

export default function ProfilePage() {
  const { user, status, error, retry } = useCurrentUser();

  return (
    <div className="flex min-h-screen bg-[#fbfbfa] text-gray-900 font-sans">
      <Sidebar />

      <main className="flex-1 p-8 md:p-12 max-w-3xl mx-auto">
        <div className="mb-8">
          <span className="text-[10px] uppercase font-bold tracking-wider bg-emerald-50 text-[#0d4d3a] px-2.5 py-1 rounded-full border border-emerald-100">
            Your Profile
          </span>
          <h1 className="mt-2 text-2xl md:text-3xl font-serif text-gray-900">
            Account & Application Profile
          </h1>
        </div>

        {status === "loading" && (
          <div className="space-y-2" aria-busy="true" aria-label="Loading profile">
            <Skeleton />
            <Skeleton />
            <Skeleton />
          </div>
        )}

        {status === "error" && (
          <div className="rounded-2xl border border-red-100 bg-red-50 p-6 text-center">
            <p className="text-sm text-red-700">{error}</p>
            <div className="mt-3 flex items-center justify-center gap-3">
              <button
                type="button"
                onClick={retry}
                className="rounded-full bg-red-600 px-4 py-1.5 text-xs font-semibold text-white transition hover:bg-red-700"
              >
                Retry
              </button>
              <Link
                href="/login"
                className="text-xs font-semibold text-red-700 underline underline-offset-2"
              >
                Log in again
              </Link>
            </div>
          </div>
        )}

        {status === "success" && user && (
          <div className="space-y-6">
            <section className="rounded-2xl border border-gray-200/80 bg-white p-6 shadow-2xs">
              <h2 className="text-sm font-semibold text-gray-500 mb-4">Account</h2>
              <dl className="grid grid-cols-2 gap-4 text-sm">
                <Field label="Email" value={user.email} />
                <Field
                  label="Subscription"
                  value={user.subscriptionTier === "paid" ? "Paid" : "Free"}
                />
              </dl>
            </section>

            <section className="rounded-2xl border border-gray-200/80 bg-white p-6 shadow-2xs">
              <h2 className="text-sm font-semibold text-gray-500 mb-4">
                Application Profile
              </h2>
              {user.profile ? (
                <dl className="grid grid-cols-2 gap-4 text-sm">
                  <Field label="Degree level" value={user.profile.degreeLevel} />
                  <Field
                    label="GPA"
                    value={
                      user.profile.gpa !== null
                        ? `${user.profile.gpa} / ${user.profile.gpaScale}`
                        : null
                    }
                  />
                  <Field label="IELTS score" value={user.profile.ieltsScore} />
                  <Field label="Field of study" value={user.profile.fieldOfStudy} />
                  <Field label="ECTS credits" value={user.profile.ects} />
                  <Field
                    label="Work experience"
                    value={
                      user.profile.workExperienceYears !== null
                        ? `${user.profile.workExperienceYears} years`
                        : null
                    }
                  />
                  <Field
                    label="Target countries"
                    value={
                      user.profile.targetCountries.length > 0
                        ? user.profile.targetCountries.join(", ")
                        : null
                    }
                  />
                </dl>
              ) : (
                <p className="text-sm text-gray-500">
                  No application profile on file yet.
                </p>
              )}
            </section>
          </div>
        )}
      </main>
    </div>
  );
}

function Field({
  label,
  value,
}: {
  label: string;
  value: string | number | null;
}) {
  return (
    <div>
      <dt className="text-xs text-gray-400">{label}</dt>
      <dd className="mt-0.5 text-gray-900">
        {value === null || value === undefined || value === "" ? "—" : value}
      </dd>
    </div>
  );
}
