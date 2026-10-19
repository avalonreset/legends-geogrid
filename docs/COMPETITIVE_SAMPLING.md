# Competitive sampling and collection

## Study policy

A completed competitive study retains **one primary Google Business Profile and
every observed profile**, with a default focus shortlist of nine rivals. The
shortlist is not a cap on analysis or selection. Different physical locations with distinct profile
IDs remain separate competitors even when their names and websites match.
Display addresses for repeated names. A shared brand does not prove cannibalization.
Discover rivals from the shared searches, then freeze the shortlist across queries.
The export ranks eligible profiles by the sum of `21 - organic rank` for ranks
1–20 over every measured origin and query, weighting each equally. Break ties by
top-three appearances, then total appearances, then exact CID. Use returned
business categories and retained profile identity as preliminary service-relevance
evidence; the plan's `competitor_policy.eligible_category_pattern` can filter
candidates but does not establish full business-intelligence qualification.
Selection scores, query contributions, categories and example evidence origins
are included for each rival. If fewer than nine eligible identities are measured,
mark the shortlist incomplete rather than inventing businesses.

This legacy regional score is a declared display default, not a universal answer
to "who matters most to the primary business." Compare per-query regional reach,
head-to-head observations and local competitors in candidate areas separately.
See `docs/BATTLEFIELD_INTELLIGENCE.md`.

Retain **all thirty organic Maps listings** per location when returned, even for
businesses outside the shortlist. Ads are excluded from organic rank. Maps
listings are not three ten-result pages of Google's website search results.
Short/empty provider responses do not prove absence at depth thirty.

Use a complete, regular primary-centered lattice clipped to the requested
geodesic radius for the main map. Expansion adds the lattice locations inside
the new radius at the same resolution and collects them for every query.
Spacing controls density; radius controls coverage. Neither is the provider
Maps viewport zoom. Irregular exploratory samples remain separate evidence. Never move
measured coordinates to fit a grid or paint interpolated rankings as observations.
Preserve researched query wording; changes require new evidence and a separately
identified study. Calibrate query intent and collection zoom before the full scan.

## Regular comparison grid

For a legible primary ranking map, use a regular lattice centered on the primary
business. The exploratory footprint below remains useful as a separate study.
Rows and columns stay aligned; the resulting cyan/green/yellow/red pattern can be irregular
without scattering search origins.

```powershell
python tools/lattice_sampling.py --source-plan runs/competitive-plan.json --output runs/regular-plan.json --size 21 --spacing-km 1
python tools/competitive_collect.py --plan runs/regular-plan.json --output-dir runs/regular-study
```

The planner retains researched queries, business identities and measurement controls.
Spacing is approximate kilometers at the center latitude; longitude intervals remain
constant to preserve aligned columns. A 21 by 21 grid at 1 km spacing spans 20 km
on each side. This is a comparison window, not a proven market boundary.
Review the estimate, then use the existing execute and cost flags. No observations
are relocated or interpolated from exploratory samples. Export carries geometry and
spacing into the viewer.

## Exploratory competitor sampling

`tools/competitive_sampling.py` builds a shared sampling footprint around a primary
business and the rivals identified in a saved battlefield study. This legacy
exploration path does not define the main grid or the current nine-rival shortlist. It preserves
the selected queries from the researched study plan. The planner runs offline.

The default footprint combines:

- Supplied business locations and straight-line connecting probes (Phase 1).
- Preserved prior origins for a newly refreshed shared baseline (Phase 2).
- A 3x3 neighborhood core around each supplied business at 0.65 km spacing (Phase 2).
- Eight compass directional probes per center at 2, 5, and 10 km (configurable via `--sentinel-radii-km`, Phase 3).

Proposed origins within 50 meters merge into one retained coordinate, keeping the actual chosen coordinate. This reduces duplicated planned searches along shared commercial corridors (such as co-located competitors); it never infers reuse or treats historical measurements as fresh. One Maps search at each origin and query measures every business returned there; it does not require buying an identical search separately for each competitor.

These are exploratory candidate probes, not complete boundary claims. They do not certify continuous territory, customer demand, travel accessibility, an outer market boundary, or the ease of improving a rank. Geography is map context; ranking evidence determines observed visibility. Strong rankings at outer probes justify further research. Unsampled gaps remain unknown. An absent business is only confirmed outside the returned depth when all requested organic rank positions are present. Status 'planned_requires_review' indicates provider connectivity, source freshness, and business geographic relevance must be reviewed before live execution.

## Run a study

Live collection requires the configured `legends_dataforseo` Python provider kit.
Planning, export, and tests do not require provider credentials.

```powershell
python tools/competitive_sampling.py --battlefield runs/example/battlefield/battlefield-model.json --study-plan runs/example/evidence/study-plan.json --output runs/competitive-plan.json
python tools/competitive_collect.py --plan runs/competitive-plan.json --output-dir runs/competitive-study
```

Review the estimate and source query plan. The fresh comparative experiment uses
Standard queued Maps collection: depth 30, a calibrated common zoom, desktop, English, google.com,
search_this_area=true and search_places=false. The original query research remains
linked; its earlier measurements are not mixed into the fresh study.

```powershell
python tools/competitive_collect.py --plan runs/competitive-plan.json --output-dir runs/competitive-study --execute --confirm-cost-usd 4 --workers 6
# If status is queued, retrieve saved provider task IDs later without new spending:
python tools/competitive_collect.py --plan runs/competitive-plan.json --output-dir runs/competitive-study --execute --confirm-cost-usd 0 --workers 6
# Export only once status is collected.
python tools/competitive_export.py --run-dir runs/competitive-study
```

Standard is the default, at $0.0006 per normal Maps task at depth 30.
Live costs $0.002 and requires an explicit user request, an explicitly Live plan,
and `--allow-live`. Do not infer that choice from permission to spend credits.
There is no automatic fallback to Live. Normal queue turnaround targets 45 minutes;
provider delays can exceed that. Pending observations are not NR. Task IDs,
submission costs and result envelopes survive process exit; retrieval does not
repurchase completed or pending searches. A `STOP` file in the output directory
stops new submissions at the next batch boundary.

The spending ceiling is a caller-reviewed dispatch budget, not a guarantee about
provider billing. Actual provider cost is recorded, and further dispatch stops if
the next reservation exceeds the remaining budget. On resume, the ceiling applies
to additional spending; the receipt also reports total recorded run cost.

Optional `--phase 1` collects business locations and connecting areas first. Run
again without the phase filter to complete the same frozen plan. Completed exact
requests are reused only from this run. Changed plans, response integrity failures,
provider failures and unresolved reservations stop collection. A timeout is not
retried automatically. Inspect the saved evidence before any recovery; never delete
reservations merely to force another paid call.

The collector saves request files before dispatch, original response envelopes,
SHA-256 receipts, a reservation ledger, normalized observations and report config.
It drains in-flight responses before stopping a failed batch. Source-plan validation
is mandatory for execution. Concurrent writers are excluded by a run lock.

## View and inspect

Open `companion-study.json` in the companion viewer, or serve it locally with:

`?study=/runs/competitive-study/companion-study.json`

The export selects the nine-rival focus set using the policy above, identified by
CID/place ID, and preserves all returned profiles in the observations. The companion
derives its searchable full field from those retained results. The shortlist is fixed across all query views; it is not
a market-share ranking.
Provider timestamps describe observation time; export time is separate.
It contains no speculative vulnerability or opportunity scores.

A coverage percentage is specific to this footprint. Adding competitor-focused
origins changes its denominator, so percentages from different footprints must not
be presented as an improvement or decline over time.

## Verification

```powershell
python -m unittest discover -s tests -p 'test_competitive_*.py'
pnpm test:viewer
```

Tests cover sampling coverage, fresh-task estimates, researched-query lineage,
exact resume, ambiguous requests, provider errors, cost overruns, full-depth result
preservation, and export compatibility. Public sample tests run without private
study files or provider credentials.
