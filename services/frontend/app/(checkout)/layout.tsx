import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { Icon, Text } from "@/components/ui";
import { Wordmark } from "@/components/marketing/wordmark";

/* ------------------------------------------------------------------ *
 * Shell for the checkout (GOA-039).
 *
 * A route group, so it changes nothing about the URL -- /billing/demo-checkout
 * is unaffected, and middleware.ts still protects the /billing prefix exactly
 * as before. What it changes is the chrome: the (app) layout renders the full
 * sidebar, which puts nine navigation targets next to a payment form and
 * quietly invites the user to wander off mid-transaction. Checkout is the one
 * place in the product where the right number of exits is one.
 *
 * So: the brand, a single way back, and nothing else. Same language as the
 * (auth) shell, which makes the same argument for the same reason.
 *
 * Server Component -- no client JS is spent on chrome that never changes.
 * ------------------------------------------------------------------ */

export default function CheckoutLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-canvas-subtle">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-5 py-4 sm:px-8">
          <Link href="/" className="inline-flex rounded-chip">
            <Wordmark className="h-7" />
            <span className="sr-only">Dalil home</span>
          </Link>

          {/* Chrome-level navigation back to the plans. The explicit *cancel*
              action lives beside the pay button, where it carries
              ?checkout=cancelled and earns the "you have not been charged"
              reassurance -- this link makes no claim about the payment. */}
          <Link
            href="/pricing"
            className="inline-flex items-center gap-1.5 rounded-chip text-sm font-medium text-fg-muted transition-colors hover:text-fg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            <Icon icon={ArrowLeft} size="xs" />
            Back to pricing
          </Link>
        </div>
      </header>

      <main id="main-content" className="flex-1">
        {children}
      </main>

      <footer className="border-t border-border px-5 py-6 sm:px-8">
        <Text size="sm" tone="subtle" className="mx-auto max-w-5xl text-center">
          © {new Date().getFullYear()} Dalil · Billing for this project is
          simulated for demonstration purposes.
        </Text>
      </footer>
    </div>
  );
}
