# legends-geogrid Agent Recipe

This recipe is the canonical agent handoff for `legends-geogrid`, loaded by the `cto-legends` router (`cto-legends handoff legends-geogrid`). Do not register `legends-geogrid` as a separate skill.

## 1. Zero-Credit Companion Launch & Readiness Check

To open the bundled 10-mile Austin starter study (`Home Slice Pizza`, `1,249` origins, `702` competitors, `165` optically audited profiles) or any saved study in the browser without background daemons or open ports:

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
| `python tools/business_name_review.py plan\|submit\|retrieve\|websites\|photos\|export\|attach --output-dir <dir>` | Audit recurring `#1` competitors for GBP title discrepancies, website branding, multi-vantage Street View, and optional `--jev` optical signage checks |
| `python tools/strategy_report.py --config <report-config.json>` | Render the 18-page vector Letter PDF and standalone HTML strategy report |

Refer to [`STUDY-RECIPE.md`](STUDY-RECIPE.md), [`START_A_STUDY.md`](START_A_STUDY.md), and [`BUSINESS_NAME_REVIEW.md`](BUSINESS_NAME_REVIEW.md) for detailed study design and interpretation rules.

## 3. Spend Gates and Credential Discipline

- All paid DataForSEO commands default to offline estimation/preview and require **both** `--execute` and `--confirm-cost-usd <ceiling>` before submitting live provider tasks.
- Standard queue is the default for Google Maps ranking studies and GBP profile refreshes; never fall back from Standard to Live without explicit user request and `--allow-live`.
- Read credentials strictly from environment variables (`DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD`, `TYPESAFE_API_KEY`) or an explicit key file (`--typesafe-api-key-file`). Never print, log, or embed secret values in reports or commits.

## 4. EDR and Security Guardrails

- **No hidden consoles or execution-policy bypass wrappers**: invoke `python tools/study.py`, `python tools/geogrid_doctor.py`, and companion tools directly through standard process execution without hidden console flags or shell execution-policy bypass wrappers.
- **No parent-process tree walking**: never enumerate parent processes or inspect system process trees.
- **No browser profile or OS credential harvesting**: read credentials strictly from environment variables or an explicit key file (`--typesafe-api-key-file`), never from local browser profile databases or OS DPAPI stores.
- **Symlink refusal**: refuse symlink paths (`Path.is_symlink()`) on file inputs, key files, and output paths.
- **Network allowlist**: outbound HTTPS requests are restricted to explicit study and provider endpoints.
