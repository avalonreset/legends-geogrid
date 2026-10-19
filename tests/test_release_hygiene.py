from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {
    ".git",
    ".codex-tmp",
    ".private",
    ".pytest_cache",
    "bulk-runs",
    "runs",
    "dist",
    "node_modules",
    "__pycache__",
}
TEXT_SUFFIXES = {"", ".css", ".csv", ".html", ".js", ".json", ".md", ".py", ".svg", ".txt", ".yaml", ".yml"}
PRIVATE_MARKERS = (
    "rcco" + "l",
    "e:\\" + "ai-marketing-hub-pro",
    "e:\\" + "empire",
    "c:\\" + "users\\",
    "ben" + "jamin",
    "ala" + "na",
    "daniel " + "agrishi",
    "glit" + "chy",
    "omni" + "gent",
    "alpha " + "mechanical",
    "alpha_" + "mechanical",
    "alpha-" + "mechanical",
    "alpha" + "mechanicals",
    "bell " + "brothers",
    "bellbros" + "hvac",
    "7375192447" + "881678500",
)


class ReleaseHygieneTests(unittest.TestCase):
    def test_ignored_ancestor_does_not_disable_source_scan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / ".private" / "checkout"
            root.mkdir(parents=True)
            (root / "source.md").write_text(PRIVATE_MARKERS[0], encoding="utf-8")
            with patch.dict(globals(), ROOT=root):
                with self.assertRaises(AssertionError):
                    self.test_public_tree_has_no_house_or_personal_markers()
                (root / "source.md").write_text("Public example", encoding="utf-8")
                (root / "runs").mkdir()
                (root / "runs" / "private.md").write_text(PRIVATE_MARKERS[0], encoding="utf-8")
                self.test_public_tree_has_no_house_or_personal_markers()

    def test_public_tree_has_no_house_or_personal_markers(self) -> None:
        offenders: list[str] = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts):
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            if any(marker in text for marker in PRIVATE_MARKERS):
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual([], offenders)

    def test_example_credentials_are_empty(self) -> None:
        values: dict[str, str] = {}
        for raw_line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            key, value = line.split("=", 1)
            values[key] = value
        self.assertEqual("", values["DATAFORSEO_USERNAME"])
        self.assertEqual("", values["DATAFORSEO_PASSWORD"])

    def test_bundled_starter_pack_is_complete_and_compact(self) -> None:
        study_path = ROOT / "src" / "data" / "home-slice-study.json"
        research_path = ROOT / "src" / "data" / "home-slice-campaign-research.json"
        review_path = ROOT / "src" / "data" / "home-slice-name-review.json"
        report_pdf = ROOT / "examples" / "starter-home-slice" / "report" / "report.pdf"
        self.assertTrue(study_path.is_file())
        self.assertTrue(research_path.is_file())
        self.assertTrue(review_path.is_file())
        self.assertTrue(report_pdf.is_file())

        study = json.loads(study_path.read_text(encoding="utf-8"))
        self.assertEqual("geogrid-companion/v1", study.get("schema"))
        self.assertEqual(1249, len(study.get("points") or []))
        self.assertEqual(4, len(study.get("lanes") or []))
        self.assertEqual(30, (study.get("study") or {}).get("depth"))
        self.assertIsInstance(study.get("profiles"), dict)
        plan_sha = (study.get("evidence") or {}).get("plan_sha256")
        self.assertTrue(isinstance(plan_sha, str) and len(plan_sha) == 64)

        research = json.loads(research_path.read_text(encoding="utf-8"))
        self.assertEqual("geogrid-campaign-research/v1", research.get("schema"))
        self.assertEqual(plan_sha, research.get("studyPlanSha256"))

        review = json.loads(review_path.read_text(encoding="utf-8"))
        self.assertEqual("geogrid-name-review/v1", review.get("schema"))
        self.assertEqual(plan_sha, review.get("study_plan_sha256"))

    def test_map_endpoint_and_attribution_match_osm_policy(self) -> None:
        source = (ROOT / "src" / "main.js").read_text(encoding="utf-8")
        self.assertIn("https://tile.openstreetmap.org/{z}/{x}/{y}.png", source)
        self.assertNotIn("https://{s}.tile.openstreetmap.org", source)
        self.assertIn("https://www.openstreetmap.org/copyright", source)

    def test_notices_and_generated_license_config_are_present(self) -> None:
        notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        provenance = (ROOT / "docs" / "PROVENANCE.md").read_text(encoding="utf-8")
        vite_config = (ROOT / "vite.config.js").read_text(encoding="utf-8")
        self.assertIn("Copyright (c) 2010-2023, Volodymyr Agafonkin", notices)
        self.assertIn("Open Database License", notices)
        self.assertIn("DataForSEO", notices)
        self.assertIn("Local Falcon", provenance)
        self.assertIn("Search Atlas", provenance)
        self.assertIn("third-party-licenses.md", vite_config)

    def test_product_brand_is_lowercase_slug(self) -> None:
        offenders: list[str] = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts):
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "Legends" + " GeoGrid" in text:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual([], offenders)

    def test_attribution_links_use_verified_upstream_githubs(self) -> None:
        public_attribution = "\n".join(
            [
                (ROOT / "README.md").read_text(encoding="utf-8"),
                (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8"),
                (ROOT / "docs" / "PROVENANCE.md").read_text(encoding="utf-8"),
            ]
        )
        expected = {
            "https://github.com/Leaflet/Leaflet",
            "https://github.com/vitejs/vite",
            "https://github.com/postcss/postcss",
            "https://github.com/openstreetmap",
            "https://github.com/dataforseo",
            "https://github.com/local-falcon",
            "https://github.com/search-atlas-group",
            "https://github.com/BrightLocal",
        }
        self.assertEqual([], sorted(url for url in expected if url not in public_attribution))


if __name__ == "__main__":
    unittest.main()
