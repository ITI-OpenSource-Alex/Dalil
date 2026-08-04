import { Target, GraduationCap, FileText } from "lucide-react";

const features = [
  {
    icon: Target,
    title: "Opportunity Matching",
    description:
      "GOA scores your profile against a European catalogue of Master's programs and scholarships, ranking real matches by fit — not a keyword search.",
  },
  {
    icon: GraduationCap,
    title: "IELTS Preparation",
    description:
      "Full Reading, Listening, Writing and Speaking practice with instant AI band scoring, so you always know exactly where you stand.",
  },
  {
    icon: FileText,
    title: "CV Review",
    description:
      "Section-by-section feedback on structure, ATS keywords and country-specific conventions, tailored to the programs you're applying to.",
  },
];

export default function Features() {
  return (
    <section id="features" className="bg-white py-24">
      <div className="mx-auto max-w-7xl px-6">
        <div className="mx-auto max-w-2xl text-center">
          <span className="inline-flex items-center rounded-full border border-slate-200 bg-white px-4 py-1 text-sm text-slate-600 shadow-sm">
            Features
          </span>
          <h2 className="mt-6 text-4xl font-bold tracking-tight text-slate-900">
            Everything you need, in one place
          </h2>
          <p className="mt-4 text-lg leading-8 text-slate-600">
            From your first search to your final application, GOA replaces a
            dozen tabs and spreadsheets with one AI assistant.
          </p>
        </div>

        <div className="mt-16 grid grid-cols-1 gap-8 md:grid-cols-3">
          {features.map((feature) => (
            <div
              key={feature.title}
              className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm transition hover:shadow-md"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700">
                <feature.icon size={22} />
              </div>

              <h3 className="mt-6 text-lg font-semibold text-slate-900">
                {feature.title}
              </h3>

              <p className="mt-2 text-sm leading-6 text-slate-600">
                {feature.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
