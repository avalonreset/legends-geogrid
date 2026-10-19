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

## 0.4 / 0.2.0 (Router-native) · Competitive map companion & battlefield intelligence (Shipped)

- Interactive Competitive Map Companion (`src/companion.js`) with `geogrid-companion/v1` and `geogrid-battlefield/v1` local study import and study-bound sidecar attachments (`*.attachments.json`).
- Five coordinated map lenses (**Rankings**, **Local leaders**, **Campaigns**, **Keyword stuffing**, and **Head-to-head**) plus a dockable split-screen **Strategy room**.
- Deterministic study-wide OKLab neighbor color separation, stable `L`-number badges, and outside-circle competitor base connectors.
- Regular circular-lattice sampling (`search_this_area=false`) and nested radius composition (`tools/lattice_sampling.py`, `tools/radius_compose.py`, `tools/competitive_collect.py`).
- Business-name review workbench (`tools/business_name_review.py`, `tools/compose_name_reviews.py`) with Standard-queue exact-CID refreshes, website branding capture, historical report lead matching, and the `0-5` `title-evidence-v1` concern confidence scale.

## Later

- Multi-keyword recurring scans with freshness controls.
- Historical trend charts and competitor movement analysis across time series.
- Optional local SQLite run indexing and CLI/API hooks for workflow automation.
- White-label report templates.

Hosted multi-tenant accounts, cloud billing, and SaaS administration remain intentionally outside the project scope.

