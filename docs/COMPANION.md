# Competitive map companion

The browser is a shared visual workspace alongside an agent conversation. Run
`pnpm dev` and open the local URL. The original studio remains at `/legacy.html`;
existing generated battlefield consoles remain untouched.

The default view uses the bundled historical pizza sample. In development, a private
`runs/current-study.json` containing `{"study":"/runs/<study>/companion-study.json"}`
can select the active local study. Explicit study URLs take precedence; the pointer
is never included in the production build. **Open study** imports
a `geogrid-battlefield/v1` or `geogrid-companion/v1` JSON model locally in the browser. Nothing is uploaded.
With the development server, `?study=/runs/<study>/battlefield/battlefield-model.json`
opens a saved local study. Private run data is not included in production builds.
Production builds support local file import.
Fresh competitive collection and export are described in [COMPETITIVE_SAMPLING.md](COMPETITIVE_SAMPLING.md).

## Map backgrounds

The **Map source** selector above the map offers original and inverted
OpenStreetMap, plus OpenFreeMap Fiord, Dark, Liberty, and Positron.
The default **OpenStreetMap · Legends dark** treatment dims the inverted map
to 68% brightness with 85% saturation, retaining colored roads, parks and water.
It affects only the background tiles, leaving ranking colors and labels intact.
The original inverted map remains available as a separate choice. OpenFreeMap
uses MapLibre WebGL, loaded only when selected. Its original style colors are
preserved. Changing a background preserves the business, query, coordinates,
zoom and ranking evidence. The choice persists locally and in `basemap=`.
Failed sources leave the previous background in place, with a persistent retry
and OpenStreetMap choice. A failed initial load explicitly says the background
is unavailable; it never presents an empty background as successful.

**Google Maps · Streets**, **Dark**, and **Satellite + labels** are interactive
Map Tiles API backgrounds in the same map, with the same overlays and navigation.
Set server-only `GOOGLE_MAP_TILES_API_KEY`, restricted to Map Tiles API, in the
local Vite server environment. Google API access and billing must be enabled.
The browser receives an opaque local session ID, never the provider key or token.
Google attribution and viewport copyright remain visible. Sessions are reused;
images are not persistently cached, and failed requests are not automatically
repurchased. These requests can incur Google charges but never purchase
DataForSEO rankings. Vite dev and preview have the local adapter; a static-only
production deployment requires an equivalent authenticated server adapter.
See [BASEMAPS.md](BASEMAPS.md) for setup and limits.

## A strategy map with explainable rules

**Coverage dots** starts enabled. Hollow gray outlines retain the full sampled
footprint when the selected profile is outside the returned top 30; amber dashed
outlines indicate incomplete evidence. Both have transparent interiors. This
option changes visibility only. Historical studies collected with Search this
area enabled display a warning about possible rectangular viewport cutoffs.
See [Search-window policy](SEARCH_WINDOW_POLICY.md).

- **Rankings** is the default and shows the selected business's observed ranks for
  one query. Ten saturated colors run from pure cyan (#00ffff) at 1 through
  green to pure yellow (#ffff00) at 10, with evenly spaced hues. Top-ten opacity falls evenly from
  100% at rank 1 to 75% at rank 10. Rank 11 switches to pure red at 25%
  opacity; ranks 12–30 retain pure red and fade evenly to 2% at rank 30.
  Translucent mode multiplies top-ten opacity by 45% (45% to 33.75%) while preserving the red scale.
  Diamond gradients blend the same colors and opacity without a second alpha multiplier.
  Hollow stop signs mean confirmed absence from the top thirty; dashed stop signs
  mean incomplete evidence. Earlier depth-20 absences do not prove top-30 absence.
  Rank-one cells keep their cyan faces and have a prominent halo with eight staggered white
  sparkles around their corners on a 3.6-second cycle, only in the Rankings lens. Coordinate-based phases stagger neighboring
  cells. The separate overlay canvas updates at no more than twenty frames per
  second and never redraws the basemap, base data fills, or diamonds. Hidden tabs
  pause it; reduced motion and cells below three pixels use a static halo and sparkles. Both halo and sparkle textures are generated once
  and reused across all visible cells.
  Markers contain no text; hover or click for the actual result.
- **Local leaders** (the factions lens) identifies the first-ranked business at each search origin.
  The saved shortlist contains the primary business and nine rivals. **All observed**
  exposes the full retained field, searchable by name, address or profile ID in
  pages of 25. Search expands beyond the shortlist. These are observed listings,
  not all verified direct competitors. Selecting any profile changes its Rankings
  and Strike zones maps. Recurring winners (three or more first places) use business colors;
  All winners includes even single-point winners. Both modes ignore shortlist or
  business address. Smaller winners stay hollow, except the selected profile.
  The Local leaders business panel orders these profiles by first-place count.
- **Citadels** are supplied business locations, shown as diamonds in Local leaders
  and a small ring for the selected business in Rankings. Estimated
  locations are omitted. A supplied coordinate is not independently verified by
  this viewer and does not establish a territory of dominance.
- **Strike zones** are observed ranks 4–10. They invite investigation; they do
  not predict an easy ranking improvement or prescribe an SEO action.
- **Location** shows the returned organic results for a selected map point.
- **Study** explains evidence states, metrics and limitations.

The competitive leaderboard orders all profiles by selected-query top-three
coverage, descending, then by top-20 visibility points (21 minus rank at each
location). Equal scores share a position. The primary badge and highlight never
pin the primary business above better performers. Changing queries recalculates
the order. Positions refer to the full observed field even when the list is
filtered to the fixed shortlist or search results. Metrics and leaderboards are
cached for each immutable study/query; the UI does not render hundreds of rows.

Top 3 coverage is a fraction of sampled locations, not market share. Average
rank excludes locations where the business was not found. Incomplete results,
empty responses and failures remain distinct from confirmed absence at the
requested depth. Map space between samples remains unmeasured.

A competitor's useful footprint may extend beyond the current grid. Expand with
complete rows and columns at the same spacing and measure every added origin
for every query. Retain irregular exploratory samples as separate studies; they
do not define a continuous market boundary.

## Working with an agent

**Copy context** prepares the selected business, query, metrics, and location
results for the existing conversation. This viewer does not contain a second
chat client or purchase ranking searches. Selecting an enabled Google background
does make billable map requests through the local server.

A browser-connected agent can also use:

```js
GeoGrid.getState()
GeoGrid.setQuery('q2')
GeoGrid.selectBusiness('F01')
GeoGrid.selectPoint('r4c8')
GeoGrid.setView('factions')
GeoGrid.context()
GeoGrid.loadStudy(model)
```

Query, business, location, and lens are reflected in the URL. A local file
import must be reopened after a reload; its contents are not stored or included
in the URL. Saved study URL loading is limited to the same origin.

## Verification

`pnpm check` runs the existing Python suite, build, dependency audit, doctor,
dry-run and report smoke checks. `node --test tests/study-model.test.js` checks
the display adapter's identity, rank, evidence-state and metric behavior.

Map tiles require connectivity and retain OpenStreetMap attribution. Street-map
loading failures display a notice. Font loading has system-font fallbacks.

## Theme and pane sizing

The companion defaults to near-black surfaces, including native controls, tooltips and
scrollbars. A filter darkens and desaturates the existing OpenStreetMap tiles; the geographic
basemap, labels and attribution remain available.

Desktop and embedded panes size to their own dynamic viewport height. The header
stays in place and only the evidence panel scrolls. Short windows reduce surrounding
spacing and omit the footer. At widths of 700 CSS pixels or less, the layout stacks
with a sticky header and a single document scroll, preserving map height.

The study overview refits when the map resizes. Once you pan, zoom or inspect a
near miss, your chosen view is preserved. **Fit study** restores the overview and
automatic fitting.

## Regular grids and exploration

Regular square studies display equal-sided stop signs without text. Every marker
uses 30% of the shared geographic grid spacing and scales with zoom, including
below one pixel, without a minimum-size overlap. All eight sides are equal.
Hover or select a stop sign for its actual ranking. The square collection window can reveal an irregular
ranking pattern without changing the coordinate matrix. Exploratory samples remain
at their real locations and are explicitly labeled as irregular sampling.

A diamond at the intersection of each four neighboring stop signs blends their
colors using a continuous four-corner gradient, with each diamond edge exactly
the length of a stop-sign edge. Unranked stop
signs have no interior fill; their gradient contributions are transparent too.
Thin outlines retain the sampled locations while streets show through.
Colored stop signs, unranked stop signs and diamonds use pure-black outlines
at 50% opacity. Translucent mode changes their colored fills, not the outlines.
Diamonds are visual interpolation, not additional searches or predicted ranks; corners touching incomplete evidence
remain unfilled. **Gradient diamonds** toggles this treatment, enabled by default
for regular grids in Rankings. **Translucent markers** reveals more of the streets.
The companion displays miles only, including old links with `units=km` and saved
metric preferences. There is no unit switcher. Stored geographic coordinates and
provider distances retain their original units; only the presentation converts.
**Distance rings** shows subtle 1, 2, 5 and 10 mile guides around the selected
business (the primary business in Local leaders). Rings have thin outlines and
no fill. Small labels hide as you zoom out.

Wheel input accumulates into a target zoom while animation is in progress;
fractional zoom eases toward that target at the cursor. Old street tiles remain
visible underneath the replacement tiles until they load and fade in. Reduced
motion preferences disable the easing and tile fade.

Raster basemaps use Leaflet's nearest integer tile level and allow scaling between
levels. Preserve the readable size of baked-in OSM labels: do not request finer
levels solely to eliminate pixel enlargement on high-DPI screens. That experiment
made labels too small and was reverted at the owner's request. Smooth zoom and
tile crossfades remain enabled; OpenFreeMap vector styles are an alternative.

Local leaders defaults to Recurring winners: at least three first places for
the selected query. All winners colors every identified first-place profile;
missing first-place evidence stays distinct. The coverage choice persists in
the URL (`leaders=all` or `leaders=recurring`). The selected profile is an explicit
exception. A hollow point identifies a smaller winner; hover shows its name and
win count. It does not mean the area is vacant. Supplied business coordinates
are retained for all observed profiles, including outside the study radius.
Every qualifying base gets a matching diamond. Bases more than two miles beyond
the circle edge get a dashed connector to the center of their largest connected
winning patch (four-neighbor adjacency at the recorded spacing). Inside and
nearby-outside bases get no connector. These lines do not imply routes, service
areas or additional measurements. Missing coordinates are labeled and never
inferred. The explicit Fit circle + leader bases control reveals outside bases
without automatically shrinking the scan on every query change. Selecting a
leader fits its base and largest patch. This uses saved results, not paid calls. Unavailable first-place evidence uses an
amber dashed outline. Strike zones remains a ranks-4–10 filter for the selected
business, not a prediction of effort, demand, or achievable ranking gains.

The optional `study_views` field contains `{label, url}` entries for related
same-origin saved studies. The footprint selector loads each independently; it
never merges denominators or moves observations. Each file needs its own evidence
timestamps. Local file imports without this field work as before.

## Linked strategy workspace

Strategy room is an optional panel, toggled from the app header. At 1,200 CSS
pixels and wider it docks beside the map, initially sharing the width equally.
Drag the separator to resize, use Left/Right when it is focused, or double-click
(or press Home) to restore the even split. The preferred split is saved locally.
Minimum panel widths preserve readable controls. Expand switches to the focused
Strategy view; Split view restores the dock. Smaller windows use the focused
view automatically and return to the dock when widened.

While docked, selecting a service/area matrix cell updates the map immediately.
Rival comparisons and investigation links keep the panel visible. Query changes
on the map synchronize the strategy selection. Selecting a measured location
shows its area and a location/rank context line in Strategy room, with raw results
in the map's Details drawer. Details is optional while docked so it does not
permanently consume map width. Hide strategy restores the original map layout.
Neither docking nor resizing changes observations, sampling, rank colors, or
manual map zoom. Existing evidence URLs retain their query and region state.
For DPI-scaled panes between 900 and 1,199 CSS pixels, Split view remains an
explicit option in the focused view. Below 900 pixels the focused view protects
readability. The compact matrix scrolls horizontally while service labels stay
visible, and it preserves its scroll position when a cell is selected.

## Campaign recommendations and business-title findings

**Campaigns** separates agent-researched campaign options from spatial ranking
filters. A prepared option names the business objective, evidence, proposed work,
launch requirements, and outcomes to measure. It is a recommendation, not proof
of customer demand or work already published. **Read plans in Strategy room**
opens the wider view; ranking-pattern controls remain available below the plans.
Plans may legitimately recommend further diagnosis when the data does not yet
support an intervention. Never invent additional campaigns to satisfy a count.

**Keyword stuffing** evaluates business names/titles only. Its default scope is
the union of recurring Local leaders across all queries: at least three first-place
results in any query. Titles do not depend on the selected map keyword. A
selected-keyword scope is optional, and updates both the summary and case list.
Cases show disputed words, captured branding, sources, contrary evidence and
the next agent action. A source discrepancy is not a confirmed Google policy
violation. Metadata-only names are explicitly labeled as unverified trading names.
See [BUSINESS_NAME_REVIEW.md](BUSINESS_NAME_REVIEW.md).

Both research types can follow a study-only URL through a same-origin sidecar:
`companion-study.attachments.json` beside `companion-study.json`. The manifest
must match the study's `evidence.plan_sha256`:

```json
{
  "schema": "geogrid-study-attachments/v1",
  "study_plan_sha256": "<the saved plan hash>",
  "name_review": "../research/name-review.json",
  "campaign_research": "../campaign-research.json"
}
```

Explicit `name_review=` and `research=` URLs take precedence. Data adapters also
check profile identity and query text; a different client's findings cannot be
silently substituted. Serve the study, manifest and research together. Importing
a bare JSON file does not carry research attachments, and private `/runs/` files
are never bundled into a public build.


### Local-leader identity and color separation

A cached study-wide graph joins different first-place winners at neighboring
origins (including diagonal neighbors) across every query. A deterministic
saturation-ordered assignment favors large minimum OKLab color differences
between neighboring winners, with weighted boundary contrast as a tiebreaker.
Colors remain stable across query and coverage-mode changes for the same study.
There are more profiles than readily distinguishable colors: distant profiles
may reuse colors, and universal perceptual uniqueness is not promised.

Stable study-local L-number identifiers appear inside business-base diamonds,
in the business list, and in measured-point hover text. These are identity
labels, not ranks. They may change in a newly collected study. Stop-sign shapes
and ranking-mode color semantics remain unchanged. No extra observations or
paid provider requests are needed. Business locations and far-outside connector
rules apply in both coverage modes.
