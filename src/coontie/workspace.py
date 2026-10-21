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
    from .outage import Outage

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
                path = self._write_artifact(outage.id, "notice", subject, body)
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
                notice_path = self._write_artifact(fresh.id, "restoration", subject, body)
                csv_path = self._write_artifact(fresh.id, "dispensations", None, csv_text, suffix=".csv")
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

    def _write_artifact(self, outage_id: str, kind: str, subject: str | None, body: str, suffix: str = ".txt") -> Path:
        directory = Path(self.path).resolve().parent / "reports"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"outage-{outage_id}-{kind}{suffix}"
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
