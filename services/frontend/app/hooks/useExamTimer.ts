import { useEffect, useState, useRef } from "react";

export function useExamTimer(
  initialSeconds: number,
  sessionId: string,
  onTimeUp: () => void,
) {
  const [secondsLeft, setSecondsLeft] = useState(initialSeconds);
  const heartbeatIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Countdown clock
  useEffect(() => {
    if (secondsLeft <= 0) {
      onTimeUp();
      return;
    }

    const timer = setInterval(() => {
      setSecondsLeft((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [secondsLeft, onTimeUp]);

  // Heartbeat system (Every 60s)
  useEffect(() => {
    heartbeatIntervalRef.current = setInterval(() => {
      fetch(`/api/sessions/${sessionId}/heartbeat`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ remaining_seconds: secondsLeft }),
      }).catch((err) => console.error("Heartbeat failed:", err));
    }, 60000);

    return () => {
      if (heartbeatIntervalRef.current)
        clearInterval(heartbeatIntervalRef.current);
    };
  }, [sessionId, secondsLeft]);

  const formatTime = () => {
    const minutes = Math.floor(secondsLeft / 60);
    const seconds = secondsLeft % 60;
    return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
  };

  const isCritical = secondsLeft <= 300; // 5 minutes

  return { secondsLeft, formatTime, isCritical };
}
