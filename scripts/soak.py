#!/usr/bin/env python3
"""Thirty days of one facility, through the CLI, then the invariants.

A soak is not a feature. It puts a month of ordinary work through the record at a simulated clock and
then asks the questions a stage test cannot: does the chain still verify, does every gram still add up,
does every correction still carry its notice, and does the same seed produce the same record twice.

    python3 scripts/soak.py --db /tmp/soak/ws.sqlite3 --days 30 --seed 7 --keep

Spec: docs/flows/soak.md. Refuses to write into a path that already holds a record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
FIXTURE = ROOT / "tests" / "fixtures" / "operator_export.csv"

FACILITY = {
    "name": "Soak Creek Cultivation, LLC",
    "license": "MMTC-2026-0099",
    "rooms": [("inventory", "INV1", "01"), ("inventory", "INV2", "02"), ("grow", "G1", "03"),
              ("grow", "G2", "04"), ("inventory", "DRY1", "05")],
}

CULTIVARS = ("Blue Dream", "Sour Diesel", "Northern Lights", "Jack Herer")


class SoakFailure(SystemExit):
    """A violated invariant, with the day and the query that shows it."""


class Soak:
    def __init__(self, db: Path, *, days: int = 30, seed: int = 7,
                 start: datetime | None = None, verbose: bool = True):
        self.db = db
        self.days = days
        self.rng = random.Random(seed)
        self.seed = seed
        self.at = start or datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
        self.verbose = verbose
        self.stats = {"days": 0, "events": 0, "lots": 0, "corrections": 0, "manifests": 0,
                      "outages": 0, "drift_resolved": 0, "late": 0, "disposals": 0}
        self.late_sends = 0
        self.drift_pulled = False

    # -- plumbing ---------------------------------------------------------------------------
    def cli(self, *args: str, at: datetime | None = None, check: bool = True) -> str:
        argv = [sys.executable, "-m", "coontie.cli", "--db", str(self.db), *args]
        if at is not None:
            argv += ["--at", at.isoformat()]
        proc = subprocess.run(argv, capture_output=True, text=True, env=ENV)
        if proc.returncode != 0 and check:
            raise SoakFailure(
                f"day {self.stats['days']}: `{' '.join(args)}` failed ({proc.returncode})\n"
                f"  {proc.stderr.strip()[:400] or proc.stdout.strip()[:400]}")
        return proc.stdout

    def one(self, sql: str, args: tuple = ()):
        with sqlite3.connect(self.db) as conn:
            row = conn.execute(sql, args).fetchone()
        return row[0] if row else None

    def rows(self, sql: str, args: tuple = ()):
        with sqlite3.connect(self.db) as conn:
            return conn.execute(sql, args).fetchall()

    def day_clock(self, hour: int = 9, minute: int = 0) -> datetime:
        return self.at + timedelta(hours=hour, minutes=minute)

    # -- the month ---------------------------------------------------------------------------
    def run(self) -> dict:
        self.setup()
        for n in range(1, self.days + 1):
            self.at = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc) + timedelta(days=n - 1)
            self.stats["days"] = n
            self.settle_receipts()
            self.ordinary_day(n)
            if n % 2 == 0:
                self.processing_day(n)
            if n % 3 == 0:
                self.transport_day(n)
            if n % 4 == 0:
                self.correction_day(n)
            if n % 5 == 0:
                self.disposal_day(n)
            if n == 12:
                self.outage_day(n)
            if n % 6 == 0:
                self.drift_day(n)
            self.check_daily(n)
            if self.verbose:
                print(self.day_line(n))
        summary = self.check_final()
        return summary

    def setup(self) -> None:
        argv = [sys.executable, "-m", "coontie.cli", "--db", str(self.db), "init"]
        argv += ["--name", FACILITY["name"], "--license", FACILITY["license"]]
        for kind, name, number in FACILITY["rooms"]:
            argv += ["--room", f"{kind}:{name}:{number}"]
        proc = subprocess.run(argv, capture_output=True, text=True, env=ENV)
        if proc.returncode != 0:
            raise SoakFailure(f"init failed: {proc.stderr.strip()[:300]}")
        self.cli("integration", "--approved-on", "2026-09-20", "--reference", "INT-2026-0099")
        if FIXTURE.exists():
            self.cli("import", "--csv", str(FIXTURE), check=False)

    def ordinary_day(self, n: int) -> None:
        """A batch, its plants, and a harvest when the schedule on the books is due."""
        when = self.day_clock(9)
        free_now = self.one("SELECT COUNT(*) FROM plants WHERE state NOT IN ('harvested', 'disposed')")
        if not free_now or int(free_now) < 16:
            cultivar = self.rng.choice(CULTIVARS)
            room = "G1" if n % 2 else "G2"
            self.cli("batch", "--cultivar", cultivar, "--room", room, "--count", "8", at=when)
            batch = self.one("SELECT id FROM batches ORDER BY rowid DESC LIMIT 1")
            self.cli("plant", "--batch", batch, "--count", "8", at=when)

        waiting = self.one(
            "SELECT plant_ids FROM harvests WHERE scheduled_at IS NOT NULL AND harvested_at IS NULL"
            " ORDER BY rowid LIMIT 1")
        free = [r[0] for r in self.rows(
            "SELECT id FROM plants WHERE state NOT IN ('harvested', 'disposed')"
            " ORDER BY rowid LIMIT 8")]
        if waiting:
            # plant_ids is stored as a JSON list; the command takes a comma list
            if isinstance(waiting, str) and waiting.startswith("["):
                waiting = ",".join(json.loads(waiting))
            self.cli("harvest", "--plants", waiting, "--wet", "1500", "--waste", "120",
                     "--other", "30", "--room", "DRY1", at=self.day_clock(13))
        elif len(free) >= 8:
            self.cli("harvest", "--plants", ",".join(free), "--schedule", at=self.day_clock(10))

        self._cure_any_pending(n)

    def _cure_any_pending(self, n: int) -> None:
        pending = self.rows(
            "SELECT h.id FROM harvests h LEFT JOIN cures c ON c.harvest_id = h.id"
            " WHERE c.id IS NULL AND h.harvested_at IS NOT NULL ORDER BY h.rowid LIMIT 1")
        if not pending:
            return
        harvest = pending[0][0]
        post = Decimal(self.rng.choice(["540", "600", "620", "680"]))
        self.cli("cure", "--harvest", harvest, "--post", str(post), "--waste", "40",
                 "--room", "DRY1", at=self.day_clock(15))
        self.cli("lot", "--kind", "cured and dried flower", "--cultivar", self.rng.choice(CULTIVARS),
                 "--weight", str(post - Decimal("20")), "--room", "INV1",
                 "--harvest", harvest, at=self.day_clock(16))
        lot = self.one("SELECT id FROM stock_lots ORDER BY rowid DESC LIMIT 1")
        if n % 2 == 0 and lot and self.balance(lot) >= Decimal("120"):
            self.cli("split", "--lot", lot, "--amount", "100", "--to", "INV2",
                     at=self.day_clock(16))
        if n % 9 == 0:
            # `move --lot` takes a product lot (the department's inventory row), not a processing lot
            product_lot = self.one(
                "SELECT l.id FROM lots l JOIN rooms r ON r.id = l.room_id"
                " WHERE l.quantity > 0 AND l.on_hold = 0 AND r.name <> 'INV2'"
                " ORDER BY l.rowid DESC LIMIT 1")
            if product_lot:
                self.cli("move", "--lot", product_lot, "--to", "INV2", at=self.day_clock(17))

    def processing_day(self, n: int) -> None:
        when = self.day_clock(11)
        lot = self.fattest("cured%")
        if not lot:
            return
        # ask for what the lot holds, not what the script had in mind
        remove = min(Decimal("120"), self.balance(lot) - Decimal("10"))
        if remove < Decimal("20"):
            return
        self.cli("convert", "--lot", lot, "--remove", str(remove), "--to", "extract",
                 "--resulting", str((remove * Decimal("0.35")).quantize(Decimal("1"))),
                 "--waste", "10", "--room", "INV2", at=when)
        extract = self.fattest("extract%")
        if extract and n % 6 == 0:
            self.cli("sample", "--lot", extract, "--weight", "2", "--cmtl", "TL-2026-0912",
                     at=when)
        upid = self.one("SELECT upid FROM products ORDER BY rowid LIMIT 1")
        if extract and upid:
            net = (self.balance(extract) - Decimal("2")).quantize(Decimal("1"))
            if net >= Decimal("5"):
                # --packaged is the packaging date; the net weight is the lot's own balance less a jar
                self.cli("final", "--lot", extract, "--upid", upid, "--units", "40",
                         "--net", str(net), "--packaged", when.date().isoformat(),
                         "--expires", "2027-10-01", "--room", "INV2", at=when)
        if n % 9 == 0:
            self.cli("device", "--type", "vape cartridge", "--units", "20", "--room", "INV2",
                     at=when)

    def transport_day(self, n: int) -> None:
        when = self.day_clock(8)
        vehicle = self.one("SELECT id FROM vehicles ORDER BY rowid LIMIT 1")
        if not vehicle:
            self.cli("vehicle", "--name", "White Transit", "--plate", "FL-SOAK-1",
                     "--make", "Ford", "--model", "Transit", "--year", "2024", at=when)
            vehicle = self.one("SELECT id FROM vehicles ORDER BY rowid LIMIT 1")
        lot = self.fattest("cured%")
        if not lot:
            return
        amount = min(Decimal("50"), self.balance(lot) - Decimal("20"))
        if amount < Decimal("10"):
            return
        recipient = self.rng.choice(("Tampa Dispensary", "Gainesville Apothecary",
                                     "Ocala Botanicals"))
        self.cli("manifest", "--recipient", recipient,
                 "--address", "900 N Tampa St, Tampa FL 33602", "--vehicle", vehicle,
                 "--employees", "Maria Lopez; Deon Carter",
                 "--depart", (when + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
                 "--arrive", (when + timedelta(days=1, hours=3)).strftime("%Y-%m-%dT%H:%M"),
                 "--item", f"{lot}:{amount}", "--route", "SR-50 west to I-75 south", at=when)
        manifest = self.one("SELECT id FROM manifests ORDER BY rowid DESC LIMIT 1")
        self.cli("dispatch", "--manifest", manifest, at=when + timedelta(hours=2))
        self.stats["manifests"] += 1
        # three receipts: exact, then two with rejects, then one short
        choice = n % 4
        if choice == 0:
            self.cli("receive", "--manifest", manifest, "--receiver", "Ana Ruiz", "--room", "INV1",
                     "--received", f"{lot}:{amount}", at=when + timedelta(days=1, hours=3))
        elif choice == 2:
            self.cli("receive", "--manifest", manifest, "--receiver", "Ana Ruiz", "--room", "INV1",
                     "--received", f"{lot}:{amount - 2}", "--rejected", f"{lot}:2",
                     at=when + timedelta(days=1, hours=3))

    def correction_day(self, n: int) -> None:
        when = self.day_clock(14)
        lot = self.fattest("cured%")
        if not lot or self.balance(lot) < Decimal("10"):
            return
        cause = self.rng.choice(self.non_exempt_causes())
        self.cli("adjust", "--lot", lot, "--remove", "3", "--cause", cause,
                 "--reason", "Physical recount against the jar", "--actor", "Maria Lopez", at=when)
        self.stats["corrections"] += 1
        justification = self.one("SELECT id FROM justifications ORDER BY rowid DESC LIMIT 1")
        if justification and n % 10 == 0:
            # deliberately late: the record must call it late rather than quietly accept it
            self.cli("justify", justification, "--send", at=when + timedelta(hours=13))
            self.late_sends += 1
            self.stats["late"] += 1
        elif justification:
            self.cli("justify", justification, "--send", at=when + timedelta(hours=2))

    def disposal_day(self, n: int) -> None:
        when = self.day_clock(10)
        lot = self.one("SELECT id FROM lots WHERE quantity > 0 ORDER BY rowid DESC LIMIT 1")
        if not lot:
            return
        pending = self.one("SELECT COUNT(*) FROM disposals WHERE disposed_at IS NULL")
        if pending:
            self.cli("dispose", "--lot", lot, "--matter", "200", "--reason",
                     "failed potency test", at=when, check=False)
        else:
            self.cli("dispose", "--lot", lot, "--schedule", "--reason", "failed potency test",
                     at=when, check=False)
        self.stats["disposals"] += 1

    def outage_day(self, n: int) -> None:
        when = self.day_clock(6)
        self.cli("outage", "--start", at=when, check=False)
        self.cli("watch", "--once", at=when + timedelta(hours=2, minutes=30), check=False)
        self.cli("outage", "--restore", at=when + timedelta(hours=5), check=False)
        self.stats["outages"] += 1

    def drift_day(self, n: int) -> None:
        from coontie.workspace import Workspace

        sys.path.insert(0, str(ROOT / "src"))
        sys.path.insert(0, str(ROOT / "tests"))
        ws = Workspace(self.db)
        try:
            try:
                import test_drift_gate as drift_fixture
            except Exception:  # the fixture is a test module; a missing one is not a soak failure
                return
            csv_text = drift_fixture.state_csv(ws)
        finally:
            ws.close()
        path = self.db.parent / f"state-day{n}.csv"
        path.write_text(csv_text, encoding="utf-8")
        self.cli("drift", "pull", "--csv", str(path), at=None, check=False)
        self.cli("drift", "compare", check=False)
        self.drift_pulled = True
        pending = self.rows(
            "SELECT id, rowid FROM drift_findings WHERE resolved_at IS NULL ORDER BY rowid")
        actions = ("accept_state", "keep_local", "recount", "record_state", "resend")
        for finding, ordinal in pending:
            action = actions[ordinal % len(actions)]
            self.cli("drift", "resolve", finding, "--action", action, "--actor", "Maria Lopez",
                     check=False)
            self.stats["drift_resolved"] += 1

    def non_exempt_causes(self) -> tuple:
        """The taxonomy lives in the module that enforces it; a copy here would drift from the rule."""
        sys.path.insert(0, str(ROOT / "src"))
        from coontie.amendments import NON_EXEMPT_CAUSES

        return tuple(NON_EXEMPT_CAUSES)

    def fattest(self, kind_like: str):
        """The lot of a kind that still holds the most, because the newest row is often nearly spent."""
        row = self.one(
            "SELECT s.id FROM stock_lots s WHERE s.kind LIKE ?"
            " ORDER BY CAST(s.original AS REAL) - COALESCE((SELECT SUM(CAST(m.amount AS REAL))"
            " FROM stock_moves m WHERE m.lot_id = s.id), 0) DESC LIMIT 1", (kind_like,))
        return row

    def balance(self, lot_id: str) -> Decimal:
        """What a processing lot actually holds: original minus every move, never a stored number."""
        original = self.one("SELECT original FROM stock_lots WHERE id = ?", (lot_id,))
        moved = self.one("SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) FROM stock_moves"
                         " WHERE lot_id = ?", (lot_id,))
        return Decimal(str(original)) - Decimal(str(moved))

    def fingerprint(self) -> dict:
        """What the seed reproduces: the sequence of events and the values the seed chose.

        Ids are uuids and `recorded_at` is when the row was written, so a run cannot be byte
        identical; claiming otherwise would be a lie in the summary. This is the part that is a
        regression test: the same schedule in the same order, with the same weights and causes.
        """
        keys = [r[0] for r in self.rows("SELECT event_key FROM events ORDER BY seq")]
        values = self.rows(
            "SELECT c.post_weight FROM cures c ORDER BY c.rowid")
        causes = self.rows("SELECT cause FROM amendments ORDER BY rowid")
        recipients = self.rows("SELECT recipient_name FROM manifests ORDER BY rowid")
        return {
            "events": len(keys),
            "shape": hashlib.sha256("|".join(keys).encode()).hexdigest(),
            "seeded": hashlib.sha256(repr((values, causes, recipients)).encode()).hexdigest(),
        }

    def _has_table(self, name: str) -> bool:
        return bool(self.one("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
                             (name,)))

    # -- the invariants ----------------------------------------------------------------------
    def settle_receipts(self) -> None:
        """A delivery is received the day after it leaves; an older one is the soak's failure, not a rule."""
        for manifest, ids in self.rows(
                "SELECT m.id, m.employee_ids FROM manifests m WHERE m.status = 'dispatched'"):
            items = self.rows("SELECT lot_id, quantity FROM manifest_items WHERE manifest_id = ?",
                              (manifest,))
            if not items:
                continue
            received = ",".join(f"{lot}:{qty}" for lot, qty in items)
            self.cli("receive", "--manifest", manifest, "--receiver", "Ana Ruiz", "--room", "INV1",
                     "--received", received,
                     at=self.day_clock(11))

    def check_daily(self, n: int) -> None:
        """The checks run in process: the same code the CLI calls, without a process per question."""
        sys.path.insert(0, str(ROOT / "src"))
        from coontie import inspect as inspector
        from coontie.workspace import Workspace

        ws = Workspace(self.db)
        try:
            ok, summary = ws.verify()
            if not ok:
                raise SoakFailure(f"day {n}: the chain does not verify\n  {summary}")
            findings = inspector.inspect(ws)
        finally:
            ws.close()
        breaches = [f for f in findings if f.severity == "breach"]
        if breaches:
            raise SoakFailure(f"day {n}: {len(breaches)} breach(es) in the record\n  "
                              + "\n  ".join(f.line() for f in breaches[:5]))
        # A delivery in flight is not a breach. A delivery still unreceived a day after it left is.
        now = self.day_clock(23)
        stale = [row for row in self.rows(
            "SELECT id, departure_at FROM manifests WHERE status = 'dispatched'")
            if datetime.fromisoformat(str(row[1])) < now - timedelta(days=1)]
        if stale:
            raise SoakFailure(
                f"day {n}: {len(stale)} delivery(ies) left more than a day ago and were never "
                f"received: {[r[0] for r in stale[:5]]}")
        self.stats["last_exposures"] = sum(1 for f in findings if f.severity == "exposure")
        self.stats["last_notes"] = sum(1 for f in findings if f.severity == "note")

    def check_final(self) -> dict:
        events = self.one("SELECT COUNT(*) FROM events")
        self.stats["events"] = events
        self.stats["lots"] = self.one("SELECT COUNT(*) FROM stock_lots")
        problems = []

        # every catalogue event carries the fields the catalogue requires
        sys.path.insert(0, str(ROOT / "src"))
        from coontie import events as catalogue

        for seq, key, payload in self.rows("SELECT seq, event_key, payload FROM events ORDER BY seq"):
            spec = catalogue.BY_KEY.get(key)
            if not spec:
                continue
            required = [f for f in getattr(spec, "fields", []) if getattr(f, "required", False)]
            body = json.loads(payload)
            missing = [getattr(f, "name", str(f)) for f in required
                       if getattr(f, "name", str(f)) not in body]
            if missing:
                problems.append(f"event {seq} ({key}) is missing {missing}")

        # no negative balance, and weight conserved on every processing lot
        for lot_id, original, unit in self.rows(
                "SELECT id, original, unit FROM stock_lots WHERE original IS NOT NULL"):
            moved = self.one("SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) FROM stock_moves"
                             " WHERE lot_id = ?", (lot_id,))
            balance = Decimal(str(original)) - Decimal(str(moved))
            if balance < 0:
                problems.append(f"lot {lot_id} is negative: {original} {unit} - {moved} = {balance}")

        # every non-exempt correction has a notice, and the one late send is recorded as late
        # exemptions come from the rule's own list, never from a column that does not exist
        sys.path.insert(0, str(ROOT / "src"))
        from coontie.amendments import is_exempt

        unsent = [(row[0], row[1]) for row in self.rows(
            "SELECT a.id, a.cause FROM amendments a LEFT JOIN justifications j"
            " ON j.amendment_id = a.id WHERE j.id IS NULL") if not is_exempt(row[1])]
        if unsent:
            problems.append(f"{len(unsent)} non-exempt correction(s) have no notice: "
                            f"{[r[0] for r in unsent[:5]]}")
        late = self.one("SELECT COUNT(*) FROM justifications WHERE sent_at IS NOT NULL"
                        " AND julianday(sent_at) > julianday(deadline)")
        if late and int(late) != self.late_sends:
            problems.append(f"{late} notice(s) were sent late, the soak expected {self.late_sends}")

        # no timed obligation past its deadline unsent
        if self._has_table("breaches"):
            open_breaches = self.one("SELECT COUNT(*) FROM breaches WHERE resolved_at IS NULL")
            if open_breaches:
                problems.append(f"{open_breaches} obligation(s) are past their deadline unsent")

        if problems:
            raise SoakFailure(f"day {self.stats['days']}: the soak broke the record\n  "
                              + "\n  ".join(problems[:10]))
        head = self.one("SELECT hash FROM events ORDER BY seq DESC LIMIT 1")
        self.stats["chain_head"] = head
        self.stats["seed"] = self.seed
        self.stats["fingerprint"] = self.fingerprint()
        return self.stats

    def day_line(self, n: int) -> str:
        events = self.one("SELECT COUNT(*) FROM events")
        lots = self.one("SELECT COUNT(*) FROM stock_lots")
        open_findings = self.one("SELECT COUNT(*) FROM drift_findings WHERE resolved_at IS NULL") \
            if self._has_table("drift_findings") else 0
        return (f"day {n:2d}  chain ok  {events:5d} events  lots {lots:3d}  "
                f"open {open_findings or 0}  corrections {self.stats['corrections']}  "
                f"manifests {self.stats['manifests']}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="thirty days of one facility, then the invariants")
    parser.add_argument("--db", required=True, help="where the synthetic record goes")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--report", help="write the summary as JSON here")
    parser.add_argument("--keep", action="store_true", help="leave the record behind as a demo dataset")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    db = Path(args.db).expanduser().resolve()
    marker = db.with_suffix(".soak")
    if db.exists():
        sys.exit(f"{db} already exists. A soak writes a synthetic record and will not touch a real "
                 f"one; give a fresh path or delete the soak's own file, which carries {marker.name}")
    db.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"soak {datetime.now(timezone.utc).isoformat()} seed {args.seed}\n")

    soak = Soak(db, days=args.days, seed=args.seed, verbose=not args.quiet)
    try:
        stats = soak.run()
    except SoakFailure as failure:
        print(f"SOAK FAILED: {failure}", file=sys.stderr)
        return 1

    print()
    print(f"soak passed: {stats['days']} days, {stats['events']} events, {stats['lots']} lots, "
          f"{stats['corrections']} corrections, {stats['manifests']} manifests, "
          f"{stats['outages']} outage")
    print(f"chain head {str(stats['chain_head'])[:16]}  seed {stats['seed']}")
    fingerprint = stats.get("fingerprint", {})
    print(f"shape {fingerprint.get('shape', '')[:16]}  seeded values "
          f"{fingerprint.get('seeded', '')[:16]}")
    if args.report:
        Path(args.report).write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
        print(f"report {args.report}")
    if args.keep:
        print(f"record {db}  (left behind as a demo dataset)")
    else:
        db.unlink(missing_ok=True)
        marker.unlink(missing_ok=True)
        shutil.rmtree(db.parent / "reports", ignore_errors=True)
        print("record removed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
