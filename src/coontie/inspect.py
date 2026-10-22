"""The inspection simulator: what the department would find if it walked in today.

Not a dashboard. Every finding is a row in the operator's own record that contradicts a rule
we already enforce elsewhere, carrying the citation and the identifier of the thing found.
The whole module is arithmetic over SQLite: no clock of its own (``now`` is passed in), no
I/O except the database it is given, and the same record always produces the same findings.

Severities:

- ``breach``   a rule is broken now; the department could cite this today.
- ``exposure`` something looks wrong and no rule is broken yet; fix it before it becomes one.
- ``note``     worth knowing, no exposure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

BREACH = "breach"
EXPOSURE = "exposure"
NOTE = "note"
ORDER = {BREACH: 0, EXPOSURE: 1, NOTE: 2}

CITATIONS = {
    "justification_missing": "Rule 64-4.222(12), F.A.C.",
    "justification_unsent": "Rule 64-4.222(12), F.A.C.",
    "justification_late": "Rule 64-4.222(12), F.A.C.",
    "disconnect_notice_missing": "Rule 64-4.222(2), F.A.C.",
    "disconnect_notice_late": "Rule 64-4.222(2), F.A.C.",
    "outage_report_missing": "Rule 64-4.222(2)(b), F.A.C.",
    "harvest_unscheduled": "Rule 64-4.222(6), F.A.C.",
    "disposal_early": "Rule 64-4.222(6), F.A.C.",
    "hold_unresolved": "Rule 64-4.222(11), F.A.C.",
    "expired_available": "Rule 64-4.221(2), F.A.C.",
    "manifest_unreceived": "s. 381.986(8)(g), F.S.",
    "manifest_no_invoice": "DH5059-OMMU-05/2026, wholesale invoice",
    "location_missing": "Rule 64-4.222(11), F.A.C.",
    "ledger_broken": "Rule 64-4.222(3), F.A.C.",
    "drift_open": "Rule 64-4.222(3), F.A.C.",
    "stock_negative": "Rule 64-4.222(11), F.A.C.",
    "stock_unit_mismatch": "Rule 64-4.222(11), F.A.C.",
    "stock_no_origin": "Rule 64-4.222(11), F.A.C.",
}


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    summary: str
    subject: str = ""
    detail: str = ""
    facts: dict = field(default_factory=dict)

    @property
    def citation(self) -> str:
        return CITATIONS.get(self.code, "")

    def line(self) -> str:
        where = f" [{self.subject}]" if self.subject else ""
        cite = f"  ({self.citation})" if self.citation else ""
        return f"{self.severity.upper():9} {self.summary}{where}{cite}"


@dataclass(frozen=True)
class CannotCheck:
    """An obligation this system cannot verify, said out loud rather than silently passed."""

    area: str
    why: str


CANNOT_CHECK = (
    CannotCheck(
        "Records reaching the department within 12 hours",
        "Coontie holds no department API credentials, so it cannot report whether a record was "
        "transmitted. It can prove what the record says.",
    ),
    CannotCheck(
        "Patient status and purchase limits at the counter",
        "MMUR access is unresolved; dispensing is out of scope until it is.",
    ),
    CannotCheck(
        "Physical security, cameras, and two-person presence",
        "Those are observed conditions, not records. The manifest proves who was named, not who was there.",
    ),
)


def _dt(value) -> datetime | None:
    if not value:
        return None
    text = str(value)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _amount(value) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001 - a bad number is a finding, not a crash
        return Decimal("0")


def _rows(ws, sql: str, args: tuple = ()):
    return ws.conn.execute(sql, args).fetchall()


def inspect(ws, now: datetime | None = None) -> list[Finding]:
    """Every finding, worst first. ``now`` is an argument so a test can pin the clock."""
    now = now or datetime.now(timezone.utc)
    findings: list[Finding] = []
    findings += _ledger(ws)
    findings += _justifications(ws, now)
    findings += _outages(ws, now)
    findings += _cultivation(ws)
    findings += _disposals(ws)
    findings += _holds_and_expiry(ws, now)
    findings += _transport(ws)
    findings += _stock(ws)
    findings += _drift(ws)
    findings += _locations(ws)
    return sorted(findings, key=lambda f: (ORDER.get(f.severity, 9), f.code, f.subject))


def _ledger(ws) -> list[Finding]:
    ok, detail = ws.ledger.verify_chain()
    if ok:
        return []
    return [Finding("ledger_broken", BREACH, f"The ledger does not verify: {detail}")]


def _justifications(ws, now) -> list[Finding]:
    from .amendments import is_exempt

    out: list[Finding] = []
    rows = _rows(
        ws,
        "SELECT a.id, a.target_id, a.cause, a.before_value, a.after_value, j.id AS jid, j.deadline, j.sent_at "
        "FROM amendments a LEFT JOIN justifications j ON j.amendment_id = a.id "
        "WHERE a.justification_id IS NULL OR j.id IS NULL",
    )
    for r in rows:
        if is_exempt(r["cause"]):
            continue  # the rule exempts this cause; no notice is owed
        out.append(Finding(
            "justification_missing", BREACH,
            f"Correction {r['target_id']} ({r['before_value']} to {r['after_value']}, cause "
            f"{r['cause']}) has no written justification drafted",
            subject=r["id"],
        ))
    for r in _rows(ws, "SELECT * FROM justifications"):
        deadline = _dt(r["deadline"])
        sent = _dt(r["sent_at"])
        if sent is None and deadline and now > deadline:
            out.append(Finding(
                "justification_unsent", BREACH,
                f"Justification {r['id']} was due {deadline.isoformat()} and has not been sent",
                subject=r["id"],
            ))
        elif sent and deadline and sent > deadline:
            late = sent - deadline
            hours = round(late.total_seconds() / 3600, 2)
            out.append(Finding(
                "justification_late", EXPOSURE,
                f"Justification {r['id']} was sent {hours}h after its deadline",
                subject=r["id"],
            ))
    return out


def _outages(ws, now) -> list[Finding]:
    from .compliance import DISCONNECT_NOTICE_DEADLINE, DISCONNECT_THRESHOLD

    out: list[Finding] = []
    for r in _rows(ws, "SELECT * FROM outages"):
        started = _dt(r["started_at"])
        restored = _dt(r["restored_at"])
        if not started:
            continue
        if restored is None:
            if now - started > DISCONNECT_THRESHOLD and not r["notice_created_at"]:
                out.append(Finding(
                    "disconnect_notice_missing", BREACH,
                    f"The connection has been down since {started.isoformat()} and no notice has been drafted",
                    subject=r["id"],
                ))
            continue
        if now - started > DISCONNECT_THRESHOLD:
            drafted = _dt(r["notice_created_at"])
            if not drafted:
                out.append(Finding(
                    "disconnect_notice_missing", BREACH,
                    f"Outage {r['id']} lasted {round((restored - started).total_seconds() / 3600, 2)}h "
                    "with no notice drafted",
                    subject=r["id"],
                ))
            elif drafted - started > DISCONNECT_NOTICE_DEADLINE:
                out.append(Finding(
                    "disconnect_notice_late", EXPOSURE,
                    f"Outage {r['id']}: the notice was drafted after the "
                    f"{DISCONNECT_NOTICE_DEADLINE.total_seconds() / 3600:.0f}-hour deadline",
                    subject=r["id"],
                ))
        if not r["report_csv"]:
            out.append(Finding(
                "outage_report_missing", EXPOSURE,
                f"Outage {r['id']} was restored with no itemized dispensation report on file",
                subject=r["id"],
            ))
    return out


def _cultivation(ws) -> list[Finding]:
    out: list[Finding] = []
    for r in _rows(ws, "SELECT id, plant_ids, harvested_at FROM harvests WHERE scheduled_at IS NULL"):
        if r["harvested_at"]:
            out.append(Finding(
                "harvest_unscheduled", BREACH,
                f"Harvest {r['id']} was taken without a schedule on file",
                subject=r["id"],
            ))
    return out


def _disposals(ws) -> list[Finding]:
    from .compliance import DISPOSAL_WAIT

    out: list[Finding] = []
    for r in _rows(ws, "SELECT * FROM disposals WHERE disposed_at IS NOT NULL"):
        scheduled, disposed = _dt(r["scheduled_at"]), _dt(r["disposed_at"])
        if scheduled and disposed and disposed - scheduled < DISPOSAL_WAIT:
            waited = (disposed - scheduled).total_seconds() / 3600
            out.append(Finding(
                "disposal_early", BREACH,
                f"Disposal {r['id']} of {r['subject']} happened {round(waited, 1)}h after it was "
                f"scheduled; the wait is {DISPOSAL_WAIT.total_seconds() / 3600:.0f}h",
                subject=r["id"],
            ))
    return out


def _holds_and_expiry(ws, now) -> list[Finding]:
    out: list[Finding] = []
    for r in _rows(ws, "SELECT id, product_id, quantity, unit FROM lots WHERE on_hold = 1"):
        out.append(Finding(
            "hold_unresolved", EXPOSURE,
            f"Lot {r['id']} of {r['quantity']} {r['unit']} is still on hold",
            subject=r["id"],
        ))
    today = now.date().isoformat()
    for r in _rows(ws, "SELECT id, upid, unit_count, expiration_date, room_id FROM final_products "
                       "WHERE expiration_date < ?", (today,)):
        out.append(Finding(
            "expired_available", EXPOSURE,
            f"{r['unit_count']} units of {r['upid']} expired {r['expiration_date']} and still sit in "
            f"{r['room_id']}",
            subject=r["id"],
        ))
    return out


def _transport(ws) -> list[Finding]:
    out: list[Finding] = []
    for r in _rows(ws, "SELECT id, recipient_name, departure_at, status FROM manifests "
                       "WHERE status = 'dispatched'"):
        out.append(Finding(
            "manifest_unreceived", EXPOSURE,
            f"Manifest {r['id']} to {r['recipient_name']} left on {str(r['departure_at'])[:10]} "
            "and no receipt is recorded",
            subject=r["id"],
            facts={"manifest": r["id"], "recipient": r["recipient_name"],
                   "departed": str(r["departure_at"])},
        ))
    for r in _rows(ws, "SELECT id, recipient_name FROM manifests WHERE status = 'received' "
                       "AND invoice_id = ''"):
        out.append(Finding(
            "manifest_no_invoice", NOTE,
            f"Manifest {r['id']} to {r['recipient_name']} was received with no wholesale invoice "
            "recorded; fine unless it was a sale",
            subject=r["id"],
        ))
    return out


def _stock(ws) -> list[Finding]:
    out: list[Finding] = []
    lots = {r["id"]: r for r in _rows(ws, "SELECT * FROM stock_lots")}
    moves: dict[str, list] = {}
    for m in _rows(ws, "SELECT lot_id, kind, amount, unit FROM stock_moves"):
        moves.setdefault(m["lot_id"], []).append(m)
    for lot_id, lot in lots.items():
        taken = sum((_amount(m["amount"]) for m in moves.get(lot_id, [])), Decimal("0"))
        left = _amount(lot["original"]) - taken
        if left < 0:
            out.append(Finding(
                "stock_negative", BREACH,
                f"Lot {lot_id} has given up {-left} {lot['unit']} more than it held",
                subject=lot_id,
            ))
        wrong_units = {m["unit"] for m in moves.get(lot_id, []) if m["unit"] and m["unit"] != lot["unit"]}
        if wrong_units:
            out.append(Finding(
                "stock_unit_mismatch", EXPOSURE,
                f"Lot {lot_id} is in {lot['unit']} but has moves recorded in "
                f"{', '.join(sorted(wrong_units))}; the balance cannot be trusted",
                subject=lot_id,
            ))
        if not lot["harvest_ids"] or lot["harvest_ids"] in ("[]", ""):
            if not lot["source_lot_id"]:
                out.append(Finding(
                    "stock_no_origin", NOTE,
                    f"Lot {lot_id} names no harvest and no parent lot; provenance stops here",
                    subject=lot_id,
                ))
    return out


def _drift(ws) -> list[Finding]:
    out: list[Finding] = []
    # only the newest comparison is open work; a superseded snapshot is history, and listing its
    # findings beside the current ones showed the same missing lot twice under two finding ids
    latest = ws.latest_snapshot()
    if latest is None:
        return out
    for r in _rows(
        ws,
        "SELECT id, kind, record_key, ours, theirs FROM drift_findings"
        " WHERE resolution IS NULL AND snapshot_id = ?",
        (latest["id"],),
    ):
        ours = json.loads(r["ours"] or "{}")
        theirs = json.loads(r["theirs"] or "{}")

        def number(value) -> str:
            text = str(value if value not in (None, "") else "?")
            return text[:-2] if text.endswith(".0") else text

        if r["kind"] == "missing_locally":
            detail = (f"the export has {number(theirs.get('quantity'))} "
                      f"{theirs.get('unit') or ''}".rstrip() + ", and no such lot is held here")
        elif r["kind"] == "missing_at_state":
            detail = (f"this record holds {number(ours.get('quantity'))} "
                      f"{ours.get('unit') or ''}".rstrip() + ", and the export has no such lot")
        else:
            fields = [key for key in ("quantity", "status", "unit")
                      if key in ours and ours.get(key) != theirs.get(key)]
            detail = ", ".join(
                f"{key} ours {number(ours.get(key))}, theirs {number(theirs.get(key))}" for key in fields
            )
        out.append(Finding(
            "drift_open", EXPOSURE,
            f"The state's record and ours disagree on {r['record_key']}"
            + (f" ({detail})" if detail else f" ({r['kind']})")
            + "; nobody has decided which is right",
            subject=r["id"],
            facts={"kind": r["kind"], "record_key": r["record_key"],
                   "ours": ours, "theirs": theirs},
        ))
    return out


def _locations(ws) -> list[Finding]:
    """A record without a facility location breaks 64-4.222(11) at the moment it is written."""
    out: list[Finding] = []
    missing = 0
    for r in _rows(ws, "SELECT event_key, payload FROM events"):
        try:
            payload = json.loads(r["payload"])
        except Exception:  # noqa: BLE001
            continue
        wants = any(k in payload for k in ("facility_location", "creating_facility_location",
                                           "transferring_facility_location", "receiving_facility_location"))
        if wants and not any(payload.get(k) for k in ("facility_location", "creating_facility_location",
                                                      "transferring_facility_location",
                                                      "receiving_facility_location")):
            missing += 1
    if missing:
        out.append(Finding(
            "location_missing", EXPOSURE,
            f"{missing} record(s) name no facility location",
        ))
    return out


def summarize(findings: list[Finding]) -> dict:
    counts = {BREACH: 0, EXPOSURE: 0, NOTE: 0}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    return counts


def as_dict(findings: list[Finding]) -> dict:
    return {
        "findings": [
            {"code": f.code, "severity": f.severity, "summary": f.summary, "subject": f.subject,
             "citation": f.citation}
            for f in findings
        ],
        "counts": summarize(findings),
        "cannot_check": [{"area": c.area, "why": c.why} for c in CANNOT_CHECK],
    }
