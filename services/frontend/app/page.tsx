import { cookies } from "next/headers";
import { Navbar } from "@/components/marketing/navbar";
import { Hero } from "@/components/marketing/hero";
import { TrustBar } from "@/components/marketing/trust-bar";
import { Features } from "@/components/marketing/features";
import { HowItWorks } from "@/components/marketing/how-it-works";
import { Proof } from "@/components/marketing/proof";
import { Pricing } from "@/components/marketing/pricing";
import { FAQ } from "@/components/marketing/faq";
import { CTA } from "@/components/marketing/cta";
import { Footer } from "@/components/marketing/footer";

/**
 * The landing page reads as one argument, top to bottom:
 *
 *   Hero        hook, and the product doing its job
 *   TrustBar    quiet credibility — where this works
 *   Features    what it does                        (subtle)
 *   HowItWorks  how it does it, step by step        (canvas)
 *   Proof       why it matters                      (DARK — midpoint anchor)
 *   Pricing     what it costs                       (subtle)
 *   FAQ         the objections                      (canvas)
 *   CTA         the ask                             (DARK)
 *   Footer                                          (DARKER)
 *
 * The two dark sections are the page's anchors. Everything between them
 * alternates canvas/subtle, so the rhythm is a property of the page rather
 * than of nine independently-styled bands.
 *
 * Every section is a Server Component. The only client islands are the
 * navbar (mobile menu + scroll state), Reveal, and StatCounter.
 */
export default async function HomePage() {
  // Read on the server, not in the browser. access_token is HttpOnly (the
  // Gateway sets it that way deliberately), so client JS cannot see it — a
  // client-side check would have to call the API and would flash "Sign in" at
  // every signed-in visitor before correcting itself. Reading the cookie here
  // opts this route out of static prerendering; the page still renders entirely
  // on the server, and the alternative is a wrong CTA on first paint.
  const signedIn = (await cookies()).has("access_token");

  return (
    <>
      {/* Scroll reveals ship their hidden state in the HTML so there is no
          flash of unrevealed content. If JS never runs, this restores every
          section to visible rather than leaving the page blank. */}
      <noscript>
        <style>{`[data-reveal]{opacity:1 !important;transform:none !important}`}</style>
      </noscript>

      <Navbar signedIn={signedIn} />

      <main id="main-content">
        <Hero />
        <TrustBar />
        <Features />
        <HowItWorks />
        <Proof />
        {/* Same cookie read as the Navbar above: a visitor who already has an
            account is sent to /pricing, which knows their tier, rather than to
            a registration form. */}
        <Pricing signedIn={signedIn} />
        <FAQ />
        <CTA />
      </main>

      <Footer />
    </>
  );
}
