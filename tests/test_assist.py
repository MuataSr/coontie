"""The deterministic reader and grammar: what "AI-like" means with no model at all."""

import unittest

from coontie.assist import (
    COA_FIELDS,
    INVOICE_FIELDS,
    KNOWN_LABS,
    Parse,
    parse_command,
    read_document,
)

LOTS = (("stk-77ce050301", "Blue Dream"), ("stk-6ca1f059ca", "Nightshade Gummies"))
VOCAB = dict(
    cultivars=("Blue Dream", "Nightshade Gummies"),
    rooms=("INV1", "INV2"),
    labs=KNOWN_LABS,
    people=("Maria Lopez", "Dev Patel"),
    manifests=("man-4c918dee4e",),
    lots=LOTS,
)


class TestCommandGrammar(unittest.TestCase):
    def parse(self, text: str) -> Parse:
        return parse_command(text, **VOCAB)

    def test_send_becomes_a_manifest_with_the_lot_already_resolved(self):
        p = self.parse("send 200 g blue dream to Tampa Dispensary with Maria Lopez, Dev Patel")
        self.assertEqual(p.intent, "manifest")
        self.assertEqual(p.args["items"], [("stk-77ce050301", "200")])
        self.assertEqual(p.args["crew"], ["Maria Lopez", "Dev Patel"])
        self.assertIn("--item stk-77ce050301:200", p.command())

    def test_crew_survives_and_handles_typos(self):
        p = self.parse("ship 50 g blue dream to Tampa with maria and dev")
        self.assertEqual(len(p.args["crew"]), 2)

    def test_one_person_is_flagged_not_refused_at_parse_time(self):
        p = self.parse("send 10 g blue dream to Tampa with Maria Lopez")
        self.assertEqual(p.intent, "manifest")
        self.assertTrue(any("two people" in n for n in p.notes))

    def test_move_becomes_a_split_and_does_not_read_the_room_number_as_a_quantity(self):
        p = self.parse("move the nightshade gummies from inv1 to inv2")
        self.assertEqual(p.intent, "split")
        self.assertEqual(p.args["room"], "INV2")
        self.assertEqual(p.args["quantity"], "")
        self.assertTrue(any("no quantity" in n for n in p.notes))

    def test_sample_names_the_lot_and_the_lab(self):
        p = self.parse("sample 5 g of blue dream for ACS")
        self.assertEqual(p.intent, "sample")
        self.assertEqual(p.args["lot"], "stk-77ce050301")
        self.assertEqual(p.args["lab"], "ACS Laboratory")

    def test_adjust_maps_plain_words_to_the_rules_own_cause(self):
        p = self.parse("adjust 2 g of blue dream because I knocked over a jar")
        self.assertEqual(p.intent, "adjust")
        self.assertEqual(p.args["cause"], "spillage")

    def test_adjust_without_a_cause_says_so(self):
        p = self.parse("adjust 2 g of blue dream")
        self.assertEqual(p.intent, "adjust")
        self.assertTrue(any("no cause" in n for n in p.notes))

    def test_cure_reads_the_harvest_id_and_the_post_weight(self):
        p = self.parse("cure harvest hrv-1234 to 620 g")
        self.assertEqual(p.intent, "cure")
        self.assertEqual(p.args["harvest"], "hrv-1234")
        self.assertEqual(p.args["post"], "620")

    def test_verbs_inside_a_sentence_are_found(self):
        p = self.parse("can you dispatch manifest man-4c918dee4e please")
        self.assertEqual(p.intent, "dispatch")

    def test_a_report_needs_no_arguments(self):
        self.assertEqual(self.parse("audit").intent, "audit")
        self.assertEqual(self.parse("brief").intent, "brief")

    def test_unknown_verb_names_a_near_miss(self):
        p = self.parse("shipp 10 g blue dream to Tampa")
        self.assertEqual(p.intent, "manifest")

    def test_a_question_is_not_a_command_and_says_so(self):
        p = self.parse("what happened to blue dream last week")
        self.assertFalse(p.ok)
        self.assertTrue(p.notes)


class TestDocumentReading(unittest.TestCase):
    COA = (
        "CERTIFICATE OF ANALYSIS\nProduct: Blue Dream Flower 3.5g\nTotal THC 24.31 %\n"
        "Total CBD 0.08 %\nACS Laboratory\nTested: 11/02/2026\nSample ID: ACS-88213\n"
    )

    def test_a_complete_coa_reads_every_field(self):
        got = read_document(self.COA)
        self.assertEqual(got.kind, "coa")
        self.assertTrue(got.complete)
        self.assertEqual(got.fields["thc_percent"], "24.31")
        self.assertEqual(got.fields["tested_on"], "2026-11-02")
        self.assertEqual(got.fields["lab"], "ACS Laboratory")

    def test_a_missing_value_stays_missing_rather_than_guessed(self):
        got = read_document("Certificate of Analysis\nProduct: Sour Diesel\nTotal THC: 19.6 %\n")
        self.assertIn("cbd_percent", got.missing)
        self.assertNotIn("cbd_percent", got.fields)

    def test_an_unknown_lab_is_not_named(self):
        got = read_document(self.COA.replace("ACS Laboratory", "GreenLeaf Analytics"))
        self.assertIn("lab", got.missing)

    def test_an_invoice_reads_the_money_fields(self):
        got = read_document(
            "INVOICE INV-2291\nBill To: Tampa Dispensary\nSeller: Nature's Grace FL, LLC\n"
            "Quantity: 1,200 g\nUnit Price: $7.00\nInvoice Date: 2026-12-15\n"
        )
        self.assertEqual(got.kind, "invoice")
        self.assertEqual(got.fields["buyer"], "Tampa Dispensary")
        self.assertEqual(got.fields["quantity"], "1200")
        self.assertEqual(got.fields["unit_price"], "7")
        self.assertEqual(got.fields["invoice_date"], "2026-12-15")

    def test_nothing_recognisable_returns_no_fields(self):
        got = read_document("lorem ipsum dolor sit amet")
        self.assertEqual(got.kind, "unknown")
        self.assertEqual(got.fields, {})
        self.assertEqual(got.missing, COA_FIELDS)

    def test_invoice_fields_are_the_ones_we_store(self):
        got = read_document("Invoice\nBill To: X\n")
        self.assertEqual(set(got.missing) | set(got.fields), set(INVOICE_FIELDS))


if __name__ == "__main__":
    unittest.main()
