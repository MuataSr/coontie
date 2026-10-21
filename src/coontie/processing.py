"""Processing: cure, lots, splits, conversions, ingredients, samples, final products.

One idea holds this module together: **weight is conserved**. Every removal is a move, a move
cannot exceed what the lot still holds, and a conversion cannot produce more than it removed.
The department's catalog asks for those numbers; this module refuses to let them disagree.

The other hard rule is one sentence of the catalog: the expiration date is *immutable once
recorded*. So there is no command that changes one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

# The catalog's own examples for inventory_type, plus the ones processing produces.
INVENTORY_TYPES = (
    "cured and dried flower",
    "dried flower",
    "wet flower",
    "whole flower",
    "extract",
    "concentrate",
    "edible",
    "topical",
    "tincture",
    "vape",
    "capsule/tablet",
)

# From the department's published approved-integrator list. Not enforced: a CMTL's trade name
# and its license identity are not the same string, so this only produces a note.
KNOWN_CMTLS = (
    "acs laboratory",
    "terplife",
    "modern canna",
    "method labs",
    "accuscience",
    "us cannalytics",
    "kaycha labs",
    "act lab",
    "confident",
)


@dataclass(frozen=True)
class StockLot:
    id: str
    kind: str
    cultivar: str
    room_id: str
    original: Decimal
    unit: str
    harvest_ids: tuple[str, ...] = ()
    source_lot_id: str = ""
    created_at: datetime | None = None

    @property
    def label(self) -> str:
        return f"{self.original} {self.unit} {self.kind} {self.cultivar}".strip()


@dataclass(frozen=True)
class Cure:
    id: str
    harvest_id: str
    plant_ids: tuple[str, ...]
    post_weight: Decimal
    post_unit: str
    waste_weight: Decimal
    waste_unit: str
    room_id: str
    cured_at: datetime


@dataclass(frozen=True)
class LabSample:
    id: str
    source_lot_id: str
    weight: Decimal
    unit: str
    cmtl_id: str
    is_rnd: bool
    at: datetime
    note: str = ""


@dataclass(frozen=True)
class FinalProduct:
    id: str
    lot_id: str
    upid: str
    product_type: str
    cultivar: str
    unit_count: int
    net_weight: Decimal
    unit: str
    weight_per_unit: Decimal | None
    approved_name: str
    packaged_at: datetime
    expiration_date: date
    room_id: str


@dataclass(frozen=True)
class Device:
    id: str
    upid: str
    inventory_type: str
    unit_count: int
    room_id: str
    at: datetime


# -- arithmetic ----------------------------------------------------------------


def amount(text) -> Decimal:
    cleaned = re.sub(r"[^0-9.\-]", "", str(text or ""))
    if cleaned in ("", "-", "."):
        raise ValueError(f"{text!r} is not a number")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"{text!r} is not a number") from exc


def remaining(original: Decimal, moves: list[Decimal]) -> Decimal:
    return original - sum(moves, Decimal("0"))


def check_removal(lot: StockLot, currently: Decimal, wanted: Decimal) -> None:
    if wanted <= 0:
        raise ValueError("the amount removed must be greater than zero")
    if wanted > currently:
        raise ValueError(
            f"{lot.id} holds {currently} {lot.unit} and {wanted} {lot.unit} was asked for; "
            "a lot cannot give up more than it holds"
        )


def check_conversion(removed: Decimal, resulting: Decimal, waste: Decimal) -> None:
    if resulting < 0 or waste < 0:
        raise ValueError("weights cannot be negative")
    if resulting + waste > removed:
        raise ValueError(
            f"the result ({resulting}) plus waste ({waste}) exceeds the {removed} removed; "
            "check the scales before recording this conversion"
        )


def check_expiration(packaged_at: datetime, expiration: date) -> None:
    if expiration <= packaged_at.date():
        raise ValueError(
            f"expiration {expiration.isoformat()} is not after the packaging date "
            f"{packaged_at.date().isoformat()}"
        )


def expiration_conflict(existing: FinalProduct | None, requested: date) -> str | None:
    """The catalog says the expiration is immutable once recorded. This is that sentence."""
    if existing is None:
        return None
    if existing.expiration_date != requested:
        return (
            f"final product {existing.upid} was recorded with expiration "
            f"{existing.expiration_date.isoformat()}; the expiration date is immutable once recorded "
            f"(DH5059, Final Product Inventory), so it cannot become {requested.isoformat()}"
        )
    return None


def cmtl_note(cmtl_id: str) -> str:
    key = (cmtl_id or "").strip().lower()
    if any(known in key for known in KNOWN_CMTLS):
        return ""
    return f"note: {cmtl_id!r} is not one of the laboratory names on the department's approved list; record the license identity as it appears there"


def parse_csv_list(text: str) -> list[str]:
    return [part.strip() for part in (text or "").split(",") if part.strip()]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
