"""Guardrails: the failures nobody notices, surfaced as countable items.

Derived from the pain research (2026-10-21): operators complained about limit and
minor checks that silently did not fire, package holds nobody was watching, expirations
nobody tracked, and errors discovered late. The product answer is not a dashboard. It is
a short, always-visible list of things that are wrong right now, each with the rule it
touches and the action that clears it.

Every alert carries a citation. No alert exists for a condition the rules or the form
do not care about.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

from . import compliance as c


class Guard(str, Enum):
    LOT_ON_HOLD = "lot_on_hold"
    EXPIRING_PRODUCT = "expiring_product"
    ADJUSTMENT_UNJUSTIFIED = "adjustment_unjustified"
    DISCONNECT_CLOCK = "disconnect_clock"
    STALE_LOCATION = "stale_location"


# Which alerts block work, which merely warn. Severity drives ordering on the screen.
BLOCKING = {Guard.LOT_ON_HOLD, Guard.DISCONNECT_CLOCK}


@dataclass(frozen=True)
class Alert:
    guard: Guard
    subject: str
    message: str
    citation: str
    action: str
    severity: c.Severity = c.Severity.WARNING
    evidence: dict = field(default_factory=dict)

    @property
    def blocks(self) -> bool:
        return self.guard in BLOCKING

    def sort_key(self) -> tuple:
        return (0 if self.blocks else 1, self.guard.value, self.subject)


def lot_on_hold(lot, reason: str = "") -> Alert | None:
    """A held lot cannot legally be dispensed; it must come off the floor at once."""
    if not getattr(lot, "on_hold", False):
        return None
    return Alert(
        guard=Guard.LOT_ON_HOLD,
        subject=str(lot.id),
        message=f"Lot {lot.id} is on hold and cannot be dispensed until the hold clears."
        + (f" Reason: {reason}" if reason else ""),
        citation="Rule 64-4.222(2)(a) and the state STS package status",
        action="Quarantine the lot and record the hold's resolution before selling it.",
        severity=c.Severity.VIOLATION,
        evidence={"lot_id": str(lot.id), "room": str(getattr(lot, "room_id", ""))},
    )


def expiring_products(products, now: datetime, window_days: int = 30) -> list[Alert]:
    """Final products whose expiration is inside the window, soonest first."""
    out: list[Alert] = []
    horizon = now + timedelta(days=window_days)
    for p in products:
        exp = getattr(p, "expiration_date", None)
        if exp is None or exp > horizon:
            continue
        expired = exp <= now
        out.append(
            Alert(
                guard=Guard.EXPIRING_PRODUCT,
                subject=str(p.id),
                message=(
                    f"{p.approved_product_name} ({p.id}) has "
                    + ("EXPIRED" if expired else f"expires {exp.date().isoformat()}")
                ),
                citation="DH5059 final product inventory; expiration is immutable once recorded",
                action="Pull it, or schedule disposal (72-hour wait before disposal).",
                severity=c.Severity.VIOLATION if expired else c.Severity.WARNING,
                evidence={"expiration": exp.isoformat(), "room": str(getattr(p, "room_id", ""))},
            )
        )
    return out


def unjustified_adjustments(adjustments) -> list[Alert]:
    """Non-exempt adjustments with no justification on file, or one past 12 hours."""
    out: list[Alert] = []
    for a in adjustments:
        if a.cause in c.EXEMPT_ADJUSTMENT_CAUSES:
            continue
        if a.justification_sent_at is not None and (
            a.justification_sent_at - a.occurred_at <= c.ADJUSTMENT_JUSTIFICATION_DEADLINE
        ):
            continue
        deadline = a.occurred_at + c.ADJUSTMENT_JUSTIFICATION_DEADLINE
        out.append(
            Alert(
                guard=Guard.ADJUSTMENT_UNJUSTIFIED,
                subject=f"{a.inventory_id}:{a.occurred_at.isoformat()}",
                message=(
                    f"Adjustment of {a.quantity} {a.unit} on {a.inventory_id} "
                    f"({a.cause}) needs a written justification."
                ),
                citation="Rule 64-4.222(12), F.A.C.",
                action=f"Draft and send the justification to {c.DEPT_EMAIL}; due {deadline.isoformat()}.",
                severity=c.Severity.VIOLATION,
                evidence={"cause": a.cause, "deadline": deadline.isoformat()},
            )
        )
    return out


def disconnect_clock(
    started_at: datetime,
    now: datetime,
    restored_at: datetime | None = None,
    notified_at: datetime | None = None,
) -> Alert | None:
    """The 2-hour threshold and the 3-hour notice deadline, as a live countdown."""
    elapsed = (restored_at or now) - started_at
    if elapsed <= c.DISCONNECT_THRESHOLD and restored_at is None:
        remaining = c.DISCONNECT_THRESHOLD - elapsed
        return Alert(
            guard=Guard.DISCONNECT_CLOCK,
            subject="disconnect",
            message=f"Disconnected {_hms(elapsed)}; notice is due at {_hms(c.DISCONNECT_THRESHOLD)}.",
            citation="Rule 64-4.222(2), F.A.C.",
            action="Restore the link, or prepare the notice now.",
            severity=c.Severity.WARNING,
            evidence={"elapsed_seconds": elapsed.total_seconds(), "remaining": str(remaining)},
        )
    if notified_at is not None and notified_at <= started_at + c.DISCONNECT_NOTICE_DEADLINE:
        return None
    return Alert(
        guard=Guard.DISCONNECT_CLOCK,
        subject="disconnect",
        message=(
            f"Disconnected {_hms(elapsed)} and the 3-hour notice deadline "
            f"({_hms(c.DISCONNECT_NOTICE_DEADLINE)}) was missed."
        ),
        citation="Rule 64-4.222(2), F.A.C.",
        action=f"Send the notice to {c.DEPT_EMAIL} now and record the send time.",
        severity=c.Severity.VIOLATION,
        evidence={
            "elapsed_seconds": elapsed.total_seconds(),
            "notified_at": notified_at.isoformat() if notified_at else None,
        },
    )


def stale_locations(records, known_rooms: set[str]) -> list[Alert]:
    """Records pointing at a room that no longer exists, or at no room at all."""
    out: list[Alert] = []
    for r in records:
        room = getattr(r, "room_id", None)
        if room is None or str(room) not in known_rooms:
            out.append(
                Alert(
                    guard=Guard.STALE_LOCATION,
                    subject=str(getattr(r, "id", "?")),
                    message=f"Record {getattr(r, 'id', '?')} points at room {room!r}, which is not a known room.",
                    citation="Rule 64-4.222(11), F.A.C.",
                    action="Move it to a known room and record the move.",
                    severity=c.Severity.VIOLATION,
                    evidence={"room": str(room)},
                )
            )
    return out


def collect(
    *,
    lots=(),
    products=(),
    adjustments=(),
    records=(),
    known_rooms=(),
    now: datetime | None = None,
    expiry_window_days: int = 30,
    disconnect=None,
) -> list[Alert]:
    """Everything wrong right now, blocking items first."""
    now = now or datetime.now(timezone.utc)
    alerts: list[Alert] = []
    for lot in lots:
        a = lot_on_hold(lot)
        if a:
            alerts.append(a)
    alerts += expiring_products(products, now, expiry_window_days)
    alerts += unjustified_adjustments(adjustments)
    if known_rooms:
        alerts += stale_locations(records, set(map(str, known_rooms)))
    if disconnect:
        a = disconnect_clock(**disconnect)
        if a:
            alerts.append(a)
    return sorted(alerts, key=lambda a: a.sort_key())


def counts(alerts) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in alerts:
        out[a.guard.value] = out.get(a.guard.value, 0) + 1
    return out


def _hms(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m{s:02d}s"
