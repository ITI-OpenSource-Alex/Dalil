"use client";

export default function PrintButton() {
  return (
    <button
      type="button"
      onClick={() => window.print()}
      className="print-hidden inline-flex items-center gap-2 rounded-full bg-brand px-4 py-2 text-xs font-semibold text-fg-on-brand transition hover:bg-brand-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-muted"
    >
      Export as PDF
    </button>
  );
}
