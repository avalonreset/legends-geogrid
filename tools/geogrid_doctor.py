#!/usr/bin/env python
"""Local readiness check for legends-geogrid."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', action='store_true', help='Require the optional PDF report engine and its dependencies')
    parser.add_argument('--dataforseo', action='store_true', help='Require the shared DataForSEO kit for fresh scans; no API calls')
    parser.add_argument('--jev', action='store_true', help='Check optional legends-jev v0.2.0+ optical recognition readiness')
    parser.add_argument('--basemaps', action='store_true', help='Check local street-map browser setup; no network or paid requests')
    parser.add_argument('--check-playwright', action='store_true', help='Verify local Playwright Chromium launch readiness for street basemaps')
    parser.add_argument('--json', action='store_true', help='Emit machine-readable JSON readiness summary')
    args = parser.parse_args()
    checks: list[dict[str, str]] = []

    def record_ok(label: str, detail: str = "") -> None:
        checks.append({"status": "ok", "label": label, "detail": detail})
        if not args.json:
            ok(label, detail)

    def record_warn(label: str, detail: str = "") -> None:
        checks.append({"status": "warn", "label": label, "detail": detail})
        if not args.json:
            warn(label, detail)

    def record_fail(label: str, detail: str = "") -> None:
        checks.append({"status": "fail", "label": label, "detail": detail})
        if not args.json:
            fail(label, detail)

    required = [
        "package.json",
        "src/main.js",
        "src/data/home-slice-study.json",
        "src/data/home-slice-campaign-research.json",
        "src/data/home-slice-name-review.json",
        "examples/starter-home-slice/report/report.pdf",
        "assets/companion-runtime.js",
        "assets/companion-runtime.css",
        "tools/companion_standalone.py",
        "tools/local_heatmap_poc.py",
        "tools/bulk_geogrid_runner.py",
        "examples/sample-prospects.csv",
        "tests/test_runners.py",
        "tests/test_release_hygiene.py",
        "LICENSE",
        "SECURITY.md",
        "THIRD_PARTY_NOTICES.md",
        "docs/PROVENANCE.md",
        "vite.config.js",
    ]
    missing = []
    if args.basemaps or args.check_playwright:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True, args=['--enable-unsafe-swiftshader'])
                browser.close()
            record_ok('OpenFreeMap renderer', 'Chromium ready; no API key needed (internet required when rendering)')
        except Exception:
            missing.append('street-map browser')
            record_fail('street-map browser', 'pip install -r requirements-basemaps.txt; python -m playwright install --with-deps chromium (Linux system libraries included)')
        if os.environ.get('GOOGLE_MAPS_API_KEY'):
            record_ok('Google Maps key', 'present; optional, not validated; explicit charge opt-in required')
        else:
            record_ok('Google Maps', 'optional; free maps work without it. See docs/BASEMAPS.md for setup')
    if args.dataforseo:
        try:
            import legends_dataforseo
            from legends_dataforseo import api_request  # noqa: F401
            pkg_ver = getattr(legends_dataforseo, "__version__", "installed")
            record_ok('legends-dataforseo', str(pkg_ver))
        except (ImportError, ModuleNotFoundError):
            missing.append('legends-dataforseo')
            record_fail('legends-dataforseo', 'install requirements-dataforseo.txt or cto-legends install legends-dataforseo')
    if args.jev:
        try:
            import legends_jev
            pkg_ver = getattr(legends_jev, "__version__", "installed")
            has_ocr = hasattr(legends_jev, "inspect_signage") and hasattr(legends_jev, "inspect_ocr")
            if has_ocr:
                record_ok('legends-jev', f"{pkg_ver} (optical recognition + signage ready)")
            else:
                record_warn('legends-jev', f"{pkg_ver} (upgrade to >=0.2.0 for optical recognition)")
        except (ImportError, ModuleNotFoundError):
            record_warn('legends-jev', 'not in current Python env (optional; cto-legends install legends-jev for --jev optical signage speed boost)')
    if args.reports:
        required.extend(['tools/strategy_report.py', 'tools/report_model.py', 'tools/adaptive_geogrid.py', 'requirements-report.txt'])
        for module in ('reportlab', 'PIL', 'pypdf', 'pypdfium2'):
            if importlib.util.find_spec(module) is None:
                missing.append(module)
                record_fail('report dependency', f'{module}; install requirements-report.txt')
            else:
                record_ok('report dependency', module)
    for rel in required:
        path = ROOT / rel
        if path.exists():
            record_ok("file", rel)
        else:
            missing.append(rel)
            record_fail("file", rel)

    try:
        payload = json.loads((ROOT / "src/data/home-slice-study.json").read_text(encoding="utf-8"))
        pts = len(payload.get("points") or [])
        lanes = len(payload.get("lanes") or [])
        record_ok("starter dataset", f"{pts} points, {lanes} queries")
    except Exception as exc:
        missing.append("starter dataset parse")
        record_fail("starter dataset", str(exc))

    if command_exists("pnpm"):
        record_ok("pnpm", "available")
    else:
        record_warn("pnpm", "not found on PATH")

    username = os.environ.get("DATAFORSEO_LOGIN") or os.environ.get("DATAFORSEO_USERNAME")
    password = os.environ.get("DATAFORSEO_PASSWORD")
    if username and password:
        record_ok("DataForSEO env", "configured for paid scans")
    else:
        record_warn("DataForSEO env", "not configured, dashboard and dry-runs still work")

    if sys.version_info >= (3, 11):
        record_ok("Python", sys.version.split()[0])
    else:
        missing.append("Python 3.11+")
        record_fail("Python", f"3.11+ required; found {sys.version.split()[0]}")

    if args.json:
        print(json.dumps({"ok": not missing, "missing": missing, "checks": checks}, indent=2))
    if missing:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
