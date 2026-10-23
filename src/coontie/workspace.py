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

import uuid
import json
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
    from .cultivation import Additive, Batch, Disposal, Harvest, Plant
    from .outage import Outage
    from .processing import Cure, Device, FinalProduct, LabSample, StockLot
    from .transport import Manifest, Vehicle

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
CREATE TABLE IF NOT EXISTS outages (
    id                TEXT PRIMARY KEY,
    facility_id       TEXT NOT NULL DEFAULT '',
    started_at        TEXT NOT NULL,
    restored_at       TEXT,
    notice_subject    TEXT NOT NULL DEFAULT '',
    notice_body       TEXT NOT NULL DEFAULT '',
    notice_created_at TEXT,
    notice_sent_at    TEXT,
    notice_breach_at  TEXT,
    restore_subject   TEXT NOT NULL DEFAULT '',
    restore_body      TEXT NOT NULL DEFAULT '',
    restore_created_at TEXT,
    restore_sent_at   TEXT,
    report_csv        TEXT NOT NULL DEFAULT '',
    report_path       TEXT NOT NULL DEFAULT '',
    report_rows       INTEGER NOT NULL DEFAULT 0,
    report_created_at TEXT,
    report_sent_at    TEXT,
    report_breach_at  TEXT,
    created_at        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dispensations (
    id            TEXT PRIMARY KEY,
    facility_id   TEXT NOT NULL DEFAULT '',
    dispensed_at  TEXT NOT NULL,
    patient_id    TEXT NOT NULL,
    inventory_id  TEXT NOT NULL,
    weight        TEXT NOT NULL,
    unit          TEXT NOT NULL DEFAULT 'g',
    location      TEXT NOT NULL DEFAULT '',
    sale_id       TEXT NOT NULL DEFAULT '',
    mmur_verified INTEGER NOT NULL DEFAULT 0,
    outage_id     TEXT,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS state_snapshots (
    id          TEXT PRIMARY KEY,
    source_file TEXT NOT NULL DEFAULT '',
    as_of       TEXT NOT NULL,
    rows        INTEGER NOT NULL DEFAULT 0,
    rejected    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS state_inventory (
    snapshot_id       TEXT NOT NULL,
    sts_inventory_id  TEXT NOT NULL,
    product           TEXT NOT NULL DEFAULT '',
    quantity          TEXT NOT NULL DEFAULT '0',
    unit              TEXT NOT NULL DEFAULT 'units',
    status            TEXT NOT NULL DEFAULT '',
    room              TEXT NOT NULL DEFAULT '',
    raw               TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (snapshot_id, sts_inventory_id)
);
CREATE TABLE IF NOT EXISTS drift_findings (
    id             TEXT PRIMARY KEY,
    snapshot_id    TEXT NOT NULL,
    kind           TEXT NOT NULL,
    record_key     TEXT NOT NULL,
    ours           TEXT NOT NULL DEFAULT '',
    theirs         TEXT NOT NULL DEFAULT '',
    note           TEXT NOT NULL DEFAULT '',
    resolution     TEXT,
    resolution_note TEXT NOT NULL DEFAULT '',
    resolved_at    TEXT,
    created_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS integration (
    id          TEXT PRIMARY KEY,
    approved_on TEXT NOT NULL,
    reference   TEXT NOT NULL DEFAULT '',
    note        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS batches (
    id              TEXT PRIMARY KEY,
    facility_id     TEXT NOT NULL,
    room_id         TEXT NOT NULL,
    cultivar        TEXT NOT NULL,
    count           INTEGER NOT NULL,
    mother_plant_id TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plants (
    id         TEXT PRIMARY KEY,
    batch_id   TEXT NOT NULL,
    cultivar   TEXT NOT NULL,
    room_id    TEXT NOT NULL,
    is_mother  INTEGER NOT NULL DEFAULT 0,
    planted_at TEXT NOT NULL,
    state      TEXT NOT NULL DEFAULT 'immature',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS harvests (
    id                   TEXT PRIMARY KEY,
    room_id              TEXT NOT NULL,
    post_harvest_room_id TEXT NOT NULL,
    plant_ids            TEXT NOT NULL,
    wet_weight           TEXT NOT NULL,
    wet_unit             TEXT NOT NULL,
    waste_weight         TEXT NOT NULL,
    waste_unit           TEXT NOT NULL,
    other_weight         TEXT NOT NULL,
    other_unit           TEXT NOT NULL,
    scheduled_at         TEXT,
    harvested_at         TEXT,
    created_at           TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS additives (
    id          TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    amount      TEXT NOT NULL,
    unit        TEXT NOT NULL,
    plant_ids   TEXT NOT NULL,
    applied_at  TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS disposals (
    id           TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,
    subject      TEXT NOT NULL,
    reason       TEXT NOT NULL DEFAULT '',
    scheduled_at TEXT,
    disposed_at  TEXT,
    weight       TEXT,
    unit         TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL
);
-- A paired tablet is a terminal. `devices` already means a DH5059 delivery device
-- (upid, inventory_type, unit_count), so the two must never share a name.
CREATE TABLE IF NOT EXISTS terminals (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    code_verifier  TEXT NOT NULL DEFAULT '',
    code_expires_at TEXT,
    token_verifier TEXT NOT NULL DEFAULT '',
    added_by       TEXT NOT NULL DEFAULT '',
    added_at       TEXT NOT NULL,
    paired_at      TEXT,
    last_seen_at   TEXT,
    revoked_at     TEXT
);
CREATE TABLE IF NOT EXISTS transmissions (
    id               TEXT PRIMARY KEY,
    envelope_path    TEXT NOT NULL,
    envelope_sha256  TEXT NOT NULL,
    first_seq        INTEGER NOT NULL,
    last_seq         INTEGER NOT NULL,
    events           INTEGER NOT NULL,
    state            TEXT NOT NULL DEFAULT 'packaged',
    adapter          TEXT NOT NULL DEFAULT '',
    result           TEXT NOT NULL DEFAULT '',
    reference        TEXT NOT NULL DEFAULT '',
    attempt_at       TEXT,
    created_at       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    set_by     TEXT NOT NULL DEFAULT '',
    set_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS employees (
    id            TEXT PRIMARY KEY,
    full_name     TEXT NOT NULL,
    date_of_birth TEXT NOT NULL,
    hire_date     TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_users (
    id          TEXT PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    permissions TEXT NOT NULL,
    verifier    TEXT NOT NULL,
    kdf         TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cures (
    id            TEXT PRIMARY KEY,
    harvest_id    TEXT NOT NULL,
    plant_ids     TEXT NOT NULL,
    post_weight   TEXT NOT NULL,
    post_unit     TEXT NOT NULL,
    waste_weight  TEXT NOT NULL,
    waste_unit    TEXT NOT NULL,
    room_id       TEXT NOT NULL,
    cured_at      TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stock_lots (
    id            TEXT PRIMARY KEY,
    kind          TEXT NOT NULL,
    cultivar      TEXT NOT NULL DEFAULT '',
    room_id       TEXT NOT NULL,
    original      TEXT NOT NULL,
    unit          TEXT NOT NULL DEFAULT 'g',
    harvest_ids   TEXT NOT NULL DEFAULT '[]',
    source_lot_id TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stock_moves (
    id            TEXT PRIMARY KEY,
    lot_id        TEXT NOT NULL,
    kind          TEXT NOT NULL,
    amount        TEXT NOT NULL,
    unit          TEXT NOT NULL,
    target_lot_id TEXT NOT NULL DEFAULT '',
    note          TEXT NOT NULL DEFAULT '',
    at            TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lab_samples (
    id            TEXT PRIMARY KEY,
    source_lot_id TEXT NOT NULL,
    weight        TEXT NOT NULL,
    unit          TEXT NOT NULL,
    cmtl_id       TEXT NOT NULL,
    is_rnd        INTEGER NOT NULL DEFAULT 0,
    at            TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS final_products (
    id               TEXT PRIMARY KEY,
    lot_id           TEXT NOT NULL,
    upid             TEXT NOT NULL,
    product_type     TEXT NOT NULL,
    cultivar         TEXT NOT NULL DEFAULT '',
    unit_count       INTEGER NOT NULL DEFAULT 0,
    net_weight       TEXT NOT NULL,
    unit             TEXT NOT NULL,
    weight_per_unit  TEXT,
    approved_name    TEXT NOT NULL DEFAULT '',
    packaged_at      TEXT NOT NULL,
    expiration_date  TEXT NOT NULL,
    room_id          TEXT NOT NULL,
    created_at       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
    id             TEXT PRIMARY KEY,
    upid           TEXT NOT NULL DEFAULT '',
    inventory_type TEXT NOT NULL,
    unit_count     INTEGER NOT NULL,
    room_id        TEXT NOT NULL,
    at             TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vehicles (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    vin        TEXT NOT NULL DEFAULT '',
    plate      TEXT NOT NULL DEFAULT '',
    make       TEXT NOT NULL DEFAULT '',
    model      TEXT NOT NULL DEFAULT '',
    year       TEXT NOT NULL DEFAULT '',
    color      TEXT NOT NULL DEFAULT '',
    in_service INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS manifests (
    id                TEXT PRIMARY KEY,
    facility_id       TEXT NOT NULL,
    recipient_name    TEXT NOT NULL,
    recipient_address TEXT NOT NULL,
    vehicle_id        TEXT NOT NULL,
    employee_ids      TEXT NOT NULL,
    departure_at      TEXT NOT NULL,
    arrival_at        TEXT NOT NULL,
    route             TEXT NOT NULL DEFAULT '',
    stops             TEXT NOT NULL DEFAULT '[]',
    invoice_id        TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'built',
    artifact_path     TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS manifest_items (
    id          TEXT PRIMARY KEY,
    manifest_id TEXT NOT NULL,
    lot_id      TEXT NOT NULL,
    quantity    TEXT NOT NULL,
    unit        TEXT NOT NULL,
    form        TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS transfers (
    id            TEXT PRIMARY KEY,
    manifest_id   TEXT NOT NULL,
    direction     TEXT NOT NULL,
    facility_id   TEXT NOT NULL DEFAULT '',
    at            TEXT NOT NULL,
    receiver_name TEXT NOT NULL DEFAULT '',
    detail        TEXT NOT NULL DEFAULT '[]',
    created_at    TEXT NOT NULL
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
        self.conn = sqlite3.connect(self.path, timeout=10)
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._migrate()
        self.ledger = Ledger(self.path)

    def _migrate(self) -> None:
        """Additive migrations only: an operator's file is never rebuilt underneath them."""
        columns = {r[1] for r in self.conn.execute("PRAGMA table_info(lots)")}
        if "sts_inventory_id" not in columns:
            self.conn.execute("ALTER TABLE lots ADD COLUMN sts_inventory_id TEXT")
        self.conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_lots_sts ON lots(sts_inventory_id)"
            " WHERE sts_inventory_id IS NOT NULL"
        )
        self.conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_findings_key ON drift_findings(snapshot_id, kind, record_key)"
        )
        self.conn.commit()

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
            # The DH5058 catalogue registration, not the DH5059 inventory event of the same
            # concept: registering a product type is not producing a final product. The
            # catalog's `final_product` key is reserved for the processing module.
            "product_catalogue_add",
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

    def _product_type(self, product_id: str) -> str:
        row = self.conn.execute("SELECT product_type FROM products WHERE id = ?", (product_id,)).fetchone()
        return row["product_type"] if row else ""

    def _product_cultivar(self, product_id: str) -> str:
        row = self.conn.execute("SELECT cultivar FROM products WHERE id = ?", (product_id,)).fetchone()
        return row["cultivar"] if row else ""

    def _product_facility(self, product_id: str) -> str:
        row = self.conn.execute("SELECT facility_id FROM products WHERE id = ?", (product_id,)).fetchone()
        return row["facility_id"] if row else ""

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
                "inventory_type": self._product_type(lot.product_id),
                "cultivar": self._product_cultivar(lot.product_id),
                "facility_location": self._product_facility(lot.product_id),
                "room": lot.room_id,
                "harvest_batch_ids": [],
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
                # same shape as adjust_stock: the catalogue requires inventory_id, and a product lot
                # has a department id when it was linked, so say which id was written
                "inventory_id": self._department_id(lot_id) or lot_id,
                "inventory_id_source": "department" if self._department_id(lot_id) else "local",
                "inventory_reference": lot_id,
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
        # Rule 64-4.222(12): a non-exempt correction drafts the written notice. adjust_stock always
        # did this; amend_lot did not, so a product-lot correction silently skipped the notice.
        if amendment.exempt:
            return amendment
        self.create_justification(amendment.id)
        return amendment

    def create_justification(self, amendment_id: str, extra: str = "") -> "Justification":
        """Draft the 64-4.222(12) notice for a non-exempt amendment. Nothing is sent."""
        from .amendments import draft_text, new_id

        amendment = self._amendment_row(amendment_id)
        if amendment is None:
            raise ValueError(f"no amendment {amendment_id!r}")
        existing = self.conn.execute(
            "SELECT id FROM justifications WHERE amendment_id = ? ORDER BY created_at", (amendment_id,)
        ).fetchone()
        if existing:
            # One correction, one notice. Callers that draft for themselves get the same one back.
            return self._justification_row(existing["id"])
        if amendment.exempt:
            raise ValueError(f"cause {amendment.cause!r} is exempt from the written justification")
        lot = self.conn.execute("SELECT * FROM lots WHERE id = ?", (amendment.target_id,)).fetchone()
        if lot:
            product = self.conn.execute("SELECT * FROM products WHERE id = ?", (lot["product_id"],)).fetchone()
            product_name = product["name"] if product else ""
            upid = product["upid"] if product else ""
        else:
            stock = self.conn.execute("SELECT * FROM stock_lots WHERE id = ?", (amendment.target_id,)).fetchone()
            product_name = f"{stock['kind']} {stock['cultivar']}".strip() if stock else ""
            upid = ""
        facility = self.facility()
        subject, body = draft_text(
            amendment,
            mmtc_name=facility.name if facility else "",
            license_number=facility.license_number if facility else "",
            product_name=product_name,
            upid=upid,
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

    # -- appearance: one look and one voice, recorded rather than toggled ------

    def appearance(self) -> dict:
        """The installed look and voice. Defaults when nothing has been chosen."""
        from . import theme

        found = {r["key"]: r["value"] for r in self.conn.execute("SELECT key,value FROM settings")}
        look = found.get("look", theme.DEFAULT_SKIN)
        voice = found.get("voice", theme.DEFAULT_VOICE)
        if look not in theme.SKINS:
            look = theme.DEFAULT_SKIN
        if voice not in theme.VALID_VOICES:
            voice = theme.DEFAULT_VOICE
        row = self.conn.execute(
            "SELECT set_by, set_at FROM settings WHERE key = 'look'").fetchone()
        return {"look": look, "voice": voice,
                "set_by": (row["set_by"] if row else ""),
                "set_at": (row["set_at"] if row else "")}

    def set_appearance(self, *, look: str, voice: str, actor: str = "",
                       at: datetime | None = None) -> dict:
        """Choose the look and voice for this install, and write the choice to the record."""
        from . import theme

        if look not in theme.SKINS:
            raise ValueError(f"no skin called {look!r}; the skins are {', '.join(sorted(theme.SKINS))}")
        if voice not in theme.VALID_VOICES:
            raise ValueError(f"no voice called {voice!r}; the voices are "
                             f"{', '.join(theme.VALID_VOICES)}")
        problems = theme.check_skin(look, theme.SKINS[look])
        if voice in theme.VOICES:
            problems += theme.check_voice(voice, theme.VOICES[voice])
        if problems:
            raise ValueError("that choice does not pass its own check: " + "; ".join(problems))
        at = at or datetime.now(timezone.utc)
        who = (actor or "").strip()
        self.conn.execute(
            "INSERT INTO settings (key,value,set_by,set_at) VALUES ('look',?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value, set_by=excluded.set_by,"
            " set_at=excluded.set_at", (look, who, at.isoformat()))
        self.conn.execute(
            "INSERT INTO settings (key,value,set_by,set_at) VALUES ('voice',?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value, set_by=excluded.set_by,"
            " set_at=excluded.set_at", (voice, who, at.isoformat()))
        self.conn.commit()
        self.ledger.append("appearance_chosen",
                           {"look": look, "voice": voice, "set_by": who}, at)
        return self.appearance()

    # -- people (DH5059 admin events) ----------------------------------------

    def add_employee(
        self,
        *,
        full_name: str,
        date_of_birth,
        hire_date,
        email: str,
        at: datetime | None = None,
    ) -> "Employee":
        from . import people
        from .outage import new_id

        name = people.check_name(full_name)
        born = people.check_date(date_of_birth, field="date of birth")
        hired = people.check_hire_date(hire_date)
        mail = people.check_email(email, who="an employee's email")
        if born >= hired:
            raise ValueError(
                f"{name}: date of birth {born.isoformat()} is not before the hire date "
                f"{hired.isoformat()}"
            )
        if self.conn.execute("SELECT 1 FROM employees WHERE email = ?", (mail,)).fetchone():
            raise ValueError(f"{mail} is already an employee on this record; a second record for "
                             "one person is how a manifest names a stranger")
        at = at or datetime.now(timezone.utc)
        employee = people.Employee(
            id=new_id("emp"), full_name=name, date_of_birth=born, hire_date=hired, email=mail,
        )
        self.conn.execute(
            "INSERT INTO employees (id,full_name,date_of_birth,hire_date,email,active,created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (employee.id, name, born.isoformat(), hired.isoformat(), mail, 1, _now()),
        )
        self.conn.commit()
        self.ledger.append(
            "employee_record",
            {
                "full_name": name, "dob": born.isoformat(), "hire_date": hired.isoformat(),
                "email": mail, "employee_id": employee.id,
            },
            at,
        )
        return employee

    def employees(self) -> list:
        from . import people

        return [
            people.Employee(
                id=r["id"], full_name=r["full_name"],
                date_of_birth=date.fromisoformat(r["date_of_birth"]),
                hire_date=date.fromisoformat(r["hire_date"]), email=r["email"],
                active=bool(r["active"]),
            )
            for r in self.conn.execute("SELECT * FROM employees ORDER BY full_name")
        ]

    def add_api_user(
        self,
        *,
        email: str,
        password: str,
        permissions,
        at: datetime | None = None,
    ) -> "ApiUser":
        """Record an API user. The password is derived into a verifier and then forgotten."""
        from . import people
        from .outage import new_id

        mail = people.check_email(email, who="an API user's email")
        scope = people.check_permissions(permissions)
        if self.conn.execute("SELECT 1 FROM api_users WHERE email = ?", (mail,)).fetchone():
            raise ValueError(f"{mail} is already an API user on this record")
        verifier, encoded = people.derive_verifier(password)
        at = at or datetime.now(timezone.utc)
        user = people.ApiUser(
            id=new_id("api"), email=mail, permissions=scope, verifier=verifier,
            kdf=f"pbkdf2_sha256${people.PBKDF2_ITERATIONS}",
        )
        self.conn.execute(
            "INSERT INTO api_users (id,email,permissions,verifier,kdf,created_at)"
            " VALUES (?,?,?,?,?,?)",
            (user.id, mail, ", ".join(scope), encoded, user.kdf, _now()),
        )
        self.conn.commit()
        self.ledger.append(
            "api_user",
            {
                "email": mail,
                "permissions": list(scope),
                # the catalogue asks for the password; this record holds a verifier instead, because
                # the ledger can never forget what it is given. See docs/flows/facility-records.md.
                "password_verifier": verifier,
                "password_kdf": user.kdf,
                "password_note": "verifier only; the plaintext is not stored",
                "api_user_id": user.id,
            },
            at,
        )
        return user

    def api_users(self) -> list:
        from . import people

        return [
            people.ApiUser(
                id=r["id"], email=r["email"],
                permissions=tuple(p.strip() for p in r["permissions"].split(",") if p.strip()),
                verifier=r["verifier"], kdf=r["kdf"],
            )
            for r in self.conn.execute("SELECT * FROM api_users ORDER BY email")
        ]

    # -- inventory moves and disposal ---------------------------------------

    def move_inventory(self, lot_ref: str, to_room: str, *, note: str = "",
                       at: datetime | None = None) -> "Lot":
        """Move a product lot between rooms. A hold stops the move, not just the paperwork."""
        lot = self.lot(lot_ref)
        target = self._room_ref(to_room)
        if lot.room_id == target.id:
            raise ValueError(
                f"lot {lot.id} is already in {target.name}; a move to where it sits records nothing"
            )
        if lot.on_hold:
            raise ValueError(
                f"lot {lot.id} is on hold; a held lot does not move. Release the hold with its cause "
                f"first (coontie amend --lot {lot.id} --release --cause ...)"
            )
        if Decimal(str(lot.quantity)) <= 0:
            raise ValueError(f"lot {lot.id} holds no quantity; there is nothing to move")
        at = at or datetime.now(timezone.utc)
        origin = lot.room_id
        self.conn.execute("UPDATE lots SET room_id = ? WHERE id = ?", (target.id, lot.id))
        self.conn.commit()
        self.ledger.append(
            "inventory_move",
            {
                "facility_location": origin,
                "inventory_ids": [lot.id],
                "to_room": target.id,
                "quantity": str(lot.quantity), "unit": lot.unit,
                "note": note.strip(),
            },
            at,
            facility_id=self._product_facility(lot.product_id),
        )
        return self.lot(lot.id)

    def schedule_disposal_lot(self, lot_ref: str, *, reason: str,
                              at: datetime | None = None) -> "Disposal":
        from .cultivation import Disposal, utcnow
        from .outage import new_id
        lot = self.lot(lot_ref)
        if not (reason or "").strip():
            raise ValueError("a disposal schedule needs a reason")
        if Decimal(str(lot.quantity)) <= 0:
            raise ValueError(f"lot {lot.id} holds no quantity; there is nothing to destroy")
        open_schedule = [
            d for d in self.disposals()
            if d.kind == "inventory" and d.disposed_at is None and d.subject == lot.id
        ]
        if open_schedule:
            raise ValueError(
                f"lot {lot.id} is already scheduled for destruction ({open_schedule[0].id}, "
                f"reason {open_schedule[0].reason!r}); one schedule, then the wait"
            )
        at = at or utcnow()
        disposal = Disposal(
            id=new_id("dsp"), kind="inventory", subject=lot.id, reason=reason.strip(),
            scheduled_at=at, disposed_at=None, weight=Decimal(str(lot.quantity)), unit=lot.unit,
        )
        self.conn.execute(
            "INSERT INTO disposals (id,kind,subject,reason,scheduled_at,disposed_at,weight,unit,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (disposal.id, disposal.kind, disposal.subject, disposal.reason, at.isoformat(), None,
             str(disposal.weight), disposal.unit, _now()),
        )
        self.conn.commit()
        self.ledger.append(
            "disposal_schedule_inventory",
            {"inventory_id": lot.id, "reason": disposal.reason, "disposal_id": disposal.id},
            at,
            facility_id=self._product_facility(lot.product_id),
        )
        return disposal

    def dispose_lot(self, lot_ref: str, *, at: datetime | None = None) -> "Disposal":
        """Destroy a scheduled lot. The row stays and its quantity goes to zero."""
        from .cultivation import require_disposal_wait, utcnow
        lot = self.lot(lot_ref)
        match = None
        for d in self.disposals():
            if d.kind == "inventory" and d.disposed_at is None and d.subject == lot.id:
                match = d
                break
        if match is None:
            raise ValueError(
                f"lot {lot.id} has no destruction scheduled; DH5059 asks for the schedule first "
                f"(coontie dispose --schedule-lot {lot.id} --reason ...)"
            )
        at = at or utcnow()
        require_disposal_wait(match.scheduled_at, at)
        destroyed = Decimal(str(lot.quantity))
        self.conn.execute("UPDATE disposals SET disposed_at = ? WHERE id = ?", (at.isoformat(), match.id))
        self.conn.execute("UPDATE lots SET quantity = '0' WHERE id = ?", (lot.id,))
        self.conn.commit()
        self.ledger.append(
            "disposal_inventory",
            {
                "inventory_id": lot.id, "disposal_id": match.id,
                "reason": match.reason, "weight": str(destroyed), "unit": lot.unit,
            },
            at,
            facility_id=self._product_facility(lot.product_id),
        )
        return [d for d in self.disposals() if d.id == match.id][0]


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
            if target_id in (payload.get("inventory_id"), payload.get("inventory"),
                             payload.get("inventory_reference"),
                             payload.get("inventory_lot")) or payload.get("lot_id") == target_id:
                entries.append({"when": e.occurred_at, "kind": e.event_key, "detail": payload, "hash": e.hash})
            elif e.event_key == "inventory_adjustment" and target_id in (
                    payload.get("inventory_id"), payload.get("inventory"),
                    payload.get("inventory_reference")):
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

    # -- disconnections (S3) -------------------------------------------------

    def start_outage(self, when: datetime | None = None) -> "Outage":
        from .outage import Outage, new_id

        when = (when or datetime.now(timezone.utc)).astimezone(timezone.utc)
        existing = self.open_outage()
        if existing:
            raise ValueError(f"an outage is already open ({existing.id}); restore it first")
        facility = self.facility()
        outage = Outage(id=new_id("out"), facility_id=facility.id if facility else "", started_at=when)
        self.conn.execute(
            "INSERT INTO outages (id,facility_id,started_at,created_at) VALUES (?,?,?,?)",
            (outage.id, outage.facility_id, when.isoformat(), _now()),
        )
        self.conn.commit()
        self.ledger.append(
            "disconnect_start",
            {"outage": outage.id, "facility_location": outage.facility_id, "started_at": when.isoformat()},
            when,
            facility_id=outage.facility_id or None,
        )
        return outage

    def restore_outage(self, outage_id: str | None = None, when: datetime | None = None) -> "Outage":
        """Close the outage. The restoration notice and the outage CSV are generated at once."""
        from .outage import new_id  # noqa: F401  (kept for symmetry with start_outage)

        outage = self.outage(outage_id) if outage_id else self.open_outage()
        if outage is None:
            raise ValueError("no outage to restore")
        if not outage.open:
            raise ValueError(f"outage {outage.id} was already restored")
        when = (when or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if when < outage.started_at:
            raise ValueError("restoration cannot precede the disconnection")
        self.conn.execute("UPDATE outages SET restored_at = ? WHERE id = ?", (when.isoformat(), outage.id))
        self.conn.commit()
        self.ledger.append(
            "disconnect_restored",
            {"outage": outage.id, "restored_at": when.isoformat(), "duration_minutes": int((when - outage.started_at).total_seconds() // 60)},
            when,
            facility_id=outage.facility_id or None,
        )
        self.watch(now=when)
        return self.outage(outage.id)

    def record_dispensation(
        self,
        *,
        patient_id: str,
        inventory_id: str,
        weight,
        unit: str = "g",
        location: str = "",
        when: datetime | None = None,
        mmur_verified: bool = False,
        sale_id: str = "",
    ) -> dict:
        """Record one dispensation, and refuse it if an outage is open without MMUR verification.

        Rule 64-4.222(2)(a): during a disconnection, dispensing requires verifiable active
        status, current physician certification and remaining supply in the MMUR. If the
        registry is unavailable, do not dispense. This is the one place the rule is
        enforced rather than warned about.
        """
        when = (when or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if not patient_id:
            raise ValueError("a dispensation needs the patient's MMUR number")
        if not inventory_id:
            raise ValueError("a dispensation needs the department seed-to-sale inventory identification number")
        outage = self.open_outage(at=when)
        if outage and not mmur_verified:
            raise ValueError(
                f"outage {outage.id} is open: dispensing requires MMUR verification of active status, "
                "current physician certification and remaining supply (Rule 64-4.222(2)(a)); "
                "if the registry is unavailable, do not dispense"
            )
        if not location:
            facility = self.facility()
            location = facility.name if facility else ""
        rid = f"dsp-{uuid.uuid4().hex[:10]}"
        self.conn.execute(
            "INSERT INTO dispensations (id,facility_id,dispensed_at,patient_id,inventory_id,weight,unit,"
            "location,sale_id,mmur_verified,outage_id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                rid, outage.facility_id if outage else "", when.isoformat(), patient_id, inventory_id,
                str(Decimal(str(weight))), unit, location, sale_id, int(bool(mmur_verified)),
                outage.id if outage else None, _now(),
            ),
        )
        self.conn.commit()
        self.ledger.append(
            "dispensation",
            {
                "sale_id": sale_id or rid,
                "item_id": inventory_id,
                "patient_mmurnumber": patient_id,
                "unit_count": str(Decimal(str(weight))),
                "unit": unit,
                "dispensing_facility_location": location,
                "mmur_verified": bool(mmur_verified),
                "during_outage": outage.id if outage else None,
            },
            when,
            facility_id=(outage.facility_id if outage else None),
        )
        return {
            "id": rid, "dispensed_at": when, "patient_id": patient_id, "inventory_id": inventory_id,
            "weight": str(Decimal(str(weight))), "unit": unit, "location": location,
            "mmur_verified": bool(mmur_verified), "outage_id": outage.id if outage else None,
        }

    def outages(self) -> list:
        rows = self.conn.execute("SELECT * FROM outages ORDER BY started_at")
        return [self._outage_from_row(r) for r in rows]

    def outage(self, outage_id: str):
        row = self.conn.execute("SELECT * FROM outages WHERE id = ?", (outage_id,)).fetchone()
        return self._outage_from_row(row) if row else None

    def open_outage(self, at: datetime | None = None):
        for o in self.outages():
            if o.open:
                return o
        return None

    def dispensations(self, outage_id: str | None = None) -> list[dict]:
        if outage_id:
            outage = self.outage(outage_id)
            if not outage:
                raise ValueError(f"no outage {outage_id!r}")
            end = outage.restored_at or datetime.now(timezone.utc)
            rows = self.conn.execute(
                "SELECT * FROM dispensations WHERE dispensed_at >= ? AND dispensed_at <= ? ORDER BY dispensed_at",
                (outage.started_at.isoformat(), end.isoformat()),
            )
        else:
            rows = self.conn.execute("SELECT * FROM dispensations ORDER BY dispensed_at")
        return [
            {
                "id": r["id"], "dispensed_at": datetime.fromisoformat(r["dispensed_at"]),
                "patient_id": r["patient_id"], "inventory_id": r["inventory_id"],
                "weight": r["weight"], "unit": r["unit"], "location": r["location"],
                "mmur_verified": bool(r["mmur_verified"]), "outage_id": r["outage_id"],
            }
            for r in rows
        ]

    def watch(self, now: datetime | None = None) -> list[str]:
        """One unattended tick: draft what the clock says is due, and write the artifacts.

        Called by `coontie watch`, and automatically on restoration. No arguments beyond the
        clock, so a cron job or a service manager can run it forever.
        """
        from .outage import notice_draft, render_dispensations_csv, restoration_draft

        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        actions: list[str] = []
        facility = self.facility()
        name = facility.name if facility else ""
        license_number = facility.license_number if facility else ""

        for outage in self.outages():
            count = len(self.dispensations(outage.id))

            if outage.notice_is_due(now):
                subject, body = notice_draft(
                    outage, mmtc_name=name, license_number=license_number, dispensations=count, now=now
                )
                self.conn.execute(
                    "UPDATE outages SET notice_subject=?, notice_body=?, notice_created_at=? WHERE id=?",
                    (subject, body, now.isoformat(), outage.id),
                )
                self.conn.commit()
                path = self._write_artifact(f"outage-{outage.id}", "notice", subject, body)
                self.ledger.append(
                    "disconnect_notice",
                    {"outage": outage.id, "subject": subject, "dispensations_during_outage": count, "artifact": str(path)},
                    now,
                    facility_id=outage.facility_id or None,
                )
                actions.append(f"drafted disconnection notice {outage.id}: {path}")

            fresh = self.outage(outage.id)
            assert fresh is not None
            if fresh.open and not fresh.notice_sent_at and not fresh.notice_breach_at and now > fresh.notice_deadline:
                self.conn.execute("UPDATE outages SET notice_breach_at=? WHERE id=?", (now.isoformat(), fresh.id))
                self.conn.commit()
                actions.append(
                    f"BREACH: notice for {fresh.id} was due {fresh.notice_deadline.isoformat()} and is still unsent"
                )

            if fresh.restored_at and not fresh.restore_created_at:
                subject, body = restoration_draft(
                    fresh, mmtc_name=name, license_number=license_number, dispensations=count
                )
                rows = self.dispensations(fresh.id)
                csv_text = render_dispensations_csv(rows)
                self.conn.execute(
                    "UPDATE outages SET restore_subject=?, restore_body=?, restore_created_at=?, report_csv=?, "
                    "report_rows=?, report_created_at=? WHERE id=?",
                    (subject, body, now.isoformat(), csv_text, len(rows), now.isoformat(), fresh.id),
                )
                self.conn.commit()
                notice_path = self._write_artifact(f"outage-{fresh.id}", "restoration", subject, body)
                csv_path = self._write_artifact(f"outage-{fresh.id}", "dispensations", None, csv_text, suffix=".csv")
                self.conn.execute("UPDATE outages SET report_path=? WHERE id=?", (str(csv_path), fresh.id))
                self.conn.commit()
                self.ledger.append(
                    "outage_report",
                    {
                        "outage": fresh.id, "dispensations": len(rows),
                        "restoration_artifact": str(notice_path), "csv_artifact": str(csv_path),
                    },
                    now,
                    facility_id=fresh.facility_id or None,
                )
                actions.append(
                    f"restored {fresh.id}: drafted restoration notice {notice_path} and outage CSV {csv_path} ({len(rows)} dispensations)"
                )

            fresh = self.outage(outage.id)
            assert fresh is not None
            if (
                fresh.restored_at
                and not fresh.report_sent_at
                and not fresh.report_breach_at
                and fresh.report_deadline
                and now > fresh.report_deadline
            ):
                self.conn.execute("UPDATE outages SET report_breach_at=? WHERE id=?", (now.isoformat(), fresh.id))
                self.conn.commit()
                actions.append(
                    f"BREACH: outage CSV for {fresh.id} was due {fresh.report_deadline.isoformat()} and is still unsent"
                )
        return actions

    def send_outage(self, outage_id: str, what: str, when: datetime | None = None):
        from .compliance import DEPT_EMAIL

        when = (when or datetime.now(timezone.utc)).astimezone(timezone.utc)
        column = {"notice": "notice_sent_at", "restoration": "restore_sent_at", "report": "report_sent_at"}.get(what)
        if not column:
            raise ValueError("what must be one of: notice, restoration, report")
        cur = self.conn.execute(f"UPDATE outages SET {column} = ? WHERE id = ?", (when.isoformat(), outage_id))
        if cur.rowcount == 0:
            raise ValueError(f"no outage {outage_id!r}")
        self.conn.commit()
        return DEPT_EMAIL

    def _write_artifact(self, stem: str, kind: str, subject: str | None, body: str, suffix: str = ".txt") -> Path:
        directory = Path(self.path).resolve().parent / "reports"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{stem}-{kind}{suffix}"
        text = body if subject is None else f"{subject}\n\n{body}\n"
        path.write_text(text, encoding="utf-8")
        return path

    def _outage_from_row(self, row):
        from .outage import Outage

        def _dt(v):
            return datetime.fromisoformat(v) if v else None

        return Outage(
            id=row["id"], facility_id=row["facility_id"], started_at=datetime.fromisoformat(row["started_at"]),
            restored_at=_dt(row["restored_at"]), notice_subject=row["notice_subject"], notice_body=row["notice_body"],
            notice_created_at=_dt(row["notice_created_at"]), notice_sent_at=_dt(row["notice_sent_at"]),
            notice_breach_at=_dt(row["notice_breach_at"]), restore_subject=row["restore_subject"],
            restore_body=row["restore_body"], restore_created_at=_dt(row["restore_created_at"]),
            restore_sent_at=_dt(row["restore_sent_at"]), report_csv=row["report_csv"],
            report_path=row["report_path"], report_rows=row["report_rows"],
            report_created_at=_dt(row["report_created_at"]), report_sent_at=_dt(row["report_sent_at"]),
            report_breach_at=_dt(row["report_breach_at"]),
        )

    # -- drift (S4) ----------------------------------------------------------

    def link_lot(self, lot_id: str, sts_inventory_id: str, when: datetime | None = None):
        """Attach the department's inventory identification number to one of our lots."""
        when = (when or datetime.now(timezone.utc)).astimezone(timezone.utc)
        row = self.conn.execute("SELECT * FROM lots WHERE id = ?", (lot_id,)).fetchone()
        if not row:
            raise ValueError(f"no lot {lot_id!r}")
        sts_inventory_id = sts_inventory_id.strip()
        if not sts_inventory_id:
            raise ValueError("the department inventory id cannot be empty")
        clash = self.conn.execute(
            "SELECT id FROM lots WHERE sts_inventory_id = ? AND id <> ?", (sts_inventory_id, lot_id)
        ).fetchone()
        if clash:
            raise ValueError(f"{sts_inventory_id} is already linked to lot {clash['id']}")
        self.conn.execute("UPDATE lots SET sts_inventory_id = ? WHERE id = ?", (sts_inventory_id, lot_id))
        self.conn.commit()
        self.ledger.append(
            "sts_id_link", {"lot_id": lot_id, "sts_inventory_id": sts_inventory_id}, when
        )
        return lot_id

    def unlinked_lots(self) -> list:
        return [
            _lot(r)
            for r in self.conn.execute("SELECT * FROM lots WHERE sts_inventory_id IS NULL ORDER BY created_at")
        ]

    def pull_state(self, text: str, *, source_file: str = "", as_of: datetime | None = None):
        """Store one snapshot of the department's copy. Returns (snapshot_id, rows, rejected)."""
        from .driftfeed import parse_state_export
        from .outage import new_id

        parsed = parse_state_export(text)
        if not parsed.rows:
            reason = parsed.rejected[0][1] if parsed.rejected else "no usable rows"
            raise ValueError(f"could not read the state export: {reason}")
        as_of = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
        sid = new_id("snp")
        self.conn.execute(
            "INSERT INTO state_snapshots (id,source_file,as_of,rows,rejected,created_at) VALUES (?,?,?,?,?,?)",
            (sid, source_file, as_of.isoformat(), len(parsed.rows), len(parsed.rejected), _now()),
        )
        for r in parsed.rows:
            self.conn.execute(
                "INSERT OR REPLACE INTO state_inventory"
                " (snapshot_id,sts_inventory_id,product,quantity,unit,status,room,raw) VALUES (?,?,?,?,?,?,?,?)",
                (
                    sid, r.sts_inventory_id, r.product, str(r.quantity), r.unit, r.status, r.room,
                    json.dumps(r.raw, sort_keys=True),
                ),
            )
        self.conn.commit()
        self.last_parsed = parsed
        return sid, len(parsed.rows), len(parsed.rejected)

    def latest_snapshot(self):
        row = self.conn.execute("SELECT * FROM state_snapshots ORDER BY as_of DESC, created_at DESC LIMIT 1").fetchone()
        if not row:
            return None
        return {
            "id": row["id"], "source_file": row["source_file"], "as_of": datetime.fromisoformat(row["as_of"]),
            "rows": row["rows"], "rejected": row["rejected"],
        }

    def state_rows(self, snapshot_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM state_inventory WHERE snapshot_id = ? ORDER BY sts_inventory_id", (snapshot_id,)
        )
        return [
            {
                "sts_inventory_id": r["sts_inventory_id"], "product": r["product"], "quantity": r["quantity"],
                "unit": r["unit"], "status": r["status"], "room": r["room"], "raw": json.loads(r["raw"] or "{}"),
            }
            for r in rows
        ]

    def compare_drift(self, snapshot_id: str | None = None, tolerance: str = "0.05"):
        """Compare the day's records to one state snapshot and persist the differences."""
        from . import drift as drift_mod
        from .driftfeed import to_base
        from .outage import new_id

        snapshot = self.latest_snapshot() if snapshot_id is None else {"id": snapshot_id}
        if snapshot is None:
            raise ValueError("no state snapshot yet: run `coontie drift pull --csv <file>` first")
        sid = snapshot["id"]

        ours: dict[str, dict] = {}
        for r in self.conn.execute(
            "SELECT l.*, p.name AS product_name, r.name AS room_name, r.number AS room_number"
            " FROM lots l JOIN products p ON p.id = l.product_id JOIN rooms r ON r.id = l.room_id"
            " WHERE l.sts_inventory_id IS NOT NULL"
        ):
            quantity, base_unit = to_base(r["quantity"], r["unit"])
            ours[r["sts_inventory_id"]] = {
                "quantity": str(quantity), "unit": base_unit,
                "status": "on_hold" if r["on_hold"] else "active",
                "product": r["product_name"], "room": r["room_name"], "lot_id": r["id"],
            }

        theirs: dict[str, dict] = {}
        for r in self.state_rows(sid):
            quantity, base_unit = to_base(r["quantity"], r["unit"])
            theirs[r["sts_inventory_id"]] = {
                "quantity": str(quantity), "unit": base_unit, "status": r["status"],
                "product": r["product"], "room": r["room"],
            }

        report = drift_mod.compare(ours, theirs, quantity_tolerance=tolerance)
        for item in report.items:
            self.conn.execute(
                "INSERT OR IGNORE INTO drift_findings"
                " (id,snapshot_id,kind,record_key,ours,theirs,note,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    new_id("drf"), sid, item.kind.value, item.key,
                    json.dumps(item.ours, sort_keys=True), json.dumps(item.theirs, sort_keys=True),
                    item.note, _now(),
                ),
            )
        self.conn.commit()
        return report, self.drift_findings(sid, open_only=False)

    def drift_findings(self, snapshot_id: str | None = None, open_only: bool = True) -> list[dict]:
        if snapshot_id is None:
            snapshot = self.latest_snapshot()
            if not snapshot:
                return []
            snapshot_id = snapshot["id"]
        sql = "SELECT * FROM drift_findings WHERE snapshot_id = ?"
        if open_only:
            sql += " AND resolution IS NULL"
        sql += " ORDER BY kind, record_key"
        out = []
        for r in self.conn.execute(sql, (snapshot_id,)):
            ours = json.loads(r["ours"] or "{}")
            theirs = json.loads(r["theirs"] or "{}")
            out.append(
                {
                    "id": r["id"], "snapshot_id": r["snapshot_id"], "kind": r["kind"],
                    "record_key": r["record_key"], "ours": ours, "theirs": theirs, "note": r["note"],
                    "resolution": r["resolution"], "resolution_note": r["resolution_note"],
                    "resolved_at": r["resolved_at"],
                }
            )
        return out

    def finding(self, ref: str) -> dict | None:
        for f in self.drift_findings(self.latest_snapshot()["id"] if self.latest_snapshot() else None, open_only=False):
            if f["id"] == ref or f["id"].startswith(ref):
                return f
        return None

    def resolve_finding(
        self,
        ref: str,
        action: str,
        *,
        note: str = "",
        quantity=None,
        product: str | None = None,
        room: str | None = None,
        actor: str = "",
        when: datetime | None = None,
    ) -> dict:
        """Resolve one difference. Every action is recorded; nothing is silently discarded."""
        from .driftfeed import normalise_unit, to_base

        when = (when or datetime.now(timezone.utc)).astimezone(timezone.utc)
        finding = self.finding(ref)
        if finding is None:
            raise ValueError(f"no finding matching {ref!r}")
        if finding["resolution"]:
            raise ValueError(f"finding {finding['id']} is already resolved ({finding['resolution']})")
        kind = finding["kind"]
        key = finding["record_key"]
        theirs = finding["theirs"]
        ours = finding["ours"]
        allowed = {
            "quantity_mismatch": {"accept_state", "keep_local", "recount"},
            "status_mismatch": {"accept_state", "keep_local"},
            "missing_at_state": {"keep_local", "resend"},
            "missing_locally": {"record_state", "keep_local"},
        }[kind]
        if action not in allowed:
            raise ValueError(f"{action!r} does not apply to a {kind}; choose one of: {', '.join(sorted(allowed))}")

        lot_row = self.conn.execute("SELECT * FROM lots WHERE sts_inventory_id = ?", (key,)).fetchone()
        before = dict(ours)
        after: dict = {}
        reason = note or f"drift resolution against state snapshot {finding['snapshot_id']}"

        if action == "accept_state":
            if kind == "quantity_mismatch":
                if normalise_unit(ours.get("unit", "")) != normalise_unit(theirs.get("unit", "")):
                    raise ValueError(
                        f"the two records are in different units ({ours.get('unit')} vs {theirs.get('unit')}); "
                        "recount rather than accept"
                    )
                self.amend_lot(
                    lot_row["id"], new_quantity=theirs["quantity"], cause="miscount",
                    reason=f"aligned to the department's quantity: {reason}", actor=actor, when=when,
                )
                after = {"quantity": theirs["quantity"]}
            else:
                hold = theirs.get("status") == "on_hold"
                self.amend_lot(
                    lot_row["id"], new_on_hold=hold, cause="other",
                    reason=f"aligned to the department's status {theirs.get('status')!r}: {reason}",
                    actor=actor, when=when,
                )
                after = {"status": theirs.get("status")}

        elif action == "recount":
            if quantity is None:
                raise ValueError("recount needs a counted quantity")
            self.amend_lot(
                lot_row["id"], new_quantity=quantity, cause="miscount",
                reason=f"physical recount: {reason}", actor=actor, when=when,
            )
            after = {"quantity": str(Decimal(str(quantity)))}

        elif action == "record_state":
            count, base_unit = to_base(theirs.get("quantity", "0"), theirs.get("unit", "units"))
            target_product = self._match_product(product or theirs.get("product", ""))
            if target_product is None:
                raise ValueError(
                    f"no product matches {theirs.get('product')!r}; add it with `coontie product add` first"
                )
            target_room = self._match_room(room or theirs.get("room", ""))
            if target_room is None:
                raise ValueError(f"no room matches {theirs.get('room')!r}; give --room")
            lot_id = f"lot-{uuid.uuid4().hex[:10]}"
            self.conn.execute(
                "INSERT INTO lots (id,product_id,room_id,quantity,unit,on_hold,sts_inventory_id,created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (lot_id, target_product["id"], target_room.id, str(count), base_unit,
                 int(theirs.get("status") == "on_hold"), key, _now()),
            )
            self.conn.commit()
            self.ledger.append(
                "inventory_lot_create",
                {
                    "inventory": target_product["id"], "lot_id": lot_id, "weight_or_volume": str(count),
                    "unit": base_unit, "inventory_type": target_product["product_type"],
                    "cultivar": target_product["cultivar"], "facility_location": target_product["facility_id"],
                    "room": target_room.id, "harvest_batch_ids": [], "sts_inventory_id": key,
                    "recovered_from_state_snapshot": finding["snapshot_id"],
                },
                when,
            )
            after = {"quantity": str(count), "unit": base_unit, "lot_id": lot_id}

        elif action == "resend":
            # Nothing changes locally; the generic drift_resolution entry below is the record.
            after = {"resend": True}

        self.conn.execute(
            "UPDATE drift_findings SET resolution=?, resolution_note=?, resolved_at=? WHERE id=?",
            (action, reason, when.isoformat(), finding["id"]),
        )
        self.conn.commit()
        self.ledger.append(
            "drift_resolution",
            {
                "snapshot": finding["snapshot_id"], "kind": kind, "record_key": key, "action": action,
                "note": reason, "checked_at": finding["snapshot_id"],
                "before": before, "after": after,
            },
            when,
        )
        return self.finding(finding["id"])

    def _match_product(self, text: str):
        if not text:
            return None
        row = self.conn.execute("SELECT * FROM products WHERE LOWER(name) = LOWER(?)", (text.strip(),)).fetchone()
        if row:
            return row
        row = self.conn.execute("SELECT * FROM products WHERE upid = ?", (text.strip(),)).fetchone()
        return row

    def _match_room(self, text: str):
        if text:
            for r in self.rooms():
                if text.strip().lower() in (r.name.lower(), r.number.lower(), f"{r.name} {r.number}".lower()):
                    return r
        rooms = [r for r in self.rooms() if r.kind == "inventory"]
        return rooms[0] if rooms else None

    # -- cultivation (S5) ----------------------------------------------------

    def record_integration(self, approved_on: datetime, reference: str = "", note: str = "") -> dict:
        """Record that the department approved this MMTC's integration. Cultivation needs it."""
        from .outage import new_id

        rid = new_id("int")
        self.conn.execute(
            "INSERT INTO integration (id,approved_on,reference,note,created_at) VALUES (?,?,?,?,?)",
            (rid, approved_on.isoformat(), reference, note, _now()),
        )
        self.conn.commit()
        self.ledger.append(
            "integration_approved",
            {"approved_on": approved_on.isoformat(), "reference": reference, "note": note},
            approved_on,
        )
        return {"id": rid, "approved_on": approved_on, "reference": reference, "note": note}

    def integration(self) -> dict | None:
        row = self.conn.execute("SELECT * FROM integration ORDER BY approved_on DESC LIMIT 1").fetchone()
        if not row:
            return None
        return {
            "id": row["id"], "approved_on": datetime.fromisoformat(row["approved_on"]),
            "reference": row["reference"], "note": row["note"],
        }

    def _room_ref(self, value: str):
        text = (value or "").strip().lower()
        for r in self.rooms():
            if text in (r.id.lower(), r.name.lower(), r.number.lower(), f"{r.name} {r.number}".lower()):
                return r
        raise ValueError(f"no room matches {value!r}; rooms are: {', '.join(r.name for r in self.rooms()) or 'none yet'}")

    def start_batch(
        self,
        *,
        cultivar: str,
        room: str,
        count: int,
        mother_plant_id: str = "",
        when: datetime | None = None,
    ) -> "Batch":
        from .cultivation import Batch, utcnow
        from .outage import new_id

        if not self.integration():
            raise ValueError(
                "cultivation cannot start before integration is complete and recorded: "
                "Rule 64-4.221(4) requires full integration before cultivation authorization "
                "(record it with `coontie integration --approved-on <date> --reference <plan ref>`)"
            )
        if not cultivar.strip():
            raise ValueError("a batch needs a cultivar")
        count = int(count)
        if count <= 0:
            raise ValueError("a batch needs a positive count of seeds or clones")
        facility = self.facility()
        if not facility:
            raise ValueError("no facility yet: run `coontie init` first")
        target = self._room_ref(room)
        when = when or utcnow()
        batch = Batch(
            id=new_id("bat"), facility_id=facility.id, room_id=target.id, cultivar=cultivar.strip(),
            count=count, mother_plant_id=mother_plant_id.strip(), created_at=when,
        )
        self.conn.execute(
            "INSERT INTO batches (id,facility_id,room_id,cultivar,count,mother_plant_id,created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (batch.id, batch.facility_id, batch.room_id, batch.cultivar, batch.count,
             batch.mother_plant_id, when.isoformat()),
        )
        self.conn.commit()
        self.ledger.append(
            "seed_clone_batch",
            {
                "facility_location": facility.id, "room": target.id, "cultivar": batch.cultivar,
                "count": batch.count, "mother_plant_id": batch.mother_plant_id,
            },
            when,
            facility_id=facility.id,
        )
        return batch

    def plant_batch(
        self, batch_id: str, count: int, *, at: datetime | None = None, is_mother: bool = False
    ) -> list["Plant"]:
        from .cultivation import Plant, plant_id, utcnow

        row = self.conn.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
        if not row:
            raise ValueError(f"no batch {batch_id!r}")
        already = int(self.conn.execute("SELECT COUNT(*) FROM plants WHERE batch_id = ?", (batch_id,)).fetchone()[0])
        count = int(count)
        if count <= 0:
            raise ValueError("plant at least one")
        if already + count > row["count"]:
            raise ValueError(
                f"batch {batch_id} holds {row['count']} and already has {already} planted; {count} more is too many"
            )
        at = at or utcnow()
        next_number = int(self.conn.execute("SELECT COUNT(*) FROM plants").fetchone()[0]) + 1
        made: list[Plant] = []
        for offset in range(count):
            plant = Plant(
                id=plant_id(next_number + offset), batch_id=batch_id, cultivar=row["cultivar"],
                room_id=row["room_id"], is_mother=is_mother, planted_at=at, state="immature",
            )
            self.conn.execute(
                "INSERT INTO plants (id,batch_id,cultivar,room_id,is_mother,planted_at,state,created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (plant.id, plant.batch_id, plant.cultivar, plant.room_id, int(is_mother),
                 at.isoformat(), plant.state, _now()),
            )
            self.conn.commit()
            self.ledger.append(
                "immature_plant",
                {
                    "facility_location": row["facility_id"], "room": plant.room_id,
                    "cultivar": plant.cultivar, "is_mother_plant": bool(is_mother),
                    "planted_at": at.isoformat(), "origin_batch_id": batch_id, "plant_id": plant.id,
                },
                at,
                facility_id=row["facility_id"],
            )
            made.append(plant)
        return made

    def move_plants(self, ids: tuple[str, ...], to_room: str, *, at: datetime | None = None) -> list["Plant"]:
        from .cultivation import require_growing, utcnow

        target = self._room_ref(to_room)
        at = at or utcnow()
        plants = {p.id: p for p in self.plants()}
        require_growing(plants, ids)
        for pid in ids:
            self.conn.execute("UPDATE plants SET room_id = ? WHERE id = ?", (target.id, pid))
        self.conn.commit()
        self.ledger.append(
            "plant_move",
            {"facility_location": plants[ids[0]].batch_id and self._facility_of_batch(plants[ids[0]].batch_id),
             "plant_ids": list(ids), "to_room": target.id},
            at,
        )
        return [self.plants_map()[pid] for pid in ids]

    def _facility_of_batch(self, batch_id: str) -> str:
        row = self.conn.execute("SELECT facility_id FROM batches WHERE id = ?", (batch_id,)).fetchone()
        return row["facility_id"] if row else ""

    def apply_additive(
        self,
        ids: tuple[str, ...],
        *,
        description: str,
        amount,
        unit: str,
        at: datetime | None = None,
    ) -> "Additive":
        from .cultivation import Additive, amount as to_amount, require_growing, utcnow
        from .outage import new_id

        if not description.strip():
            raise ValueError("say what was applied: active ingredient, concentration, manufacturer lot")
        plants = self.plants_map()
        require_growing(plants, ids)
        value = to_amount(amount)
        at = at or utcnow()
        additive = Additive(
            id=new_id("add"), description=description.strip(), amount=value, unit=unit.strip() or "ml",
            plant_ids=tuple(ids), applied_at=at,
        )
        self.conn.execute(
            "INSERT INTO additives (id,description,amount,unit,plant_ids,applied_at,created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (additive.id, additive.description, str(value), additive.unit, json.dumps(list(ids)), at.isoformat(), _now()),
        )
        self.conn.commit()
        self.ledger.append(
            "additive_application",
            {
                "facility_location": self._facility_of_batch(plants[ids[0]].batch_id),
                "additive_description": additive.description, "amount": str(value), "unit": additive.unit,
                "plant_ids": list(ids),
            },
            at,
        )
        return additive

    def schedule_harvest(self, ids: tuple[str, ...], *, at: datetime | None = None) -> "Harvest":
        from .cultivation import Harvest, require_growing, utcnow
        from .outage import new_id

        plants = self.plants_map()
        require_growing(plants, ids)
        wanted = set(ids)
        for h in self.harvests():
            if h.scheduled and not h.completed and wanted & set(h.plant_ids):
                raise ValueError(
                    f"{', '.join(sorted(wanted & set(h.plant_ids)))} is already scheduled for harvest ({h.id})"
                )
        at = at or utcnow()
        harvest = Harvest(
            id=new_id("hrv"), room_id=plants[ids[0]].room_id, post_harvest_room_id="",
            plant_ids=tuple(ids), wet_weight=Decimal("0"), wet_unit="g",
            waste_weight=Decimal("0"), waste_unit="g", other_weight=Decimal("0"), other_unit="g",
            scheduled_at=at,
        )
        self.conn.execute(
            "INSERT INTO harvests (id,room_id,post_harvest_room_id,plant_ids,wet_weight,wet_unit,waste_weight,"
            "waste_unit,other_weight,other_unit,scheduled_at,harvested_at,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (harvest.id, harvest.room_id, "", json.dumps(list(ids)), "0", "g", "0", "g", "0", "g",
             at.isoformat(), None, _now()),
        )
        self.conn.commit()
        self.ledger.append(
            "harvest_schedule",
            {"facility_location": self._facility_of_batch(plants[ids[0]].batch_id), "plant_ids": list(ids)},
            at,
        )
        return harvest

    def harvest(
        self,
        ids: tuple[str, ...],
        *,
        wet,
        waste="0",
        other="0",
        unit: str = "g",
        post_harvest_room: str,
        at: datetime | None = None,
    ) -> "Harvest":
        from .cultivation import (
            amount as to_amount,
            check_harvest_weights,
            matching_schedule,
            describe_open_schedules,
            require_growing,
            utcnow,
        )

        plants = self.plants_map()
        require_growing(plants, ids)
        schedule = matching_schedule(self.harvests(), ids)
        if schedule is None:
            raise ValueError(
                "a harvest must be scheduled before the plants are harvested (DH5059: Scheduling Plant "
                f"Harvests); open schedules: {describe_open_schedules(self.harvests())}"
            )
        target = self._room_ref(post_harvest_room)
        wet_d = to_amount(wet)
        waste_d = to_amount(waste)
        other_d = to_amount(other)
        check_harvest_weights(wet_d, waste_d, other_d)
        at = at or utcnow()

        self.conn.execute(
            "UPDATE harvests SET post_harvest_room_id=?, wet_weight=?, wet_unit=?, waste_weight=?, waste_unit=?,"
            " other_weight=?, other_unit=?, harvested_at=? WHERE id=?",
            (target.id, str(wet_d), unit, str(waste_d), unit, str(other_d), unit, at.isoformat(), schedule.id),
        )
        for pid in ids:
            self.conn.execute("UPDATE plants SET state = 'harvested' WHERE id = ?", (pid,))
        self.conn.commit()
        self.ledger.append(
            "harvest",
            {
                "facility_location": self._facility_of_batch(plants[ids[0]].batch_id),
                "plant_ids": list(ids), "wet_flower_weight": str(wet_d), "wet_flower_unit": unit,
                "waste_weight": str(waste_d), "waste_unit": unit,
                "other_material_weight": str(other_d), "other_material_unit": unit,
                "post_harvest_room": target.id, "harvest_id": schedule.id,
            },
            at,
        )
        return self.harvest_map()[schedule.id]

    def schedule_disposal_plants(self, ids: tuple[str, ...], *, reason: str, at: datetime | None = None):
        from .cultivation import Disposal, require_growing, utcnow
        from .outage import new_id

        plants = self.plants_map()
        require_growing(plants, ids)
        if not reason.strip():
            raise ValueError("a disposal schedule needs a reason")
        at = at or utcnow()
        disposal = Disposal(
            id=new_id("dsp"), kind="plants", subject=json.dumps(list(ids)), reason=reason.strip(),
            scheduled_at=at, disposed_at=None,
        )
        self.conn.execute(
            "INSERT INTO disposals (id,kind,subject,reason,scheduled_at,disposed_at,created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (disposal.id, disposal.kind, disposal.subject, disposal.reason, at.isoformat(), None, _now()),
        )
        self.conn.commit()
        self.ledger.append(
            "disposal_schedule_plants", {"plant_ids": list(ids), "reason": disposal.reason}, at
        )
        return disposal

    def dispose_plants(self, ids: tuple[str, ...], *, at: datetime | None = None) -> "Disposal":
        from .cultivation import Disposal, require_disposal_wait, require_growing, utcnow

        plants = self.plants_map()
        require_growing(plants, ids)
        wanted = set(ids)
        match = None
        for d in self.disposals():
            if d.kind == "plants" and d.disposed_at is None and set(json.loads(d.subject)) == wanted:
                match = d
                break
        if match is None:
            raise ValueError(
                "plant disposal must be scheduled first (DH5059: Schedule Plant Disposal), and the schedule "
                "must cover exactly these plants"
            )
        at = at or utcnow()
        require_disposal_wait(match.scheduled_at, at)
        self.conn.execute("UPDATE disposals SET disposed_at = ? WHERE id = ?", (at.isoformat(), match.id))
        for pid in ids:
            self.conn.execute("UPDATE plants SET state = 'disposed' WHERE id = ?", (pid,))
        self.conn.commit()
        self.ledger.append("disposal_plants", {"plant_ids": list(ids), "disposal_id": match.id}, at)
        return [d for d in self.disposals() if d.id == match.id][0]

    def dispose_matter(self, *, weight, unit: str = "g", at: datetime | None = None) -> "Disposal":
        from .cultivation import Disposal, amount as to_amount, utcnow
        from .outage import new_id

        facility = self.facility()
        value = to_amount(weight)
        if value <= 0:
            raise ValueError("plant matter disposal needs a weight greater than zero")
        at = at or utcnow()
        disposal = Disposal(
            id=new_id("dsp"), kind="matter", subject="post-defoliation matter", reason="waste",
            scheduled_at=None, disposed_at=at, weight=value, unit=unit,
        )
        self.conn.execute(
            "INSERT INTO disposals (id,kind,subject,reason,scheduled_at,disposed_at,weight,unit,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (disposal.id, disposal.kind, disposal.subject, disposal.reason, None, at.isoformat(),
             str(value), unit, _now()),
        )
        self.conn.commit()
        self.ledger.append(
            "plant_matter_disposal",
            {
                "facility_location": facility.id if facility else "",
                "collected_at": at.isoformat(), "weight": str(value), "unit": unit,
            },
            at,
            facility_id=facility.id if facility else None,
        )
        return disposal

    # -- cultivation reads ---------------------------------------------------

    def batches(self) -> list["Batch"]:
        from .cultivation import Batch

        return [
            Batch(
                id=r["id"], facility_id=r["facility_id"], room_id=r["room_id"], cultivar=r["cultivar"],
                count=r["count"], mother_plant_id=r["mother_plant_id"],
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in self.conn.execute("SELECT * FROM batches ORDER BY created_at, rowid")
        ]

    def plants(self) -> list["Plant"]:
        from .cultivation import Plant

        return [
            Plant(
                id=r["id"], batch_id=r["batch_id"], cultivar=r["cultivar"], room_id=r["room_id"],
                is_mother=bool(r["is_mother"]), planted_at=datetime.fromisoformat(r["planted_at"]),
                state=r["state"],
            )
            for r in self.conn.execute("SELECT * FROM plants ORDER BY id")
        ]

    def plants_map(self) -> dict:
        return {p.id: p for p in self.plants()}

    def harvests(self) -> list["Harvest"]:
        from .cultivation import Harvest

        return [
            Harvest(
                id=r["id"], room_id=r["room_id"], post_harvest_room_id=r["post_harvest_room_id"],
                plant_ids=tuple(json.loads(r["plant_ids"])), wet_weight=Decimal(r["wet_weight"]),
                wet_unit=r["wet_unit"], waste_weight=Decimal(r["waste_weight"]), waste_unit=r["waste_unit"],
                other_weight=Decimal(r["other_weight"]), other_unit=r["other_unit"],
                scheduled_at=datetime.fromisoformat(r["scheduled_at"]) if r["scheduled_at"] else None,
                harvested_at=datetime.fromisoformat(r["harvested_at"]) if r["harvested_at"] else None,
            )
            for r in self.conn.execute("SELECT * FROM harvests ORDER BY created_at, rowid")
        ]

    def harvest_map(self) -> dict:
        return {h.id: h for h in self.harvests()}

    def additives(self) -> list["Additive"]:
        from .cultivation import Additive

        return [
            Additive(
                id=r["id"], description=r["description"], amount=Decimal(r["amount"]), unit=r["unit"],
                plant_ids=tuple(json.loads(r["plant_ids"])), applied_at=datetime.fromisoformat(r["applied_at"]),
            )
            for r in self.conn.execute("SELECT * FROM additives ORDER BY applied_at, rowid")
        ]

    def disposals(self) -> list["Disposal"]:
        from .cultivation import Disposal

        return [
            Disposal(
                id=r["id"], kind=r["kind"], subject=r["subject"], reason=r["reason"],
                scheduled_at=datetime.fromisoformat(r["scheduled_at"]) if r["scheduled_at"] else None,
                disposed_at=datetime.fromisoformat(r["disposed_at"]) if r["disposed_at"] else None,
                weight=Decimal(r["weight"]) if r["weight"] else None, unit=r["unit"],
            )
            for r in self.conn.execute("SELECT * FROM disposals ORDER BY created_at, rowid")
        ]

    def growing(self) -> dict:
        rows = self.conn.execute(
            "SELECT room_id, COUNT(*) AS n FROM plants WHERE state = 'immature' GROUP BY room_id"
        )
        rooms = {r.id: r.name for r in self.rooms()}
        return {rooms.get(r["room_id"], r["room_id"]): r["n"] for r in rows}

    # -- processing (S6) -----------------------------------------------------

    def cure(self, harvest_id: str, *, post, waste="0", unit: str = "g", room: str, at: datetime | None = None):
        from .outage import new_id
        from .processing import Cure, amount as to_amount, utcnow

        row = self.conn.execute("SELECT * FROM harvests WHERE id = ?", (harvest_id,)).fetchone()
        if not row:
            raise ValueError(f"no harvest {harvest_id!r}")
        if not row["harvested_at"]:
            raise ValueError(f"harvest {harvest_id} has not been harvested yet; there is nothing to cure")
        already = self.conn.execute(
            "SELECT id, post_weight, cured_at FROM cures WHERE harvest_id = ? ORDER BY cured_at",
            (harvest_id,)).fetchone()
        if already:
            raise ValueError(
                f"harvest {harvest_id} was already cured to {already['post_weight']} g on "
                f"{str(already['cured_at'])[:16].replace('T', ' ')}; a harvest is cured once. "
                f"To correct that figure, record a correction with its cause"
            )
        target = self._room_ref(room)
        post_d = to_amount(post)
        waste_d = to_amount(waste)
        if post_d <= 0:
            raise ValueError("a cure needs a post-cure weight greater than zero")
        if waste_d < 0:
            raise ValueError("waste cannot be negative")
        if waste_d + post_d > Decimal(row["wet_weight"]):
            raise ValueError(
                f"post-cure ({post_d}) plus waste ({waste_d}) exceeds the {row['wet_weight']} {row['wet_unit']} "
                "that came off the plants"
            )
        at = at or utcnow()
        cure = Cure(
            id=new_id("cur"), harvest_id=harvest_id, plant_ids=tuple(json.loads(row["plant_ids"])),
            post_weight=post_d, post_unit=unit, waste_weight=waste_d, waste_unit=unit,
            room_id=target.id, cured_at=at,
        )
        self.conn.execute(
            "INSERT INTO cures (id,harvest_id,plant_ids,post_weight,post_unit,waste_weight,waste_unit,room_id,"
            "cured_at,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cure.id, harvest_id, row["plant_ids"], str(post_d), unit, str(waste_d), unit, target.id,
             at.isoformat(), _now()),
        )
        self.conn.commit()
        self.ledger.append(
            "cure_dry",
            {
                "facility_location": self._facility_of_batch(
                    self._batch_of_harvest(harvest_id)
                ),
                "harvest_batch_id": harvest_id, "plant_ids": json.loads(row["plant_ids"]),
                "post_cure_weight": str(post_d), "post_cure_unit": unit,
                "waste_weight": str(waste_d), "waste_unit": unit, "post_cure_room": target.id,
            },
            at,
        )
        return cure

    def _batch_of_harvest(self, harvest_id: str) -> str:
        row = self.conn.execute("SELECT plant_ids FROM harvests WHERE id = ?", (harvest_id,)).fetchone()
        if not row:
            return ""
        ids = json.loads(row["plant_ids"])
        if not ids:
            return ""
        plant = self.conn.execute("SELECT batch_id FROM plants WHERE id = ?", (ids[0],)).fetchone()
        return plant["batch_id"] if plant else ""

    def cured_available(self, harvest_id: str) -> Decimal:
        row = self.conn.execute("SELECT post_weight FROM cures WHERE harvest_id = ? ORDER BY cured_at", (harvest_id,)).fetchall()
        total = sum((Decimal(r["post_weight"]) for r in row), Decimal("0"))
        # Only a lot created directly from the cure consumes the harvest. A split, a conversion
        # or a packaged child still carries harvest_ids for lineage, but its weight is already
        # inside the parent's allocation: counting it again drove the balance negative.
        used = Decimal("0")
        for lot in self.stock_lots():
            if harvest_id in lot.harvest_ids and not lot.source_lot_id:
                used += lot.original
        return total - used

    def new_lot(
        self, *, kind: str, cultivar: str = "", weight, unit: str = "g", room: str, harvest_id: str = "",
        at: datetime | None = None,
    ) -> "StockLot":
        from .outage import new_id
        from .processing import StockLot, amount as to_amount, utcnow

        target = self._room_ref(room)
        value = to_amount(weight)
        if value <= 0:
            raise ValueError("a lot needs a weight greater than zero")
        if harvest_id:
            available = self.cured_available(harvest_id)
            if value > available:
                raise ValueError(
                    f"harvest {harvest_id} has {available} {unit} cured and unallocated; {value} was asked for"
                )
        facility = self.facility()
        at = at or utcnow()
        lot = StockLot(
            id=new_id("stk"), kind=kind.strip(), cultivar=cultivar.strip(), room_id=target.id,
            original=value, unit=unit, harvest_ids=(harvest_id,) if harvest_id else (), created_at=at,
        )
        self.conn.execute(
            "INSERT INTO stock_lots (id,kind,cultivar,room_id,original,unit,harvest_ids,source_lot_id,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (lot.id, lot.kind, lot.cultivar, lot.room_id, str(value), unit,
             json.dumps(list(lot.harvest_ids)), "", at.isoformat()),
        )
        self.conn.commit()
        self.ledger.append(
            "inventory_lot_create",
            {
                "weight_or_volume": str(value), "unit": unit, "inventory_type": lot.kind,
                "cultivar": lot.cultivar, "facility_location": facility.id if facility else "",
                "room": target.id, "harvest_batch_ids": list(lot.harvest_ids), "stock_lot_id": lot.id,
            },
            at,
            facility_id=facility.id if facility else None,
        )
        return lot

    def stock_lots(self) -> list["StockLot"]:
        from .processing import StockLot

        return [
            StockLot(
                id=r["id"], kind=r["kind"], cultivar=r["cultivar"], room_id=r["room_id"],
                original=Decimal(r["original"]), unit=r["unit"], harvest_ids=tuple(json.loads(r["harvest_ids"])),
                source_lot_id=r["source_lot_id"], created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in self.conn.execute("SELECT * FROM stock_lots ORDER BY created_at, rowid")
        ]

    def lot(self, ref: str) -> Lot:
        """Resolve a product lot by full id or unique prefix, and say what matched when ambiguous."""
        text = (ref or "").strip()
        if not text:
            raise ValueError("a lot reference is required")
        rows = [r for r in self.lots() if r.id == text]
        if not rows:
            rows = [r for r in self.lots() if r.id.startswith(text)]
        if not rows:
            raise ValueError(f"no product lot matching {ref!r} in this workspace")
        if len(rows) > 1:
            raise ValueError(
                f"{ref!r} matches {len(rows)} lots: {', '.join(sorted(r.id for r in rows)[:5])}; "
                "give more characters"
            )
        return rows[0]

    def stock_lot(self, ref: str) -> "StockLot":
        for lot in self.stock_lots():
            if lot.id == ref or lot.id.startswith(ref):
                return lot
        raise ValueError(f"no stock lot matching {ref!r}")

    def stock_moves(self, lot_id: str | None = None) -> list[dict]:
        sql = "SELECT * FROM stock_moves"
        args: tuple = ()
        if lot_id:
            sql += " WHERE lot_id = ?"
            args = (lot_id,)
        sql += " ORDER BY at, rowid"
        return [
            {
                "id": r["id"], "lot_id": r["lot_id"], "kind": r["kind"], "amount": Decimal(r["amount"]),
                "unit": r["unit"], "target_lot_id": r["target_lot_id"], "note": r["note"],
                "at": datetime.fromisoformat(r["at"]),
            }
            for r in self.conn.execute(sql, args)
        ]

    def stock_remaining(self, lot_id: str) -> Decimal:
        from .processing import remaining

        lot = self.stock_lot(lot_id)
        moves = [m["amount"] for m in self.stock_moves(lot.id)]
        return remaining(lot.original, moves)

    def _move(self, lot_id: str, kind: str, amount: Decimal, unit: str, *, target_lot_id: str = "", note: str = "", at=None):
        from .outage import new_id
        from .processing import utcnow

        at = at or utcnow()
        self.conn.execute(
            "INSERT INTO stock_moves (id,lot_id,kind,amount,unit,target_lot_id,note,at,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (new_id("mov"), lot_id, kind, str(amount), unit, target_lot_id, note, at.isoformat(), _now()),
        )
        self.conn.commit()

    def split_lot(self, lot_ref: str, *, amount, to_room: str, at: datetime | None = None) -> "StockLot":
        from .outage import new_id
        from .processing import StockLot, amount as to_amount, check_removal, utcnow

        lot = self.stock_lot(lot_ref)
        currently = self.stock_remaining(lot.id)
        value = to_amount(amount)
        check_removal(lot, currently, value)
        target = self._room_ref(to_room)
        facility = self.facility()
        at = at or utcnow()
        child = StockLot(
            id=new_id("stk"), kind=lot.kind, cultivar=lot.cultivar, room_id=target.id, original=value,
            unit=lot.unit, harvest_ids=lot.harvest_ids, source_lot_id=lot.id, created_at=at,
        )
        self.conn.execute(
            "INSERT INTO stock_lots (id,kind,cultivar,room_id,original,unit,harvest_ids,source_lot_id,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (child.id, child.kind, child.cultivar, child.room_id, str(value), lot.unit,
             json.dumps(list(child.harvest_ids)), lot.id, at.isoformat()),
        )
        self.conn.commit()
        self._move(lot.id, "split", value, lot.unit, target_lot_id=child.id, note="sublot", at=at)
        self.ledger.append(
            "lot_split",
            {
                "source_lot_id": lot.id, "facility_location": facility.id if facility else "",
                "new_room": target.id, "removed_weight_or_volume": str(value), "unit": lot.unit,
                "new_lot_id": child.id,
            },
            at,
            facility_id=facility.id if facility else None,
        )
        return child

    def convert(
        self, lot_ref: str, *, remove, resulting_kind: str, resulting_weight, waste="0",
        room: str, at: datetime | None = None,
    ) -> "StockLot":
        from .outage import new_id
        from .processing import (
            StockLot, amount as to_amount, check_conversion, check_removal, utcnow,
        )

        lot = self.stock_lot(lot_ref)
        currently = self.stock_remaining(lot.id)
        removed = to_amount(remove)
        result = to_amount(resulting_weight)
        waste_d = to_amount(waste)
        check_removal(lot, currently, removed)
        check_conversion(removed, result, waste_d)
        target = self._room_ref(room)
        facility = self.facility()
        at = at or utcnow()
        child = StockLot(
            id=new_id("stk"), kind=resulting_kind.strip(), cultivar=lot.cultivar, room_id=target.id,
            original=result, unit=lot.unit, harvest_ids=lot.harvest_ids, source_lot_id=lot.id, created_at=at,
        )
        self.conn.execute(
            "INSERT INTO stock_lots (id,kind,cultivar,room_id,original,unit,harvest_ids,source_lot_id,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (child.id, child.kind, child.cultivar, child.room_id, str(result), lot.unit,
             json.dumps(list(child.harvest_ids)), lot.id, at.isoformat()),
        )
        self.conn.commit()
        self._move(lot.id, "conversion", removed, lot.unit, target_lot_id=child.id,
                   note=f"{result} {lot.unit} {child.kind}, {waste_d} waste", at=at)
        self.ledger.append(
            "conversion",
            {
                "source_inventory_id": lot.id, "removed_weight_or_volume": str(removed),
                "removed_unit": lot.unit, "resulting_inventory_type": child.kind,
                "cultivar": child.cultivar, "resulting_weight_or_volume": str(result),
                "resulting_unit": lot.unit, "waste_weight": str(waste_d), "waste_unit": lot.unit,
                "facility_location": facility.id if facility else "", "post_conversion_room": target.id,
                "resulting_lot_id": child.id,
            },
            at,
            facility_id=facility.id if facility else None,
        )
        return child

    def add_ingredients(
        self, lot_ref: str, *, names: list[str], amounts: list[str], units: list[str], at: datetime | None = None
    ) -> list[tuple[str, Decimal, str]]:
        from .processing import amount as to_amount, utcnow

        if not (len(names) == len(amounts) == len(units)):
            raise ValueError("each ingredient needs one amount and one unit")
        lot = self.stock_lot(lot_ref)
        facility = self.facility()
        at = at or utcnow()
        parsed = [(n, to_amount(a), u) for n, a, u in zip(names, amounts, units)]
        # Ingredients are added, not taken: no stock move, no change to the lot's balance. The
        # ledger event carries the department's fields; a move here would report a gram lot as
        # having millilitre movements and the balance check would stop meaning anything.
        self.ledger.append(
            "ingredient_add",
            {
                "inventory_id": lot.id, "ingredient_names": [n for n, _, _ in parsed],
                "ingredient_amounts": [str(a) for _, a, _ in parsed], "units": [u for _, _, u in parsed],
                "facility_location": facility.id if facility else "",
            },
            at,
            facility_id=facility.id if facility else None,
        )
        return parsed

    def adjust_stock(
        self, lot_ref: str, *, remove, cause: str, reason: str, actor: str = "", at: datetime | None = None
    ):
        """A processing-lot correction: moves weight, keeps the cause, drafts the notice if needed."""
        from .amendments import Amendment, new_id, validate_cause
        from .processing import amount as to_amount, check_removal, utcnow

        validate_cause(cause)
        if not (reason or "").strip():
            raise ValueError("an adjustment needs a reason")
        lot = self.stock_lot(lot_ref)
        currently = self.stock_remaining(lot.id)
        value = to_amount(remove)
        check_removal(lot, currently, value)
        at = at or utcnow()
        after = currently - value
        amendment = Amendment(
            id=new_id("amd"), target_kind="stock_lot", target_id=lot.id, field="quantity",
            before=str(currently), after=str(after), cause=cause, reason=reason.strip(),
            actor=actor, occurred_at=at, unit=lot.unit,
            sequence=int(self.conn.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 FROM amendments WHERE target_id = ?", (lot.id,)
            ).fetchone()[0]),
        )
        self.conn.execute(
            "INSERT INTO amendments (id,sequence,target_kind,target_id,field,before_value,after_value,cause,"
            "reason,actor,occurred_at,facility_id,unit,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (amendment.id, amendment.sequence, amendment.target_kind, amendment.target_id, amendment.field,
             amendment.before, amendment.after, cause, amendment.reason, actor, at.isoformat(),
             lot.room_id, lot.unit, _now()),
        )
        self.conn.commit()
        self._move(lot.id, "adjustment", value, lot.unit, note=f"{cause}: {reason}", at=at)
        facility = self.facility()
        self.ledger.append(
            "inventory_adjustment",
            {
                # The catalogue requires inventory_id on every adjustment. A processing lot may have
                # no department id yet, so the field carries the department's number when the record
                # has it and the local id when it does not, and says which one it is. Leaving the
                # field out was the alternative, and a payload missing a required field is not a
                # record the department can read.
                "inventory_id": self._department_id(lot.id) or lot.id,
                "inventory_id_source": "department" if self._department_id(lot.id) else "local",
                "inventory_reference": lot.id,
                "adjustment_type": "weight", "reason": reason,
                "removed_weight_or_volume": str(value), "unit": lot.unit,
                "facility_location": facility.id if facility else "", "cause": cause,
            },
            at,
            facility_id=facility.id if facility else None,
        )
        if amendment.exempt:
            return amendment, None
        return amendment, self.create_justification(amendment.id)

    def lab_sample(
        self, lot_ref: str, *, weight, cmtl_id: str, is_rnd: bool = False, at: datetime | None = None
    ) -> "LabSample":
        from .outage import new_id
        from .processing import LabSample, amount as to_amount, check_removal, cmtl_note, utcnow

        if not (cmtl_id or "").strip():
            raise ValueError("a lab sample needs the identity of the certified testing laboratory (cmtl_id)")
        lot = self.stock_lot(lot_ref)
        currently = self.stock_remaining(lot.id)
        value = to_amount(weight)
        check_removal(lot, currently, value)
        facility = self.facility()
        at = at or utcnow()
        sample = LabSample(
            id=new_id("lab"), source_lot_id=lot.id, weight=value, unit=lot.unit,
            cmtl_id=cmtl_id.strip(), is_rnd=is_rnd, at=at, note=cmtl_note(cmtl_id),
        )
        self.conn.execute(
            "INSERT INTO lab_samples (id,source_lot_id,weight,unit,cmtl_id,is_rnd,at,created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (sample.id, lot.id, str(value), lot.unit, sample.cmtl_id, int(is_rnd), at.isoformat(), _now()),
        )
        self.conn.commit()
        self._move(lot.id, "lab_sample", value, lot.unit, note=sample.cmtl_id, at=at)
        self.ledger.append(
            "lab_sample_create",
            {
                "is_research_and_development": is_rnd, "source_ids": [lot.id],
                "removed_weight_or_volume": str(value), "unit": lot.unit, "cmtl_id": sample.cmtl_id,
                "facility_location": facility.id if facility else "",
            },
            at,
            facility_id=facility.id if facility else None,
        )
        return sample

    def final_product(
        self,
        lot_ref: str,
        *,
        upid: str,
        unit_count: int,
        net_weight,
        unit: str = "g",
        weight_per_unit=None,
        packaged_at: datetime,
        expiration,
        room: str,
        approved_name: str = "",
        product_type: str = "",
        at: datetime | None = None,
    ) -> "FinalProduct":
        from datetime import date as date_cls

        from .outage import new_id
        from .processing import (
            FinalProduct, amount as to_amount, check_expiration, check_removal, expiration_conflict, utcnow,
        )

        product = self.find_product(upid)
        if product is None:
            available = ", ".join(p.upid for p in self.products()) or "none yet"
            raise ValueError(
                f"unique product ID {upid!r} is not in the catalogue; add it first (catalogue: {available})"
            )
        lot = self.stock_lot(lot_ref)
        currently = self.stock_remaining(lot.id)
        net = to_amount(net_weight)
        check_removal(lot, currently, net)
        expiration_date = expiration if isinstance(expiration, date_cls) else date_cls.fromisoformat(str(expiration))
        check_expiration(packaged_at, expiration_date)
        existing = self.final_for(upid, packaged_at)
        conflict = expiration_conflict(existing, expiration_date)
        if conflict:
            raise ValueError(conflict)
        target = self._room_ref(room)
        facility = self.facility()
        at = at or utcnow()
        final = FinalProduct(
            id=new_id("fin"), lot_id=lot.id, upid=upid, product_type=product_type or product.product_type,
            cultivar=product.cultivar, unit_count=int(unit_count), net_weight=net, unit=unit,
            weight_per_unit=(to_amount(weight_per_unit) if weight_per_unit not in (None, "") else None),
            approved_name=approved_name or product.name, packaged_at=packaged_at,
            expiration_date=expiration_date, room_id=target.id,
        )
        self.conn.execute(
            "INSERT INTO final_products (id,lot_id,upid,product_type,cultivar,unit_count,net_weight,unit,"
            "weight_per_unit,approved_name,packaged_at,expiration_date,room_id,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (final.id, lot.id, final.upid, final.product_type, final.cultivar, final.unit_count,
             str(final.net_weight), final.unit,
             str(final.weight_per_unit) if final.weight_per_unit is not None else None,
             final.approved_name, packaged_at.isoformat(), expiration_date.isoformat(), target.id, _now()),
        )
        self.conn.commit()
        self._move(lot.id, "final", net, lot.unit, note=upid, at=at)
        self.ledger.append(
            "final_product",
            {
                "cultivar": final.cultivar, "product_type": final.product_type,
                "unit_count": final.unit_count, "expiration_date": expiration_date.isoformat(),
                "net_weight_or_volume": str(final.net_weight), "unit": final.unit,
                "approved_product_name": final.approved_name,
                "weight_per_unit": str(final.weight_per_unit) if final.weight_per_unit is not None else "",
                "packaged_at": packaged_at.isoformat(), "unique_product_id": final.upid,
                "facility_location": facility.id if facility else "", "room": target.id,
                "final_product_id": final.id,
            },
            at,
            facility_id=facility.id if facility else None,
        )
        return final

    def final_for(self, upid: str, packaged_at: datetime):
        row = self.conn.execute(
            "SELECT * FROM final_products WHERE upid = ? AND packaged_at = ?", (upid, packaged_at.isoformat())
        ).fetchone()
        if not row:
            return None
        return self._final_from_row(row)

    def add_device(
        self, *, inventory_type: str, unit_count: int, room: str, upid: str = "", at: datetime | None = None
    ) -> "Device":
        from .outage import new_id
        from .processing import Device, utcnow

        target = self._room_ref(room)
        facility = self.facility()
        at = at or utcnow()
        device = Device(
            id=new_id("dev"), upid=upid.strip(), inventory_type=inventory_type.strip(),
            unit_count=int(unit_count), room_id=target.id, at=at,
        )
        if device.unit_count <= 0:
            raise ValueError("a device inventory record needs a positive unit count")
        self.conn.execute(
            "INSERT INTO devices (id,upid,inventory_type,unit_count,room_id,at,created_at) VALUES (?,?,?,?,?,?,?)",
            (device.id, device.upid, device.inventory_type, device.unit_count, target.id, at.isoformat(), _now()),
        )
        self.conn.commit()
        self.ledger.append(
            "delivery_device_inventory",
            {
                "unique_product_id": device.upid, "inventory_type": device.inventory_type,
                "unit_count": device.unit_count, "facility_location": facility.id if facility else "",
                "room": target.id, "device_id": device.id,
            },
            at,
            facility_id=facility.id if facility else None,
        )
        return device

    # -- processing reads ----------------------------------------------------

    def cures(self) -> list["Cure"]:
        from .processing import Cure

        return [
            Cure(
                id=r["id"], harvest_id=r["harvest_id"], plant_ids=tuple(json.loads(r["plant_ids"])),
                post_weight=Decimal(r["post_weight"]), post_unit=r["post_unit"],
                waste_weight=Decimal(r["waste_weight"]), waste_unit=r["waste_unit"],
                room_id=r["room_id"], cured_at=datetime.fromisoformat(r["cured_at"]),
            )
            for r in self.conn.execute("SELECT * FROM cures ORDER BY cured_at, rowid")
        ]

    def samples(self) -> list["LabSample"]:
        from .processing import LabSample

        return [
            LabSample(
                id=r["id"], source_lot_id=r["source_lot_id"], weight=Decimal(r["weight"]), unit=r["unit"],
                cmtl_id=r["cmtl_id"], is_rnd=bool(r["is_rnd"]), at=datetime.fromisoformat(r["at"]),
            )
            for r in self.conn.execute("SELECT * FROM lab_samples ORDER BY at, rowid")
        ]

    def finals(self) -> list["FinalProduct"]:
        return [self._final_from_row(r) for r in self.conn.execute("SELECT * FROM final_products ORDER BY created_at")]

    def _final_from_row(self, r) -> "FinalProduct":
        from .processing import FinalProduct

        return FinalProduct(
            id=r["id"], lot_id=r["lot_id"], upid=r["upid"], product_type=r["product_type"],
            cultivar=r["cultivar"], unit_count=r["unit_count"], net_weight=Decimal(r["net_weight"]),
            unit=r["unit"], weight_per_unit=(Decimal(r["weight_per_unit"]) if r["weight_per_unit"] else None),
            approved_name=r["approved_name"], packaged_at=datetime.fromisoformat(r["packaged_at"]),
            expiration_date=date.fromisoformat(r["expiration_date"]), room_id=r["room_id"],
        )

    def devices(self) -> list["Device"]:
        from .processing import Device

        return [
            Device(
                id=r["id"], upid=r["upid"], inventory_type=r["inventory_type"],
                unit_count=r["unit_count"], room_id=r["room_id"], at=datetime.fromisoformat(r["at"]),
            )
            for r in self.conn.execute("SELECT * FROM devices ORDER BY at, rowid")
        ]

    # -- transport (S7) ------------------------------------------------------

    def register_vehicle(
        self, *, name: str, vin: str = "", plate: str = "", make: str = "", model: str = "",
        year: str = "", color: str = "", in_service: bool = True, at: datetime | None = None,
    ) -> "Vehicle":
        from .outage import new_id
        from .transport import Vehicle, utcnow

        if not (plate or "").strip():
            raise ValueError("a vehicle needs its license plate (s. 381.986(8)(g)1.f.)")
        at = at or utcnow()
        vehicle = Vehicle(
            id=new_id("veh"), name=name.strip() or plate.strip(), vin=vin.strip(), plate=plate.strip(),
            make=make.strip(), model=model.strip(), year=year.strip(), color=color.strip(),
            in_service=bool(in_service),
        )
        self.conn.execute(
            "INSERT INTO vehicles (id,name,vin,plate,make,model,year,color,in_service,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (vehicle.id, vehicle.name, vehicle.vin, vehicle.plate, vehicle.make, vehicle.model,
             vehicle.year, vehicle.color, int(vehicle.in_service), at.isoformat()),
        )
        self.conn.commit()
        self.ledger.append(
            "vehicle_register",
            {
                "vin": vehicle.vin, "license_plate": vehicle.plate, "make": vehicle.make,
                "model": vehicle.model, "year": vehicle.year, "color": vehicle.color,
                "vehicle_name": vehicle.name,
            },
            at,
        )
        return vehicle

    def vehicles(self) -> list["Vehicle"]:
        from .transport import Vehicle

        return [
            Vehicle(
                id=r["id"], name=r["name"], vin=r["vin"], plate=r["plate"], make=r["make"],
                model=r["model"], year=r["year"], color=r["color"], in_service=bool(r["in_service"]),
            )
            for r in self.conn.execute("SELECT * FROM vehicles ORDER BY created_at, rowid")
        ]

    def vehicle(self, ref: str) -> "Vehicle":
        for v in self.vehicles():
            if v.id == ref or v.id.startswith(ref) or v.plate.lower() == (ref or "").lower():
                return v
        raise ValueError(f"no vehicle matching {ref!r}; register one with `coontie vehicle`")

    def build_manifest(
        self,
        *,
        recipient_name: str,
        recipient_address: str,
        vehicle: str,
        employee_ids: tuple[str, ...],
        departure_at: datetime,
        arrival_at: datetime,
        items: list[tuple[str, object, str]],
        route: str = "",
        stops: tuple[str, ...] = (),
        invoice_id: str = "",
        at: datetime | None = None,
    ) -> "Manifest":
        """Build a manifest and its printable page. Refuses what the statute forbids."""
        from .outage import new_id
        from .transport import Manifest, ManifestItem, amount as to_amount, render_manifest, utcnow, validate_manifest

        facility = self.facility()
        if not facility:
            raise ValueError("no facility yet: run `coontie init` first")
        veh = self.vehicle(vehicle)
        parsed: list[ManifestItem] = []
        for lot_ref, quantity, form in items:
            lot = self.stock_lot(lot_ref)
            parsed.append(ManifestItem(lot_id=lot.id, quantity=to_amount(quantity), unit=lot.unit,
                                       form=(form or lot.kind).strip()))
        validate_manifest(
            recipient_name=recipient_name, recipient_address=recipient_address, vehicle=veh,
            employee_ids=employee_ids, departure_at=departure_at, arrival_at=arrival_at, items=parsed,
        )
        at = at or utcnow()
        manifest = Manifest(
            id=new_id("man"), facility_id=facility.id, recipient_name=recipient_name.strip(),
            recipient_address=recipient_address.strip(), vehicle_id=veh.id,
            employee_ids=tuple(e.strip() for e in employee_ids if (e or "").strip()),
            departure_at=departure_at, arrival_at=arrival_at, route=route.strip(),
            stops=tuple(s.strip() for s in stops if (s or "").strip()), invoice_id=invoice_id,
            status="built", created_at=at,
        )
        self.conn.execute(
            "INSERT INTO manifests (id,facility_id,recipient_name,recipient_address,vehicle_id,employee_ids,"
            "departure_at,arrival_at,route,stops,invoice_id,status,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (manifest.id, manifest.facility_id, manifest.recipient_name, manifest.recipient_address,
             manifest.vehicle_id, json.dumps(list(manifest.employee_ids)), departure_at.isoformat(),
             arrival_at.isoformat(), manifest.route, json.dumps(list(manifest.stops)), manifest.invoice_id,
             manifest.status, at.isoformat()),
        )
        for item in parsed:
            self.conn.execute(
                "INSERT INTO manifest_items (id,manifest_id,lot_id,quantity,unit,form) VALUES (?,?,?,?,?,?)",
                (new_id("mni"), manifest.id, item.lot_id, str(item.quantity), item.unit, item.form),
            )
        self.conn.commit()
        labels = {(i.lot_id): self._lot_label(i.lot_id) for i in parsed}
        page = render_manifest(
            manifest, facility_name=facility.name, facility_address=self._facility_address(facility),
            license_number=facility.license_number, vehicle=veh,
            items=[(i, labels[i.lot_id]) for i in parsed], crew=manifest.employee_ids,
        )
        path = self._write_artifact(f"manifest-{manifest.id}", "page", None, page)
        self.conn.execute("UPDATE manifests SET artifact_path = ? WHERE id = ?", (str(path), manifest.id))
        self.conn.commit()
        self.ledger.append(
            "manifest",
            {
                "driver_employee_ids": list(manifest.employee_ids), "stops": list(manifest.stops),
                "arrival_times": [arrival_at.isoformat()], "departure_times": [departure_at.isoformat()],
                "route_directions": manifest.route, "item_ids": [i.lot_id for i in parsed],
                "invoice_id": manifest.invoice_id, "creating_facility_location": manifest.facility_id,
                "vehicle_id": veh.id, "manifest_id": manifest.id, "artifact": str(path),
            },
            at,
            facility_id=manifest.facility_id,
        )
        return self.manifest(manifest.id)

    def _facility_address(self, facility) -> str:
        parts = [facility.street, facility.city, facility.state, facility.zip]
        return ", ".join(p for p in parts if p) or "(address not recorded)"

    def _lot_label(self, lot_id: str) -> str:
        """Identify the lot, never its original weight: the manifest's quantity is the item's."""
        lot = self.stock_lot(lot_id)
        return f"{lot.kind} {lot.cultivar}".strip() + f" (lot {lot.id})"

    def manifests(self) -> list["Manifest"]:
        from .transport import Manifest

        out = []
        for r in self.conn.execute("SELECT * FROM manifests ORDER BY created_at, rowid"):
            out.append(
                Manifest(
                    id=r["id"], facility_id=r["facility_id"], recipient_name=r["recipient_name"],
                    recipient_address=r["recipient_address"], vehicle_id=r["vehicle_id"],
                    employee_ids=tuple(json.loads(r["employee_ids"])),
                    departure_at=datetime.fromisoformat(r["departure_at"]),
                    arrival_at=datetime.fromisoformat(r["arrival_at"]), route=r["route"],
                    stops=tuple(json.loads(r["stops"])), invoice_id=r["invoice_id"], status=r["status"],
                    created_at=datetime.fromisoformat(r["created_at"]),
                )
            )
        return out

    def manifest(self, ref: str) -> "Manifest":
        for m in self.manifests():
            if m.id == ref or m.id.startswith(ref):
                return m
        raise ValueError(f"no manifest matching {ref!r}")

    def manifest_items(self, manifest_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM manifest_items WHERE manifest_id = ? ORDER BY rowid", (manifest_id,)
        )
        return [
            {"lot_id": r["lot_id"], "quantity": Decimal(r["quantity"]), "unit": r["unit"], "form": r["form"]}
            for r in rows
        ]

    def manifest_artifact(self, ref: str) -> Path:
        row = self.conn.execute("SELECT artifact_path FROM manifests WHERE id = ? OR id LIKE ?",
                                (ref, f"{ref}%")).fetchone()
        if not row or not row["artifact_path"]:
            raise ValueError(f"no manifest artifact for {ref!r}")
        return Path(row["artifact_path"])

    def dispatch_manifest(self, ref: str, *, at: datetime | None = None) -> "Manifest":
        """The transfer out: real time, and the weight leaves the lot."""
        from .processing import check_removal, utcnow
        from .transport import utcnow as _utcnow  # noqa: F401

        manifest = self.manifest(ref)
        if manifest.status != "built":
            raise ValueError(f"manifest {manifest.id} is {manifest.status}; it can only be dispatched once")
        at = at or utcnow()
        items = self.manifest_items(manifest.id)
        detail = []
        for item in items:
            lot = self.stock_lot(item["lot_id"])
            check_removal(lot, self.stock_remaining(lot.id), item["quantity"])
        for item in items:
            self._move(item["lot_id"], "transfer_out", item["quantity"], item["unit"],
                       note=f"manifest {manifest.id} to {manifest.recipient_name}", at=at)
            detail.append({"lot_id": item["lot_id"], "quantity": str(item["quantity"]), "unit": item["unit"]})
        self.conn.execute(
            "INSERT INTO transfers (id,manifest_id,direction,facility_id,at,detail,created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (f"trf-{uuid.uuid4().hex[:10]}", manifest.id, "out", manifest.facility_id, at.isoformat(),
             json.dumps(detail), _now()),
        )
        self.conn.execute("UPDATE manifests SET status = 'dispatched' WHERE id = ?", (manifest.id,))
        self.conn.commit()
        self.ledger.append(
            "transfer_out",
            {
                "item_ids": [i["lot_id"] for i in items], "manifest_id": manifest.id,
                "quantity": str(sum(i["quantity"] for i in items)),
                "unit": items[0]["unit"], "transferring_facility_location": manifest.facility_id,
            },
            at,
            facility_id=manifest.facility_id,
        )
        return self.manifest(manifest.id)

    def receive_manifest(
        self,
        ref: str,
        *,
        receiver_name: str,
        room: str,
        received: dict[str, str] | None = None,
        rejected: dict[str, str] | None = None,
        at: datetime | None = None,
    ) -> "Manifest":
        """The transfer in: real time, with what arrived and what was refused."""
        from .outage import new_id
        from .processing import amount as to_amount, utcnow

        manifest = self.manifest(ref)
        if manifest.status == "built":
            raise ValueError(f"manifest {manifest.id} was never dispatched; there is nothing to receive")
        if manifest.status == "received":
            raise ValueError(f"manifest {manifest.id} was already received")
        if not (receiver_name or "").strip():
            raise ValueError("the receiving party's name is required for the acknowledgment")
        target = self._room_ref(room)
        at = at or utcnow()
        items = self.manifest_items(manifest.id)
        detail = []
        for item in items:
            dispatched = item["quantity"]
            got = to_amount(received[item["lot_id"]]) if received and item["lot_id"] in received else dispatched
            lost = to_amount(rejected[item["lot_id"]]) if rejected and item["lot_id"] in rejected else Decimal("0")
            if got < 0 or lost < 0:
                raise ValueError("received and rejected quantities cannot be negative")
            if got > dispatched:
                raise ValueError(
                    f"{item['lot_id']}: {got} {item['unit']} received against {dispatched} dispatched"
                )
            if got + lost != dispatched:
                raise ValueError(
                    f"{item['lot_id']}: {dispatched} {item['unit']} dispatched but {got} received and {lost} "
                    f"rejected leaves {dispatched - got - lost} unaccounted; record the rejection or the loss"
                )
            detail.append(
                {"lot_id": item["lot_id"], "quantity": str(dispatched), "unit": item["unit"],
                 "received": str(got), "rejected": str(lost), "form": item["form"]}
            )
        source_by_lot = {i["lot_id"]: self.stock_lot(i["lot_id"]) for i in items}
        for entry in detail:
            if Decimal(entry["received"]) <= 0:
                continue
            source = source_by_lot[entry["lot_id"]]
            lot_id = new_id("stk")
            self.conn.execute(
                "INSERT INTO stock_lots (id,kind,cultivar,room_id,original,unit,harvest_ids,source_lot_id,created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (lot_id, source.kind, source.cultivar, target.id, entry["received"], entry["unit"],
                 json.dumps(list(source.harvest_ids)), source.id, at.isoformat()),
            )
        self.conn.commit()
        self.conn.execute(
            "INSERT INTO transfers (id,manifest_id,direction,facility_id,at,receiver_name,detail,created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (new_id("trf"), manifest.id, "in", manifest.facility_id, at.isoformat(), receiver_name.strip(),
             json.dumps(detail), _now()),
        )
        self.conn.execute("UPDATE manifests SET status = 'received' WHERE id = ?", (manifest.id,))
        self.conn.commit()
        self.ledger.append(
            "transfer_in",
            {
                "item_ids": [d["lot_id"] for d in detail], "manifest_id": manifest.id,
                "units_received": sum(int(Decimal(d["received"])) for d in detail),
                "units_rejected": sum(int(Decimal(d["rejected"])) for d in detail),
                "quantity_received": str(sum(Decimal(d["received"]) for d in detail)),
                "unit_received": detail[0]["unit"],
                "quantity_rejected": str(sum(Decimal(d["rejected"]) for d in detail)),
                "unit_rejected": detail[0]["unit"],
                "receiving_facility_location": target.id, "receiver": receiver_name.strip(),
            },
            at,
            facility_id=manifest.facility_id,
        )
        return self.manifest(manifest.id)

    def record_invoice(
        self, ref: str, *, buyer: str, seller: str, price, quantity, unit: str = "g", at: datetime | None = None
    ) -> str:
        from .outage import new_id
        from .processing import amount as to_amount, utcnow

        manifest = self.manifest(ref)
        at = at or utcnow()
        invoice_id = new_id("inv")
        self.conn.execute("UPDATE manifests SET invoice_id = ? WHERE id = ?", (invoice_id, manifest.id))
        self.conn.commit()
        self.ledger.append(
            "wholesale_invoice",
            {
                "item_ids": [i["lot_id"] for i in self.manifest_items(manifest.id)],
                "buyer_facility_location": buyer.strip(), "seller_facility_location": seller.strip(),
                "price": str(to_amount(price)), "quantity": str(to_amount(quantity)), "unit": unit,
                "invoice_id": invoice_id, "manifest_id": manifest.id,
            },
            at,
            facility_id=manifest.facility_id,
        )
        return invoice_id

    def transfers(self, manifest_id: str | None = None) -> list[dict]:
        sql = "SELECT * FROM transfers"
        args: tuple = ()
        if manifest_id:
            sql += " WHERE manifest_id = ?"
            args = (manifest_id,)
        sql += " ORDER BY at, rowid"
        return [
            {
                "id": r["id"], "manifest_id": r["manifest_id"], "direction": r["direction"],
                "at": datetime.fromisoformat(r["at"]), "receiver_name": r["receiver_name"],
                "detail": json.loads(r["detail"]),
            }
            for r in self.conn.execute(sql, args)
        ]

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

    def _department_id(self, lot_id: str) -> str:
        """The department's inventory identification number for a lot, or empty when it has none."""
        for table, column in (("lots", "sts_inventory_id"), ("stock_lots", "sts_inventory_id")):
            try:
                row = self.conn.execute(
                    f"SELECT {column} FROM {table} WHERE id = ?", (lot_id,)).fetchone()
            except sqlite3.OperationalError:
                continue
            if row and row[0]:
                return str(row[0])
        return ""

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
