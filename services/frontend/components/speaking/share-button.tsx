"use client";

import { useState } from "react";
import { Check, Share2 } from "lucide-react";
import { createShareLink } from "@/lib/speaking-api";
import { useClipboard } from "@/app/hooks/useClipboard";

interface ShareButtonProps {
  sessionId: string;
}

export default function ShareButton({ sessionId }: ShareButtonProps) {
  const [loading, setLoading] = useState(false);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const { status, copy } = useClipboard();

  const handleShare = async () => {
    setLoading(true);
    setRequestError(null);

    try {
      let url = shareUrl;
      if (!url) {
        const { share_token } = await createShareLink(sessionId);
        url = `${window.location.origin}/speaking/share/${share_token}`;
        setShareUrl(url);
      }
      await copy(url);
    } catch (err) {
      setRequestError(
        err instanceof Error ? err.message : "Failed to create share link",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <button
        type="button"
        onClick={handleShare}
        disabled={loading}
        className="flex items-center gap-2 rounded-full bg-[#0d4d3a] px-4 py-2 text-xs font-semibold text-white transition hover:bg-[#09382a] disabled:cursor-not-allowed disabled:opacity-60"
      >
        {status === "copied" ? <Check size={14} /> : <Share2 size={14} />}
        {status === "copied"
          ? "Copied!"
          : loading
            ? "Generating link..."
            : "Share"}
      </button>

      {/* Announces copy success to screen readers without duplicating the visible label. */}
      <span className="sr-only" role="status" aria-live="polite">
        {status === "copied" ? "Share link copied to clipboard" : ""}
      </span>

      {status === "error" && shareUrl && (
        <div className="mt-2">
          <p className="text-xs text-gray-500">
            Couldn&apos;t copy automatically — copy the link below:
          </p>
          <input
            readOnly
            value={shareUrl}
            onFocus={(e) => e.currentTarget.select()}
            className="mt-1 w-full rounded-lg border border-gray-200/80 bg-[#fbfbfa] px-3 py-1.5 text-xs text-gray-700"
          />
        </div>
      )}

      {requestError && (
        <p role="alert" className="mt-1 text-xs text-red-600">
          {requestError}
        </p>
      )}
    </div>
  );
}
