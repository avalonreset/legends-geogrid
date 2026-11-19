# GeoGrid report viewer package

The viewer is a prebuilt, self-contained browser bundle for showing a GeoGrid scan inside another web app. It is built from the same source as the local companion (`src/companion-app.js` and the shared map modules), so the rank pin heatmap and rank palette match.

## Files

| File | Purpose |
| --- | --- |
| `geogrid-viewer.js` | Script. Defines the global `GeoGridViewer`. |
| `geogrid-viewer.css` | Styles, every rule scoped to `.ggv-root`. |
| `geogrid-viewer-worker.js` | MapLibre web worker. Keep it in the same folder as the script. |

Build it with `pnpm build:viewer` (output in `dist-viewer/`). Release archives are `geogrid-viewer-<version>.tgz` and are pinned by the SHA-256 in `SHA256SUMS`.

## Mounting

```html
<link rel="stylesheet" href="/vendor/geogrid-viewer.css">
<script src="/vendor/geogrid-viewer.js"></script>
<div id="report" style="height: 640px"></div>
<script>
  const viewer = GeoGridViewer.mount(document.getElementById('report'), model, {
    capabilities: { perPointListings: false, profiles: false, nameReview: false, campaignResearch: false, strategyRoom: false },
    basemaps: ['ofm-dark', 'ofm-fiord', 'ofm-liberty', 'ofm-positron'],
    defaultBasemap: 'ofm-dark',
    googleSessionPath: undefined,
    attribution: 'OpenFreeMap © OpenMapTiles © OpenStreetMap contributors',
  })
  // later: viewer.destroy()
</script>
```

`GeoGridViewer.mount(el, model, options)` returns `{ destroy() }`. It never reads `window.__GEOGRID_BOOTSTRAP__` or any other page global.

- `el`: an element, or a selector that matches one. Give it a height; the viewer fills it (minimum 480 px).
- `model`: a `geogrid-viewer/v1` object (see `docs/viewer-model.md`) or a `geogrid-companion/v1` study.
- `options.capabilities`: `perPointListings`, `profiles`, `nameReview`, `campaignResearch`, `strategyRoom`. A panel is shown only when its flag is `true`. For a companion study, a panel whose flag is off is hidden and nothing errors when its data is absent. The lean model never shows these panels.
- `options.basemaps`: ids to offer. Default is every OpenFreeMap style: `ofm-dark`, `ofm-fiord`, `ofm-liberty`, `ofm-positron`.
- `options.defaultBasemap`: default `ofm-dark`.
- `options.googleSessionPath`: optional. When set, Google tile entries (`google-roadmap`, `google-dark`, `google-satellite`) are offered and tiles are requested through this same-origin session endpoint. If the session or a tile request fails (HTTP 403, 429, any 5xx, or a network error), the viewer silently returns to the default OpenFreeMap background and hides the Google entries for the rest of the session.
- `options.attribution`: plain text credit for the map. Default is "OpenFreeMap © OpenMapTiles © OpenStreetMap contributors".
- `options.workerUrl`: optional URL for `geogrid-viewer-worker.js` if it is not served next to the script.
- `options.units`: `mi` (default) or `km` for the lean model distance rings.

Unsupported or malformed models throw an `Error` from `mount()` with a short reason.

## Content Security Policy

The bundle needs no inline script and no eval. A strict policy that works with it:

```
default-src 'none';
script-src 'self';
worker-src 'self' blob:;
style-src 'self';
style-src-attr 'unsafe-inline';
connect-src 'self' https://tiles.openfreemap.org;
img-src 'self' data: blob: https://tiles.openfreemap.org;
```

- Script: the viewer script, same origin.
- Worker: `geogrid-viewer-worker.js`, same origin. It must be served with a JavaScript content type.
- Style: the stylesheet, same origin. The generated markup uses a few inline `style` attributes, so `style-src-attr 'unsafe-inline'` is needed. Style changes made by script do not need it.
- Connect: `https://tiles.openfreemap.org` for the vector style, tiles, sprites and glyphs, plus `'self'` for the optional Google session endpoint and tiles.
- Img: `data:` and `blob:` for generated images, `https://tiles.openfreemap.org` for sprites, `'self'` for same-origin Google tiles.
- No raster tiles from `tile.openstreetmap.org`, no web fonts, and no other third party origin.

Note on the worker: the MapLibre GL worker (third party, BSD 3-Clause) contains a script loader that falls back to `globalThis.eval` for a classic script fetched by URL (this is how MapLibre loads its optional right-to-left text plugin). The viewer never asks the worker to load an extra script, so the code path does not run and a policy without `'unsafe-eval'` works. The viewer script and stylesheet contain no `eval` and no `new Function`.
