"""The look and voice layer: variety that cannot break the record.

The tests that matter here are the ones about what does NOT change: the same DOM under every skin,
the same printed evidence in every voice, and a checker that refuses a skin which smuggles in a
script, a network fetch or a colour that will not follow the theme.
"""

import re
import sys
import tempfile
import unittest
from pathlib import Path

from coontie import theme
from coontie.workspace import Workspace
from coontie.web import App

sys.path.insert(0, str(Path(__file__).parent))
import test_g4_gate as g4  # noqa: E402  (a seeded facility with a dispatched manifest)


def seed(db: Path) -> None:
    g4.seed(db)


def visible(html: str) -> str:
    """The words on the page, with styles and markup removed."""
    body = re.sub(r"<style.*?</style>", "", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", text).strip()


class TestSkins(unittest.TestCase):
    def test_every_skin_defines_every_required_token(self):
        for name, tokens in theme.SKINS.items():
            missing = [t for t in theme.REQUIRED_TOKENS if t not in tokens]
            self.assertEqual(missing, [], f"{name} is missing {missing}")

    def test_the_built_in_skins_and_voices_pass_their_own_check(self):
        self.assertEqual(theme.check_all(), [])

    def test_the_stylesheet_carries_no_colour_that_would_ignore_the_skin(self):
        hexes = re.findall(r"#[0-9a-fA-F]{3,8}\b", theme.SHELL_CSS)
        self.assertEqual(hexes, [], f"hardcoded colours in the skin layer: {hexes}")

    def test_the_evidence_layout_is_black_on_white_and_not_a_token(self):
        self.assertIn("color:#000", theme.EVIDENCE_CSS.replace(" ", ""))
        self.assertIn("background:#fff", theme.EVIDENCE_CSS.replace(" ", ""))
        self.assertNotIn("var(--", theme.EVIDENCE_CSS)

    def test_only_the_tokens_differ_between_skins(self):
        calm, touch = theme.css_for("calm"), theme.css_for("touch")
        def strip_tokens(css: str) -> str:
            return re.sub(r":root \{[^}]*\}\n", "", css)
        self.assertEqual(strip_tokens(calm), strip_tokens(touch),
                         "a skin changed more than the token block")

    def test_the_same_page_has_the_same_words_under_every_skin(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "ws.sqlite3"
            seed(db)
            ws = Workspace(db)
            texts = {}
            try:
                for skin in theme.SKINS:
                    ws.set_appearance(look=skin, voice="quiet", actor="test")
                    app = App(db)
                    texts[skin] = visible(app.render_today(ws, "Maria Lopez"))
            finally:
                ws.close()
            first = texts["calm"]
            for skin, text in texts.items():
                self.assertEqual(text, first, f"{skin} changed the words on the page")

    def test_each_skin_actually_changes_the_pixels(self):
        self.assertNotEqual(theme.css_for("calm"), theme.css_for("contrast"))
        self.assertIn("--size:19px", theme.css_for("touch"))

    def test_a_skin_that_breaks_the_contract_is_refused(self):
        broken = dict(theme.SKINS["calm"])
        del broken["--accent"]
        self.assertTrue(any("missing token --accent" in p for p in
                            theme.check_skin("broken", broken)))
        self.assertTrue(any("markup" in p for p in
                            theme.check_skin("broken", {**theme.SKINS["calm"], "--ink": "<b>"})))
        self.assertTrue(any("script" in p for p in
                            theme.check_skin("broken", theme.SKINS["calm"], "<script>x</script>")))
        self.assertTrue(any("network" in p for p in
                            theme.check_skin("broken", theme.SKINS["calm"],
                                             "@import url('https://x/y.css');")))


class TestVoices(unittest.TestCase):
    def test_every_voice_names_only_labels_the_program_has(self):
        # two vocabularies now: the canonical label keys, and the form fields a voice may rename.
        # Both are checked here, because a voice that invents either is a pack the contract refuses.
        from coontie.web import form_fields

        fields = {theme.field_key(action, name) for action, name in form_fields()}
        for name, labels in theme.VOICES.items():
            unknown = [k for k in labels if k not in theme.CANONICAL and k not in fields]
            self.assertEqual(unknown, [], f"{name} invents {unknown}")
            # and the contract itself must agree, so this cannot pass by being generous here
            self.assertEqual(theme.check_voice(name, labels, fields=form_fields()), [], name)

    def test_every_voice_says_something_for_every_word_that_stands_for_a_rule(self):
        for name, labels in theme.VOICES.items():
            for key, term in theme.TERMS.items():
                self.assertIn(key, labels, f"{name} is silent about {key} ({term})")

    def test_each_term_the_voices_point_at_is_a_citation_this_record_can_make(self):
        for term in theme.TERMS.values():
            self.assertTrue(theme.catalogue_reference(term), term)

    def test_a_voice_with_an_unknown_label_or_an_empty_line_is_refused(self):
        self.assertTrue(theme.check_voice("x", {"no.such.label": "hi"}))
        self.assertTrue(theme.check_voice("x", {**theme.VOICES["quiet"], "word.manifest": "  "}))

    def test_the_voice_changes_the_heading_and_the_words_the_record_generates(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "ws.sqlite3"
            seed(db)
            ws = Workspace(db)
            try:
                ws.set_appearance(look="calm", voice="canonical", actor="test")
                canonical = visible(App(db).render_today(ws, "Maria Lopez"))
                ws.set_appearance(look="calm", voice="shop", actor="test")
                shop = visible(App(db).render_today(ws, "Maria Lopez"))
            finally:
                ws.close()
            self.assertIn("Notes", canonical)
            self.assertIn("This week", canonical)
            self.assertIn("Worth a look", shop)      # the same section, in the shop voice
            self.assertIn("Last week", shop)
            self.assertIn(theme.greeting("shop", __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc)), shop)   # the heading, from the clock
            self.assertIn("to sort", shop)           # the badge label

    def test_the_record_s_own_words_are_renamed_without_touching_the_record(self):
        line = "Justification jst-1a2b is due soon. 2 exposures open."
        shop = theme.speak(line, "shop")
        self.assertIn("written explanation", shop)
        self.assertIn("things open", shop)
        self.assertNotIn("Justification", shop)
        self.assertEqual(theme.speak(line, "canonical"), line)

    def test_the_printed_evidence_keeps_its_own_words_in_every_voice(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "ws.sqlite3"
            seed(db)
            ws = Workspace(db)
            try:
                for voice in ("canonical", "shop"):
                    ws.set_appearance(look="calm", voice=voice, actor="test")
                    html = App(db).render_audit(ws, "Maria Lopez")
                    block = re.search(r"<div class=['\"]printonly['\"]>.*", html, re.S)
                    self.assertIsNotNone(block, "the print block is gone")
                    printed = block.group(0)
                    # the statutory furniture is there whichever voice is installed
                    self.assertIn("Inspected by", printed)
                    self.assertIn("hash chain head", printed)
                    self.assertIn("MMTC-2026-0030", printed)
                    # and none of the operator-facing voice leaked into the evidence
                    for shop_word in ("Good morning", "to sort", "Worth a look", "things open"):
                        self.assertNotIn(shop_word, printed)
            finally:
                ws.close()


class TestGreeting(unittest.TestCase):
    def when(self, hour, minute=0):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        return datetime(2026, 10, 22, hour, minute, tzinfo=ZoneInfo("America/New_York"))

    def test_the_shop_voice_greets_the_hour_it_actually_is(self):
        self.assertEqual(theme.greeting("shop", self.when(8)), "Good morning")
        self.assertEqual(theme.greeting("shop", self.when(11, 59)), "Good morning")
        self.assertEqual(theme.greeting("shop", self.when(12)), "Good afternoon")
        self.assertEqual(theme.greeting("shop", self.when(12, 21)), "Good afternoon")
        self.assertEqual(theme.greeting("shop", self.when(16, 59)), "Good afternoon")
        self.assertEqual(theme.greeting("shop", self.when(17)), "Good evening")
        self.assertEqual(theme.greeting("shop", self.when(23, 50)), "Good evening")

    def test_only_the_shop_voice_greets(self):
        for voice in ("canonical", "quiet", "official"):
            self.assertEqual(theme.greeting(voice, self.when(9)), "", voice)

    def test_the_page_says_the_greeting_that_matches_its_own_clock(self):
        from datetime import datetime, timezone

        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "ws.sqlite3"
            seed(db)
            ws = Workspace(db)
            try:
                ws.set_appearance(look="calm", voice="shop", actor="test")
                text = visible(App(db).render_today(ws, "Maria Lopez"))
            finally:
                ws.close()
            expected = theme.greeting("shop", datetime.now(timezone.utc))
            self.assertTrue(expected, "the shop voice should greet at any hour")
            self.assertIn(expected, text)
            for other in ("Good morning", "Good afternoon", "Good evening"):
                if other != expected:
                    self.assertNotIn(other, text)


class TestFindingSentences(unittest.TestCase):
    def finding(self, code="drift_open", kind="quantity_mismatch"):
        from coontie.inspect import EXPOSURE, Finding

        return Finding(
            code, EXPOSURE, "canonical summary", subject="drf-1",
            facts={"kind": kind, "record_key": "FL-INV-005",
                   "ours": {"quantity": "25", "unit": "units", "status": "active"},
                   "theirs": {"quantity": "35.0", "unit": "units", "status": "on_hold"}},
        )

    def test_each_voice_phrases_the_same_finding_its_own_way(self):
        f = self.finding()
        self.assertEqual(theme.finding_sentence("canonical", f), "canonical summary")
        self.assertIn("you count 25 units, they count 35 units",
                      theme.finding_sentence("shop", f))
        self.assertIn("you hold 25 units, the department holds 35 units",
                      theme.finding_sentence("quiet", f))
        self.assertIn("quantity differs, ours 25 units, theirs 35 units",
                      theme.finding_sentence("official", f))

    def test_a_parser_artefact_is_not_a_quantity(self):
        self.assertNotIn("35.0", theme.finding_sentence("shop", self.finding()))

    def test_missing_and_status_read_differently_in_each_voice(self):
        missing = self.finding(kind="missing_locally")
        missing.facts["ours"] = {}
        self.assertIn("The state has FL-INV-005 and you do not",
                      theme.finding_sentence("shop", missing))
        self.assertIn("is in the department's export and not in this record",
                      theme.finding_sentence("official", missing))

        status = self.finding(kind="status_mismatch")
        self.assertIn("is on hold on their side", theme.finding_sentence("shop", status))
        self.assertIn("status differs, ours active, theirs on hold",
                      theme.finding_sentence("official", status))

    def test_a_finding_without_facts_keeps_the_inspector_s_words(self):
        from coontie.inspect import EXPOSURE, Finding

        bare = Finding("ledger_broken", EXPOSURE, "The chain does not verify")
        self.assertEqual(theme.finding_sentence("shop", bare), "The chain does not verify")

    def test_the_manifest_sentence_speaks_each_voice(self):
        from coontie.inspect import EXPOSURE, Finding

        f = Finding("manifest_unreceived", EXPOSURE, "canonical summary", subject="man-1",
                    facts={"manifest": "man-1", "recipient": "Tampa Dispensary",
                           "departed": "2026-10-22T08:00:00+00:00"})
        self.assertIn("Nothing came back from Tampa Dispensary",
                      theme.finding_sentence("shop", f))
        self.assertIn("No receipt recorded for the delivery to Tampa Dispensary",
                      theme.finding_sentence("quiet", f))
        self.assertIn("departed 2026-10-22 with no receipt",
                      theme.finding_sentence("official", f))


class TestInstallation(unittest.TestCase):
    def test_the_choice_is_recorded_with_who_made_it(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "ws.sqlite3"
            seed(db)
            ws = Workspace(db)
            try:
                chosen = ws.set_appearance(look="contrast", voice="shop", actor="Maria Lopez")
                self.assertEqual((chosen["look"], chosen["voice"]), ("contrast", "shop"))
                self.assertEqual(chosen["set_by"], "Maria Lopez")
                events = [e.event_key for e in ws.ledger.entries()]
                self.assertEqual(events.count("appearance_chosen"), 1)
                ok, summary = ws.verify()
                self.assertTrue(ok, summary)
            finally:
                ws.close()
            again = Workspace(db)
            try:
                self.assertEqual(again.appearance()["look"], "contrast")
            finally:
                again.close()

    def test_a_choice_that_does_not_exist_is_refused_with_the_real_names(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "ws.sqlite3"
            seed(db)
            ws = Workspace(db)
            try:
                with self.assertRaises(ValueError) as ctx:
                    ws.set_appearance(look="dark", voice="shop")
                self.assertIn("calm", str(ctx.exception))
                with self.assertRaises(ValueError) as ctx:
                    ws.set_appearance(look="calm", voice="pirate")
                self.assertIn("canonical", str(ctx.exception))
            finally:
                ws.close()

    def test_an_unknown_setting_in_the_file_falls_back_to_the_default(self):
        with tempfile.TemporaryDirectory() as d:
            db = Path(d) / "ws.sqlite3"
            seed(db)
            ws = Workspace(db)
            try:
                ws.conn.execute("INSERT INTO settings (key,value,set_by,set_at)"
                                " VALUES ('look','neon','x','2026-10-22T00:00:00+00:00')")
                ws.conn.commit()
                self.assertEqual(ws.appearance()["look"], theme.DEFAULT_SKIN)
            finally:
                ws.close()


if __name__ == "__main__":
    unittest.main()
