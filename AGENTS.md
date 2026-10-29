# legends-geogrid agent instructions

legends-geogrid is an open-source google maps rank checker. Preserve that
lowercase positioning and the approved Legends banner style.
Interface chrome uses the Legends red, black, and white palette: neutral black
surfaces, white/gray type, and red interaction accents. Do not tint the dark
theme purple or blue. Evidence colors remain distinct from brand decoration.

## Setup and dependencies

- Offline report: install `requirements-report.txt`, then run the README's
  synthetic report example. No provider credentials or API spending are needed.
- Browser demo: `pnpm install --frozen-lockfile`, then `pnpm dev`.
- Fresh scans: install `requirements-dataforseo.txt`. This installs the public
  [legends-dataforseo](https://github.com/avalonreset/legends-dataforseo)
  dependency. Run `python tools/geogrid_doctor.py --dataforseo` before collection.
  Release 0.2.2 works with the pinned DataForSEO dependency or `legends-dataforseo`
  `v0.1.6+` installed via `cto-legends install legends-dataforseo`.
  Do not install an MCP server or copy a second HTTP/authentication client.
- Optional optical signage accelerator: when investigating business-name discrepancies
  (`tools/business_name_review.py photos`), check whether `legends-jev` (`v0.2.0+`)
  is installed via `cto-legends status` or `python tools/geogrid_doctor.py --jev`.
  The workflow operates standalone without `legends-jev`, or accepts `--jev` to run
  ~200ms System One optical recognition over GBP and multi-vantage Street View photos.
- Credentials: `DATAFORSEO_LOGIN` (or `DATAFORSEO_USERNAME`) and
  `DATAFORSEO_PASSWORD`. Never print, commit, or embed credentials in reports.

## Research and collection

Read `docs/STUDY-RECIPE.md`, `docs/START_A_STUDY.md` and `docs/STUDY_CONTRACT.md` before collection.
Default to 3-5 distinct evidence-backed search themes, one representative query
per theme, following `docs/QUERY_SELECTION_POLICY.md`. Fewer requires a cited
explanation and focused scope; never pad with synonyms.
Given only a business, research and select queries from website, public GBP and
DataForSEO evidence; do not ask users to supply keywords by default. Use
`tools/study.py` for researched studies. Raw runners require explicit `--diagnostic`.
Read `docs/START_A_STUDY.md` before paid collection. Establish business identity,
query, location, language and the decision being studied. Estimate first. Paid
scans require both `--execute` and `--confirm-cost-usd`; retain these gates.
Use DataForSEO for provider access and the GeoGrid runners for sampling/caching.
Never describe advisory estimates as a provider-enforced billing limit.
Standard queue is the default for Maps ranking studies, including new studies
derived from historical Live plans. Live requires an explicit user request and
the collector's `--allow-live` flag. A desire for detail or permission to spend
credits does not imply permission to choose Live. Persist queued provider task
IDs and retrieve them without repurchasing. Never fall back from Standard to Live.

Regional visibility studies use `search_this_area=false`. A dense circular set
of origins does not prevent Google's individual search viewports from creating
rectangular cutoffs. Calibrate search controls across suspected edges before
bulk collection; preserve changed controls as a separate run, never patch ranks
from different settings into one study. Intentional viewport experiments need
an explicit purpose and remain labeled as such. See
`docs/SEARCH_WINDOW_POLICY.md` for the diagnostic and acceptance procedure.

## Verification and publishing

Run `pnpm check` for code changes after installing report dependencies. Test the
shared transport with fixtures; no paid call is necessary for ordinary tests.
Preserve full basemaps and attribution. Inspect every final report page.
Keep user run folders and private reports out of commits. Maintain the distinction
between measured ranks, missing evidence, business hypotheses and recommendations.

## Competitive companion policy

Use a complete regular lattice centered on the primary business, clipped to the
requested geographic radius, for the main map. Radius and sample spacing are
separate settings. Never substitute a square footprint for a requested radius.
Keep one primary Google Business Profile and retain every observed profile.
The nine-rival shortlist is a default focus set, never a cap on analysis or
selection. Expose the full observed field with search and bounded lists; distinguish
observed listings from service-qualified rivals. Read `docs/BATTLEFIELD_INTELLIGENCE.md`
for competitor lenses, spatial investigation, and evidence limitations.
Separate physical listings with distinct CIDs remain separate even
when their names or domains match; show addresses to distinguish repeated names.
The competitive leaderboard sorts every profile, including the primary, by
selected-query top-three coverage, then top-20 visibility points. Equal scores
share a position. Primary highlighting must never pin or promote its position.
Collect and preserve organic Maps ranks through 30, including non-shortlisted profiles.
Local leaders release policy: default to Recurring winners (three or more
first-place observations for the selected query), with All winners exposing
every observed winner. Never restrict eligibility by shortlist or base address
inside the study radius. The selected profile may remain highlighted below the
threshold. Hollow points mean filtered smaller winners, not vacant territory;
unavailable first-place evidence remains distinct.
Use study-wide neighbor-aware colors and matching study-local L-number IDs on
business diamonds, list entries and hover evidence. Keep these stable across
queries and coverage modes; do not promise globally unique colors. Preserve
stop-sign search markers. Show supplied base coordinates outside the circle;
never invent a base from its rankings. Connect bases to their largest winning
cluster only when more than two miles beyond the circle edge. Keep fitting
outside bases an explicit control. See docs/COMPANION.md for exact behavior.
GeoGrid is an agent-operated intelligence workflow with a visual evidence companion.
Agents perform research, synthesize case files, and attach the results to the
study. Do not delegate the investigation to the owner through import/export
wizards, evidence-entry forms, or reviewer checkboxes. The Keyword stuffing mode
is a read-only findings brief; navigation and source inspection remain available.
Business-name review defaults to recurring Local leaders plus individually
matched historical or owner-supplied title leads. Recurring means at least three
first-place observations in any study query, including
businesses based outside the radius. Business titles are independent of the selected
map keyword. Keep summary counts and cases in the same scope; selected-query-only
review is an explicit optional filter. Investigate the union individually;
retain singleton winners in an optional all-observed scope. A supplied naming
lead does not need any first-place wins: match its exact CID to the study and
show its measured appearances, radius relationship, old title and current title.
Optional concern confidence is an individually reasoned 0–5 ordinal judgement,
not a violation probability. Bind it to the exact CID/current title and fresh
sources; missing evidence remains unscored. Distinguish pending
research from individually assessed but insufficient evidence. Limit this feature
to business names/titles, not reviews or unrelated abuse. Refresh individual exact-CID
profiles through Standard queue and compare public brand evidence. Follow
docs/BUSINESS_NAME_REVIEW.md: lexical signals are research prompts, not violation
probabilities; legal entity names and DBA filings do not alone determine Google's
real-world naming rule. Preserve counterevidence, source timestamps and hashes.
Keep automated screening, analyst source review and user-reviewed drafts distinct.
Never automatically submit name edits or competitor complaints. Missing, stale
or unavailable evidence cannot justify a correction.
Companion policy: ten saturated shades from pure cyan (#00ffff) at rank 1,
through green to pure yellow (#ffff00) at rank 10, with evenly spaced hues. Top-ten opacity falls evenly from 100% at rank 1 to
75% at rank 10. Rank 11 is pure red
(#ff0000) at 25% fill opacity. Ranks 12–30 retain pure red and fade evenly to 2%
at rank 30. Translucent mode multiplies top-ten opacity by 45% but preserves the red
scale. Diamonds blend the same colors and alpha; never multiply alpha twice.
NR beyond 30 requires complete top-30 evidence. Older depth-20 absences cannot
certify absence from the top 30. Incomplete evidence remains distinct.
Markers are equal-sided stop signs of uniform geographic size on the lattice.
Keep the four-corner gradient diamonds between them; these blend display colors
and are never additional observations. Rings have outlines only. See
docs/COMPETITIVE_SAMPLING.md and docs/COMPANION.md for selection and display rules.

## Street maps

Real report observations default to OpenFreeMap street maps (no API key).
Install `requirements-basemaps.txt` and run `python -m playwright install chromium`;
check `python tools/geogrid_doctor.py --reports --basemaps` before rendering.
See `docs/BASEMAPS.md`. Do not silently switch a failed real map to a schematic.
Synthetic examples remain offline. Google imagery is optional and requires
`GOOGLE_MAPS_API_KEY` plus explicit `--allow-google-maps-charge`; never expose the key.
The companion's Google map sources are interactive Map Tiles API backgrounds,
not Static Maps previews. Use server-only `GOOGLE_MAP_TILES_API_KEY` restricted
to Map Tiles API; preserve panning, zoom, evidence overlays and Google attribution.
Never substitute a snapshot when interactive access fails. Explain the exact
configuration gap and preserve the selected study. See `docs/BASEMAPS.md`.
