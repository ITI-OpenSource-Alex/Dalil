import { useEffect, useMemo, useRef, useState } from "react";

export function useExamTimer(initialSeconds: number, onTimeUp: () => void) {
  const [secondsLeft, setSecondsLeft] = useState(initialSeconds);
  const onTimeUpRef = useRef(onTimeUp);
  onTimeUpRef.current = onTimeUp;

  // Resyncing (e.g. once the backend's remaining_time_seconds becomes known
  // after loading) and ticking down are handled in one effect, keyed only on
  // initialSeconds. Keeping them as two separate effects (one resyncing
  // secondsLeft, another treating secondsLeft <= 0 as expiry) previously let
  // a resync and an expiry-check run in the same commit against the
  // not-yet-applied, stale secondsLeft value — e.g. going from a "session
  // not loaded yet" initialSeconds of 0 straight to a real value would still
  // see the old secondsLeft (0) and spuriously fire onTimeUp before the
  // countdown ever started.
  useEffect(() => {
    setSecondsLeft(initialSeconds);

    if (initialSeconds <= 0) {
      return;
    }

    const interval = window.setInterval(() => {
      setSecondsLeft((current) => {
        const next = Math.max(0, current - 1);
        if (next === 0) onTimeUpRef.current();
        return next;
      });
    }, 1000);

    return () => window.clearInterval(interval);
  }, [initialSeconds]);

  const minutes = Math.floor(secondsLeft / 60);
  const seconds = secondsLeft % 60;

  const formattedTime = useMemo(
    () =>
      `${minutes.toString().padStart(2, "0")}:${seconds
        .toString()
        .padStart(2, "0")}`,
    [minutes, seconds],
  );

  return {
    secondsLeft,
    formattedTime,
    isCritical: secondsLeft <= 300,
  };
}
