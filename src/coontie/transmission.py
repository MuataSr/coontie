"""The outbox: what has not reached the department yet.

DH5059 gives every event type a window: twelve hours by default, real time for dispensing, refunds,
voids and both sides of a transfer. Coontie has no department credentials, so this module does the one
honest thing available: it says what is waiting, how old it is, and seals it into a file a person can
hand to an integrator today. It never says a record was delivered.

Spec: docs/flows/transmission.md.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import events as catalogue
from .compliance import EVENT_WINDOW

FORMAT = "coontie-envelope/1"
REALTIME = timedelta(0)
ADAPTERS = ("stub", "folder")
REPORTS_DIR = "reports"
TRANSMISSIONS_DIR = "transmissions"

PACKAGED = "packaged"
FAILED = "failed"
HANDED_OVER = "handed_over"
ABANDONED = "abandoned"


class OutboxError(Exception):
    """A hand-off that must not proceed, with a reason an operator can act on."""


@dataclass
class Owed:
    seq: int
    event: str
    title: str
    occurred_at: datetime
    due_at: datetime
    citation: str
    ref: str = ""

    def overdue(self, now: datetime) -> bool:
        return self.due_at <= now

    def age(self, now: datetime) -> timedelta:
        return now - self.occurred_at


@dataclass
class Package:
    id: str
    path: Path
    sha256: str
    first_seq: int
    last_seq: int
    events: int
    created_at: datetime
    state: str = PACKAGED
    adapter: str = ""
    reference: str = ""
    result: str = ""


def window_for(key: str) -> timedelta:
    """The catalogue's own window for an event key; not a second copy of the number."""
    spec = catalogue.BY_KEY.get(key)
    if spec is None:
        return EVENT_WINDOW
    return REALTIME if getattr(spec.timing, "value", spec.timing) == "realtime" else EVENT_WINDOW


def _transmitted(ws) -> set:
    """Sequence numbers a package has already carried, whether or not it was handed over."""
    rows = ws.conn.execute(
        "SELECT first_seq, last_seq FROM transmissions WHERE state IN (?, ?)",
        (PACKAGED, HANDED_OVER)).fetchall()
    covered = set()
    for first, last in rows:
        covered.update(range(int(first), int(last) + 1))
    return covered


def owed(ws, *, now: datetime | None = None, limit: int | None = None) -> list:
    """Every catalogue event the record holds and no package carries, newest last."""
    now = now or datetime.now(timezone.utc)
    taken = _transmitted(ws)
    out = []
    # oldest first: a queue that opens on the newest row hides the record that is already late
    for row in ws.conn.execute(
            "SELECT seq, event_key, occurred_at, payload FROM events ORDER BY occurred_at, seq"):
        seq, key, occurred, payload_text = int(row[0]), row[1], row[2], row[3]
        spec = catalogue.BY_KEY.get(key)
        if spec is None or seq in taken:
            continue
        when = datetime.fromisoformat(str(occurred))
        # a title alone cannot pick one row out of four identical ones, so the record's own id goes
        # in the queue beside it
        try:
            payload = json.loads(payload_text or "{}")
        except ValueError:
            payload = {}
        ref = next((str(payload[k]) for k in ("plant_id", "inventory_id", "lot_id", "manifest_id",
                                              "harvest_id", "batch_id") if payload.get(k)), "")
        out.append(Owed(seq=seq, event=key, title=spec.title, occurred_at=when,
                        due_at=when + window_for(key), citation=spec.citation,
                        ref=ref or f"#{seq}"))
        if limit and len(out) >= limit:
            break
    return out


def backlog(ws, *, now: datetime | None = None) -> dict:
    """One sentence's worth of numbers: how many are waiting, how old the oldest is, how many late."""
    now = now or datetime.now(timezone.utc)
    waiting = owed(ws, now=now)
    overdue = [item for item in waiting if item.overdue(now)]
    oldest = max((now - item.occurred_at for item in waiting), default=timedelta(0))
    handed = ws.conn.execute(
        "SELECT COUNT(*) FROM transmissions WHERE state = ?", (HANDED_OVER,)).fetchone()[0]
    return {"waiting": len(waiting), "overdue": len(overdue), "oldest": oldest,
            "handed_over": int(handed), "any_handed_over": bool(int(handed)),
            "next_due": min((item.due_at for item in waiting), default=None)}


def _reports_dir(ws) -> Path:
    return Path(ws.path).resolve().parent / REPORTS_DIR / TRANSMISSIONS_DIR


def _seal(body: dict) -> str:
    """The hash covers the body without the hash field, so a reader can recompute it."""
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def package(ws, *, at: datetime | None = None, limit: int | None = None,
            adapter: str = "stub") -> Package:
    """Seal what is owed into one file. Nothing leaves the machine."""
    at = at or datetime.now(timezone.utc)
    if adapter not in ADAPTERS:
        raise OutboxError(f"no adapter called {adapter!r}; this build has {', '.join(ADAPTERS)}")
    waiting = owed(ws, now=at, limit=limit)
    if not waiting:
        raise OutboxError("nothing is waiting to be sent, so there is nothing to seal")
    facility = ws.facility()
    head = ws.conn.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
    detail = []
    for item in waiting:
        row = ws.conn.execute("SELECT payload FROM events WHERE seq = ?", (item.seq,)).fetchone()
        detail.append({"seq": item.seq, "event": item.event, "occurred_at": item.occurred_at.isoformat(),
                       "due_at": item.due_at.isoformat(), "payload": json.loads(row[0])})
    body = {
        "format": FORMAT,
        "facility": facility.name if facility else "",
        "license": facility.license_number if facility else "",
        "created_at": at.isoformat(),
        "adapter": adapter,
        "first_seq": waiting[0].seq,
        "last_seq": waiting[-1].seq,
        "events": len(waiting),
        "chain_head": head[0] if head else "",
        "events_detail": detail,
    }
    digest = _seal(body)
    body["sha256"] = digest
    directory = _reports_dir(ws)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"envelope-{stamp}-{waiting[0].seq}-{waiting[-1].seq}.json"
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")

    from .amendments import new_id

    package_id = new_id("tx")
    ws.conn.execute(
        "INSERT INTO transmissions (id, envelope_path, envelope_sha256, first_seq, last_seq, events,"
        " state, adapter, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (package_id, str(path), digest, waiting[0].seq, waiting[-1].seq, len(waiting),
         PACKAGED, adapter, at.isoformat()),
    )
    ws.conn.commit()
    ws.ledger.append("transmission_packaged", {
        "envelope": path.name, "sha256": digest, "first_seq": waiting[0].seq,
        "last_seq": waiting[-1].seq, "events": len(waiting), "adapter": adapter,
        "chain_head": body["chain_head"],
    }, at)
    return Package(id=package_id, path=path, sha256=digest, first_seq=waiting[0].seq,
                   last_seq=waiting[-1].seq, events=len(waiting), created_at=at, adapter=adapter)


def packages(ws) -> list:
    rows = ws.conn.execute(
        "SELECT * FROM transmissions ORDER BY created_at DESC, rowid DESC").fetchall()
    return [Package(id=r["id"], path=Path(r["envelope_path"]), sha256=r["envelope_sha256"],
                    first_seq=int(r["first_seq"]), last_seq=int(r["last_seq"]),
                    events=int(r["events"]),
                    created_at=datetime.fromisoformat(r["created_at"]), state=r["state"],
                    adapter=r["adapter"] or "", reference=r["reference"] or "",
                    result=r["result"] or "") for r in rows]


# -- adapters -------------------------------------------------------------------------------------
@dataclass
class Result:
    accepted: bool
    state: str
    detail: str
    reference: str = ""


class StubAdapter:
    """The default. It refuses, because there is nothing configured to hand anything to."""

    name = "stub"

    def send(self, path: Path) -> Result:
        return Result(False, FAILED, "no adapter is configured; nothing was sent")


class FolderAdapter:
    """Hands the file to a directory. That is a hand-off, and the word delivery is not used."""

    name = "folder"

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def send(self, path: Path) -> Result:
        if not self.directory.is_dir():
            return Result(False, FAILED, f"{self.directory} is not a directory; nothing was handed over")
        target = self.directory / path.name
        target.write_bytes(path.read_bytes())
        return Result(True, HANDED_OVER,
                      f"handed over to {self.directory}; delivery is not confirmed",
                      reference=str(target))


def adapter_for(name: str, *, folder: str | Path | None = None):
    if name == "stub":
        return StubAdapter()
    if name == "folder":
        if not folder:
            raise OutboxError("the folder adapter needs --to <directory>")
        return FolderAdapter(folder)
    raise OutboxError(f"no adapter called {name!r}; this build has {', '.join(ADAPTERS)}")


def hand_over(ws, package_id: str, *, adapter, at: datetime | None = None) -> Package:
    """One hand-off per package. A retry is a new package, so the record shows two files."""
    at = at or datetime.now(timezone.utc)
    row = ws.conn.execute("SELECT * FROM transmissions WHERE id = ?", (package_id,)).fetchone()
    if row is None:
        raise OutboxError(f"no package {package_id!r}")
    if row["state"] != PACKAGED:
        raise OutboxError(f"package {package_id} is {row['state']}; one hand-off per package, "
                          f"so seal a new one to try again")
    path = Path(row["envelope_path"])
    if not path.exists():
        raise OutboxError(f"{path.name} is gone; a package that no longer exists cannot be handed over")
    data = path.read_bytes()
    if hashlib.sha256(json.dumps(
            {k: v for k, v in json.loads(data).items() if k != "sha256"}, sort_keys=True
    ).encode()).hexdigest() != row["envelope_sha256"]:
        raise OutboxError(f"{path.name} no longer matches the hash recorded when it was sealed")

    result = adapter.send(path)
    ws.conn.execute(
        "UPDATE transmissions SET state = ?, result = ?, reference = ?, attempt_at = ? WHERE id = ?",
        (result.state, result.detail, result.reference, at.isoformat(), package_id))
    ws.conn.commit()
    ws.ledger.append("transmission_attempted", {
        "package": package_id, "envelope": path.name, "adapter": getattr(adapter, "name", "?"),
        "accepted": result.accepted, "result": result.detail, "reference": result.reference,
        "first_seq": int(row["first_seq"]), "last_seq": int(row["last_seq"]),
    }, at)
    return next(p for p in packages(ws) if p.id == package_id)


def abandon(ws, package_id: str, *, reason: str, at: datetime | None = None) -> Package:
    """Withdraw a package with a reason. The events return to owed; nothing is deleted."""
    if not (reason or "").strip():
        raise OutboxError("abandoning a package needs a reason; the record keeps the file and the why")
    row = ws.conn.execute("SELECT * FROM transmissions WHERE id = ?", (package_id,)).fetchone()
    if row is None:
        raise OutboxError(f"no package {package_id!r}")
    if row["state"] != PACKAGED:
        raise OutboxError(f"package {package_id} is {row['state']}; only a sealed package can be "
                          f"withdrawn")
    at = at or datetime.now(timezone.utc)
    ws.conn.execute("UPDATE transmissions SET state = ?, result = ?, attempt_at = ? WHERE id = ?",
                    (ABANDONED, reason.strip(), at.isoformat(), package_id))
    ws.conn.commit()
    ws.ledger.append("transmission_abandoned", {
        "package": package_id, "envelope": Path(row["envelope_path"]).name,
        "reason": reason.strip(), "first_seq": int(row["first_seq"]),
        "last_seq": int(row["last_seq"]),
    }, at)
    return next(p for p in packages(ws) if p.id == package_id)
