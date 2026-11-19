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
