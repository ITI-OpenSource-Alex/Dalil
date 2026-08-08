import Link from "next/link";
import { Check } from "lucide-react";
import { Icon, Text } from "@/components/ui";
import { Wordmark } from "@/components/marketing/wordmark";

/* ------------------------------------------------------------------ *
 * Shared shell for Register / Login / Forgot Password / Reset Password /
 * Verify Email. A route group ("(auth)") so it changes nothing about the
 * URLs -- /login, /register etc. are unaffected -- while replacing three
 * (soon five) independently copy-pasted gradient-card pages with one layout.
 *
 * Split screen on lg+: a brand panel carrying the same dark-forest language
 * as the landing page's CTA and footer, and the form itself on a plain
 * canvas. Below lg the panel collapses to a compact top band so the form is
 * reached without scrolling on a phone.
 *
 * Server Component: no client JS is spent on chrome that never changes.
 * ------------------------------------------------------------------ */

const REASSURANCE = [
  "Matches you against programmes you can actually get into",
  "Turns every match into a step-by-step application checklist",
  "Trains all four IELTS skills with instant, specific feedback",
];

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      {/* Brand panel */}
      <div className="relative isolate flex shrink-0 flex-col justify-between overflow-hidden bg-forest-950 px-6 py-10 sm:px-10 lg:w-[42%] lg:px-12 lg:py-14">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 -z-10 bg-grid opacity-[0.07] [mask-image:radial-gradient(ellipse_80%_60%_at_20%_0%,black,transparent)]"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-24 -left-24 -z-10 h-[26rem] w-[26rem] rounded-full bg-brand/20 blur-3xl"
        />

        <Link href="/" className="inline-block rounded-chip">
          <Wordmark tone="inverse" />
          <span className="sr-only">home</span>
        </Link>

        {/* Hidden below lg: the panel is a compact band there, not the full
            pitch -- there is no room for it above the fold on a phone. */}
        <div className="hidden lg:block">
          <Text
            as="p"
            size="lg"
            tone="inverse"
            className="max-w-sm font-serif text-2xl leading-snug"
          >
            The AI study abroad platform, from first match to your visa
            checklist.
          </Text>

          <ul className="mt-8 flex flex-col gap-3">
            {REASSURANCE.map((item) => (
              <li key={item} className="flex items-start gap-2.5">
                <Icon icon={Check} size="xs" className="mt-1 shrink-0 text-accent" />
                <Text as="span" size="sm" tone="inverse-muted">
                  {item}
                </Text>
              </li>
            ))}
          </ul>
        </div>

        <p className="hidden text-sm text-forest-200/60 lg:block">
          © {new Date().getFullYear()} Dalil. Not affiliated with the IELTS
          test owners.
        </p>
      </div>

      {/* Form column */}
      <div className="flex flex-1 items-center justify-center bg-canvas px-6 py-12 sm:px-10">
        <div className="w-full max-w-sm">{children}</div>
      </div>
    </div>
  );
}
