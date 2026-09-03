# Legends GeoGrid

Legends GeoGrid is an open-source, local-first geo-grid rank scanner for Google Maps results. It turns one business, one keyword, and a center coordinate into a visual ranking grid without requiring a hosted rank-tracking subscription.

![Legends GeoGrid studio](docs/legends-geogrid-studio.png)

The browser studio ships with a saved real-world 17 x 17 proof scan, so you can explore the interface without credentials or API spend. The Python runners use DataForSEO for fresh scans, cache results by scan fingerprint, and require explicit execution plus a cost ceiling before spending credits.

## Why it exists

A 17 x 17 grid contains 289 coordinate checks. At DataForSEO's documented September 2026 Standard Queue base rate of `$0.0006` per Maps SERP, one 17 x 17 business-keyword scan is about `$0.1734` in raw rank-data cost. One thousand equivalent scans are about `$173.40` before any optional parameter multipliers.

That is the point of this project: the underlying data collection can be inexpensive when you own the workflow. Legends GeoGrid gives builders, agencies, and local SEO operators a transparent starting point instead of forcing every experiment through a SaaS credit system.

Pricing changes. Depth above 100 results and other paid parameters can multiply the actual charge. The runners include the documented depth multiplier in estimates, but always review current DataForSEO pricing before a large run.

## What works

- Interactive Leaflet/OpenStreetMap studio with rank pins, heat view, evidence view, and cost planning.
- Saved 17 x 17 and 5 x 5 proof datasets that do not trigger API calls.
- Single-business DataForSEO Google Maps SERP runner.
- CSV-driven bulk runner with estimates, fingerprints, freshness-aware caching, and resumable artifacts.
- Standard, Priority, and Live DataForSEO methods.
- Explicit `--execute` and `--confirm-cost-usd` spend gates.
- Markdown, HTML, JSON, JSONL, and CSV artifacts.
- No database, hosted backend, analytics, or telemetry.

This is a practical local tool and reference implementation, not feature-for-feature parity with a mature hosted platform.

## Quick start: browser demo

Requirements:

- Node.js 20.19+ or 22.12+
- pnpm 10+
- Python 3.10+ for scan runners

```powershell
git clone https://github.com/avalonreset/legends-geogrid.git
cd legends-geogrid
pnpm install --frozen-lockfile
pnpm dev
```

Open the local URL printed by Vite. No DataForSEO credentials are needed for the saved proof or modeled demo.

Run the full local verification:

```powershell
pnpm check
```

## Estimate a fresh scan

Estimation is the default. This command makes no API call and spends nothing:

```powershell
python tools/local_heatmap_poc.py `
  --keyword "pizza" `
  --target-name "Example Pizza" `
  --center-lat 30.249711 `
  --center-lng -97.749132 `
  --grid-size 17 `
  --radius-km 2 `
  --depth 20 `
  --method standard
```

## Run a paid scan

Set credentials in your shell. Do not put them in Git:

```powershell
$env:DATAFORSEO_USERNAME="your-login"
$env:DATAFORSEO_PASSWORD="your-password"
```

Then repeat the estimate command with both spend gates:

```powershell
python tools/local_heatmap_poc.py `
  --keyword "pizza" `
  --target-name "Example Pizza" `
  --center-lat 30.249711 `
  --center-lng -97.749132 `
  --grid-size 17 `
  --radius-km 2 `
  --depth 20 `
  --method standard `
  --execute `
  --confirm-cost-usd 0.18
```

The command refuses to execute when its estimated base cost exceeds the ceiling.

For stronger business matching, add a known `--target-cid`, `--target-place-id`, or `--target-domain`. Name matching alone is intentionally conservative but can still produce false positives for similar business names.

## Bulk scans

Start with the bundled no-credit dry run:

```powershell
pnpm dryrun:sample
```

Estimate your own CSV:

```powershell
python tools/bulk_geogrid_runner.py `
  --prospects prospects.csv `
  --run-id dentists-austin `
  --method standard `
  --grid-size 5 `
  --radius-km 2 `
  --depth 20
```

Execute only after reviewing the manifest and total ceiling:

```powershell
python tools/bulk_geogrid_runner.py `
  --prospects prospects.csv `
  --run-id dentists-austin `
  --method standard `
  --grid-size 5 `
  --radius-km 2 `
  --depth 20 `
  --execute `
  --confirm-cost-usd 15
```

The sample CSV documents accepted columns. By default, artifacts stay under the repository's ignored `bulk-runs/` directory. To write an optional Obsidian-style summary elsewhere, pass `--vault-data-dir <directory>` explicitly.

## Cache identity

Paid scans are fingerprinted by target identity, keyword, center coordinate, radius, grid size, depth, zoom, device, language, search domain, search-places setting, and queue method. Fresh cached scans are skipped before paid calls.

Cache protection reduces accidental duplicate work; it is not a transactional billing guarantee. DataForSEO does not refund duplicate tasks caused by client-side mistakes, so keep the spend ceiling conservative.

## Repository map

- `src/` — local Vite studio and saved parsed proof datasets.
- `tools/local_heatmap_poc.py` — estimate-first single scan runner.
- `tools/bulk_geogrid_runner.py` — cache-aware CSV runner.
- `tools/geogrid_doctor.py` — local readiness check.
- `tests/` — cost, grid, cache, and no-spend safety tests.
- `examples/` — sample CSV and sanitized proof artifacts.
- `docs/` — product status, technical notes, roadmap, and demo screenshot.

## Data and privacy

Fresh run folders can contain business names, coordinates, public Maps listing details, DataForSEO task IDs, and raw API responses. They are ignored by Git by default. Review artifacts before sharing them and follow the terms and legal rights that apply to your DataForSEO account and the underlying search-engine data.

The bundled Home Slice Pizza proof is historical demonstration data collected on June 26, 2026. It is not a current ranking claim, an endorsement, or private client data.

## License

MIT. See [LICENSE](LICENSE).

Leaflet is BSD-2-Clause licensed. OpenStreetMap tiles and data carry their own usage and attribution requirements; the studio displays OpenStreetMap attribution on the map.

Legends GeoGrid is independent software. It is not affiliated with or endorsed by DataForSEO, Google, OpenStreetMap, Local Falcon, or Search Atlas.
