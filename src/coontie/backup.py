"""Backup, verify, restore and the drill.

The record is one SQLite file plus a directory of artifacts. A backup is both, copied at one instant,
with a manifest that proves the copy is the same record and not a plausible-looking one. See
`docs/flows/backup.md` for the four guarantees and the reason restore is not a screen.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

FORMAT = "coontie-backup/1"
TOOL = "coontie 0.1"
REPORTS_DIR = "reports"


class BackupError(Exception):
    """A backup or restore that must not proceed, with the reason an operator can act on."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_state(db_path: Path) -> dict:
    """Event count, chain head, facility and licence, read without opening a Workspace."""
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        events = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        row = connection.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        head = row[0] if row else ""
        facility = connection.execute("SELECT name FROM facilities LIMIT 1").fetchone()
        licence = connection.execute(
            "SELECT license_number FROM facilities ORDER BY rowid LIMIT 1").fetchone()
        return {"events": int(events), "chain_head": head,
                "facility": facility[0] if facility else "",
                "license": licence[0] if licence else ""}
    finally:
        connection.close()


def _counts(db_path: Path) -> dict:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            " ORDER BY name")]
        return {t: int(connection.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0])
                for t in tables}
    finally:
        connection.close()


@dataclass
class Backup:
    directory: Path
    database: Path
    manifest: Path
    events: int = 0
    chain_head: str = ""
    reports: list = field(default_factory=list)

    @property
    def stem(self) -> str:
        return self.database.name.split("-")[-1].split(".")[0]


def backup(ws, dest: str | Path, *, at: datetime | None = None, free_bytes: int | None = None) -> Backup:
    """Copy the live record, consistently, and write a manifest that can prove it later."""
    at = at or datetime.now(timezone.utc)
    source_db = Path(ws.path)
    directory = Path(dest)
    directory.mkdir(parents=True, exist_ok=True)

    state = _read_state(source_db)
    size = source_db.stat().st_size
    free = shutil.disk_usage(directory).free if free_bytes is None else free_bytes
    if free < size * 2:
        raise BackupError(
            f"{directory} has {free // 1024} KB free and a {size // 1024} KB record needs twice that "
            f"for a backup, so nothing was written")

    stamp = at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"coontie-backup-{stamp}-{state['chain_head'][:8] or '00000000'}-{state['events']}"
    db_path = directory / f"{name}.sqlite3"
    manifest_path = directory / f"{name}.manifest.json"

    # SQLite's own backup API: pages are copied under the database lock, so backing up a record that
    # is being served produces one instant rather than a torn file.
    target = sqlite3.connect(db_path)
    try:
        ws.conn.backup(target)
    finally:
        target.close()

    copied = _read_state(db_path)
    if (copied["events"], copied["chain_head"]) != (state["events"], state["chain_head"]):
        db_path.unlink(missing_ok=True)
        raise BackupError(
            f"the copy does not match the record: {copied['events']} events and head "
            f"{copied['chain_head'][:8]} against {state['events']} and {state['chain_head'][:8]}")

    reports = _copy_reports(Path(source_db).resolve().parent, directory)
    manifest = {
        "format": FORMAT, "created_at": at.isoformat(), "tool": TOOL,
        "facility": state["facility"], "license": state["license"],
        "events": state["events"], "chain_head": state["chain_head"],
        "database": {"name": db_path.name, "bytes": db_path.stat().st_size,
                     "sha256": _sha256(db_path)},
        "reports": reports,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return Backup(directory=directory, database=db_path, manifest=manifest_path,
                  events=state["events"], chain_head=state["chain_head"],
                  reports=[r["name"] for r in reports])


def _copy_reports(source_dir: Path, dest_dir: Path) -> list:
    """Copy every artifact, keeping the directory flat and the hashes honest."""
    out = []
    source = source_dir / REPORTS_DIR
    if not source.is_dir():
        return out
    target = dest_dir / REPORTS_DIR
    target.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.iterdir()):
        if not path.is_file():
            continue
        copy = target / path.name
        copy.write_bytes(path.read_bytes())
        out.append({"name": path.name, "bytes": copy.stat().st_size, "sha256": _sha256(copy)})
    return out


def _manifest_of(path: Path) -> tuple[Path, dict]:
    """Accept a manifest, a database or the directory that holds one."""
    path = Path(path)
    if path.is_dir():
        found = sorted(path.glob("*.manifest.json"))
        if not found:
            raise BackupError(f"no manifest in {path}; that directory does not hold a backup")
        path = found[-1]
    if path.suffix == ".json":
        manifest = json.loads(path.read_text(encoding="utf-8"))
        return path, manifest
    manifest = path.with_name(path.name.replace(".sqlite3", ".manifest.json"))
    if not manifest.exists():
        raise BackupError(f"{path.name} has no manifest beside it; a database alone is not a backup")
    return manifest, json.loads(manifest.read_text(encoding="utf-8"))


def verify(path: str | Path) -> tuple[bool, list, dict]:
    """Recompute the manifest against the files. Returns (ok, problems, manifest)."""
    manifest_path, manifest = _manifest_of(Path(path))
    directory = manifest_path.parent
    problems: list = []
    if manifest.get("format") != FORMAT:
        problems.append(f"unknown backup format {manifest.get('format')!r}")

    db_path = directory / manifest.get("database", {}).get("name", "")
    if not db_path.exists():
        problems.append(f"{db_path.name or 'the database'} is missing")
    else:
        if db_path.stat().st_size != manifest["database"].get("bytes"):
            problems.append(f"{db_path.name} is {db_path.stat().st_size} bytes, the manifest says "
                            f"{manifest['database'].get('bytes')}")
        elif _sha256(db_path) != manifest["database"].get("sha256"):
            problems.append(f"{db_path.name} does not hash to the value in the manifest")
        else:
            state = None
            try:
                state = _read_state(db_path)
            except sqlite3.DatabaseError as exc:
                problems.append(f"{db_path.name} is not a readable database ({exc})")
            if state is not None:
                if state["events"] != manifest.get("events"):
                    problems.append(f"{db_path.name} holds {state['events']} events, the manifest "
                                    f"says {manifest.get('events')}")
                if state["chain_head"] != manifest.get("chain_head"):
                    problems.append(f"{db_path.name} ends at {state['chain_head'][:8]}, the manifest "
                                    f"says {str(manifest.get('chain_head'))[:8]}")
                ok, reason = _chain_verifies(db_path)
                if not ok:
                    problems.append(f"the chain in {db_path.name} does not verify: {reason}")

    for entry in manifest.get("reports", []):
        artifact = directory / REPORTS_DIR / entry["name"]
        if not artifact.exists():
            problems.append(f"report {entry['name']} is missing")
        elif _sha256(artifact) != entry.get("sha256"):
            problems.append(f"report {entry['name']} does not hash to the value in the manifest")
    return (not problems), problems, manifest


def _chain_verifies(db_path: Path) -> tuple[bool, str]:
    """Verify the hash chain in a database file without a Workspace."""
    from .store import Ledger

    ledger = Ledger(db_path)
    try:
        return ledger.verify_chain()
    finally:
        ledger.close()


def restore(backup_path: str | Path, target_db: str | Path, *, force: bool = False,
            actor: str = "", at: datetime | None = None) -> dict:
    """Verify, copy, verify the restored chain, then record that it happened."""
    ok, problems, manifest = verify(backup_path)
    if not ok:
        raise BackupError("the backup does not verify: " + "; ".join(problems))

    given = Path(backup_path)
    if given.suffix == ".json":
        base = given.parent
    elif given.is_dir():
        base = given
    else:
        base = given.parent
    source_db = base / manifest["database"]["name"]
    target = Path(target_db)
    if target.exists() and not force:
        raise BackupError(f"{target} already exists; a restore overwrites a record, so it needs "
                          f"--force")
    target.parent.mkdir(parents=True, exist_ok=True)
    before = _counts(target) if target.exists() else {}

    shutil.copy2(source_db, target)
    for entry in manifest.get("reports", []):
        artifact = source_db.parent / REPORTS_DIR / entry["name"]
        destination = target.parent / REPORTS_DIR / entry["name"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            continue  # a restore merges artifacts; it never deletes evidence the target holds
        shutil.copy2(artifact, destination)

    state = _read_state(target)
    if (state["events"], state["chain_head"]) != (manifest["events"], manifest["chain_head"]):
        raise BackupError(
            f"the restored file does not verify: {state['events']} events and head "
            f"{state['chain_head'][:8]} against {manifest['events']} and "
            f"{manifest['chain_head'][:8]}")
    ok, reason = _chain_verifies(target)
    if not ok:
        raise BackupError(f"the restored chain does not verify: {reason}")

    # The restore is part of the record's life, so it is on the record. It is appended only after the
    # restored file proved itself, which keeps the manifest's head the head of a verifiable file.
    from .workspace import Workspace

    at = at or datetime.now(timezone.utc)
    ws = Workspace(target)
    try:
        ws.ledger.append("restore_performed", {
            "backup": source_db.name,
            "backup_chain_head": manifest["chain_head"],
            "restored_chain_head": state["chain_head"],
            "events_restored": manifest["events"],
            "actor": (actor or "").strip(),
        }, at)
    finally:
        ws.close()
    after = _counts(target)
    return {"target": str(target), "events": manifest["events"], "chain_head": manifest["chain_head"],
            "before": before, "after": after, "employee_rows": after.get("employees", 0)}


def prune(dest: str | Path, keep: int) -> list:
    """Delete the oldest verified backups beyond `keep`. Never the newest, never an unverified one."""
    if keep < 1:
        raise BackupError(f"--keep must be at least 1, not {keep}")
    directory = Path(dest)
    backups = []
    for manifest in sorted(directory.glob("*.manifest.json")):
        ok, _, data = verify(manifest)
        backups.append((data.get("created_at", ""), manifest, ok))
    backups.sort(key=lambda row: row[0])
    removed = []
    while len(backups) > keep:
        created, manifest, ok = backups[0]
        if not ok:
            raise BackupError(f"{manifest.name} does not verify, so it will not be pruned; "
                              f"delete it by hand once you have decided what it is")
        db_path = manifest.parent / manifest.name.replace(".manifest.json", ".sqlite3")
        db_path.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
        removed.append(db_path.name)
        backups.pop(0)
    return removed


def drill(source_db: str | Path, *, into: str | Path | None = None, actor: str = "drill") -> list:
    """Back up, verify, restore, compare, then prove tampering is caught. Returns the steps."""
    from .workspace import Workspace

    steps: list = []
    workdir = Path(into) if into else Path(tempfile.mkdtemp(prefix="coontie-drill-"))
    workdir.mkdir(parents=True, exist_ok=True)
    ws = Workspace(source_db)
    try:
        saved = backup(ws, workdir / "backup")
        steps.append(f"backed up {saved.events} events ending {saved.chain_head[:8]} to {saved.database.name}")

        ok, problems, manifest = verify(saved.manifest)
        if not ok:
            raise BackupError("the backup does not verify: " + "; ".join(problems))
        steps.append(f"verified {manifest['database']['name']} and {len(manifest.get('reports', []))} "
                     f"report file(s)")

        target = workdir / "restored.sqlite3"
        result = restore(saved.manifest, target, actor=actor, force=True)
        steps.append(f"restored into {target.name}: {result['events']} events")

        live, restored = _counts(Path(ws.path)), _counts(target)
        differing = {t: (n, restored.get(t)) for t, n in live.items()
                     if restored.get(t, -1) != n and t != "events"}
        if differing:
            raise BackupError(f"the restored record differs table by table: {differing}")
        steps.append(f"every table matches: {', '.join(f'{n} {t}' for t, n in live.items())}")

        state = _read_state(target)
        restored_event_count = result["events"] + 1  # the restore_performed event
        if state["events"] != restored_event_count:
            raise BackupError(f"the restored record holds {state['events']} events, expected "
                              f"{restored_event_count}")
        steps.append(f"the restore is on the record: {state['events']} events, head {state['chain_head'][:8]}")
    finally:
        ws.close()

    # A backup that cannot detect a flipped byte is a copy, not a control.
    tampered = workdir / "tampered"
    tampered.mkdir(exist_ok=True)
    db_copy = tampered / saved.database.name
    data = bytearray(db_copy.read_bytes() if db_copy.exists() else saved.database.read_bytes())
    offset = len(data) // 2
    data[offset] = (data[offset] + 1) % 256
    db_copy.write_bytes(bytes(data))
    shutil.copy2(saved.manifest, tampered / saved.manifest.name)
    ok, problems, _ = verify(tampered / saved.manifest.name)
    if ok:
        raise BackupError("a flipped byte in the database passed verification")
    steps.append(f"a flipped byte is caught: {problems[0]}")

    truncated = workdir / "truncated"
    truncated.mkdir(exist_ok=True)
    cut = truncated / saved.database.name
    cut.write_bytes(saved.database.read_bytes()[:4096])
    shutil.copy2(saved.manifest, truncated / saved.manifest.name)
    ok, problems, _ = verify(truncated / saved.manifest.name)
    if ok:
        raise BackupError("a truncated database passed verification")
    steps.append(f"a truncated file is caught: {problems[0]}")
    steps.append(f"drill passed in {workdir}")
    return steps
