import { useEffect, useMemo, useState } from "react";

export function useExamTimer(initialSeconds: number, onTimeUp: () => void) {
  const [secondsLeft, setSecondsLeft] = useState(initialSeconds);

  // If the backend sends a different remaining time (for example after
  // loading or resuming a session), synchronize with it.
  useEffect(() => {
    setSecondsLeft(initialSeconds);
  }, [initialSeconds]);

  useEffect(() => {
    if (secondsLeft <= 0) {
      onTimeUp();
      return;
    }

    const interval = window.setInterval(() => {
      setSecondsLeft((current) => Math.max(0, current - 1));
    }, 1000);

    return () => window.clearInterval(interval);
  }, [secondsLeft, onTimeUp]);

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
