# legends-geogrid technical notes

## Rank-data path

Each grid coordinate becomes one DataForSEO Google Maps SERP task. The runner can use the Standard Queue, Priority Queue, or Live endpoint. Standard and Priority tasks are posted in batches of at most 100 and polled until complete or until the configured timeout.

When CID or place ID is supplied, every supplied identifier must match exactly.
Missing or conflicting identifiers reject the item; there is no name or domain
fallback. Without exact identifiers the runner uses hostname-boundary domain
matching, normalized exact/partial names, then a fuzzy score. CID or place ID is
the preferred production identifier. The standalone report builder also accepts
`--target-cid` and `--target-place-id`; its legacy name-fragment mode remains
available when neither is supplied.
Pass the same target identifiers to `verify_pins.py`. Its HTML check traces each
displayed rank/NR label and projected coordinate to the raw response, in addition
to checking baked circles. If the base-map projection differs from the default
12, pass the same `--zoom` to builder and verifier; this is display zoom, distinct
from each provider request's measurement zoom.

All scanner, report and verification ranks use organic Maps `rank_group`.
`maps_paid_item` and other explicitly non-Maps item types are excluded, as are
`maps_search` items flagged `is_paid: true`. Legacy items without a type may be
used only with a valid group rank. Absolute rank is preserved in item metadata,
never substituted for missing group rank: two ads before the first organic Maps
result make its absolute position 3 while its organic rank remains 1. Paid-only
responses do not create target ranks or populate observed organic rank sequences.

## Measurement contract and calibration

Both runners expose `--search-this-area` and `--no-search-this-area`. The default
is explicitly **true**, preserving the provider default previously obtained by
omitting the parameter. `search_places` remains false by default. CSV columns
`search_this_area` and `search_places` accept true/false (also 1/0, yes/no, y/n);
a non-empty cell overrides the CLI default, including an explicit false.
Unknown boolean text is rejected before execution.

API zoom is validated from **3 through 21**. Grid radius controls point spacing;
zoom controls the requested viewport, so they are independent. Compare scans
only with the same settings. A calibration point can return a very short list
at a tight zoom and a longer list, including the target, at a wider zoom. Neither
observation alone establishes a general geographic visibility boundary.

Provider references, checked 2026-09-19:
[Maps Live parameters](https://docs.dataforseo.com/v3/serp-maps-live-advanced/) and
[Maps task-post parameters](https://docs.dataforseo.com/v3/serp-google-maps-task_post/).
Turning off search-this-area allows results beyond the displayed area. It is a
different measurement, not an automatic correction for an absent target.

The parsed JSON, estimate, Markdown and HTML contain the full runner measurement
settings. Bulk manifests and schema-4 cache fingerprints include viewport,
language/device/domain, method, grid geometry, exact target fields, matching
policy/threshold, competitor limit, organic Maps rank basis, and full SHA-256
verification of all artifacts (parsed JSON, raw requests, provider responses, Markdown,
and HTML). Unverified prior cache entries are rejected and not reused.
HTML reports from `tools/local_heatmap_poc.py` render as a labeled square schematic of
approximate local east/north distances with explicit extent; `--map-image` is accepted on
the CLI for backward compatibility, but unregistered supplied imagery is ignored by the
renderer (registered cartography uses `tools/strategy_report.py` with `map.basemap`).

## Point states and denominators

| State | Meaning |
|---|---|
| `found` | A matching target has a numeric returned rank. |
| `not_returned_depth_reached` | Target absent; returned ranks cover 1 through requested depth. Still a statement about this response, not a universal rank assertion. |
| `not_returned_incomplete` | Target absent from a shorter or discontinuous returned list. |
| `empty_results` | Provider returned no items: success with an empty result array, or explicit status 40102 `No Search Results.`. |
| `no_organic_results` | Provider returned items, but all were paid or outside the organic Maps result type. |
| `provider_error` | Task did not report success. |
| `missing_result` | No task was mapped to this coordinate. |

Each parsed point retains total returned item count, organic item count, and
observed organic group-rank positions. No
missing rank is relabeled `20+`. Empty, failed, category-excluded and absent-target
responses do not establish an absence of market demand. Reports retain planned
point counts and disclose state counts rather than silently dropping these cells.
Status 40102 is terminal empty in both Live aggregation and queue polling, not an
API failure. Other non-success statuses, including 40101, remain errors. The
verifier accepts explicit empty results and fails on provider-error responses.

`solv` and `visible_share` describe observed top-3/top-10 shares among eligible
points. A point is eligible when the target has a returned rank, or the returned
rank sequence covers the entire relevant cutoff. Each share includes its explicit
eligible denominator. Zero eligible points yields JSON null, not zero visibility.
These conditional shares can be biased by excluded points and must not be read
as whole-market estimates. `not_found_points` counts nonempty absent-target
responses only; empty and error counts are separate. Average rank remains
conditional on the target being found. Short/empty scans receive a calibration
verdict instead of an outreach-opportunity claim.

## Normalized observation contract

The strategy report engine (`tools/strategy_report.py`) and adaptive collector (`tools/adaptive_geogrid.py`) consume and produce a normalized observation contract across lanes:

```json
{
  "query_id": "service",
  "lat": 40.0,
  "lng": -75.0,
  "rank": 4,
  "state": "found",
  "returned_count": 20,
  "depth": 20,
  "sampled_at": "2026-09-01T12:00:00Z",
  "source": "synthetic-fixture"
}
```

- **Five core states:** `found`, `not_returned`, `error`, `empty`, `unmeasured`. Only `found` records have a positive integer rank; all other ranks are `null`.
- **Actual depth vs. requested depth:** In observation records, `depth` records the contiguous count of organic ranks actually observed starting at 1, not requested depth. Optional `requested_depth` tracks provider depth separately. Legacy runner depth reflects requested settings rather than verified completeness. A short or discontinuous list cannot establish absence at deeper cutoffs.
- **Measured denominator:** `measured = found + not_returned`. Top-3 and Top-10 shares use the measured denominator exclusively. Empty, error, and unmeasured points are excluded from rank shares and reported separately.
- **Duplicate rejection:** Duplicate coordinates within the same query lane fail validation rather than silently distorting denominators.

## Strategy report engine architecture

`tools/strategy_report.py` implements an offline, configuration-driven report generator (`requirements-report.txt`):

- **Letter page copy-fit contract:** All content elements (titles, captions, body copy, tables, legend bands, and maps) align strictly to a unified 516 pt column with 48 pt left and right margins on standard Letter pages (`PAGE_W=612, PAGE_H=792, MARGIN=48, COLUMN=516, MAP_W=516; main registered street maps default to 452 pt high, schematic and full-extent appendix maps to 410 pt; map.height_pt optionally sets the main map height from 410 through 480 pt`).
- **Measured vertical flow:** Headings, captions, maps, and commentary are arranged with explicit layout bounding boxes (minimum 12 pt after title, 16 pt after caption) to prevent text clipping or overlap.
- **Combined service pages:** Short service summaries are kept on the same page as the corresponding map, using a compact one-line native text legend band and readable typography (10.5 pt body, 14 pt leading). Continuation pages are used only when extensive tabular data or narrative cannot remain legible on a single page.
- **Compact native text legend band:** Rank status thresholds and missingness definitions are rendered as a compact native text legend band (`ReportBody` font in PDF) directly below the map figure, eliminating blurry rasterized legend stamps.
- **Schematic coordinate maps vs. local basemaps:** By default, map figures are generated as schematic coordinate maps displaying distance guide rings, cardinal orientation axes, coordinate bounds, and rank pins without external map services or APIs. An optional locally georeferenced raster basemap image (`map.basemap` with `path`, WGS84 `bounds`, `crs`, and mandatory source `attribution`) can be supplied in the configuration. The renderer resamples and reprojects the image to the bounding box.
- **Supporting full-extent appendix:** When distant sentinel probes or outlier points force useful near-core ranks into an overly tight cluster, the main view focuses on the calibrated near-core while an appendix renders the complete sampled coordinate envelope.
- **Neutral distance guides:** Concentric distance rings use alternating translucent neutral bands and readable boundaries. They are geographic distance references, not service boundaries. The top-level center_kind can be business (default) or market; market mode requires center_label and visibly discloses that the reference is not a verified physical business location.
- **Offline release verification (`tools/release_smoke.py`):** An end-to-end offline smoke runner executes three standalone report examples (`urban-dentist`, `rural-mobile`, `georeferenced-mobile`) with `--proof` and `--require-pdf-qa`, runs an 86-row adaptive collector replay (`examples/adaptive/sample.json` + `replay.json`), generates a handoff report from those observations (four validated PDFs in total), and verifies zero network calls and passing QA digests into `runs/release-smoke/`.

Report display copy normalizes em dashes before rendering. PDF QA rejects any surviving em dash in extracted text. Optional regular, bold and title font paths allow a light title face without bundling proprietary fonts. See [Client report acceptance policy](REPORT_ACCEPTANCE.md) for visual review and real-business acceptance requirements.

## Adaptive sampling collector architecture

`tools/adaptive_geogrid.py` implements an offline-first adaptive sampling framework:

- **Offline-first planning:** Running without execution flags calculates the coordinate lattice, geometry, and cost ceiling without network requests.
- **Synthetic replay:** `--replay <replay.json>` simulates provider responses deterministically for reproducible testing.
- **Sector exploration (`adaptive8sectors`):** The collector acquires a complete base grid across all query lanes before evaluating sectors. Outward shell expansion proceeds per compass sector.
- **Clean-negative stopping:** A sector stops expanding only when two complete consecutive shell layers at `negative_depth` are verified clean-negative across all lanes, followed by an outer sentinel probe. A positive sentinel reactivates that sector.
- **Bounded stop vs. absence:** Stops are recorded as `sampled_stop` (bounded sampling complete), never as proof of zero market demand or geographic competitor absence.
- **Atomic reservation ledger:** Per-task cost reservations are recorded before network calls. Cumulative run ceilings prevent overspending even under unexpected provider responses.
- **Collector provenance and revision v2 (`adaptive-geogrid-v2`):** Fingerprint revision is bumped to `adaptive-geogrid-v2`. Earlier v1 acquisition directories fail closed and are incompatible.
- **Response SHA digest vs. raw retention:** The collector hashes each received provider response in full using SHA-256 (`provenance.response_sha256`) and records it in the ledger and observations. Raw responses are **not retained** (`response_retained=false`), so arbitrary provider fields, tags, callback URLs, or exception text are not copied into outputs. Replay from retained raw responses is not supported for this adapter (synthetic replay uses `--replay <replay.json>`).
- **Atomic run directory allocation:** Prevents same-second or same-query output collisions across concurrent executions.

## Entity resolution and search surface separation

- **Domain is an intake seed:** A website domain is an intake clue, not authoritative business identity. Always resolve verified coordinates, physical address, and exact Google Maps CID or Place ID. When exact IDs are provided, matching requires 100% agreement with no name fallback.
- **Search surfaces are distinct:** Google Maps ranks (`rank_group`), Google Search local-pack items, and organic website rankings are distinct search surfaces. A Maps rank is not a website ranking, traffic metric, or lead count.

## Cost model

The September 2026 documented DataForSEO base rates used by 0.1.x are:

- Standard Queue: $0.0006 per Maps SERP page.
- Priority Queue: $0.0012 per Maps SERP page.
- Live Mode: $0.0020 per Maps SERP page.

The estimator multiplies those rates by the number of grid coordinates and by `ceil(depth / 100)`. Other paid request parameters may add multipliers that this release does not model.

The direct runner estimates by default. Raw-query execution requires `--diagnostic`; use `tools/study.py` for researched studies. Paid execution requires both `--execute` and a sufficient `--confirm-cost-usd` value. The bulk runner checks the total pending cost first, and every child scan also receives its own calculated ceiling.

## Coordinates

The grid is an odd square lattice centered on the supplied latitude and longitude. Radius is the center-to-edge distance, not the full grid width. Longitude spacing is latitude-adjusted with cosine scaling; polar coordinates at ±90 degrees are rejected.

## Storage

Run artifacts are local files. Raw output may include public business fields, task IDs, request coordinates, and other provider data. Run folders are ignored by Git. The bulk cache is a JSON index and should not be treated as concurrent or transactional storage.

## Browser studio

The studio is a static Vite application. Leaflet renders the map and OpenStreetMap supplies the default tiles from the exact policy endpoint, `https://tile.openstreetmap.org/{z}/{x}/{y}.png`. The map shows linked OpenStreetMap attribution. Rank pins use a canvas layer so a 17 x 17 grid remains responsive. The studio itself never calls DataForSEO and cannot spend credits.

Set `VITE_MAP_TILE_URL` and `VITE_MAP_TILE_ATTRIBUTION` at build time to use another tile provider. The operator is responsible for that provider's licence, attribution, traffic, and caching requirements. legends-geogrid does not prefetch or package map tiles.
