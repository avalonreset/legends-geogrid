# GeoGrid

GeoGrid is a private local SEO geo-grid prototype. It recreates the practical core of a Local Falcon or Search Atlas style heatmap with DataForSEO as the rank source, Google Maps as the visual layer, and our own dashboard, cache, scoring, and report workflow.

## Executive Read

The core product is buildable. DataForSEO Google Maps SERP can query local map rankings from precise coordinates, one grid point at a time. Google Maps should be used for maps and geocoding, not as the ranking source.

Raw rank-data cost is low:

| Grid | Pins | DataForSEO Standard | 1,000 prospects |
|---|---:|---:|---:|
| 3 x 3 | 9 | $0.0054 | $5.40 |
| 5 x 5 | 25 | $0.0150 | $15.00 |
| 9 x 9 | 81 | $0.0486 | $48.60 |
| 17 x 17 | 289 | $0.1734 | $173.40 |

The recommended first paid proof is a real 1,000-prospect list at 5 x 5 Standard, or 9 x 9 Standard if the goal is to spend close to $50 for a stronger visual proof.

## What Is In This Repo

- `src/` - standalone Vite dashboard demo.
- `tools/local_heatmap_poc.py` - one-business DataForSEO geo-grid runner.
- `tools/bulk_geogrid_runner.py` - cache-aware bulk runner scaffold.
- `tools/geogrid_doctor.py` - local readiness check.
- `examples/runs/home-slice-5x5/` - saved 5 x 5 DataForSEO proof run.
- `examples/bulk-runs/sample-dryrun/` - no-credit bulk dry-run manifest.
- `docs/local-seo-geogrid-executive-report.pdf` - sendable executive report.
- `docs/PRODUCT_STATUS.md` - what works today and what still needs product work.
- `docs/DANIEL_HANDOFF.md` - short review path for Daniel.

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

This is usable as local software plus CLI:

- The browser app visualizes proof data and estimates costs.
- The Python runners can execute real DataForSEO scans after credentials are set.
- The bulk runner can dry-run, estimate, fingerprint, and cache scans.

It is not yet a full self-service app where a user types a business into the browser and clicks Run. That requires a backend API, job queue, and SQLite/result store. See `docs/PRODUCT_STATUS.md`.

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
