"""Executable compliance rules for a Florida MMTC internal seed-to-sale system.

Every rule here cites the provision it enforces. The point of this module is that
a rule is never prose: it is a citation plus a check that returns a Finding.

Primary sources (retrieved 2026-10-21):
  Rule 64-4.221, F.A.C.  MMTC Seed-to-Sale Tracking System Integration (New 8-24-26)
  Rule 64-4.222, F.A.C.  MMTC STS Tracking System Procedures (New 8-24-26)
  Form DH5059-OMMU-05/2026, MMTC Seed-to-Sale Required Data Collection Document
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum

# --- Thresholds, all taken verbatim from the rule or the form ----------------------

EVENT_WINDOW = timedelta(hours=12)          # DH5059 preamble: "within 12 hours"
REALTIME_TOLERANCE = timedelta(seconds=60)  # our allowance for clock/queue lag
DISCONNECT_THRESHOLD = timedelta(hours=2)   # 64-4.222(2)
DISCONNECT_NOTICE_DEADLINE = timedelta(hours=3)  # 64-4.222(2)
OUTAGE_CSV_DEADLINE = timedelta(hours=24)   # 64-4.222(2)(b)
DEPARTMENT_CSV_DEADLINE = timedelta(hours=48)  # 64-4.222(4)
RETENTION_DAYS = 1095                       # 64-4.222(4): 3 years
ADJUSTMENT_JUSTIFICATION_DEADLINE = timedelta(hours=12)  # 64-4.222(12)
DISPOSAL_WAIT = timedelta(hours=72)         # DH5059 waste sections
OUNCE_IN_GRAMS = Decimal("0.0353")          # 64-4.222(6): 1 g = 0.0353 oz

DEPT_EMAIL = "ommu_seedtosale@flhealth.gov"

# 64-4.222(12): adjustments from these causes are exempt from the written
# justification requirement.
EXEMPT_ADJUSTMENT_CAUSES = frozenset(
    {
        "processing",
        "dispensation",
        "wholesale_purchase",
        "wholesale_distribution",
        "waste_disposal",
    }
)

# 64-4.222(5): the only roles allowed to touch the internal STS.
AUTHORIZED_ACCESS_ROLES = frozenset(
    {
        "mmtc_owner",
        "mmtc_officer",
        "mmtc_manager",
        "mmtc_employee",
        "internal_sts_vendor",
        "department_sts_vendor",
    }
)


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    VIOLATION = "violation"


@dataclass(frozen=True)
class Rule:
    id: str
    citation: str
    statement: str


@dataclass(frozen=True)
class Finding:
    rule_id: str
    citation: str
    severity: Severity
    message: str
    evidence: dict = field(default_factory=dict)


RULES: dict[str, Rule] = {
    r.id: r
    for r in (
        Rule(
            "STS-1",
            "Rule 64-4.221(2), F.A.C.",
            "The internal STS must stay fully integrated with the department STS in real time over the API.",
        ),
        Rule(
            "STS-2",
            "Rule 64-4.221(4), F.A.C.",
            "Full integration must be achieved before the MMTC obtains cultivation authorization.",
        ),
        Rule(
            "STS-3",
            "Rule 64-4.221(5)(b), F.A.C.",
            "A written integration plan must be approved before integration, and must name the internal STS, milestones, a contingency plan, and the responsible employees.",
        ),
        Rule(
            "STS-4",
            "Rule 64-4.221(6), F.A.C.",
            "A change of internal STS vendor requires a new integration plan and a new validation with the department vendor before the change.",
        ),
        Rule(
            "PROC-1",
            "Rule 64-4.222(2), F.A.C.",
            "A disconnection longer than 2 hours must be reported to the department no later than 3 hours after the disconnection begins.",
        ),
        Rule(
            "PROC-2",
            "Rule 64-4.222(2)(a), F.A.C.",
            "No dispensing during a disconnection unless MMUR status and limits are verifiable; if MMUR is unavailable, do not dispense.",
        ),
        Rule(
            "PROC-3",
            "Rule 64-4.222(2)(b), F.A.C.",
            "After restoration, an itemized CSV of dispensations during the outage is due within 24 hours.",
        ),
        Rule(
            "PROC-4",
            "Rule 64-4.222(3), F.A.C. and Form DH5059-OMMU-05/2026",
            "Each DH5059 record must reach the department within its stated timeframe (12 hours by default, real time for dispensing, refunds, voids and transfers).",
        ),
        Rule(
            "PROC-5",
            "Rule 64-4.222(4), F.A.C.",
            "All data must be retained 3 years, and native data must be producible as CSV within 48 hours of a department request.",
        ),
        Rule(
            "PROC-6",
            "Rule 64-4.222(5), F.A.C.",
            "Only MMTC people, the internal STS vendor, and the department STS vendor may access the internal STS.",
        ),
        Rule(
            "PROC-7",
            "Rule 64-4.222(6), F.A.C.",
            "Whole flower recorded in ounces converts at 1 g = 0.0353 oz.",
        ),
        Rule(
            "PROC-8",
            "Rule 64-4.222(7), F.A.C.",
            "A dispensation is recorded under exactly one route of administration, and it must be a route the qualified physician approved.",
        ),
        Rule(
            "PROC-9",
            "Rule 64-4.222(8), F.A.C.",
            "The department-approved product name is used in the STS and in the point of sale.",
        ),
        Rule(
            "PROC-10",
            "Rule 64-4.222(9), F.A.C.",
            "Every product type and delivery device carries a unique product ID, used consistently across systems.",
        ),
        Rule(
            "PROC-11",
            "Rule 64-4.222(10), F.A.C.",
            "A transportation manifest is generated from the internal STS for every transport.",
        ),
        Rule(
            "PROC-12",
            "Rule 64-4.222(11), F.A.C.",
            "The STS identifies the precise location of marijuana at all times.",
        ),
        Rule(
            "PROC-13",
            "Rule 64-4.222(12), F.A.C.",
            "Non-standard weight or count adjustments need a written justification to the department within 12 hours.",
        ),
        Rule(
            "FORM-1",
            "Form DH5059-OMMU-05/2026",
            "A harvest must be scheduled before plants are harvested.",
        ),
        Rule(
            "FORM-2",
            "Form DH5059-OMMU-05/2026",
            "Inventory and plant disposal must be scheduled at least 72 hours before disposal.",
        ),
        Rule(
            "FORM-3",
            "Form DH5059-OMMU-05/2026",
            "A final product expiration date, once recorded, cannot be changed.",
        ),
        Rule(
            "FORM-4",
            "Rule 64-4.221(1)(c), F.A.C.",
            "A unique product ID groups products of the same cultivar, size, volume, flavor, THC:CBD ratio and route; a unique SKU may serve as the ID.",
        ),
    )
}


def _finding(rule_id: str, severity: Severity, message: str, **evidence) -> Finding:
    rule = RULES[rule_id]
    return Finding(
        rule_id=rule_id,
        citation=rule.citation,
        severity=severity,
        message=message,
        evidence=evidence,
    )


# --- Checks -----------------------------------------------------------------------


def check_event_timing(timing: str, occurred_at: datetime, recorded_at: datetime) -> Finding | None:
    """PROC-4: was the record produced inside the DH5059 window?"""
    lag = recorded_at - occurred_at
    limit = REALTIME_TOLERANCE if timing == "realtime" else EVENT_WINDOW
    if lag <= limit:
        return None
    return _finding(
        "PROC-4",
        Severity.VIOLATION,
        f"Record produced {lag} after the underlying action; limit is {limit} ({timing}).",
        occurred_at=occurred_at.isoformat(),
        recorded_at=recorded_at.isoformat(),
        lag_seconds=lag.total_seconds(),
    )


def check_harvest_scheduled(harvest_at: datetime, scheduled_at: datetime | None) -> Finding | None:
    """FORM-1"""
    if scheduled_at and scheduled_at <= harvest_at:
        return None
    return _finding(
        "FORM-1",
        Severity.VIOLATION,
        "Harvest occurred without a prior scheduled harvest record.",
        harvest_at=harvest_at.isoformat(),
        scheduled_at=scheduled_at.isoformat() if scheduled_at else None,
    )


def check_disposal_wait(scheduled_at: datetime, disposed_at: datetime) -> Finding | None:
    """FORM-2"""
    if disposed_at - scheduled_at >= DISPOSAL_WAIT:
        return None
    return _finding(
        "FORM-2",
        Severity.VIOLATION,
        f"Disposal occurred {disposed_at - scheduled_at} after scheduling; the wait is 72 hours.",
        scheduled_at=scheduled_at.isoformat(),
        disposed_at=disposed_at.isoformat(),
    )


def check_expiration_immutable(recorded: datetime, proposed: datetime) -> Finding | None:
    """FORM-3"""
    if recorded == proposed:
        return None
    return _finding(
        "FORM-3",
        Severity.VIOLATION,
        "Attempt to change a final product expiration date already recorded.",
        recorded=recorded.isoformat(),
        proposed=proposed.isoformat(),
    )


def check_adjustment_justification(
    adjusted_at: datetime,
    cause: str,
    justification_sent_at: datetime | None,
) -> Finding | None:
    """PROC-13"""
    if cause in EXEMPT_ADJUSTMENT_CAUSES:
        return None
    if justification_sent_at is None:
        return _finding(
            "PROC-13",
            Severity.VIOLATION,
            f"Adjustment with cause '{cause}' has no written justification on file.",
            adjusted_at=adjusted_at.isoformat(),
            cause=cause,
        )
    lag = justification_sent_at - adjusted_at
    if lag <= ADJUSTMENT_JUSTIFICATION_DEADLINE:
        return None
    return _finding(
        "PROC-13",
        Severity.VIOLATION,
        f"Justification sent {lag} after the adjustment; the limit is 12 hours.",
        adjusted_at=adjusted_at.isoformat(),
        justification_sent_at=justification_sent_at.isoformat(),
        cause=cause,
    )


def check_dispensation_routes(
    dispensation_routes: list[str],
    physician_approved_routes: set[str],
) -> list[Finding]:
    """PROC-8: one route per dispensation, and it must be an approved route."""
    out: list[Finding] = []
    if len(set(dispensation_routes)) > 1:
        out.append(
            _finding(
                "PROC-8",
                Severity.VIOLATION,
                f"Dispensation recorded under {len(set(dispensation_routes))} routes; exactly one is allowed.",
                routes=dispensation_routes,
            )
        )
    for route in set(dispensation_routes):
        if route not in physician_approved_routes:
            out.append(
                _finding(
                    "PROC-8",
                    Severity.VIOLATION,
                    f"Route '{route}' is not a route approved for this patient.",
                    route=route,
                    approved=sorted(physician_approved_routes),
                )
            )
    return out


def check_disconnect(
    started_at: datetime,
    restored_at: datetime | None,
    notified_at: datetime | None,
) -> list[Finding]:
    """PROC-1 and PROC-3"""
    out: list[Finding] = []
    if restored_at is None:
        out.append(
            _finding(
                "PROC-1",
                Severity.WARNING,
                "Disconnection still open; the 2-hour threshold may not yet have elapsed.",
                started_at=started_at.isoformat(),
            )
        )
        return out
    duration = restored_at - started_at
    if duration <= DISCONNECT_THRESHOLD:
        return out
    deadline = started_at + DISCONNECT_NOTICE_DEADLINE
    if notified_at is None or notified_at > deadline:
        out.append(
            _finding(
                "PROC-1",
                Severity.VIOLATION,
                f"Disconnection of {duration} was not reported by the 3-hour deadline.",
                started_at=started_at.isoformat(),
                restored_at=restored_at.isoformat(),
                notified_at=notified_at.isoformat() if notified_at else None,
                deadline=deadline.isoformat(),
            )
        )
    return out


def check_outage_report(restored_at: datetime, csv_sent_at: datetime | None) -> Finding | None:
    """PROC-3"""
    if csv_sent_at is not None and csv_sent_at - restored_at <= OUTAGE_CSV_DEADLINE:
        return None
    return _finding(
        "PROC-3",
        Severity.VIOLATION,
        "Itemized CSV of dispensations during the outage is missing or late (24-hour limit).",
        restored_at=restored_at.isoformat(),
        csv_sent_at=csv_sent_at.isoformat() if csv_sent_at else None,
    )


def check_department_csv(requested_at: datetime, sent_at: datetime | None) -> Finding | None:
    """PROC-5"""
    if sent_at is not None and sent_at - requested_at <= DEPARTMENT_CSV_DEADLINE:
        return None
    return _finding(
        "PROC-5",
        Severity.VIOLATION,
        "Native CSV not produced within 48 hours of the department request.",
        requested_at=requested_at.isoformat(),
        sent_at=sent_at.isoformat() if sent_at else None,
    )


def check_access(role: str) -> Finding | None:
    """PROC-6"""
    if role in AUTHORIZED_ACCESS_ROLES:
        return None
    return _finding(
        "PROC-6",
        Severity.VIOLATION,
        f"Role '{role}' is not an authorized user of the internal STS.",
        role=role,
    )


def retention_floor(now: datetime) -> datetime:
    """PROC-5: the oldest record that may still exist."""
    return now - timedelta(days=RETENTION_DAYS)


# --- Unit conversion (PROC-7) ------------------------------------------------------


def grams_to_ounces(grams: Decimal | float | str) -> Decimal:
    """The department converts ounces to grams at 1 g = 0.0353 oz."""
    return Decimal(str(grams)) * OUNCE_IN_GRAMS


def ounces_to_grams(ounces: Decimal | float | str) -> Decimal:
    return Decimal(str(ounces)) / OUNCE_IN_GRAMS


# --- The integration plan pack (STS-3) ---------------------------------------------

INTEGRATION_PLAN_REQUIRED = (
    "contact_name_phone_email",
    "internal_sts_system_name",
    "milestone_uat_credentials",
    "milestone_integration_start",
    "milestone_integration_complete",
    "contingency_plan_while_disconnected",
    "contingency_plan_for_backfill_on_restore",
    "responsible_employees",
    "unique_product_id_inventory_form",
)


def missing_integration_plan_items(plan: dict) -> list[str]:
    """STS-3, plus the DH5058 inventory form required by 64-4.221(5)(a)."""
    return [k for k in INTEGRATION_PLAN_REQUIRED if not plan.get(k)]
