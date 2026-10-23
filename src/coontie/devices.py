"""Paired terminals for a LAN build.

A terminal is a tablet or a second workstation paired to this record. (`device` already means a
DH5059 delivery device in this codebase, so the table is `terminals`.)

A tablet in a cure room holds a token; a token is a credential. So the record stores a verifier and
never the token, the pairing code expires and works once, and guessing is made expensive by a lockout
rather than by hoping.

Spec: docs/flows/lan.md.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .amendments import new_id
from .people import derive_verifier, verify

CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # no vowels, no 0/1: nothing spells a word
CODE_LENGTH = 10
CODE_TTL = timedelta(minutes=15)
MAX_ATTEMPTS = 5
LOCKOUT = timedelta(minutes=15)


class DeviceError(Exception):
    """A pairing or revocation that must not proceed."""


@dataclass
class Device:
    id: str
    name: str
    added_by: str
    added_at: datetime
    paired_at: datetime | None = None
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None

    @property
    def paired(self) -> bool:
        return self.paired_at is not None and self.revoked_at is None

    @property
    def state(self) -> str:
        if self.revoked_at is not None:
            return "revoked"
        return "paired" if self.paired_at is not None else "waiting for a code"


def _device(row) -> Device:
    def when(value):
        return datetime.fromisoformat(value) if value else None

    return Device(id=row["id"], name=row["name"], added_by=row["added_by"] or "",
                  added_at=datetime.fromisoformat(row["added_at"]),
                  paired_at=when(row["paired_at"]), last_seen_at=when(row["last_seen_at"]),
                  revoked_at=when(row["revoked_at"]))


def _code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def add_device(ws, name: str, *, actor: str, at: datetime | None = None) -> tuple:
    """Mint a pairing code for a device. The code is returned once and stored as a verifier."""
    name = (name or "").strip()
    if not name:
        raise DeviceError("a device needs a name, so an operator can tell the tablets apart")
    at = at or datetime.now(timezone.utc)
    code = _code()
    salt, encoded = derive_verifier(code)
    device_id = new_id("dv")
    ws.conn.execute(
        "INSERT INTO terminals (id, name, code_verifier, code_expires_at, added_by, added_at)"
        " VALUES (?,?,?,?,?,?)",
        (device_id, name, encoded, (at + CODE_TTL).isoformat(), actor, at.isoformat()))
    ws.conn.commit()
    row = ws.conn.execute("SELECT * FROM terminals WHERE id = ?", (device_id,)).fetchone()
    return _device(row), code


def list_devices(ws) -> list:
    return [_device(row) for row in ws.conn.execute(
        "SELECT * FROM terminals ORDER BY added_at, rowid")]


def get(ws, device_id: str) -> Device:
    row = ws.conn.execute("SELECT * FROM terminals WHERE id = ?", (device_id,)).fetchone()
    if row is None:
        raise DeviceError(f"no device {device_id!r}")
    return _device(row)


def pair(ws, code: str, *, at: datetime | None = None) -> tuple:
    """Redeem a code for a device token. Returns (device, token). The code cannot be used twice."""
    at = at or datetime.now(timezone.utc)
    cleaned = "".join(ch for ch in (code or "").upper() if not ch.isspace() and ch != "-")
    if not cleaned:
        raise DeviceError("a pairing code is required")
    candidates = ws.conn.execute(
        "SELECT * FROM terminals WHERE paired_at IS NULL AND revoked_at IS NULL").fetchall()
    for row in candidates:
        if not row["code_verifier"]:
            continue
        expires = row["code_expires_at"]
        if expires and datetime.fromisoformat(expires) < at:
            continue
        if not verify(cleaned, row["code_verifier"]):
            continue
        token = secrets.token_urlsafe(32)
        _, encoded = derive_verifier(token)
        ws.conn.execute(
            "UPDATE terminals SET token_verifier = ?, code_verifier = '', code_expires_at = NULL,"
            " paired_at = ?, last_seen_at = ? WHERE id = ?",
            (encoded, at.isoformat(), at.isoformat(), row["id"]))
        ws.conn.commit()
        ws.ledger.append("device_paired", {"device": row["id"], "name": row["name"]}, at)
        return get(ws, row["id"]), token
    raise DeviceError("that code is not valid, has already been used, or has expired; "
                      "ask for a new one at the server")


def by_token(ws, token: str, *, at: datetime | None = None) -> Device | None:
    """The device holding this cookie value, or None. Never raises for a bad token."""
    if not token:
        return None
    at = at or datetime.now(timezone.utc)
    candidates = ws.conn.execute(
        "SELECT * FROM terminals WHERE token_verifier != '' AND revoked_at IS NULL").fetchall()
    for row in candidates:
        if verify(token, row["token_verifier"]):
            ws.conn.execute("UPDATE terminals SET last_seen_at = ? WHERE id = ?", (at.isoformat(), row["id"]))
            ws.conn.commit()
            return _device(row)
    return None


def revoke(ws, device_id: str, *, actor: str, at: datetime | None = None) -> Device:
    at = at or datetime.now(timezone.utc)
    device = get(ws, device_id)
    if device.revoked_at is not None:
        raise DeviceError(f"{device_id} was already revoked on {device.revoked_at:%Y-%m-%d %H:%M} UTC")
    ws.conn.execute("UPDATE terminals SET revoked_at = ?, token_verifier = '' WHERE id = ?",
                    (at.isoformat(), device_id))
    ws.conn.commit()
    ws.ledger.append("device_revoked", {"device": device.id, "name": device.name, "by": actor}, at)
    return get(ws, device_id)


def paired_count(ws) -> int:
    return len([d for d in list_devices(ws) if d.paired])


# The limiter is shared with operator sign-in, so it lives in its own module.
from .attempts import MAX_ATTEMPTS, LOCKOUT, Limiter  # noqa: E402,F401


def lan_address() -> str:
    """This machine's LAN address, without a network call that would hang on an isolated segment."""
    import socket

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # TEST-NET-1, never routed; connect() sends nothing
        return probe.getsockname()[0]
    except OSError:
        return ""
    finally:
        probe.close()


def address_is_local(address: str) -> bool:
    import socket

    if address in ("127.0.0.1", "localhost", "::1"):
        return True
    if address in ("0.0.0.0", ""):
        return False
    try:
        return address == lan_address() or socket.gethostbyname(socket.gethostname()) == address
    except OSError:
        return False


def describe(device: Device) -> str:
    when = device.paired_at.strftime("%Y-%m-%d %H:%M") if device.paired_at else "-"
    return f"{device.id}  {device.name:28s}  {device.state:18s}  paired {when}"


def reports_dir_note() -> str:
    return f"devices live in the record; a token is never written to {Path('reports')}"
