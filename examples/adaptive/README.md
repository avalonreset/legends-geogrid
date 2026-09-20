# Adaptive multi-query collector

Run from the repository root with Python 3.10+. These commands need no credentials and make no network calls:

```sh
python tools/adaptive_geogrid.py --config examples/adaptive/sample.json
python tools/adaptive_geogrid.py --config examples/adaptive/sample.json --replay examples/adaptive/replay.json --output-dir runs/adaptive-replay
python -m unittest discover -s tests -p test_adaptive_geogrid.py -v
```

The sample is synthetic. Replace its identity, center and query lanes with your own private configuration before collecting. Keep private configurations and outputs in ignored `runs/` or another private directory. No setup, authentication lookup or paid request occurs in planning/replay mode.

Live collection uses the existing runner's `DATAFORSEO_USERNAME` and `DATAFORSEO_PASSWORD` environment authentication. Both flags are mandatory; choose your own reviewed ceiling:

```sh
python tools/adaptive_geogrid.py --config runs/my-config.json --output-dir runs/my-acquisition --execute --confirm-cost-usd 1.00
```

The first adapter supports the **Live** Maps endpoint, one request per origin/query, using `local_heatmap_poc.call_dataforseo_live_task`. It does not use external kits or queue submissions. Live estimates include the shared runner's depth multiplier. Search Places is fixed false. Provider prices may change: the estimate is not a provider-enforced billing limit. Each request reserves its estimate before submission; a higher reported charge counts immediately and stops further calls if it exhausts the ceiling.

## Configuration

`sample.json` lists every setting. Unknown fields fail validation.

| Field | Meaning |
| --- | --- |
| `center` | Latitude strictly inside the poles, longitude -180 through 180. Entire bounding square must remain valid. |
| `queries` | 1–50 `{id,keyword}` lanes; unique ASCII IDs. Every selected origin gets every lane. |
| `targets` | 1–50 alternative exact identities: `{cid?,place_id?,domain?}`. Every supplied field within an identity must match. IDs are strings. Domain uses the runner's canonical hostname normalization, with exact host equality (no subdomain or similar-name fallback). The reported rank is the best organic rank across matching alternatives. |
| `spacing_km` | Lattice step, 0.01–100 km. Uses the existing runner's local latitude/longitude approximation. |
| `starting_grid` | Odd width, 1–101, of the complete shared base. |
| `max_shell` | Square half-width in lattice steps, from the base half-width through 50. Corners lie sqrt(2) times farther than the half-width. |
| `strategy` | `adaptive8sectors` (default), `dense`, or `sparse`. |
| `depth` | Requested provider depth, 1–700. |
| `negative_depth` | Required contiguous organic ranks for a usable negative, 1 through requested depth; defaults to 20. |
| `provider_zoom` | Search viewport zoom, 3–21; independent of geometry. |
| `display_zoom` | Presentation metadata only, 0–22; never sent to the provider. |
| `language_code`, `device`, `se_domain` | Provider language, desktop/mobile device and search domain. |
| `search_this_area` | Explicit boolean, default true. |
| `max_calls` | Cumulative attempts, including errors, sentinels and backfill; 1–1,000,000. |
| `timeout_seconds` | Per Live request timeout, 1–600 seconds. |

Adaptive selection starts only after the entire base has been attempted. The outer base shell can count as the first negative layer. A one-point base cannot count as a sector layer. Each sector then acquires complete Chebyshev shell sectors until it has two consecutive clean-negative layers across all lanes. A farther central-ray sentinel must also return clean negatives across all lanes before `sampled_stop`. Any positive sentinel reactivates the sector and fills all cells on that sector's sentinel shell, reusing the already collected probe. Short lists, rank gaps, errors, empty responses and missing observations never qualify as negatives. Inconclusive sectors stop as unresolved for review.

`dense` acquires the complete bounded square. `sparse` completes the base then samples eight rays on every remaining shell. Its termination is `sampled_bounds`; it makes no full-sector stopping claim. All strategies describe sampled evidence only, never geographic absence between or beyond measurements. A bound reached before a sentinel remains `bounds_reached`.

## Report interface and resume

`plan.json` includes settings, base origins, maximum tasks and estimated Live cost. Adaptive maximums assume the full square; actual selection depends on responses. `manifest.json` contains the acquisition fingerprint, accounting, per-sector states, events, completeness counts and termination reason. `observations.json` is a JSON array, also emitted as `observations.jsonl`:

```json
{"query_id":"pizza","lat":40.0,"lng":-100.0,"rank":2,"state":"found","returned_count":20,"depth":20,"sampled_at":"2000-01-01T00:00:00+00:00","source":"synthetic-replay","x":0,"y":0,"requested_depth":20,"observed_ranks":[1,2,3],"clean_negative":false}
```

The abbreviated `observed_ranks` above illustrates the field only; actual output includes all observed ranks. `depth` is the largest **contiguous observed organic rank starting at 1**, not the requested depth or raw item count. Rank is null or a positive integer. State is `found`, `not_returned`, `error`, `empty`, or `unmeasured`. A target with a missing organic group rank is an error, never a negative. Ads do not contribute to ranks or returned counts. `source` is `dataforseo-live`, `synthetic-replay`, or `unmeasured`. Errors include a safe error code; raw provider errors and credential values are not written.

Every selected origin appears for every query, including explicit `unmeasured` rows after a budget stop. `complete_common_base` and `complete_selected_origins` mean acquisition attempted, including errors; inspect `state_counts` and sector states for usable evidence. The collector admits a whole origin only when its remaining lanes fit the cumulative ceiling. An interruption or an unexpectedly higher actual charge can still leave a partially measured origin.

Domain-only identities intentionally identify the domain's listings as a group; provide CID/place ID to restrict a multi-location business to a specific branch. An invalid provider charge stops collection as `unknown_reported_charge`, including on resume. Existing acquisition artifacts without their ledger are rejected to avoid accidentally starting a second billed acquisition in the same directory.

Reuse the same config, mode and output directory to resume. The entire canonical config, algorithm revision, adapter identity and replay contents are fingerprinted; changed settings require a new directory. Raising only `--confirm-cost-usd` resumes a budget-limited run. `max_calls` is part of the immutable config. Accounted spend sums max(estimated reservation, reported charge) per attempted request, including probes, failures and previously interrupted requests. This is conservative, and can exceed reported spend. Replay records simulated accounting, never actual spend.

`state.json` is an atomically replaced, integrity-checked ledger; do not edit it. The run holds `.collector.lock` to prevent concurrent writers. After a killed process, verify the process has stopped before manually removing a stale lock. Requests interrupted after reservation remain charged conservatively and become `error` on resume; they are never automatically retried. To repeat failed measurements, deliberately start a separate acquisition directory and account for that separate run's budget. Normal provider errors are retained on resume too. Exit code 2 indicates refusal, budget stop, unresolved evidence or interruption; inspect artifacts before deciding the next action.

## Synthetic frontier tests

Replay has an optional `default` and `observations` keyed `query_id:x:y`. Outcomes support `state`, `returned_count`, optional `rank`, `cost_usd` and `sampled_at`. A full provider `response` can replace the outcome fields to exercise malformed data, identity conflicts and rank gaps. Missing keys without a default yield provider errors. Default timestamps are fixed for reproducibility. The bundled replay makes a positive east sentinel reactivate its sector, then reaches the configured bound without inventing an absence certificate.

The CLI supplies the maximum estimated ceiling for replay when none is given. Pass `--confirm-cost-usd 0.02` to exercise a hard stop and repeat with a larger ceiling to exercise resume. Replay/live caches cannot mix. Plan mode writes only `plan.json`; it never changes the acquisition ledger or observation artifacts.
