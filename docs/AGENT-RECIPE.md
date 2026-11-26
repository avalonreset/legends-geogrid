# legends-geogrid Agent Recipe

This recipe is the canonical agent handoff for `legends-geogrid`, loaded by the `cto-legends` router (`cto-legends handoff legends-geogrid`). Do not register `legends-geogrid` as a separate skill.

## 1. Zero-Credit Companion Launch & Readiness Check

To open the bundled 6-mile river-clipped South Philadelphia starter study (`Cosmi's Deli`, `458` dry-land honeycomb origins, `1,170` observed profiles, all `250` `#1` winners audited) or any saved study in the browser without background daemons or open ports:

```sh
python tools/study.py --open
python tools/study.py open --study runs/<slug>/companion-study.json
```

Before running fresh scans, PDF report rendering, or optional optical signage verification, verify local environment readiness offline:

```sh
python tools/geogrid_doctor.py --dataforseo --jev --reports --basemaps --check-playwright --json
```

## 2. Core CLI Workflows

| Command | Purpose |
| --- | --- |
| `python tools/study.py --open` | Build and open the self-contained static Competitive Map Companion in the default browser (`$0`, zero background processes) |
| `python tools/geogrid_doctor.py [--dataforseo] [--jev] [--reports] [--basemaps] [--check-playwright] [--json]` | Offline readiness check for Python/Node runtimes, `legends-dataforseo`, optional `legends-jev`, ReportLab/Pillow, and Playwright Chromium |
| `python tools/study.py query-review --plan <plan.json>` | Validate candidate search themes, GBP categories, observation ages, and scope before paid collection |
| `python tools/study.py proposal --plan <plan.json> --output-dir <dir>` | Generate the pre-collection HTML/PDF study proposal and cost estimate |
| `python tools/competitive_collect.py --plan <plan.json> --output-dir <dir> [--execute --confirm-cost-usd <max>]` | Preview or execute circular-lattice Google Maps Standard queue collection |
| `python tools/competitive_export.py --run-dir <dir> --output <companion-study.json> --compact` | Export collected observations into a compact `geogrid-companion/v1` dataset |
| `python tools/business_name_review.py plan\|submit\|retrieve\|websites\|photos\|export\|attach --output-dir <dir>` | Audit `#1` competitors for GBP title discrepancies via Firecrawl/HTTP websites, provider GBP storefront/logo photos, optional `--official-streetview`, and optional `--jev` optical checks |
| `python tools/report_builder.py --hex-study <companion-study.json> --pdf <report.pdf>` | Render the 30-layer vector topography and river-clipped Local Leaders hex PDF report |
| `python tools/strategy_report.py --config <report-config.json>` | Render the legacy multi-page vector Letter PDF and standalone HTML strategy report |

Refer to [`STUDY-RECIPE.md`](STUDY-RECIPE.md), [`START_A_STUDY.md`](START_A_STUDY.md), and [`BUSINESS_NAME_REVIEW.md`](BUSINESS_NAME_REVIEW.md) for detailed study design and interpretation rules.

## 3. Spend Gates and Credential Discipline

- All paid DataForSEO commands default to offline estimation/preview and require **both** `--execute` and `--confirm-cost-usd <ceiling>` before submitting live provider tasks.
- Standard queue is the default for Google Maps ranking studies and GBP profile refreshes; never fall back from Standard to Live without explicit user request and `--allow-live`.
- Read credentials strictly from environment variables (`DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD`, `TYPESAFE_API_KEY`) or an explicit key file (`--typesafe-api-key-file`). Never print, log, or embed secret values in reports or commits.
- On first optional Google Maps setup, ask the user once where to store `GOOGLE_MAP_TILES_API_KEY` (an OS user environment variable or persistent `~/.cto-legends/secrets/geogrid.env`) so it survives shell restarts and `cto-legends` upgrades.
- Google Maps key lookup runs strictly server-side in priority order: process env, `LEGENDS_GEOGRID_ENV_FILE`, `~/.cto-legends/secrets/geogrid.env`, then repo `.env.local` and `.env` (refusing symlinked paths and never exposing keys to the browser).
- Verify Google Maps key readiness offline with `python tools/geogrid_doctor.py --basemaps --json` (reports boolean presence and source type only).

## 4. EDR and Security Guardrails

- **No hidden consoles or execution-policy bypass wrappers**: invoke `python tools/study.py`, `python tools/geogrid_doctor.py`, and companion tools directly through standard process execution without hidden console flags or shell execution-policy bypass wrappers.
- **No parent-process tree walking**: never enumerate parent processes or inspect system process trees.
- **No browser profile or OS credential harvesting**: read credentials strictly from environment variables or an explicit key file (`--typesafe-api-key-file`), never from local browser profile databases or OS DPAPI stores.
- **Symlink refusal**: refuse symlink paths (`Path.is_symlink()`) on file inputs, key files, and output paths.
- **Network allowlist**: outbound HTTPS requests are restricted to explicit study and provider endpoints.
