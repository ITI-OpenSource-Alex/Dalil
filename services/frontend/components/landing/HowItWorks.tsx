const steps = [
  {
    number: "1",
    title: "Create your profile",
    description:
      "Tell GOA your GPA, IELTS score and target countries — or let it pull your background straight from your CV.",
  },
  {
    number: "2",
    title: "Get matched instantly",
    description:
      "See ranked Master's programs and scholarships, each with a real, computed confidence score.",
  },
  {
    number: "3",
    title: "Generate your checklist",
    description:
      "One click turns a matched program into a personalised, phase-by-phase application checklist.",
  },
  {
    number: "4",
    title: "Practise for IELTS",
    description:
      "Sit full Reading, Listening, Writing and Speaking simulations with instant AI band scoring.",
  },
];

export default function HowItWorks() {
  return (
    <section id="how-it-works" className="bg-slate-50 py-24">
      <div className="mx-auto max-w-7xl px-6">
        <div className="mx-auto max-w-2xl text-center">
          <span className="inline-flex items-center rounded-full border border-slate-200 bg-white px-4 py-1 text-sm text-slate-600 shadow-sm">
            How it works
          </span>
          <h2 className="mt-6 text-4xl font-bold tracking-tight text-slate-900">
            From first search to final application
          </h2>
        </div>

        <div className="relative mt-16 grid grid-cols-1 gap-12 md:grid-cols-4 md:gap-8">
          {/* Connecting rule between step circles, desktop only. */}
          <div
            aria-hidden="true"
            className="absolute top-6 left-0 right-0 hidden h-px bg-slate-200 md:block"
            style={{ marginInline: "12.5%" }}
          />

          {steps.map((step) => (
            <div key={step.number} className="relative text-center">
              <div className="relative z-10 mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-700 text-lg font-semibold text-white">
                {step.number}
              </div>

              <h3 className="mt-5 text-base font-semibold text-slate-900">
                {step.title}
              </h3>

              <p className="mt-2 text-sm leading-6 text-slate-600">
                {step.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
