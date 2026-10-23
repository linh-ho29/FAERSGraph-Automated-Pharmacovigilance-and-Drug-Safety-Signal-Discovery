from pathlib import Path

import pytest
from freezegun import freeze_time

from faersgraph.openfda.rate_limiter import (
    DailyQuotaExceeded,
    DailyQuotaTracker,
    RateLimiter,
    SlidingWindowRateLimiter,
)


class FakeClock:
    """Manually-advanced clock so sliding-window tests don't depend on real sleeps."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleep_calls: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self.now += seconds


def test_sliding_window_allows_requests_under_limit() -> None:
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(
        limit_per_min=3, time_fn=clock.time, sleep_fn=clock.sleep
    )
    for _ in range(3):
        limiter.acquire()
    assert clock.sleep_calls == []


def test_sliding_window_sleeps_when_limit_exceeded() -> None:
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(
        limit_per_min=3, time_fn=clock.time, sleep_fn=clock.sleep
    )
    for _ in range(3):
        limiter.acquire()
    limiter.acquire()
    assert len(clock.sleep_calls) == 1
    assert clock.sleep_calls[0] == pytest.approx(60.0)


def test_sliding_window_does_not_sleep_once_window_has_passed() -> None:
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(
        limit_per_min=2, time_fn=clock.time, sleep_fn=clock.sleep
    )
    limiter.acquire()
    limiter.acquire()
    clock.now += 61.0
    limiter.acquire()
    assert clock.sleep_calls == []


def test_daily_quota_tracker_fresh_db_starts_at_zero(tmp_path: Path) -> None:
    tracker = DailyQuotaTracker(tmp_path / "quota.sqlite", limit_per_day=5)
    assert tracker.remaining_today() == 5


def test_daily_quota_tracker_increments_persist_across_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "quota.sqlite"
    tracker1 = DailyQuotaTracker(db_path, limit_per_day=5)
    tracker1.check_and_increment()
    tracker1.check_and_increment()
    tracker1.close()

    tracker2 = DailyQuotaTracker(db_path, limit_per_day=5)
    assert tracker2.remaining_today() == 3


def test_daily_quota_tracker_raises_when_exceeded(tmp_path: Path) -> None:
    tracker = DailyQuotaTracker(tmp_path / "quota.sqlite", limit_per_day=2)
    tracker.check_and_increment()
    tracker.check_and_increment()
    with pytest.raises(DailyQuotaExceeded):
        tracker.check_and_increment()


def test_daily_quota_tracker_resets_at_utc_midnight(tmp_path: Path) -> None:
    db_path = tmp_path / "quota.sqlite"
    with freeze_time("2026-01-01 23:59:59+00:00"):
        tracker = DailyQuotaTracker(db_path, limit_per_day=2)
        tracker.check_and_increment()
        tracker.check_and_increment()
        with pytest.raises(DailyQuotaExceeded):
            tracker.check_and_increment()

    with freeze_time("2026-01-02 00:00:01+00:00"):
        tracker2 = DailyQuotaTracker(db_path, limit_per_day=2)
        assert tracker2.remaining_today() == 2
        tracker2.check_and_increment()  # does not raise


def test_rate_limiter_facade_composes_both(tmp_path: Path) -> None:
    clock = FakeClock()
    sliding = SlidingWindowRateLimiter(limit_per_min=100, time_fn=clock.time, sleep_fn=clock.sleep)
    daily = DailyQuotaTracker(tmp_path / "quota.sqlite", limit_per_day=2)
    limiter = RateLimiter(sliding, daily)

    limiter.acquire()
    limiter.acquire()
    assert limiter.remaining_today() == 0
    with pytest.raises(DailyQuotaExceeded):
        limiter.acquire()
