"""The generated catalog must match the code. Regenerate with scripts/export_events.py."""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestGeneratedDocs(unittest.TestCase):
    def test_catalog_doc_is_current(self):
        committed = (ROOT / "docs" / "requirements" / "dh5059-events.md").read_text(encoding="utf-8")
        sys.path.insert(0, str(ROOT / "src"))
        sys.path.insert(0, str(ROOT / "scripts"))
        from export_events import render  # noqa: WPS433

        self.assertEqual(
            committed,
            render(),
            "docs/requirements/dh5059-events.md is stale; run python3 scripts/export_events.py",
        )

    def test_sources_file_lists_the_primary_documents(self):
        text = (ROOT / "docs" / "sources.md").read_text(encoding="utf-8")
        for needle in ("64-4.221", "64-4.222", "DH5059-OMMU-05/2026", "Ref-19592"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
