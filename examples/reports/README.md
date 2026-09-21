# Portable strategy reports

All examples here are **synthetic**, including business identities, observations,
and hypotheses. They are offline demonstrations, not client findings.
Any observation source containing `synthetic` forces the synthetic report label,
even when the config omits or disables it. Mixing those sources with real or
unclassified sources is rejected; use separate reports. The `unmeasured` source
is neutral. `synthetic: true` requires explicit synthetic source labels for any
other records. All non-synthetic reports disclose **user-supplied evidence**:
the renderer does not independently authenticate source labels or origins. An operator may separately audit the acquisition evidence.
Missing or blank source metadata fails validation.

```sh
python -m pip install -r requirements-report.txt
python tools/strategy_report.py --config examples/reports/urban-dentist.json --output-dir .private/release-030/urban
python tools/strategy_report.py --config examples/reports/rural-mobile.json --output-dir .private/release-030/rural
python tools/strategy_report.py --config examples/reports/georeferenced-mobile.json --output-dir .private/release-030/georeferenced
```

Outputs: `report.pdf`, `report.html`, `report-model.json`, `report-qa.json`, and
local map PNGs. No network access occurs. Existing output files are refused;
choose a fresh directory. Output contains the supplied identity and observations:
choose a private output directory for private inputs. Nothing is published.

## Config v1 / collector handoff

Paths resolve relative to the config file. Required keys:

```json
{
  "schema_version": 1,
  "synthetic": true,
  "business": {"name": "Synthetic Example", "location": "Example district", "lat": 40.0, "lng": -75.0},
  "thesis": "Nearby sampled origins may show stronger visibility; test this hypothesis.",
  "objectives": ["Establish an observed baseline"],
  "lanes": [{"query_id": "service", "label": "Example service", "query": "example service near me", "records_path": "observations.json"}],
  "map": {"radius_bands_km": [1, 3, 5]}
}
```

Optional top-level `center_kind` is `business` (default) or `market`.
`center_label` defaults to the business name in business mode; market mode
requires an explicit nonblank label such as `"Synthetic town square"`.
For backward compatibility, `business.lat` and `business.lng` remain the scan
center coordinates in both modes. In market mode they are **not** a verified
physical business base. Cover text, map captions, HTML, normalized model and
map QA ledger identify the market reference; the crosshair and distance rings
are centered on it. Observations retain their exact coordinates. Default
business mode identifies the origin as user supplied, not independently verified.

Supply any positive number of lanes. Each lane accepts exactly one of `records`
(inline list), `records_path`, or `records_paths` (list of paths). Record files
may contain a normalized list or an object with `observations`. A shared list
may mix query IDs; each lane selects its ID. Unknown IDs in inline records fail.
The observation contract is:

```json
{"query_id":"service","lat":40.0,"lng":-75.0,"rank":4,"state":"found","returned_count":20,"depth":20,"sampled_at":"2026-09-01T12:00:00Z","source":"synthetic-fixture"}
```

`state`: `found`, `not_returned`, `error`, `empty`, `unmeasured`. Only found
records have positive integer ranks; all other ranks must be null. Coordinates
are WGS84 degrees. `returned_count` is a nonnegative integer or null (unknown),
`depth` is a nonnegative integer or null; collector depth is contiguous organic
ranks actually observed, including zero. Optional `requested_depth` records the
positive requested depth separately. The legacy adapter also computes `depth`
from the contiguous prefix of saved `observed_ranks`; without that list, depth
is null (zero for empty/unmeasured states). Requested settings are retained only
as `requested_depth`, never promoted to observed completeness. `sampled_at` is an ISO 8601 timestamp
with timezone or null; `source` is a human-readable provenance label (not a
credential). Both fields must be present. Optional `observed_ranks` is a list of
actual positive organic ranks; it must not be synthesized from returned_count.
Duplicates at the same coordinates within a lane fail rather than silently
reweight the denominator. Separate time comparisons into distinct lane IDs.

Existing runner `parsed-grid.json` files (`results` and `measurement_settings`)
also work via a lane records path. The adapter checks any recorded target and
keyword against config, retains organic ranks, excludes irrelevant/no-organic
results as unmeasured, and records absent timestamps as missing evidence. It
uses the already-selected saved rank/status; it does not rerun business matching.
`matched_item`, `top_items`, and raw provider responses are neither consulted
nor exported. Saved rank authenticity still depends on the supplying runner.

Counts are computed per lane, never averaged across differently sampled lanes.
Measured = found + not_returned. Sampled = every supplied record (including
unmeasured planned origins). Top 3 = ranks 1–3; top 10 = ranks 1–10; near miss =
ranks 4–10 inclusive. Shares explicitly use the measured denominator and mean
**observed appearances at valid sampled origins**, not area/market coverage.
Empty/error/unmeasured origins are excluded and counted. A missing target with
no complete observed rank sequence through a cutoff cannot establish absence
at that cutoff; the model reports the unknown count separately. Requested
depth and returned item count alone do not prove sequence completeness.

Optional lane `narrative`, top-level `next_actions`, and `missing_evidence` are
user-supplied copy, labeled accordingly. No commercial recommendations are
invented. Thesis is always labeled a user hypothesis. Automatic next steps are
limited to evidence gaps. Long copy continues at readable font sizes.

## Maps and fonts

US Letter uses fixed 48 pt side margins and a 516 pt content column. Schematic
maps and full-extent appendix maps are 516×410 pt; supplied-basemap service maps
are 516×452 pt. Raster resolution is 216 effective PPI (1548×1230 or 1548×1356).
Geography always uses equal projected x/y scale. Schematics use letterboxing.
Overlay-safe basemap viewports expand around the requested bounds with 16 pt marker
clearance to fill the geographic frame. Images with embedded credits instead retain
their complete extent and use letterboxing when needed; no image strip is detached. This can reveal additional supplied origins. The asset ledger
records both `requested_bounds` and actual displayed `bounds`. Expansion beyond
supported latitude/longitude bounds fails explicitly. Source imagery must cover
the expanded view for edge-to-edge street context; uncovered pixels stay schematic.
QA reports `geographic_plot_pt` separately from asset size and protected credits.
Compact native PDF colored-dot legends and short computed findings stay with normal
service maps on one page. There are no colored vector pills or 564 pt mode.

Automatic extent includes exact observations and business location, with
padding. Optional `map.bounds` or lane `map.bounds`: `[west,south,east,north]`.
An explicit crop reports excluded origins and adds a full-extent appendix.
Extents must not cross the antimeridian and must remain within Web Mercator
latitude limits (±85 degrees); unsupported geometry fails clearly.
Neutral `radius_bands_km` are distance guides, not service areas or performance
boundaries. Only complete rings within the view are drawn; omitted bands are
listed in the detailed appendix/HTML caption and QA receipt. Coordinates are projected without rounding or snapping. Coincident
or dense pins retain their positions; collisions are disclosed, and the HTML
observation ledger provides exact coordinates and states for every origin.

Optional `map.basemap` (also allowed per lane) is a locally supplied image:
`{"path":"map.png","bounds":[-75.1,39.9,-74.9,40.1],"crs":"EPSG:3857","protected_bottom_px":44,"attribution_policy":"preserve-in-place","attribution":"Required source and license credit"}`.
Bounds are WGS84 degrees for the **complete image edges**, including all bottom
rows. Pixels must be north-up and linearly georeferenced in the declared
`EPSG:3857` or `EPSG:4326` CRS. Attribution is mandatory and printed without
truncation. User is responsible for source rights.

Two attribution policies are supported:

- `protected_bottom_px: N` defaults to `attribution_policy: "preserve-in-place"`.
  The whole image is rendered with one geographic transform. Credits stay in
  their original location; the bottom N source rows are protected from overlays.
  No strip is removed, separately resized, or pasted back. The displayed extent
  is the complete image extent, with letterboxing if its projected aspect ratio
  differs from the frame. Supply an image covering the requested bounds with
  enough room for complete marker footprints above the credits. A marker or
  origin overlapping credits or an image edge fails clearly; rings that cannot
  fit are omitted and disclosed. Source-image bounds and protection geometry are
  checked against the final raster.
- `attribution_policy: "separate-caption"` with `overlay_safe: true` declares an
  image suitable for cropping and overlays, with the complete required credit
  suitable for separate caption use. The supplied attribution is printed outside
  the image. Embedded credits are **not** protected in this mode; do not use it
  for a source that requires embedded credit preservation.

### Migrating configurations that detached credits

`credit_strip_px` and `preserve-bottom-strip` are rejected with a migration
message. Their old behavior could splice streets at different scales. Replace
those settings with `protected_bottom_px` and `preserve-in-place`, and supply
bounds for the **entire original image**. Do not simply rename the field while
retaining bounds that exclude the bottom rows: that would misregister markers.
If the source has a separate non-geographic footer, supply a continuous,
fully georeferenced image with credits embedded, or an overlay-safe image using
`separate-caption` as appropriate. The renderer does not guess missing bounds.

Outside image bounds the schematic backdrop remains visible. Without an image,
maps explicitly say **Schematic coordinate map — no street basemap**. No API key
or map provider is required. No roads or geographic detail are invented.

`georeferenced-mobile.json` uses a continuous 1280×704 synthetic EPSG:4326
latitude/longitude graticule, with credits overlaid in the bottom 64 pixels. A
diagonal crosses the protected-area boundary to expose any slicing regression.
It depicts coordinate context only, not real terrain or streets. Regenerate it
with `python examples/reports/make_basemap_fixture.py`. QA records source native
pixels and effective PPI over its projected span (vertical average for
EPSG:4326), as well as final raster pixels/PPI and the actual geographic plot.

Reports use the Jev theme by default: paper background, ink text, blue accent, a holographic header bar, Inter body and title type, and uppercase JetBrains Mono labels. Both fonts ship in `tools/fonts/` under the SIL Open Font License. Set `"theme": "geogrid"` for the original dark theme, which uses ReportLab's bundled Bitstream Vera fonts. Optional `verification_notes` (a list of strings) adds a "How the findings were checked" section and, in the Jev theme, a CHECKED WITH JEV header label. Optional
`fonts: {"regular":"font.ttf","bold":"font-bold.ttf","title":"font-light.ttf","mono":"font-mono.ttf"}`
supplies local Unicode TrueType fonts; `title` and `mono` are optional and otherwise use
`regular`. Supply only fonts you have permission to use and embed; none are
downloaded. Unsupported glyphs fail rather than disappear. Titles are 24/30 pt;
body is 11/16 pt and map findings 10.5/14 pt. Captions/legend are at least 8.5 pt;
pin labels at least 8 pt at final PDF scale. Rank colors are pure green (1–3),
yellow (4–10) and red (11+), with neutral excluded/not-returned markers, distance
band shading and labels. Longer attribution and geometry notes remain in the
evidence appendix; mandatory supplied attribution stays beside the main map.
Em dashes in all PDF/HTML display copy are normalized to spaced hyphens. Raw
identity, query and source strings remain unchanged in the evidence JSON.
PDF QA also rejects any surviving em dash. Text inside supplied raster imagery
cannot be normalized or checked by text extraction: supply compliant map labels
and credit artwork, and visually inspect them. Credits are never edited to hide
or rewrite provider content.

## QA and dependency licenses

Every build reconciles marker indices, ranks, states and counts against visible
observations, recomputes projected coordinates and complete circle/stroke
footprints, validates every closed ring and omitted-band count, and checks the
final raster's marker/ring painted pixels against the validated geometry.
Protected credit pixels are compared with the uniformly resized source strip.
Clipping, missing/modified paint, counts, or credit mismatch fail the build.
This is geometric/raster QA, not OCR or verification of the source geography.
Layout boxes are also checked. If installed, pypdfium2 additionally
checks rendered PDF text bounds, nonblank pages, Letter size, and dark corners;
`--require-pdf-qa` makes its absence an error. `--proof` writes rendered page PNGs.
QA includes hashes, page count, map extents, collision counts and denominator
evidence. A passed bbox check is not a substitute for inspecting cartography.
ReportLab (BSD), Pillow (MIT-CMU), and bundled Bitstream Vera fonts have permissive
licenses. Optional pypdfium2 uses Apache-2.0/BSD-3-Clause; its PDFium binaries have
additional bundled third-party notices. Retain dependency distribution notices.
No PyMuPDF / AGPL dependency is introduced.
