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
        j = ws.mark_justification_sent(j.id, _now_arg(args.at))
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


def cmd_employee(args) -> int:
    ws = _ws(args)
    try:
        employee = ws.add_employee(
            full_name=args.name, date_of_birth=args.dob, hire_date=args.hire_date,
            email=args.email, at=_now_arg(args.at),
        )
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"{employee.id}  {employee.full_name}  hired {employee.hire_date.isoformat()}  "
          f"{employee.email}")
    print("date of birth is on the record and deliberately not printed again")
    ws.close()
    return 0


def cmd_api_user(args) -> int:
    ws = _ws(args)
    try:
        user = ws.add_api_user(
            email=args.email, password=args.password, permissions=args.permissions,
            at=_now_arg(args.at),
        )
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"{user.id}  {user.email}  permissions: {', '.join(user.permissions)}")
    print("a verifier was recorded; the password itself is not on the record and cannot be read back")
    ws.close()
    return 0


def cmd_outbox(args) -> int:
    from . import transmission

    ws = _ws(args)
    try:
        now = _now_arg(args.at)
        from datetime import datetime, timezone
        now = now or datetime.now(timezone.utc)
        state = transmission.backlog(ws, now=now)
        waiting = transmission.owed(ws, now=now)
        print(f"{state['waiting']} record(s) not yet sent"
              + (f", oldest {_human_age(state['oldest'])}" if state["waiting"] else ""))
        if state["overdue"]:
            print(f"{state['overdue']} of them are past the department's window")
        for item in waiting[:12]:
            mark = "OVERDUE" if item.overdue(now) else "waiting"
            print(f"  {item.seq:5d}  {mark:8s} {local_iso(item.due_at)}  {item.title}")
        if len(waiting) > 12:
            print(f"  ... and {len(waiting) - 12} more")
        made = transmission.packages(ws)
        if made:
            print()
            print("packages:")
            for pack in made:
                print(f"  {pack.id}  {pack.state:12s} {pack.events:4d} record(s)  "
                      f"{pack.path.name}")
                if pack.result:
                    print(f"      {pack.result}")
        if not made:
            print()
            print("nothing has been sealed yet; `coontie transmit --package` writes a file a person "
                  "can hand over")
        print()
        print("Coontie has no department adapter, so it cannot tell you whether a record arrived")
        print("(DH5059 gives 12 hours by default, real time for dispensing and transfers)")
    finally:
        ws.close()
    return 0


def _human_age(delta) -> str:
    total = int(delta.total_seconds())
    days, rest = divmod(total, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days} d {hours} h"
    if hours:
        return f"{hours} h {minutes} m"
    return f"{minutes} m"


def local_iso(moment) -> str:
    """The operator's clock with the zone spelled out, the same rule the screens follow."""
    try:
        from zoneinfo import ZoneInfo

        return moment.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M %Z")
    except Exception:
        return moment.isoformat()


def cmd_transmit(args) -> int:
    from . import transmission

    ws = _ws(args)
    try:
        at = _now_arg(args.at)
        if args.package:
            try:
                pack = transmission.package(ws, at=at, limit=args.limit, adapter=args.adapter)
            except transmission.OutboxError as exc:
                sys.exit(str(exc))
            print(f"sealed {pack.events} record(s), sequences {pack.first_seq}-{pack.last_seq}")
            print(f"  {pack.path}")
            print(f"  sha256 {pack.sha256}")
            print("nothing was sent; a package is a file, not a delivery")
            return 0
        if args.abandon:
            try:
                pack = transmission.abandon(ws, args.abandon, reason=args.reason or "", at=at)
            except transmission.OutboxError as exc:
                sys.exit(str(exc))
            print(f"{pack.id} withdrawn: {pack.result}")
            print("the records it carried are waiting again")
            return 0
        adapter = transmission.adapter_for(args.adapter, folder=args.to)
        try:
            pack = transmission.hand_over(ws, args.send, adapter=adapter, at=at)
        except transmission.OutboxError as exc:
            sys.exit(str(exc))
        print(f"{pack.id} {pack.state}: {pack.result}")
        if pack.state != transmission.HANDED_OVER:
            print("the records are still waiting; seal a new package when the adapter can take it")
        else:
            print("handed over is not delivered: no receipt exists without a department adapter")
    finally:
        ws.close()
    return 0


def cmd_backup(args) -> int:
    from . import backup as backups

    if args.verify:
        ok, problems, manifest = backups.verify(args.verify)
        print(f"{manifest['database']['name']}: {manifest.get('events')} events, head "
              f"{str(manifest.get('chain_head'))[:8]}, {len(manifest.get('reports', []))} report file(s)")
        for line in problems:
            print(f"  {line}")
        print("this backup verifies" if ok else f"{len(problems)} problem(s); it must not be used")
        return 0 if ok else 1

    if not args.to:
        sys.exit("give --to <directory> to write a backup, or --verify <path> to check one")
    ws = _ws(args)
    try:
        saved = backups.backup(ws, args.to)
    except backups.BackupError as exc:
        sys.exit(str(exc))
    finally:
        ws.close()
    print(f"backed up {saved.events} events ending {saved.chain_head[:8]} to {saved.database}")
    print(f"manifest {saved.manifest.name} lists {len(saved.reports)} report file(s)")
    if args.keep:
        try:
            removed = backups.prune(args.to, args.keep)
        except backups.BackupError as exc:
            sys.exit(str(exc))
        print(f"kept {args.keep}: " + (f"removed {', '.join(removed)}" if removed else "nothing to prune"))
    print("run `coontie drill` on a copy if this is the first backup of the year")
    return 0


def cmd_restore(args) -> int:
    from . import backup as backups

    try:
        result = backups.restore(args.source, args.db, force=args.force, actor=args.actor or "")
    except backups.BackupError as exc:
        sys.exit(str(exc))
    print(f"restored {result['events']} events into {result['target']}")
    print(f"chain head {result['chain_head'][:8]} matches the manifest before the restore was recorded")
    for table in sorted(result["after"]):
        before = result["before"].get(table, 0)
        if result["before"] and before != result["after"][table]:
            print(f"  {table}: {before} -> {result['after'][table]}")
    print("`coontie audit` on the restored record is the next check")
    return 0


def cmd_drill(args) -> int:
    from . import backup as backups

    try:
        for step in backups.drill(args.db, into=args.into):
            print(step)
    except backups.BackupError as exc:
        sys.exit(f"drill FAILED: {exc}")
    return 0


def cmd_theme(args) -> int:
    from . import theme

    ws = _ws(args)
    if args.set:
        if not (args.look and args.voice):
            sys.exit("give --look and --voice; `coontie theme --list` shows the names")
        try:
            chosen = ws.set_appearance(look=args.look, voice=args.voice, actor=args.actor or "")
        except ValueError as exc:
            sys.exit(str(exc))
        print(f"look {chosen['look']}, voice {chosen['voice']} recorded"
              f"{' by ' + chosen['set_by'] if chosen['set_by'] else ''}")
        print("the choice is on the ledger; the record, the exports and the printed pages are unchanged")
        ws.close()
        return 0

    if args.check:
        problems = theme.check_all()
        for key, term in theme.TERMS.items():
            if not theme.catalogue_reference(term):
                problems.append(f"{key} points at {term}, which the record cannot cite")
        chosen = ws.appearance()
        print(f"installed: look {chosen['look']}, voice {chosen['voice']}")
        for line in problems:
            print(f"  {line}")
        print("the look and voice layer holds" if not problems else f"{len(problems)} problem(s)")
        ws.close()
        return 0 if not problems else 1

    chosen = ws.appearance()
    print(f"installed: look {chosen['look']}, voice {chosen['voice']}")
    print()
    print("looks:")
    for name in sorted(theme.SKINS):
        mark = "*" if name == chosen["look"] else " "
        print(f" {mark} {name:10s} {theme.SKIN_TITLES.get(name, '')}")
    print("voices:")
    for name in ["canonical", *sorted(theme.VOICES)]:
        mark = "*" if name == chosen["voice"] else " "
        print(f" {mark} {name:10s} {theme.VOICE_TITLES.get(name, '')}")
    print()
    print("coontie theme --set --look calm --voice shop --actor \"Maria Lopez\"")
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
        from .web import announce, serve as serve_app

        httpd = serve_app(args.db, port=args.port)
        announce(httpd)
        print(f"the drift screen is at http://127.0.0.1:{args.port}/drift", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped", flush=True)
        finally:
            httpd.server_close()
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


def cmd_integration(args) -> int:
    ws = _ws(args)
    if args.show or not args.approved_on:
        record = ws.integration()
        if not record:
            print("no integration recorded")
            print("cultivation cannot start until it is: Rule 64-4.221(4)")
        else:
            print(f"integration approved {record['approved_on'].date().isoformat()}  reference {record['reference'] or '(none)'}")
        ws.close()
        return 0
    record = ws.record_integration(_now_arg(args.approved_on), args.reference or "", args.note or "")
    print(f"integration recorded: approved {record['approved_on'].date().isoformat()}, reference {record['reference'] or '(none)'}")
    print("cultivation may now be recorded")
    ws.close()
    return 0


def cmd_batch(args) -> int:
    from .cultivation import parse_plants

    ws = _ws(args)
    try:
        batch = ws.start_batch(
            cultivar=args.cultivar, room=args.room, count=args.count,
            mother_plant_id=(parse_plants(args.mother)[0] if args.mother else ""),
            when=_now_arg(args.at),
        )
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"{batch.id}  {batch.count} x {batch.cultivar} into {batch.room_id}")
    print(f"next: coontie plant --batch {batch.id} --count {batch.count}")
    ws.close()
    return 0


def cmd_plant(args) -> int:
    ws = _ws(args)
    try:
        made = ws.plant_batch(args.batch, args.count, at=_now_arg(args.at), is_mother=args.mother)
    except ValueError as exc:
        sys.exit(str(exc))
    ids = [p.id for p in made]
    print(f"{len(ids)} plant(s) recorded: {ids[0]}" + (f"..{ids[-1]}" if len(ids) > 1 else ""))
    ws.close()
    return 0


def cmd_move(args) -> int:
    from .cultivation import parse_plants

    ws = _ws(args)
    if bool(args.plants) == bool(args.lot):
        sys.exit("give --plants or --lot, not both and not neither")
    try:
        if args.lot:
            lot = ws.move_inventory(args.lot, args.to, note=args.note or "", at=_now_arg(args.at))
            print(f"{lot.id}  moved to {args.to}; {lot.quantity} {lot.unit} on the record")
            ws.close()
            return 0
        moved = ws.move_plants(parse_plants(args.plants), args.to, at=_now_arg(args.at))
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"{len(moved)} plant(s) moved to {args.to}")
    ws.close()
    return 0


def cmd_additive(args) -> int:
    from .cultivation import parse_plants

    ws = _ws(args)
    try:
        additive = ws.apply_additive(
            parse_plants(args.plants), description=args.what, amount=args.amount, unit=args.unit,
            at=_now_arg(args.at),
        )
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"{additive.id}  {additive.amount} {additive.unit} of {additive.description} on {len(additive.plant_ids)} plant(s)")
    ws.close()
    return 0


def cmd_harvest(args) -> int:
    from .cultivation import parse_plants

    ws = _ws(args)
    ids = parse_plants(args.plants)
    try:
        if args.schedule:
            harvest = ws.schedule_harvest(ids, at=_now_arg(args.at))
            print(f"{harvest.id}  {len(ids)} plant(s) scheduled for harvest")
            print(f"next: coontie harvest --plants {args.plants} --wet <g> --room <post-harvest room>")
        else:
            for required in ("wet", "room"):
                if getattr(args, required) in (None, ""):
                    sys.exit(f"a harvest needs --{required}")
            harvest = ws.harvest(
                ids, wet=args.wet, waste=args.waste or "0", other=args.other or "0", unit=args.unit,
                post_harvest_room=args.room, at=_now_arg(args.at),
            )
            print(
                f"{harvest.id}  harvested {len(harvest.plant_ids)} plant(s): "
                f"{harvest.wet_weight} {harvest.wet_unit} wet flower, "
                f"{harvest.waste_weight} waste, {harvest.other_weight} other, into {harvest.post_harvest_room_id}"
            )
    except ValueError as exc:
        sys.exit(str(exc))
    ws.close()
    return 0


def cmd_growing(args) -> int:
    ws = _ws(args)
    plants = ws.plants()
    if not plants:
        print("no plants yet")
        ws.close()
        return 0
    by_room = ws.growing()
    for room, n in sorted(by_room.items()):
        print(f"{room:<14} {n} growing")
    states: dict[str, int] = {}
    for p in plants:
        states[p.state] = states.get(p.state, 0) + 1
    print(", ".join(f"{v} {k}" for k, v in sorted(states.items())))
    for h in ws.harvests():
        state = "harvested" if h.completed else "scheduled"
        print(
            f"{h.id}  {state:<10} {len(h.plant_ids)} plant(s)"
            + (f"  {h.wet_weight} {h.wet_unit} wet into {h.post_harvest_room_id}" if h.completed else "")
        )
    ws.close()
    return 0


def cmd_dispose(args) -> int:
    from .cultivation import parse_plants

    ws = _ws(args)
    try:
        if args.lot:
            if args.schedule:
                if not args.reason:
                    sys.exit("a disposal schedule needs --reason")
                disposal = ws.schedule_disposal_lot(args.lot, reason=args.reason, at=_now_arg(args.at))
                print(f"{disposal.id}  lot {args.lot} scheduled for destruction "
                      f"({disposal.weight} {disposal.unit}); 72 hours must pass before destroying it")
            else:
                disposal = ws.dispose_lot(args.lot, at=_now_arg(args.at))
                print(f"{disposal.id}  lot {args.lot} destroyed; {disposal.weight} {disposal.unit} off the record")
            ws.close()
            return 0
        if args.matter:
            disposal = ws.dispose_matter(weight=args.matter, unit=args.unit, at=_now_arg(args.at))
            print(f"{disposal.id}  plant matter disposed: {disposal.weight} {disposal.unit}")
        else:
            if not args.plants:
                sys.exit("give --plants or --matter")
            ids = parse_plants(args.plants)
            if args.schedule:
                for required in ("reason",):
                    if not getattr(args, required):
                        sys.exit("a disposal schedule needs --reason")
                disposal = ws.schedule_disposal_plants(ids, reason=args.reason, at=_now_arg(args.at))
                print(f"{disposal.id}  {len(ids)} plant(s) scheduled for disposal; 72 hours must pass before disposing")
            else:
                disposal = ws.dispose_plants(ids, at=_now_arg(args.at))
                print(f"{disposal.id}  {len(ids)} plant(s) disposed")
    except ValueError as exc:
        sys.exit(str(exc))
    ws.close()
    return 0


def _date_arg(value: str):
    from datetime import datetime, timezone

    if not value:
        return None
    text = value.strip()
    if len(text) == 10:
        return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def cmd_cure(args) -> int:
    ws = _ws(args)
    try:
        cure = ws.cure(args.harvest, post=args.post, waste=args.waste or "0", unit=args.unit, room=args.room,
                       at=_now_arg(args.at))
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"{cure.id}  cured {cure.post_weight} {cure.post_unit} ({cure.waste_weight} waste) from {cure.harvest_id}")
    available = ws.cured_available(cure.harvest_id)
    print(f"available to allocate into lots: {available} {cure.post_unit}")
    ws.close()
    return 0


def cmd_lot(args) -> int:
    ws = _ws(args)
    try:
        lot = ws.new_lot(kind=args.kind, cultivar=args.cultivar or "", weight=args.weight, unit=args.unit,
                         room=args.room, harvest_id=args.harvest or "", at=_now_arg(args.at))
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"{lot.id}  {lot.original} {lot.unit} of {lot.kind} {lot.cultivar} in {lot.room_id}")
    ws.close()
    return 0


def cmd_split(args) -> int:
    ws = _ws(args)
    try:
        child = ws.split_lot(args.lot, amount=args.amount, to_room=args.to, at=_now_arg(args.at))
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"{child.id}  {child.original} {child.unit} split into {child.room_id}; {args.lot} now holds "
          f"{ws.stock_remaining(child.source_lot_id)} {child.unit}")
    ws.close()
    return 0


def cmd_convert(args) -> int:
    ws = _ws(args)
    try:
        child = ws.convert(args.lot, remove=args.remove, resulting_kind=args.to, resulting_weight=args.resulting,
                           waste=args.waste or "0", room=args.room, at=_now_arg(args.at))
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"{child.id}  {child.original} {child.unit} of {child.kind} from {args.lot}; "
          f"source now holds {ws.stock_remaining(child.source_lot_id)} {child.unit}")
    ws.close()
    return 0


def cmd_ingredient(args) -> int:
    from .processing import parse_csv_list

    ws = _ws(args)
    try:
        parsed = ws.add_ingredients(
            args.lot, names=parse_csv_list(args.name), amounts=parse_csv_list(args.amount),
            units=parse_csv_list(args.unit), at=_now_arg(args.at),
        )
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"{len(parsed)} ingredient(s) added to {args.lot}: " + ", ".join(f"{n} {a} {u}" for n, a, u in parsed))
    ws.close()
    return 0


def cmd_adjust(args) -> int:
    ws = _ws(args)
    try:
        amendment, justification = ws.adjust_stock(
            args.lot, remove=args.remove, cause=args.cause, reason=args.reason,
            actor=args.actor or "", at=_now_arg(args.at),
        )
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"{amendment.id}  {amendment.before} -> {amendment.after} {amendment.unit}  cause={amendment.cause}")
    if amendment.exempt:
        print(f"exempt from the written justification under Rule 64-4.222(12): {amendment.cause}")
    else:
        print(f"justification drafted: {justification.id}  deadline {justification.deadline.isoformat()}")
        print(f"review: coontie justify {justification.id} --show")
    ws.close()
    return 0


def cmd_sample(args) -> int:
    ws = _ws(args)
    try:
        sample = ws.lab_sample(args.lot, weight=args.weight, cmtl_id=args.cmtl, is_rnd=args.rnd,
                               at=_now_arg(args.at))
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"{sample.id}  {sample.weight} {sample.unit} to {sample.cmtl_id}"
          + (" (research and development)" if sample.is_rnd else ""))
    if sample.note:
        print(sample.note)
    ws.close()
    return 0


def cmd_final(args) -> int:
    ws = _ws(args)
    try:
        final = ws.final_product(
            args.lot, upid=args.upid, unit_count=args.units, net_weight=args.net, unit=args.unit,
            weight_per_unit=args.per_unit, packaged_at=_date_arg(args.packaged), expiration=args.expires,
            room=args.room, approved_name=args.approved or "", product_type=args.type or "",
            at=_now_arg(args.at),
        )
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"{final.id}  {final.unit_count} x {final.upid}: {final.net_weight} {final.unit} "
          f"({final.weight_per_unit or '-'} per unit), expires {final.expiration_date.isoformat()}")
    print(f"{args.lot} now holds {ws.stock_remaining(final.lot_id)} {final.unit}")
    ws.close()
    return 0


def cmd_device(args) -> int:
    ws = _ws(args)
    try:
        device = ws.add_device(inventory_type=args.type, unit_count=args.units, room=args.room,
                               upid=args.upid or "", at=_now_arg(args.at))
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"{device.id}  {device.unit_count} x {device.inventory_type} into {device.room_id}")
    ws.close()
    return 0


def cmd_stock(args) -> int:
    ws = _ws(args)
    lots = ws.stock_lots()
    if not lots:
        print("no processing lots yet")
        ws.close()
        return 0
    print(f"{'lot':<14} {'kind':<22} {'original':>9} {'remaining':>9} {'room':<10} source")
    for lot in lots:
        left = ws.stock_remaining(lot.id)
        rooms = {r.id: r.name for r in ws.rooms()}
        print(
            f"{lot.id:<14} {lot.kind[:22]:<22} {lot.original:>9} {left:>9} "
            f"{rooms.get(lot.room_id, lot.room_id):<10} "
            f"{lot.source_lot_id or (lot.harvest_ids[0] if lot.harvest_ids else '')}"
        )
    for final in ws.finals():
        print(f"{final.id:<14} {final.product_type[:22]:<22} {final.unit_count:>9} units  "
              f"expires {final.expiration_date.isoformat()}  {final.upid}")
    for sample in ws.samples():
        print(f"{sample.id:<14} sample {sample.weight} {sample.unit} -> {sample.cmtl_id}")
    ws.close()
    return 0


def _pairs(values: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for chunk in values or []:
        lot, _, qty = chunk.partition(":")
        if not qty:
            raise SystemExit(f"expected LOT:QUANTITY, got {chunk!r}")
        out[lot.strip()] = qty.strip()
    return out


def cmd_vehicle(args) -> int:
    ws = _ws(args)
    try:
        vehicle = ws.register_vehicle(
            name=args.name or args.plate, vin=args.vin or "", plate=args.plate, make=args.make or "",
            model=args.model or "", year=str(args.year or ""), color=args.color or "",
            in_service=not args.out_of_service, at=_now_arg(args.at),
        )
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"{vehicle.id}  {vehicle.name}: {vehicle.description or '(make and model not recorded)'} "
          f"plate {vehicle.plate}" + ("" if vehicle.in_service else "  OUT OF SERVICE"))
    ws.close()
    return 0


def cmd_vehicles(args) -> int:
    ws = _ws(args)
    rows = ws.vehicles()
    if not rows:
        print("no vehicles registered")
    for v in rows:
        print(f"{v.id}  {v.name:<16} {v.description:<24} {v.plate:<12} "
              + ("in service" if v.in_service else "OUT OF SERVICE"))
    ws.close()
    return 0


def cmd_manifest(args) -> int:
    from .transport import parse_crew

    ws = _ws(args)
    items = []
    for chunk in args.item or []:
        parts = chunk.split(":")
        if len(parts) < 2:
            sys.exit(f"expected LOT:QUANTITY[:FORM], got {chunk!r}")
        items.append((parts[0], parts[1], parts[2] if len(parts) > 2 else ""))
    try:
        manifest = ws.build_manifest(
            recipient_name=args.recipient, recipient_address=args.address, vehicle=args.vehicle,
            employee_ids=parse_crew(args.employees), departure_at=_date_arg(args.depart),
            arrival_at=_date_arg(args.arrive), items=items, route=args.route or "",
            stops=tuple(args.stop or []), at=_now_arg(args.at),
        )
    except ValueError as exc:
        sys.exit(str(exc))
    path = ws.manifest_artifact(manifest.id)
    print(f"{manifest.id}  {len(items)} item(s) to {manifest.recipient_name}, "
          f"departing {manifest.departure_at.isoformat()}, arriving {manifest.arrival_at.isoformat()}")
    print(f"manifest page: {path}")
    print(f"next: coontie dispatch --manifest {manifest.id}")
    ws.close()
    return 0


def cmd_manifests(args) -> int:
    ws = _ws(args)
    rows = ws.manifests()
    if not rows:
        print("no manifests yet")
    for m in rows:
        print(f"{m.id}  {m.status:<11} {m.recipient_name[:28]:<28} depart {m.departure_at.date()} "
              f"crew {len(m.employee_ids)}  vehicle {m.vehicle_id}")
    ws.close()
    return 0


def cmd_dispatch(args) -> int:
    ws = _ws(args)
    try:
        manifest = ws.dispatch_manifest(args.manifest, at=_now_arg(args.at))
    except ValueError as exc:
        sys.exit(str(exc))
    for item in ws.manifest_items(manifest.id):
        print(f"  out: {item['quantity']} {item['unit']} of {item['form']} (lot {item['lot_id']}); "
              f"remaining {ws.stock_remaining(item['lot_id'])}")
    print(f"{manifest.id}  {manifest.status}")
    print(f"next: coontie receive --manifest {manifest.id} --receiver \"<name>\" --room <room>")
    ws.close()
    return 0


def cmd_receive(args) -> int:
    ws = _ws(args)
    try:
        manifest = ws.receive_manifest(
            args.manifest, receiver_name=args.receiver, room=args.room,
            received=_pairs(args.received), rejected=_pairs(args.rejected), at=_now_arg(args.at),
        )
    except ValueError as exc:
        sys.exit(str(exc))
    for t in ws.transfers(manifest.id):
        if t["direction"] != "in":
            continue
        for d in t["detail"]:
            print(f"  in: {d['received']} {d['unit']} received, {d['rejected']} rejected of {d['quantity']} "
                  f"({d['form']}, lot {d['lot_id']})")
    print(f"{manifest.id}  {manifest.status}  acknowledged by {args.receiver}")
    ws.close()
    return 0


def cmd_invoice(args) -> int:
    ws = _ws(args)
    try:
        invoice_id = ws.record_invoice(
            args.manifest, buyer=args.buyer, seller=args.seller, price=args.price,
            quantity=args.quantity, unit=args.unit, at=_now_arg(args.at),
        )
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"{invoice_id}  wholesale invoice recorded against {args.manifest}")
    ws.close()
    return 0


def cmd_audit(args) -> int:
    """The inspection simulator: what the department would find today."""
    import json as _json

    from .inspect import BREACH, CANNOT_CHECK, EXPOSURE, NOTE, as_dict, inspect, summarize

    ws = _ws(args)
    findings = inspect(ws, now=_now_arg(args.at))
    if args.json:
        print(_json.dumps(as_dict(findings), indent=2))
    else:
        counts = summarize(findings)
        print(f"Coontie inspection: {counts[BREACH]} breach(es), {counts[EXPOSURE]} exposure(s), "
              f"{counts[NOTE]} note(s)")
        if not findings:
            print("Nothing found. That is not a guarantee: see what this system cannot check.")
        for f in findings:
            print("  " + f.line())
            if f.detail:
                print(f"            {f.detail}")
        print()
        print("What this cannot check")
        for c in CANNOT_CHECK:
            print(f"  - {c.area}: {c.why}")
    ws.close()
    return 1 if (args.strict and any(f.severity == BREACH for f in findings)) else 0


def cmd_lineage(args) -> int:
    from .insight import lineage

    ws = _ws(args)
    try:
        lines = lineage(ws, args.ref)
    except ValueError as exc:
        sys.exit(str(exc))
    for line in lines:
        print(line.render())
    ws.close()
    return 0


def cmd_explain(args) -> int:
    from .insight import explain

    ws = _ws(args)
    try:
        candidates = explain(ws, args.lot, gap=args.gap)
    except ValueError as exc:
        sys.exit(str(exc))
    if not candidates:
        print("nothing has moved out of that lot")
    for c in candidates:
        print(c.line())
    if args.gap not in (None, ""):
        matches = [c for c in candidates if c.matches]
        print(f"\n{len(matches)} move(s) match a difference of {args.gap}")
        if not matches:
            print("no single move accounts for it; the difference may be in the department's record, "
                  "not ours")
    ws.close()
    return 0


def cmd_next(args) -> int:
    from .insight import prefill, prefill_command

    ws = _ws(args)
    got = prefill(ws, args.recipient or "")
    if not got:
        print("no manifests yet, nothing to reuse")
        ws.close()
        return 0
    print(f"defaults from {got['from_manifest']} (last departure {got['last_departure'][:16]})")
    print(f"  recipient  {got['recipient_name']}")
    print(f"  address    {got['recipient_address']}")
    print(f"  vehicle    {got['vehicle_id']}")
    print(f"  crew       {', '.join(got['employees'])}")
    for lot, qty, form in got["items"]:
        print(f"  item       {qty} of {form} (lot {lot})")
    print()
    print(prefill_command(ws, args.recipient or ""))
    ws.close()
    return 0


def cmd_anomalies(args) -> int:
    from .insight import anomalies

    ws = _ws(args)
    found = anomalies(ws, threshold=args.threshold)
    if not found:
        print("nothing unusual, or not enough history to say (five records of a kind is the floor)")
    for a in found:
        print(a.line())
    ws.close()
    return 0


def cmd_brief(args) -> int:
    from .insight import brief

    ws = _ws(args)
    print(brief(ws, now=_now_arg(args.at), days=args.days))
    ws.close()
    return 0


def cmd_serve(args) -> int:
    """The appliance interface, on loopback."""
    from .web import announce, serve

    httpd = serve(args.db, port=args.port, verbose=args.verbose)
    announce(httpd)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped", flush=True)
    finally:
        httpd.server_close()
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
    jfy.add_argument("--at", help="when it was sent, ISO; defaults to now")
    jfy.set_defaults(func=cmd_justify)

    jrn = _db(sub.add_parser("journal", help="everything that happened to one record"))
    jrn.add_argument("--lot", required=True)
    jrn.set_defaults(func=cmd_journal)

    alr = _db(sub.add_parser("alerts", help="the guardrails: what is wrong right now"))
    alr.set_defaults(func=cmd_alerts)

    integ = _db(sub.add_parser("integration", help="record the department's approval of your integration"))
    integ.add_argument("--approved-on", help="date the integration was approved (yyyy-mm-dd)")
    integ.add_argument("--reference", help="the integration plan reference")
    integ.add_argument("--note")
    integ.add_argument("--show", action="store_true")
    integ.set_defaults(func=cmd_integration)

    bat = _db(sub.add_parser("batch", help="start a batch of seeds or clones"))
    bat.add_argument("--cultivar", required=True)
    bat.add_argument("--room", required=True)
    bat.add_argument("--count", type=int, required=True)
    bat.add_argument("--mother", help="mother plant id, if the cuttings came from one of yours")
    bat.add_argument("--at")
    bat.set_defaults(func=cmd_batch)

    pln = _db(sub.add_parser("plant", help="turn part of a batch into plants"))
    pln.add_argument("--batch", required=True)
    pln.add_argument("--count", type=int, required=True)
    pln.add_argument("--mother", action="store_true", help="keep these as mother plants")
    pln.add_argument("--at")
    pln.set_defaults(func=cmd_plant)

    mv = _db(sub.add_parser("move", help="move plants or a product lot to another room"))
    mv.add_argument("--plants", help="PL-0001,PL-0002 or a range PL-0001..PL-0012")
    mv.add_argument("--lot", help="a product lot id; moves inventory rather than plants")
    mv.add_argument("--to", required=True)
    mv.add_argument("--note")
    mv.add_argument("--at")
    mv.set_defaults(func=cmd_move)

    add = _db(sub.add_parser("additive", help="record an additive applied to plants"))
    add.add_argument("--plants", required=True)
    add.add_argument("--what", required=True, help="active ingredient, concentration, manufacturer lot, EPA reg")
    add.add_argument("--amount", required=True)
    add.add_argument("--unit", default="ml")
    add.add_argument("--at")
    add.set_defaults(func=cmd_additive)

    hrv = _db(sub.add_parser("harvest", help="schedule a harvest, then record it"))
    hrv.add_argument("--plants", required=True)
    hrv.add_argument("--schedule", action="store_true", help="record the schedule only")
    hrv.add_argument("--wet", help="wet flower weight")
    hrv.add_argument("--waste")
    hrv.add_argument("--other", help="other material weight")
    hrv.add_argument("--unit", default="g")
    hrv.add_argument("--room", help="post-harvest room")
    hrv.add_argument("--at")
    hrv.set_defaults(func=cmd_harvest)

    grw = _db(sub.add_parser("growing", help="what is in the grow rooms"))
    grw.set_defaults(func=cmd_growing)

    dsp2 = _db(sub.add_parser("dispose", help="dispose of plants or plant matter"))
    dsp2.add_argument("--plants")
    dsp2.add_argument("--lot", help="a product lot id: schedule its destruction, then destroy it")
    dsp2.add_argument("--matter", help="weight of post-defoliation matter")
    dsp2.add_argument("--reason")
    dsp2.add_argument("--unit", default="g")
    dsp2.add_argument("--schedule", action="store_true", help="schedule the disposal; 72 hours must pass first")
    dsp2.add_argument("--at")
    dsp2.set_defaults(func=cmd_dispose)

    cur = _db(sub.add_parser("cure", help="record a cure/dry of a harvest"))
    cur.add_argument("--harvest", required=True)
    cur.add_argument("--post", required=True, help="post-cure weight")
    cur.add_argument("--waste")
    cur.add_argument("--unit", default="g")
    cur.add_argument("--room", required=True)
    cur.add_argument("--at")
    cur.set_defaults(func=cmd_cure)

    lot = _db(sub.add_parser("lot", help="create a processing inventory lot"))
    lot.add_argument("--kind", required=True, help="cured and dried flower, extract, edible, ...")
    lot.add_argument("--cultivar")
    lot.add_argument("--weight", required=True)
    lot.add_argument("--unit", default="g")
    lot.add_argument("--room", required=True)
    lot.add_argument("--harvest", help="the harvest it came from")
    lot.add_argument("--at")
    lot.set_defaults(func=cmd_lot)

    spl = _db(sub.add_parser("split", help="split a lot into a sublot"))
    spl.add_argument("--lot", required=True)
    spl.add_argument("--amount", required=True)
    spl.add_argument("--to", required=True)
    spl.add_argument("--at")
    spl.set_defaults(func=cmd_split)

    cnv = _db(sub.add_parser("convert", help="convert inventory through processing"))
    cnv.add_argument("--lot", required=True)
    cnv.add_argument("--remove", required=True)
    cnv.add_argument("--to", required=True, help="resulting inventory type")
    cnv.add_argument("--resulting", required=True, help="resulting weight")
    cnv.add_argument("--waste")
    cnv.add_argument("--room", required=True)
    cnv.add_argument("--at")
    cnv.set_defaults(func=cmd_convert)

    ing = _db(sub.add_parser("ingredient", help="add ingredients to a lot"))
    ing.add_argument("--lot", required=True)
    ing.add_argument("--name", required=True, help="comma separated ingredient names")
    ing.add_argument("--amount", required=True, help="comma separated amounts")
    ing.add_argument("--unit", required=True, help="comma separated units")
    ing.add_argument("--at")
    ing.set_defaults(func=cmd_ingredient)

    adj2 = _db(sub.add_parser("adjust", help="correct a processing lot (cause required)"))
    adj2.add_argument("--lot", required=True)
    adj2.add_argument("--remove", required=True)
    adj2.add_argument("--cause", required=True)
    adj2.add_argument("--reason", required=True)
    adj2.add_argument("--actor")
    adj2.add_argument("--at")
    adj2.set_defaults(func=cmd_adjust)

    smp = _db(sub.add_parser("sample", help="take a lab sample from a lot"))
    smp.add_argument("--lot", required=True)
    smp.add_argument("--weight", required=True)
    smp.add_argument("--cmtl", required=True, help="the certified testing laboratory")
    smp.add_argument("--rnd", action="store_true", help="research and development sample")
    smp.add_argument("--at")
    smp.set_defaults(func=cmd_sample)

    fin = _db(sub.add_parser("final", help="record a final product"))
    fin.add_argument("--lot", required=True)
    fin.add_argument("--upid", required=True)
    fin.add_argument("--units", type=int, required=True)
    fin.add_argument("--net", required=True, help="net weight or volume")
    fin.add_argument("--unit", default="g")
    fin.add_argument("--per-unit", help="weight per unit")
    fin.add_argument("--packaged", required=True, help="packaging date")
    fin.add_argument("--expires", required=True, help="expiration date (immutable once recorded)")
    fin.add_argument("--room", required=True)
    fin.add_argument("--approved", help="department-approved product name")
    fin.add_argument("--type", help="product type; defaults to the catalogue's")
    fin.add_argument("--at")
    fin.set_defaults(func=cmd_final)

    dev = _db(sub.add_parser("device", help="record delivery device inventory"))
    dev.add_argument("--type", required=True, help="inventory type")
    dev.add_argument("--units", type=int, required=True)
    dev.add_argument("--room", required=True)
    dev.add_argument("--upid")
    dev.add_argument("--at")
    dev.set_defaults(func=cmd_device)

    stk = _db(sub.add_parser("stock", help="processing lots, final products, samples"))
    stk.set_defaults(func=cmd_stock)

    veh = _db(sub.add_parser("vehicle", help="register a delivery vehicle"))
    veh.add_argument("--name")
    veh.add_argument("--plate", required=True)
    veh.add_argument("--vin")
    veh.add_argument("--make")
    veh.add_argument("--model")
    veh.add_argument("--year")
    veh.add_argument("--color")
    veh.add_argument("--out-of-service", action="store_true")
    veh.add_argument("--at")
    veh.set_defaults(func=cmd_vehicle)

    vehs = _db(sub.add_parser("vehicles", help="list registered vehicles"))
    vehs.set_defaults(func=cmd_vehicles)

    man = _db(sub.add_parser("manifest", help="build a transportation manifest"))
    man.add_argument("--recipient", required=True)
    man.add_argument("--address", required=True)
    man.add_argument("--vehicle", required=True)
    man.add_argument("--employees", required=True, help="comma separated names, at least two")
    man.add_argument("--depart", required=True, help="departure date and time")
    man.add_argument("--arrive", required=True, help="estimated arrival date and time")
    man.add_argument("--item", action="append", metavar="LOT:QTY[:FORM]", help="repeatable")
    man.add_argument("--route")
    man.add_argument("--stop", action="append")
    man.add_argument("--at")
    man.set_defaults(func=cmd_manifest)

    mans = _db(sub.add_parser("manifests", help="list manifests"))
    mans.set_defaults(func=cmd_manifests)

    dsp3 = _db(sub.add_parser("dispatch", help="record the transfer out (real time)"))
    dsp3.add_argument("--manifest", required=True)
    dsp3.add_argument("--at")
    dsp3.set_defaults(func=cmd_dispatch)

    rcv = _db(sub.add_parser("receive", help="record the transfer in (real time)"))
    rcv.add_argument("--manifest", required=True)
    rcv.add_argument("--receiver", required=True)
    rcv.add_argument("--room", required=True)
    rcv.add_argument("--received", action="append", metavar="LOT:QTY")
    rcv.add_argument("--rejected", action="append", metavar="LOT:QTY")
    rcv.add_argument("--at")
    rcv.set_defaults(func=cmd_receive)

    invc = _db(sub.add_parser("invoice", help="record a wholesale invoice for a manifest"))
    invc.add_argument("--manifest", required=True)
    invc.add_argument("--buyer", required=True)
    invc.add_argument("--seller", required=True)
    invc.add_argument("--price", required=True)
    invc.add_argument("--quantity", required=True)
    invc.add_argument("--unit", default="g")
    invc.add_argument("--at")
    invc.set_defaults(func=cmd_invoice)

    lin = _db(sub.add_parser("lineage", help="where a jar came from"))
    lin.add_argument("ref", help="a final product id (fin-...) or a lot (stk-...)")
    lin.set_defaults(func=cmd_lineage)

    exp = _db(sub.add_parser("explain", help="what in our history could explain a difference"))
    exp.add_argument("--lot", required=True)
    exp.add_argument("--gap", help="the difference you are trying to account for")
    exp.set_defaults(func=cmd_explain)

    nxt = _db(sub.add_parser("next", help="defaults for the next manifest"))
    nxt.add_argument("--recipient")
    nxt.set_defaults(func=cmd_next)

    ano = _db(sub.add_parser("anomalies", help="numbers that do not look like your own history"))
    ano.add_argument("--threshold", type=float, default=3.5, help="modified z-score (default 3.5)")
    ano.set_defaults(func=cmd_anomalies)

    brf = _db(sub.add_parser("brief", help="a paragraph about the period, assembled from counts"))
    brf.add_argument("--days", type=int, default=7)
    brf.add_argument("--at")
    brf.set_defaults(func=cmd_brief)

    srv = _db(sub.add_parser("serve", help="start the appliance interface on 127.0.0.1"))
    srv.add_argument("--port", type=int, default=8080)
    srv.add_argument("--verbose", action="store_true", help="log each request")
    srv.set_defaults(func=cmd_serve)

    aud = _db(sub.add_parser("audit", help="what the department would find today"))
    aud.add_argument("--json", action="store_true", help="machine-readable findings")
    aud.add_argument("--strict", action="store_true", help="exit 1 if anything is a breach")
    aud.add_argument("--at", help="treat this moment as now (ISO)")
    aud.set_defaults(func=cmd_audit)

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

    emp = _db(sub.add_parser("employee", help="record an MMTC employee"))
    emp.add_argument("--name", required=True, help="full name, as the payroll file has it")
    emp.add_argument("--dob", required=True, help="date of birth, YYYY-MM-DD")
    emp.add_argument("--hire-date", required=True, dest="hire_date", help="YYYY-MM-DD")
    emp.add_argument("--email", required=True)
    emp.add_argument("--at")
    emp.set_defaults(func=cmd_employee)

    apiu = _db(sub.add_parser("api-user", help="record an authorized API user"))
    apiu.add_argument("--email", required=True)
    apiu.add_argument("--permissions", required=True,
                      help="comma separated, for example inventory.read,transport.write")
    apiu.add_argument("--password", required=True,
                      help="used to derive a verifier; the plaintext is never stored")
    apiu.add_argument("--at")
    apiu.set_defaults(func=cmd_api_user)

    obx = _db(sub.add_parser("outbox", help="what has not reached the department yet"))
    obx.add_argument("--at")
    obx.set_defaults(func=cmd_outbox)

    txm = _db(sub.add_parser("transmit", help="seal what is owed, hand it over, or withdraw it"))
    group = txm.add_mutually_exclusive_group(required=True)
    group.add_argument("--package", action="store_true", help="seal the waiting records into one file")
    group.add_argument("--send", metavar="PACKAGE", help="hand a sealed package to an adapter")
    group.add_argument("--abandon", metavar="PACKAGE", help="withdraw a sealed package, with a reason")
    txm.add_argument("--adapter", default="stub", choices=("stub", "folder"))
    txm.add_argument("--to", help="the directory a folder hand-off writes into")
    txm.add_argument("--limit", type=int, help="seal at most this many records")
    txm.add_argument("--reason", help="why a package is being withdrawn")
    txm.add_argument("--at")
    txm.set_defaults(func=cmd_transmit)

    bak = _db(sub.add_parser("backup", help="copy the record so it can be restored"))
    bak.add_argument("--to", help="the directory to write the backup into")
    bak.add_argument("--keep", type=int, help="after copying, delete the oldest beyond this many")
    bak.add_argument("--verify", metavar="PATH", help="verify an existing backup instead of writing one")
    bak.add_argument("--actor", help="who ran it")
    bak.set_defaults(func=cmd_backup)

    rst = _db(sub.add_parser("restore", help="restore the record from a verified backup"))
    rst.add_argument("--from", dest="source", required=True, help="the backup database or manifest")
    rst.add_argument("--force", action="store_true", help="overwrite an existing record")
    rst.add_argument("--actor", help="who ran it")
    rst.set_defaults(func=cmd_restore)

    drl = _db(sub.add_parser("drill", help="prove a backup restores, and that tampering is caught"))
    drl.add_argument("--into", help="a scratch directory; a temporary one is used otherwise")
    drl.set_defaults(func=cmd_drill)

    thm = _db(sub.add_parser("theme", help="the look and the voice of the screens"))
    thm.add_argument("--list", action="store_true", help="what can be installed")
    thm.add_argument("--set", action="store_true", help="install a look and a voice")
    thm.add_argument("--look")
    thm.add_argument("--voice")
    thm.add_argument("--actor", help="who chose it; the choice goes on the record")
    thm.add_argument("--check", action="store_true", help="prove the installed ones, and the built-ins, hold")
    thm.set_defaults(func=cmd_theme)

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
