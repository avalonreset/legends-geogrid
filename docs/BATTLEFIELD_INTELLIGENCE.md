# Full-field intelligence policy

Version 1: descriptive evidence and investigation planning. This is not a
validated ranking-gain or revenue prediction model.

## Start with the owner, retain the entire field

The primary business anchors the decision and the sampling circle. Preserve every
observed organic listing through the requested depth at every origin and query.
One primary plus nine rivals is a focus shortlist, never a collection or analysis
limit. Users must be able to search and select other observed profiles without
buying the same searches again. Keep separate GBP identities separate, including
different locations of the same brand.

The observed field is not a census of businesses physically inside the circle.
It contains profiles returned by the configured searches. Some results may have
mixed intent, unrelated categories, hidden addresses or locations outside the
circle. Do not equate a category regex match with a qualified direct competitor.
Record qualification as observed-only, category-supported candidate, or
service-verified rival, with the supporting evidence and date. Missing research
remains unknown. Do not silently discard an inconvenient first-place winner.

Provider coordinates without an addressed, verified location may represent a
service-area center. Never use them alone to claim an actual remote establishment
or plot a verified physical-business marker. An addressed rival outside the
circle can still compete for customers inside it.

## Use three competitor lenses

1. **Regional visibility:** count first-place, top-three, top-ten and top-thirty
   appearances by query on the same sampled footprint. Use the full common
   denominator and show incomplete evidence separately. A percentage is sampled
   location coverage, not search demand, click share or market share.
2. **Direct competition:** count which profiles outrank the primary at the same
   origin and query. Report the denominator, distinguishing primary-returned
   observations from complete top-depth absences. Do not assign NR a fictional
   exact rank. Conditional head-to-head comparisons describe that subset only.
3. **Local competition:** for each candidate group of origins, report its actual
   first-place winners and profiles ahead of the primary. A modest regional rival
   can be the important local opponent. Never limit this calculation to the
   focus shortlist.

The current export's regional shortlist uses sum(max(0, 21-rank)), with its
documented tie breakers and category candidate filter. Preserve and name that
formula when displaying historical shortlists. Do not call it "the best nine"
without specifying the decision and metric.

Do not silently combine these lenses into an opaque opportunity score. Report
query-specific results first. Equal-query averages, if used, are descriptive and
are not demand or revenue weights. For primary-centric interpretation also show
distance bands: 0–2 miles (inclusive), >2–5 miles, and >5–10 miles for a ten-mile
study. The outer band has more sampled area; that is not evidence of more demand.

## Turn locations into investigation areas

Classify measured primary ranks per query:

- 1–3: existing top-three foothold to understand and maintain.
- 4–10: near-top-three observations to investigate.
- 11–30: weaker observed visibility requiring a different hypothesis.
- Absent from a complete top 30: not observed at that depth, not empty territory.
- Missing, pending or incomplete evidence: unknown, never a ranking failure.

For a regular lattice, connect directly adjacent measured origins (north, east,
south and west) within the same band and query. Retain singleton components.
Report the member origin IDs, representative measured origin, measured rank
distribution, distance from the primary and local rivals. Never claim that the
entire polygon between points has been measured. Do not bridge missing cells.
On irregular sampling, skip lattice component claims unless adjacency has been
explicitly defined and justified.

Cross-query recurrence can identify places worth reviewing across several
services. Report which queries and how many support the pattern; do not call
the queries independent confirmations or infer sales value from recurrence.

Order investigation lists by transparent descriptive fields such as component
size and recurrence, retaining the underlying counts. "Near top 3" is a filter,
not an assertion that ranking gains are easy.

## Convert a candidate into an owner action

### Interactive campaign workbench

The companion's **Campaigns** lens always analyzes the primary profile, regardless
of the last competitor selected. Selecting a rival returns to its Rankings view.
The following lenses are deterministic, cached views of the saved evidence:

- **Territory overview:** top-three, ranks 4–10, ranks 11–30, outside top 30 and
  incomplete evidence, with up to three featured investigation components.
- **Near top 3:** orthogonally connected primary ranks 4–10.
- **Service gaps:** selected-query ranks 4–10 where at least one other studied
  query reaches the top three at the same origin. Show the compared queries and
  ranks; this is a contrast, not proof of a content deficiency.
- **Expansion frontier:** only ranks 11–30 directly adjacent north/east/south/west
  to a complete same-query top-ten observation. Do not highlight an entire
  connected weak-ranking region merely because one edge touches the top ten.
- **Hold top 3:** existing top-three observations, not proven persistent territory.

Area cards expose measured members, representative results, median rank, distance
range, and the three most frequent other top-three profiles within that area.
Their counts use area locations as denominator and include all observed profiles.
Each card can focus the map or open all-query results at a representative origin.
Singleton observations remain visible and labeled separately. Selection and lens
are shareable in the URL. Copy context includes the selected area's members and
rivals for agent follow-up.

The engine requires depth 30, thirty unique ranked identities, successful status
and agreement between target rank and the returned items. It reconstructs expected
radius-grid coordinates using the collector's exact Earth radius (6371.0088 km);
missing cells are unknown and never bridged. Unknowns must not become invented NR
or a market opportunity. Irregular or incompatible geometry is unavailable.

Optional private website research uses `research=<same-origin JSON URL>`, schema
`geogrid-campaign-research/v1`. Bind it to the primary CID and exact query text,
not query IDs alone. Keep checked website facts separate from hypotheses and
next checks. Existing city/service links do not certify that a selected component
is inside that city's boundary. Do not bundle client research in public code.

Before recommending spending or content for an area, establish:

- The primary actually offers the service and can serve the area.
- The query reflects the intended customer need, with mixed intent disclosed.
- Demand, commercial value and operational fit have evidence or remain unknown.
- The proposed action addresses an observed gap in the website, GBP or customer
  experience. A colored patch alone does not justify a location page, new office,
  ads budget or fabricated service-area claim.
- Where decisions are material, repeat selected measurements with the same
  controls using Standard queue and compare like-for-like origins and queries.

Keep a short owner brief: existing foothold, candidate expansion areas, actual
local opponents, supporting observations, missing business evidence and next
investigation. Avoid giving the owner a 653-row spreadsheet as the entire product.

## Provenance and acceptance

Derived intelligence must identify the input file/hash, controls, observation
window, sample/query counts and metric version. No paid calls are required to
recompute it from retained data. Preserve raw results and original exports.
Tests must cover censored absence, incomplete evidence, separate location
identities, adjacency gaps and changing the focus shortlist without losing
profiles or altering observations. Check responsiveness with the full measured
directory and bound the number of DOM rows.

A 10-mile regional HVAC study is the regression motivation: 653 observed
profiles and 163 distinct first-place winners versus a ten-profile focus set.
Its private raw evidence and derived audit stay under the local run folder.

## Offline geographic analysis

```powershell
python tools/battlefield_intelligence.py --study runs/example/scan/companion-study.json --output-dir runs/example/intelligence
```

This writes JSON and a Markdown investigation report without provider calls.
The analyzer requires a declared regular circular lattice, reconstructs expected
origins, and validates full rank/identity evidence before assigning investigation
bands. It preserves unknowns for missing or contradictory evidence. Cross-query
focus means ranks 4–10 on at least `min(3, query count)` queries; the threshold is
recorded in the output. The report is an investigation aid, not a commercial
priority score. Input SHA-256 and exact source controls accompany the results.

## Strategy room: service and regional comparison

The [strategy engine](../src/strategy-engine.js) computes regional summaries and
head-to-head comparisons from the same immutable normalized study used by the map.
It reuses the strict completeness checks in
[territory intelligence](../src/territory-intelligence.js). The
[strategy room](../src/strategy-room.js) presents these summaries; its matrix is
an investigation aid, not a demand or revenue forecast.

For a ten-mile study, nine nonoverlapping regions partition the measured circle:

- `core`: origins within two miles, inclusive.
- `inner-ne`, `inner-se`, `inner-sw`, `inner-nw`: directional sectors beyond two
  miles through five miles, inclusive.
- `outer-ne`, `outer-se`, `outer-sw`, `outer-nw`: directional sectors beyond five
  miles through the study radius.

`all` is an additional whole-study summary, not a tenth disjoint region. Smaller
studies cap the bounds at their actual radius and omit bands beyond that radius.
For studies larger than ten miles, the outer band continues to the declared
radius. Direction is relative to the primary origin; points on an axis belong
to its north/east side (`y >= 0`, `x >= 0`). These labels do not establish city
boundaries, customer populations, or commercial service areas.

### Denominators and competitor lenses

Each region/query cell reports complete and unknown observations separately.
Top-three and top-ten percentages divide by that cell's **complete** origins.
Zero complete observations yields an unavailable percentage, never zero
visibility. Missing expected origins remain unknown. Rank 4–10, returned
top-30, service-gap and frontier counts retain the previously defined evidence
rules. The matrix shows counts alongside percentages so a small or incomplete
region cannot look convincing through percentage alone.

Regional rival coverage is the arithmetic mean of each query's top-three
coverage percentage within the selected region. Queries with no complete
observations are excluded from that mean; eligible queries have equal weight,
not demand or revenue weight. The denominator and per-query counts remain
available. Ordering uses mean coverage, then top-ten appearance count, then
profile ID.

Local pressure counts appearances ahead of the primary **only where the primary
ranks 4–10**, pooled across all studied query/origin pairs in the selected region.
Its denominator is those near-top-three pairs, not every search in the region.
Ties use the number of appearances ahead when the primary was returned, then
profile ID. Primary-returned comparisons have their own denominator. The
regional leader and the local blocker can therefore legitimately differ.
Neither metric estimates ranking difficulty. All observed profiles can
participate; the nine-rival shortlist never limits these calculations.

### Head-to-head evidence

`strategyMatchup(model, queryId, rivalId, regionId)` compares exact profile IDs,
retaining CID/place identity and addresses. Separate locations of the same brand
remain separate opponents. Every selected origin has one state:

- `primaryAhead` or `rivalAhead`: both returned, with the stated observed rank
  comparison.
- `primaryOnly` or `rivalOnly`: only that profile appears within a complete top
  30. The absent profile's exact rank is unknown.
- `neither`: neither appears within a complete top 30; this is **not** an exact
  rank tie or vacant territory.
- `unknown`: evidence is missing, incomplete, or contradictory.
- `tied`: reserved for equal observed ranks; current strict unique-rank evidence
  normally prevents this state for distinct profiles.

No absent profile receives an invented rank of 31. A displayed matchup leader
means more complete origins with a better observed position or exclusive
top-30 presence. It does not imply greater sales, market share, or an easier
campaign. Equal win counts yield no leader.

### Owner workflow and implementation contract

1. Select a service and region in the matrix; compare top-three and top-ten
   reach, using the visible complete/unknown counts.
2. Compare regional leaders with local pressure, then open a specific profile
   matchup or inspect the region on the map.
3. Open measured origin evidence and compare the other studied queries. Review
   separately checked website assets before interpreting a service gap.
4. Open an investigation and turn it into a campaign only after service fit,
   demand, capacity, job value, and the proposed intervention have evidence.
   Copy the brief for agent follow-up; retain measured baseline and success
   criteria before making changes.

`strategyIntelligence(model)` returns regions, the query matrix, and up to three
deterministic investigation cards. Current triggers are core service gaps,
connected adjoining frontier observations, and a difference between regional
and near-top-three rival leadership. Each card retains its query, origin IDs,
evidence counts, next check, and limitations. `rivalPressure(model, regionId)`
exposes the two competitor orderings and their denominators. Cards are
hypotheses, not a validated campaign priority score.

Results are cached by immutable model; matchups additionally key by query,
profile, and region. They require no extra paid API requests and do not alter
raw or exported evidence. Replacing the study model creates a fresh analysis.
Tests in [strategy-engine.test.js](../tests/strategy-engine.test.js) cover
partitioning, unknown evidence, query weighting, same-name profile separation,
head-to-head censorship, and evidence-backed investigation triggers.
