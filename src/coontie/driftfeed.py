"""Reading the department's copy of the inventory into something comparable.

Nobody publishes a schema for the export the department's system hands back, so this
module is deliberately alias-driven and total: it accepts the column names operators
actually get, refuses to guess a value it does not recognise, and keeps the raw row so a
human can look at what arrived.

Two normalisations happen here, and nowhere else:

* **Status.**  "Active", "ACTIVE", "on hold", "Quarantine" all mean something specific to
  us: ``active``, ``on_hold``, ``sold``, ``inactive``. An unrecognised status is passed
  through lowercased rather than silently matched.
* **Quantity and unit.**  Quantities are converted to a common base (grams for mass,
  millilitres for volume, units for counts) before comparison, using the conversion in
  :mod:`coontie.compliance`, so the rule's 1 g = 0.0353 oz is applied in one place.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .compliance import ounces_to_grams

ID_ALIASES = ("inventory id", "inventory identification number", "inventory number", "sts inventory id",
              "department inventory id", "item id", "inventory")
QUANTITY_ALIASES = ("quantity", "qty", "on hand", "on_hand", "weight", "amount", "balance")
UNIT_ALIASES = ("unit", "uom", "unit of measure", "units")
STATUS_ALIASES = ("status", "state", "hold status", "inventory status")
ROOM_ALIASES = ("room", "location", "area", "storage area", "room name")
PRODUCT_ALIASES = ("product", "product name", "item name", "name", "description")

STATUS_MAP = {
    "active": "active",
    "a": "active",
    "available": "active",
    "on hand": "active",
    "on hold": "on_hold",
    "onhold": "on_hold",
    "hold": "on_hold",
    "held": "on_hold",
    "quarantine": "on_hold",
    "quarantined": "on_hold",
    "sold": "sold",
    "dispensed": "sold",
    "depleted": "sold",
    "inactive": "inactive",
    "void": "inactive",
}

UNIT_MAP = {
    "g": "g", "gram": "g", "grams": "g", "gm": "g", "gr": "g",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "mg": "mg", "milligram": "mg", "milligrams": "mg",
    "ml": "ml", "milliliter": "ml", "millilitre": "ml",
    "unit": "units", "units": "units", "ea": "units", "each": "units", "ct": "units",
}

MASS = {"g", "oz", "mg"}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").strip().lower()).strip()


def normalise_status(text: str) -> str:
    key = _norm(text)
    return STATUS_MAP.get(key, key)


def normalise_unit(text: str) -> str:
    key = _norm(text)
    return UNIT_MAP.get(key, key or "units")


def to_base(quantity, unit: str) -> tuple[Decimal, str]:
    """Convert a quantity to grams, millilitres, or units."""
    amount = Decimal(str(quantity))
    unit = normalise_unit(unit)
    if unit == "oz":
        return ounces_to_grams(amount), "g"
    if unit == "mg":
        return amount / Decimal("1000"), "g"
    if unit in ("g", "ml", "units"):
        return amount, unit
    return amount, unit


@dataclass(frozen=True)
class StateRow:
    sts_inventory_id: str
    product: str
    quantity: Decimal
    unit: str
    status: str
    room: str
    raw: dict


@dataclass(frozen=True)
class ParsedState:
    rows: tuple[StateRow, ...]
    mapping: dict
    unmapped: tuple[str, ...]
    rejected: tuple[tuple[int, str], ...]


def _pick(headers: list[str], aliases: tuple[str, ...]) -> str | None:
    normalised = {h: _norm(h) for h in headers}
    for alias in aliases:
        for header, n in normalised.items():
            if n == alias:
                return header
    return None


def parse_state_export(text: str) -> ParsedState:
    """Read the department's CSV. Every row either parses or is reported with its line."""
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = list(reader.fieldnames or [])
    id_col = _pick(headers, ID_ALIASES)
    qty_col = _pick(headers, QUANTITY_ALIASES)
    unit_col = _pick(headers, UNIT_ALIASES)
    status_col = _pick(headers, STATUS_ALIASES)
    room_col = _pick(headers, ROOM_ALIASES)
    product_col = _pick(headers, PRODUCT_ALIASES)

    mapping = {
        "sts_inventory_id": id_col, "quantity": qty_col, "unit": unit_col,
        "status": status_col, "room": room_col, "product": product_col,
    }
    used = {c for c in mapping.values() if c}
    unmapped = tuple(h for h in headers if h not in used)

    rows: list[StateRow] = []
    rejected: list[tuple[int, str]] = []
    if not id_col:
        return ParsedState(rows=(), mapping=mapping, unmapped=unmapped,
                           rejected=((1, "no inventory id column found"),))

    for line_no, row in enumerate(reader, start=2):
        raw_id = (row.get(id_col) or "").strip()
        if not raw_id:
            rejected.append((line_no, "no inventory id"))
            continue
        qty_text = (row.get(qty_col) or "").strip() if qty_col else ""
        quantity = Decimal("0")
        if qty_text:
            cleaned = re.sub(r"[^0-9.\-]", "", qty_text)
            try:
                quantity = Decimal(cleaned)
            except (InvalidOperation, ValueError):
                rejected.append((line_no, f"quantity {qty_text!r} is not a number"))
                continue
        unit = normalise_unit((row.get(unit_col) or "") if unit_col else "")
        rows.append(
            StateRow(
                sts_inventory_id=raw_id,
                product=(row.get(product_col) or "").strip() if product_col else "",
                quantity=quantity,
                unit=unit,
                status=normalise_status((row.get(status_col) or "") if status_col else ""),
                room=(row.get(room_col) or "").strip() if room_col else "",
                raw={k: (v or "") for k, v in row.items() if k},
            )
        )
    return ParsedState(rows=tuple(rows), mapping=mapping, unmapped=unmapped, rejected=tuple(rejected))
