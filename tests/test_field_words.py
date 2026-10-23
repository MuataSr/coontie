"""Field words: a voice may rename a label, never invent one and never touch a refusal.

Thirty-six forms and one hundred and twenty-eight fields. The canonical labels live in the form specs,
which is the only place they are written; a voice reaches them through one function, and `theme --check`
refuses a pack that names a field the program does not render.
"""

import re
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from test_lan_gate import Server  # noqa: E402

from coontie import theme, web  # noqa: E402
from coontie.workspace import Facility, Room, Workspace  # noqa: E402


class TestTheVocabulary(unittest.TestCase):
    def test_the_program_knows_its_own_fields(self):
        fields = web.form_fields()
        self.assertGreater(len(fields), 100, "the vocabulary is derived from the specs, not typed")
        self.assertIn(("plant", "count"), fields)
        self.assertIn(("receive", "rejected"), fields)

    def test_every_voice_names_only_fields_the_program_renders(self):
        problems = theme.check_all(fields=web.form_fields())
        self.assertEqual(problems, [])

    def test_a_voice_that_names_a_field_that_does_not_exist_is_refused(self):
        problems = theme.check_voice("liar", {**theme.CANONICAL, "field.plant.weight": "Weight"},
                                     fields=web.form_fields())
        self.assertTrue(any("no field" in problem for problem in problems), problems)

    def test_a_voice_that_invents_a_label_is_still_refused(self):
        problems = theme.check_voice("liar", {**theme.CANONICAL, "today.nonsense": "Hello"},
                                     fields=web.form_fields())
        self.assertTrue(any("no label" in problem for problem in problems), problems)

    def test_the_fallback_is_the_wording_the_form_was_written_with(self):
        self.assertEqual(theme.field_label("canonical", "plant", "count", "How many"), "How many")
        self.assertEqual(theme.field_label("quiet", "plant", "count", "How many"), "How many")
        self.assertEqual(theme.field_label("shop", "plant", "count", "How many"),
                         "How many went in")


class TestTheScreen(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "ws.sqlite3"
        self.ws = Workspace(self.db)
        self.ws.add_facility(Facility(id="f1", name="Cure Room Cultivation, LLC",
                                      license_number="MMTC-2026-0781", street="1 Grove Rd",
                                      city="Brooksville", state="FL", zip="34601"))
        self.ws.add_room(Room(id="grow1", facility_id="f1", kind="grow", name="G1", number="01"))
        self.server = None

    def tearDown(self):
        if self.server:
            self.server.close()
        self.ws.close()
        self.tmp.cleanup()

    def start(self):
        self.server = Server(self.db, lan=False)
        self.server.wait()
        return self.server

    def choose(self, voice: str):
        self.ws.set_appearance(look="calm", voice=voice, actor="Maria Lopez",
                               at=datetime(2026, 12, 1, 9, tzinfo=timezone.utc))

    def test_the_shipped_voice_renders_the_canonical_label(self):
        self.choose("canonical")
        status, body, _ = self.start().get("/plant")
        self.assertEqual(status, 200)
        self.assertIn(">How many<", body)

    def test_the_shop_voice_renames_that_label_on_the_same_form(self):
        self.choose("shop")
        status, body, _ = self.start().get("/plant")
        self.assertEqual(status, 200)
        self.assertIn(">How many went in<", body)
        # only the plant form's count is renamed: the batch form's own "How many" is a different field
        # and stays as written, which is what a per-field label table is for
        plant_form = body[body.index("id='plant'"):body.index("id='move'")]
        self.assertNotIn(">How many<", plant_form)
        batch_form = body[body.index("id='batch'"):body.index("id='plant'")]
        self.assertIn(">How many<", batch_form)

    def test_a_form_field_the_voice_says_nothing_about_keeps_its_own_wording(self):
        self.choose("shop")
        _, body, _ = self.start().get("/plant")
        self.assertIn(">Room<", body, "a voice is a set of choices, not a rewrite of every label")

    def refusal_under(self, voice: str) -> str:
        """Post the same bad form under one voice and return the sentence the record refused with."""
        self.choose(voice)
        server = Server(self.db, lan=False)
        server.wait()
        try:
            server.get("/plant")  # a page load is what sets the session cookie
            token = server.httpd.RequestHandlerClass.app.token
            _, body, _ = server.post("/plant", {"token": token, "action": "plant",
                                                "plant__batch": "no-such-batch",
                                                "plant__count": "2"})
            match = re.search(r"<div class=['\"]refusal['\"]>(.*?)</div>", body, re.S)
            self.assertTrue(match, f"no refusal was rendered under {voice}: {body[:400]}")
            return " ".join(match.group(1).split())
        finally:
            server.close()

    def test_a_refusal_reads_the_same_in_every_voice(self):
        canonical = self.refusal_under("canonical")
        shop = self.refusal_under("shop")
        self.assertEqual(canonical, shop,
                         "a refusal comes from the write path, so no voice may soften or sharpen it")
        self.assertIn("batch", canonical.lower())


if __name__ == "__main__":
    unittest.main()
