"""Append-only event ledger for an internal STS.

Two rules drive this design:

* Rule 64-4.222(4): every record is retained 3 years and the native data must be
  producible as CSV within 48 hours of a department request.
* Rule 64-4.222(11): the system must state the precise location of marijuana at
  all times, which means the ledger must be reconstructable, not just current.

So: no updates, no deletes, one hash-chained row per event, and an export that
the operator can hand over as-is. A tampered row breaks the chain loudly.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key    TEXT NOT NULL,
    occurred_at  TEXT NOT NULL,
    recorded_at  TEXT NOT NULL,
    facility_id  TEXT,
    payload      TEXT NOT NULL,
    prev_hash    TEXT NOT NULL,
    hash         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_key ON events(event_key);
CREATE INDEX IF NOT EXISTS idx_events_occurred ON events(occurred_at);
"""


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _hash(prev_hash: str, event_key: str, occurred_at: str, recorded_at: str, payload_json: str) -> str:
    body = "|".join((prev_hash, event_key, occurred_at, recorded_at, payload_json))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LedgerEntry:
    seq: int
    event_key: str
    occurred_at: str
    recorded_at: str
    facility_id: str | None
    payload: dict
    prev_hash: str
    hash: str


class Ledger:
    """A single MMTC facility's event ledger."""

    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # -- writes ---------------------------------------------------------------

    def append(
        self,
        event_key: str,
        payload: dict,
        occurred_at: datetime,
        recorded_at: datetime | None = None,
        facility_id: str | None = None,
    ) -> LedgerEntry:
        recorded_at = recorded_at or datetime.now(timezone.utc)
        occurred_s = occurred_at.astimezone(timezone.utc).isoformat()
        recorded_s = recorded_at.astimezone(timezone.utc).isoformat()
        payload_json = _canonical(payload)

        row = self.conn.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        prev = row["hash"] if row else GENESIS
        digest = _hash(prev, event_key, occurred_s, recorded_s, payload_json)

        cur = self.conn.execute(
            "INSERT INTO events (event_key, occurred_at, recorded_at, facility_id, payload, prev_hash, hash)"
            " VALUES (?,?,?,?,?,?,?)",
            (event_key, occurred_s, recorded_s, facility_id, payload_json, prev, digest),
        )
        self.conn.commit()
        return LedgerEntry(
            seq=cur.lastrowid,
            event_key=event_key,
            occurred_at=occurred_s,
            recorded_at=recorded_s,
            facility_id=facility_id,
            payload=payload,
            prev_hash=prev,
            hash=digest,
        )

    # -- reads ----------------------------------------------------------------

    def entries(self, event_key: str | None = None) -> list[LedgerEntry]:
        sql = "SELECT * FROM events"
        args: tuple = ()
        if event_key:
            sql += " WHERE event_key = ?"
            args = (event_key,)
        sql += " ORDER BY seq"
        return [
            LedgerEntry(
                seq=r["seq"],
                event_key=r["event_key"],
                occurred_at=r["occurred_at"],
                recorded_at=r["recorded_at"],
                facility_id=r["facility_id"],
                payload=json.loads(r["payload"]),
                prev_hash=r["prev_hash"],
                hash=r["hash"],
            )
            for r in self.conn.execute(sql, args)
        ]

    def latest(self, event_key: str, where=None) -> LedgerEntry | None:
        for entry in reversed(self.entries(event_key)):
            if where is None or where(entry):
                return entry
        return None

    # -- integrity ------------------------------------------------------------

    def verify_chain(self) -> tuple[bool, str]:
        prev = GENESIS
        for r in self.conn.execute("SELECT * FROM events ORDER BY seq"):
            expected = _hash(prev, r["event_key"], r["occurred_at"], r["recorded_at"], r["payload"])
            if r["prev_hash"] != prev or r["hash"] != expected:
                return False, f"chain breaks at seq {r['seq']} ({r['event_key']})"
            prev = r["hash"]
        return True, "ok"

    # -- export (PROC-5) ------------------------------------------------------

    def export_csv(self, path: str | Path | None = None) -> str:
        """Flatten the ledger to native CSV for a department request."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        cols: list[str] = []
        rows = self.entries()
        for entry in rows:
            for k in entry.payload:
                if k not in cols:
                    cols.append(k)
        writer.writerow(
            ["seq", "event_key", "occurred_at", "recorded_at", "facility_id", *cols, "prev_hash", "hash"]
        )
        for entry in rows:
            writer.writerow(
                [
                    entry.seq,
                    entry.event_key,
                    entry.occurred_at,
                    entry.recorded_at,
                    entry.facility_id or "",
                    *[entry.payload.get(c, "") for c in cols],
                    entry.prev_hash,
                    entry.hash,
                ]
            )
        text = buf.getvalue()
        if path:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def close(self) -> None:
        self.conn.close()
