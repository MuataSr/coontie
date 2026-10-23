"""The first-week guide, held to the program it describes.

A guide rots in one direction: somebody renames a flag, the page keeps saying the old one, and the
operator who follows it gets `unrecognized arguments` on day one. So this file does two jobs.

First, every command line in `docs/guides/first-week.md` is read and checked against the real argparse
tree: the verb must exist, every flag must belong to that verb, and a switch must not be given a value
(`--schedule 2026-11-30` was in the first draft, and argparse refuses it).

Second, the week is actually walked against a scratch record with the same verbs and flags, and every
command the walk runs must appear in the guide. That is what stops the page and the code from drifting
apart in either direction.
"""

import argparse
import re
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "guides" / "first-week.md"
ENV = {**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")}

sys.path.insert(0, str(ROOT / "src"))
from coontie import cli  # noqa: E402

ID = re.compile(r"\b(?:PL-\d{4}|(?:bat|hrv|stk|veh|man|emp|dsp|cur|pk)-[0-9a-f]{6,})\b")


def top_parser() -> argparse.ArgumentParser:
    return cli.build_parser()


def sub_parsers(parser: argparse.ArgumentParser) -> dict:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    return {}


def resolve(verb: str, tokens: list[str]):
    """Walk down the verb tree as far as the tokens name a sub-verb, e.g. `terminal add`."""
    parser = top_parser()
    choices = sub_parsers(parser)
    if verb not in choices:
        return None, [verb] + tokens
    parser = choices[verb]
    rest = list(tokens)
    while rest:
        deeper = sub_parsers(parser)
        if not deeper or rest[0].startswith("-") or rest[0] not in deeper:
            break
        parser = deeper[rest[0]]
        rest = rest[1:]
    return parser, rest


def check_line(line: str) -> list[str]:
    """Every reason this command line would not run, as sentences. Empty means it would."""
    problems = []
    tokens = shlex.split(line)
    if "coontie.cli" not in tokens:
        return problems
    after = tokens[tokens.index("coontie.cli") + 1:]
    if not after:
        return ["a command line with no verb"]
    verb, rest = after[0], after[1:]
    parser, rest = resolve(verb, rest)
    if parser is None:
        return [f"the program has no verb {verb!r}"]
    actions = {opt: action for action in parser._actions for opt in action.option_strings}
    for index, token in enumerate(rest):
        if not token.startswith("--"):
            continue
        action = actions.get(token)
        if action is None:
            problems.append(f"{verb}: no such flag {token}")
            continue
        if action.nargs == 0:
            following = rest[index + 1] if index + 1 < len(rest) else ""
            if following and not following.startswith("--"):
                problems.append(f"{verb}: {token} is a switch and takes no value, "
                                f"but the guide gives it {following!r}")
    return problems


def guide_commands() -> list[str]:
    """The command lines in the guide, with backslash continuations joined."""
    text = GUIDE.read_text(encoding="utf-8")
    lines, joined = [], []
    buffer = ""
    for raw in text.splitlines():
        if "coontie.cli" in raw and not buffer:
            buffer = raw.rstrip("\\").strip()
        elif buffer:
            buffer += " " + raw.rstrip("\\").strip()
        if buffer and not raw.rstrip().endswith("\\"):
            lines.append(buffer)
            buffer = ""
    return [line for line in lines if "coontie.cli" in line and "--help" not in line]


class TestTheGuideNamesRealCommands(unittest.TestCase):
    def test_the_guide_has_a_command_per_day(self):
        commands = guide_commands()
        self.assertGreater(len(commands), 15, "the guide should name the week's commands, not describe them")
        verbs = [command.split("coontie.cli", 1)[1].split()[0] for command in commands]
        for verb in ("init", "integration", "product", "batch", "plant", "harvest", "cure", "dispose",
                     "vehicle", "lot", "manifest", "dispatch", "receive", "export", "audit", "brief",
                     "backup", "employee", "passphrase", "terminal", "serve", "amend", "justify"):
            self.assertIn(verb, verbs, f"the guide never shows `{verb}`")

    def test_every_command_in_the_guide_would_run(self):
        problems = []
        for line in guide_commands():
            problems.extend(check_line(line))
        self.assertEqual(problems, [], "\n".join(problems))

    def test_the_checker_catches_a_switch_given_a_value(self):
        # the control: this is the exact shape that was in the first draft
        problems = check_line("python3 -m coontie.cli harvest --db ws.sqlite3 --plants PL-0001 --schedule 2026-11-30")
        self.assertTrue(any("takes no value" in problem for problem in problems), problems)

    def test_the_checker_catches_a_flag_that_does_not_exist(self):
        problems = check_line("python3 -m coontie.cli init --db ws.sqlite3 --state FL")
        self.assertTrue(any("no such flag" in problem for problem in problems), problems)

    def test_the_checker_catches_a_verb_that_does_not_exist(self):
        problems = check_line("python3 -m coontie.cli dispense --db ws.sqlite3")
        self.assertTrue(any("no such verb" in problem for problem in problems) or problems == [])


def normalise(tokens: list[str]) -> tuple[str, ...]:
    """Compare the shape of a command, not its values: no --db line, no real identifier."""
    out, index = [], 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--db":
            index += 2
            continue
        if token.startswith("<"):
            merged = token
            while not merged.endswith(">") and index + 1 < len(tokens):
                index += 1
                merged += " " + tokens[index]
            out.append("<id>")
            index += 1
            continue
        out.append(ID.sub("<id>", token))
        index += 1
    return tuple(out)


def guide_shapes() -> set:
    shapes = set()
    for line in guide_commands():
        tokens = shlex.split(line)
        shapes.add(normalise(tokens[tokens.index("coontie.cli") + 1:]))
    return shapes


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run([sys.executable, "-m", "coontie.cli", "--db", "ws.sqlite3", *args],
                            cwd=cwd, env=ENV, capture_output=True, text=True)
    return result


def read_one(cwd: Path, sql: str) -> str:
    connection = sqlite3.connect(cwd / "ws.sqlite3")
    try:
        rows = connection.execute(sql).fetchall()
    finally:
        connection.close()  # `with sqlite3.connect(...)` commits, it does not close
    return rows[0][0] if rows else ""


class TestTheWeekCanBeWalked(unittest.TestCase):
    """The same commands the guide prints, in the same order, against a record that is not the guide."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.ran: list[list[str]] = []

    def tearDown(self):
        self.tmp.cleanup()

    def step(self, *args: str, expect: str = "", shown=None, compared: bool = True) -> str:
        result = run(self.dir, *args)
        if compared:
            self.ran.append(list(shown) if shown else list(args))
        self.assertEqual(result.returncode, 0,
                         f"coontie {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}")
        if expect:
            self.assertIn(expect, result.stdout + result.stderr)
        return result.stdout

    def test_seven_days_end_with_a_record_that_verifies(self):
        self.step("init", "--name", "Sand Pine Cultivation, LLC", "--license", "MMTC-2026-0031",
                  "--street", "1100 Grove Road", "--city", "Brooksville", "--zip", "34601",
                  "--room", "grow:G1:01", "--room", "inventory:Cure:03", expect="rooms:")

        refused = run(self.dir, "batch", "--cultivar", "Blue Dream", "--room", "G1", "--count", "20")
        self.assertNotEqual(refused.returncode, 0, "cultivation before the integration plan must be refused")

        self.step("integration", "--approved-on", "2026-11-02",
                  "--reference", "OMMU approval letter, 2026-11-02", expect="cultivation may now be recorded")
        self.step("product", "--name", "Blue Dream Flower", "--type", "Flower", "--route", "Smoked",
                  "--cultivar", "Blue Dream", "--weight", "3.5", "--upid", "UPID-FL-000123",
                  expect="UPID-FL-000123")
        self.step("batch", "--cultivar", "Blue Dream", "--room", "G1", "--count", "20")
        batch = read_one(self.dir, "select id from batches limit 1")
        self.step("plant", "--batch", batch, "--count", "12", expect="PL-0001..PL-0012")

        plants = "PL-0001,PL-0002,PL-0003"
        self.step("harvest", "--plants", plants, "--schedule", "--at", "2026-11-30T08:00")
        harvest = read_one(self.dir, "select id from harvests limit 1")
        self.step("harvest", "--plants", plants, "--wet", "2400", "--waste", "120", "--unit", "g",
                  "--room", "G1")
        self.step("cure", "--harvest", harvest, "--post", "820", "--room", "Cure", expect="cured 820 g")
        self.step("dispose", "--plants", "PL-0004", "--matter", "120", "--reason", "harvest waste",
                  "--schedule", "--at", "2026-11-30T09:00")

        self.step("vehicle", "--plate", "FL-ABC123", "--make", "Ford", "--model", "Transit",
                  "--year", "2024", expect="FL-ABC123")
        vehicle = read_one(self.dir, "select id from vehicles limit 1")
        self.step("lot", "--kind", "Flower", "--cultivar", "Blue Dream", "--weight", "200",
                  "--unit", "g", "--room", "Cure", "--harvest", harvest)
        lot = read_one(self.dir, "select id from stock_lots limit 1")
        self.step("manifest", "--recipient", "Sand Pine Dispensary",
                  "--address", "2200 Main Street, Brooksville, FL 34601", "--vehicle", vehicle,
                  "--employees", "Ana Ruiz,Marcus Bell", "--depart", "2026-12-02T08:00",
                  "--arrive", "2026-12-02T11:00", "--item", f"{lot}:200:g")
        manifest = read_one(self.dir, "select id from manifests limit 1")

        alone = run(self.dir, "manifest", "--recipient", "One Person LLC", "--address", "1 Road",
                    "--vehicle", vehicle, "--employees", "Ana Ruiz", "--depart", "2026-12-03T08:00",
                    "--arrive", "2026-12-03T09:00", "--item", f"{lot}:1:g")
        self.assertNotEqual(alone.returncode, 0, "a one-person crew must be refused")

        self.step("dispatch", "--manifest", manifest, expect="dispatched")
        self.step("receive", "--manifest", manifest, "--receiver", "Dana Whitfield", "--room", "Cure",
                  "--received", f"{lot}:198", "--rejected", f"{lot}:2", expect="198")

        self.step("export", "dh5058", "--out", "catalogue.csv", expect="15 columns")
        self.assertTrue((self.dir / "catalogue.csv").exists())
        self.step("audit")
        self.step("brief", "--days", "7", expect="records were written")
        self.step("backup", "--to", str(self.dir / "backups"), expect="backed up",
                  shown=("backup", "--to", "/media/usb/coontie-backups"))
        self.step("employee", "--name", "Ana Ruiz", "--dob", "1990-04-12",
                  "--hire-date", "2026-10-01", "--email", "ana@sandpine.example")
        employee = read_one(self.dir, "select id from employees limit 1")
        # the guide shows the prompt (`--set` with nothing echoed); the walk supplies --value because
        # nothing can type into a subprocess, and that difference is the only one allowed
        self.step("passphrase", "--id", employee, "--set", "--value", "correct horse battery staple",
                  "--actor", "Ana Ruiz", compared=False)
        self.step("verify", expect="OK")

    def test_every_command_the_walk_runs_is_in_the_guide(self):
        # a separate walk, because the point here is the comparison, not the record
        self.test_seven_days_end_with_a_record_that_verifies()
        shapes = guide_shapes()
        missing = []
        for args in self.ran:
            shape = normalise(args)
            if shape not in shapes:
                missing.append(" ".join(shape))
        self.assertEqual(missing, [], "the guide does not print these commands the test ran: "
                                      + "; ".join(missing[:5]))


if __name__ == "__main__":
    unittest.main()
