"""Import an incumbent's export into a Coontie workspace.

The gate for S1 is "an operator's export becomes a working record, with no manual SQL",
so this module is deliberately forgiving about column names and strict about values:

* Headers are matched by alias, case-insensitively, ignoring punctuation, so
  "THC (mg)", "Tetrahydrocannabinol (THC) Weight" and "thc_mg" all land in the same field.
* A row that cannot be understood is reported with its line number and a reason. It
  never aborts the batch.
* ``dry_run`` reads and reports without writing a single row.
* A product that already exists under the same unique product ID is reused, not
  duplicated. That is Rule 64-4.221(1)(c) doing its job.
"""

from __future__ import annotations

import csv
import re
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .products import upid_for, validate_product_row
from .workspace import Lot, Product, Workspace

FIELDS = (
    "mmtc_name", "product_name", "product_type", "route", "delivery_device", "brand", "upid",
    "thc_mg", "cbd_mg", "weight_g", "size", "volume", "formulation", "cultivar", "flavor",
    "approval_date", "reference_number", "quantity", "unit", "room",
)

ALIASES: dict[str, tuple[str, ...]] = {
    "mmtc_name": ("mmtc name", "licensee", "facility", "company", "store"),
    "product_name": ("product name", "product", "item", "item name", "name", "description"),
    "product_type": ("product type", "type", "category", "product category"),
    "route": ("route of administration", "route", "administration"),
    "delivery_device": ("marijuana delivery device", "delivery device", "device", "hardware"),
    "brand": ("product brand", "brand", "label"),
    "upid": ("unique product id", "unique id", "upid", "sku", "product id"),
    "thc_mg": ("tetrahydrocannabinol (thc) weight", "thc weight", "thc mg", "thc_mg", "thc", "thc%", "thc percent"),
    "cbd_mg": ("cannabidiol (cbd) weight", "cbd weight", "cbd mg", "cbd_mg", "cbd", "cbd%", "cbd percent"),
    "weight_g": ("product weight", "net weight", "weight", "weight (g)", "size (g)", "grams"),
    "size": ("size", "net weight", "weight"),
    "volume": ("volume", "ml", "volume (ml)"),
    "formulation": ("product formulation", "formulation", "potency", "cannabinoids per serving"),
    "cultivar": ("cultivar or strain name", "cultivar", "strain", "variety"),
    "flavor": ("flavor name", "flavour", "flavor"),
    "approval_date": ("approval date", "approved", "approved date", "approval_date"),
    "reference_number": ("reference number", "reference", "approval letter", "ref"),
    "quantity": ("quantity", "qty", "on hand", "on_hand", "stock", "units"),
    "unit": ("unit", "uom", "unit of measure"),
    "room": ("room", "location", "area", "storage area"),
}

_TRUE = {"yes", "y", "true", "1", "device"}


@dataclass
class ImportReport:
    source: str
    rows_total: int = 0
    rows_ok: int = 0
    rows_failed: int = 0
    products_created: int = 0
    products_reused: int = 0
    lots_created: int = 0
    mapping: dict[str, str] = field(default_factory=dict)
    unmapped: list[str] = field(default_factory=list)
    errors: list[tuple[int, str]] = field(default_factory=list)
    dry_run: bool = False
    batch_id: str = ""

    def summary(self) -> str:
        verb = "would import" if self.dry_run else "imported"
        return (
            f"{verb} {self.rows_ok}/{self.rows_total} rows "
            f"({self.products_created} new products, {self.products_reused} reused, "
            f"{self.lots_created} lots), {self.rows_failed} failed"
        )


def _norm(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (h or "").strip().lower()).strip()


def map_headers(headers: list[str]) -> tuple[dict[str, str], list[str]]:
    """Return {canonical field: original header} plus any headers nobody claimed."""
    norm = {h: _norm(h) for h in headers}
    mapping: dict[str, str] = {}
    for field_name, aliases in ALIASES.items():
        for header, n in norm.items():
            if n in aliases and field_name not in mapping:
                mapping[field_name] = header
                break
    claimed = set(mapping.values())
    return mapping, [h for h in headers if h not in claimed]


def _get(row: dict, mapping: dict, name: str) -> str:
    header = mapping.get(name)
    if not header:
        return ""
    return (row.get(header) or "").strip()


def _decimal(text: str, field_name: str) -> Decimal | None:
    if text == "":
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if cleaned in ("", "-", "."):
        raise ValueError(f"{field_name} {text!r} is not a number")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} {text!r} is not a number") from exc


def _date(text: str) -> date | None:
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            from datetime import datetime

            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    raise ValueError(f"approval date {text!r} is not yyyy-mm-dd or mm/dd/yyyy")


def import_csv(
    workspace: Workspace,
    path: str | Path,
    *,
    facility_id: str,
    default_room_id: str | None = None,
    dry_run: bool = False,
) -> ImportReport:
    path = Path(path)
    report = ImportReport(source=str(path), dry_run=dry_run, batch_id=uuid.uuid4().hex[:12])

    with path.open(newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        headers = list(reader.fieldnames or [])
        mapping, unmapped = map_headers(headers)
        report.mapping = mapping
        report.unmapped = unmapped

        for line_no, row in enumerate(reader, start=2):
            report.rows_total += 1
            try:
                product = _row_to_product(row, mapping, facility_id)
            except ValueError as exc:
                report.rows_failed += 1
                report.errors.append((line_no, str(exc)))
                continue

            existing = workspace.find_product(product.upid, facility_id)
            if existing:
                product = existing

            quantity_text = _get(row, mapping, "quantity")
            lot = None
            if quantity_text:
                try:
                    qty = _decimal(quantity_text, "quantity")
                except ValueError as exc:
                    report.rows_failed += 1
                    report.errors.append((line_no, str(exc)))
                    continue
                if qty is None:
                    report.rows_failed += 1
                    report.errors.append((line_no, "quantity could not be read"))
                    continue
                unit = _get(row, mapping, "unit") or "g"
                room_id = _resolve_room(workspace, _get(row, mapping, "room"), default_room_id)
                if room_id is None:
                    report.rows_failed += 1
                    report.errors.append((line_no, "quantity given but no room could be resolved"))
                    continue
                lot = Lot(id=f"lot-{uuid.uuid4().hex[:10]}", product_id=product.id, room_id=room_id, quantity=qty, unit=unit)

            if not dry_run:
                product, created = workspace.add_product(product)
                if created:
                    report.products_created += 1
                else:
                    report.products_reused += 1
                if lot:
                    lot = Lot(id=lot.id, product_id=product.id, room_id=lot.room_id, quantity=lot.quantity, unit=lot.unit)
                    workspace.add_lot(lot)
                    report.lots_created += 1
            else:
                if existing:
                    report.products_reused += 1
                else:
                    report.products_created += 1
                if lot:
                    report.lots_created += 1

            report.rows_ok += 1

    if not dry_run:
        workspace.conn.execute(
            "INSERT INTO import_batches (id,source_file,rows_total,rows_ok,rows_failed,mapping,created_at)"
            " VALUES (?,?,?,?,?,?,datetime('now'))",
            (
                report.batch_id, report.source, report.rows_total, report.rows_ok, report.rows_failed,
                ",".join(sorted(report.mapping)),
            ),
        )
        workspace.conn.commit()
    return report


def _row_to_product(row: dict, mapping: dict, facility_id: str) -> Product:
    name = _get(row, mapping, "product_name")
    if not name:
        raise ValueError("no product name")
    raw_type = _get(row, mapping, "product_type")
    if not raw_type:
        raise ValueError("no product type")
    product_type, route = validate_product_row(product_type=raw_type, route=_get(row, mapping, "route") or _infer_route(raw_type))
    device = _get(row, mapping, "delivery_device").lower() in _TRUE or product_type == "Marijuana Delivery Device"

    thc = _decimal(_get(row, mapping, "thc_mg"), "thc")
    cbd = _decimal(_get(row, mapping, "cbd_mg"), "cbd")
    weight = _decimal(_get(row, mapping, "weight_g"), "weight")
    size = _get(row, mapping, "size") or (str(weight) if weight is not None else "")
    volume = _get(row, mapping, "volume")
    cultivar = _get(row, mapping, "cultivar")
    flavor = _get(row, mapping, "flavor")
    supplied = _get(row, mapping, "upid")

    upid, _key = upid_for(
        cultivar=cultivar, size=size, volume=volume, flavor=flavor,
        thc_mg=thc or 0, cbd_mg=cbd or 0, route=route, supplied_sku=supplied,
    )

    return Product(
        id=f"prod-{uuid.uuid4().hex[:10]}",
        facility_id=facility_id,
        name=name,
        brand=_get(row, mapping, "brand"),
        product_type=product_type,
        route=route,
        upid=upid,
        is_delivery_device=device,
        thc_mg=thc,
        cbd_mg=cbd,
        weight_g=weight,
        size=size,
        volume=volume,
        formulation=_get(row, mapping, "formulation"),
        cultivar=cultivar,
        flavor=flavor,
        approval_date=_date(_get(row, mapping, "approval_date")),
        reference_number=_get(row, mapping, "reference_number"),
    )


_ROUTE_BY_TYPE = {
    "Whole Flower": "Smoking",
    "Ground Whole Flower": "Smoking",
    "Pre-rolled marijuana cigarette": "Smoking",
    "Vape": "Inhalation",
    "Concentrate": "Inhalation",
    "Capsule/Tablet": "Oral",
    "Tincture": "Sublingual",
    "Topical": "Topical",
    "Suppository": "Suppository",
    "Gelatin": "Edible",
    "Chocolate": "Edible",
    "Baked Good": "Edible",
    "Lozenge": "Oral",
    "Drink Powder": "Oral",
    "Marijuana Delivery Device": "Inhalation",
}


def _infer_route(product_type: str) -> str:
    return _ROUTE_BY_TYPE.get(product_type, "")


def _resolve_room(workspace: Workspace, name: str, default_room_id: str | None) -> str | None:
    if name:
        for room in workspace.rooms():
            if name.lower() in (room.name.lower(), room.number.lower(), f"{room.name} {room.number}".lower()):
                return room.id
    if default_room_id:
        return default_room_id
    rooms = [r for r in workspace.rooms() if r.kind == "inventory"]
    return rooms[0].id if rooms else None
