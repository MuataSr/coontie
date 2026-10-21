"""Cultivation: batches, plants, moves, additives, harvests, disposals.

The shape follows ``docs/flows/cultivation.md``, which was written before this module. Every
record here maps to one DH5059 event, with the department's field names, so the export is a
projection rather than a translation.

Three rules are enforced rather than warned about, because the rule text is unambiguous:

* No cultivation record before integration is recorded (64-4.221(4)).
* No harvest without a schedule that covers exactly those plants (DH5059: "A harvest must be
  scheduled before the plants are harvested").
* No plant disposal inside 72 hours of scheduling it (``compliance.DISPOSAL_WAIT``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from .compliance import DISPOSAL_WAIT

PLANT_STATES = ("immature", "harvested", "disposed")
GROWING = ("immature",)


@dataclass(frozen=True)
class Batch:
    id: str
    facility_id: str
    room_id: str
    cultivar: str
    count: int
    mother_plant_id: str = ""
    created_at: datetime | None = None


@dataclass(frozen=True)
class Plant:
    id: str
    batch_id: str
    cultivar: str
    room_id: str
    is_mother: bool = False
    planted_at: datetime | None = None
    state: str = "immature"


@dataclass(frozen=True)
class Harvest:
    id: str
    room_id: str
    post_harvest_room_id: str
    plant_ids: tuple[str, ...]
    wet_weight: Decimal
    wet_unit: str
    waste_weight: Decimal
    waste_unit: str
    other_weight: Decimal
    other_unit: str
    scheduled_at: datetime | None = None
    harvested_at: datetime | None = None

    @property
    def scheduled(self) -> bool:
        return self.scheduled_at is not None

    @property
    def completed(self) -> bool:
        return self.harvested_at is not None

    @property
    def total_out(self) -> Decimal:
        return self.waste_weight + self.other_weight


@dataclass(frozen=True)
class Additive:
    id: str
    description: str
    amount: Decimal
    unit: str
    plant_ids: tuple[str, ...]
    applied_at: datetime


@dataclass(frozen=True)
class Disposal:
    id: str
    kind: str            # plants | matter | inventory
    subject: str         # plant ids, a weight, or an inventory id
    reason: str
    scheduled_at: datetime | None
    disposed_at: datetime | None
    weight: Decimal | None = None
    unit: str = ""

    @property
    def waits_until(self) -> datetime | None:
        return self.scheduled_at + DISPOSAL_WAIT if self.scheduled_at else None


# -- plant identifiers ---------------------------------------------------------


def plant_id(n: int) -> str:
    return f"PL-{n:04d}"


def parse_plants(text: str) -> tuple[str, ...]:
    """Accept ``PL-0001,PL-0002``, ``PL-0001..PL-0003``, or both, and stop guessing there."""
    ids: list[str] = []
    for chunk in re.split(r"[,\s]+", (text or "").strip()):
        if not chunk:
            continue
        if ".." in chunk:
            start, _, end = chunk.partition("..")
            a = _plant_number(start)
            b = _plant_number(end)
            if a is None or b is None or b < a:
                raise ValueError(f"cannot read the plant range {chunk!r}")
            ids.extend(plant_id(n) for n in range(a, b + 1))
        else:
            n = _plant_number(chunk)
            if n is None:
                raise ValueError(f"cannot read the plant id {chunk!r}; use PL-0001 or a range like PL-0001..PL-0003")
            ids.append(plant_id(n))
    if not ids:
        raise ValueError("no plants given")
    if len(set(ids)) != len(ids):
        raise ValueError("the same plant is listed twice")
    return tuple(ids)


def _plant_number(text: str) -> int | None:
    match = re.fullmatch(r"(?:PL-?)?0*(\d{1,6})", (text or "").strip(), flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


# -- validation ----------------------------------------------------------------


def amount(text) -> Decimal:
    cleaned = re.sub(r"[^0-9.\-]", "", str(text or ""))
    if cleaned in ("", "-", "."):
        raise ValueError(f"{text!r} is not a number")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"{text!r} is not a number") from exc


def require_growing(plants: dict[str, Plant], ids: tuple[str, ...]) -> None:
    missing = [i for i in ids if i not in plants]
    if missing:
        raise ValueError(f"unknown plant(s): {', '.join(missing)}")
    gone = [i for i in ids if plants[i].state not in GROWING]
    if gone:
        states = ", ".join(f"{i} is {plants[i].state}" for i in gone)
        raise ValueError(f"those plants are no longer growing: {states}")


def matching_schedule(harvests: list[Harvest], ids: tuple[str, ...]) -> Harvest | None:
    wanted = set(ids)
    for h in harvests:
        if h.completed:
            continue
        if h.scheduled and set(h.plant_ids) == wanted:
            return h
    return None


def describe_open_schedules(harvests: list[Harvest]) -> str:
    open_ones = [h for h in harvests if h.scheduled and not h.completed]
    if not open_ones:
        return "none"
    return "; ".join(f"{len(h.plant_ids)} plants ({h.plant_ids[0]}...{h.plant_ids[-1]})" for h in open_ones)


def require_disposal_wait(scheduled_at: datetime, at: datetime) -> None:
    if at - scheduled_at < DISPOSAL_WAIT:
        remaining = DISPOSAL_WAIT - (at - scheduled_at)
        hours = int(remaining.total_seconds() // 3600)
        raise ValueError(
            f"disposal must wait {DISPOSAL_WAIT} after scheduling; {hours}h remain "
            f"(scheduled {scheduled_at.isoformat()})"
        )


def check_harvest_weights(wet: Decimal, waste: Decimal, other: Decimal) -> None:
    if wet <= 0:
        raise ValueError("a harvest needs a wet flower weight greater than zero")
    if waste < 0 or other < 0:
        raise ValueError("weights cannot be negative")
    if waste + other > wet:
        raise ValueError(
            f"waste ({waste}) plus other material ({other}) exceeds the wet flower weight ({wet}); "
            "check the scales and the units"
        )


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
