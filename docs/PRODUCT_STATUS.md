# Product Status

## What This Is Today

GeoGriddy is a usable local prototype and proof package for an eventual Local SEO Brain feature.

A person can:

- Run the dashboard locally with `pnpm dev`.
- View a real saved 17 x 17 DataForSEO proof scan.
- Pan and zoom the interactive map.
- Review an Alana-style keyword scan list with business, keyword, average score, scan settings, View buttons, and CSV export.
- Estimate raw DataForSEO scan costs.
- Run no-credit bulk dry runs from CSV.
- Run paid DataForSEO scans from the Python CLI after setting credentials.
- Share the executive HTML report or browser-safe PDF with a decision maker.

## Current Proof Dataset

The main dashboard proof is Home Slice Pizza in Austin for the keyword `pizza`:

- Grid: 17 x 17, 289 coordinate tasks.
- Queue: DataForSEO Standard Queue.
- Reported raw rank-data cost: $0.1734.
- Found points: 225 of 289.
- Top 3 points: 100 of 289.
- Top 10 points: 201 of 289.
- Average rank where found: 4.97.

The older 5 x 5 proof remains in `examples/runs/home-slice-5x5/` as a historical cache artifact.

## What It Is Not Yet

GeoGriddy is not a SaaS project.

Missing feature pieces:

- Agent command or skill wrapper that takes a business, keyword, radius, and grid size.
- Result store for cached scans, preferably SQLite or the Local SEO Brain vault data layer.
- Browser report launch from a saved scan ID.
- Scheduled campaigns and historical trend charts.
- CSV import or brain-backed business list intake with progress, retries, and result scoring.
- PDF/export generated from saved scan artifacts.

## Practical Use Without An Agent

The current repo does not require Codex to operate.

Use the dashboard for demo and interpretation:

```powershell
pnpm install
pnpm dev
```

Use the CLI for DataForSEO work:

```powershell
$env:DATAFORSEO_USERNAME="..."
$env:DATAFORSEO_PASSWORD="..."
pnpm dryrun:sample
```

Paid execution requires adding `--execute --confirm-cost-usd <amount>` to the bulk runner command.

## Best Next Product Step

Add a small local backend:

- FastAPI or Node API.
- SQLite database.
- `/api/scans/dry-run`.
- `/api/scans/run`.
- `/api/scans/:id`.
- App form that calls those endpoints.

That turns the current prototype into a real Local SEO Brain feature: agent prepares the work, the CLI/API executes it, and the browser report provides the visual proof.

## Parked Citation Research

Citations are not part of the core GeoGriddy feature right now.

They are a separate local SEO service covering NAP consistency, directory presence, aggregator distribution, duplicate cleanup, and sometimes paid fulfillment. That is useful, but it should not distract from the first product: geo-grid ranking scans plus keyword-list reports.

If this becomes a future add-on, GeoGriddy could reasonably build:

- NAP extraction and mismatch detection.
- Tier-one citation presence checks.
- Citation watchlists by business type.
- Lead-report recommendations that explain whether paying $20-$40 for citation fulfillment is sensible.

GeoGriddy does not yet provide:

- Direct aggregator submission.
- Directory account creation.
- Ongoing citation renewal or publisher monitoring.

The practical path is to add audit and proof first, then decide whether fulfillment should be vendor-assisted, manually operated, or built through direct aggregator access.
