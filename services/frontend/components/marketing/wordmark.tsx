import { cn } from "@/lib/cn";

/**
 * The GOA lockup: a forest roundel carrying a serif "G", followed by the
 * wordmark in the same display face.
 *
 * Matches the mark already used in the authenticated app's sidebar, so the
 * brand does not change identity when a user signs in — it previously did,
 * with marketing showing a bare bold "GOA" and the app showing this roundel.
 */

export interface WordmarkProps {
  tone?: "default" | "inverse";
  className?: string;
}

export function Wordmark({ tone = "default", className }: WordmarkProps) {
  const inverse = tone === "inverse";

  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <span
        aria-hidden="true"
        className={cn(
          "flex h-8 w-8 items-center justify-center rounded-full font-serif text-base font-bold",
          inverse
            ? "bg-surface text-brand-fg"
            : "bg-brand text-fg-on-brand",
        )}
      >
        G
      </span>
      <span
        className={cn(
          "font-serif text-xl font-bold tracking-tight",
          inverse ? "text-fg-inverse" : "text-fg",
        )}
      >
        goa
      </span>
    </span>
  );
}
