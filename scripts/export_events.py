#!/usr/bin/env python3
"""Render the DH5059 event catalog to markdown.

Generated artifact: tests/test_docs.py fails if the committed file drifts from
the catalog, so run this after any change to events.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from coontie.events import EVENTS, Stage  # noqa: E402

HEADER = """# DH5059 event catalog

Generated from `src/coontie/events.py`. Do not edit by hand.

Source: Form DH5059-OMMU-05/2026, "MMTC Seed-to-Sale Required Data Collection
Document" (Eff. 05/26), incorporated by reference in Rule 64-4.222(3), F.A.C.

Timing: 12 hours by default; **real time** for dispensation, refund, void and
both sides of a transfer. A `*` marks an optional field.
"""

STAGE_TITLES = {
    Stage.CULTIVATION: "Cultivation tracking",
    Stage.PROCESSING: "Processing tracking",
    Stage.DISPENSING: "Dispensing tracking (real time)",
    Stage.LOCATION: "Storage location",
    Stage.WASTE: "Waste destruction",
    Stage.TRANSFER: "Plant and inventory transfer (real time)",
    Stage.TRANSPORT: "Transport",
    Stage.ADMIN: "Employees and API users",
}


def render() -> str:
    out = [HEADER]
    for stage in Stage:
        events = [e for e in EVENTS if e.stage is stage]
        if not events:
            continue
        out.append(f"\n## {STAGE_TITLES[stage]}\n")
        for e in events:
            timing = "real time" if e.timing.value == "realtime" else "12 h"
            out.append(f"### `{e.key}` - {e.title}\n")
            line = f"Timing: {timing}. Fields: {len(e.fields)}."
            if e.wait_hours_before_next:
                line += f" Wait {e.wait_hours_before_next} h before the next step."
            out.append(line + "\n")
            out.append("| Field | Required | Note |")
            out.append("|---|---|---|")
            for f in e.fields:
                req = "yes" if f.required else "no `*`"
                note = f.note.replace("|", "/")
                out.append(f"| `{f.name}` | {req} | {note} |")
            if e.notes:
                out.append(f"\nNote: {e.notes}")
            out.append("")
    return "\n".join(out).rstrip() + "\n"


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "docs" / "requirements" / "dh5059-events.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(), encoding="utf-8")
    print(f"wrote {target} ({len(EVENTS)} events)")
