import HeroButtons from "./HeroButtons";
import HeroStats from "./HeroStats";

export default function HeroContent() {
  return (
    <div>
      <span className="inline-flex items-center rounded-full border border-slate-200 bg-white px-4 py-1 text-sm text-slate-600 shadow-sm">✨ The AI Study Abroad Platform</span>

      <h1 className="mt-8 text-5xl font-bold leading-tight tracking-tight text-slate-900 lg:text-7xl">
        Study Abroad
        <br />
        <span className="bg-gradient-to-r from-emerald-700 via-emerald-500 to-amber-500 bg-clip-text text-transparent">Smarter with AI</span>
      </h1>

      <p className="mt-8 max-w-xl text-lg leading-8 text-slate-600">
        Discover scholarships, find your perfect university, prepare for IELTS, review your CV, and manage your entire application journey using one AI assistant.
      </p>

      <HeroButtons />

      <HeroStats />
    </div>
  );
}
