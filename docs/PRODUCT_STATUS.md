# Product Status

## Release state

The refreshed version 0.3.0 adds the shared legends-dataforseo-kit dependency for fresh provider calls. Offline reporting and saved demos remain credential-free. The transport change keeps existing queue handling and scan spend gates.

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

## Proof dataset

The bundled Home Slice Pizza dataset is a historical demonstration scan for `pizza` in Austin, collected June 26, 2026:

- Grid: 17 x 17 / 289 coordinate tasks.
- DataForSEO method: Standard Queue.
- Historical reported raw API cost: $0.1734.
- Found: 225 of 289 points.
- Top 3: 100 of 289 points.
- Top 10: 201 of 289 points.
- Average rank where found: 4.97.

It is demonstration data, not a claim about current rankings.

## Recommended next milestone

Import saved `parsed-grid.json` scans and report configurations directly into the Leaflet browser studio, then add optional SQLite-backed local run history. That closes the gap between the working CLI toolchain and the visual interface without introducing cloud dependencies.
