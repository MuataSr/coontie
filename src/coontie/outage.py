"""Disconnections from the Department STS: the clock, the notice, and the outage CSV.

Rule 64-4.222(2), F.A.C., in its own words:

    "If an MMTC's Internal STS Tracking System disconnects from the Department STS
     Tracking System for more than 2 hours ... the MMTC must notify the department of the
     disconnection no later than three hours after the disconnection begins."

    64-4.222(2)(a): no dispensing during a disconnection unless the patient's active
    status, current physician certification and remaining supply can be verified in the
    Medical Marijuana Use Registry; if the registry is unavailable, do not dispense.

    64-4.222(2)(b): notify the department immediately on restoration, and within 24 hours
    provide an itemized CSV of all dispensations during the outage containing, at a
    minimum, the date and time, the patient ID number, the department seed-to-sale
    inventory identification number, the weight dispensed, and the dispensing facility
    location.

The rule's clock is the product's job. Everything here is pure text and arithmetic so it
can be tested against a simulated clock; the workspace does the writing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .compliance import DEPT_EMAIL, DISCONNECT_NOTICE_DEADLINE, DISCONNECT_THRESHOLD, OUTAGE_CSV_DEADLINE

REPORT_COLUMNS = (
    "Date and Time of Dispensation",
    "Patient ID Number",
    "Department Seed-to-Sale Inventory Identification Number",
    "Weight Dispensed",
    "Unit",
    "Dispensing Facility Location",
)


@dataclass(frozen=True)
class Outage:
    id: str
    facility_id: str
    started_at: datetime
    restored_at: datetime | None = None
    notice_subject: str = ""
    notice_body: str = ""
    notice_created_at: datetime | None = None
    notice_sent_at: datetime | None = None
    notice_breach_at: datetime | None = None
    restore_subject: str = ""
    restore_body: str = ""
    restore_created_at: datetime | None = None
    restore_sent_at: datetime | None = None
    report_csv: str = ""
    report_path: str = ""
    report_rows: int = 0
    report_created_at: datetime | None = None
    report_sent_at: datetime | None = None
    report_breach_at: datetime | None = None

    @property
    def open(self) -> bool:
        return self.restored_at is None

    @property
    def duration(self) -> timedelta:
        end = self.restored_at or datetime.now(timezone.utc)
        return end - self.started_at

    @property
    def notice_deadline(self) -> datetime:
        return self.started_at + DISCONNECT_NOTICE_DEADLINE

    @property
    def report_deadline(self) -> datetime | None:
        return self.restored_at + OUTAGE_CSV_DEADLINE if self.restored_at else None

    def elapsed(self, now: datetime) -> timedelta:
        return (self.restored_at or now) - self.started_at

    def notice_status(self, now: datetime | None = None) -> str:
        now = now or datetime.now(timezone.utc)
        if self.notice_sent_at:
            return "sent_on_time" if self.notice_sent_at <= self.notice_deadline else "sent_late"
        if self.elapsed(now) <= DISCONNECT_THRESHOLD:
            return "not_due"
        if now <= self.notice_deadline:
            return "due"
        return "late"

    def report_status(self, now: datetime | None = None) -> str:
        now = now or datetime.now(timezone.utc)
        if not self.restored_at:
            return "not_restored"
        if self.report_sent_at:
            return "sent_on_time" if self.report_sent_at <= self.report_deadline else "sent_late"
        if now > self.report_deadline:
            return "late"
        if self.report_created_at:
            return "ready"
        return "due"

    def notice_is_due(self, now: datetime) -> bool:
        """True once the disconnection has passed two hours, whether or not it has ended."""
        return self.elapsed(now) > DISCONNECT_THRESHOLD and not self.notice_created_at


def new_id(prefix: str = "out") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hms(td: timedelta) -> str:
    minutes = int(td.total_seconds() // 60)
    return f"{minutes // 60}h{minutes % 60:02d}m"


def notice_draft(
    outage: Outage,
    *,
    mmtc_name: str,
    license_number: str,
    dispensations: int,
    contact: str = "",
    now: datetime | None = None,
) -> tuple[str, str]:
    now = now or datetime.now(timezone.utc)
    subject = (
        f"Disconnection notice - {mmtc_name} - license {license_number} - "
        f"{outage.started_at.astimezone(timezone.utc).strftime('%Y-%m-%d')}"
    )
    elapsed = outage.elapsed(now)
    body = "\n".join(
        [
            f"To: {DEPT_EMAIL}",
            f"Subject: {subject}",
            "",
            "Notice of disconnection between the MMTC's Internal STS Tracking System and the",
            "Department STS Tracking System, submitted under Rule 64-4.222(2), F.A.C.",
            "",
            f"MMTC: {mmtc_name}",
            f"License number: {license_number}",
            f"Facility: {outage.facility_id}",
            f"Outage reference: {outage.id}",
            "",
            f"Disconnection began: {_utc(outage.started_at)}",
            f"Duration at the time of this notice: {_hms(elapsed)} (the notice threshold is 2 hours)",
            f"Time of this notice: {_utc(now)}",
            f"Notice deadline: {_utc(outage.notice_deadline)} (3 hours after the disconnection began)",
            "",
            f"Dispensations recorded during the disconnection so far: {dispensations}",
            (
                "Each of those dispensations was verified against the Medical Marijuana Use Registry for "
                "active status, a current physician certification, and remaining order and supply limits "
                "before dispensing, as required by Rule 64-4.222(2)(a), F.A.C."
                if dispensations
                else "No dispensing has occurred during the disconnection."
            ),
            "",
            "Communication has not been restored as of this notice. The department will be notified",
            "immediately upon restoration, and the itemized CSV of dispensations during the outage will",
            "follow within 24 hours, as required by Rule 64-4.222(2)(b), F.A.C.",
        ]
    )
    if contact:
        body += f"\n\nContact for this notice: {contact}"
    return subject, body


def restoration_draft(
    outage: Outage,
    *,
    mmtc_name: str,
    license_number: str,
    dispensations: int,
    contact: str = "",
) -> tuple[str, str]:
    assert outage.restored_at is not None
    subject = (
        f"Restoration of connection - {mmtc_name} - license {license_number} - "
        f"{outage.restored_at.astimezone(timezone.utc).strftime('%Y-%m-%d')}"
    )
    body = "\n".join(
        [
            f"To: {DEPT_EMAIL}",
            f"Subject: {subject}",
            "",
            "Notice that communication between the MMTC's Internal STS Tracking System and the",
            "Department STS Tracking System has been restored, submitted under",
            "Rule 64-4.222(2)(b), F.A.C.",
            "",
            f"MMTC: {mmtc_name}",
            f"License number: {license_number}",
            f"Facility: {outage.facility_id}",
            f"Outage reference: {outage.id}",
            "",
            f"Disconnection began: {_utc(outage.started_at)}",
            f"Communication restored: {_utc(outage.restored_at)}",
            f"Total duration: {_hms(outage.restored_at - outage.started_at)}",
            "",
            "The itemized list of dispensations that occurred during the outage is provided in CSV",
            "format with this notice, and is also recorded in the internal seed-to-sale tracking",
            "system. It contains, for each dispensation, the date and time, the patient ID number, the",
            "department seed-to-sale inventory identification number, the weight dispensed, and the",
            "dispensing facility location.",
            "",
            f"Dispensations during the outage: {dispensations}",
            "Records created during the outage are being submitted to the Department STS Tracking",
            "System in accordance with the timeframes in Form DH5059-OMMU-05/2026.",
        ]
    )
    if contact:
        body += f"\n\nContact for this notice: {contact}"
    return subject, body


def _csv_field(value: str) -> str:
    text = "" if value is None else str(value)
    if any(ch in text for ch in ',"\n\r'):
        return '"' + text.replace('"', '""') + '"'
    return text


def render_dispensations_csv(rows: list[dict]) -> str:
    lines = [",".join(_csv_field(c) for c in REPORT_COLUMNS)]
    for r in rows:
        lines.append(
            ",".join(
                _csv_field(v)
                for v in (
                    _iso(r["dispensed_at"]) if isinstance(r["dispensed_at"], datetime) else r["dispensed_at"],
                    r["patient_id"],
                    r["inventory_id"],
                    str(Decimal(str(r["weight"]))),
                    r["unit"],
                    r["location"],
                )
            )
        )
    return "\n".join(lines) + "\n"
