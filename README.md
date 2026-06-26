# geo-griddy

geo-griddy is a private local SEO geo-grid feature prototype. It recreates the practical core of a Local Falcon or Search Atlas style heatmap with DataForSEO as the rank source, an interactive browser map as the visual layer, and our own dashboard, cache, scoring, and report workflow.

The intended home is the AI Marketing Hub / Local SEO Brain ecosystem, not a standalone SaaS. A user should be able to invoke the workflow from Codex or Claude, reuse business data already stored in the brain, and open a browser artifact for the visual proof.

## Executive Read

The core product is buildable. DataForSEO Google Maps SERP can query local map rankings from precise coordinates, one grid point at a time. Map rendering and geocoding are separate display utilities; the current prototype uses an interactive browser map so the paid rank source stays isolated from the visual layer.

Raw rank-data cost is low:

| Grid | Pins | DataForSEO Standard | 1,000 prospects |
|---|---:|---:|---:|
| 3 x 3 | 9 | $0.0054 | $5.40 |
| 5 x 5 | 25 | $0.0150 | $15.00 |
| 9 x 9 | 81 | $0.0486 | $48.60 |
| 17 x 17 | 289 | $0.1734 | $173.40 |

The recommended first bulk proof is a real 1,000-prospect list at 5 x 5 Standard, or 9 x 9 Standard if the goal is to spend close to $50 for a stronger visual proof. Dense 17 x 17 views are better used as one-prospect showpieces or high-value account scans, not first-pass bulk triage. This repo includes one real 17 x 17 Home Slice Pizza proof scan.

## What Is In This Repo

- `src/` - standalone Vite dashboard demo for the eventual Local SEO Brain feature.
- `tools/local_heatmap_poc.py` - one-business DataForSEO geo-grid runner.
- `tools/bulk_geogrid_runner.py` - cache-aware bulk runner scaffold.
- `tools/geogrid_doctor.py` - local readiness check.
- `src/data/home-slice-17x17.json` - parsed real 17 x 17 DataForSEO proof scan.
- `examples/runs/home-slice-5x5/` - saved 5 x 5 DataForSEO proof run.
- `examples/runs/20260626-105950-homeslicepizza/` - saved 17 x 17 DataForSEO proof run.
- `examples/bulk-runs/sample-dryrun/` - no-credit bulk dry-run manifest.
- `docs/local-seo-geogrid-executive-report.pdf` - sendable executive report.
- `docs/PRODUCT_STATUS.md` - what works today and what still needs product work.
- `docs/DANIEL_HANDOFF.md` - short review path for Daniel.
- `docs/CITATION_MODULE_NOTES.md` - parked citation/NAP research for a possible future add-on.

## Quickstart

```powershell
pnpm install
pnpm dev
```

Then open the local Vite URL.

Build check:

```powershell
pnpm build
pnpm check:python
pnpm doctor
```

## What Works Today

This is usable as local agent-operated software plus CLI:

- The browser app opens on a real cached 17 x 17 DataForSEO proof scan and visualizes it on an interactive pan/zoom map.
- The browser app includes an Alana-style keyword scan list with CSV export.
- The Python runners can execute real DataForSEO scans after credentials are set.
- The bulk runner can dry-run, estimate, fingerprint, and cache scans.

## Proof Artifacts

- `docs/proof-geogriddy-17x17-clean.png` - real one-prospect 17 x 17 proof map.
- `docs/proof-geogriddy-keyword-list.png` - Alana-style multi-keyword scan list.

It is not trying to become a hosted SaaS. The next product shape is a Local SEO Brain feature where the agent prepares scan inputs, executes cached or paid DataForSEO work, and opens the browser report. See `docs/PRODUCT_STATUS.md`.

Citations are intentionally not mixed into the core feature. The research is parked in `docs/CITATION_MODULE_NOTES.md` because citation fulfillment is a separate local SEO service, not the rank-map product Alana asked for.

## Running A Paid Scan

Set credentials in your shell, not in Git:

```powershell
$env:DATAFORSEO_USERNAME="..."
$env:DATAFORSEO_PASSWORD="..."
```

Dry-run a bulk estimate:

```powershell
python tools/bulk_geogrid_runner.py --prospects examples/sample-prospects.csv --run-id sample-dryrun --method standard --grid-size 5 --radius-km 2 --depth 20 --zoom 15
```

Execute only after confirming a real prospect list and cost ceiling:

```powershell
python tools/bulk_geogrid_runner.py --prospects prospects.csv --run-id dentists-austin-202606 --method standard --grid-size 5 --radius-km 2 --depth 20 --zoom 15 --execute --confirm-cost-usd 15
```

## Cache Rule

Do not pay twice for the same dataset. The bulk runner fingerprints scans by target identity, keyword, center coordinate, radius, grid size, depth, zoom, device, language, search domain, search-places flag, and queue mode.

Keep raw paid receipts outside Obsidian-style note folders when runs become large. Store compact indexes, manifests, parsed JSONL or SQLite, screenshots, timestamps, freshness labels, and DataForSEO task IDs.

## Private Status

This is an internal prototype. No open-source license is granted by default.
