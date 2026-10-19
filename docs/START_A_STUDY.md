# Start a useful GeoGrid study

Start with the [study recipe](STUDY-RECIPE.md) and [study contract](STUDY_CONTRACT.md).
For business-only requests, the agent researches website, public GBP and DataForSEO
evidence and selects queries. Do not ask the user to design the SEO study.

Choose [3-5 distinct evidenced search themes](QUERY_SELECTION_POLICY.md), not
arbitrary keywords. Fewer themes require a supported explanation and focused scope.

## 1. State the decision

Write one sentence: which service, which market, and what decision will change after measurement? Do not promise a website recovery diagnosis from Maps ranks.

## 2. Establish identity and geography

Resolve an exact CID, place ID, or canonical domain. Record the verified business base separately from advertised cities and practical service territory. Private accounts (Search Console, private GBP owner metrics, CRM), profitability figures, and owner interview answers are never required for first use: mark unprovided private inputs as `unknown` and proceed with an explicitly exploratory public study. A market-centered or radial exploratory study is valid when explicitly commissioned and labeled; never present its sampling boundary as a verified customer catchment or profitable dispatch territory.

## 3. Run bounded discovery before a dense grid

Follow [Search-window policy](SEARCH_WINDOW_POLICY.md). Origin-based visibility
uses `search_this_area=false`; radius and spacing do not override a provider
viewport. Compare controls across suspicious straight edges before scaling.
Intentional restricted-window studies require an explicit purpose.

Check branded identity and representative service queries. Where relevant, check organic website visibility separately. Review whether returned competitors actually supply the service. Record result depth, zoom, language, device and search-this-area setting. Run `python tools/study.py query-review --plan <study-plan.json>` (or `--refresh-dir <refresh-folder>`) to verify source observation ages, request/response hashes, service-theme coverage, synonym overlap, accepted/rejected/deferred candidate reasons, and `unknown` private business inputs before spending on a dense scan. Historical studies remain frozen, and `legends-geogrid` operates standalone without requiring AI Marketing Hub Home. If controls conflict, change one setting at a time and preserve each run separately.

## 4. Choose the useful route

- Preserve active or owner-established study geometry: Never silently override an active study's established radius, spacing, search-window control, or query IDs (for example, an established 10-mile radial open-search study at half-mile spacing with `search_this_area=false`).
- Regional half-mile radial baseline (default): Follow [Competitive sampling](COMPETITIVE_SAMPLING.md). Use half-mile spacing clipped to the requested radial footprint (such as a 10-mile radius around the verified business center) with `search_this_area=false` and Standard queue by default.
- Focused neighborhood core (optional): When a tight walk-in or neighborhood check is specifically appropriate before regional sampling, use a compact radius with explicit scope notes rather than substituting it for an established regional study.
- Path A (Zoom / Extent Comparison): If ranks 1-3 hold across the initial footprint, evaluate wider regional extent or zoom controls explicitly while keeping prior runs frozen.
- Path B (Targeted Densification / Outward Expansion): Where ranks 4-10 or competitive transitions occur along active corridors, use `enhance` or quarter-mile follow-up sampling in those supported directions.
- Sparse or irrelevant results: If results are missing near the business center, calibrate categories, primary/secondary GBP alignment, and address verification before buying additional outer samples.
- Unknown private inputs: Mark private conversion, margin, and travel constraints as `unknown` and deliver an explicitly exploratory public study. Do not infer profitable travel from ranking positions alone.

## 5. Collect and report

Use Standard queue by default. Half-mile spacing is the initial regional sampling
policy; clip the regular lattice to the requested radius. Quarter-mile spacing
is a separately priced detailed study when evidence justifies it. Eighth-mile
sampling is reserved for a bounded diagnostic with a specific decision to resolve.
Normal queue Maps requests at depth 30 cost $0.0006 each; all tracked profiles
share the same request per coordinate and query. Live ($0.002) requires explicit
user choice, never an automatic convenience upgrade. Both priced requests and
NR observations must remain visible in the cost estimate and receipt.

Estimate cost before execution. Use fixed sampling for repeat comparisons and adaptive expansion for a stated reach question. All compared queries share locations and settings. Keep controls separate. Use the normalized report contract in `examples/reports/README.md`; configure a registered basemap if street geography is required. Preserve evidence, observed depth and missing-data states.

## 6. Accept the output

Inspect every PDF page at reading size. Check map registration, readable labels, intact rings and attribution, text fit, and no em dashes. Verify counts against evidence. Close with what was learned, one supported next action, and the missing evidence that could change it. Never manufacture a confident prescription from ranks alone.

The study entry point validates required evidence lineage and collection controls.
Market fit and interpretation still require agent review; validation cannot certify them. See [report acceptance](REPORT_ACCEPTANCE.md) and [product limitations](PRODUCT_STATUS.md).
