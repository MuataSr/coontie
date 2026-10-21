"""The workspace: one SQLite file holding an MMTC's master data and its event ledger.

Design notes, deliberately boring:

* Master data (facility, rooms, products, lots) lives in plain tables so a human can
  read it with any SQLite browser under pressure.
* Every creation also appends to the hash-chained ledger, so the history exists even
  though the projections are plain rows. The projections are a convenience; the ledger
  is the record.
* One file per MMTC. No accounts, no cloud, no migration service. Copy the file, that
  is the backup.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from .compliance import DEPT_EMAIL

from .store import Ledger

if TYPE_CHECKING:  # pragma: no cover
    from .amendments import Amendment, Justification

SCHEMA = """
CREATE TABLE IF NOT EXISTS facilities (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    license_number TEXT NOT NULL,
    street        TEXT, city TEXT, state TEXT DEFAULT 'FL', zip TEXT,
    contact_name  TEXT, contact_phone TEXT, contact_email TEXT,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rooms (
    id            TEXT PRIMARY KEY,
    facility_id   TEXT NOT NULL REFERENCES facilities(id),
    kind          TEXT NOT NULL CHECK (kind IN ('grow','inventory')),
    name          TEXT NOT NULL,
    number        TEXT NOT NULL,
    is_quarantine INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    UNIQUE (facility_id, name, number)
);
CREATE TABLE IF NOT EXISTS products (
    id             TEXT PRIMARY KEY,
    facility_id    TEXT NOT NULL REFERENCES facilities(id),
    name           TEXT NOT NULL,
    brand          TEXT,
    product_type   TEXT NOT NULL,
    route          TEXT NOT NULL,
    is_delivery_device INTEGER NOT NULL DEFAULT 0,
    upid           TEXT NOT NULL,
    thc_mg         TEXT,
    cbd_mg         TEXT,
    weight_g       TEXT,
    size           TEXT,
    volume         TEXT,
    formulation    TEXT,
    cultivar       TEXT,
    flavor         TEXT,
    approval_date  TEXT,
    reference_number TEXT,
    created_at     TEXT NOT NULL,
    UNIQUE (facility_id, upid)
);
CREATE TABLE IF NOT EXISTS lots (
    id            TEXT PRIMARY KEY,
    product_id    TEXT NOT NULL REFERENCES products(id),
    room_id       TEXT NOT NULL REFERENCES rooms(id),
    quantity      TEXT NOT NULL,
    unit          TEXT NOT NULL,
    on_hold       INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS import_batches (
    id            TEXT PRIMARY KEY,
    source_file   TEXT NOT NULL,
    rows_total    INTEGER NOT NULL,
    rows_ok       INTEGER NOT NULL,
    rows_failed   INTEGER NOT NULL,
    mapping       TEXT,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS amendments (
    id            TEXT PRIMARY KEY,
    sequence      INTEGER NOT NULL,
    target_kind   TEXT NOT NULL,
    target_id     TEXT NOT NULL,
    field         TEXT NOT NULL,
    before_value  TEXT NOT NULL,
    after_value   TEXT NOT NULL,
    cause         TEXT NOT NULL,
    reason        TEXT NOT NULL,
    actor         TEXT NOT NULL DEFAULT '',
    occurred_at   TEXT NOT NULL,
    facility_id   TEXT NOT NULL DEFAULT '',
    unit          TEXT NOT NULL DEFAULT '',
    justification_id TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_amend_target ON amendments(target_id);
CREATE TABLE IF NOT EXISTS justifications (
    id            TEXT PRIMARY KEY,
    amendment_id  TEXT NOT NULL,
    subject       TEXT NOT NULL,
    body          TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    deadline      TEXT NOT NULL,
    sent_at       TEXT,
    recipient     TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Facility:
    id: str
    name: str
    license_number: str
    street: str = ""
    city: str = ""
    state: str = "FL"
    zip: str = ""
    contact_name: str = ""
    contact_phone: str = ""
    contact_email: str = ""


@dataclass(frozen=True)
class Room:
    id: str
    facility_id: str
    kind: str
    name: str
    number: str
    is_quarantine: bool = False


@dataclass(frozen=True)
class Product:
    id: str
    facility_id: str
    name: str
    product_type: str
    route: str
    upid: str
    is_delivery_device: bool = False
    brand: str = ""
    thc_mg: Decimal | None = None
    cbd_mg: Decimal | None = None
    weight_g: Decimal | None = None
    size: str = ""
    volume: str = ""
    formulation: str = ""
    cultivar: str = ""
    flavor: str = ""
    approval_date: date | None = None
    reference_number: str = ""


@dataclass(frozen=True)
class Lot:
    id: str
    product_id: str
    room_id: str
    quantity: Decimal
    unit: str
    on_hold: bool = False


class Workspace:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.ledger = Ledger(self.path)

    # -- setup ---------------------------------------------------------------

    def add_facility(self, facility: Facility) -> Facility:
        self.conn.execute(
            "INSERT INTO facilities (id,name,license_number,street,city,state,zip,contact_name,"
            "contact_phone,contact_email,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                facility.id, facility.name, facility.license_number, facility.street, facility.city,
                facility.state, facility.zip, facility.contact_name, facility.contact_phone,
                facility.contact_email, _now(),
            ),
        )
        self.conn.commit()
        self.ledger.append(
            "facility_registered",
            {"facility": facility.name, "license": facility.license_number},
            datetime.now(timezone.utc),
            facility_id=facility.id,
        )
        return facility

    def add_room(self, room: Room) -> Room:
        self.conn.execute(
            "INSERT INTO rooms (id,facility_id,kind,name,number,is_quarantine,created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (room.id, room.facility_id, room.kind, room.name, room.number, int(room.is_quarantine), _now()),
        )
        self.conn.commit()
        key = "grow_room_create" if room.kind == "grow" else "inventory_room_create"
        self.ledger.append(
            key,
            {
                "facility_location": room.facility_id,
                "room_name": room.name,
                "room_number": room.number,
                "is_quarantine": room.is_quarantine,
            },
            datetime.now(timezone.utc),
            facility_id=room.facility_id,
        )
        return room

    # -- products ------------------------------------------------------------

    def find_product(self, upid: str, facility_id: str | None = None) -> Product | None:
        sql = "SELECT * FROM products WHERE upid = ?"
        args: list = [upid]
        if facility_id:
            sql += " AND facility_id = ?"
            args.append(facility_id)
        row = self.conn.execute(sql, args).fetchone()
        return _product(row) if row else None

    def add_product(self, product: Product) -> tuple[Product, bool]:
        """Insert a product, or return the existing one with the same unique product ID.

        Returns (product, created). Reusing one ID for two different six-attribute keys
        is impossible here because the ID is derived from those attributes; a supplied
        SKU that collides with a different key is caught by the caller's key check.
        """
        existing = self.find_product(product.upid, product.facility_id)
        if existing:
            return existing, False
        self.conn.execute(
            "INSERT INTO products (id,facility_id,name,brand,product_type,route,is_delivery_device,upid,"
            "thc_mg,cbd_mg,weight_g,size,volume,formulation,cultivar,flavor,approval_date,"
            "reference_number,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                product.id, product.facility_id, product.name, product.brand, product.product_type,
                product.route, int(product.is_delivery_device), product.upid, _dec(product.thc_mg),
                _dec(product.cbd_mg), _dec(product.weight_g), product.size, product.volume,
                product.formulation, product.cultivar, product.flavor,
                product.approval_date.isoformat() if product.approval_date else None,
                product.reference_number, _now(),
            ),
        )
        self.conn.commit()
        self.ledger.append(
            "final_product",
            {
                "unique_product_id": product.upid,
                "approved_product_name": product.name,
                "product_type": product.product_type,
                "route_of_administration": product.route,
                "cultivar": product.cultivar,
                "facility_location": product.facility_id,
            },
            datetime.now(timezone.utc),
            facility_id=product.facility_id,
        )
        return product, True

    def add_lot(self, lot: Lot) -> Lot:
        self.conn.execute(
            "INSERT INTO lots (id,product_id,room_id,quantity,unit,on_hold,created_at) VALUES (?,?,?,?,?,?,?)",
            (lot.id, lot.product_id, lot.room_id, _dec(lot.quantity), lot.unit, int(lot.on_hold), _now()),
        )
        self.conn.commit()
        self.ledger.append(
            "inventory_lot_create",
            {
                "inventory": lot.product_id,
                "lot_id": lot.id,
                "weight_or_volume": str(lot.quantity),
                "unit": lot.unit,
                "room": lot.room_id,
            },
            datetime.now(timezone.utc),
        )
        return lot

    # -- corrections (S2) ----------------------------------------------------

    def amend_lot(
        self,
        lot_id: str,
        *,
        new_quantity: Decimal | str | None = None,
        new_on_hold: bool | None = None,
        cause: str,
        reason: str,
        actor: str = "",
        when: datetime | None = None,
    ) -> Amendment:
        """Change a lot's quantity or hold status without losing the prior value."""
        from .amendments import Amendment, new_id, validate_cause

        validate_cause(cause)
        if new_quantity is None and new_on_hold is None:
            raise ValueError("nothing to amend: give a new quantity or a hold state")
        row = self.conn.execute("SELECT * FROM lots WHERE id = ?", (lot_id,)).fetchone()
        if not row:
            raise ValueError(f"no lot {lot_id!r} in this workspace")
        product = self.conn.execute("SELECT * FROM products WHERE id = ?", (row["product_id"],)).fetchone()
        facility_id = product["facility_id"] if product else ""

        when = when or datetime.now(timezone.utc)
        sequence = int(
            self.conn.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM amendments WHERE target_id = ?", (lot_id,)).fetchone()[0]
        )

        amendment_id = new_id("amd")
        if new_quantity is not None:
            field, before, after = "quantity", row["quantity"], str(Decimal(str(new_quantity)))
            if Decimal(before) == Decimal(after):
                raise ValueError("new quantity is the same as the recorded quantity")
            self.conn.execute("UPDATE lots SET quantity = ? WHERE id = ?", (after, lot_id))
        else:
            field, before, after = "on_hold", str(int(row["on_hold"])), str(int(bool(new_on_hold)))
            if before == after:
                raise ValueError("hold state is already what was asked for")
            self.conn.execute("UPDATE lots SET on_hold = ? WHERE id = ?", (after, lot_id))
        self.conn.commit()

        amendment = Amendment(
            id=amendment_id,
            target_kind="lot",
            target_id=lot_id,
            field=field,
            before=before,
            after=after,
            cause=cause,
            reason=reason,
            actor=actor,
            occurred_at=when,
            facility_id=facility_id,
            unit=row["unit"],
            sequence=sequence,
        )
        self.conn.execute(
            "INSERT INTO amendments (id,sequence,target_kind,target_id,field,before_value,after_value,"
            "cause,reason,actor,occurred_at,facility_id,unit,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                amendment.id, sequence, amendment.target_kind, amendment.target_id, field, before, after,
                cause, reason, actor, when.isoformat(), facility_id, row["unit"], _now(),
            ),
        )
        self.conn.commit()
        self.ledger.append(
            "inventory_adjustment",
            {
                "inventory": lot_id,
                "adjustment_type": field,
                "reason": reason,
                "removed_weight_or_volume": str(amendment.delta),
                "unit": row["unit"],
                "facility_location": facility_id,
                "cause": cause,
            },
            when,
            facility_id=facility_id or None,
        )
        return amendment

    def create_justification(self, amendment_id: str, extra: str = "") -> "Justification":
        """Draft the 64-4.222(12) notice for a non-exempt amendment. Nothing is sent."""
        from .amendments import draft_text, new_id

        amendment = self._amendment_row(amendment_id)
        if amendment is None:
            raise ValueError(f"no amendment {amendment_id!r}")
        if amendment.exempt:
            raise ValueError(f"cause {amendment.cause!r} is exempt from the written justification")
        lot = self.conn.execute("SELECT * FROM lots WHERE id = ?", (amendment.target_id,)).fetchone()
        product = self.conn.execute("SELECT * FROM products WHERE id = ?", (lot["product_id"],)).fetchone() if lot else None
        facility = self.facility()
        subject, body = draft_text(
            amendment,
            mmtc_name=facility.name if facility else "",
            license_number=facility.license_number if facility else "",
            product_name=product["name"] if product else "",
            upid=product["upid"] if product else "",
            extra=extra,
        )
        jid = new_id("jst")
        self.conn.execute(
            "INSERT INTO justifications (id,amendment_id,subject,body,created_at,deadline,recipient)"
            " VALUES (?,?,?,?,?,?,?)",
            (jid, amendment_id, subject, body, _now(), amendment.deadline.isoformat(), DEPT_EMAIL),
        )
        self.conn.execute("UPDATE amendments SET justification_id = ? WHERE id = ?", (jid, amendment_id))
        self.conn.commit()
        return self._justification_row(jid)

    def mark_justification_sent(self, justification_id: str, when: datetime | None = None):
        when = when or datetime.now(timezone.utc)
        cur = self.conn.execute("UPDATE justifications SET sent_at = ? WHERE id = ?", (when.isoformat(), justification_id))
        if cur.rowcount == 0:
            raise ValueError(f"no justification {justification_id!r}")
        self.conn.commit()
        return self._justification_row(justification_id)

    def amendments(self, target_id: str | None = None) -> list:
        sql = "SELECT * FROM amendments"
        args: tuple = ()
        if target_id:
            sql += " WHERE target_id = ?"
            args = (target_id,)
        sql += " ORDER BY occurred_at, sequence"
        return [self._amendment_from_row(r) for r in self.conn.execute(sql, args)]

    def justifications(self, pending_only: bool = False) -> list:
        sql = "SELECT * FROM justifications"
        if pending_only:
            sql += " WHERE sent_at IS NULL"
        sql += " ORDER BY deadline"
        return [self._justification_from_row(r) for r in self.conn.execute(sql)]

    def journal(self, target_id: str) -> list[dict]:
        """Everything that ever happened to one record, oldest first."""
        entries: list[dict] = []
        for e in self.ledger.entries():
            payload = e.payload or {}
            if target_id in (payload.get("inventory"), payload.get("inventory_lot")) or payload.get("lot_id") == target_id:
                entries.append({"when": e.occurred_at, "kind": e.event_key, "detail": payload, "hash": e.hash})
            elif e.event_key == "inventory_adjustment" and payload.get("inventory") == target_id:
                entries.append({"when": e.occurred_at, "kind": e.event_key, "detail": payload, "hash": e.hash})
        for a in self.amendments(target_id):
            entries.append(
                {
                    "when": a.occurred_at.isoformat(),
                    "kind": "amendment",
                    "detail": {
                        "field": a.field,
                        "before": a.before,
                        "after": a.after,
                        "cause": a.cause,
                        "reason": a.reason,
                        "justification": a.justification_id,
                    },
                    "hash": a.id,
                }
            )
        return sorted(entries, key=lambda x: x["when"])

    def pending_amendments(self) -> list:
        return [a for a in self.amendments() if a.requires_justification and not a.justification_id]

    def adjustment_views(self) -> list:
        """Amendments with their justification timestamp attached, ready for guardrails."""
        from dataclasses import replace

        sent = {j.amendment_id: j.sent_at for j in self.justifications()}
        return [replace(a, justification_sent_at=sent.get(a.id)) for a in self.amendments()]

    def _amendment_row(self, amendment_id: str):
        row = self.conn.execute("SELECT * FROM amendments WHERE id = ?", (amendment_id,)).fetchone()
        return self._amendment_from_row(row) if row else None

    def _amendment_from_row(self, row):
        from .amendments import Amendment

        return Amendment(
            id=row["id"], target_kind=row["target_kind"], target_id=row["target_id"], field=row["field"],
            before=row["before_value"], after=row["after_value"], cause=row["cause"], reason=row["reason"],
            actor=row["actor"], occurred_at=datetime.fromisoformat(row["occurred_at"]),
            facility_id=row["facility_id"], unit=row["unit"], justification_id=row["justification_id"],
            sequence=row["sequence"],
        )

    def _justification_row(self, jid: str):
        row = self.conn.execute("SELECT * FROM justifications WHERE id = ?", (jid,)).fetchone()
        return self._justification_from_row(row) if row else None

    def _justification_from_row(self, row):
        from .amendments import Justification

        return Justification(
            id=row["id"], amendment_id=row["amendment_id"], subject=row["subject"], body=row["body"],
            created_at=datetime.fromisoformat(row["created_at"]), deadline=datetime.fromisoformat(row["deadline"]),
            sent_at=datetime.fromisoformat(row["sent_at"]) if row["sent_at"] else None, recipient=row["recipient"],
        )

    # -- reads ---------------------------------------------------------------

    def facility(self) -> Facility | None:
        row = self.conn.execute("SELECT * FROM facilities ORDER BY created_at LIMIT 1").fetchone()
        return _facility(row) if row else None

    def rooms(self) -> list[Room]:
        return [_room(r) for r in self.conn.execute("SELECT * FROM rooms ORDER BY name, number")]

    def products(self) -> list[Product]:
        return [
            _product(r)
            for r in self.conn.execute("SELECT * FROM products ORDER BY product_type, name, upid")
        ]

    def lots(self) -> list[Lot]:
        return [_lot(r) for r in self.conn.execute("SELECT * FROM lots ORDER BY created_at")]

    def inventory(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT p.name AS product, p.upid AS upid, p.product_type AS type, l.quantity AS quantity,"
            " l.unit AS unit, r.name AS room, r.number AS room_number, l.on_hold AS on_hold"
            " FROM lots l JOIN products p ON p.id = l.product_id JOIN rooms r ON r.id = l.room_id"
            " ORDER BY p.name, r.name"
        )
        return [dict(r) for r in rows]

    def verify(self) -> tuple[bool, str]:
        ok, reason = self.ledger.verify_chain()
        counts = {
            "facilities": self._count("facilities"),
            "rooms": self._count("rooms"),
            "products": self._count("products"),
            "lots": self._count("lots"),
            "events": self._count("events"),
        }
        summary = ", ".join(f"{v} {k}" for k, v in counts.items())
        return ok, f"{reason} ({summary})"

    def _count(self, table: str) -> int:
        return int(self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def close(self) -> None:
        self.ledger.close()
        self.conn.close()


# -- row mapping ---------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dec(value) -> str | None:
    if value is None or value == "":
        return None
    return str(Decimal(str(value)))


def _facility(r) -> Facility:
    return Facility(
        id=r["id"], name=r["name"], license_number=r["license_number"], street=r["street"] or "",
        city=r["city"] or "", state=r["state"] or "FL", zip=r["zip"] or "",
        contact_name=r["contact_name"] or "", contact_phone=r["contact_phone"] or "",
        contact_email=r["contact_email"] or "",
    )


def _room(r) -> Room:
    return Room(
        id=r["id"], facility_id=r["facility_id"], kind=r["kind"], name=r["name"],
        number=r["number"], is_quarantine=bool(r["is_quarantine"]),
    )


def _product(r) -> Product:
    return Product(
        id=r["id"], facility_id=r["facility_id"], name=r["name"], brand=r["brand"] or "",
        product_type=r["product_type"], route=r["route"], upid=r["upid"],
        is_delivery_device=bool(r["is_delivery_device"]),
        thc_mg=_maybe_dec(r["thc_mg"]), cbd_mg=_maybe_dec(r["cbd_mg"]), weight_g=_maybe_dec(r["weight_g"]),
        size=r["size"] or "", volume=r["volume"] or "", formulation=r["formulation"] or "",
        cultivar=r["cultivar"] or "", flavor=r["flavor"] or "",
        approval_date=date.fromisoformat(r["approval_date"]) if r["approval_date"] else None,
        reference_number=r["reference_number"] or "",
    )


def _lot(r) -> Lot:
    return Lot(
        id=r["id"], product_id=r["product_id"], room_id=r["room_id"],
        quantity=Decimal(r["quantity"]), unit=r["unit"], on_hold=bool(r["on_hold"]),
    )


def _maybe_dec(v):
    return Decimal(v) if v is not None else None
