# GeoGrid viewer model (geogrid-viewer/v1)

`geogrid-viewer/v1` is a small, self-contained description of one geo-grid scan. It is the input for the GeoGrid report viewer when a host app wants to show a scan without shipping the full study file. The viewer also accepts the existing `geogrid-companion/v1` study (see `docs/COMPANION.md`).

The machine readable definition is `docs/geogrid-viewer-v1.schema.json` (JSON Schema 2020-12). A small example is `examples/viewer-lean-fixture.json`.

## Conventions

- Shares are fractions from 0 to 1 (0.28 means 28 percent). The viewer prints them as percentages.
- Ranks are whole numbers where 1 is best. `null` means the business was not found for that point.
- Coordinates are decimal degrees (WGS 84).
- The viewer ignores fields it does not know. Missing optional fields never cause an error.
- Business names and labels are treated as plain text and escaped before display.

## Shape

```json
{
  "schema": "geogrid-viewer/v1",
  "business": { "name": "string", "lat": 0, "lng": 0 },
  "scan": { "id": "string", "keyword": "string", "gridSize": 5, "radiusM": 4000, "createdAt": "ISO 8601", "device": "mobile" },
  "points": [ { "row": 0, "col": 0, "lat": 0, "lng": 0, "rank": 3, "label": "Rank 3", "heat": 0.9 } ],
  "scores": { "foundShare": 0, "solv": 0, "visibleShare": 0, "arp": 0, "atrp": 0, "centerRank": 1 },
  "zones": { "rings": [ { "id": "ring-1", "label": "Inner ring", "points": 8, "foundShare": 1, "avgRank": 2.4 } ], "quadrants": [] },
  "competitors": [ { "name": "string", "top3Share": 0, "outrankShare": 0, "avgRank": 0, "presenceShare": 0 } ],
  "delta": null,
  "zoneCompetitors": [ { "zoneId": "ring-1", "top": [ { "name": "string", "presenceShare": 0, "top3Share": 0, "outrankShare": 0 } ] } ]
}
```

## Fields

`business`: the business the scan is about. The map marks this location and draws the distance rings around it.

`scan`: `id` identifies the scan, `keyword` is the search phrase, `gridSize` is the number of points per side, `radiusM` is the scan radius in meters, `createdAt` is when the scan ran, and `device` is the device type searched from.

`points`: one entry per grid point. `row` and `col` locate the point in the grid, `lat` and `lng` place it on the map, `rank` is the business rank at that point or `null`, `label` is the text shown when a point is hovered or selected, and `heat` is an optional number from 0 to 1 reserved for hosts that want to carry their own intensity value. The viewer colors points by `rank` using the shared GeoGrid rank palette: ranks 1 to 10 run cyan to yellow, ranks 11 to 30 are red with fading opacity, and `null` draws as a dark not found cell.

`scores`: the summary numbers for the scan.

- `foundShare`: share of points where the business appears.
- `solv`: share of local voice, computed by the host.
- `visibleShare`: share of points where the business ranks in the top 3.
- `arp`: average rank across the points where the business was found.
- `atrp`: average rank across all points, with not found points counted at the host's chosen penalty rank.
- `centerRank`: rank at the center point of the grid.

`zones`: statistics for areas of the grid. `rings` are bands by distance from the business, `quadrants` are the four compass quarters. Each zone has an `id`, a `label`, the number of `points` it holds, its `foundShare`, and its `avgRank`.

`competitors`: the aggregate table across the whole grid. `presenceShare` is the share of points where the competitor appears, `top3Share` is the share where it ranks in the top 3, `outrankShare` is the share of points where it ranks above the business, and `avgRank` is its average rank where it appears.

`delta`: `null` when there is no earlier scan. Otherwise an object with `scores` holding the change for each score (current minus previous; share changes are fractions, so 0.08 means 8 percentage points), optional `previousScanId` and `previousCreatedAt`, and optional counts of grid points that `improved`, `declined` or stayed `unchanged`. For ARP, ATRP and center rank a lower number is better, so a negative change is shown as an improvement. Score changes may also sit directly on `delta` without the `scores` wrapper.

`zoneCompetitors`: optional. For each zone id, the leading `top` businesses inside that zone. When present, the viewer shows a zone picker above a small table.

## What the viewer shows from this model

With every capability flag off and only the fields above, the viewer shows the rank pin heatmap on the basemap, the score cards, the ring and quadrant tables, the aggregate competitor table, the change since the last scan, and, when supplied, the per zone competitor table. See `docs/VIEWER.md` for mounting and security notes.

# Full study with every ranking (geogrid-companion/v1, viewer 0.2.9)

For the per-point rankings and the competitor panel, send the full study `geogrid-companion/v1` and mount it with `capabilities.perPointListings: true`. The machine readable definition is `docs/geogrid-companion-v1.schema.json`; a complete example with 100 ranked listings per point is `examples/viewer-companion-depth100-fixture.json` (regenerate it with `python scripts/make_viewer_depth_fixture.py`). Everything below is additive: studies that omit these fields open exactly as they did in 0.2.8.

## What the viewer shows

- Location tab: pick a point and the viewer lists that point's captured results, ranks 1 to 20 first. When more than 20 were captured a `Show all N` control lists them all and `Show top 20` collapses it again. The primary business is marked, and when it ranks beyond 20 the viewer says so with its real position (for example `ranks 37 here`) and pins that row under the top 20.
- Competitors tab: every other business seen at the measured points for the selected query, most frequent first. Each row shows appearances out of measured points, share of points and average rank where it appears. The first 25 are listed with a `Show all N` control. Selecting a row recolors the map to that business, so its points stand out. Appearances count every captured position, deep ones included.
- Score cards stay anchored to the top 20 (see `study.score_window` and `lanes[].scores` below), so scans captured at different depths compare the same way.
- Business names, ratings and categories are shown as plain text.

## Fields to send

```json
{
  "schema": "geogrid-companion/v1",
  "business": { "name": "string" },
  "factions": [ { "faction_id": "biz-0", "name": "string", "is_target": true, "lat": 0, "lng": 0, "rating": 4.8, "votes_count": 412, "category": "Plumber" } ],
  "profiles": { "k-3fa9": { "title": "string", "rating": 4.6, "votes_count": 120, "category": "Plumber" } },
  "lanes": [ { "lane_id": "q1", "query": "string", "scores": { "found_share": 0.84, "top3_share": 0.02, "avg_rank": 13.56 } } ],
  "points": [ { "tag": "p_00_00", "lat": 0, "lng": 0, "by_lane": { "q1": {
      "target_rank": 37, "status": "found", "sampled_at": "ISO 8601",
      "top_items": [ { "faction_id": "k-3fa9", "rank": 1 }, { "faction_id": "biz-0", "rank": 37 } ] } } } ],
  "study": { "geometry": "square_grid", "depth": 100, "score_window": 20, "sampling": { "spacing_km": 1, "center": { "lat": 0, "lng": 0 } } }
}
```

- `factions`: must contain the primary business with `is_target: true`. Other competitors may be listed here (to give them an address or position) or only appear in `top_items`.
- `faction_id`: an opaque string key. The viewer never parses it, links it or assumes it is a provider id. Use any string that is stable within one report: a short index, or an HMAC of the stored identity. It is matched across points, queries, `factions` and `profiles` by exact string equality. Items that carry a provider listing identifier (`cid` or `place_id`) are matched the older way instead; leave those out.
- `top_items`: every captured result for the point, best first, as `{ faction_id, rank }`. Send as many as were captured (up to 100 or more). `rank` is a whole number from 1. Items may also carry `title`, `rating`, `votes_count` and `category` inline; `profiles[faction_id]` is the compact alternative that avoids repeating them at every point. Inline values win over `profiles`.
- Display fields: `title` (or `name`), optional `rating` (number 0 to 5), optional `votes_count` (review count) and optional `category` (text). A competitor with no name shows as `Unnamed profile`.
- `target_rank`: the primary business's actual rank, including beyond 20, or `null` when it was not found in the captured results. With `study.depth` set, a `null` with status `not_returned_depth_reached` reads as `Not in returned top 100`.
- `study.score_window` (integer, normally 20): score cards count only ranks 1 to this number, even when `top_items` goes deeper. Leave it out and every captured rank counts, as in 0.2.8.
- `lanes[].scores`: optional precomputed scores for the primary business in the score window. `found_share` and `top3_share` are fractions from 0 to 1 and `avg_rank` is the average rank where found. When present the viewer shows these numbers as given and does not recompute them from ranks, deeper or not. Competitor cards use the score window.
- Other fields of the study (for example `generated_at`, `location`, `evidence`, `study.sampling`) behave as in `docs/COMPANION.md`. Fields the viewer does not know are ignored.

## Mounting

```js
const viewer = GeoGridViewer.mount(el, study, { capabilities: { perPointListings: true } })
viewer.selectPoint('p_00_03') // optional: open a location's rankings, throws for an unknown tag
```

The Location and Competitors tabs appear only when `perPointListings` is `true`. On a point click the embedded viewer opens the Location tab. The lean `geogrid-viewer/v1` model has no per-point listings.
