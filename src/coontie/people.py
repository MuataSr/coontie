"""People, their passphrases, and API users: the DH5059 admin events the record did not carry.

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
PASSPHRASE_MIN = 12
PERSON_COOKIE = "coontie_person"

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class Employee:
    id: str
    full_name: str
    date_of_birth: date
    hire_date: date
    email: str
    active: bool = True
    can_sign_in: bool = False

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


class SignInError(Exception):
    """A refusal a person reads. The message is the whole of it: no code, no stack."""


def check_passphrase(value: str, *, name: str = "") -> str:
    """A passphrase protects a controlled-substance record; three weak shapes are refused by name."""
    text = value or ""
    if len(text) < PASSPHRASE_MIN:
        raise ValueError(
            f"a passphrase shorter than {PASSPHRASE_MIN} characters is refused; this one protects a "
            "controlled-substance record")
    if len(set(text)) == 1:
        raise ValueError("a passphrase of one repeated character is not a passphrase")
    words = [w.lower() for w in (name or "").split() if len(w) > 2]
    lowered = text.lower()
    if any(word in lowered for word in words):
        raise ValueError(
            "a passphrase that contains the person's name is the first thing anyone would try")
    return text


def person_cookie(server_token: str, employee_id: str) -> str:
    """`<id>.<hmac>`: a cookie naming a person the server did not sign is not a sign-in."""
    if not server_token or not employee_id:
        return ""
    signature = hmac.new(server_token.encode("utf-8"), employee_id.encode("utf-8"),
                         hashlib.sha256).hexdigest()[:32]
    return f"{employee_id}.{signature}"


def person_from_cookie(server_token: str, value: str) -> str:
    """The employee id a valid cookie names, or the empty string. Never raises on junk."""
    if not value or not server_token or "." not in value:
        return ""
    employee_id, _, signature = value.rpartition(".")
    expected = hmac.new(server_token.encode("utf-8"), employee_id.encode("utf-8"),
                        hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(signature, expected):
        return ""
    return employee_id


def signers(ws) -> list:
    """Employees who have been given a passphrase, so the ones the sign-in page can offer."""
    return [person for person in ws.employees() if person.can_sign_in]


def any_passphrase(ws) -> bool:
    """Whether this record has begun requiring a person. Derived from the record, not from a flag."""
    return bool(ws.conn.execute(
        "SELECT 1 FROM employees WHERE passphrase_verifier <> '' LIMIT 1").fetchone())


def sign_in(ws, employee_id: str, passphrase: str) -> Employee:
    """Check a passphrase against one employee's verifier. Raises SignInError with a plain sentence."""
    row = ws.conn.execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()
    if row is None or not row["active"]:
        raise SignInError("that person is not on the payroll record, or is no longer active")
    if not row["passphrase_verifier"]:
        raise SignInError(
            "that person has no passphrase; enrol one at the server with coontie passphrase --id "
            f"{row['id']} --set")
    if not verify(passphrase or "", row["passphrase_verifier"]):
        raise SignInError("that passphrase does not match")
    return Employee(
        id=row["id"], full_name=row["full_name"],
        date_of_birth=date.fromisoformat(row["date_of_birth"]),
        hire_date=date.fromisoformat(row["hire_date"]), email=row["email"],
        active=bool(row["active"]),
    )
