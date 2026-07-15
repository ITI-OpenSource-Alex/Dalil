"use client";

import { ExternalLink } from "lucide-react";
import { motion } from "framer-motion";

interface Props {
  sources: string[];
}

export default function SourcesFootnote({ sources }: Props) {
  if (!sources.length) return null;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="mt-2 rounded-lg border border-[#E8ECE7] bg-[#FAFBF9] p-3"
    >
      <p className="mb-2 text-xs font-semibold text-[#526053]">Sources</p>

      <ul className="space-y-1">
        {sources.map((source, index) => (
          <li key={index}>
            <a
              href={source}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-xs text-emerald-700 hover:underline"
            >
              <ExternalLink size={12} />
              {source}
            </a>
          </li>
        ))}
      </ul>
    </motion.div>
  );
}
