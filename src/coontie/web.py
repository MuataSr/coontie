"""The appliance interface: standard library only, server-rendered, one POST one write.

`coontie serve` starts this on 127.0.0.1 and the operator works in a browser that is already
installed. No JavaScript, no build step, no CDN, no network. Every page is generated from SQLite
on each request, so two windows cannot disagree.

Security model (see docs/flows/gui.md):

- bind to loopback only, and refuse any request whose Host is not that address;
- a session token minted at startup, set as an HttpOnly SameSite=Strict cookie, and required as a
  hidden field on every POST;
- Origin must be this server on every POST, because any page in the operator's browser can POST
  to loopback;
- the operator name is a claim for attribution, never a credential. The OS login is the boundary.
"""

from __future__ import annotations

import html
import re
import secrets
import sys
import threading
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import assist
from .inspect import BREACH, EXPOSURE, NOTE, inspect, summarize
from .insight import brief
from .workspace import Workspace

CSS = """
:root { --ink:#1d232a; --muted:#5d6b7a; --line:#d8dee6; --bg:#fbfcfd; --card:#fff;
        --breach:#a4262c; --exposure:#8a5a00; --note:#3b6ea5; --accent:#14532d; }
* { box-sizing:border-box; }
body { margin:0; font:15px/1.5 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       color:var(--ink); background:var(--bg); }
a { color:var(--accent); }
header { display:flex; align-items:center; gap:18px; padding:10px 18px; background:var(--card);
         border-bottom:1px solid var(--line); position:sticky; top:0; }
header .name { font-weight:600; }
header .spacer { flex:1; }
header .badge { text-decoration:none; border:1px solid var(--line); border-radius:999px;
                padding:2px 10px; font-size:13px; }
header .badge.hot { border-color:var(--breach); color:var(--breach); }
.layout { display:flex; min-height:calc(100vh - 52px); }
nav { width:190px; padding:14px 10px; border-right:1px solid var(--line); background:var(--card); }
nav a { display:block; padding:7px 10px; border-radius:6px; text-decoration:none; color:var(--ink); }
nav a:hover { background:#eef2f6; }
nav a.here { background:#e6efe9; font-weight:600; }
main { flex:1; padding:22px 26px 60px; max-width:900px; }
h1 { font-size:21px; margin:0 0 4px; }
h2 { font-size:16px; margin:26px 0 8px; padding-bottom:4px; border-bottom:1px solid var(--line); }
p.lede { color:var(--muted); margin:0 0 18px; }
p.context { color:var(--muted); font-size:14px; margin:0; max-width:70ch; }
.sentence { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:14px 16px; }
ul.findings { list-style:none; padding:0; margin:0; }
ul.findings li.row { padding:11px 0 11px 12px; border-bottom:1px solid var(--line);
                     border-left:3px solid var(--line);
                     display:grid; grid-template-columns:auto 1fr; column-gap:10px; row-gap:4px; }
ul.findings li.row.breach { border-left-color:var(--breach); }
ul.findings li.row.exposure { border-left-color:var(--exposure); }
ul.findings li.row.note { border-left-color:var(--note); }
.headline { display:contents; }
.headline > span:not(.sev) { font-size:15px; line-height:1.45; align-self:baseline; }
.meta { grid-column:2; font-size:13px; color:var(--muted); display:flex; gap:10px;
        flex-wrap:wrap; align-items:center; }
.meta code { color:var(--accent); }
.sev { font-size:12px; letter-spacing:.05em; text-transform:uppercase; font-weight:700;
       padding:2px 7px; border-radius:4px; flex:none; align-self:start; }
.sev.breach { color:#fff; background:var(--breach); }
.sev.exposure { color:#fff; background:var(--exposure); }
.sev.note { color:#fff; background:var(--note); }
.cite { color:var(--muted); font-size:13px; }
code, pre { font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:13px; }
pre { background:#0f172a; color:#e6edf3; padding:12px 14px; border-radius:8px; overflow-x:auto; }
label { display:block; font-weight:600; margin:12px 0 4px; }
input[type=text], textarea { width:100%; padding:9px 10px; border:1px solid var(--line);
       border-radius:6px; font:inherit; background:var(--card); }
textarea { min-height:90px; }
button { margin-top:14px; padding:9px 16px; border:0; border-radius:6px; background:var(--accent);
         color:#fff; font:inherit; font-weight:600; cursor:pointer; }
button.quiet { background:#dbe9df; color:var(--accent); border:1px solid #b9cfc1; }
.refusal { border-left:4px solid var(--breach); background:#fdf3f3; padding:10px 14px;
           border-radius:4px; margin:14px 0; }
.note { border-left:4px solid var(--accent); background:#f1f7f3; padding:10px 14px;
        border-radius:4px; margin:14px 0; }
footer { color:var(--muted); font-size:13px; margin-top:34px; border-top:1px solid var(--line);
         padding-top:10px; }
table { border-collapse:collapse; width:100%; }
th.num, td.num { text-align:right; font-variant-numeric:tabular-nums; }
td.ident { font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:13px; }
tr.picked td { background:#e6efe9; }
tr.picked td:first-child { box-shadow:inset 3px 0 0 var(--accent); font-weight:600; }
tr.held td { background:#fdf6ec; }
pre.lineage { background:#f6f8fa; color:var(--ink); border:1px solid var(--line);
              white-space:pre; line-height:1.5; }
form.filters { margin:0 0 6px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
form.filters input[type=text] { width:120px; }
th, td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); font-size:14px; }
.muted { color:var(--muted); }
@media print {
  header, nav, footer, form, button { display:none !important; }
  main { max-width:none; padding:0; }
  body { background:#fff; }
  h2 { page-break-after:avoid; }
}
"""

RAIL = [
    ("/", "Today", "t"),
    ("/say", "Say it", "y"),
    ("/inventory", "Inventory", "i"),
    ("/plant", "Plant", "l"),
    ("/process", "Process", "p"),
    ("/transport", "Transport", "r"),
    ("/correct", "Correct", "c"),
    ("/drift", "Drift", "d"),
    ("/audit", "Audit", "a"),
    ("/setup", "Setup", "s"),
]

# Screens this build actually serves. A finding that would link to a screen not yet built shows
# the command instead, so the interface never offers a dead link.
BUILT = {"/": "Today", "/say": "Say it", "/inventory": "Inventory", "/audit": "Audit",
         "/operator": "Operator"}


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def prose(text) -> str:
    """Escape the record's own sentences, then render `command` spans as code.

    The brief is written once and read in two places, so it keeps its backticks and the HTML
    layer turns them into code instead of showing them as punctuation.
    """
    escaped = esc(text)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)


def page(*, title: str, body: str, here: str = "", facility: str = "", operator: str = "",
         token: str = "", badge: tuple[int, str] | None = None) -> str:
    rail = "".join(
        f'<a href="{esc(path)}" accesskey="{key}" class="{"here" if path == here else ""}">'
        f"{esc(label)}</a>"
        for path, label, key in RAIL
    )
    badge_html = ""
    if badge is not None:
        count, target = badge
        badge_html = (f'<a class="badge{" hot" if count else ""}" href="{esc(target)}">'
                      f"{count} open</a>")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · Coontie</title><style>{CSS}</style></head>
<body>
<header>
  <span class="name">{esc(facility or "Coontie")}</span>
  {badge_html}
  <span class="spacer"></span>
  <form method="post" action="/operator" style="margin:0">
    <input type="hidden" name="token" value="{esc(token)}">
    <label for="operator" style="display:inline; margin:0 6px 0 0; font-weight:400">Operator</label>
    <input id="operator" name="operator" type="text" value="{esc(operator)}" size="16"
           placeholder="your name" style="width:150px; display:inline-block">
    <button type="submit" class="quiet" style="margin:0 0 0 6px; padding:5px 10px">Set</button>
  </form>
</header>
<div class="layout">
  <nav aria-label="Sections">{rail}</nav>
  <main>
{body}
  </main>
</div>
</body></html>"""


def _finding_link(finding, commands: dict[str, str]) -> str:
    """A finding links to the screen that fixes it, or names the command if that screen is not built."""
    target = commands.get(finding.code)
    if not target:
        return ""
    if "{subject}" in target:
        if not finding.subject:
            return ""
        target = target.replace("{subject}", str(finding.subject))
    if target.startswith("/") and target.split("?")[0] in BUILT:
        return f'<a href="{esc(target)}">fix</a>'
    return f'<code class="muted">{esc(target)}</code>'


FIX_ROUTES = {
    "justification_missing": "coontie justifications",
    "justification_unsent": "coontie justify --show <id>",
    "justification_late": "coontie justify --show <id>",
    "disconnect_notice_missing": "coontie outage --show",
    "outage_report_missing": "coontie outage --show",
    "expired_available": "coontie stock",
    "hold_unresolved": "coontie inventory",
    "manifest_unreceived": "coontie manifests",
    "manifest_no_invoice": "coontie invoice --manifest <id>",
    "harvest_unscheduled": "coontie growing",
    "disposal_early": "",
    "stock_unit_mismatch": "/inventory?lot={subject}",
    "stock_negative": "/inventory?lot={subject}",
    "stock_no_origin": "/inventory?lot={subject}",
    "drift_open": "/drift",
    "ledger_broken": "coontie verify",
    "location_missing": "coontie journal",
}


class App:
    """Everything the handler needs, built once per server."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.token = secrets.token_urlsafe(24)
        self.lock = threading.Lock()

    # -- pages ---------------------------------------------------------------

    def render_today(self, ws: Workspace, operator: str) -> str:
        now = datetime.now(timezone.utc)
        findings = inspect(ws, now=now)
        counts = summarize(findings)
        facility = ws.facility()
        body = ['<h1>Today</h1>',
                f'<p class="lede">{esc(now.strftime("%A %-d %B %Y, %H:%M UTC"))}</p>']

        groups = [(BREACH, "Breaches"), (EXPOSURE, "Exposures"), (NOTE, "Notes")]
        any_rows = False
        for severity, heading in groups:
            rows = [f for f in findings if f.severity == severity]
            if not rows:
                continue
            any_rows = True
            body.append(f"<h2>{esc(heading)}</h2><ul class='findings'>")
            for f in rows:
                link = _finding_link(f, FIX_ROUTES)
                cite = f'<span class="cite">({esc(f.citation)})</span>' if f.citation else ""
                # the subject is usually already inside the summary; repeating it reads as debug output
                where = (f'<span class="cite">{esc(f.subject)}</span>'
                         if f.subject and str(f.subject) not in f.summary else "")
                body.append(
                    f'<li class="row {esc(f.severity)}">'
                    f'<div class="headline"><span class="sev {esc(f.severity)}">{esc(f.severity)}</span>'
                    f"<span>{esc(f.summary)}</span></div>"
                    f'<div class="meta">{where} {cite} {link}</div></li>'
                )
            body.append("</ul>")

        due = self._due(ws, now)
        if due:
            any_rows = True
            body.append("<h2>Due</h2><ul class='findings'>")
            for line in due:
                body.append(f"<li>{line}</li>")
            body.append("</ul>")

        if not any_rows:
            body.append(
                "<div class='note'>Nothing is open. "
                "<a href='/audit'>Audit</a> lists what this record can and cannot check.</div>"
            )

        body.append("<h2>This week</h2>")
        body.append(f"<p class='context'>{prose(brief(ws, now=now, days=7))}</p>")
        body.append("<footer>coontie audit</footer>")
        return page(title="Today", body="\n".join(body), here="/", operator=operator,
                    facility=facility.name if facility else "", token=self.token,
                    badge=(counts[BREACH] + counts[EXPOSURE], "/audit"))

    def _due(self, ws: Workspace, now: datetime) -> list[str]:
        out: list[str] = []
        soon = (now + timedelta(hours=12)).isoformat()
        rows = ws.conn.execute(
            "SELECT id, deadline FROM justifications WHERE sent_at IS NULL AND deadline <= ? "
            "ORDER BY deadline", (soon,)
        ).fetchall()
        for r in rows:
            out.append(f"Justification <code>{esc(r['id'])}</code> is due "
                       f"{esc(str(r['deadline'])[:16].replace('T', ' '))} UTC")
        for r in ws.conn.execute(
            "SELECT id, recipient_name FROM manifests WHERE status = 'dispatched' ORDER BY created_at"
        ).fetchall():
            out.append(f"Manifest <code>{esc(r['id'])}</code> to {esc(r['recipient_name'])} is still out")
        for r in ws.conn.execute(
            "SELECT h.id FROM harvests h LEFT JOIN cures c ON c.harvest_id = h.id "
            "WHERE h.harvested_at IS NOT NULL AND c.id IS NULL ORDER BY h.harvested_at"
        ).fetchall():
            out.append(f"Harvest <code>{esc(r['id'])}</code> is harvested and not yet cured")
        for r in ws.conn.execute(
            "SELECT id, started_at FROM outages WHERE restored_at IS NULL ORDER BY started_at DESC"
        ).fetchall():
            started = datetime.fromisoformat(str(r["started_at"]).replace("Z", "+00:00"))
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            hours = (now - started).total_seconds() / 3600
            state = "past the notice threshold" if hours > 2 else "inside the notice window"
            out.append(f"The department connection is down ({hours:.1f}h, {state}), "
                       f"recorded {esc(r['id'])}")
        return out

    def render_say(self, ws: Workspace, operator: str, sentence: str = "") -> str:
        body = ["<h1>Say it</h1>",
                "<p class='lede'>Type it the way you would say it. Nothing is written: the parse "
                "opens a form you can read first.</p>",
                "<form method='post' action='/say'>",
                f"<input type='hidden' name='token' value='{esc(self.token)}'>",
                "<label for='sentence'>What are you doing?</label>",
                f"<textarea id='sentence' name='sentence' placeholder='send 200 g blue dream to "
                f"tampa with maria and dev'>{esc(sentence)}</textarea>",
                "<button type='submit'>Show me</button></form>"]

        if sentence.strip():
            vocab = self._vocabulary(ws)
            parsed = assist.parse_command(sentence, **vocab)
            body.append("<h2>What that means</h2>")
            if not parsed.ok:
                body.append("<div class='refusal'>" + "<br>".join(esc(n) for n in parsed.notes) + "</div>")
            else:
                body.append(f"<p><strong>{esc(parsed.intent)}</strong></p>")
                if parsed.args:
                    body.append("<table><tbody>")
                    for key, value in parsed.args.items():
                        body.append(f"<tr><th>{esc(key)}</th><td>{esc(value)}</td></tr>")
                    body.append("</tbody></table>")
                if parsed.notes:
                    body.append("<div class='note'>" + "<br>".join(esc(n) for n in parsed.notes) + "</div>")
                body.append("<h2>The command</h2>")
                body.append(f"<pre>{esc(parsed.command())}</pre>")
                body.append(
                    "<div class='note'>This is exactly what the form will run. The "
                    f"{esc(parsed.intent)} screen arrives in a later build; until then the command "
                    "above is the path.</div>"
                )
            body.append("<footer>coontie say — nothing written</footer>")
        return page(title="Say it", body="\n".join(body), here="/say", operator=operator,
                    facility=(ws.facility().name if ws.facility() else ""), token=self.token)

    def render_inventory(self, ws: Workspace, operator: str, params: dict) -> str:
        from .insight import lineage

        room_filter = (params.get("room") or "").strip()
        held_only = params.get("held") == "1"
        selected = (params.get("lot") or "").strip()

        lots = ws.stock_lots()
        rooms = {room.id: room.name for room in ws.rooms()}
        if room_filter:
            lots = [lot for lot in lots if lot.room_id == room_filter or
                    rooms.get(lot.room_id, "") == room_filter]

        product_rows = ws.conn.execute(
            "SELECT l.id, l.room_id, l.quantity, l.unit, l.on_hold, p.name, p.cultivar, p.product_type, p.upid "
            "FROM lots l JOIN products p ON p.id = l.product_id ORDER BY l.created_at, l.rowid"
        ).fetchall()
        held = [r for r in product_rows if r["on_hold"]]
        if held_only:
            product_rows = held
        if room_filter:
            product_rows = [r for r in product_rows if r["room_id"] == room_filter or
                            rooms.get(r["room_id"], "") == room_filter]

        body = ["<h1>Inventory</h1>",
                "<p class='lede'>What the facility holds, and where each lot came from.</p>"]

        if selected:
            lines = lineage(ws, selected)
            body.append(f"<h2>Lineage for <code>{esc(selected)}</code> "
                        f"<a class='cite' href='/inventory' style='font-weight:400'>clear</a></h2>")
            body.append("<pre class='lineage'>" + esc("\n".join(line.render() for line in lines)) + "</pre>")

        body += [
                "<form method='get' action='/inventory' class='filters'>",
                "<label for='room'>Room</label> <input id='room' name='room' type='text' "
                f"value='{esc(room_filter)}' size='8'> ",
                "<label for='held' style='display:inline'>Held only</label> ",
                f"<input id='held' name='held' type='checkbox' value='1' {'checked' if held_only else ''}> ",
                "<button type='submit' class='quiet'>Filter</button>",
                "</form>"]

        # "held only" means exactly that: processing lots carry no hold flag, so they are out
        if not held_only:
            body.append(f"<h2>Processing lots ({len(lots)})</h2>")
        if lots and not held_only:
            body.append("<table><thead><tr><th>Lot</th><th>Kind</th><th>Cultivar</th>"
                        "<th class='num'>Original</th><th class='num'>Remaining</th><th>Unit</th>"
                        "<th>Room</th><th>Source</th></tr></thead><tbody>")
            for lot in lots:
                remaining = ws.stock_remaining(lot.id)
                source = lot.source_lot_id or (lot.harvest_ids[0] if lot.harvest_ids else "")
                mark = " class='picked'" if selected and (
                    lot.id == selected or lot.id.startswith(selected)) else ""
                source_cell = (f"<a class='cite' href='/inventory?lot={esc(source)}'>{esc(source)}</a>"
                               if source else "")
                body.append(
                    f"<tr{mark}><td class='ident'>"
                    f"<a href='/inventory?lot={esc(lot.id)}'>{esc(lot.id)}</a></td>"
                    f"<td>{esc(lot.kind)}</td><td>{esc(lot.cultivar)}</td>"
                    f"<td class='num'>{esc(lot.original)}</td>"
                    f"<td class='num'><strong>{esc(remaining)}</strong></td>"
                    f"<td>{esc(lot.unit)}</td>"
                    f"<td>{esc(rooms.get(lot.room_id, lot.room_id))}</td>"
                    f"<td>{source_cell}</td></tr>"
                )
            body.append("</tbody></table>")
        elif not held_only:
            body.append("<p class='muted'>No processing lots match.</p>")

        if held:
            body.append(f"<h2>Held product inventory ({len(held)})</h2>")
            body.append("<table><thead><tr><th>Lot</th><th>Product</th><th>Quantity</th>"
                        "<th>Room</th><th>Hold</th></tr></thead><tbody>")
            for r in held:
                body.append(
                    f"<tr class='held'><td>{esc(r['id'])}</td>"
                    f"<td>{esc(r['name'])} <span class='cite'>{esc(r['product_type'])}</span></td>"
                    f"<td>{esc(r['quantity'])} {esc(r['unit'])}</td>"
                    f"<td>{esc(rooms.get(r['room_id'], r['room_id']))}</td>"
                    f"<td><span class='sev breach'>on hold</span></td></tr>"
                )
            body.append("</tbody></table>")

        if product_rows and not held_only:
            body.append(f"<h2>Product inventory ({len(product_rows)})</h2>")
            body.append("<table><thead><tr><th>Lot</th><th>Product</th><th>Type</th>"
                        "<th class='num'>Quantity</th><th>Unit</th><th>Room</th>"
                        "<th>Unique product id</th></tr></thead><tbody>")
            for r in product_rows:
                body.append(
                    f"<tr><td class='ident'>{esc(r['id'])}</td>"
                    f"<td>{esc(r['name'])} <span class='cite'>{esc(r['cultivar'])}</span></td>"
                    f"<td>{esc(r['product_type'])}</td>"
                    f"<td class='num'>{esc(r['quantity'])}</td>"
                    f"<td>{esc(r['unit'])}</td>"
                    f"<td>{esc(rooms.get(r['room_id'], r['room_id']))}</td>"
                    f"<td class='cite'>{esc(r['upid'])}</td></tr>"
                )
            body.append("</tbody></table>")

        body.append("<footer>coontie lineage &lt;lot&gt;</footer>")
        return page(title="Inventory", body="\n".join(body), here="/inventory", operator=operator,
                    facility=(ws.facility().name if ws.facility() else ""), token=self.token)

    def _vocabulary(self, ws: Workspace) -> dict:
        lots = [(lot.id, lot.cultivar) for lot in ws.stock_lots()]
        cultivars = tuple(sorted({c for _i, c in lots if c}))
        rooms = tuple(sorted({room.name for room in ws.rooms()}))
        manifests = tuple(m.id for m in ws.manifests() if m.status == "built")
        # the crew of previous manifests is the only roster the record holds, and it is enough
        people = tuple(sorted({name for m in ws.manifests() for name in m.employee_ids}))
        return {"cultivars": cultivars, "rooms": rooms, "labs": assist.KNOWN_LABS,
                "people": people, "manifests": manifests, "lots": tuple(lots)}


# -- request handling --------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "Coontie"
    sys_version = ""
    app: App  # set by serve()

    def log_message(self, fmt: str, *args) -> None:  # quiet by default
        if getattr(self.server, "verbose", False):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # -- helpers -------------------------------------------------------------

    def _expected_host(self) -> str:
        return f"{self.server.server_address[0]}:{self.server.server_address[1]}"

    def _check_host(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        allowed = {self._expected_host().lower(), f"localhost:{self.server.server_address[1]}"}
        return host in allowed

    def _check_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True  # same-origin form posts from older browsers; the token still applies
        origin = origin.strip().lower()
        port = self.server.server_address[1]
        return origin in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    def _cookie_token(self) -> str:
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            name, _, value = part.strip().partition("=")
            if name == "coontie_session":
                return value
        return ""

    def _send(self, code: int, body: str, *, ctype: str = "text/html; charset=utf-8",
              headers: dict | None = None) -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _operator(self) -> str:
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            name, _, value = part.strip().partition("=")
            if name == "coontie_operator":
                return urllib.parse.unquote(value)
        return ""

    def _ws(self) -> Workspace:
        return Workspace(self.app.db_path)

    def _with_ws(self, render) -> None:
        ws = self._ws()
        try:
            body = render(ws)
        finally:
            ws.close()
        self._send(200, body, headers=self._session_cookie())

    def _session_cookie(self) -> dict:
        if self._cookie_token() == self.app.token:
            return {}
        return {"Set-Cookie": f"coontie_session={self.app.token}; HttpOnly; SameSite=Strict; Path=/"}

    # -- verbs ---------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        if not self._check_host():
            self._send(403, "Host not allowed")
            return
        path = urllib.parse.urlsplit(self.path).path.rstrip("/") or "/"
        operator = self._operator()
        if path == "/health":
            self._send(200, "ok", ctype="text/plain; charset=utf-8")
            return
        if path == "/":
            self._with_ws(lambda ws: self.app.render_today(ws, operator))
            return
        if path == "/say":
            self._with_ws(lambda ws: self.app.render_say(ws, operator))
            return
        if path == "/inventory":
            params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query,
                                                 keep_blank_values=True))
            ws = self._ws()
            try:
                body = self.app.render_inventory(ws, operator, params)
            except ValueError as exc:
                self._send(404, f"<p>{html.escape(str(exc))}</p>")
                return
            finally:
                ws.close()
            self._send(200, body, headers=self._session_cookie())
            return
        if path == "/audit":
            self._with_ws(lambda ws: self._render_audit(ws, operator))
            return
        if path in {p for p, _l, _k in RAIL}:
            self._with_ws(lambda ws: self._render_pending(path, ws, operator))
            return
        self._send(404, "Not found")

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if not self._check_host() or not self._check_origin():
            self._send(403, "Request not allowed from here")
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 65536:
            self._send(413, "Bad length")
            return
        raw = self.rfile.read(length).decode("utf-8", "replace")
        form = urllib.parse.parse_qs(raw, keep_blank_values=True)
        token = (form.get("token") or [""])[0]
        if not secrets.compare_digest(token, self.app.token) or \
                not secrets.compare_digest(self._cookie_token(), self.app.token):
            self._send(403, "Session token missing or wrong. Reload the page and try again.")
            return
        path = urllib.parse.urlsplit(self.path).path.rstrip("/") or "/"

        if path == "/operator":
            name = (form.get("operator") or [""])[0].strip()[:80]
            cookie = f"coontie_operator={urllib.parse.quote(name)}; HttpOnly; SameSite=Strict; Path=/"
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if path == "/say":
            sentence = (form.get("sentence") or [""])[0][:2000]
            self._with_ws(lambda ws: self.app.render_say(ws, self._operator(), sentence))
            return

        self._send(404, "Not found")

    # -- pages that exist only as placeholders in this build ------------------

    def _render_pending(self, path: str, ws: Workspace, operator: str) -> str:
        label = dict((p, l) for p, l, _k in RAIL).get(path, path)
        body = [f"<h1>{esc(label)}</h1>",
                "<div class='note'>This screen is specified in <code>docs/flows/gui.md</code> and "
                "arrives in a later build step. Until then the command line is the path.</div>"]
        return page(title=label, body="\n".join(body), here=path, operator=operator,
                    facility=(ws.facility().name if ws.facility() else ""), token=self.app.token)

    def _render_audit(self, ws: Workspace, operator: str) -> str:
        now = datetime.now(timezone.utc)
        findings = inspect(ws, now=now)
        body = ["<h1>Audit</h1>",
                "<p class='lede'>What the department would find if it walked in now.</p>",
                f"<p>{prose(brief(ws, now=now, days=7))}</p>"]
        if findings:
            body.append("<h2>Findings</h2><ul class='findings'>")
            for f in findings:
                cite = f'<span class="cite">({esc(f.citation)})</span> ' if f.citation else ""
                body.append(
                    f'<li class="row {esc(f.severity)}">'
                    f'<div class="headline"><span class="sev {esc(f.severity)}">{esc(f.severity)}</span>'
                    f"<span>{esc(f.summary)}</span></div>"
                    f'<div class="meta">{cite}</div></li>'
                )
            body.append("</ul>")
        else:
            body.append("<div class='note'>No findings.</div>")
        body.append("<h2>What this cannot check</h2><ul>")
        from .inspect import CANNOT_CHECK

        for item in CANNOT_CHECK:
            body.append(f"<li><strong>{esc(item.area)}</strong> — {esc(item.why)}</li>")
        body.append("</ul>")
        body.append("<footer>coontie audit</footer>")
        return page(title="Audit", body="\n".join(body), here="/audit", operator=operator,
                    facility=(ws.facility().name if ws.facility() else ""), token=self.app.token,
                    badge=(summarize(findings)[BREACH] + summarize(findings)[EXPOSURE], "/audit"))


def serve(db_path: str | Path, *, port: int = 8080, host: str = "127.0.0.1",
          verbose: bool = False) -> ThreadingHTTPServer:
    """Build the server. Only loopback is allowed; --lan is a separate increment."""
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("the appliance serves loopback only; a LAN build is a separate increment")
    app = App(db_path)
    handler = type("BoundHandler", (Handler,), {"app": app})
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.verbose = verbose
    httpd.daemon_threads = True
    return httpd


def announce(httpd: ThreadingHTTPServer) -> str:
    host, port = httpd.server_address[0], httpd.server_address[1]
    url = f"http://{host}:{port}/"
    print(f"coontie serve on {url}  (ctrl-c to stop)", flush=True)
    return url
