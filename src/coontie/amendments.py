"""Corrections: amend a record without deleting it, and justify it to the department.

Why this module exists, in the operators' own words (OMMU workshop, 2025-10-29):

    "At the harvest... if you make a mistake that's a very expensive and time-consuming
     mistake. You have to actually go engage the operator of the system and go through a
     lot of coding and back-end work in order to reverse the error. And you can't really
     move your inventory until that's done."

The rule that makes the paperwork unavoidable is 64-4.222(12): a change to weight or
count that did **not** result from processing, dispensation, a wholesale purchase or
distribution, or disposal of waste needs a written justification to
ommu_seedtosale@flhealth.gov within 12 hours.

So: nothing is deleted, every change carries a cause, and a non-exempt change produces a
draft the operator can send as-is.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .compliance import ADJUSTMENT_JUSTIFICATION_DEADLINE, DEPT_EMAIL, EXEMPT_ADJUSTMENT_CAUSES

# Causes an operator can pick. The first five are the rule's own exemptions; the rest are
# the ordinary ways a number goes wrong, and every one of them needs the 12-hour notice.
NON_EXEMPT_CAUSES = (
    "miscount",
    "shrinkage",
    "spillage",
    "damage",
    "theft",
    "contamination",
    "data_entry_error",
    "expired_destruction",
    "other",
)

ALL_CAUSES = tuple(sorted(EXEMPT_ADJUSTMENT_CAUSES)) + NON_EXEMPT_CAUSES


def is_exempt(cause: str) -> bool:
    return cause in EXEMPT_ADJUSTMENT_CAUSES


def validate_cause(cause: str) -> str:
    if cause not in ALL_CAUSES:
        raise ValueError(f"unknown cause {cause!r}; choose one of: {', '.join(ALL_CAUSES)}")
    return cause


@dataclass(frozen=True)
class Amendment:
    """A single change to a record. The original value is never overwritten in the ledger."""

    id: str
    target_kind: str          # 'lot' right now; 'product' when S5 lands
    target_id: str
    field: str                # 'quantity' | 'on_hold'
    before: str
    after: str
    cause: str
    reason: str
    actor: str
    occurred_at: datetime
    facility_id: str = ""
    unit: str = ""
    justification_id: str | None = None
    sequence: int = 0
    justification_sent_at: datetime | None = None

    @property
    def exempt(self) -> bool:
        return is_exempt(self.cause)

    @property
    def requires_justification(self) -> bool:
        return not self.exempt

    @property
    def deadline(self) -> datetime:
        return self.occurred_at + ADJUSTMENT_JUSTIFICATION_DEADLINE

    @property
    def delta(self) -> Decimal:
        if self.field != "quantity":
            return Decimal("0")  # a hold change is not a quantity movement
        try:
            return Decimal(self.after) - Decimal(self.before)
        except Exception:
            return Decimal("0")

    def status(self, now: datetime | None = None) -> str:
        now = now or datetime.now(timezone.utc)
        if not self.requires_justification:
            return "exempt"
        if self.justification_id:
            return "drafted"
        return "overdue" if now > self.deadline else "pending"

    # Guardrails expect these attribute names; keeping them avoids a translation layer.
    @property
    def inventory_id(self) -> str:
        return self.target_id

    @property
    def quantity(self) -> Decimal:
        return self.delta


@dataclass(frozen=True)
class Justification:
    id: str
    amendment_id: str
    subject: str
    body: str
    created_at: datetime
    deadline: datetime
    sent_at: datetime | None = None
    recipient: str = DEPT_EMAIL

    @property
    def status(self) -> str:
        if self.sent_at:
            return "sent_on_time" if self.sent_at <= self.deadline else "sent_late"
        return "overdue" if datetime.now(timezone.utc) > self.deadline else "draft"


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def draft_text(
    amendment: Amendment,
    *,
    mmtc_name: str,
    license_number: str,
    product_name: str,
    upid: str,
    extra: str = "",
) -> tuple[str, str]:
    """Compose the 64-4.222(12) notice. Deliberately plain: no adjectives, no apology."""
    when = amendment.occurred_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    deadline = amendment.deadline.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    change = f"{amendment.before} {amendment.unit}".strip() + " to " + f"{amendment.after} {amendment.unit}".strip()
    delta = amendment.delta
    subject = f"Weight/count adjustment justification - {product_name} - {amendment.target_id} - {when[:10]}"

    body = "\n".join(
        [
            f"To: {DEPT_EMAIL}",
            f"Subject: {subject}",
            "",
            "Written justification for a change to weight or count inventory, submitted under",
            "Rule 64-4.222(12), F.A.C.",
            "",
            f"MMTC: {mmtc_name}",
            f"License number: {license_number}",
            f"Facility: {amendment.facility_id}",
            "",
            f"Record: {amendment.target_id}",
            f"Product: {product_name}",
            f"Unique product ID: {upid}",
            "",
            f"Change: {change} (difference {delta:+} {amendment.unit})".replace("+-", "-"),
            f"Cause: {amendment.cause} (not one of the exemptions listed in the rule)",
            f"Reason recorded by the operator: {amendment.reason}",
            f"Date and time of the adjustment: {when}",
            f"Recorded by: {amendment.actor}",
            "",
            "This adjustment did not result from a processing step, dispensation of marijuana,",
            "wholesale purchase or distribution, or disposal of waste.",
            "",
            "Both the original value and this correction remain in the internal seed-to-sale",
            "tracking system with an unbroken audit trail, for the 3-year retention period",
            "required by Rule 64-4.222(4), F.A.C.",
            "",
            f"Notice deadline: {deadline} (12 hours after the adjustment, per Rule 64-4.222(12)).",
        ]
    )
    if extra:
        body += "\n\nAdditional context:\n" + extra.strip()
    return subject, body


def deadline_remaining(amendment: Amendment, now: datetime | None = None) -> timedelta:
    now = now or datetime.now(timezone.utc)
    return amendment.deadline - now
