# Product Status

## What This Is Today

GeoGrid is a usable local prototype and proof package.

A person can:

- Run the dashboard locally with `pnpm dev`.
- View a real saved 5 x 5 DataForSEO proof scan.
- Switch between proof data and dense Local Falcon-style simulation.
- Review an Alana-style keyword scan list with business, keyword, average score, scan settings, View buttons, and CSV export.
- Estimate raw DataForSEO scan costs.
- Run no-credit bulk dry runs from CSV.
- Run paid DataForSEO scans from the Python CLI after setting credentials.
- Share the executive PDF with a decision maker.

## What It Is Not Yet

GeoGrid is not yet a finished self-service SaaS.

Missing product pieces:

- Web form that takes a business name, keyword, radius, grid size, and runs DataForSEO directly.
- Backend API for credential storage, job queueing, and result persistence.
- Login, team access, billing, and share links.
- Scheduled campaigns and historical trend charts.
- CSV import UI with progress, retries, and result scoring.
- PDF export generated from inside the app.

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

That turns the current prototype into a real local software product a non-agent user can operate entirely from the browser.

## Parked Citation Research

Citations are not part of the core GeoGrid product right now.

They are a separate local SEO service covering NAP consistency, directory presence, aggregator distribution, duplicate cleanup, and sometimes paid fulfillment. That is useful, but it should not distract from the first product: geo-grid ranking scans plus keyword-list reports.

If this becomes a future add-on, GeoGrid could reasonably build:

- NAP extraction and mismatch detection.
- Tier-one citation presence checks.
- Citation watchlists by business type.
- Lead-report recommendations that explain whether paying $20-$40 for citation fulfillment is sensible.

GeoGrid does not yet provide:

- Direct aggregator submission.
- Directory account creation.
- Ongoing citation renewal or publisher monitoring.

The practical path is to add audit and proof first, then decide whether fulfillment should be vendor-assisted, manually operated, or built through direct aggregator access.
