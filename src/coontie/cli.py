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


def _now_arg(value: str | None):
    from datetime import datetime, timezone

    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def cmd_outage(args) -> int:
    ws = _ws(args)
    when = _now_arg(args.at)
    try:
        if args.start:
            outage = ws.start_outage(when=when)
            print(f"outage {outage.id} open since {outage.started_at.isoformat()}")
            print(f"notice threshold: 2h ({outage.started_at.isoformat()} + 2h); notice deadline: {outage.notice_deadline.isoformat()} (3h)")
            print("run `coontie watch` and the notice drafts itself once two hours have passed")
        elif args.restore:
            outage = ws.restore_outage(args.id, when=when)
            print(f"outage {outage.id} restored at {outage.restored_at.isoformat()}")
            print(f"restoration notice: {outage.restore_subject or '(none)'}")
            print(f"outage CSV: {outage.report_path or '(none)'} ({outage.report_rows} dispensations)")
            print(f"report deadline: {outage.report_deadline.isoformat()} (24 hours after restoration)")
        elif args.send:
            open_outage = ws.open_outage()
            outage_id = args.id or (open_outage.id if open_outage else None)
            if not outage_id:
                sys.exit("give --id: no outage is open")
            recipient = ws.send_outage(outage_id, args.send, when=when)
            print(f"marked {args.send} sent to {recipient}")
        elif args.show:
            from datetime import datetime, timezone

            now = when or datetime.now(timezone.utc)
            outage = ws.outage(args.id) if args.id else ws.open_outage()
            if not outage:
                sys.exit("no outage to show")
            print(f"outage {outage.id}  facility {outage.facility_id}")
            print(f"  started:  {outage.started_at.isoformat()}")
            print(f"  restored: {outage.restored_at.isoformat() if outage.restored_at else '(still open)'}")
            print(f"  duration: {outage.elapsed(now)}")
            print(f"  notice:   {outage.notice_status(now):<14} deadline {outage.notice_deadline.isoformat()}")
            print(f"  report:   {outage.report_status(now):<14} deadline {outage.report_deadline.isoformat() if outage.report_deadline else '-'}")
            print(f"  rows:     {outage.report_rows} dispensations during the outage")
            if outage.notice_body:
                print(f"  notice file: {outage.notice_subject}")
            if outage.report_path:
                print(f"  csv:      {outage.report_path}")
        else:
            rows = ws.outages()
            if not rows:
                print("no outages recorded")
            for o in rows:
                state = "open" if o.open else "restored"
                print(f"{o.id}  {state:<9} started {o.started_at.isoformat()}  notice {o.notice_status()}  report {o.report_status()}  rows {o.report_rows}")
    except ValueError as exc:
        sys.exit(str(exc))
    ws.close()
    return 0


def cmd_watch(args) -> int:
    import time

    ws = _ws(args)
    when = _now_arg(args.at)
    ticks = 0
    try:
        while True:
            actions = ws.watch(now=when)
            ticks += 1
            for line in actions:
                print(line)
            if not args.every:
                if not actions:
                    print("nothing due")
                break
            time.sleep(args.every)
    except KeyboardInterrupt:
        print(f"stopped after {ticks} tick(s)")
    finally:
        ws.close()
    return 0


def cmd_dispense(args) -> int:
    ws = _ws(args)
    try:
        d = ws.record_dispensation(
            patient_id=args.patient,
            inventory_id=args.inventory,
            weight=args.weight,
            unit=args.unit,
            location=args.location or "",
            when=_now_arg(args.at),
            mmur_verified=args.mmur_verified,
            sale_id=args.sale or "",
        )
    except ValueError as exc:
        sys.exit(str(exc))
    flag = "MMUR verified" if d["mmur_verified"] else "no outage open"
    print(f"{d['id']}  {d['dispensed_at'].isoformat()}  patient {d['patient_id']}  {d['weight']} {d['unit']}  {flag}")
    if d["outage_id"]:
        print(f"recorded during outage {d['outage_id']}; it will appear in the outage CSV")
    ws.close()
    return 0


def cmd_link(args) -> int:
    ws = _ws(args)
    try:
        ws.link_lot(args.lot, args.sts_id, when=_now_arg(args.at))
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"{args.lot} linked to department inventory id {args.sts_id}")
    ws.close()
    return 0


def cmd_drift(args) -> int:
    ws = _ws(args)
    action = args.drift_action
    if action == "pull":
        text = Path(args.csv).read_text(encoding="utf-8-sig")
        try:
            sid, rows, rejected = ws.pull_state(text, source_file=str(args.csv), as_of=_now_arg(args.as_of))
        except ValueError as exc:
            sys.exit(str(exc))
        print(f"snapshot {sid}: {rows} record(s) from {args.csv}" + (f", {rejected} rejected" if rejected else ""))
        parsed = getattr(ws, "last_parsed", None)
        if parsed:
            for line, reason in parsed.rejected:
                print(f"  line {line}: {reason}")
        print("next: coontie drift compare")
    elif action == "compare":
        try:
            report, findings = ws.compare_drift(tolerance=args.tolerance)
        except ValueError as exc:
            sys.exit(str(exc))
        print(report.summary())
        unlinked = len(ws.unlinked_lots())
        if unlinked:
            print(f"{unlinked} lot(s) are unlinked and were not compared (coontie link --lot ... --sts-id ...)")
        if report.items:
            print("run `coontie drift serve` to work through them, or `coontie drift show` to read them here")
    elif action == "show":
        rows = ws.drift_findings(open_only=not args.all)
        snapshot = ws.latest_snapshot()
        if not snapshot:
            sys.exit("no state snapshot yet: coontie drift pull --csv <file>")
        print(f"snapshot {snapshot['id']}  {snapshot['as_of'].strftime('%Y-%m-%d %H:%M UTC')}  {snapshot['rows']} record(s)")
        if not rows:
            print("no open differences")
        for f in rows:
            ours = f["ours"] or {}
            theirs = f["theirs"] or {}
            print(
                f"{f['id']}  {f['kind']:<18} {f['record_key']:<16} "
                f"ours {ours.get('quantity', ours.get('status', '-'))} / theirs {theirs.get('quantity', theirs.get('status', '-'))}"
                + (f"  resolved={f['resolution']}" if f["resolution"] else "")
            )
        print(f"{len(rows)} difference(s)")
    elif action == "serve":
        from .driftview import serve

        serve(args.db, port=args.port)
    elif action == "resolve":
        try:
            f = ws.resolve_finding(
                args.ref, args.action, note=args.note or "", quantity=args.quantity,
                product=args.product, room=args.room, actor=args.actor or "operator",
            )
        except ValueError as exc:
            sys.exit(str(exc))
        print(f"{f['id']}  {f['kind']}  resolved: {f['resolution']}")
        if f["resolution_note"]:
            print(f"  {f['resolution_note']}")
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

    out = _db(sub.add_parser("outage", help="record a disconnection, restore it, inspect it"))
    what = out.add_mutually_exclusive_group()
    what.add_argument("--start", action="store_true", help="record that the Department STS connection dropped")
    what.add_argument("--restore", action="store_true", help="record that the connection came back")
    what.add_argument("--show", action="store_true", help="state of one outage (or the open one)")
    what.add_argument("--send", choices=["notice", "restoration", "report"], help="mark one artifact sent")
    out.add_argument("--id", help="outage id (defaults to the open one)")
    out.add_argument("--at", help="ISO timestamp, for simulation and back-entry")
    out.set_defaults(func=cmd_outage)

    wat = _db(sub.add_parser("watch", help="one unattended tick: draft whatever the clock says is due"))
    wat.add_argument("--once", action="store_true", help="deprecated; one tick is the default")
    wat.add_argument("--every", type=int, metavar="SECONDS", help="keep ticking every N seconds")
    wat.add_argument("--at", help="ISO timestamp, for simulation")
    wat.set_defaults(func=cmd_watch)

    dsp = _db(sub.add_parser("dispense", help="record a dispensation"))
    dsp.add_argument("--patient", required=True, help="patient MMUR number")
    dsp.add_argument("--inventory", required=True, help="department seed-to-sale inventory identification number")
    dsp.add_argument("--weight", required=True)
    dsp.add_argument("--unit", default="g")
    dsp.add_argument("--location", help="dispensing facility location")
    dsp.add_argument("--sale", help="MMTC sale id")
    dsp.add_argument("--mmur-verified", action="store_true", help="registry checked before dispensing")
    dsp.add_argument("--at", help="ISO timestamp, for simulation")
    dsp.set_defaults(func=cmd_dispense)

    lnk = _db(sub.add_parser("link", help="attach the department inventory id to a lot"))
    lnk.add_argument("--lot", required=True)
    lnk.add_argument("--sts-id", required=True, dest="sts_id")
    lnk.add_argument("--at", help="ISO timestamp, for back-entry")
    lnk.set_defaults(func=cmd_link)

    drf = _db(sub.add_parser("drift", help="compare our record with the state's copy"))
    drift_sub = drf.add_subparsers(dest="drift_action", required=True)

    d_pull = _db(drift_sub.add_parser("pull", help="store the department's export as a snapshot"))
    d_pull.add_argument("--csv", required=True)
    d_pull.add_argument("--as-of", help="when the export was taken")
    d_pull.set_defaults(func=cmd_drift)

    d_cmp = _db(drift_sub.add_parser("compare", help="classify every difference"))
    d_cmp.add_argument("--tolerance", default="0.05", help="quantity difference treated as agreement (default 0.05)")
    d_cmp.set_defaults(func=cmd_drift)

    d_show = _db(drift_sub.add_parser("show", help="list the differences in the terminal"))
    d_show.add_argument("--all", action="store_true", help="include resolved ones")
    d_show.set_defaults(func=cmd_drift)

    d_serve = _db(drift_sub.add_parser("serve", help="open the one-screen drift view on localhost"))
    d_serve.add_argument("--port", type=int, default=8770)
    d_serve.set_defaults(func=cmd_drift)

    d_res = _db(drift_sub.add_parser("resolve", help="resolve one difference"))
    d_res.add_argument("ref", help="finding id (prefix is enough)")
    d_res.add_argument("--action", required=True,
                       choices=["accept_state", "keep_local", "recount", "record_state", "resend"])
    d_res.add_argument("--quantity", help="for recount")
    d_res.add_argument("--note")
    d_res.add_argument("--product", help="for record_state, if the name does not match")
    d_res.add_argument("--room", help="for record_state, if the room does not match")
    d_res.add_argument("--actor")
    d_res.set_defaults(func=cmd_drift)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
