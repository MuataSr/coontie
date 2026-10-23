"""Third-party packs: a look or a voice from a stranger, refused unless the contract holds.

A pack is data. What makes it safe is that `check_skin` and `check_voice` refuse a script, a network
fetch, a hardcoded colour and a label the program does not have, that a pack may not take a built-in
name, and that a broken file is reported rather than crashing a facility's appliance.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from coontie import theme, web  # noqa: E402

TOKENS = dict(theme.SKINS["calm"])


class base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        theme.reset_packs()

    def tearDown(self):
        theme.reset_packs()
        self.tmp.cleanup()

    def pack(self, filename: str, payload) -> Path:
        path = self.dir / filename
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def look(self, name="grove", **overrides):
        entry = {"kind": "look", "name": name, "title": "Grove", "tokens": dict(TOKENS)}
        entry.update(overrides)
        return entry

    def voice(self, name="grove", labels=None):
        # a pack must speak for every term the program relies on, so the fixture starts from the
        # complete set and changes what it means to
        # canonical has a few deliberately empty entries (`today.lede` means "no lede"); a pack that
        # carries an empty string would be refused, so the fixture carries only the written ones
        base = {key: value for key, value in theme.CANONICAL.items() if str(value).strip()}
        base.update(labels or {"today.heading": "In the room"})
        return {"kind": "voice", "name": name, "title": "Grove", "labels": base}


class TestItLoads(base):
    def test_a_valid_voice_pack_is_registered_and_speaks(self):
        self.pack("grove.json", self.voice())
        problems = theme.load_packs(self.dir, fields=web.form_fields())
        self.assertEqual(problems, [])
        self.assertIn("grove", theme.VOICES)
        self.assertEqual(theme.say("grove", "today.heading"), "In the room")

    def test_a_valid_look_pack_is_registered_and_styles(self):
        self.pack("grove-look.json", self.look())
        self.assertEqual(theme.load_packs(self.dir), [])
        css = theme.css_for("grove")
        self.assertIn(TOKENS["--accent"], css)
        self.assertIn(theme.SHELL_CSS[:40], css, "a pack styles tokens; it does not replace the shell")

    def test_loading_twice_registers_once(self):
        self.pack("grove.json", self.voice())
        theme.load_packs(self.dir)
        theme.load_packs(self.dir)
        self.assertEqual([name for name in theme.VOICES].count("grove"), 1)

    def test_a_pack_may_set_a_field_label_for_a_field_that_exists(self):
        self.pack("grove.json", self.voice(labels={"today.heading": "In the room",
                                                   "field.plant.count": "How many went in"}))
        self.assertEqual(theme.load_packs(self.dir, fields=web.form_fields()), [])
        self.assertEqual(theme.field_label("grove", "plant", "count", "How many"),
                         "How many went in")


class TestItRefuses(base):
    def test_a_hardcoded_colour_outside_the_tokens_is_refused(self):
        entry = self.look()
        entry["tokens"]["--ink"] = "#a4262c; } main { color: #ff0000"
        self.pack("bad-colour.json", entry)
        problems = theme.load_packs(self.dir)
        self.assertTrue(any("markup" in problem or "colour" in problem for problem in problems),
                        problems)
        self.assertNotIn("grove", theme.SKINS)

    def test_a_missing_token_is_refused(self):
        entry = self.look()
        entry["tokens"].pop("--breach")
        self.pack("missing.json", entry)
        problems = theme.load_packs(self.dir)
        self.assertTrue(any("missing token" in problem for problem in problems), problems)
        self.assertNotIn("grove", theme.SKINS)

    def test_a_script_in_a_label_is_refused(self):
        self.pack("script.json", self.voice(labels={"today.heading": "<script>alert(1)</script>"}))
        problems = theme.load_packs(self.dir, fields=web.form_fields())
        self.assertTrue(problems, "a label carrying markup must never reach a page")
        self.assertNotIn("grove", theme.VOICES)

    def test_a_pack_may_not_replace_a_built_in(self):
        self.pack("calm.json", self.voice(name="quiet"))
        problems = theme.load_packs(self.dir)
        self.assertTrue(any("built in" in problem for problem in problems), problems)

    def test_a_voice_naming_a_field_the_program_lacks_is_refused(self):
        self.pack("liar.json", self.voice(labels={"today.heading": "In the room",
                                                  "field.plant.weight": "Weight"}))
        problems = theme.load_packs(self.dir, fields=web.form_fields())
        self.assertTrue(any("no field" in problem for problem in problems), problems)

    def test_broken_json_is_reported_not_raised(self):
        self.pack("broken.json", "{not json")
        problems = theme.load_packs(self.dir)
        self.assertTrue(any("not readable JSON" in problem for problem in problems), problems)

    def test_an_unknown_kind_is_reported(self):
        self.pack("odd.json", {"kind": "layout", "name": "grove"})
        problems = theme.load_packs(self.dir)
        self.assertTrue(any("kind" in problem for problem in problems), problems)

    def test_a_name_that_is_not_a_name_is_reported(self):
        self.pack("odd.json", {"kind": "voice", "name": "Grove Floor!", "labels": {}})
        problems = theme.load_packs(self.dir)
        self.assertTrue(any("lower case" in problem for problem in problems), problems)

    def test_a_missing_directory_is_silence_not_an_error(self):
        self.assertEqual(theme.load_packs(self.dir / "nowhere"), [])


class TestTheCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "themes"
        self.dir.mkdir()
        self.db = Path(self.tmp.name) / "ws.sqlite3"
        from coontie.workspace import Workspace

        Workspace(self.db).close()
        theme.reset_packs()

    def tearDown(self):
        theme.reset_packs()
        self.tmp.cleanup()

    def run_cli(self, *args, packs=None):
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
               "COONTIE_THEMES": str(packs or self.dir)}
        return subprocess.run([sys.executable, "-m", "coontie.cli", "--db", str(self.db), *args],
                              capture_output=True, text=True, env=env, timeout=120)

    def test_the_command_lists_a_loaded_pack(self):
        (self.dir / "grove.json").write_text(json.dumps({
            "kind": "voice", "name": "grove",
            "labels": {**{k: v for k, v in theme.CANONICAL.items() if str(v).strip()},
                       "today.heading": "In the room"}}))
        result = self.run_cli("theme", "--packs")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("voice grove", result.stdout)

    def test_the_command_reports_a_refused_pack_and_exits_non_zero(self):
        (self.dir / "bad.json").write_text(json.dumps({"kind": "look", "name": "grove",
                                                       "tokens": {"--ink": "<script>"}}))
        result = self.run_cli("theme", "--packs")
        self.assertEqual(result.returncode, 1)
        self.assertIn("refused", result.stdout)

    def test_check_still_passes_with_a_pack_loaded(self):
        (self.dir / "grove.json").write_text(json.dumps({
            "kind": "voice", "name": "grove",
            "labels": {**{k: v for k, v in theme.CANONICAL.items() if str(v).strip()},
                       "today.heading": "In the room"}}))
        result = self.run_cli("theme", "--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
