"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface LockedAudioPlayerProps {
  /** URL of the audio file to play */
  src: string;
  /** Called once when the audio finishes playing (one pass per section) */
  onComplete?: () => void;
  /** Optional className applied to the outer wrapper */
  className?: string;
  /**
   * When true, playback is attempted automatically once on mount (e.g. when
   * a new section becomes active after the silence gap). Browsers may block
   * unattended autoplay; in that case the candidate falls back to the
   * visible Play/Pause button. This only fires once per mount — pair it
   * with a `key` on this component (e.g. keyed by section number) so a new
   * section gets a fresh mount, a fresh autoplay attempt, and a fully reset
   * lock watermark.
   */
  autoPlay?: boolean;
}

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

/**
 * An audio player that only allows forward playback.
 *
 * - No native controls, no seekable progress bar.
 * - Users can only Play/Pause; they cannot scrub, rewind, or fast-forward
 *   via mouse, keyboard, or devtools/programmatic access to `currentTime`.
 * - Once playback completes, the section is locked (no replay), matching
 *   a one-pass listening exam flow.
 */
export default function LockedAudioPlayer({
  src,
  onComplete,
  className,
  autoPlay = false,
}: LockedAudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // The furthest point the user has legitimately reached. Playback is
  // never allowed to jump ahead of or behind this value except by the
  // natural forward progression of `timeupdate`.
  const allowedTimeRef = useRef(0);
  // Guards against feedback loops when we programmatically reset
  // currentTime inside the seeking/timeupdate handlers.
  const isCorrectingRef = useRef(false);

  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isComplete, setIsComplete] = useState(false);

// The largest jump a single `timeupdate` may legitimately report.
//
// The event fires about four times a second during playback. 1.5s leaves room
// for a backgrounded tab to coalesce several ticks while staying well under any
// seek a candidate would bother performing.
const MAX_TIMEUPDATE_ADVANCE_SECONDS = 1.5;

  const enforceAllowedTime = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (isCorrectingRef.current) return;

    // Any divergence from the allowed time (forward or backward) is
    // treated as an illegal seek and snapped back.
    if (Math.abs(audio.currentTime - allowedTimeRef.current) > 0.15) {
      isCorrectingRef.current = true;
      audio.currentTime = allowedTimeRef.current;
      // Let the browser settle the assignment before re-enabling checks.
      requestAnimationFrame(() => {
        isCorrectingRef.current = false;
      });
    }
  }, []);

  const handleTimeUpdate = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;

    if (isCorrectingRef.current) return;

    // Forward progress is bounded, not merely required to be forward.
    //
    // This branch used to accept anything at or ahead of the watermark, so a
    // jump straight to 60s satisfied it, was treated as normal playback, and
    // dragged the watermark with it -- the lock enforced the backward direction
    // and left the forward one open. Not every seek fires a `seeking` event
    // that handleSeeking can catch: assigning `currentTime` from devtools can
    // surface only as a `timeupdate`, which is exactly the adversarial case
    // this player exists to stop.
    //
    // `timeupdate` fires roughly every 250ms during playback, so a legitimate
    // advance is small. The ceiling is generous enough to survive a throttled
    // or backgrounded tab coalescing a few ticks, and far below any jump worth
    // making to skip audio.
    const delta = audio.currentTime - allowedTimeRef.current;

    if (delta >= -0.15 && delta <= MAX_TIMEUPDATE_ADVANCE_SECONDS) {
      allowedTimeRef.current = audio.currentTime;
      setCurrentTime(audio.currentTime);
    } else {
      enforceAllowedTime();
      setCurrentTime(allowedTimeRef.current);
    }
  }, [enforceAllowedTime]);

  const handleSeeking = useCallback(() => {
    enforceAllowedTime();
  }, [enforceAllowedTime]);

  const handleLoadedMetadata = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    setDuration(audio.duration);
  }, []);

  const handleEnded = useCallback(() => {
    setIsPlaying(false);
    setIsComplete(true);
    onComplete?.();
  }, [onComplete]);

  const handlePlayPause = useCallback(() => {
    const audio = audioRef.current;
    if (!audio || isComplete) return;

    if (audio.paused) {
      void audio.play();
      setIsPlaying(true);
    } else {
      audio.pause();
      setIsPlaying(false);
    }
  }, [isComplete]);

  // Attempt playback once on mount when asked to. Deliberately has no
  // dependency on `src`/`autoPlay` changing post-mount: this component is
  // meant to be remounted (via a `key` on section number) for each new
  // section, which gives every section both a fresh autoplay attempt and a
  // fresh lock watermark for free.
  useEffect(() => {
    if (!autoPlay) return;
    const audio = audioRef.current;
    if (!audio) return;

    void audio
      .play()
      .then(() => setIsPlaying(true))
      .catch(() => {
        // Browsers may require a direct user click before initial playback.
        // Do not treat this as an error; the Play button remains available.
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Belt-and-suspenders: also block keyboard seeking (Left/Right/Home/End/
  // MediaSeek keys) at the element level, in case focus reaches the audio
  // element itself.
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const blockSeekKeys = (e: KeyboardEvent) => {
      const seekKeys = [
        "ArrowLeft",
        "ArrowRight",
        "Home",
        "End",
        "MediaTrackPrevious",
        "MediaTrackNext",
        "MediaSeekBackward",
        "MediaSeekForward",
      ];
      if (seekKeys.includes(e.key)) {
        e.preventDefault();
        e.stopPropagation();
      }
    };

    audio.addEventListener("keydown", blockSeekKeys, true);
    return () => audio.removeEventListener("keydown", blockSeekKeys, true);
  }, []);

  const progressPercent =
    duration > 0 ? Math.min(100, (currentTime / duration) * 100) : 0;

  return (
    <div
      className={`rounded-2xl border border-gray-200 bg-white p-5 shadow-sm ${
        className ?? ""
      }`}
    >
      {/* No `controls` attribute: native controls (including the
          scrubbable seek bar) are intentionally never rendered. */}
      <audio
        ref={audioRef}
        src={src}
        preload="auto"
        onTimeUpdate={handleTimeUpdate}
        onSeeking={handleSeeking}
        onLoadedMetadata={handleLoadedMetadata}
        onEnded={handleEnded}
        tabIndex={-1}
        className="hidden"
      />

      <p className="mb-4 text-sm font-medium text-gray-800">
        {isComplete
          ? "Section complete"
          : isPlaying
            ? "Playing"
            : "Ready to play"}
      </p>

      <button
        type="button"
        data-testid="locked-audio-play-pause"
        disabled={isComplete}
        onClick={handlePlayPause}
        className="rounded-full bg-[#0d4d3a] px-4 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isComplete
          ? "Playback complete"
          : isPlaying
            ? "Pause"
            : "Play / Pause"}
      </button>

      <div className="mt-5 flex flex-col gap-1.5">
        {/* Read-only progress indicator. pointer-events: none ensures
            it can never act as a click-to-seek target, and it has no
            interactive role (not a <input type="range">, no slider
            semantics). */}
        <div
          className="relative h-1.5 w-full overflow-hidden rounded-full bg-gray-200"
          style={{ pointerEvents: "none" }}
          role="progressbar"
          aria-valuenow={Math.round(progressPercent)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-readonly="true"
        >
          <div
            className="h-full rounded-full bg-[#0d4d3a] transition-[width]"
            style={{ width: `${progressPercent}%`, pointerEvents: "none" }}
          />
        </div>

        <div
          data-testid="locked-audio-time"
          className="flex justify-between font-mono text-xs text-gray-500"
        >
          <span>{formatTime(currentTime)}</span>
          <span>{formatTime(duration)}</span>
        </div>
      </div>
    </div>
  );
}
