import Link from "next/link";
import { Menu, ArrowRight } from "lucide-react";

export default function Navbar() {
  return (
    <header className="sticky top-0 z-50 border-b border-slate-200/80 bg-white/80 backdrop-blur-md">
      <div className="mx-auto flex h-20 max-w-7xl items-center justify-between px-6">
        {/* Logo */}
        <Link
          href="/"
          className="text-3xl font-bold tracking-tight text-slate-900"
        >
          GOA
        </Link>

        {/* Desktop Navigation */}
        <nav className="hidden items-center gap-10 lg:flex">
          <Link
            href="#how-it-works"
            className="text-sm font-medium text-slate-600 transition hover:text-slate-900"
          >
            How it works
          </Link>

          <Link
            href="#features"
            className="text-sm font-medium text-slate-600 transition hover:text-slate-900"
          >
            Features
          </Link>

          <Link
            href="#pricing"
            className="text-sm font-medium text-slate-600 transition hover:text-slate-900"
          >
            Pricing
          </Link>
        </nav>

        {/* Desktop Actions */}
        <div className="hidden items-center gap-4 lg:flex">
          <Link
            href="/login"
            className="text-sm font-medium text-slate-700 transition hover:text-slate-900"
          >
            Sign In
          </Link>

          <Link
            href="/onboarding"
            className="inline-flex items-center gap-2 rounded-xl bg-emerald-700 px-5 py-3 text-sm font-medium text-white transition hover:bg-emerald-800"
          >
            Get Started
            <ArrowRight size={16} />
          </Link>
        </div>

        {/* Mobile Menu */}
        <button className="rounded-lg p-2 transition hover:bg-slate-100 lg:hidden">
          <Menu size={24} />
        </button>
      </div>
    </header>
  );
}
