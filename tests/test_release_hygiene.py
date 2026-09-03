from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {
    ".git",
    ".codex-tmp",
    ".private",
    "bulk-runs",
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
)


class ReleaseHygieneTests(unittest.TestCase):
    def test_public_tree_has_no_house_or_personal_markers(self) -> None:
        offenders: list[str] = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
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

    def test_bundled_proofs_are_minimized(self) -> None:
        allowed_root = {"target", "keyword", "location", "metrics", "results"}
        allowed_result = {"point", "rank", "matched_item", "top_items", "error"}
        allowed_point = {"row", "col", "lat", "lng", "tag"}
        for path in sorted((ROOT / "src" / "data").glob("home-slice-*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(allowed_root, set(payload))
            for result in payload["results"]:
                self.assertEqual(allowed_result, set(result))
                self.assertEqual(allowed_point, set(result["point"]))
                if result["matched_item"] is not None:
                    self.assertEqual({"title"}, set(result["matched_item"]))
                for item in result["top_items"]:
                    self.assertEqual({"title"}, set(item))

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
            if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
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
