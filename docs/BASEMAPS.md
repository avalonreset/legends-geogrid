# Street maps and optional Google Maps

## Interactive Google companion maps

The companion map selector supports **Google Maps · Streets**, **Google Maps ·
Dark**, and **Google Maps · Satellite + labels** as interactive basemaps.
Panning, wheel zoom, ranking overlays, leader bases, and study selection work on
the same map. Google is no longer a snapshot-only selector option.

Enable **Map Tiles API** in a billing-enabled Google Cloud project. Set
`GOOGLE_MAP_TILES_API_KEY` on the server, restricted to `tile.googleapis.com`.
The adapter can fall back to `GOOGLE_MAPS_API_KEY` only if that key permits Map
Tiles API; a working Static Maps key alone does not establish this. Keep server
keys out of `VITE_*`, URLs shown to users, reports, and browser bundles.

`pnpm dev` and `pnpm preview` install the same local-only adapter. For a hosted
deployment, mount `createGoogleTilesMiddleware` behind an authenticated
same-origin server boundary adapted for that host; static file hosting alone
cannot provide paid Google maps. Never deploy a public unauthenticated billing
proxy. Selecting a Google source (including reopening a saved Google selection)
uses Google-billed tile requests. OSM remains the unconfigured default. There is
no silent Static Maps substitute or switch to another provider on failure.

Provider sessions are reused until expiry; browser URLs contain local opaque
session IDs, not the API key or provider session token. Tiles are streamed with
`no-store`, with no disk cache or offline collection. Viewport copyright and
the official Google Maps logo remain visible. Dark mode uses Google's styling
parameters, not an inversion filter. Existing Static Maps report support is
unchanged. See Google's [Map Tiles documentation](https://developers.google.com/maps/documentation/tile/2d-tiles-overview)
and [attribution policy](https://developers.google.com/maps/documentation/tile/policies).

Real strategy reports now default to **OpenFreeMap street maps**, with no map API
key or account. Ranking measurements still come from DataForSEO. Changing the
background provider does not change ranking accuracy.

OpenStreetMap is the geographic dataset. OpenFreeMap is a service that hosts maps
built from that data. Leaflet/MapLibre are display libraries. The browser studio
already uses OpenStreetMap; the Python report workflow now acquires its own maps.

## One-time setup for real PDF reports

```sh
python -m pip install -r requirements-report.txt -r requirements-basemaps.txt
python -m playwright install chromium
python tools/geogrid_doctor.py --reports --basemaps
```

On Linux, missing browser system libraries may require the official
`python -m playwright install --with-deps chromium` installation command.
Playwright runs Chromium headlessly with no visible terminal or browser window.
No Google credential is required. Internet access to the pinned MapLibre assets
on jsDelivr and OpenFreeMap's map resources is required during acquisition.
Only geographic view requests go to the map service; business names, keywords,
ranking records, and DataForSEO credentials are not sent to it.

Run the usual report command:

```sh
python tools/strategy_report.py --config report-config.json --output-dir reports/my-study --proof --require-pdf-qa
```

The scan runner now writes `report-config.json` beside `parsed-grid.json`, so its
saved results can be passed directly to this command without recollection.
The scan HTML opens an interactive OpenFreeMap street map. Its coordinate-only
schematic is tucked inside a clearly labeled diagnostic disclosure.

The default report theme uses a dark street style; `"theme": "light"` uses a
light style. Source-map colors are preserved. Synthetic example reports still
run offline as labeled coordinate diagrams unless a street provider is selected.

## Choose a map provider

In your report configuration:

```json
"map": {"provider": "openfreemap"}
```

- `auto` (default): use supplied imagery if configured; otherwise use free street
  maps for real observations and schematic diagrams for synthetic fixtures.
- `openfreemap`: fetch a free street map. No API key or account.
- `google`: fetch Google Maps Static imagery; requires separate Google setup and
  explicit `--allow-google-maps-charge` on each report invocation.
- `supplied`: use your existing georeferenced local `map.basemap` image.
- `schematic`: explicitly request a coordinate-only diagram; no street imagery.

A command-line `--basemap` overrides provider selection for all report lanes.
There is **no silent fallback** from either street provider to a schematic or
another provider. A failed acquisition leaves no published PDF. Saved scan data
is retained, so retrying a map does not repeat or repay ranking collection.
Scan HTML displays a map-load error and hides the incomplete map if loading fails.

## Optional Google Maps imagery

Choose Google for its familiar cartography and branding, not different rankings.
This is optional; the free maps are usable for client reports.

1. Create/select a Google Cloud project and enable billing.
2. Enable **Maps Static API** and create an API key with appropriate restrictions
   for server-side Static Maps requests. A browser-referrer-only key is not suited
   to the Python renderer. Configure billing alerts and quotas in Google Cloud.
3. Set `GOOGLE_MAPS_API_KEY` in your process environment. Never put it into report
   JSON, a committed env file, URLs in documentation, or screenshots.
4. Run:

```sh
python tools/strategy_report.py --config report-config.json --output-dir reports/google-study --basemap google --allow-google-maps-charge --proof --require-pdf-qa
```

Google charges are separate from DataForSEO; DataForSEO's spend confirmation does
not cover Google. This flag is consent to the map requests, not a spending cap.
There is one request per distinct extent/size/theme within a build; cropped views
and full-extent appendices may need separate requests. No automatic retries or
persistent Google cache are implemented. Provider key errors are redacted.

The renderer retains the entire Google image, logo, and copyright in place.
It protects the bottom credit area from ranking markers. Standard Static Maps
image-size limits mean effective print resolution can be lower than OpenFreeMap;
the QA receipt reports native image resolution. Google imagery remains its
original color regardless of report theme. Check Google's current usage and
printed-output terms for your intended distribution.

Official setup and pricing:
- https://developers.google.com/maps/documentation/maps-static/get-api-key
- https://developers.google.com/maps/documentation/maps-static/usage-and-billing
- https://developers.google.com/maps/documentation/maps-static/policies

## Evidence and attribution

Street acquisition records full Web Mercator image bounds and preserves one
continuous geographic transform. Basemap credits are overlaid in place, never
cut off and reattached. Every final page retains attribution. OpenFreeMap uses
OpenMapTiles/OpenStreetMap attribution, including the OpenStreetMap copyright URL.
Identical map views share one acquisition within the report build. The QA receipt
records the chosen providers and the number of acquisition network requests.
Map requests do not validate the origin or correctness of ranking observations.

Public services can be unavailable. OpenFreeMap offers no SLA; acquisition failures
are reported clearly. The app does not bulk-download OpenStreetMap's community
raster tiles or use those servers as an automated PDF fallback.

References:
- https://openfreemap.org/ (free service, attribution, commercial use)
- https://openfreemap.org/quick_start/
- https://operations.osmfoundation.org/policies/tiles/
