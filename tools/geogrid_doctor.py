#!/usr/bin/env python
"""Local readiness check for the GeoGrid prototype."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def ok(label: str, detail: str = "") -> None:
    print(f"OK  {label}{': ' + detail if detail else ''}")


def warn(label: str, detail: str = "") -> None:
    print(f"WARN {label}{': ' + detail if detail else ''}")


def fail(label: str, detail: str = "") -> None:
    print(f"FAIL {label}{': ' + detail if detail else ''}")


def command_exists(command: str) -> bool:
    resolved = shutil.which(command)
    if not resolved and os.name == "nt":
        resolved = shutil.which(f"{command}.cmd")
    if not resolved:
        return False
    try:
        subprocess.run([resolved, "--version"], capture_output=True, text=True, check=False)
        return True
    except FileNotFoundError:
        return False


def main() -> int:
    required = [
        "package.json",
        "src/main.js",
        "src/data/home-slice-5x5.json",
        "tools/local_heatmap_poc.py",
        "tools/bulk_geogrid_runner.py",
        "examples/sample-prospects.csv",
        "docs/local-seo-geogrid-executive-report.pdf",
    ]
    missing = []
    for rel in required:
        path = ROOT / rel
        if path.exists():
            ok("file", rel)
        else:
            missing.append(rel)
            fail("file", rel)

    try:
        payload = json.loads((ROOT / "src/data/home-slice-5x5.json").read_text(encoding="utf-8"))
        metrics = payload.get("metrics", {})
        ok("proof dataset", f"{metrics.get('points')} points, {metrics.get('solv')}% top 3")
    except Exception as exc:
        missing.append("proof dataset parse")
        fail("proof dataset", str(exc))

    if command_exists("pnpm"):
        ok("pnpm", "available")
    else:
        warn("pnpm", "not found on PATH")

    username = os.environ.get("DATAFORSEO_USERNAME")
    password = os.environ.get("DATAFORSEO_PASSWORD")
    if username and password:
        ok("DataForSEO env", "configured for paid scans")
    else:
        warn("DataForSEO env", "not configured, dashboard and dry-runs still work")

    if os.environ.get("GOOGLE_MAPS_API_KEY"):
        ok("Google Maps env", "configured")
    else:
        warn("Google Maps env", "not configured, bundled static demo map still works")

    if missing:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
