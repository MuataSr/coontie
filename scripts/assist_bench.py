#!/usr/bin/env python3
"""Track B measurement: can a sub-1B model beat the deterministic baseline on our own tasks?

Runs the 20 cases in ``scripts/bench_cases.json`` against (a) the deterministic reader and
grammar in ``coontie.assist`` and (b) any GGUF models given on the command line, through
``llama-server``. Appends every result to a JSONL as it goes so a crash keeps its progress,
then writes a markdown report.

    python3 scripts/assist_bench.py --out docs/research/ASSIST-BENCH-2026-10-21.md \
        qwen3-0.6b=~/models/bench/qwen3-0.6b/Qwen3-0.6B-Q4_0.gguf ...

Nothing here is a dependency of the package: it is a measurement, not a feature.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from coontie.assist import KNOWN_LABS, parse_command, read_document  # noqa: E402

CASES = json.loads((ROOT / "scripts" / "bench_cases.json").read_text())
PORT = 8123
ORIGIN = f"http://127.0.0.1:{PORT}"
DOC_KEYS = {
    "coa": ["product_name", "thc_percent", "cbd_percent", "lab", "tested_on", "sample_id"],
    "invoice": ["buyer", "seller", "quantity", "unit_price", "invoice_date"],
}
INTENTS = "manifest, dispatch, receive, split, adjust, sample, cure, final, audit, stock, brief, verify, unknown"


# -- scoring -----------------------------------------------------------------

def norm(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "null", "none", "n/a", "na", "not stated", "unknown", "not specified", "-"}:
        return ""
    text = text.replace("$", "").replace("%", "").replace(",", "").strip()
    text = re.sub(r"\s+", " ", text).lower()
    try:
        return str(Decimal(text).quantize(Decimal("0.01")).normalize())
    except (InvalidOperation, ValueError):
        return text


def norm_date(value) -> str:
    text = norm(value)
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if m:
        return f"{int(m.group(3)):04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return text


def compare(field: str, expected, got) -> str:
    """correct | wrong | blank. A blank where the document says nothing is correct."""
    e = norm_date(expected) if field in ("tested_on", "invoice_date") else norm(expected)
    g = norm_date(got) if field in ("tested_on", "invoice_date") else norm(got)
    if not e and not g:
        return "correct"
    if not e and g:
        return "wrong"          # invented a value the document did not state
    if e and not g:
        return "blank"          # refused to answer a value that was there
    if field == "lab":
        # a lab we do not recognise counts as no answer, which is what the app would do
        return "correct" if (e in g or g in e) else "wrong"
    return "correct" if e == g else "wrong"


# -- transports --------------------------------------------------------------

def post_json(path: str, payload: dict, timeout: float = 240.0) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{ORIGIN}{path}", data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def wait_ready(deadline: float) -> bool:
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{ORIGIN}/health", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.4)
    return False


def rss_mb(pid: int) -> float:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    return 0.0


def ask(prompt: str, system: str) -> tuple[str, float, int]:
    started = time.time()
    body = {
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 220,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    data = post_json("/v1/chat/completions", body)
    elapsed = time.time() - started
    text = data["choices"][0]["message"]["content"]
    used = int(data.get("usage", {}).get("completion_tokens", 0))
    return text, elapsed, used


def first_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        try:
            return json.loads(m.group(0).replace("'", '"'))
        except json.JSONDecodeError:
            return {}


# -- prompts -----------------------------------------------------------------

DOC_SYSTEM = (
    "You extract fields from a licensed cannabis document into JSON. Reply with ONLY a JSON "
    "object and nothing else. Use null for any value the document does not state. Never guess."
)

CMD_SYSTEM = (
    "You map one operator instruction from a cannabis compliance system to a JSON object. "
    f'Reply with ONLY this JSON shape: {{"intent": "<one of: {INTENTS}>", "quantity": <number or null>, '
    '"cultivar": "<cultivar name or null>"}. Never invent a quantity or a name.'
)


def doc_prompt(case: dict) -> str:
    keys = DOC_KEYS[case["kind"]]
    return (
        f"Keys: {', '.join(keys)}. Dates as YYYY-MM-DD. Percentages as numbers without the % sign.\n"
        f"Document:\n{case['text']}"
    )


def cmd_prompt(case: dict) -> str:
    return f"Instruction: {case['text']}"


# -- baselines ---------------------------------------------------------------

def run_baseline() -> dict:
    doc_rows, cmd_rows, latency = [], [], []
    for case in CASES["documents"]:
        started = time.time()
        got = read_document(case["text"])
        latency.append(time.time() - started)
        for field in DOC_KEYS[case["kind"]]:
            doc_rows.append({"case": case["id"], "field": field,
                             "verdict": compare(field, case["truth"][field], got.fields.get(field))})
    vocab = CASES["vocabulary"]
    for case in CASES["commands"]:
        started = time.time()
        parsed = parse_command(
            case["text"], cultivars=tuple(vocab["cultivars"]), rooms=tuple(vocab["rooms"]),
            labs=tuple(vocab["labs"]), people=tuple(vocab["people"]),
            manifests=tuple(vocab["manifests"]), lots=tuple(tuple(x) for x in vocab["lots"]),
        )
        latency.append(time.time() - started)
        qty = parsed.args.get("quantity") or parsed.args.get("post") or parsed.args.get("units") or ""
        if not qty and parsed.args.get("items"):
            qty = parsed.args["items"][0][1]
        crew = len(parsed.args.get("crew", []) or [])
        cmd_rows.append({
            "case": case["id"],
            "intent": parsed.intent == case["intent"],
            "quantity": norm(qty) == norm(case["quantity"]),
            "crew": crew >= case.get("crew_min", 0),
        })
    return {"name": "deterministic baseline", "docs": doc_rows, "cmds": cmd_rows,
            "latency_ms": round(statistics.median(latency) * 1000, 2)}


# -- model run ---------------------------------------------------------------

def run_model(name: str, gguf: Path, jsonl: Path) -> dict:
    cmd = [
        str(Path.home() / "llama.cpp/build/bin/llama-server"), "-m", str(gguf),
        "--port", str(PORT), "-c", "1024", "-t", "2", "--no-webui", "--no-warmup",
        "-np", "1", "--log-disable",
    ]
    started = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not wait_ready(time.time() + 180):
            raise RuntimeError("server did not become ready")
        load_s = round(time.time() - started, 1)
        rss = rss_mb(proc.pid)
        ask("Reply with the single word: ready", "You are a test harness.")
        warm_ms = None

        doc_rows, cmd_rows, latencies, tokens = [], [], [], []
        for case in CASES["documents"]:
            text, elapsed, used = ask(doc_prompt(case), DOC_SYSTEM)
            got = first_json(text)
            latencies.append(elapsed)
            tokens.append(used)
            for field in DOC_KEYS[case["kind"]]:
                doc_rows.append({"case": case["id"], "field": field,
                                 "verdict": compare(field, case["truth"][field], got.get(field)),
                                 "raw": text[:400]})
            _append(jsonl, {"model": name, "case": case["id"], "kind": "doc", "raw": text,
                            "parsed": got, "ms": round(elapsed * 1000)})

        for case in CASES["commands"]:
            text, elapsed, used = ask(cmd_prompt(case), CMD_SYSTEM)
            got = first_json(text)
            latencies.append(elapsed)
            tokens.append(used)
            cmd_rows.append({
                "case": case["id"],
                "intent": norm(got.get("intent")) == norm(case["intent"]),
                "quantity": norm(got.get("quantity")) == norm(case["quantity"]),
                "crew": case.get("crew_min", 0) <= 2,   # the model is not asked for crew
                "raw": text[:300],
            })
            _append(jsonl, {"model": name, "case": case["id"], "kind": "cmd", "raw": text,
                            "parsed": got, "ms": round(elapsed * 1000)})

        # determinism: the same six cases again, temperature 0
        flips = []
        for case in CASES["documents"][:3] + CASES["commands"][:3]:
            prompt, system = (doc_prompt(case), DOC_SYSTEM) if "text" in case and "truth" in case \
                else (cmd_prompt(case), CMD_SYSTEM)
            again, _e, _u = ask(prompt, system)
            key = "truth" if "truth" in case else "intent"
            before = first_json(again)
            _append(jsonl, {"model": name, "case": case["id"], "kind": "rerun", "raw": again,
                            "parsed": before})
            first = [r for r in doc_rows + cmd_rows if r["case"] == case["id"]]
            if not first:
                continue
            if key == "truth":
                for field in DOC_KEYS[case["kind"]]:
                    a = compare(field, case["truth"][field], before.get(field))
                    if a != next((r["verdict"] for r in first if r.get("field") == field), a):
                        flips.append(f"{case['id']}.{field}")
            else:
                if norm(before.get("intent")) != norm(case["intent"]):
                    flips.append(f"{case['id']}.intent")

        total_tokens = sum(tokens) or 1
        total_s = sum(latencies) or 1
        return {
            "name": name, "docs": doc_rows, "cmds": cmd_rows,
            "load_s": load_s, "rss_mb": rss, "size_mb": round(gguf.stat().st_size / 1048576, 1),
            "latency_ms": round(statistics.median(latencies) * 1000, 1),
            "p90_ms": round(sorted(latencies)[int(len(latencies) * 0.9) - 1] * 1000, 1),
            "tok_s": round(total_tokens / total_s, 2),
            "flips": flips,
        }
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
        time.sleep(1.0)


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


# -- report ------------------------------------------------------------------

def tally(rows: list[dict]) -> dict:
    counts = {"correct": 0, "wrong": 0, "blank": 0}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    total = sum(counts.values()) or 1
    return {**counts, "total": total, "accuracy": round(counts["correct"] / total, 3)}


def report(results: list[dict], out: Path, host: str) -> None:
    lines = [
        "# Track B measurement: sub-1B models against the deterministic baseline",
        "",
        f"Run {time.strftime('%Y-%m-%d %H:%M')} on {host}. "
        "Cases: `scripts/bench_cases.json` (12 documents, 8 commands). Protocol: "
        "`docs/ASSIST-PLAN.md`.",
        "",
        "Scoring: a field the document does not state must come back empty. **wrong** means the "
        "model invented a value; **blank** means it refused one that was there. An invented "
        "value is the failure that matters in a compliance record.",
        "",
        "| Run | Size | Load | RSS | Median latency | p90 | tok/s | Doc accuracy | wrong | blank | Intent | Quantity | Determinism |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for res in results:
        d = tally(res["docs"])
        intents = sum(1 for c in res["cmds"] if c["intent"])
        qtys = sum(1 for c in res["cmds"] if c["quantity"])
        det = "n/a" if not res.get("flips") else f"{len(res['flips'])} flipped"
        lines.append(
            f"| {res['name']} | {res.get('size_mb', '-')} MB | {res.get('load_s', '-')} s | "
            f"{res.get('rss_mb', '-')} MB | {res.get('latency_ms', '-')} ms | {res.get('p90_ms', '-')} ms | "
            f"{res.get('tok_s', '-')} | {d['accuracy'] * 100:.0f}% | {d['wrong']} | {d['blank']} | "
            f"{intents}/{len(res['cmds'])} | {qtys}/{len(res['cmds'])} | {det} |"
        )
    lines += ["", "## Per-field detail", ""]
    for res in results:
        lines.append(f"### {res['name']}")
        lines.append("")
        lines.append("| Case | Field | Verdict |")
        lines.append("|---|---|---|")
        for r in res["docs"]:
            lines.append(f"| {r['case']} | {r['field']} | {r['verdict']} |")
        lines.append("")
        lines.append("| Command | Intent | Quantity |")
        lines.append("|---|---|---|")
        for c in res["cmds"]:
            lines.append(f"| {c['case']} | {'yes' if c['intent'] else 'no'} | "
                         f"{'yes' if c['quantity'] else 'no'} |")
        if res.get("flips"):
            lines += ["", f"Answers that changed between identical runs: {', '.join(res['flips'])}"]
        lines.append("")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/research/ASSIST-BENCH-2026-10-21.md")
    ap.add_argument("--jsonl", default="docs/research/assist-bench-2026-10-21.jsonl")
    ap.add_argument("--baseline-only", action="store_true")
    ap.add_argument("models", nargs="*", help="name=/path/to/model.gguf")
    args = ap.parse_args()

    jsonl = ROOT / args.jsonl
    results = [run_baseline()]
    for spec in args.models:
        name, _, path = spec.partition("=")
        gguf = Path(os.path.expanduser(path))
        print(f"running {name} ({gguf.stat().st_size / 1048576:.0f} MB)", flush=True)
        try:
            results.append(run_model(name, gguf, jsonl))
        except Exception as exc:  # a dead server must not lose the other results
            print(f"  {name} failed: {exc}", flush=True)
            results.append({"name": f"{name} (failed: {exc})", "docs": [], "cmds": []})
    report(results, ROOT / args.out, f"{os.uname().nodename}, {os.cpu_count()} threads")
    for res in results:
        d = tally(res["docs"])
        print(f"{res['name']}: docs {d['accuracy'] * 100:.0f}% correct, {d['wrong']} wrong, "
              f"{d['blank']} blank; latency {res.get('latency_ms', '-')} ms", flush=True)
    print(f"report: {ROOT / args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
