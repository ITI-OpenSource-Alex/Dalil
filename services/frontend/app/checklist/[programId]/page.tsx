"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Sidebar } from "@/components/ui/sidebar";
import ChecklistView from "@/components/checklist/ChecklistView";

export default function ChecklistPage() {
  const params = useParams<{ programId: string }>();
  const programId = params.programId;

  return (
    <div className="flex min-h-screen bg-[#fbfbfa] text-gray-900 font-sans">
      <div className="print-hidden">
        <Sidebar />
      </div>

      <main className="flex-1 p-8 md:p-12 max-w-3xl mx-auto">
        <Link
          href="/chat"
          className="print-hidden mb-6 inline-block text-xs font-semibold text-[#0d4d3a] hover:underline"
        >
          &larr; Back to Chat
        </Link>

        <div className="mb-6">
          <span className="text-[10px] uppercase font-bold tracking-wider bg-emerald-50 text-[#0d4d3a] px-2.5 py-1 rounded-full border border-emerald-100">
            Application Checklist
          </span>
          <h1 className="mt-2 text-2xl md:text-3xl font-serif text-gray-900">
            Your Step-by-Step Guide
          </h1>
        </div>

        <ChecklistView programId={programId} />
      </main>
    </div>
  );
}
