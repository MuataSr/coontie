"""Transport: vehicles, manifests, and the two ends of a transfer.

The manifest is not our invention. Rule 64-4.222(10) requires the internal system to generate
it, and s. 381.986(8)(g), F.S. lists what it must contain. This module enforces that list in
the write path, refuses the two conditions the statute forbids outright (one person in a
vehicle, an out-of-service vehicle), and renders the printable page a driver carries.

Statute text fetched 2026-10-21 from ``flsenate.gov/Laws/Statutes/2025/381.986``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

MIN_CREW = 2  # s. 381.986(8)(g)5.: at least two persons in a vehicle transporting marijuana

# The seven items in s. 381.986(8)(g)1.a-g, in the statute's order and with its letters.
# The renderer emits every one of these labels, and a test asserts it.
REQUIRED_ITEMS = (
    ("a", "Departure date and approximate time of departure"),
    ("b", "Name, location address, and license number of the originating MMTC"),
    ("c", "Name and address of the recipient of the delivery"),
    ("d", "Quantity and form of marijuana or delivery device transported"),
    ("e", "Arrival date and estimated time of arrival"),
    ("f", "Delivery vehicle make, model, and license plate number"),
    ("g", "Name and signature of the employees delivering the product"),
)


@dataclass(frozen=True)
class Vehicle:
    id: str
    name: str
    vin: str
    plate: str
    make: str
    model: str
    year: str
    color: str
    in_service: bool = True

    @property
    def description(self) -> str:
        return f"{self.year} {self.make} {self.model}".strip()


@dataclass(frozen=True)
class ManifestItem:
    lot_id: str
    quantity: Decimal
    unit: str
    form: str


@dataclass(frozen=True)
class Manifest:
    id: str
    facility_id: str
    recipient_name: str
    recipient_address: str
    vehicle_id: str
    employee_ids: tuple[str, ...]
    departure_at: datetime
    arrival_at: datetime
    route: str = ""
    stops: tuple[str, ...] = ()
    invoice_id: str = ""
    status: str = "built"          # built -> dispatched -> received
    created_at: datetime | None = None


def amount(text) -> Decimal:
    cleaned = re.sub(r"[^0-9.\-]", "", str(text or ""))
    if cleaned in ("", "-", "."):
        raise ValueError(f"{text!r} is not a number")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"{text!r} is not a number") from exc


def validate_manifest(
    *,
    recipient_name: str,
    recipient_address: str,
    vehicle: Vehicle | None,
    employee_ids: tuple[str, ...],
    departure_at: datetime | None,
    arrival_at: datetime | None,
    items: list[ManifestItem],
) -> None:
    """Refuse anything the statute forbids, in the statute's terms."""
    problems: list[str] = []
    if not (recipient_name or "").strip():
        problems.append("the recipient's name is required (s. 381.986(8)(g)1.c.)")
    if not (recipient_address or "").strip():
        problems.append("the recipient's address is required (s. 381.986(8)(g)1.c.)")
    if vehicle is None:
        problems.append("a registered vehicle is required (s. 381.986(8)(g)1.f.)")
    elif not vehicle.in_service:
        problems.append(
            f"vehicle {vehicle.name} is out of service; only vehicles in good working order may be used "
            "(s. 381.986(8)(g)2.)"
        )
    crew = [e for e in employee_ids if (e or "").strip()]
    if len(crew) < MIN_CREW:
        problems.append(
            f"at least two employees must be named, {len(crew)} given "
            "(s. 381.986(8)(g)5.: at least two persons must be in a vehicle transporting marijuana)"
        )
    if departure_at is None:
        problems.append("the departure date and time are required (s. 381.986(8)(g)1.a.)")
    if arrival_at is None:
        problems.append("the estimated arrival date and time are required (s. 381.986(8)(g)1.e.)")
    if departure_at and arrival_at and arrival_at < departure_at:
        problems.append("the estimated arrival cannot precede the departure")
    if not items:
        problems.append("a manifest needs at least one item (s. 381.986(8)(g)1.d.)")
    for item in items:
        if item.quantity <= 0:
            problems.append(f"{item.lot_id} has a quantity of {item.quantity}; it must be greater than zero")
    if problems:
        raise ValueError("; ".join(problems))


def _stamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def render_manifest(
    manifest: Manifest,
    *,
    facility_name: str,
    facility_address: str,
    license_number: str,
    vehicle: Vehicle,
    items: list[tuple[ManifestItem, str]],
    crew: tuple[str, ...],
) -> str:
    """The printable page. One copy per recipient, retained three years."""
    lines = [
        "MARIJUANA TRANSPORTATION MANIFEST",
        "Generated from the internal seed-to-sale tracking system,",
        "as required by Rule 64-4.222(10), F.A.C. and s. 381.986(8)(g), F.S.",
        "",
        f"Manifest: {manifest.id}",
        "",
        f"(a) Departure date and approximate time of departure: {_stamp(manifest.departure_at)}",
        f"(e) Arrival date and estimated time of arrival:      {_stamp(manifest.arrival_at)}",
        "",
        "(b) Originating medical marijuana treatment center",
        f"    Name:           {facility_name}",
        f"    Location:       {facility_address}",
        f"    License number: {license_number}",
        "",
        "(c) Recipient of the delivery",
        f"    Name:    {manifest.recipient_name}",
        f"    Address: {manifest.recipient_address}",
        "",
        "(f) Delivery vehicle",
        f"    Make and model: {vehicle.description}",
        f"    License plate:  {vehicle.plate}",
        f"    Vehicle name:   {vehicle.name}",
        "",
        "(d) Quantity and form being transported",
    ]
    total = Decimal("0")
    for item, label in items:
        lines.append(f"    {label}")
        lines.append(f"        {item.quantity} {item.unit}  ({item.form})   lot {item.lot_id}")
        total += item.quantity
    lines.append(f"    Total: {total}")
    if manifest.stops:
        lines += ["", "Intended stops, in order"]
        for i, stop in enumerate(manifest.stops, start=1):
            lines.append(f"    {i}. {stop}")
    if manifest.route:
        lines += ["", "Route directions", f"    {manifest.route}"]
    if manifest.invoice_id:
        lines += ["", f"Wholesale invoice: {manifest.invoice_id}"]

    lines += [
        "",
        "(g) Employees delivering the product",
    ]
    for i, name in enumerate(crew, start=1):
        lines.append(f"    {i}. {name}    signature: ______________________________")
    lines += [
        "",
        "Received by",
        "    Name: ______________________________",
        "    Signature: _________________________    Date and time: ____________________",
        "",
        "A copy of this manifest is provided to each recipient, who signs this copy acknowledging",
        "receipt. The transporting employee presents this manifest and an employee identification",
        "card to a law enforcement officer on request. Copies are retained for at least three years.",
        "(s. 381.986(8)(g)1.(I), (II), (III), F.S.)",
    ]
    return "\n".join(lines) + "\n"


def parse_crew(text: str) -> tuple[str, ...]:
    """Crew names as a comma or semicolon separated list. Two is the statutory minimum."""
    parts = [p.strip() for p in re.split(r"[,;]+", text or "") if p.strip()]
    return tuple(parts)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
