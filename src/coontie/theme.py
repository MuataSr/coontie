"""Look and voice: two layers of variety that cannot break the record.

The record is one program. What an operator sees is two thin layers over it:

* **skin** (look) is CSS custom properties, nothing else. The markup is identical under every skin,
  so the tests that prove the interface behave also prove every skin.
* **voice** (words) is a dictionary. It renames things for the person at the glass and never touches
  a payload, an export, a manifest or a printed audit.

Evidence is never themed. `EVIDENCE_CSS` is pinned: the manifest, the printed audit and every export
keep the department's words and one official layout whichever skin is installed.

A third party may ship a skin. `check_skin` and `check_voice` are what make that safe: they refuse a
skin that adds a script, fetches anything over the network, drops a required token or hardcodes a
colour outside the token block, and a voice that names a label the program does not have.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# The record keeps UTC; the operator reads their own wall clock. One zone name, one place.
OPERATOR_ZONE = "America/New_York"

# -- tokens ---------------------------------------------------------------------------------------
# Every name a skin must define. A skin that omits one is refused rather than rendered half styled.
REQUIRED_TOKENS = (
    "--ink", "--muted", "--line", "--bg", "--card", "--accent", "--accent-ink",
    "--breach", "--exposure", "--note",
    "--hover", "--here", "--here-ink", "--picked", "--held", "--code-bg", "--code-ink",
    "--refusal-bg", "--note-bg", "--quiet-bg", "--quiet-line",
    "--font", "--font-mono", "--size", "--meta-size", "--leading", "--row-pad", "--radius",
    "--gap",
    "--target", "--nav-width", "--measure",
)

SKINS: dict[str, dict[str, str]] = {
    "calm": {
        "--ink": "#1d232a", "--muted": "#5d6b7a", "--line": "#d8dee6", "--bg": "#fbfcfd",
        "--card": "#ffffff", "--accent": "#14532d", "--accent-ink": "#ffffff",
        "--breach": "#a4262c", "--exposure": "#8a5a00", "--note": "#3b6ea5",
        "--hover": "#eef2f6", "--here": "#e6efe9", "--here-ink": "#14532d",
        "--picked": "#e6efe9", "--held": "#fdf6ec", "--code-bg": "#f6f8fa", "--code-ink": "#1d232a",
        "--refusal-bg": "#fdf3f3", "--note-bg": "#f1f7f3", "--quiet-bg": "#dbe9df",
        "--quiet-line": "#b9cfc1",
        "--font": '-apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
        "--font-mono": "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
        "--size": "15px", "--meta-size": "13px", "--leading": "1.5", "--row-pad": "11px", "--radius": "6px",
        "--gap": "18px", "--target": "34px", "--nav-width": "190px", "--measure": "70ch",
    },
    "contrast": {
        "--ink": "#000000", "--muted": "#242424", "--line": "#000000", "--bg": "#ffffff",
        "--card": "#ffffff", "--accent": "#00308f", "--accent-ink": "#ffffff",
        "--breach": "#8b0000", "--exposure": "#5a3a00", "--note": "#00308f",
        "--hover": "#e8e8e8", "--here": "#d9e4ff", "--here-ink": "#001a4d",
        "--picked": "#d9e4ff", "--held": "#fff2cc", "--code-bg": "#ffffff", "--code-ink": "#000000",
        "--refusal-bg": "#ffe8e8", "--note-bg": "#e8f0ff", "--quiet-bg": "#e8e8e8",
        "--quiet-line": "#000000",
        "--font": '-apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
        "--font-mono": "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
        "--size": "17px", "--meta-size": "15px", "--leading": "1.6", "--row-pad": "14px", "--radius": "3px",
        "--gap": "20px", "--target": "40px", "--nav-width": "200px", "--measure": "62ch",
    },
    "touch": {
        "--ink": "#1d232a", "--muted": "#48535f", "--line": "#c3ccd6", "--bg": "#fbfcfd",
        "--card": "#ffffff", "--accent": "#0f4a28", "--accent-ink": "#ffffff",
        "--breach": "#8d1f24", "--exposure": "#7a4f00", "--note": "#2f5d8a",
        "--hover": "#eef2f6", "--here": "#dfece4", "--here-ink": "#0f4a28",
        "--picked": "#dfece4", "--held": "#fdf3e2", "--code-bg": "#f6f8fa", "--code-ink": "#1d232a",
        "--refusal-bg": "#fdf0f0", "--note-bg": "#eef6f1", "--quiet-bg": "#d7e7de",
        "--quiet-line": "#a9c6b6",
        "--font": '-apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
        "--font-mono": "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
        "--size": "19px", "--meta-size": "17px", "--leading": "1.6", "--row-pad": "18px", "--radius": "10px",
        "--gap": "24px", "--target": "56px", "--nav-width": "220px", "--measure": "56ch",
    },
}
DEFAULT_SKIN = "calm"

SKIN_TITLES = {
    "calm": "Calm: the default. Green, quiet, made for a desk.",
    "contrast": "High contrast: sunlight, older eyes, a monitor that is going.",
    "touch": "Big touch: gloves, a tablet in a cure room, a thumb instead of a mouse.",
}

# -- the stylesheet, in tokens only ---------------------------------------------------------------
SHELL_CSS = """
* { box-sizing:border-box; }
body { margin:0; font:var(--size)/var(--leading) var(--font);
       color:var(--ink); background:var(--bg); }
a { color:var(--accent); }
header { display:flex; align-items:center; gap:var(--gap); padding:10px 18px; background:var(--card);
         border-bottom:1px solid var(--line); position:sticky; top:0; }
header .name { font-weight:600; }
header .spacer { flex:1; }
header .badge { text-decoration:none; border:1px solid var(--line); border-radius:999px;
                padding:2px 10px; font-size:calc(var(--size) - 2px); min-height:var(--target);
                display:inline-flex; align-items:center; }
header .badge.hot { border-color:var(--breach); color:var(--breach); }
.layout { display:flex; min-height:calc(100vh - 52px); }
nav { width:var(--nav-width); padding:14px 10px; border-right:1px solid var(--line);
      background:var(--card); }
nav a { display:block; padding:7px 10px; border-radius:var(--radius); text-decoration:none;
        color:var(--ink); min-height:var(--target); display:flex; align-items:center; }
nav a:hover { background:var(--hover); }
nav a.here { background:var(--here); color:var(--here-ink); font-weight:600; }
main { flex:1; padding:22px 26px 60px; max-width:960px; }
h1 { font-size:calc(var(--size) + 6px); margin:0 0 4px; }
h2 { font-size:calc(var(--size) + 1px); margin:26px 0 8px; padding-bottom:4px;
     border-bottom:1px solid var(--line); }
p.lede { color:var(--muted); margin:0 0 18px; }
p.context { color:var(--muted); font-size:calc(var(--size) - 1px); margin:0; max-width:var(--measure); }
.sentence { background:var(--card); border:1px solid var(--line); border-radius:calc(var(--radius) + 2px);
            padding:14px 16px; }
ul.findings { list-style:none; padding:0; margin:0; }
ul.findings li.row { padding:var(--row-pad) 0 var(--row-pad) 12px; border-bottom:1px solid var(--line);
                     border-left:3px solid var(--line);
                     display:grid; grid-template-columns:auto 1fr; column-gap:10px; row-gap:4px; }
ul.findings li.row.breach { border-left-color:var(--breach); }
ul.findings li.row.exposure { border-left-color:var(--exposure); }
ul.findings li.row.note { border-left-color:var(--note); }
.headline { display:contents; }
.headline > span:not(.sev) { font-size:var(--size); line-height:var(--leading); align-self:baseline; }
.meta { grid-column:2; font-size:var(--meta-size); color:var(--muted); display:flex;
        gap:10px; flex-wrap:wrap; align-items:center; }
.meta a { display:inline-flex; align-items:center; min-height:var(--target); padding:0 10px;
          border:1px solid var(--line); border-radius:var(--radius); background:var(--card);
          text-decoration:none; font-weight:600; }
.meta code { color:var(--accent); }
.sev { font-size:12px; letter-spacing:.05em; text-transform:uppercase; font-weight:700;
       padding:2px 7px; border-radius:calc(var(--radius) - 2px); flex:none; align-self:start; }
.sev.breach { color:var(--accent-ink); background:var(--breach); }
.sev.exposure { color:var(--accent-ink); background:var(--exposure); }
.sev.note { color:var(--accent-ink); background:var(--note); }
.cite { color:var(--muted); font-size:var(--meta-size); }
code, pre { font-family:var(--font-mono); font-size:calc(var(--size) - 2px); }
pre { background:var(--code-bg); color:var(--code-ink); padding:12px 14px;
      border-radius:var(--radius); overflow-x:auto; }
label { display:block; font-weight:600; margin:12px 0 4px; }
input[type=text], input[type=password], textarea { width:100%; padding:9px 10px;
       border:1px solid var(--line); border-radius:var(--radius); font:inherit;
       background:var(--card); color:var(--ink); min-height:var(--target); }
textarea { min-height:90px; }
button { margin-top:14px; padding:9px 16px; border:0; border-radius:var(--radius);
         background:var(--accent); color:var(--accent-ink); font:inherit; font-weight:600;
         cursor:pointer; min-height:var(--target); }
button.quiet { background:var(--quiet-bg); color:var(--accent); border:1px solid var(--quiet-line); }
.refusal { border-left:4px solid var(--breach); background:var(--refusal-bg); padding:10px 14px;
           border-radius:4px; margin:14px 0; }
.note { border-left:4px solid var(--accent); background:var(--note-bg); padding:10px 14px;
        border-radius:4px; margin:14px 0; }
footer { color:var(--muted); font-size:var(--meta-size); margin-top:34px;
         border-top:1px solid var(--line); padding-top:10px; }
table { border-collapse:collapse; width:100%; }
th.num, td.num { text-align:right; font-variant-numeric:tabular-nums; }
td.ident { font-family:var(--font-mono); font-size:calc(var(--size) - 2px); }
tr.picked td { background:var(--picked); }
tr.picked td:first-child { box-shadow:inset 3px 0 0 var(--accent); font-weight:600; }
tr.held td { background:var(--held); }
pre.lineage { background:var(--code-bg); color:var(--code-ink); border:1px solid var(--line);
              white-space:pre; line-height:1.5; }
p.chips { display:flex; flex-wrap:wrap; gap:6px; margin:0 0 10px; }
p.chips a { font-size:calc(var(--size) - 2px); text-decoration:none; border:1px solid var(--line);
            border-radius:999px; padding:3px 10px; background:var(--card); }
p.chips a:hover { background:var(--hover); }
form.inline { display:flex; gap:6px; align-items:center; flex-wrap:wrap; margin:0; }
form.inline button { margin:0; padding:5px 10px; font-size:calc(var(--size) - 2px); }
form.inline input[type=text], form.inline input[type=number] { width:auto; }
form.job-open { background:var(--card); border:1px solid var(--line);
                border-radius:calc(var(--radius) + 2px); padding:14px 16px; max-width:660px; }
form.filters { margin:0 0 6px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
details.job { background:var(--card); border:1px solid var(--line);
              border-radius:calc(var(--radius) + 2px); margin:10px 0; max-width:660px; }
details.job > summary { cursor:pointer; padding:11px 16px; font-weight:600; font-size:var(--size);
                        list-style:none; display:flex; justify-content:space-between;
                        min-height:var(--target); align-items:center; }
details.job > summary::-webkit-details-marker { display:none; }
details.job > summary::after { content:"\\25B8"; color:var(--muted); font-weight:400;
                               font-size:calc(var(--size) - 2px); }
details.job[open] > summary::after { content:"\\25BE"; }
details.job[open] > summary { border-bottom:1px solid var(--line); }
details.job form { padding:4px 16px 16px; }
details.job p.why { margin:8px 0 6px; color:var(--muted); font-size:calc(var(--size) - 2px); }
details.job label { display:block; margin:9px 0 3px; font-size:calc(var(--size) - 2px);
                    font-weight:600; }
details.job input[type=text], details.job select { width:100%; padding:9px 10px;
           border:1px solid var(--line); border-radius:var(--radius); font:inherit;
           background:var(--card); color:var(--ink); min-height:var(--target); }
form.filters input[type=text] { width:120px; }
th, td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--line);
         font-size:calc(var(--size) - 1px); }
.muted { color:var(--muted); }
.printonly { display:none; }
"""

# Evidence layout. Not a token, not themeable: black on white, the department's words, the chain head.
EVIDENCE_CSS = """
@media print {
  @page { margin:18mm 16mm; }
  .printonly { display:block !important; }
  .printonly h1 { font-size:19pt; margin:0 0 2mm; }
  .printonly .chain { font-size:9pt; color:#000; }
  .printonly .signoff { margin-top:6mm; font-size:10pt; }
  header, nav, footer, form, button { display:none !important; }
  main { max-width:none; padding:0; }
  body { background:#fff; color:#000; font-size:11pt; }
  h2 { page-break-after:avoid; border-bottom:1px solid #000; }
  .sev { color:#000 !important; background:#fff !important; border:1px solid #000 !important;
         -webkit-print-color-adjust:exact; print-color-adjust:exact; }
  ul.findings li.row { border-left-color:#000 !important; page-break-inside:avoid; }
  .cite, .meta { color:#333; }
  a { color:#000; text-decoration:none; }
  pre, pre.lineage { border:1px solid #000; background:#fff; color:#000; }
}
"""

# -- voices ---------------------------------------------------------------------------------------
# The canonical wording is the control. A voice renames; it never invents a label the program does
# not have, which is what `check_voice` enforces.
CANONICAL: dict[str, str] = {
    "today.heading": "Today",
    "today.lede": "",
    "today.breaches": "Breaches",
    "today.exposures": "Exposures",
    "today.notes": "Notes",
    "today.due": "Due",
    "today.week": "This week",
    "finding.fix": "fix",
    "badge.label": "open",
    "word.justification": "Justification",
    "word.manifest": "Manifest",
    "word.exposures": "exposures",
    "word.exposure": "exposure",
    "sev.breach": "Breach",
    "sev.exposure": "Exposure",
    "sev.note": "Note",
}

# Sentences the screen builds from a finding's facts. `{x}` is filled from Finding.facts; a voice
# that lacks the template falls back to the canonical summary the inspector wrote.
FINDING_TEXT: dict[str, dict[str, str]] = {
    "canonical": {},
    "quiet": {
        "drift.quantity_mismatch": "{record_key}: you hold {ours_qty}, the department holds {theirs_qty}",
        "drift.status_mismatch": "{record_key} is {theirs_status} in the department's copy, "
                                 "{ours_status} here",
        "drift.missing_locally": "The department has {record_key} ({theirs_qty}); this record does not",
        "drift.missing_at_state": "This record holds {record_key} ({ours_qty}); the department's copy does not",
        "manifest.unreceived": "No receipt recorded for the delivery to {recipient} on {departed}",
    },
    "shop": {
        "drift.quantity_mismatch": "{record_key}: you count {ours_qty}, they count {theirs_qty}",
        "drift.status_mismatch": "{record_key} is {theirs_status} on their side",
        "drift.missing_locally": "The state has {record_key} and you do not ({theirs_qty})",
        "drift.missing_at_state": "You have {record_key} and the state does not ({ours_qty})",
        "manifest.unreceived": "Nothing came back from {recipient}",
    },
    "official": {
        "drift.quantity_mismatch": "{record_key}: quantity differs, ours {ours_qty}, theirs {theirs_qty}",
        "drift.status_mismatch": "{record_key}: status differs, ours {ours_status}, theirs {theirs_status}",
        "drift.missing_locally": "{record_key} is in the department's export and not in this record",
        "drift.missing_at_state": "{record_key} is in this record and not in the department's export",
        "manifest.unreceived": "Manifest to {recipient} departed {departed} with no receipt recorded",
    },
}

VOICES: dict[str, dict[str, str]] = {
    "quiet": {
        "today.heading": "Today",
        "today.lede": "What is open, and what is due.",
        "today.breaches": "Breaches",
        "today.exposures": "Open",
        "today.notes": "Notes",
        "today.due": "Due",
        "today.week": "This week",
        "finding.fix": "fix",
        "badge.label": "open",
        "word.justification": "Written explanation",
        "word.manifest": "Delivery",
        "word.exposures": "open items",
        "word.exposure": "open item",
        "sev.breach": "Breach",
        "sev.exposure": "Open",
        "sev.note": "Note",
    },
    "shop": {
        "today.heading": "Good morning",
        "today.lede": "Here is what needs a person. Nothing else.",
        "today.breaches": "Do now",
        "today.exposures": "Open",
        "today.notes": "Worth a look",
        "today.due": "By the clock",
        "today.week": "Last week",
        "finding.fix": "fix it",
        "badge.label": "to sort",
        "word.justification": "written explanation",
        "word.manifest": "delivery",
        "word.exposures": "things open",
        "word.exposure": "open thing",
        "sev.breach": "Now",
        "sev.exposure": "Open",
        "sev.note": "Look",
        # Field labels. Each key names a field the interface really renders, so `theme --check` can
        # refuse a pack that renames something the program does not have.
        "field.plant.batch": "Which batch",
        "field.plant.count": "How many went in",
        "field.batch.count": "How many",
        "field.harvest.plants": "Which plants came down",
        "field.harvest.wet": "Wet weight",
        "field.cure.post": "Weight after cure",
        "field.receive.received": "How many arrived",
        "field.receive.rejected": "How many came back",
        "field.adjust.remove": "Take this much off",
        "field.amend.value": "Corrected number",
        "field.employee.dob": "Date of birth",
        "field.import.csv": "The file",
    },
    "official": {
        "today.heading": "Today",
        "today.lede": "Plain words here. The department's words on anything that leaves this building.",
        "today.breaches": "Breaches",
        "today.exposures": "Open items",
        "today.notes": "Notes",
        "today.due": "Due",
        "today.week": "This week",
        "finding.fix": "fix",
        "badge.label": "open",
        "word.justification": "Written explanation (justification)",
        "word.manifest": "Manifest",
        "word.exposures": "open items",
        "word.exposure": "open item",
        "sev.breach": "Breach",
        "sev.exposure": "Exposure",
        "sev.note": "Note",
        "field.harvest.wet": "Wet weight (weight at harvest)",
        "field.final.expiration": "Expiration date (immutable once recorded)",
        "field.facility.license": "License number",
        "field.employee.dob": "Date of birth (not printed on any report)",
    },
}
DEFAULT_VOICE = "quiet"

# "canonical" is the wording the program ships; it needs no pack because the program already says it.
VALID_VOICES = ("canonical", *sorted(VOICES))

# A greeting is a function of the operator's clock, so it cannot live in a pack as a fixed string.
GREETINGS: dict[str, tuple[str, str, str]] = {
    "shop": ("Good morning", "Good afternoon", "Good evening"),
}

VOICE_TITLES = {
    "canonical": "As built: the wording that shipped.",
    "quiet": "Quiet professional: declarative, no second person.",
    "shop": "Shop floor: verb first, second person, no made-up nouns.",
    "official": "Plain, with the department's word beside it.",
}

# Each label stands for something real in the record. A voice cannot rename a thing that is not there.
TERMS: dict[str, str] = {
    "today.exposures": "64-4.222(3)",
    "word.manifest": "381.986(8)(g)",
    "word.justification": "64-4.222(12)",
    "today.due": "64-4.222",
}

_BAD_IN_CSS = (
    ("<script", "a script tag"),
    ("javascript:", "a javascript: URL"),
    ("http://", "a network fetch"),
    ("https://", "a network fetch"),
    ("@import", "an imported stylesheet"),
)


def css_for(skin: str = DEFAULT_SKIN) -> str:
    tokens = SKINS.get(skin) or SKINS[DEFAULT_SKIN]
    root = ":root { " + " ".join(f"{name}:{value};" for name, value in tokens.items()) + " }\n"
    return root + SHELL_CSS + EVIDENCE_CSS


def _amount(data: dict, side: str) -> str:
    values = data.get(side) or {}
    quantity = values.get("quantity")
    if quantity in (None, ""):
        return "nothing"
    text = str(quantity)
    text = text[:-2] if text.endswith(".0") else text
    unit = values.get("unit") or ""
    return f"{text} {unit}".strip()


def finding_sentence(voice: str, finding) -> str:
    """The screen's sentence for one finding, in the installed voice, or the canonical one."""
    facts = getattr(finding, "facts", None) or {}
    templates = FINDING_TEXT.get(voice) or {}
    if not facts or not templates:
        return finding.summary
    if finding.code == "drift_open":
        template = templates.get(f"drift.{facts.get('kind')}")
    elif finding.code == "manifest_unreceived":
        template = templates.get("manifest.unreceived")
    else:
        template = None
    if not template:
        return finding.summary
    ours, theirs = facts.get("ours") or {}, facts.get("theirs") or {}
    return template.format(
        record_key=facts.get("record_key", ""),
        ours_qty=_amount(facts, "ours"), theirs_qty=_amount(facts, "theirs"),
        ours_status=str(ours.get("status") or "not held").replace("_", " "),
        theirs_status=str(theirs.get("status") or "not in the export").replace("_", " "),
        recipient=facts.get("recipient", "the recipient"),
        departed=str(facts.get("departed") or "")[:10],
        manifest=facts.get("manifest", ""),
    )


def greeting(voice: str, when: datetime) -> str:
    """The pack's greeting for the operator's local hour, or empty when the voice does not greet."""
    words = GREETINGS.get(voice)
    if not words:
        return ""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    local = when.astimezone(ZoneInfo(OPERATOR_ZONE))
    hour = local.hour
    if hour < 12:
        return words[0]
    if hour < 17:
        return words[1]
    return words[2]


FIELD_PREFIX = "field."


def field_key(action: str, name: str) -> str:
    """The label-table key for one form field: an action and a field, no free text."""
    return f"{FIELD_PREFIX}{action}.{name}"


def field_label(voice: str, action: str, name: str, canonical: str) -> str:
    """One field's label in the installed voice, or the wording the form was written with.

    A voice may rename a field; it may not remove one, and it cannot reach a refusal: those come from
    the record's own write path and never pass through here.
    """
    key = field_key(action, name)
    if voice in VOICES and key in VOICES[voice]:
        return VOICES[voice][key]
    return canonical


def say(voice: str, key: str) -> str:
    """One label in the installed voice, falling back to the canonical wording."""
    if voice in VOICES and key in VOICES[voice]:
        return VOICES[voice][key]
    return CANONICAL.get(key, key)


def speak(text: str, voice: str) -> str:
    """Rewrite the record's own words in the installed voice, without touching the record.

    Used for prose the record generates (`Justification jst-... is due`, the week summary), so the
    body copy speaks the same way as the headings. A canonical voice changes nothing.
    """
    if voice not in VOICES:
        return text
    out = text
    for key in ("word.justification", "word.manifest", "word.exposures", "word.exposure"):
        canonical = CANONICAL[key]
        replacement = say(voice, key)
        if replacement == canonical:
            continue
        out = out.replace(canonical, replacement)
        out = out.replace(canonical.lower(), replacement.lower())
    return out


def check_skin(name: str, tokens: dict[str, str], css: str | None = None) -> list[str]:
    problems = []
    for token in REQUIRED_TOKENS:
        if token not in tokens:
            problems.append(f"{name}: missing token {token}")
    for token, value in tokens.items():
        if not token.startswith("--"):
            problems.append(f"{name}: {token!r} is not a custom property")
        if any(ch in value for ch in ("<", ">", "{", "}")):
            problems.append(f"{name}: {token} has markup in its value")
    for needle, what in _BAD_IN_CSS:
        if needle in SHELL_CSS:
            problems.append(f"{name}: the skin layer contains {what}")
        if css and needle in css:
            problems.append(f"{name}: stylesheet contains {what}")
    # a colour outside the token block will not follow a skin, so it is a bug rather than a style.
    # EVIDENCE_CSS is exempt and stays black on white: evidence is not themed.
    stripped = re.sub(r"/\*.*?\*/", "", SHELL_CSS, flags=re.S)
    for match in re.findall(r"#[0-9a-fA-F]{3,8}\b", stripped):
        problems.append(f"{name}: hardcoded colour {match} outside the token block")
    return problems


def check_voice(name: str, labels: dict[str, str], *, fields=()) -> list[str]:
    """Refuse a voice that invents a label or a field, and one that stays silent about a term.

    `fields` is the program's own set of `action.field` pairs, passed in because the form specs live in
    the interface module and this one must not import it.
    """
    problems = []
    known_fields = {field_key(action, name_) for action, name_ in fields}
    for key in labels:
        if key.startswith(FIELD_PREFIX):
            if fields and key not in known_fields:
                problems.append(f"{name}: the program has no field {key[len(FIELD_PREFIX):]!r}")
            continue
        if key not in CANONICAL:
            problems.append(f"{name}: the program has no label {key!r}")
    for key, term in TERMS.items():
        if key not in labels:
            problems.append(f"{name}: no wording for {key!r}, which stands for {term}")
    for key, value in labels.items():
        if not str(value).strip():
            problems.append(f"{name}: {key} is empty")
        if any(ch in str(value) for ch in "<>"):
            problems.append(f"{name}: {key} carries markup; a label is words, not a page")
    return problems


def check_all(*, fields=()) -> list[str]:
    problems = []
    for name, tokens in SKINS.items():
        problems += check_skin(name, tokens)
    for name, labels in VOICES.items():
        problems += check_voice(name, labels, fields=fields)
    return problems


def catalogue_reference(term: str) -> bool:
    """True when the term is a citation this record can actually point at."""
    from .inspect import CITATIONS

    return any(term in citation for citation in CITATIONS.values())


def describe(skin: str | None = None, voice: str | None = None) -> str:
    lines = []
    if skin:
        lines.append(f"look: {skin}. {SKIN_TITLES.get(skin, '')}")
    if voice:
        lines.append(f"voice: {voice}. {VOICE_TITLES.get(voice, '')}")
    return "\n".join(lines)


# -- third-party packs ----------------------------------------------------------------------------
# A stranger may ship a look or a voice. What makes that safe is not trust in the stranger: it is that a
# pack is data, that `check_skin` and `check_voice` refuse it if it smuggles a script, a network fetch, a
# hardcoded colour or a label the program does not have, and that a pack may never take a built-in name.
# The loader reports what it refused and never guesses at a broken file.

BUILTIN_SKINS = frozenset(SKINS)
BUILTIN_VOICES = frozenset(VOICES)
_NAME_OK = re.compile(r"^[a-z][a-z0-9_-]{1,30}$")


def packs_dir() -> Path:
    """Where packs live unless COONTIE_THEMES says otherwise."""
    override = os.environ.get("COONTIE_THEMES")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "coontie" / "themes"


def _pack_problems(entry, name: str, kind: str, fields) -> list[str]:
    if kind == "look":
        problems = check_skin(name, entry.get("tokens") or {})
        if not isinstance(entry.get("tokens"), dict):
            problems.append(f"{name}: a look needs a tokens object")
        return problems
    labels = entry.get("labels")
    if not isinstance(labels, dict):
        return [f"{name}: a voice needs a labels object"]
    return check_voice(name, labels, fields=fields or ())


def load_packs(directory=None, *, fields=None) -> list[str]:
    """Register every valid pack under `directory`. Returns one line per refused file, never raises."""
    directory = Path(directory) if directory is not None else packs_dir()
    problems: list[str] = []
    if not directory.is_dir():
        return problems
    for path in sorted(directory.glob("*.json")):
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{path.name}: not readable JSON ({exc})")
            continue
        if not isinstance(entry, dict):
            problems.append(f"{path.name}: a pack is a JSON object")
            continue
        kind = str(entry.get("kind") or "").strip().lower()
        name = str(entry.get("name") or "").strip().lower()
        if kind not in ("look", "voice"):
            problems.append(f"{path.name}: kind must be 'look' or 'voice', not {kind or 'missing'!r}")
            continue
        if not _NAME_OK.match(name):
            problems.append(f"{path.name}: name {name or 'missing'!r} must be lower case letters, "
                            "digits, hyphen or underscore")
            continue
        if (kind == "look" and name in BUILTIN_SKINS) or (kind == "voice" and name in BUILTIN_VOICES):
            problems.append(f"{path.name}: {name} is built in; a pack cannot replace it")
            continue
        found = _pack_problems(entry, name, kind, fields)
        if found:
            problems.extend(f"{path.name}: {line}" for line in found)
            continue
        if kind == "look":
            SKINS[name] = dict(entry["tokens"])
            SKIN_TITLES[name] = str(entry.get("title") or "Third-party look")
        else:
            VOICES[name] = dict(entry["labels"])
            VOICE_TITLES[name] = str(entry.get("title") or "Third-party voice")
    return problems


def reset_packs() -> None:
    """Forget every loaded pack, leaving the program exactly as it shipped. Used by tests."""
    for name in set(SKINS) - BUILTIN_SKINS:
        SKINS.pop(name, None)
        SKIN_TITLES.pop(name, None)
    for name in set(VOICES) - BUILTIN_VOICES:
        VOICES.pop(name, None)
        VOICE_TITLES.pop(name, None)
