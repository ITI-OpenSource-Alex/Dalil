import Link from "next/link";
import { Check, ArrowRight } from "lucide-react";

const freeFeatures = [
  "AI opportunity matching & confidence scoring",
  "Personalised application checklists",
  "Unlimited chat Q&A with GOA",
];

const paidFeatures = [
  "Everything in Free",
  "Full IELTS exam simulations (all 4 skills)",
  "Speaking practice with live feedback",
  "Writing evaluation & AI band scoring",
  "CV review & rewrite suggestions",
];

export default function Pricing() {
  return (
    <section id="pricing" className="bg-white py-24">
      <div className="mx-auto max-w-7xl px-6">
        <div className="mx-auto max-w-2xl text-center">
          <span className="inline-flex items-center rounded-full border border-slate-200 bg-white px-4 py-1 text-sm text-slate-600 shadow-sm">
            Pricing
          </span>
          <h2 className="mt-6 text-4xl font-bold tracking-tight text-slate-900">
            Start free. Upgrade when you're ready.
          </h2>
          <p className="mt-4 text-lg leading-8 text-slate-600">
            Opportunity matching and application checklists are free,
            forever — no card required.
          </p>
        </div>

        <div className="mx-auto mt-16 grid max-w-4xl grid-cols-1 gap-8 md:grid-cols-2">
          {/* Free */}
          <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
            <h3 className="text-lg font-semibold text-slate-900">Free</h3>
            <p className="mt-1 text-sm text-slate-500">
              Everything you need to find and apply.
            </p>

            <p className="mt-6 text-4xl font-bold text-slate-900">$0</p>

            <ul className="mt-8 space-y-4">
              {freeFeatures.map((feature) => (
                <li key={feature} className="flex items-start gap-3">
                  <Check
                    size={18}
                    className="mt-0.5 shrink-0 text-emerald-600"
                  />
                  <span className="text-sm text-slate-600">{feature}</span>
                </li>
              ))}
            </ul>

            <Link
              href="/register"
              className="mt-8 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-6 py-3 font-medium text-slate-800 transition hover:bg-slate-50"
            >
              Get Started Free
            </Link>
          </div>

          {/* Paid */}
          <div className="rounded-2xl border-2 border-emerald-700 bg-white p-8 shadow-sm">
            <span className="inline-flex items-center rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
              Most popular
            </span>

            <h3 className="mt-3 text-lg font-semibold text-slate-900">
              GOA Pro
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              Full IELTS prep and AI feedback across every skill.
            </p>

            <p className="mt-6 text-4xl font-bold text-slate-900">
              $7
              <span className="text-base font-medium text-slate-500">
                /month
              </span>
            </p>

            <ul className="mt-8 space-y-4">
              {paidFeatures.map((feature) => (
                <li key={feature} className="flex items-start gap-3">
                  <Check
                    size={18}
                    className="mt-0.5 shrink-0 text-emerald-600"
                  />
                  <span className="text-sm text-slate-600">{feature}</span>
                </li>
              ))}
            </ul>

            <Link
              href="/register"
              className="mt-8 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-700 px-6 py-3 font-medium text-white transition hover:bg-emerald-800"
            >
              Upgrade for $7/month
              <ArrowRight size={16} />
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
