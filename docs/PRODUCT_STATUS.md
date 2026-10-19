# Current release: 0.2.0

The current release pairs the **Competitive Map Companion** (`index.html`, `src/companion.js`), **Local Leaders & neighbor-aware OKLab coloring**, **Strategy Room & Head-to-Head matchups**, **Territory Campaigns**, **Circular-Lattice sampling & nested radius composition**, and the **Business-Name Review (`Keyword stuffing`) workbench** (including the `0-5` `title-evidence-v1` concern confidence scale and historical report lead reconciliation) with business-first research, public GBP and website evidence, 3-5 justified search themes, decision-oriented PDF/HTML reports, and a persistent Markdown/JSON study library. Real reports default to free street maps; dark and white print modes share the same template. `study.py enhance` executes finer sampling within the existing footprint with eligible point reuse and incremental estimates.

520 automated tests (129 Node viewer tests and 391 Python unit tests) and four offline report workflows passed, including Windows and Linux Python 3.10 and 3.12 CI. Agents remain responsible for semantic research and recommendation quality. See [release readiness](RELEASE_READINESS.md) for supported limits and [GitHub Releases](https://github.com/avalonreset/legends-geogrid/releases) for exact-commit verification receipts and downloads.


## Historical 0.3.0 record

# Product Status

## Release state

The refreshed version 0.3.0 adds the shared legends-dataforseo dependency for fresh provider calls. Offline reporting and saved demos remain credential-free. The transport change keeps existing queue handling and scan spend gates.

Version 0.3.0 adds the multi-lane strategy report engine, adaptive sampling collector, and copy-fit contracts. Source distributions and release notes are available from [GitHub Releases](https://github.com/avalonreset/legends-geogrid/releases).

Today it can:

- Run a no-credential browser demo with a saved real 17 x 17 proof scan.
- Switch between rank pins, a heat view, and point-level evidence in the Leaflet studio.
- Estimate single or bulk scan cost without making an API call.
- Execute fresh DataForSEO scans only after `--execute` and a sufficient `--confirm-cost-usd` ceiling are supplied.
- Cache bulk scans by full request identity and skip fresh matches.
- Build multi-intent HTML reports and verify pins against raw JSON evidence (`tools/verify_pins.py`).
- Generate screen-reading Letter PDFs and HTML strategy reports (`tools/strategy_report.py`) under a map-first copy-fit contract (516 pt content width, 48 pt margins, compact native text legend band; 216 PPI figures).
- Plan and execute sector-based adaptive scans (`tools/adaptive_geogrid.py`) with offline-first planning and synthetic replay.
- Run complete offline release smoke tests (`tools/release_smoke.py` / `pnpm check:reports`) verifying three standalone report examples and an 86-row collector handoff (four validated PDFs in total) without network access.
- Write raw receipts, parsed JSON, Markdown, HTML, JSONL, and CSV artifacts locally.

Client acceptance completed on 19 September 2026 with a second real business: four service queries across 121 shared origins, processed through the common configuration and renderer. The resulting nine-page PDF passed independent raw-evidence, metric, geographic-registration and all-page visual review against the approved design. Private client data and proprietary fonts are excluded from this source package. See [Client report acceptance policy](REPORT_ACCEPTANCE.md). This validates the tested workflow, not every business or future scan.

Final 0.3.0 local acceptance passed 172 tests, four PDF workflows, the browser build, and dependency audit. The exact source package independently passed all 172 tests and four PDF workflows on Windows. The preceding candidate passed 168 tests and four offline PDF workflows on Windows and clean Linux. A final renderer-disclosure correction passed 45 report tests on both platforms and all four Linux PDF workflows. Version 0.3.0 retains that implementation and includes the discovery-first operating recipe learned during client review. Release scope is the improved collection and reporting tool, not an automated guarantee of commercially useful market selection. Operators must complete the study-purpose and market-fit review before dense collection. See [Start a study](START_A_STUDY.md).

## v0.3.0 release refresh

The refreshed v0.3.0 source distribution replaces detached basemap credit strips with continuous-image
rendering. Embedded credits remain in place and protected from overlays. Legacy
`credit_strip_px` configurations require complete-image bounds and the new
`protected_bottom_px` setting; see [map configuration and migration](../examples/reports/README.md#maps-and-fonts).
The refresh passes 174 tests and four offline PDF workflows. The version and release URL remain unchanged.

## Honest limitations

- Business discovery and market-fit acceptance are operator-led procedures. The software does not automatically research an operating base, validate travel economics, or enforce that review before a scan.

- The browser studio does not yet load arbitrary run folders or import report configs; it ships with bundled proof and modeled demonstration datasets.
- Strategy report PDF generation requires local Python dependencies (`reportlab`, `Pillow`) from `requirements-report.txt`.
- Strategy reports render schematic coordinate maps (distance rings, cardinal axes, and rank pins without requiring external tile basemaps) unless an optional georeferenced local basemap image is supplied. Schematic map style is independent of whether the underlying observations are real or synthetic.
- `tools/local_heatmap_poc.py` HTML reports are schematic only; unregistered `--map-image` inputs are ignored (use `tools/strategy_report.py` with `map.basemap` for registered cartography).
- The adaptive collector (`adaptive-geogrid-v2`) records full SHA-256 digests of provider responses in the ledger and observations rather than retaining raw response bodies (`response_retained=false`); replay from stored raw responses is not supported for this adapter (use `--replay <replay.json>`).
- Cache schema 4 rejects unverified prior cache entries from earlier schemas; collector revision `adaptive-geogrid-v2` is incompatible with earlier v1 run directories.
- Business-name matching can be ambiguous. CID, place ID, or canonical domain matching is recommended for paid work.
- Queue polling is synchronous and sequential after batched submission.
- The cache index is a JSON file, not transactional or concurrent storage.
- There are no background daemons, historical trend charts, multi-user accounts, hosted service, or support SLA.
- Scans represent bounded point observations, not certified market coverage or guaranteed ranking predictions.

## Starter case study dataset (v0.2.0)

The bundled Home Slice Pizza starter case study (`src/data/home-slice-study.json`, `src/data/home-slice-campaign-research.json`, `src/data/home-slice-name-review.json`, and `examples/starter-home-slice/report/`) is a complete v0.2.0 Austin study for `Home Slice Pizza` (`1415 S Congress Ave, Austin, TX 78704`, CID `12299280573550492680`), collected October 19, 2026:

- Footprint: `10-mile` radius (`16.09344 km`), `0.5-mile` spacing (`0.804672 km`), `1,249` shared circular-lattice origins (`radius_grid`).
- Queries (4 distinct themes): `pizza restaurant` (`21` top-3, `261` top-10, `917` found), `new york style pizza` (`549` top-3, `1,023` top-10, `1,249` found), `pizza by the slice` (`470` top-3, `952` top-10, `1,183` found), and `pizza takeout` (`6` top-3, `222` top-10, `850` found).
- Controls: DataForSEO Google Maps Standard Queue, `depth = 30`, `zoom = 13`, `search_this_area = false` (`4,996` tasks, `$2.9976` SERP collection spend).
- Business-name review: `165` first-place winning profiles verified via Standard Queue GBP tasks (`$0.2475`) and `139` captured websites, with `79` recurring leaders source-reviewed and scored on the `0-5` `title-evidence-v1` rubric.
- Completed report: 18-page PDF (`examples/starter-home-slice/report/report.pdf`) and HTML (`examples/starter-home-slice/report/report.html`) with OpenFreeMap street basemaps and `pypdfium2` QA verification.

It is a saved demonstration snapshot, not a live real-time ranking claim.

## Recommended next milestone

Import saved `parsed-grid.json` scans and report configurations directly into the Leaflet browser studio, then add optional SQLite-backed local run history. That closes the gap between the working CLI toolchain and the visual interface without introducing cloud dependencies.
