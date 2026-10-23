"""Failed-attempt limiting, shared by terminal pairing and by operator sign-in.

Held in memory for the life of the server on purpose: a lockout that survives a restart is a lockout
an attacker can enforce, and this appliance's restarts are the facility's own.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

MAX_ATTEMPTS = 5
LOCKOUT = timedelta(minutes=15)


class Limiter:
    """Failures per key (an address, or an address and a person) inside one lockout window."""

    def __init__(self, *, limit: int = MAX_ATTEMPTS, lockout: timedelta = LOCKOUT):
        self.limit = limit
        self.lockout = lockout
        self.failures: dict = {}

    def retry_after(self, key: str, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        stamps = [stamp for stamp in self.failures.get(key, []) if now - stamp < self.lockout]
        self.failures[key] = stamps
        if len(stamps) < self.limit:
            return 0
        return max(1, int((self.lockout - (now - min(stamps))).total_seconds()))

    def remaining(self, key: str, now: datetime | None = None) -> int:
        """How many tries are left before the lockout, for the refusal a person reads."""
        return max(0, self.limit - len(self.failures.get(key, [])))

    def fail(self, key: str, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        self.failures.setdefault(key, []).append(now)

    def clear(self, key: str) -> None:
        self.failures.pop(key, None)
