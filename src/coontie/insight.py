"""Deterministic insight: lineage, explanation, prefill, anomalies and the morning brief.

Five small readers over the record, no model, no network, no clock of their own (``now`` is an
argument). Each one answers a question an operator actually asks, and each answer is assembled
from rows so it can be traced back and reproduced:

- :func:`lineage`     where this jar came from, and everything that touched it
- :func:`explain`     what in our own history can account for a difference
- :func:`prefill`     what this recipient's last manifest looked like
- :func:`anomalies`   a number that does not look like the operator's own history
- :func:`brief`       a paragraph about the week, assembled by rule
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from statistics import median

from .inspect import _amount, _dt, _rows


# -- A3: lineage --------------------------------------------------------------

@dataclass(frozen=True)
class Line:
    depth: int
    text: str

    def render(self) -> str:
        return "  " * self.depth + self.text


def lineage(ws, ref: str) -> list[Line]:
    """Walk a record back to the seeds it came from, and out to everything it touched."""
    out: list[Line] = []
    final = ws.conn.execute("SELECT * FROM final_products WHERE id = ? OR id LIKE ?",
                            (ref, f"{ref}%")).fetchone()
    lot_ref = final["lot_id"] if final else ref

    if final:
        out.append(Line(0, f"Final product {final['id']}"))
        out.append(Line(1, f"{final['unit_count']} units, {final['net_weight']} {final['unit']} net, "
                          f"{final['product_type']} {final['cultivar']}"))
        out.append(Line(1, f"unique product id {final['upid']}, packaged {str(final['packaged_at'])[:10]}, "
                          f"expires {final['expiration_date']}"))

    lot = ws.conn.execute("SELECT * FROM stock_lots WHERE id = ? OR id LIKE ?",
                          (lot_ref, f"{lot_ref}%")).fetchone()
    if lot is None:
        raise ValueError(f"no final product or processing lot matching {ref!r}")

    # the lot, and everything that took weight out of it
    depth = 1 if final else 0
    out.append(Line(depth, f"Processing lot {lot['id']}: {lot['original']} {lot['unit']} of "
                           f"{lot['kind']} {lot['cultivar']}".rstrip()))
    taken = Decimal("0")
    for move in _rows(ws, "SELECT * FROM stock_moves WHERE lot_id = ? ORDER BY at, rowid", (lot["id"],)):
        taken += _amount(move["amount"])
        target = f" -> {move['target_lot_id']}" if move["target_lot_id"] else ""
        note = f"  ({move['note']})" if move["note"] else ""
        out.append(Line(depth + 1, f"{str(move['at'])[:16]} {move['kind']}: {move['amount']} "
                                   f"{move['unit']}{target}{note}"))
    remaining = _amount(lot["original"]) - taken
    moves = len(_rows(ws, "SELECT id FROM stock_moves WHERE lot_id = ?", (lot["id"],)))
    out.append(Line(depth + 1, f"remaining {remaining} {lot['unit']} ({_count(moves, 'move')})"))

    # parent lots, back to the material
    parent_id = lot["source_lot_id"]
    seen = {lot["id"]}
    chain = 0
    while parent_id and parent_id not in seen and chain < 20:
        parent = ws.conn.execute("SELECT * FROM stock_lots WHERE id = ?", (parent_id,)).fetchone()
        if parent is None:
            break
        seen.add(parent["id"])
        out.append(Line(depth, f"from lot {parent['id']}: {parent['original']} {parent['unit']} of "
                               f"{parent['kind']} {parent['cultivar']}".rstrip()))
        parent_id = parent["source_lot_id"]
        chain += 1

    harvest_ids = json.loads(lot["harvest_ids"] or "[]")
    for harvest_id in harvest_ids:
        harvest = ws.conn.execute("SELECT * FROM harvests WHERE id = ?", (harvest_id,)).fetchone()
        if not harvest:
            continue
        out.append(Line(depth, f"harvest {harvest['id']}: {harvest['wet_weight']} {harvest['wet_unit']} wet, "
                               f"taken {str(harvest['harvested_at'])[:10] if harvest['harvested_at'] else 'not yet'}"))
        for cure in _rows(ws, "SELECT * FROM cures WHERE harvest_id = ?", (harvest_id,)):
            out.append(Line(depth + 1, f"cured to {cure['post_weight']} {cure['post_unit']} "
                                       f"(waste {cure['waste_weight']} {cure['waste_unit']})"))
        plant_ids = json.loads(harvest["plant_ids"] or "[]")
        if plant_ids:
            batch = ws.conn.execute("SELECT batch_id FROM plants WHERE id = ?", (plant_ids[0],)).fetchone()
            if batch:
                row = ws.conn.execute("SELECT * FROM batches WHERE id = ?", (batch["batch_id"],)).fetchone()
                if row:
                    out.append(Line(depth + 1, f"batch {row['id']}: {row['count']} x {row['cultivar']}, "
                                               f"planted {str(row['created_at'])[:10]}"))
            out.append(Line(depth + 1, f"plants {plant_ids[0]}..{plant_ids[-1]} ({len(plant_ids)})"))

    # the lab work on this lot, and the paperwork
    for sample in _rows(ws, "SELECT * FROM lab_samples WHERE source_lot_id = ? ORDER BY at", (lot["id"],)):
        kind = "research and development" if sample["is_rnd"] else "compliance"
        out.append(Line(depth, f"lab sample {sample['weight']} {sample['unit']} to {sample['cmtl_id']} "
                               f"({kind}, {str(sample['at'])[:10]})"))
    for amendment in _rows(ws, "SELECT * FROM amendments WHERE target_id = ? ORDER BY sequence", (lot["id"],)):
        out.append(Line(depth, f"correction {amendment['before_value']} -> {amendment['after_value']} "
                               f"{amendment['unit']}, cause {amendment['cause']}"))
    for item in _rows(ws, "SELECT * FROM manifest_items WHERE lot_id = ?", (lot["id"],)):
        manifest = ws.conn.execute("SELECT * FROM manifests WHERE id = ?", (item["manifest_id"],)).fetchone()
        if manifest:
            out.append(Line(depth, f"manifest {manifest['id']} to {manifest['recipient_name']}: "
                                   f"{item['quantity']} {item['unit']} ({manifest['status']})"))
    return out


# -- A4: explanation ----------------------------------------------------------

@dataclass(frozen=True)
class Candidate:
    at: str
    kind: str
    amount: Decimal
    unit: str
    note: str
    matches: bool

    def line(self) -> str:
        mark = "MATCH  " if self.matches else "       "
        return f"{mark}{self.at[:16]}  {self.kind:<12} {self.amount:>10} {self.unit}  {self.note}"


def explain(ws, lot_ref: str, gap=None) -> list[Candidate]:
    """The lot's own history, with anything matching the gap marked. Evidence, not a guess."""
    lot = ws.stock_lot(lot_ref)
    target = _amount(gap) if gap not in (None, "") else None
    rows = _rows(ws, "SELECT * FROM stock_moves WHERE lot_id = ? ORDER BY at, rowid", (lot.id,))
    candidates: list[Candidate] = []
    for move in rows:
        value = _amount(move["amount"])
        note = move["note"] or ""
        target_lot = move["target_lot_id"]
        if target_lot:
            note = (note + f" -> {target_lot}").strip()
        candidates.append(Candidate(
            at=str(move["at"]), kind=move["kind"], amount=value, unit=move["unit"], note=note,
            matches=(target is not None and value == target),
        ))
    return candidates


# -- A5: prefill --------------------------------------------------------------

def prefill(ws, recipient: str = "") -> dict:
    """What this recipient's last manifest looked like: crew, vehicle, route, items."""
    rows = _rows(ws, "SELECT * FROM manifests ORDER BY created_at DESC, rowid DESC")
    if not rows:
        return {}
    chosen = rows[0]
    if recipient:
        needle = recipient.strip().lower()
        for row in rows:
            if row["recipient_name"].lower().startswith(needle) or needle in row["recipient_name"].lower():
                chosen = row
                break
    items = _rows(ws, "SELECT * FROM manifest_items WHERE manifest_id = ?", (chosen["id"],))
    return {
        "recipient_name": chosen["recipient_name"],
        "recipient_address": chosen["recipient_address"],
        "vehicle_id": chosen["vehicle_id"],
        "employees": json.loads(chosen["employee_ids"]),
        "route": chosen["route"],
        "stops": json.loads(chosen["stops"]),
        "items": [(i["lot_id"], i["quantity"], i["form"]) for i in items],
        "from_manifest": chosen["id"],
        "last_departure": chosen["departure_at"],
    }


def prefill_command(ws, recipient: str = "") -> str:
    """The same defaults as a command line, ready to edit rather than retype."""
    got = prefill(ws, recipient)
    if not got:
        return ""
    items = " ".join(f"--item {lot}:{qty}" for lot, qty, _form in got["items"])
    crew = ";".join(got["employees"])
    stops = " ".join(f'--stop "{s}"' for s in got["stops"])
    route = f'--route "{got["route"]}"' if got["route"] else ""
    return (f'coontie manifest --recipient "{got["recipient_name"]}" '
            f'--address "{got["recipient_address"]}" --vehicle {got["vehicle_id"]} '
            f'--employees "{crew}" --depart <when> --arrive <when> {items} {stops} {route}').strip()


# -- A6: anomalies ------------------------------------------------------------

@dataclass(frozen=True)
class Anomaly:
    subject: str
    summary: str
    z: float

    def line(self) -> str:
        return f"{self.subject}: {self.summary} (modified z {self.z:+.1f})"


def _modified_z(values: list[float]) -> list[float]:
    if len(values) < 5:
        return [0.0] * len(values)
    centre = median(values)
    deviations = [abs(v - centre) for v in values]
    mad = median(deviations)
    if mad == 0:
        return [0.0] * len(values)
    return [0.6745 * (v - centre) / mad for v in values]


def anomalies(ws, *, threshold: float = 3.5) -> list[Anomaly]:
    """Flag a number that does not look like the operator's own history.

    Median and MAD, not machine learning, and nothing is reported until there are at least five
    comparable records: a new licensee gets silence rather than a confident guess.
    """
    out: list[Anomaly] = []

    harvests = [(r["id"], float(_amount(r["wet_weight"]))) for r in
                _rows(ws, "SELECT id, wet_weight FROM harvests ORDER BY harvested_at")]
    for (hid, value), z in zip(harvests, _modified_z([v for _i, v in harvests])):
        if abs(z) >= threshold:
            out.append(Anomaly(hid, f"wet weight {value:g} g is unusual for this operation", z))

    lots = [(r["id"], float(_amount(r["original"]))) for r in
            _rows(ws, "SELECT id, original FROM stock_lots ORDER BY created_at")]
    for (lid, value), z in zip(lots, _modified_z([v for _i, v in lots])):
        if abs(z) >= threshold:
            out.append(Anomaly(lid, f"lot size {value:g} is unusual for this operation", z))

    yields: list[tuple[str, float]] = []
    for lot in _rows(ws, "SELECT id, original, kind FROM stock_lots"):
        moves = _rows(ws, "SELECT kind, amount FROM stock_moves WHERE lot_id = ?", (lot["id"],))
        converted = sum((_amount(m["amount"]) for m in moves if m["kind"] == "conversion"), Decimal("0"))
        children = _rows(ws, "SELECT original FROM stock_lots WHERE source_lot_id = ? AND kind != ?",
                         (lot["id"], lot["kind"]))
        result = sum((_amount(c["original"]) for c in children), Decimal("0"))
        if converted > 0 and result > 0:
            yields.append((lot["id"], float(result / converted)))
    for (lid, ratio), z in zip(yields, _modified_z([r for _i, r in yields])):
        if abs(z) >= threshold:
            out.append(Anomaly(lid, f"conversion yield {ratio:.2f} is unusual for this operation", z))
    return out


# -- A7: the brief ------------------------------------------------------------

def _count(n: int, one: str, many: str = "") -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _was(n: int) -> str:
    return "was" if n == 1 else "were"


def _is(n: int) -> str:
    return "is" if n == 1 else "are"


def brief(ws, *, now: datetime | None = None, days: int = 7) -> str:
    """One paragraph about the period, every sentence assembled from counts.

    Deterministic by construction: the same record and the same ``now`` produce the same words.
    """
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    since_text = since.isoformat()

    def count(sql: str, args: tuple = ()) -> int:
        return int(ws.conn.execute(sql, args).fetchone()[0])

    events = count("SELECT COUNT(*) FROM events WHERE occurred_at >= ?", (since_text,))
    if events == 0:
        return f"Nothing was recorded in the {days} days to {now.date().isoformat()}."

    sentences = [f"{_count(events, 'record')} {_was(events)} written in the {days} days to "
                 f"{now.date().isoformat()}."]

    corrections = count("SELECT COUNT(*) FROM amendments WHERE occurred_at >= ?", (since_text,))
    if corrections:
        drafted = count("SELECT COUNT(*) FROM justifications WHERE created_at >= ?", (since_text,))
        sent = count("SELECT COUNT(*) FROM justifications WHERE sent_at >= ?", (since_text,))
        unsent = count("SELECT COUNT(*) FROM justifications WHERE sent_at IS NULL")
        late = count("SELECT COUNT(*) FROM justifications WHERE sent_at IS NOT NULL AND sent_at > deadline")
        piece = f"{_count(corrections, 'correction')} {_was(corrections)} made"
        piece += f", {_count(drafted, 'justification')} drafted"
        piece += f" and {sent} sent"
        if late:
            piece += f", {late} of them after the deadline"
        if unsent:
            piece += f"; {_count(unsent, 'justification')} {_is(unsent)} still waiting to go"
        sentences.append(piece + ".")

    harvests = count("SELECT COUNT(*) FROM harvests WHERE harvested_at >= ?", (since_text,))
    harvest_days = count("SELECT COUNT(*) FROM harvests WHERE scheduled_at IS NULL AND harvested_at IS NOT NULL")
    if harvests:
        piece = f"{_count(harvests, 'harvest')} came in"
        if harvest_days:
            piece += f", {harvest_days} without a schedule on file"
        sentences.append(piece + ".")

    dispatches = count("SELECT COUNT(*) FROM transfers WHERE direction = 'out' AND at >= ?", (since_text,))
    receipts = count("SELECT COUNT(*) FROM transfers WHERE direction = 'in' AND at >= ?", (since_text,))
    outstanding = count("SELECT COUNT(*) FROM manifests WHERE status = 'dispatched'")
    if dispatches or outstanding:
        piece = f"{_count(dispatches, 'manifest')} left the facility"
        if receipts:
            piece += f" and {receipts} {_was(receipts)} received"
        if outstanding:
            piece += f"; {_count(outstanding, 'manifest')} {_is(outstanding)} still out"
        sentences.append(piece + ".")

    outages = count("SELECT COUNT(*) FROM outages WHERE started_at >= ?", (since_text,))
    if outages:
        breaches = count("SELECT COUNT(*) FROM outages WHERE started_at >= ? AND notice_breach_at IS NOT NULL",
                         (since_text,))
        piece = f"The department connection dropped {_count(outages, 'time')}"
        piece += f", with {_count(breaches, 'notice')} later than the deadline" if breaches \
            else " and every notice was drafted inside the deadline"
        sentences.append(piece + ".")

    from .inspect import inspect

    findings = inspect(ws, now=now)
    breaches = sum(1 for f in findings if f.severity == "breach")
    exposures = sum(1 for f in findings if f.severity == "exposure")
    if breaches or exposures:
        # agree with the first noun phrase, the way a person would write it
        parts = []
        if breaches:
            parts.append(_count(breaches, "breach", "breaches"))
        if exposures:
            parts.append(_count(exposures, "exposure"))
        pronoun = "it" if (breaches + exposures) == 1 else "them"
        sentences.append(
            f"As of now there {_is(breaches or exposures)} {' and '.join(parts)} open; "
            f"`coontie audit` lists {pronoun}."
        )
    else:
        sentences.append("Nothing is open with the department by this record's own reading.")
    return " ".join(sentences)
