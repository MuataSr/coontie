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
        for name, labels in theme.VOICES.items():
            unknown = [k for k in labels if k not in theme.CANONICAL]
            self.assertEqual(unknown, [], f"{name} invents {unknown}")

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
            self.assertIn("Good morning", shop)      # the heading
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
