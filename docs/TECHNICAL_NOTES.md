# Legends GeoGrid Technical Notes

## Rank-data path

Each grid coordinate becomes one DataForSEO Google Maps SERP task. The runner can use the Standard Queue, Priority Queue, or Live endpoint. Standard and Priority tasks are posted in batches of at most 100 and polled until complete or until the configured timeout.

The target business is matched in this order:

1. Exact CID.
2. Exact place ID.
3. Domain containment.
4. Exact normalized name.
5. Partial normalized name.
6. Fuzzy name score above the configured threshold.

CID or place ID is the preferred production identifier.

## Cost model

The September 2026 documented DataForSEO base rates used by 0.1.x are:

- Standard Queue: $0.0006 per Maps SERP page.
- Priority Queue: $0.0012 per Maps SERP page.
- Live Mode: $0.0020 per Maps SERP page.

The estimator multiplies those rates by the number of grid coordinates and by `ceil(depth / 100)`. Other paid request parameters may add multipliers that this release does not model.

The direct runner estimates by default. Paid execution requires both `--execute` and a sufficient `--confirm-cost-usd` value. The bulk runner checks the total pending cost first, and every child scan also receives its own calculated ceiling.

## Coordinates

The grid is an odd square lattice centered on the supplied latitude and longitude. Radius is the center-to-edge distance, not the full grid width. Longitude spacing is latitude-adjusted with cosine scaling; polar coordinates at ±90 degrees are rejected.

## Storage

Run artifacts are local files. Raw output may include public business fields, task IDs, request coordinates, and other provider data. Run folders are ignored by Git. The bulk cache is a JSON index and should not be treated as concurrent or transactional storage.

## Browser studio

The studio is a static Vite application. Leaflet renders the map and OpenStreetMap supplies the default tiles from the exact policy endpoint, `https://tile.openstreetmap.org/{z}/{x}/{y}.png`. The map shows linked OpenStreetMap attribution. Rank pins use a canvas layer so a 17 x 17 grid remains responsive. The studio itself never calls DataForSEO and cannot spend credits.

Set `VITE_MAP_TILE_URL` and `VITE_MAP_TILE_ATTRIBUTION` at build time to use another tile provider. The operator is responsible for that provider's licence, attribution, traffic, and caching requirements. Legends GeoGrid does not prefetch or package map tiles.
