"use client";

export default function PrintButton() {
  return (
    <button
      type="button"
      onClick={() => window.print()}
      className="print-hidden inline-flex items-center gap-2 rounded-full bg-[#0d4d3a] px-4 py-2 text-xs font-semibold text-white transition hover:bg-[#09382a]"
    >
      Export as PDF
    </button>
  );
}
