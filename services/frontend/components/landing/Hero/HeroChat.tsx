import { opportunities } from "./opportunities";

export default function HeroChat() {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-xl">
      <div className="flex items-center justify-between border-b border-slate-200 pb-4">
        <span className="font-semibold text-slate-900">GOA Assistant</span>

        <span className="text-sm text-slate-500">/chat</span>
      </div>

      <div className="mt-6 flex justify-end">
        <div className="max-w-xs rounded-2xl rounded-tr-md bg-emerald-700 px-5 py-3 text-white">Find AI Master's programs in Germany.</div>
      </div>

      <div className="mt-6 rounded-2xl border border-slate-200 p-5">
        <p className="text-sm text-slate-700">I found the best opportunities based on your profile.</p>

        <div className="mt-5 space-y-3">
          {opportunities.map((item) => (
            <div key={item.university} className="flex items-center justify-between rounded-xl border border-slate-200 p-4">
              <div className="flex items-center gap-3">
                <span className="text-xl">{item.country}</span>

                <div>
                  <h4 className="font-semibold text-slate-900">{item.university}</h4>

                  <p className="text-sm text-slate-500">{item.program}</p>
                </div>
              </div>

              <span className="rounded-full bg-emerald-100 px-3 py-1 text-sm font-medium text-emerald-700">{item.match}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-5 rounded-xl border border-slate-200 px-4 py-3 text-sm text-slate-500">Ask GOA anything...</div>
    </div>
  );
}
