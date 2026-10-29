# Changelog

## 0.2.2 - 2026-10-29

- Raise minimum supported Python runtime to Python 3.11 (`"python": ">=3.11"`, `"node": ">=22.0.0"` in `package.json`, `tools/geogrid_doctor.py`, and CI matrix).
- Update pinned `legends-dataforseo` dependency in `requirements-dataforseo.txt` to `v0.1.6` (`58c3409253beaa5614f3f9af0a5b71903d322b55`).
- Harden GitHub Actions workflows with 40-character commit SHA action pins, explicit `contents: read` permissions, and `pip>=26.2.2` before package installation.

## 0.2.1 - 2026-10-21

- Add **Multi-Vantage Google Street View Search Quest & GBP Visual Inspection Gallery** (`tools/business_name_review.py`, `src/name-review.js`, `src/companion.css`): `photos` command pulls high-resolution GBP `main_image` and `logo` files plus up to 3 spatially distinct Street View panoramas (`streetview`, `streetview_v1`, `streetview_v2`) using progressive search radii (`18m`, `30m`, `50m`, `85m`), indoor 360 photosphere trap detection (`<= 2` road nodes), historical time-machine filtering (`info[5][0][8]`), sweet-spot standoff (`13m..38m`), and lateral road stepping (`>= 10m` apart) to step around curbside trees and side walls.
- Add **Optional `legends-jev` Optical Recognition Accelerator (`--jev`)**: when `legends-jev` (`v0.2.0+`, `jev-1.14.0`) is installed in the `cto-legends` ecosystem, `python tools/business_name_review.py photos --output-dir <dir> --jev` runs ~200ms System One optical verification over downloaded storefront, Street View, and logo images (`sign_visible`, `suspect_terms_shown`, `best_image`, `sign_box`, and `verdict`), automatically promoting unobstructed alternate Street View vantages (`streetview_v1`/`v2`).
- Update **10-Mile Home Slice Pizza Starter Case Study (`src/data/home-slice-name-review.json`, `public/starter-photos/home-slice/`)**: bundle 54 verified GBP and multi-vantage Street View evidence photos across all 18 investigated Austin pizzerias, clearing **DeSano Pizzeria Napoletana** (`301 Lavaca St Ste 200`, CID `3865327066180748277`) to `name_supported` (`0/5`) after front-street Lavaca verification (`panoid=FJ2xBzIZFRIAYHzsaTC1RA`) confirmed `DESANO PIZZERIA NAPOLETANA` on the brick facade (reducing flagged title concerns from 15 to 14).
- Fix **Canvas Territory Overlay Clipping (`src/rank-canvas.js`)**: wrap circle-clipped `ctx.clip()` draws in `ctx.save()` / `ctx.restore()` inside `drawTerritoryLayer` so hover/pan redraws never cumulatively intersect and carve away at the territory overlay.
- Ecosystem readiness (`tools/geogrid_doctor.py`): support `legends-dataforseo` (`v0.1.5`) package version inspection and optional `--jev` optical recognition readiness checks.

## 0.2.0 - 2026-10-19

- Add the **Competitive Map Companion** (`index.html`, `src/companion.js`, `src/study-model.js`, `src/rank-canvas.js`): interactive circular-lattice workspace with equal-sided stop-sign pins scaled to 30% of grid spacing, four-corner continuous gradient diamonds, animated rank-1 cyan sparkles, coverage dots distinguishing top-30 absence from incomplete responses, and full-field competitor search across all observed profiles while preserving `/legacy.html` for the original grid studio.
- Add **Local Leaders & Neighbor Coloring** (`src/local-leaders.js`, `src/leader-colors.js`): recurring (`3+` wins) and all-winner coverage modes, deterministic study-wide OKLab neighbor color separation, stable `L`-number badges across queries, and dashed connectors to competitor bases more than two miles outside the study circle.
- Add **Strategy Room & Head-to-Head Matchups** (`src/strategy-room.js`, `src/strategy-engine.js`, `src/strategy-map-panel.js`, `tools/battlefield.py`, `tools/battlefield_intelligence.py`): dockable split-screen regional/service comparison matrix and direct two-profile `matchup` map overlays.
- Add **Territory Campaigns** (`src/campaign-panel.js`, `src/territory-intelligence.js`): spatial footholds, advance zones (ranks 4-10), defended areas, and study-bound `campaign-research.json` action briefs.
- Add **Business-Name Review (`Keyword stuffing`) Workbench** (`tools/business_name_review.py`, `tools/compose_name_reviews.py`, `src/name-review.js`, `src/title-confidence.js`, `src/review-attachment.js`): read-only agent-owned dossier for Google Business Profile title discrepancies, Standard-queue exact-CID profile verification, website branding capture, historical report lead reconciliation (`--include-cid` / `--only-cid`), multi-run evidence composition, study-bound sidecar attachments (`*.attachments.json`), and an explained `0-5` `title-evidence-v1` concern confidence rubric.
- Add **Circular-Lattice Sampling & Nested Radius Composition** (`tools/lattice_sampling.py`, `tools/radius_sampling.py`, `tools/radius_compose.py`, `tools/competitive_collect.py`, `tools/competitive_export.py`, `tools/visibility_policy.py`): regular square lattice clipped to a true circle with `search_this_area=false`, reusing inner-radius points when expanding outward under matched controls, plus `--compact` profile-table deduplication (`profiles` dictionary) that shrinks 10-mile 4-query top-30 companion exports by ~90%.
- Add **10-Mile Home Slice Pizza Starter Case Study & Completed Report** (`src/data/home-slice-study.json`, `src/data/home-slice-campaign-research.json`, `src/data/home-slice-name-review.json`, `examples/starter-home-slice/`): replace the legacy single-query `17x17` and `5x5` samples with a fresh v0.2.0 10-mile, 0.5-mile spacing (`1,249`-origin, 4-query, `depth=30`, `search_this_area=false`) starter pack including Campaign Research, 165-profile Business-Name Review with `0-5` `title-evidence-v1` confidence scores, and a verified 18-page Strategy Report (`report.pdf` + `report.html`).
- Add **Interactive Basemap Switcher & Local Google Map Tiles Adapter** (`src/basemap-switcher.js`, `src/google-tiles.js`, `src/persistent-tiles.js`, `src/wheel-zoom.js`, `tools/google-tiles-plugin.mjs`): OpenStreetMap Legends dark treatment, OpenFreeMap vector styles, smooth fractional wheel zoom with tile crossfading, and optional server-held Google Map Tiles session proxying.
- Security & hygiene: override `source-map-js >= 1.2.2` (`CVE-2026-93749`) and expand public-tree release hygiene checks across 520 automated tests (129 Node viewer tests and 391 Python unit tests).

## 0.1.0 - 2026-09-25

- Router-native generation reset: study recipe moves from root SKILL.md to docs/STUDY-RECIPE.md (no skill frontmatter); pinned cto-legends router skill vendored at skills/cto-legends/SKILL.md (router commit 6975dcbf073e5eec7a30ce6a04a6975238c61158); DataForSEO kit re-pinned to kit 0.1.0 (dd00fb030393f300226ca18db3644bb141f96fb0); version reset to 0.1.0 with history preserved.

## 0.4.1 - 2026-09-23

- Introduce the Multi-Perspective Sampling Doctrine: default to a high-resolution
  neighborhood core baseline (1.0 to 1.5 km radius, <= 0.5 km point spacing) to
  dip the toe in the water with minimal initial spend (~$0.15 for 3 queries).
- Add actionable multi-perspective expansion guidance in sampling review:
  encourage users not to be cheap with DataForSEO tokens and reveal the full
  picture across multiple zoom levels.
- Add Path A (Dominant Core): recommend zooming out to a regional 8-12 mile
  footprint at provider zoom 11z-12z to locate where regional competitors contest
  service area territory when the neighborhood core is saturated.
- Add Path B (Active Edge Frontier): recommend same-resolution outward expansion
  via study enhancement along directional corridors when near-miss ranks touch
  the core perimeter.
- Fix study lane execution cost check underflow by applying floating-point tolerance
  to per-query cost confirmations in single-grid collection.

## 0.4.0 - 2026-09-22

- Add `study.py enhance`: result-driven same-extent refinement, dated observation
  reuse, incremental cost estimates, point-level acquisition/recovery, linked
  vault history, and regenerated HTML/PDF editions.
- Preserve provider observation timestamps through the single-grid collector.
- Unify light/dark editorial layouts; light uses pure-white printing surfaces
  and black ink without the former separate theme sequence.

- Add an explicitly disclosed GBP-supported study path for independently recorded website retrieval failures; identity and offering evidence remain mandatory.
- Default to 3-5 distinct search themes with cited selection rationale; label supported smaller studies as focused.
- Add agent-neutral business research recipe and source-backed study validation.
- Add bounded DataForSEO research, website capture, cost reservation ledger and evidence snapshots.
- Require explicit diagnostic mode for unresearched low-level paid scans.
- Keep market-fit interpretation distinct from automated evidence checks.


- Real PDF reports default to OpenFreeMap street imagery without a Google key; failed acquisition stops report generation. Synthetic examples remain offline.
- Saved scan HTML includes an interactive street map and writes a reusable PDF config.
- Added basemap setup doctor, optional Google Static Maps with explicit paid opt-in, and complete-image attribution protection.


## 0.3.2 - 2026-09-22

- Incorporate Agrici Daniel's report theme and dense-grid HTML improvements.
- Keep dark reports as the default; offer a pure-white light theme with red, black,
  and white accents, unchanged rank colors, and legends-geogrid branding.
- Support optional operator verification notes without an implied verification badge.
- Improve dense HTML grids, adaptive pin sizing, and missing-evidence status display.
- Preserve the pinned DataForSEO kit v0.4.0 and existing collection/cost controls.

## 0.3.1 - 2026-09-21

- Pin the separately maintained legends-dataforseo-kit v0.4.0 for fresh scans.
  Installation uses an immutable source ZIP and does not require Git.
- Retain the shared transport contract for live requests, queued submissions,
  and task retrieval, including pending, empty, and failed task statuses.
- Clarify the tested dependency pairing in user and agent setup instructions.
  Offline reports, existing caches, and explicit execution/cost gates are unchanged.

## 0.3.0 - 2026-09-20

- Use the public legends-dataforseo-kit for fresh Live and Standard/Priority Queue requests, preserving task statuses, existing spend gates, and credential-free offline workflows.
- Add the pinned provider dependency manifest, agent setup instructions, and a no-network dependency doctor.
- Lead with open-source google maps rank checker across the banner, README, and project metadata; clarify data costs and self-managed operation.


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
