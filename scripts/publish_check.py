#!/usr/bin/env python3
"""The gate a repository has to pass before it goes public.

Every check here has failed at least once in some project: a home directory in a committed path, a
token pasted into a doc, a company name that was supposed to stay out of a neutral-brand project, a
README pointing at a screenshot that was never committed. A publish is not a moment to find out.

    python3 scripts/publish_check.py            # everything, tests included
    python3 scripts/publish_check.py --skip-tests

Exit status 0 means publishable. Anything else means the reason is printed.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SECRET_PATTERNS = [
    (re.compile(r"\bsk-[A-Za-z0-9]{16,}"), "an API key shape"),
    (re.compile(r"\bhf_[A-Za-z0-9]{20,}"), "a HuggingFace token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "an AWS access key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "a private key"),
    (re.compile(r"(?i)\b(api[_-]?key|secret|token)\s*[:=]\s*['\"][A-Za-z0-9/+_-]{24,}['\"]"),
     "a credential assigned to a literal"),
    (re.compile(r"(?i)password\s*=\s*['\"][^'\"]{8,}['\"]"), "a password literal"),
]

# Strings that must not appear in a neutral-brand project. The allowlist names files where the name is
# the subject rather than the brand (nothing today, and adding one is a decision, not a convenience).
BRAND_WORDS = ("Mu2", "TML", "Sabal", "Tupelo Honey")
# This file is the list, not a mention of the names: it has to spell them to refuse them.
BRAND_ALLOWLIST: tuple = ("scripts/publish_check.py",)

SKIP_DIRS = {".git", "__pycache__", ".venv", "build", "dist", ".pytest_cache"}
TEXT_SUFFIXES = {".py", ".md", ".txt", ".toml", ".cfg", ".ini", ".json", ".jsonl", ".csv", ".yaml",
                 ".yml", ".html", ".css", ".sh", ".example"}
BINARY_ALLOW = {"docs/screens"}


def tracked() -> list:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        return []
    return [Path(line) for line in out.stdout.splitlines() if line.strip()]


def text_files() -> list:
    return [path for path in tracked() if path.suffix in TEXT_SUFFIXES]


def check_licence(problems: list) -> None:
    licence = ROOT / "LICENSE"
    if not licence.exists():
        problems.append("LICENSE is missing")
    elif "MIT License" not in licence.read_text()[:200]:
        problems.append("LICENSE does not start as an MIT licence")
    pyproject = (ROOT / "pyproject.toml").read_text()
    if 'license = { text = "MIT" }' not in pyproject:
        problems.append("pyproject.toml does not declare the MIT licence")
    if "MIT" not in (ROOT / "README.md").read_text():
        problems.append("README never states the licence")


def check_secrets(problems: list) -> None:
    for path in text_files():
        try:
            body = (ROOT / path).read_text(errors="ignore")
        except OSError:
            continue
        for pattern, label in SECRET_PATTERNS:
            if not pattern.search(body):
                continue
            # a deliberately fake password in a test is a fixture, not a credential; the record's own
            # test asserts that string never reaches the database bytes
            if label == "a password literal" and str(path).startswith("tests/"):
                continue
            problems.append(f"{path}: looks like {label}")


def check_brand(problems: list) -> None:
    for path in text_files():
        if str(path) in BRAND_ALLOWLIST:
            continue
        body = (ROOT / path).read_text(errors="ignore")
        for word in BRAND_WORDS:
            if re.search(rf"\b{re.escape(word)}\b", body):
                problems.append(f"{path}: mentions {word!r}, which a neutral-brand project cannot carry")


def check_paths(problems: list) -> None:
    for path in text_files():
        body = (ROOT / path).read_text(errors="ignore")
        for match in re.finditer(r"(/home/[a-z0-9_.-]+|/Users/[A-Za-z0-9_.-]+)", body):
            problems.append(f"{path}: an absolute home path ({match.group(0)})")


def check_size(problems: list) -> None:
    for path in tracked():
        full = ROOT / path
        if not full.exists():
            continue
        if any(str(path).startswith(prefix) for prefix in BINARY_ALLOW):
            continue
        if full.stat().st_size > 1_000_000:
            problems.append(f"{path}: {full.stat().st_size // 1024} KB is too large to carry in git")
        if path.suffix in {".pyc", ".sqlite3", ".db", ".soak"}:
            problems.append(f"{path}: a generated file is tracked")


def check_screenshots(problems: list) -> None:
    readme = (ROOT / "README.md").read_text()
    for name in re.findall(r"\((docs/screens/[^)]+)\)", readme):
        if not (ROOT / name).exists():
            problems.append(f"README links {name}, which is not committed")


def check_version(problems: list) -> None:
    pyproject = (ROOT / "pyproject.toml").read_text()
    match = re.search(r'version = "([^"]+)"', pyproject)
    if not match:
        problems.append("pyproject.toml has no version")
    elif match.group(1).startswith("0.0.0"):
        problems.append(f"version {match.group(1)} is a placeholder")


def check_syntax(problems: list) -> None:
    """Compile every module with the interpreter that runs this check, and say which one it was.

    A syntax feature newer than the declared floor is invisible on a new interpreter: PEP 701 nested
    f-strings import cleanly on 3.12+ and are a SyntaxError on 3.11. This check can only speak for the
    interpreter it runs on, so it prints that version and CI carries the matrix that covers the floor.
    """
    compiled = 0
    for path in sorted((ROOT / "src").rglob("*.py")):
        try:
            compile(path.read_text(), str(path), "exec")
            compiled += 1
        except SyntaxError as exc:
            problems.append(f"{path.relative_to(ROOT)}: does not compile on {sys.version.split()[0]}: "
                            f"{exc.msg} (line {exc.lineno})")
    print(f"  compiled {compiled} module(s) with Python {sys.version.split()[0]}")


def check_tests(problems: list) -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    out = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                         cwd=ROOT, capture_output=True, text=True, env=env)
    if out.returncode != 0:
        tail = (out.stderr or out.stdout).strip().splitlines()[-1:] or ["no output"]
        problems.append(f"the test suite is not green: {tail[0]}")
    else:
        ran = re.search(r"Ran (\d+) tests", out.stderr)
        print(f"  suite: {ran.group(1) if ran else '?'} tests passed")


def check_import(problems: list) -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    out = subprocess.run([sys.executable, "-c",
                          "import coontie, coontie.cli, coontie.web, coontie.transmission; "
                          "print('ok')"], cwd=ROOT, capture_output=True, text=True, env=env)
    if out.returncode != 0 or "ok" not in out.stdout:
        problems.append("the package does not import cleanly: " + (out.stderr.strip()[:200]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="is this repository fit to publish?")
    parser.add_argument("--skip-tests", action="store_true", help="skip the suite (fast checks only)")
    args = parser.parse_args(argv)

    problems: list = []
    for name, check in (("licence", check_licence), ("secrets", check_secrets),
                        ("brand", check_brand), ("paths", check_paths), ("size", check_size),
                        ("screenshots", check_screenshots), ("version", check_version),
                        ("syntax", check_syntax), ("import", check_import)):
        before = len(problems)
        check(problems)
        print(f"  {name}: {'ok' if len(problems) == before else 'FAILED'}")
    if not args.skip_tests:
        before = len(problems)
        check_tests(problems)
        print(f"  tests: {'ok' if len(problems) == before else 'FAILED'}")

    if problems:
        print()
        print(f"{len(problems)} thing(s) to fix before this goes public:")
        for line in problems:
            print(f"  - {line}")
        return 1
    print()
    print("publishable. What is left is a decision, not a fix: where it goes and under whose name.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
