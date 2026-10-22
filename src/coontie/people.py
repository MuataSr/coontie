"""People and API users: the two DH5059 admin events the record did not carry.

An API user's password never enters the record. The form derives a verifier and the ledger holds
the verifier, because the ledger is append-only, hash-chained, printed and backed up: a secret
written there can never be taken out again. See `docs/flows/facility-records.md`.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from dataclasses import dataclass
from datetime import date

PBKDF2_ITERATIONS = 300_000
SALT_BYTES = 16

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class Employee:
    id: str
    full_name: str
    date_of_birth: date
    hire_date: date
    email: str
    active: bool = True

    def initialled(self) -> str:
        """A name short enough for a table cell, never a substitute for the full one."""
        return " ".join(part[0] + "." for part in self.full_name.split() if part)


@dataclass(frozen=True)
class ApiUser:
    id: str
    email: str
    permissions: tuple[str, ...]
    verifier: str
    kdf: str


def check_email(value: str, *, who: str = "an email address") -> str:
    text = (value or "").strip()
    if not _EMAIL.match(text):
        raise ValueError(f"{who} is not an email address: {value!r}")
    return text.lower()


def check_name(value: str) -> str:
    text = " ".join((value or "").split())
    if not text:
        raise ValueError("a person needs a full name")
    if len(text.split()) < 2:
        raise ValueError(
            f"{text!r} is one word; the record needs the full name the department can match"
        )
    return text


def check_date(value, *, field: str) -> date:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} is not a date in YYYY-MM-DD form: {text!r}") from exc


def check_hire_date(value, *, today: date | None = None) -> date:
    hire = check_date(value, field="hire date")
    today = today or date.today()
    if hire > today:
        raise ValueError(f"hire date {hire.isoformat()} is in the future; the record is not a plan")
    return hire


def check_permissions(value) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        parts = [str(p).strip() for p in value]
    else:
        parts = [p.strip() for p in str(value or "").replace(";", ",").split(",")]
    parts = [p for p in parts if p]
    if not parts:
        raise ValueError(
            "an API user needs its permissions listed (for example inventory.read, transport.write)"
        )
    return tuple(parts)


def derive_verifier(password: str, *, salt: bytes | None = None) -> tuple[str, str]:
    """PBKDF2-HMAC-SHA256 over a random salt. Returns (verifier, encoded) and holds no password."""
    if not password:
        raise ValueError("an API user needs a password to derive its verifier")
    if len(password) < 8:
        raise ValueError(
            "a password shorter than eight characters is refused here as well as at the STS"
        )
    salt = salt or os.urandom(SALT_BYTES)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    encoded = f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}"
    return derived.hex(), encoded


def verify(password: str, encoded: str) -> bool:
    """Check a password against an encoded verifier, for tests and for a future login prompt."""
    try:
        scheme, iterations, salt_hex, expected = encoded.split("$")
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
    )
    return hmac.compare_digest(derived.hex(), expected)
