"""Drift: compare our record against the state's copy, and name which side is wrong.

The pain research is blunt about this one. Operators live with two ledgers, ours and
the state's, and when they disagree nobody can say which one moved:

    "these two don't sync at times and then it breaks. So you need to see where the
     drift happened and if Metrc is outdated or Dutchie is and then you can fix it."

So the product answer is a comparison, not a sync button. The comparison takes the two
snapshots, classifies every difference, and refuses to guess a winner without evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class Drift(str, Enum):
    MISSING_LOCALLY = "missing_locally"
    MISSING_AT_STATE = "missing_at_state"
    QUANTITY_MISMATCH = "quantity_mismatch"
    STATUS_MISMATCH = "status_mismatch"


@dataclass(frozen=True)
class DriftItem:
    kind: Drift
    key: str
    ours: dict = field(default_factory=dict)
    theirs: dict = field(default_factory=dict)
    note: str = ""

    @property
    def citation_hint(self) -> str:
        if self.kind is Drift.STATUS_MISMATCH:
            return "Rule 64-4.222(11): the record must state the location and status at all times"
        if self.kind is Drift.QUANTITY_MISMATCH:
            return "Rule 64-4.222(12): quantity changes need a cause or a justification"
        return "Rule 64-4.221(2): the internal system must stay integrated with the state system"


@dataclass(frozen=True)
class DriftReport:
    items: tuple[DriftItem, ...]
    ours_count: int
    theirs_count: int

    @property
    def clean(self) -> bool:
        return not self.items

    def by_kind(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for i in self.items:
            out[i.kind.value] = out.get(i.kind.value, 0) + 1
        return out

    def summary(self) -> str:
        if self.clean:
            return f"no drift ({self.ours_count} records on both sides)"
        parts = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in sorted(self.by_kind().items()))
        return f"{len(self.items)} differences: {parts}"


def _norm(records: dict) -> dict[str, dict]:
    """Accept either a dict of dicts or a dict of scalars."""
    out: dict[str, dict] = {}
    for k, v in records.items():
        out[str(k)] = v if isinstance(v, dict) else {"quantity": v}
    return out


def compare(ours: dict, theirs: dict, *, quantity_tolerance: Decimal | str = "0") -> DriftReport:
    """Classify every difference between the local record and the state snapshot.

    ``quantity_tolerance`` exists because unit conversion is not exact in either
    direction (Rule 64-4.222(6) fixes 1 g = 0.0353 oz); anything inside the tolerance is
    treated as agreement.
    """
    a, b = _norm(ours), _norm(theirs)
    tol = Decimal(str(quantity_tolerance))
    items: list[DriftItem] = []

    for key in sorted(set(a) | set(b)):
        if key not in b:
            items.append(
                DriftItem(Drift.MISSING_AT_STATE, key, ours=a[key], note="we hold a record the state does not have")
            )
            continue
        if key not in a:
            items.append(
                DriftItem(Drift.MISSING_LOCALLY, key, theirs=b[key], note="the state holds a record we do not have")
            )
            continue

        qa, qb = a[key].get("quantity"), b[key].get("quantity")
        if qa is not None and qb is not None:
            try:
                if abs(Decimal(str(qa)) - Decimal(str(qb))) > tol:
                    items.append(
                        DriftItem(
                            Drift.QUANTITY_MISMATCH,
                            key,
                            ours=a[key],
                            theirs=b[key],
                            note=f"quantity {qa} vs {qb}",
                        )
                    )
                    continue
            except Exception:
                pass

        sa, sb = a[key].get("status"), b[key].get("status")
        if sa is not None and sb is not None and sa != sb:
            items.append(
                DriftItem(Drift.STATUS_MISMATCH, key, ours=a[key], theirs=b[key], note=f"status {sa} vs {sb}")
            )

    return DriftReport(items=tuple(items), ours_count=len(a), theirs_count=len(b))
