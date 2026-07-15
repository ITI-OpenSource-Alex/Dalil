from datetime import datetime, timedelta, timezone

from app.services.timer_service import TimerService


def test_timer_expires_after_time_limit_plus_grace_period() -> None:
    timer = TimerService()
    started_at = datetime.now(timezone.utc) - timedelta(seconds=91)

    assert timer.is_expired(started_at, 60) is True
