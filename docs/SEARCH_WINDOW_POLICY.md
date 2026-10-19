# Search-window policy

The geographic study footprint and the provider's search viewport are different.
A 10-mile circle at half-mile spacing defines where searches originate. Google
Maps zoom and `search_this_area` define the search experience at each origin.
More origins or greater result depth do not remove viewport restrictions.

## Default for origin-based visibility

- Use Standard queue, `search_this_area=false`, `search_places=false`, and
  explicit zoom, language, domain, device and depth. No automatic Live fallback.
- Keep a shared, complete regular lattice clipped by geodesic distance to the
  primary business. All queries use identical origins and collection controls.
- One response measures every returned profile, including the primary and nine
  tracked competitors. Separate physical Google profiles stay separate.
- Zoom remains a measurement variable with Search this area disabled. Do not
  describe these results as universal, personalized, organic-web or local-pack
  rankings. Record the chosen zoom and the calibration evidence.
- Never choose settings simply because they produce higher ranks or a prettier
  shape. Compare on-edge and off-edge origins, include all selected queries,
  examine returned businesses and locations, and retain negative findings too.

## Diagnose straight cutoffs before expansion

1. Reconstruct the expected lattice. Reconcile every origin/query pair with a
   saved request, provider task ID, response and exported ranking.
2. Check request coordinates, unique task IDs, response echoes, hashes, errors,
   short result sets and exact CID/place-ID matching. A successful request does
   not necessarily return the requested depth.
3. Select paired origins on either side of suspicious edges. Request the same
   queries with contemporaneous controls: original setting, Search this area
   disabled at the same zoom, and a wider viewport with the original setting.
4. Change only one control per comparison. Save diagnostic runs separately.
   Do not merge their ranks into the production study or retry ambiguous POSTs.
5. If the restriction excludes otherwise returned businesses, recollect all
   origin/query pairs under a single calibrated setting. Preserve the old run
   as a viewport-restricted archive, with a warning in the companion.
6. Verify remaining edges against raw responses. Turning off Search this area
   permits results beyond the displayed area; it does not guarantee every
   business appears or that Google has no other spatial selection behavior.

## Execution guard

The competitive collector defaults an omitted `search_this_area` to false.
Before purchasing new searches, both the competitive collector and study run
entry point reject restricted searches unless the plan explicitly contains:

```json
{
  "collection_policy": {
    "intent": "viewport",
    "rationale": "The specific displayed-area question this study answers."
  }
}
```

A diagnostic can instead record `diagnostic.purpose` and
`diagnostic.source_scan`. Previously queued tasks can still be retrieved without
repurchasing or altering their settings. Historical reports remain readable.
These exceptions are deliberate study choices, not defaults.

## Coverage is distinct from rank

Show all measured origins with the Coverage dots option, enabled initially.
Ranked locations retain their rank colors. A hollow neutral outline means the
business was absent from a complete top-30 response. An amber dashed outline
means incomplete or missing evidence. Both keep a transparent interior. Hover
and selection expose the underlying results. Unmeasured locations never become
NR. Never invent or interpolate rank observations to fill blank areas; gradient
diamonds remain decorative blends.

Count complete, short, empty and failed responses separately. Do not repeatedly
buy short responses merely to force 30 listings: Google may return fewer. Use a
bounded diagnostic when incompleteness affects the decision.

## Regression evidence

On 2026-10-18 a regional HVAC diagnostic used four existing origins, four
queries and three controls (48 Standard requests, $0.0288). At `r_025_023`,
a recurring competitor profile was absent from all four top-30 responses
with zoom 13 and Search this area on. With that restriction disabled, it
returned at 5 (HVAC contractor), 14 (air conditioning repair), 8 (air
conditioning contractor), and 10 (furnace repair). A zoom-12 restricted control
also returned it. This supports a search-window artifact, not missing origins.

Private evidence stays in the local run folder
`runs/example-study/viewport-diagnostic/`; credentials and private
raw response archives must not be committed.

Provider reference: [Google Maps Standard task parameters](https://docs.dataforseo.com/v3/serp-google-maps-task_post/).
