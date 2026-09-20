# Roadmap

## 0.1 · Local scanner foundation (Shipped)

- Estimate-first single and bulk DataForSEO Google Maps SERP runners.
- Explicit `--execute` and `--confirm-cost-usd` spend ceilings.
- Interactive Leaflet/OpenStreetMap browser studio with bundled demonstration datasets.
- Schema-v3 cache fingerprinting and no-spend safety tests.

## 0.2 · Report layer & verification (Shipped)

- Multi-intent HTML report builder (`tools/report_builder.py`).
- Pre-spend query calibration formula (`docs/keyword-formula.md`).
- Evidence-gate pin verifier (`tools/verify_pins.py`) tracing pins to raw JSON.
- Vendored MIT Claude SEO skills for keyword demand and Maps intelligence.

## 0.3 · Strategy reports & adaptive sampling (0.3.0)

- Multi-lane strategy report engine (`tools/strategy_report.py`) producing screen-reading Letter PDFs and HTML.
- Map-first copy-fit contract: unified 516 pt content columns, 48 pt margins, compact native text legend band, and supporting full-extent appendices.
- Adaptive sampling collector (`tools/adaptive_geogrid.py`) with sector expansion (`adaptive8sectors`), clean-negative stopping, and synthetic replay.
- Normalized observation contract (`query_id, lat, lng, rank, state, returned_count, depth, sampled_at, source`).

## 0.4 · Connect runners to studio

- Import saved `parsed-grid.json` scans and strategy report configurations directly into the Leaflet browser studio.
- Add an optional lightweight local SQLite store for run indexing.
- Side-by-side scan comparisons in the browser.

## Later

- Multi-keyword recurring scans with freshness controls.
- Historical trend charts and competitor movement analysis.
- Optional local CLI/API hooks for workflow automation.
- White-label report templates.

Hosted multi-tenant accounts, cloud billing, and SaaS administration remain intentionally outside the project scope.
