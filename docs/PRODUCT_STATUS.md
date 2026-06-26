# Product Status

## What This Is Today

GeoGrid is a usable local prototype and proof package.

A person can:

- Run the dashboard locally with `pnpm dev`.
- View a real saved 5 x 5 DataForSEO proof scan.
- Switch between proof data and dense Local Falcon-style simulation.
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
