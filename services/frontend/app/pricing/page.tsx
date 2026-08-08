import type { Metadata } from "next";
import { cookies } from "next/headers";
import { Navbar } from "@/components/marketing/navbar";
import { Footer } from "@/components/marketing/footer";
import { FAQ } from "@/components/marketing/faq";
import { PricingPlans } from "@/components/pricing/plan-grid";

/**
 * /pricing — GOA-039.
 *
 * A top-level route, deliberately outside the (app) group: a signed-out
 * visitor must be able to read it, and the authenticated shell (sidebar,
 * UpgradeProvider) would be wrong chrome for them. middleware.ts does not
 * list it, so it stays public.
 *
 * Server-rendered like the landing page, including the same server-side
 * cookie read: `access_token` is HttpOnly, so a client-side session check
 * would have to call the API and would flash the wrong CTA at every
 * signed-in visitor first. Only the plan grid hydrates.
 *
 * This is also where every upgrade CTA in the product now points
 * (DEFAULT_UPGRADE_URL in lib/subscription.ts).
 */
export const metadata: Metadata = {
  title: "Pricing — Dalil",
  description:
    "Programme matching, checklists and chat are free forever. Dalil Pro adds full IELTS exam simulations, AI band scoring, speaking practice and CV review.",
};

export default async function PricingPage() {
  const signedIn = (await cookies()).has("access_token");

  return (
    <>
      {/* FAQ uses Reveal, which ships its hidden state in the HTML. Without
          this override the section stays invisible when JS never runs —
          same reasoning, and same fix, as app/page.tsx. */}
      <noscript>
        <style>{`[data-reveal]{opacity:1 !important;transform:none !important}`}</style>
      </noscript>

      <Navbar signedIn={signedIn} />

      <main id="main-content">
        <PricingPlans signedIn={signedIn} />
        <FAQ />
      </main>

      <Footer />
    </>
  );
}
