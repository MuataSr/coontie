"""The drift screen: one page, one question, one number.

"Is my record the same as the state's?" The answer is a count, and under it a list where
each difference can be resolved without leaving the page.

KISS constraints this obeys:

* One screen. No navigation, no dashboard, no charts.
* Standard library only. No JavaScript, no CDN, no build step. It works offline.
* Localhost only, one operator at a time. There is no account because there is nobody to
  authenticate to; the file is already the boundary.
* Every button maps to one rule and one resolution, spelled out in the row.

The page is regenerated from the database on every request, so the file on disk is never
the source of truth.
"""

from __future__ import annotations

import html
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from .workspace import Workspace

KIND_LABEL = {
    "quantity_mismatch": "Quantity differs",
    "status_mismatch": "Status differs",
    "missing_at_state": "We hold it, the state does not",
    "missing_locally": "The state holds it, we do not",
}

KIND_HELP = {
    "quantity_mismatch": "One of the two counts is wrong. Accept the state's number, keep yours, or record a recount.",
    "status_mismatch": "Hold or release state does not match. Accept the state's status or keep yours.",
    "missing_at_state": "A record of ours never reached the department. Re-send it or accept the gap.",
    "missing_locally": "The department has inventory we have no lot for. Record it, or accept the gap.",
}

CITATIONS = {
    "quantity_mismatch": "64-4.222(12)",
    "status_mismatch": "64-4.222(11)",
    "missing_at_state": "64-4.221(2)",
    "missing_locally": "64-4.221(2)",
}

CSS = """
:root { --ink:#1d1d1f; --muted:#6b6b70; --line:#e3e3e6; --bg:#fbfbfc; --block:#b3261e; --ok:#1c6b3c; --soft:#f2f2f4; }
* { box-sizing:border-box; }
body { margin:0; padding:2rem 1.25rem 4rem; font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
       color:var(--ink); background:var(--bg); }
main { max-width:1080px; margin:0 auto; }
h1 { font-size:1.35rem; letter-spacing:-0.01em; margin:0 0 .25rem; }
.meta { color:var(--muted); font-size:.85rem; margin-bottom:1.5rem; }
.answer { display:flex; gap:2rem; align-items:baseline; padding:1rem 1.25rem; background:#fff; border:1px solid var(--line);
          border-radius:10px; margin-bottom:1.25rem; }
.answer .n { font-size:2.1rem; font-weight:650; letter-spacing:-0.02em; }
.answer .n.clean { color:var(--ok); }
.answer .n.dirty { color:var(--block); }
.answer .k { color:var(--muted); font-size:.85rem; }
.answer .parts { margin-left:auto; color:var(--muted); font-size:.85rem; text-align:right; }
table { width:100%; border-collapse:collapse; background:#fff; border:1px solid var(--line); border-radius:10px; overflow:hidden; }
th,td { text-align:left; padding:.65rem .7rem; border-bottom:1px solid var(--line); vertical-align:top; font-size:.88rem; }
th { background:var(--soft); font-weight:600; font-size:.78rem; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }
tr:last-child td { border-bottom:0; }
.kind { font-weight:600; }
.help { color:var(--muted); font-size:.8rem; margin-top:.15rem; }
.key { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.82rem; }
.pair { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.82rem; }
.ours { color:var(--ink); }
.theirs { color:var(--block); }
form { display:flex; flex-wrap:wrap; gap:.35rem; align-items:center; }
button { font:inherit; font-size:.8rem; padding:.3rem .55rem; border:1px solid var(--line); background:#fff; border-radius:6px; cursor:pointer; }
button:hover { background:var(--soft); }
button.primary { border-color:#1d1d1f; }
input[type=text], input[type=number] { font:inherit; font-size:.8rem; padding:.3rem .4rem; border:1px solid var(--line);
       border-radius:6px; width:6.5rem; }
.flash { padding:.7rem 1rem; border-radius:8px; margin-bottom:1rem; font-size:.88rem; }
.flash.ok { background:#eaf5ee; color:#144d2b; border:1px solid #cfe6d8; }
.flash.err { background:#fbeceb; color:#7a1c16; border:1px solid #f2cfcc; }
.empty { padding:2rem; text-align:center; color:var(--muted); background:#fff; border:1px solid var(--line); border-radius:10px; }
footer { margin-top:1.5rem; color:var(--muted); font-size:.8rem; }
a { color:inherit; }
"""


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


def _fmt(row: dict) -> str:
    if not row:
        return "-"
    bits = []
    if row.get("quantity") is not None:
        unit = row.get("unit") or ""
        bits.append(f"{row['quantity']} {unit}".strip())
    if row.get("status"):
        bits.append(str(row["status"]))
    if row.get("product"):
        bits.append(str(row["product"]))
    if row.get("room"):
        bits.append(f"in {row['room']}")
    return " / ".join(str(b) for b in bits)


def _buttons(finding: dict) -> str:
    fid = _esc(finding["id"])
    kind = finding["kind"]
    out = [f'<form method="post" action="/resolve">', f'<input type="hidden" name="id" value="{fid}">']
    if kind in ("quantity_mismatch", "status_mismatch"):
        out.append('<button class="primary" name="action" value="accept_state">Accept the state</button>')
    if kind == "quantity_mismatch":
        out.append(
            '<input type="number" step="0.001" name="quantity" placeholder="counted">'
            '<button name="action" value="recount">Recount</button>'
        )
    if kind == "missing_locally":
        out.append('<button class="primary" name="action" value="record_state">Record it here</button>')
    if kind == "missing_at_state":
        out.append('<button class="primary" name="action" value="resend">Re-send it</button>')
    out.append('<button name="action" value="keep_local">Keep ours</button>')
    out.append("</form>")
    return "".join(out)


def render(ws: Workspace, message: str = "", error: str = "") -> str:
    snapshot = ws.latest_snapshot()
    findings = ws.drift_findings(open_only=True) if snapshot else []
    all_findings = ws.drift_findings(open_only=False) if snapshot else []
    resolved = [f for f in all_findings if f["resolution"]]
    unlinked = len(ws.unlinked_lots())

    if snapshot is None:
        body = (
            '<div class="empty"><p>No state snapshot yet.</p>'
            '<p class="key">coontie drift pull --csv &lt;the export from the department&gt;</p></div>'
        )
        count_html = '<div class="n">-</div><div><div>Nothing pulled</div><div class="k">no comparison has been run</div></div>'
    elif not findings:
        body = '<div class="empty"><p>No differences. The two records agree.</p></div>'
        count_html = (
            f'<div class="n clean">0</div><div><div>differences</div>'
            f'<div class="k">{snapshot["rows"]} records compared, {len(resolved)} resolved</div></div>'
        )
    else:
        parts: dict[str, int] = {}
        rows = []
        for i, f in enumerate(findings, start=1):
            parts[f["kind"]] = parts.get(f["kind"], 0) + 1
            rows.append(
                "<tr>"
                f'<td>{i}</td>'
                f'<td><div class="kind">{_esc(KIND_LABEL.get(f["kind"], f["kind"]))}</div>'
                f'<div class="help">{_esc(KIND_HELP.get(f["kind"], ""))}</div></td>'
                f'<td class="key">{_esc(f["record_key"])}</td>'
                f'<td class="pair"><span class="ours">{_esc(_fmt(f["ours"]))}</span></td>'
                f'<td class="pair"><span class="theirs">{_esc(_fmt(f["theirs"]))}</span></td>'
                f'<td class="key">{_esc(CITATIONS.get(f["kind"], ""))}</td>'
                f"<td>{_buttons(f)}</td>"
                "</tr>"
            )
        body = (
            "<table><thead><tr><th>#</th><th>What</th><th>Record</th><th>Yours</th><th>The state's</th>"
            "<th>Rule</th><th>Resolve</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        )
        summary = ", ".join(f"{v} {KIND_LABEL.get(k, k).lower()}" for k, v in sorted(parts.items()))
        count_html = (
            f'<div class="n dirty">{len(findings)}</div><div><div>differences</div>'
            f'<div class="k">of {snapshot["rows"]} records compared</div></div>'
            f'<div class="parts">{_esc(summary)}<br>{len(resolved)} resolved</div>'
        )

    flash = ""
    if message:
        flash = f'<div class="flash ok">{_esc(message)}</div>'
    if error:
        flash = f'<div class="flash err">{_esc(error)}</div>'

    meta = (
        f'Snapshot {_esc(snapshot["id"])} taken {_esc(snapshot["as_of"].strftime("%Y-%m-%d %H:%M UTC"))}'
        f' from {_esc(snapshot["source_file"] or "an unnamed export")}'
        if snapshot
        else "No snapshot"
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Coontie drift</title><style>{CSS}</style></head>
<body><main>
<h1>Your record vs the state's</h1>
<div class="meta">{meta}</div>
{flash}
<div class="answer">{count_html}</div>
{body}
<footer>
{unlinked} lot(s) are not linked to a department inventory id and cannot be compared.
Link them with <span class="key">coontie link --lot &lt;lot&gt; --sts-id &lt;id&gt;</span>.
Every resolution is written to the ledger with its cause and the snapshot it came from.
</footer>
</main></body></html>
"""


class _Handler(BaseHTTPRequestHandler):
    db_path: str = ""
    server_version = "CoontieDrift/1"

    def log_message(self, format, *args):  # quiet: one operator, no access log noise
        return

    def _workspace(self) -> Workspace:
        """A connection per request: a SQLite connection belongs to the thread that opened it."""
        return Workspace(self.db_path)

    def _send(self, code: int, body: str, ctype: str = "text/html; charset=utf-8", extra: dict | None = None):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path not in ("/", "/drift"):
            self._send(404, "not found", "text/plain; charset=utf-8")
            return
        query = parse_qs(parsed.query)
        message = query.get("done", [""])[0]
        error = query.get("error", [""])[0]
        ws = self._workspace()
        try:
            page = render(ws, message=message, error=error)
        finally:
            ws.close()
        self._send(200, page)

    def do_POST(self):
        if self.path != "/resolve":
            self._send(404, "not found", "text/plain; charset=utf-8")
            return
        length = int(self.headers.get("Content-Length") or 0)
        form = parse_qs(self.rfile.read(length).decode("utf-8"))
        fid = (form.get("id") or [""])[0]
        action = (form.get("action") or [""])[0]
        quantity = (form.get("quantity") or [""])[0] or None
        note = (form.get("note") or [""])[0]
        ws = self._workspace()
        try:
            ws.resolve_finding(fid, action, note=note, quantity=quantity, actor="operator")
        except ValueError as exc:
            target = "/?error=" + _q(str(exc))
        else:
            target = "/?done=" + _q(f"{action.replace('_', ' ')} recorded for {fid}")
        finally:
            ws.close()
        self.send_response(303)
        self.send_header("Location", target)
        self.send_header("Content-Length", "0")
        self.end_headers()


def _q(text: str) -> str:
    from urllib.parse import quote

    return quote(text, safe="")


def make_server(target, port: int = 8770) -> HTTPServer:
    """Serve the drift screen for a workspace file. Accepts a Workspace or a path."""
    db_path = str(getattr(target, "path", target))
    handler = type("Handler", (_Handler,), {"db_path": db_path})
    return HTTPServer(("127.0.0.1", port), handler)


def serve(db_path: str, port: int = 8770, ready: list | None = None) -> None:
    server = make_server(db_path, port)
    if ready is not None:
        ready.append(server.server_address[1])
    print(f"drift screen on http://127.0.0.1:{server.server_address[1]}/  (ctrl-c to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    finally:
        server.server_close()
