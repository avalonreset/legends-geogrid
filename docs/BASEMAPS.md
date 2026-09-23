# Street maps and optional Google Maps

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
