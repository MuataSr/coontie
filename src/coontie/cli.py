"""The Coontie command line: the entire first-run experience for S1.

    coontie init      create the workspace, the MMTC and its first rooms
    coontie room      add a grow or inventory room
    coontie product   add one product by hand
    coontie import    bring in an incumbent's export
    coontie inventory what we hold, by room
    coontie export    produce the DH5058 inventory list for the integration plan
    coontie verify    check the ledger chain and print counts

No account, no server, no SQL. Everything is a file the operator owns.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from . import forms
from .importer import import_csv
from .products import upid_for, validate_product_row
from .workspace import Facility, Product, Room, Workspace

DEFAULT_DB = "coontie.sqlite3"


def _ws(args) -> Workspace:
    return Workspace(Path(args.db))


def _require_facility(ws: Workspace) -> Facility:
    facility = ws.facility()
    if not facility:
        sys.exit("no facility yet: run `coontie init` first")
    return facility


def cmd_init(args) -> int:
    ws = _ws(args)
    existing = ws.facility()
    if existing:
        sys.exit(f"this workspace already has a facility ({existing.name})")
    facility_id = f"fac-{uuid.uuid4().hex[:8]}"
    ws.add_facility(
        Facility(
            id=facility_id,
            name=args.name,
            license_number=args.license,
            street=args.street or "",
            city=args.city or "",
            zip=args.zip or "",
            contact_name=args.contact or "",
            contact_phone=args.phone or "",
            contact_email=args.email or "",
        )
    )
    for spec in args.room or []:
        kind, name, number = _parse_room(spec)
        ws.add_room(Room(id=f"room-{uuid.uuid4().hex[:8]}", facility_id=facility_id, kind=kind, name=name, number=number))
    print(f"workspace {ws.path}: {args.name} ({args.license})")
    if args.room:
        print(f"rooms: {', '.join(args.room)}")
    print("next: `coontie import --csv <export.csv>` or `coontie product add ...`")
    ws.close()
    return 0


def _parse_room(spec: str) -> tuple[str, str, str]:
    """'grow:G1:01' -> (grow, G1, 01). The kind decides the DH5059 event that records it."""
    parts = spec.split(":")
    if len(parts) != 3 or parts[0] not in ("grow", "inventory"):
        sys.exit(f"room spec must be grow|inventory:NAME:NUMBER, got {spec!r}")
    return parts[0], parts[1], parts[2]


def cmd_room(args) -> int:
    ws = _ws(args)
    facility = _require_facility(ws)
    kind, name, number = _parse_room(args.spec)
    ws.add_room(
        Room(
            id=f"room-{uuid.uuid4().hex[:8]}",
            facility_id=facility.id,
            kind=kind,
            name=name,
            number=number,
            is_quarantine=args.quarantine,
        )
    )
    print(f"room {name} {number} ({kind}) added")
    ws.close()
    return 0


def cmd_product(args) -> int:
    ws = _ws(args)
    facility = _require_facility(ws)
    product_type, route = validate_product_row(product_type=args.type, route=args.route)
    upid, _key = upid_for(
        cultivar=args.cultivar or "",
        size=args.size or "",
        volume=args.volume or "",
        flavor=args.flavor or "",
        thc_mg=args.thc or 0,
        cbd_mg=args.cbd or 0,
        route=route,
        supplied_sku=args.upid or "",
    )
    product = Product(
        id=f"prod-{uuid.uuid4().hex[:10]}",
        facility_id=facility.id,
        name=args.name,
        brand=args.brand or "",
        product_type=product_type,
        route=route,
        upid=upid,
        is_delivery_device=product_type == "Marijuana Delivery Device",
        thc_mg=args.thc,
        cbd_mg=args.cbd,
        weight_g=args.weight,
        size=args.size or "",
        volume=args.volume or "",
        formulation=args.formulation or "",
        cultivar=args.cultivar or "",
        flavor=args.flavor or "",
    )
    product, created = ws.add_product(product)
    print(f"{'created' if created else 'already existed'}: {product.name} -> {product.upid}")
    ws.close()
    return 0


def cmd_import(args) -> int:
    ws = _ws(args)
    facility = _require_facility(ws)
    rooms = [r for r in ws.rooms() if r.kind == "inventory"]
    report = import_csv(
        ws,
        args.csv,
        facility_id=facility.id,
        default_room_id=args.room or (rooms[0].id if rooms else None),
        dry_run=args.dry_run,
    )
    print(report.summary())
    print("mapping: " + ", ".join(f"{k}<-{v}" for k, v in sorted(report.mapping.items())))
    if report.unmapped:
        print("ignored columns: " + ", ".join(report.unmapped))
    for line, reason in report.errors:
        print(f"  row {line}: {reason}")
    if report.rows_failed:
        print("failed rows were skipped; fix them and re-import (existing products are reused)")
    ws.close()
    return 0 if report.rows_failed == 0 else 2


def cmd_inventory(args) -> int:
    ws = _ws(args)
    rows = ws.inventory()
    if not rows:
        print("no inventory yet")
    else:
        width = max(len(r["product"]) for r in rows)
        print(f"{'product'.ljust(width)}  {'qty':>8} {'unit':<4} {'room':<12} {'hold'}")
        for r in rows:
            print(f"{r['product'].ljust(width)}  {r['quantity']:>8} {r['unit']:<4} {r['room']:<12} {'YES' if r['on_hold'] else ''}")
        print(f"\n{len(rows)} lot(s)")
    ws.close()
    return 0


def cmd_export(args) -> int:
    ws = _ws(args)
    facility = _require_facility(ws)
    products = ws.products()
    if not products:
        sys.exit("no products to export yet")
    text = forms.render_csv(products, facility.name)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}: {len(products)} row(s), {len(forms.COLUMNS)} columns ({forms.FORM_ID})")
        print(f"submission target: {forms.SUBMIT_TO}")
    else:
        sys.stdout.write(text)
    ws.close()
    return 0


def cmd_verify(args) -> int:
    ws = _ws(args)
    ok, summary = ws.verify()
    print(("OK   " if ok else "FAIL ") + summary)
    ws.close()
    return 0 if ok else 1


def cmd_amend(args) -> int:
    ws = _ws(args)
    hold = True if args.hold else (False if args.release else None)
    try:
        amendment = ws.amend_lot(
            args.lot,
            new_quantity=args.quantity,
            new_on_hold=hold,
            cause=args.cause,
            reason=args.reason,
            actor=args.actor or "",
        )
    except ValueError as exc:
        sys.exit(str(exc))
    sign = "+" if amendment.delta > 0 else ""
    print(f"{amendment.id}  {amendment.field}: {amendment.before} -> {amendment.after}  ({sign}{amendment.delta} {amendment.unit})  cause={amendment.cause}")
    if amendment.exempt:
        print(f"exempt from the written justification under Rule 64-4.222(12): cause {amendment.cause!r}")
    else:
        justification = ws.create_justification(amendment.id)
        print(f"justification drafted: {justification.id}")
        print(f"deadline: {justification.deadline.isoformat()} (12 hours after the adjustment)")
        print(f"review: coontie justify {justification.id} --show")
        print(f"send:   coontie justify {justification.id} --send")
    ws.close()
    return 0


def cmd_justifications(args) -> int:
    ws = _ws(args)
    rows = ws.justifications(pending_only=args.pending)
    if not rows:
        print("no justifications yet" if not args.pending else "nothing pending: every non-exempt change is sent")
        ws.close()
        return 0
    for j in rows:
        print(f"{j.id}  {j.status:<12} deadline {j.deadline.isoformat()}  {j.subject[:70]}")
    print(f"\n{len(rows)} justification(s)")
    ws.close()
    return 0


def cmd_justify(args) -> int:
    ws = _ws(args)
    matches = [j for j in ws.justifications() if j.id.startswith(args.id)]
    if not matches:
        sys.exit(f"no justification matching {args.id!r}")
    j = matches[0]
    if args.send:
        j = ws.mark_justification_sent(j.id)
        print(f"marked sent to {j.recipient} at {j.sent_at.isoformat()} ({j.status})")
    if args.show or not args.send:
        print(f"subject: {j.subject}")
        print(f"status:  {j.status}   deadline: {j.deadline.isoformat()}")
        if j.sent_at:
            print(f"sent:    {j.sent_at.isoformat()}")
        print("-" * 72)
        print(j.body)
    ws.close()
    return 0


def cmd_journal(args) -> int:
    ws = _ws(args)
    entries = ws.journal(args.lot)
    if not entries:
        sys.exit(f"no history for {args.lot!r}")
    for e in entries:
        detail = e["detail"]
        if e["kind"] == "amendment":
            print(f"{e['when']}  amendment  {detail['field']}: {detail['before']} -> {detail['after']}  cause={detail['cause']}  justification={detail['justification']}")
        else:
            print(f"{e['when']}  {e['kind']:<22} {json.dumps(detail, sort_keys=True)[:110]}")
    print(f"\n{len(entries)} entries, oldest first. The ledger hash chain covers the recorded events.")
    ws.close()
    return 0


def cmd_alerts(args) -> int:
    from . import guardrails

    ws = _ws(args)
    alerts = guardrails.collect(
        lots=ws.lots(),
        products=ws.products(),
        adjustments=ws.adjustment_views(),
        known_rooms={r.id for r in ws.rooms()},
        records=ws.lots(),
    )
    if not alerts:
        print("nothing to fix")
        ws.close()
        return 0
    for a in alerts:
        flag = "BLOCK" if a.blocks else "warn "
        print(f"{flag}  {a.guard.value:<24} {a.message}")
        print(f"        {a.citation}")
        print(f"        action: {a.action}")
    print()
    print(", ".join(f"{v} {k}" for k, v in guardrails.counts(alerts).items()))
    ws.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="coontie", description="Open record for a Florida MMTC's internal seed-to-sale duties.")
    p.add_argument("--db", default=DEFAULT_DB, help=f"workspace file (default {DEFAULT_DB})")
    sub = p.add_subparsers(dest="command", required=True)

    def _db(sp):
        """Allow --db on either side of the subcommand; absent means the value above."""
        sp.add_argument("--db", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        return sp

    init = _db(sub.add_parser("init", help="create the workspace, MMTC and first rooms"))
    init.add_argument("--name", required=True, help="MMTC legal name")
    init.add_argument("--license", required=True, help="MMTC license number")
    init.add_argument("--street")
    init.add_argument("--city")
    init.add_argument("--zip")
    init.add_argument("--contact")
    init.add_argument("--phone")
    init.add_argument("--email")
    init.add_argument("--room", action="append", metavar="KIND:NAME:NUMBER", help="e.g. grow:G1:01")
    init.set_defaults(func=cmd_init)

    room = _db(sub.add_parser("room", help="add a grow or inventory room"))
    room.add_argument("spec", metavar="KIND:NAME:NUMBER")
    room.add_argument("--quarantine", action="store_true")
    room.set_defaults(func=cmd_room)

    product = _db(sub.add_parser("product", help="add one product"))
    product.add_argument("--name", required=True)
    product.add_argument("--type", required=True, help="form product type, e.g. 'Whole Flower'")
    product.add_argument("--route", required=True, help="form route, e.g. 'Smoking'")
    product.add_argument("--brand")
    product.add_argument("--cultivar")
    product.add_argument("--flavor")
    product.add_argument("--size")
    product.add_argument("--volume")
    product.add_argument("--thc", type=float, help="THC mg")
    product.add_argument("--cbd", type=float, help="CBD mg")
    product.add_argument("--weight", type=float, help="product weight in grams")
    product.add_argument("--formulation")
    product.add_argument("--upid", help="adopt an existing SKU as the unique product ID")
    product.set_defaults(func=cmd_product)

    imp = _db(sub.add_parser("import", help="import an incumbent CSV export"))
    imp.add_argument("--csv", required=True)
    imp.add_argument("--room", help="default room id for quantities")
    imp.add_argument("--dry-run", action="store_true")
    imp.set_defaults(func=cmd_import)

    inv = _db(sub.add_parser("inventory", help="what we hold"))
    inv.set_defaults(func=cmd_inventory)

    exp = _db(sub.add_parser("export", help="produce a state form"))
    exp.add_argument("form", choices=["dh5058"])
    exp.add_argument("--out", help="write to a file instead of stdout")
    exp.set_defaults(func=cmd_export)

    ver = _db(sub.add_parser("verify", help="check the ledger chain"))
    ver.set_defaults(func=cmd_verify)

    amd = _db(sub.add_parser("amend", help="correct a lot without deleting the previous value"))
    amd.add_argument("--lot", required=True)
    amd.add_argument("--quantity", help="new quantity")
    amd.add_argument("--hold", action="store_true", help="place the lot on hold")
    amd.add_argument("--release", action="store_true", help="release a hold")
    amd.add_argument("--cause", required=True, help="one of: " + ", ".join(__import__("coontie.amendments", fromlist=["ALL_CAUSES"]).ALL_CAUSES))
    amd.add_argument("--reason", required=True)
    amd.add_argument("--actor", help="who made the change")
    amd.set_defaults(func=cmd_amend)

    jst = _db(sub.add_parser("justifications", help="list correction notices and their deadlines"))
    jst.add_argument("--pending", action="store_true", help="only those not yet sent")
    jst.set_defaults(func=cmd_justifications)

    jfy = _db(sub.add_parser("justify", help="show or send one justification"))
    jfy.add_argument("id", help="justification id (prefix is enough)")
    jfy.add_argument("--show", action="store_true")
    jfy.add_argument("--send", action="store_true")
    jfy.set_defaults(func=cmd_justify)

    jrn = _db(sub.add_parser("journal", help="everything that happened to one record"))
    jrn.add_argument("--lot", required=True)
    jrn.set_defaults(func=cmd_journal)

    alr = _db(sub.add_parser("alerts", help="the guardrails: what is wrong right now"))
    alr.set_defaults(func=cmd_alerts)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
