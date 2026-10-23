import sqlite3
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

_DAILY_QUOTA_DDL = """
CREATE TABLE IF NOT EXISTS daily_quota (
    date          TEXT PRIMARY KEY,
    request_count INTEGER NOT NULL DEFAULT 0
);
"""


class DailyQuotaExceeded(Exception):
    def __init__(self, date: str, limit: int):
        self.date = date
        self.limit = limit
        super().__init__(f"Daily openFDA quota of {limit} requests exceeded for {date} (UTC)")


class SlidingWindowRateLimiter:
    """In-process per-minute throttle. Does not need to persist across runs."""

    def __init__(
        self,
        limit_per_min: int,
        window_seconds: float = 60.0,
        time_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        self.limit_per_min = limit_per_min
        self.window_seconds = window_seconds
        self._time_fn = time_fn
        self._sleep_fn = sleep_fn
        self._timestamps: deque[float] = deque()

    def _evict_expired(self, now: float) -> None:
        while self._timestamps and now - self._timestamps[0] >= self.window_seconds:
            self._timestamps.popleft()

    def acquire(self) -> None:
        now = self._time_fn()
        self._evict_expired(now)
        if len(self._timestamps) >= self.limit_per_min:
            sleep_for = self.window_seconds - (now - self._timestamps[0])
            if sleep_for > 0:
                self._sleep_fn(sleep_for)
            now = self._time_fn()
            self._evict_expired(now)
        self._timestamps.append(now)


class DailyQuotaTracker:
    """SQLite-persisted daily request counter, UTC-dated so it survives process restarts and
    resumes correctly across day boundaries (the date is simply today's primary key)."""

    def __init__(
        self,
        db_path: Path | str,
        limit_per_day: int,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.limit_per_day = limit_per_day
        self._now_fn = now_fn
        self._conn = sqlite3.connect(self.db_path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_DAILY_QUOTA_DDL)

    def _today(self) -> str:
        return self._now_fn().astimezone(timezone.utc).date().isoformat()

    def _count_today(self) -> int:
        row = self._conn.execute(
            "SELECT request_count FROM daily_quota WHERE date=?", (self._today(),)
        ).fetchone()
        return row["request_count"] if row else 0

    def remaining_today(self) -> int:
        return max(self.limit_per_day - self._count_today(), 0)

    def check_and_increment(self) -> None:
        today = self._today()
        conn = self._conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT request_count FROM daily_quota WHERE date=?", (today,)
            ).fetchone()
            count = row["request_count"] if row else 0
            if count >= self.limit_per_day:
                conn.execute("ROLLBACK")
                raise DailyQuotaExceeded(today, self.limit_per_day)
            conn.execute(
                "INSERT INTO daily_quota(date, request_count) VALUES (?, 1) "
                "ON CONFLICT(date) DO UPDATE SET request_count = request_count + 1",
                (today,),
            )
            conn.execute("COMMIT")
        except DailyQuotaExceeded:
            raise
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def close(self) -> None:
        self._conn.close()


class RateLimiter:
    """Facade composing the per-minute throttle with the persisted daily quota check.

    acquire() waits on the sliding window first, then checks/increments the daily quota. The
    daily cap raises immediately rather than sleeping until tomorrow -- that decision belongs to
    the caller (e.g. the CLI just exits non-zero and the next cron/launchd run resumes politely).
    """

    def __init__(self, sliding_window: SlidingWindowRateLimiter, daily_quota: DailyQuotaTracker):
        self._sliding = sliding_window
        self._daily = daily_quota

    def acquire(self) -> None:
        self._sliding.acquire()
        self._daily.check_and_increment()

    def remaining_today(self) -> int:
        return self._daily.remaining_today()
