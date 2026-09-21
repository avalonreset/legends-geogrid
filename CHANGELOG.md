# Changelog

## 0.3.0 - 2026-09-20

- Refreshed the existing release with continuous basemap rendering: preserve embedded credits in their original image position instead of detaching and rescaling a bottom strip. Reject legacy strip configurations with migration guidance; use complete-image bounds and `protected_bottom_px`. Added continuity and credit-overlap regression checks.

- Reject malformed target-rank evidence and provider errors in legacy diagnostic paths; export only validated map fields.
- Added a discovery-first study recipe and explicit operator-led market-fit requirements before dense paid collection. This is documented guidance, not an automatic commercial-market selector.
- Added a reusable client acceptance policy covering restrained colors, map-first pages, geographic registration, neutral distance bands, small readable markers, no em dashes, and visual inspection of every final page.
- Added explicit market-reference centers, mile or kilometer labels, optional main-map height from 410 to 480 pt, matching hollow not-returned markers and legends, and intact appendix sections.
- Added search-setting calibration guidance: verify the exact profile, compare representative queries before a full run, retain controls separately, and distinguish short result lists from full-depth negative evidence.
- Clarified that renderer validation does not authenticate acquisition evidence; independent raw-response verification remains a separate acceptance step.
- Added multi-lane strategy report engine (`tools/strategy_report.py`) producing screen-reading Letter PDFs and HTML from normalized multi-lane observations under a strict map-first copy-fit contract.
- Added copy-fit standard: combined short service pages within a unified 516 pt content column (48 pt Letter margins), compact native text legend band, measured vertical flow, and supporting full-extent appendices, replacing rigid forced multi-page splits.
- Added configuration-driven schema v1 for strategy reports (`examples/reports/`) accepting multi-lane normalized observations with five distinct states (`found`, `not_returned`, `error`, `empty`, `unmeasured`).
- Added adaptive sampling planner and collector (`tools/adaptive_geogrid.py`): offline-first planning, sector-based shell exploration (`adaptive8sectors`), two clean-negative layers with sentinel verification, and synthetic replay support (`--replay`).
- Documented entity intake workflow: target identity anchored by exact CID, place ID, or canonical domain; loose business-name matching is rejected as ambiguous.
- Explicitly separated Google Maps ranks (`rank_group`), Google Search local-pack items, and organic website rankings across all documentation and reporting models.
- Added strategy report dependencies specification (`requirements-report.txt` with ReportLab and Pillow) and updated third-party notices; CI matrix across Windows and Linux (Python 3.10 and 3.12) installs requirements before checks.
- Added offline release smoke test suite (`tools/release_smoke.py` / `pnpm check:reports`) exercising three standalone report examples (`urban-dentist`, `rural-mobile`, `georeferenced-mobile`) plus an 86-row collector-to-report handoff (four validated PDFs in total) without network access; CI uploads proof artifacts from `runs/release-smoke/`.
- Clarified that strategy reports output schematic coordinate maps by default (coordinate axes, distance rings, and rank pins without external tile basemaps) unless an optional local georeferenced basemap image is configured.
- Clarified that Studio currently visualizes bundled demonstration datasets; arbitrary run configuration import remains scheduled on the roadmap.
- Hardened legacy runner (`tools/local_heatmap_poc.py`): HTML reports output schematic distance maps only; `--map-image` is retained for CLI compatibility but unregistered supplied imagery is ignored (registered cartography uses `tools/strategy_report.py` with `map.basemap`).
- Hardened bulk runner (`tools/bulk_geogrid_runner.py`): bumped cache schema to version 4; cache reuse requires SHA-256 verification across parsed JSON, raw requests, provider responses, Markdown, and HTML, rejecting unverified prior cache entries. Added atomic run-directory allocation to prevent collisions.
- Hardened coordinate and competitor validation: dateline longitude wrapping, rejection of pole-crossing/world-spanning grids, nonfinite coordinate/radius rejection, deduplicated per-point competitor counts, and exclusion of provider errors from competitor rankings.
- Hardened adaptive collector (`tools/adaptive_geogrid.py`): updated fingerprint revision to `adaptive-geogrid-v2` (incompatible with v1 run directories); hashes provider responses in full via SHA-256 (`provenance.response_sha256`); raw response bodies are not retained (`response_retained=false`) to prevent copying arbitrary provider fields into outputs.

## 0.2.1 - 2026-09-17

- Fixed report_builder.py crash on missing map-block placeholder (caught by release self-test).

## 0.2.0 - 2026-09-17

- New report layer: keyword-selection formula (`docs/keyword-formula.md`), pre-spend pollution gate (`tools/pollution_gate.py`), multi-intent HTML report builder (`tools/report_builder.py`), and evidence-gate pin verifier (`tools/verify_pins.py`). A report that fails verification does not ship.
- Vendored claude-seo `seo-dataforseo` and `seo-maps` skills (MIT, AgriciDaniel) under `third_party/claude-seo/` with license, citation, and cost-guardrail script intact; documented in THIRD_PARTY_NOTICES.md and README attribution.

## 0.1.3 - 2026-09-03

- Added verified official GitHub hotlinks for attributed dependencies, services, map data, and market-research references.
- Kept LeadSnap linked to its official product page because no official public GitHub identity was verified.

## 0.1.2 - 2026-09-03

- Standardized the product brand everywhere as lowercase `legends-geogrid`.

## 0.1.1 - 2026-09-03

- Added explicit software, service, data, trademark, and research-source attribution.
- Added a complete Leaflet BSD 2-Clause notice and a provenance record for the original market research.
- Switched the default OpenStreetMap layer to the exact policy endpoint with linked ODbL attribution.
- Documented tile-provider overrides and the no-prefetch/no-offline-use boundary.
- Generate a bundled-dependency licence file in every production build.
- Ignore local audit worktrees so release-verification artifacts cannot be committed accidentally.

## 0.1.0 - 2026-09-03

- Renamed the project to `legends-geogrid`.
- Prepared the first public MIT-licensed release.
- Made single scans estimate-only by default.
- Added explicit execution and cost-ceiling gates.
- Included DataForSEO depth multipliers in cost estimates.
- Removed the private Empire vault path from bulk-run defaults.
- Added automated tests, CI, security guidance, and public documentation.
- Rejects incomplete API grids instead of caching or scoring them as valid scans.
- Uses hostname-boundary matching and deduplicates identical rows within a bulk run.
