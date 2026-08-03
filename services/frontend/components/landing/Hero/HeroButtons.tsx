import Link from "next/link";
import { ArrowRight } from "lucide-react";

export default function HeroButtons() {
  return (
    <div className="mt-10 flex flex-wrap gap-4">
      <Link
        href="/onboarding"
        className="inline-flex items-center gap-2 rounded-xl bg-emerald-700 px-6 py-3 font-medium text-white transition hover:bg-emerald-800"
      >
        Get Started
        <ArrowRight size={18} />
      </Link>

      <Link
        href="#features"
        className="rounded-xl border border-slate-300 bg-white px-6 py-3 font-medium text-slate-800 transition hover:bg-slate-50"
      >
        Learn More
      </Link>
    </div>
  );
}
