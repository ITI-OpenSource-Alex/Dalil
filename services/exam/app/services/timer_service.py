from datetime import datetime, timezone


class TimerService:
    GRACE_PERIOD_SECONDS = 30

    def remaining_time(self, started_at: datetime, limit_seconds: int) -> int:
        elapsed_seconds = self._elapsed_seconds(started_at)
        return max(0, int(limit_seconds - elapsed_seconds))

    def is_expired(self, started_at: datetime, limit_seconds: int) -> bool:
        elapsed_seconds = self._elapsed_seconds(started_at)
        return elapsed_seconds > limit_seconds + self.GRACE_PERIOD_SECONDS

    def _elapsed_seconds(self, started_at: datetime) -> float:
        started_at_utc = self._as_utc(started_at)
        return (datetime.now(timezone.utc) - started_at_utc).total_seconds()

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
