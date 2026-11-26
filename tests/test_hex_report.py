"""Unit tests for hex_radius 30-layer vector topography + coastline PDF generation."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import report_builder  # noqa: E402


class HexTopoPdfReportTests(unittest.TestCase):
    def test_philly_hex_study_renders_valid_multipage_vector_topo_pdf(self) -> None:
        study_path = ROOT / "src" / "data" / "cosmis-deli-philly-study.json"
        self.assertTrue(study_path.is_file())
        with tempfile.TemporaryDirectory() as tmp:
            out_pdf = Path(tmp) / "cosmis-deli-philly-topo.pdf"
            receipt = report_builder.build_hex_pdf(study_path, out_pdf)
            self.assertEqual("ok", receipt["status"])
            self.assertEqual("hex_radius", receipt["geometry"])
            self.assertEqual(5, receipt["pages"])  # cover + 3 queries + local leaders
            self.assertEqual(8, receipt["land_mask_polygons"])
            self.assertEqual(458, receipt["points"])
            self.assertGreater(receipt["bytes"], 5000)

            raw = out_pdf.read_bytes()
            self.assertTrue(raw.startswith(b"%PDF-"), "PDF must start with valid %PDF- header")
            self.assertIn(b"%%EOF", raw)

            # Verify structural readability with pypdf
            from pypdf import PdfReader

            reader = PdfReader(str(out_pdf))
            self.assertEqual(5, len(reader.pages))
            page1_text = reader.pages[0].extract_text() or ""
            self.assertIn("Cosmi", page1_text)
            self.assertIn("sandwich shop", page1_text)
            self.assertIn("hoagie", page1_text)
            self.assertNotIn("\u2014", page1_text)

            # Refusing overwrite by default
            with self.assertRaisesRegex(ValueError, "already exists"):
                report_builder.build_hex_pdf(study_path, out_pdf)

    def test_cli_hex_study_mode_emits_json_receipt(self) -> None:
        study_path = ROOT / "src" / "data" / "cosmis-deli-philly-study.json"
        with tempfile.TemporaryDirectory() as tmp:
            out_pdf = Path(tmp) / "cli-out.pdf"
            proc = subprocess.run(
                [sys.executable, str(TOOLS / "report_builder.py"), "--hex-study", str(study_path), "--pdf", str(out_pdf)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            receipt = json.loads(proc.stdout)
            self.assertEqual("ok", receipt["status"])
            self.assertTrue(out_pdf.is_file())
            self.assertTrue(out_pdf.read_bytes().startswith(b"%PDF-"))

    def test_refuses_symlink_output_and_input_paths(self) -> None:
        study_path = ROOT / "src" / "data" / "cosmis-deli-philly-study.json"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            target_file = tmp_dir / "real.pdf"
            link_pdf = tmp_dir / "link.pdf"
            try:
                os.symlink(target_file, link_pdf)
            except (OSError, NotImplementedError):
                self.skipTest("OS does not allow unprivileged symlinks in this environment")
            with self.assertRaisesRegex(ValueError, "symlink|reparse|junction"):
                report_builder.build_hex_pdf(study_path, link_pdf, overwrite=True)


if __name__ == "__main__":
    unittest.main()
