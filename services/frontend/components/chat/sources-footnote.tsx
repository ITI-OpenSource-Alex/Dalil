"use client";

import { ExternalLink } from "lucide-react";
import { motion } from "framer-motion";

interface Props {
  sources: string[];
}

/**
 * Hosts that are ours, not the user's.
 *
 * RAG seeds its catalogue with `https://goa.internal/seed/...` source URLs
 * (app/migrations/029_seed_demo_programs.sql) and relays whatever `sources`
 * the answer carried. Rendering those verbatim showed the reader an internal
 * hostname and a seed path, as a link they could click and that would never
 * resolve. Anything on an internal host is dropped entirely rather than shown
 * unlinked: a citation nobody can check is not a citation.
 */
const INTERNAL_HOST_PATTERN = /(^|\.)(goa\.internal|localhost|internal)$/i;

interface DisplaySource {
  href: string;
  label: string;
}

/**
 * Keeps only sources that are real, fetchable, external URLs, and labels each
 * by its host rather than its full path -- a 180-character URL wrapped across
 * four lines is noise, and the host is what tells a reader whether to trust it.
 */
export function presentableSources(sources: string[]): DisplaySource[] {
  const seen = new Set<string>();
  const result: DisplaySource[] = [];

  for (const source of sources) {
    if (typeof source !== "string" || !source.trim()) continue;

    let url: URL;
    try {
      url = new URL(source.trim());
    } catch {
      // Not a URL at all -- a document id, a chunk reference, a file path.
      // These are retrieval internals and are never shown.
      continue;
    }

    if (url.protocol !== "http:" && url.protocol !== "https:") continue;
    if (INTERNAL_HOST_PATTERN.test(url.hostname)) continue;

    const label = url.hostname.replace(/^www\./, "");
    const key = url.href;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push({ href: url.href, label });
  }

  return result;
}

export default function SourcesFootnote({ sources }: Props) {
  const visible = presentableSources(sources);
  if (!visible.length) return null;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="mt-2 rounded-lg border border-[#E8ECE7] bg-[#FAFBF9] p-3"
    >
      <p className="mb-2 text-xs font-semibold text-[#526053]">Sources</p>

      <ul className="flex flex-wrap gap-x-3 gap-y-1">
        {visible.map((source) => (
          <li key={source.href}>
            <a
              href={source.href}
              target="_blank"
              rel="noopener noreferrer"
              title={source.href}
              className="flex items-center gap-1.5 text-xs text-emerald-700 hover:underline"
            >
              <ExternalLink size={12} />
              {source.label}
            </a>
          </li>
        ))}
      </ul>
    </motion.div>
  );
}
