"""Deterministic assistance: a command grammar and a document reader.

Two jobs, no model, no network:

- ``parse_command`` turns a sentence an operator would say into the command it means. It
  prints the command and never runs it; the operator confirms.
- ``read_document`` pulls the fields we actually store out of pasted text (a lab COA, a
  wholesale invoice) and reports what it could not find rather than guessing.

Both are the baseline any optional model has to beat. Every function here is pure: same
input, same output, no clock, no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher, get_close_matches
from decimal import Decimal, InvalidOperation

# Vocabulary the grammar understands. Kept explicit so a refusal can name the alternatives.
VERBS = {
    "send": "manifest",
    "ship": "manifest",
    "transfer": "manifest",
    "deliver": "manifest",
    "dispatch": "dispatch",
    "receive": "receive",
    "accept": "receive",
    "split": "split",
    "move": "split",
    "adjust": "adjust",
    "correct": "adjust",
    "sample": "sample",
    "test": "sample",
    "package": "final",
    "final": "final",
    "cure": "cure",
    "dry": "cure",
    "audit": "audit",
    "check": "audit",
    "stock": "stock",
    "inventory": "stock",
    "brief": "brief",
    "verify": "verify",
}

REPORTS = {"audit", "stock", "brief", "verify"}

UNIT_WORDS = {
    "g": "g", "gram": "g", "grams": "g", "gm": "g", "gms": "g",
    "kg": "kg", "kilo": "kg", "kilos": "kg", "kilogram": "kg", "kilograms": "kg",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "ml": "ml", "milliliter": "ml", "milliliters": "ml", "millilitre": "ml",
    "unit": "unit", "units": "unit", "ea": "unit", "each": "unit",
}

NUMBER = r"(\d+(?:\.\d+)?)"
THOUSANDS = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"
QUANTITY_RE = re.compile(rf"(?<![\w.]){THOUSANDS}\s*([a-z]+)?", re.I)


@dataclass(frozen=True)
class Parse:
    """What a sentence meant, and the command that would carry it out."""

    intent: str
    args: dict = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.intent not in ("", "unknown")

    def command(self) -> str:
        """The CLI line this parse corresponds to, with names already resolved."""
        a = self.args
        if self.intent == "manifest":
            items = " ".join(f"--item {lot}:{qty}" for lot, qty in a.get("items", []))
            crew = ";".join(a.get("crew", []))
            return (f"coontie manifest --recipient \"{a.get('recipient', '')}\" "
                    f"--address \"{a.get('address', '')}\" --vehicle {a.get('vehicle', '<vehicle>')} "
                    f"--employees \"{crew}\" --depart {a.get('depart', '<depart>')} "
                    f"--arrive {a.get('arrive', '<arrive>')} {items}").strip()
        if self.intent == "split":
            return (f"coontie split --lot {a.get('lot', '<lot>')} --amount {a.get('quantity', '')} "
                    f"--to {a.get('room', '<room>')}")
        if self.intent == "sample":
            return (f"coontie sample --lot {a.get('lot', '<lot>')} --weight {a.get('quantity', '')} "
                    f"--cmtl \"{a.get('lab', '')}\"")
        if self.intent == "adjust":
            return (f"coontie adjust --lot {a.get('lot', '<lot>')} --remove {a.get('quantity', '')} "
                    f"--cause {a.get('cause', '<cause>')} --reason \"{a.get('reason', '')}\"")
        if self.intent == "dispatch":
            return f"coontie dispatch --manifest {a.get('manifest', '<manifest>')}"
        if self.intent == "receive":
            extra = ""
            if a.get("received"):
                extra += f" --received {a['received']}"
            if a.get("rejected"):
                extra += f" --rejected {a['rejected']}"
            return (f"coontie receive --manifest {a.get('manifest', '<manifest>')} "
                    f"--receiver \"{a.get('receiver', '<name>')}\" --room {a.get('room', '<room>')}{extra}")
        if self.intent in REPORTS:
            return f"coontie {self.intent}"
        if self.intent == "cure":
            return (f"coontie cure --harvest {a.get('harvest', '<harvest>')} --post {a.get('post', '')} "
                    f"--room {a.get('room', '<room>')}")
        if self.intent == "final":
            return f"coontie final --lot {a.get('lot', '<lot>')} --units {a.get('units', '')}"
        return ""


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 .%/,$\-]+", " ", (text or "").lower()).strip()


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def resolve(value: str, candidates, cutoff: float = 0.72) -> tuple[str, float]:
    """Exact, then prefix, then close. Returns ("", 0.0) when nothing is near enough."""
    if not value:
        return "", 0.0
    needle = value.strip().lower()
    pool = [c for c in candidates if c]
    for c in pool:
        if c.lower() == needle:
            return c, 1.0
    prefixed = [c for c in pool if c.lower().startswith(needle) or needle.startswith(c.lower() + " ")]
    if len(prefixed) == 1:
        return prefixed[0], 0.95
    matches = get_close_matches(needle, [c.lower() for c in pool], n=1, cutoff=cutoff)
    if matches:
        best = matches[0]
        for c in pool:
            if c.lower() == best:
                return c, round(_similarity(needle, best), 2)
    return "", 0.0


def _quantity(text: str) -> tuple[Decimal | None, str, str]:
    """(amount, unit, the matched text) from the first quantity in a sentence."""
    m = QUANTITY_RE.search(text or "")
    if not m:
        return None, "", ""
    try:
        amount = Decimal(m.group(1).replace(",", ""))
    except InvalidOperation:
        return None, "", ""
    word = (m.group(2) or "").lower()
    return amount, UNIT_WORDS.get(word, word if word in UNIT_WORDS.values() else ""), m.group(0)


def _after(text: str, *markers: str) -> str:
    """The words following the first marker, up to the next marker-ish boundary."""
    for marker in markers:
        m = re.search(rf"\b{marker}\b\s+(.+)$", text, re.I)
        if m:
            return m.group(1).strip()
    return ""


def _before(text: str, marker: str) -> str:
    idx = text.lower().find(marker.lower())
    return text[:idx].strip() if idx > 0 else ""


def _split_list(text: str) -> list[str]:
    parts = re.split(r"\s*(?:,|;|\band\b|&|\s{2,})\s*", text or "")
    return [p.strip() for p in parts if p.strip()]


def parse_command(
    text: str,
    *,
    cultivars: tuple[str, ...] = (),
    rooms: tuple[str, ...] = (),
    labs: tuple[str, ...] = (),
    people: tuple[str, ...] = (),
    manifests: tuple[str, ...] = (),
    lots: tuple[tuple[str, str], ...] = (),
) -> Parse:
    """Read an operator's sentence as the command it means.

    ``lots`` is (lot_id, cultivar) pairs, so "blue dream" can resolve to a lot.
    """
    raw = (text or "").strip()
    if not raw:
        return Parse("unknown", notes=("say something like 'send 200 g blue dream to Tampa'",))

    lower = normalize(raw)
    first = lower.split()[0] if lower.split() else ""
    intent = VERBS.get(first, "unknown")
    notes: list[str] = []
    unresolved: list[str] = []

    if intent == "unknown":
        # Try the verb anywhere in the sentence ("can you send ...").
        for word, name in VERBS.items():
            if re.search(rf"\b{word}\b", lower):
                intent = name
                notes.append(f"read the verb '{word}' inside the sentence")
                break
    if intent == "unknown":
        near = get_close_matches(first, list(VERBS), n=1, cutoff=0.85)
        if near:
            intent = VERBS[near[0]]
            notes.append(f"read '{first}' as '{near[0]}'")
        else:
            close = get_close_matches(first, list(VERBS), n=1, cutoff=0.7)
            hint = f"; did you mean '{close[0]}'?" if close else ""
            return Parse("unknown", notes=(f"no verb I know at the start of that sentence{hint}",))

    if intent in REPORTS:
        return Parse(intent)

    # Reports that take no arguments are done. The rest need a subject.
    pool = list(dict.fromkeys([c for _, c in lots] + list(cultivars)))
    cultivar, score = "", 0.0
    for candidate in pool:
        if candidate and candidate.lower() in lower and len(candidate) > len(cultivar):
            cultivar, score = candidate, 1.0
    if not cultivar and pool:
        words = [w for w in lower.split() if len(w) > 2]
        best, best_score = "", 0.0
        for candidate in pool:
            for word in words:
                s = _similarity(candidate, word)
                if s > best_score:
                    best, best_score = candidate, s
        if best_score >= 0.8:
            cultivar, score = best, round(best_score, 2)
            notes.append(f"read '{cultivar}' from a near miss in the sentence")

    lot_id = ""
    if cultivar:
        for lid, lc in lots:
            if lc == cultivar:
                lot_id = lid
                break
    if not lot_id:
        m = re.search(r"\b(stk-[0-9a-f]{4,}|lot\s+([0-9a-f]{6,}))\b", lower)
        if m:
            lot_id = m.group(1).replace("lot ", "stk-")

    amount, unit, _ = _quantity(lower)

    if intent == "manifest":
        place = _after(lower, "to")
        recipient = place.split(" with ")[0].strip() if place else ""
        crew_text = _after(lower, "with")
        crew: list[str] = []
        for name in _split_list(crew_text):
            found, _s = resolve(name, people) if people else (name.title(), 0.8)
            crew.append(found or name.title())
        args = {
            "recipient": recipient.title() if recipient else "",
            "items": [(lot_id or "<lot>", str(amount))] if amount is not None else [],
            "crew": crew,
        }
        if amount is None:
            notes.append("no quantity found; say how much is going")
        if len(crew) < 2:
            notes.append("the statute needs two people in the vehicle; only "
                         f"{len(crew)} named")
        if not recipient:
            notes.append("no recipient found; say who receives it")
        if not lot_id:
            notes.append(f"no lot matched {cultivar or 'anything in that sentence'}")
            unresolved.append(cultivar or "lot")
        return Parse(intent, args, tuple(notes), tuple(unresolved))

    if intent == "split":
        room_text = _after(lower, "to")
        room, _rs = resolve(room_text, rooms) if rooms else (room_text.title(), 0.7)
        if not room:
            notes.append("no destination room matched; say which room")
        if amount is None:
            notes.append("no quantity found")
        if not lot_id:
            notes.append("no lot matched")
        return Parse(intent, {"lot": lot_id, "quantity": str(amount or ""), "room": room},
                     tuple(notes), tuple(x for x in [cultivar] if not lot_id))

    if intent == "sample":
        lab_text = _after(lower, "to", "for", "by", "at")
        lab, _ls = resolve(lab_text, labs) if labs else (lab_text.title(), 0.6)
        if amount is None:
            notes.append("no sample weight found")
        if not lab:
            notes.append("no laboratory matched")
        return Parse(intent, {"lot": lot_id, "quantity": str(amount or ""), "lab": lab}, tuple(notes))

    if intent == "adjust":
        reason = _after(lower, "because", "since")
        cause = ""
        m = re.search(r"\b(spillage|miscount|damage|theft|contamination|expiry|data entry|typo|waste|"
                      r"processing|dispensation|wholesale|disposal)\b", lower)
        if m:
            cause = m.group(1)
        else:
            synonyms = {"knocked over": "spillage", "dropped": "spillage", "spilled": "spillage",
                        "broke": "damage", "broken": "damage", "typo": "data entry",
                        "fat finger": "data entry"}
            for phrase, mapped in synonyms.items():
                if phrase in lower:
                    cause = mapped
                    notes.append(f"read '{phrase}' as the cause '{mapped}'")
                    break
        if not cause:
            notes.append("no cause named; a correction cannot be recorded without one")
        if amount is None:
            notes.append("no quantity found")
        return Parse(intent, {"lot": lot_id, "quantity": str(amount or ""), "cause": cause,
                              "reason": reason}, tuple(notes))

    if intent == "dispatch":
        ref = _after(lower, "manifest") or (manifests[0] if len(manifests) == 1 else "")
        if not any(m in lower for m in manifests) and manifests:
            ref = ""
        if not ref:
            notes.append("no manifest matched")
        return Parse(intent, {"manifest": ref}, tuple(notes))

    if intent == "receive":
        ref = ""
        for m in manifests:
            if m.lower() in lower:
                ref = m
                break
        receiver = _after(lower, "by", "signed by", "receiver")
        received = re.search(rf"received\s+{NUMBER}", lower)
        rejected = re.search(rf"rejected\s+{NUMBER}", lower)
        if not ref:
            notes.append("no manifest matched")
        if not receiver:
            notes.append("no receiving name found")
        return Parse(intent, {
            "manifest": ref, "receiver": receiver.title() if receiver else "",
            "received": received.group(1) if received else "",
            "rejected": rejected.group(1) if rejected else "",
        }, tuple(notes))

    if intent == "cure":
        post = re.search(rf"(?:to|post)\s+{NUMBER}", lower)
        waste = re.search(rf"waste\s+{NUMBER}", lower)
        harvest = re.search(r"\b(hrv-[0-9a-z]+)\b", lower)
        return Parse(intent, {
            "harvest": harvest.group(1) if harvest else "",
            "post": post.group(1) if post else (str(amount) if amount is not None else ""),
            "waste": waste.group(1) if waste else "0",
        }, tuple(notes))

    if intent == "final":
        units = re.search(rf"{NUMBER}\s*(?:units?|packs?|jars?|packs of)", lower)
        return Parse(intent, {
            "lot": lot_id, "units": units.group(1) if units else (str(amount) if amount else ""),
        }, tuple(notes))

    return Parse("unknown", notes=("that verb is not wired to a command yet",))


# -- document reading ---------------------------------------------------------

@dataclass(frozen=True)
class Extracted:
    kind: str
    fields: dict = field(default_factory=dict)
    missing: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.missing


COA_FIELDS = ("product_name", "thc_percent", "cbd_percent", "lab", "tested_on", "sample_id")
INVOICE_FIELDS = ("buyer", "seller", "quantity", "unit_price", "invoice_date")

KNOWN_LABS = (
    "ACS Laboratory", "TerpLife Labs", "Modern Canna", "Method Labs", "AccuScience Laboratories",
    "US Cannalytics", "Kaycha Labs", "Act Lab", "Confident Cannabis",
)

_DATE = r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})"


def _clean_date(value: str) -> str:
    value = value.strip()
    if "/" in value:
        m, d, y = value.split("/")
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return ""


def _num(value: str) -> str:
    try:
        quantized = Decimal(str(value).replace(",", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, AttributeError):
        return ""
    text = format(quantized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def read_document(text: str) -> Extracted:
    """Pull the fields we store out of pasted text. Missing stays missing."""
    body = text or ""
    lower = body.lower()
    kind = "invoice" if re.search(r"\b(invoice|bill to|unit price|purchase order)\b", lower) else \
           ("coa" if re.search(r"\b(total thc|cannabinoid|certificate of analysis|\bcoa\b)\b", lower) else "unknown")

    if kind == "coa":
        fields: dict[str, str] = {}
        m = re.search(rf"(?:total\s+)?thc[^0-9%]{{0,20}}{NUMBER}\s*%", lower)
        if m:
            fields["thc_percent"] = _num(m.group(1))
        m = re.search(rf"(?:total\s+)?cbd[^0-9%]{{0,20}}{NUMBER}\s*%", lower)
        if m:
            fields["cbd_percent"] = _num(m.group(1))
        m = re.search(r"(?:product|strain|cultivar)\s*[:\-]\s*(.+)", body, re.I)
        if m:
            fields["product_name"] = m.group(1).split("\n")[0].strip()
        for lab in KNOWN_LABS:
            if lab.lower() in lower:
                fields["lab"] = lab
                break
        m = re.search(rf"(?:tested|report date|date of analysis|sampled)\s*[:\-]?\s*{_DATE}", body, re.I)
        if m:
            cleaned = _clean_date(m.group(1))
            if cleaned:
                fields["tested_on"] = cleaned
        m = re.search(r"(?:sample\s*id|sample\s*#|accession)\s*[:\-]\s*([A-Za-z0-9\-]+)", body, re.I)
        if m:
            fields["sample_id"] = m.group(1).strip()
        missing = tuple(f for f in COA_FIELDS if f not in fields)
        return Extracted("coa", fields, missing)

    if kind == "invoice":
        fields = {}
        m = re.search(r"(?:bill to|buyer|customer)\s*[:\-]\s*(.+)", body, re.I)
        if m:
            fields["buyer"] = m.group(1).split("\n")[0].strip()
        m = re.search(r"(?:seller|vendor|from|remit to)\s*[:\-]\s*(.+)", body, re.I)
        if m:
            fields["seller"] = m.group(1).split("\n")[0].strip()
        m = re.search(rf"(?:quantity|qty)\s*[:\-]?\s*{THOUSANDS}\s*([a-z]+)?", lower)
        if m:
            fields["quantity"] = _num(m.group(1))
            if m.group(2) and m.group(2) in UNIT_WORDS:
                fields["unit"] = UNIT_WORDS[m.group(2)]
        m = re.search(rf"(?:unit price|price per|per unit)\s*[:\-]?\s*\$?{NUMBER}", lower)
        if m:
            fields["unit_price"] = _num(m.group(1))
        m = re.search(rf"(?:invoice date|date)\s*[:\-]?\s*{_DATE}", body, re.I)
        if m:
            cleaned = _clean_date(m.group(1))
            if cleaned:
                fields["invoice_date"] = cleaned
        missing = tuple(f for f in INVOICE_FIELDS if f not in fields)
        return Extracted("invoice", fields, missing)

    return Extracted("unknown", {}, COA_FIELDS)


def phrase_variants(phrase: str) -> tuple[str, ...]:
    """Explicit alternatives for a refusal, so the operator is never just told 'no'."""
    return tuple(sorted({p for p in VERBS if p.startswith(phrase[:3].lower())}))[:6]
