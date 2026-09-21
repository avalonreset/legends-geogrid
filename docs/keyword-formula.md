# GeoGrid study and keyword methodology

Updated methodology for multi-intent evaluation and local search diagnostics. This replaces the former four-gate exclusion formula. The old formula confused query ambiguity, viewport filtering, and market absence.

## Start with a decision, not a larger grid

Write a falsifiable question before spending: Is visibility restricted to the business pin? Does the near-core opportunity differ by service? Is an apparent boundary stable when viewport restrictions change? Which competitor repeatedly occupies the intended buyer's results?

Measure Google Maps, the local pack in Google Search, and ordinary organic website results separately. A Maps rank is not a website rank, traffic estimate, lead count, or penalty diagnosis.

## Resolve the entity and freeze the settings

Target entity identity must be anchored by authoritative identifiers: exact Google Maps CID, Place ID, or canonical website domain. While resolving exact CID or Place ID through a diagnostic lookup is preferred to disambiguate multi-location businesses sharing a domain or address, canonical domain matching (hostname matching without protocol or www) is fully supported by the collector contract when single-location web domains unambiguously identify the target entity. Loose business-name matching is rejected as ambiguous and prone to false positives across common trade names. Branded searches are useful identity controls, not evidence of nonbrand customer acquisition. A brand can fail to appear; never assume otherwise.

Retain exact requests and timestamps. Record search engine, endpoint, keyword, coordinates, zoom, search_this_area, search_places, language, device, requested depth, returned count, provider status, matching identifiers and schema version. Treat every setting as part of cache identity. Use exact CID or Place ID whenever available; canonical domain matching is supported when single-location web domains unambiguously identify the target entity. Ambiguous business name matching is not permitted.

## Select complementary queries

Nominate from actual offered services, customer language, site content and owner priorities. Include one category control, one consumer repair query and one additional commercially relevant service. Compare a cleaner category synonym against an ambiguous consumer query; do not silently substitute one for the other.

Probe the center and several directions. Label automotive or other unrelated results explicitly, retain original ranks, and report query ambiguity. A real consumer query is not disqualified merely because one fringe result is automotive. Never renumber ranks after removing unwanted competitors. Four probes cannot establish universal query purity.

Demand estimates can prioritize equally relevant choices when geography, period, source and uncertainty are stated. Google Ads competition is advertiser competition, not organic ranking difficulty. Volume is not required for a diagnostic control, and nationwide volume does not establish neighborhood demand.

## Separate three independent controls

- Point count controls sampling density and cost.
- Spacing/extent controls geographic coverage.
- Provider search zoom and search_this_area control the search viewport, independently of display-map zoom.

Begin with center/cardinal probes at approximately 0.5, 1, 2 and 3 miles where appropriate to the business. Compare provider zoom and area restriction at the same points. Pick a baseline that answers the question, disclose alternatives, and do not optimize settings to manufacture good ranks.

### Illustrative panel dimensions (not required defaults)

Panel sizes such as 7x7, 9x9, and 11x11 are illustrative formulas to evaluate sampling density, geographic reach, and API cost trade-offs. They are not required defaults or universal service-area recommendations:

- **Illustrative 7x7 panel (half-mile spacing):** 49 points, 3 miles edge-to-edge, 1.5 miles to edge midpoints and approximately 2.12 miles to corners. This illustrates a compact neighborhood-level baseline. Expand farther only when the boundary matters; densify where a transition warrants it. Retain the original fixed panel for trend comparisons.
- **Illustrative 9x9 panel (one-mile spacing):** 81 origins, 8 miles edge-to-edge, 4 miles to side midpoints and approximately 5.66 miles to corners. This illustrates a neighborhood-to-corridor view. Paired viewport samples at the center, side midpoints, and corners test whether the outer ranking pattern survives a wider search viewport. Run each service query separately; broad category visibility does not imply repair or emergency reach.
- **Illustrative 11x11 panel (half-mile spacing):** 121 origins, 5 miles edge-to-edge, 2.5 miles to side midpoints and approximately 3.54 miles to corners. Contains 49 inner origins plus 72 outer origins per query, illustrating a denser transition study without changing spacing.

Reuse full-request-identical cache entries while preserving their original acquisition times and cost lineage. Overlapping panels contain repeated observations, not additional unique paid requests. A same-day panel assembled partly from caches is not simultaneous. Cost receipts must distinguish newly charged calls, original cost of reused responses, and historical charged repeats that a request-keyed raw archive may no longer represent uniquely; audit the call ledger and response digests (note that the adaptive collector stores response SHA-256 digests rather than raw response payloads; replay from retained raw is not supported for that adapter).

Report directional sectors with their exact geometric definitions and denominators. Use named neighborhoods only where geographic evidence supports the attribution. Identify rivals by CID and distinguish different branches sharing a business name. Rank 4-10 origins can nominate a bounded competitive comparison, but service economics and demand remain separate owner checks. If outer positions materially weaken in viewport controls, label the far reach setting-sensitive rather than reliable service coverage.

The runner currently accepts odd grid sizes through 51x51 (2,601 points), a software limit rather than a recommended scan. 17x17 is 289 points, not a maximum geographic footprint. Validate cost and runtime before a large job; a parser accepting 51 does not prove a full production run at 51.

## Classify observations honestly

Found: exact entity returned, with organic Maps rank_group and returned count.
Not returned: successful provider result without the entity. This does not establish a numerical rank, especially when fewer than requested results were returned or the viewport was restricted.
Empty: successful response with no Maps businesses. This does not prove no market, no demand, or no competitors.
Error: provider/transport failure, never counted as rank failure or market absence.
Mixed intent: a separate query-quality annotation, not a replacement for these states.

Show absent observations as NR, not an invented 20 or 21. Separate paid placements and rank_absolute from organic Maps rank_group. Do not infer a Business Profile's primary category from a query-dependent category label.

## Summarize without manufacturing coverage

Publish found count, returned-count range, errors, top-3/top-10 observation counts with explicit denominators and missingness. State how short lists affect eligibility for a given cutoff. Conditional median rank applies only to found observations. Never call the share of sampled points population coverage, area coverage, market share, clicks or revenue. Do not average censored ranks by assigning arbitrary values.

Compare equal points and settings. When two settings disagree, show paired differences and treat the diagnosis as setting-sensitive. A single run establishes a snapshot, not trend or cause. A before/after claim requires comparable dated panels and intervention records.

## Turn the study into a bounded intervention

Combine rank observations with first-party public pages and repeated competitors. Distinguish observed facts from explanations to test. Google documents relevance, distance and prominence; exact factor weights are unknown. Review count alone neither explains a loss nor rules out a prominence gap. Map embeds, URL naming style and repeated city words do not establish ranking causes.

Recommend a small service/geography experiment with an owner, exact deliverable, acceptance check, unchanged comparison panel and review date. Preserve functioning pages and existing tests. No speculative URL migrations, mass city-page production, fake locations, guaranteed rank dates or claims of a blacklist without evidence.

Recheck a fixed panel on multiple dates. Record all simultaneous changes and seasonality. Use owner-supplied Search Console exports to connect page/query impressions and clicks to the website hypothesis; public Maps measurements alone cannot supply that connection. No client credentials are required for the public baseline.

## Map-first report policy and QA contract

Client reports exist to show spatial truth clearly. Maps are the primary evidence; editorial prose and tabular diagnostics explain them. To prevent cartography from being degraded into decorative thumbnails squeezed by text, all client reports follow a strict map-first policy:

### Dedicated map pages and combined service layouts

- **Unified printable column:** On standard Letter pages, all elements—titles, captions, body copy, section labels, tables, legend bands, and cartographic map figures—align strictly to a unified 516 pt content column on 48 pt margins (`PAGE_W=612, PAGE_H=792, MARGIN=48, COLUMN=516, MAP_W=516, MAP_H=410`). No element extends to an unaligned inset.
- **Fit short commentary with its map:** For short service summaries, a 516 pt map aligned with the Letter page's 48 pt text margins keeps the map, compact legend, and narrative together without splitting across pages. Use a compact one-line native text legend band and measured vertical flow at readable type sizes (10.5 pt body, 14 pt leading). Use continuation pages only for genuinely extensive commentary or tables where a combined layout cannot remain legible. Never force a separate page for a few sentences merely to satisfy an arbitrary template boundary.
- **No artificial page caps:** Reports have no fixed 16-page or arbitrary page budgets. Let page count expand naturally so that every query map enjoys full-size, uncompromised presentation while maintaining comprehensive editorial depth.

### Copy-fit contract

- Maintain a single unified 516 pt content column on 48 pt margins for Letter pages across all elements: titles, captions, body copy, section labels, tables, legend bands, and cartographic map figures (`PAGE_W=612, PAGE_H=792, MARGIN=48, COLUMN=516, MAP_W=516, MAP_H=410`). All elements share the same 48 pt left and right editorial margins. Table cell padding is intentional and consistent.
- Place title, caption and image in a measured vertical flow, never with independently hard-coded caption baselines. Use at least 12 pt after the title's layout box and 16 pt after the caption's layout box. Captions use regular-weight secondary type, not bold competing headlines.
- Preserve readable type sizes. Balance wrapped headings to avoid an isolated final word; rewrite or add continuation space before shrinking copy or a map.
- Check every PDF page for text collisions and editorial-margin violations. Map pages additionally require aligned title/caption starts and visible title-to-caption and caption-to-map gaps. Inspect full-size examples and all-page contact sheets before delivery.

### Compact native PDF text legends

- **Native text band over raster stamps:** Avoid embedding tiny, blurry rasterized legend text or repetitive disclaimers directly into map image bitmaps. Consolidate rank thresholds and status definitions into a compact, legible native text legend band directly below the map figure.
- **Native PDF typography:** Render the legend band using native PDF typography (e.g. `1–3: green | 4–10: amber | 11+: coral | NR: not returned | E: error | Ø: empty | U: unmeasured`) rather than rasterized artwork or disconnected floating callouts.
- **Clear missingness semantics:** Distinguish non-returned points from true absences or errors: NR indicates Not Returned at requested depth, E indicates provider error, Ø indicates empty response, and U indicates unmeasured. Translucent circles indicate Not Returned, never rank 21 or zero market demand.

### Coordinate evidence bounds vs. page bounds

- **Detail and extent are different views:** If a few distant negative probes force the useful ranks into a tight cluster, use a clearly labeled closer main view and a full-extent appendix. Keep the same view across compared queries. State the measured subset and preserve all observations; never silently crop evidence.
- **Remove internal scaffolding:** Do not overlay cards describing historical pipeline stages such as retained core or standardized base. Explain sampling generations once in plain language, including spacing and physical extent. Grid dimensions alone do not describe geographic scale.
- **Complete distance rings:** Draw only rings that fit wholly inside the map and above attribution, or choose a larger view. Do not draw a ring and then erase its bottom to preserve attribution. Automated checks must cover both ring bounds and marker bounds.
- **Resolution is measured:** Record native pixel dimensions and effective PPI at final PDF placement. Never upscale a raster to claim higher resolution. Around 160 PPI can support a screen-reading edition; do not describe it as 300-PPI print production. Use native PDF text for titles, sample labels and legends.

- **Evidence-driven viewports:** Map viewports must be computed dynamically from the complete set of sampled coordinates (including outermost Chebyshev exploration shells, sentinel probe coordinates, and directional rays), adding appropriate margin for marker radius.
- **Zero marker clipping:** The cartographic bounding box must guarantee that 100% of plotted points remain fully visible. No marker may be clipped by the viewport edge, truncated by title overlays, or drawn into the protected bottom attribution area.
- **Distinguish evidence bounds from page bounds:** Evidence bounds represent the actual empirical geographic envelope sampled during the study (e.g., a 4-mile base with corners at 5.66 miles, or sentinel probes out to 9.9 miles). Display bounds simply frame the rendering page area. Reports must never conflate the two or imply that unmeasured space beyond the evidence boundary represents proven business absence.

### Visual QA and acceptance

- **Ordinary PDF full-scale visual proof:** Inspect rendered deliverable pages at 100% PDF zoom in an ordinary PDF viewer. Verify pin typography, rank number centering, boundary contrast, and neutral distance band legibility. The visual impression must deliver instant geographic clarity at normal reading distance without zooming or squinting.
- **Full-page inspection:** Check title-to-caption flow, single-page service fits, and ensure no elements collide with page margins or footer attribution.
- **Legible basemap attribution:** Provider attribution for raster basemaps (such as OpenStreetMap or Google) must remain unoccluded, legible, and legally compliant—either by retaining the complete image with credits protected in their original position (`preserve-in-place`), or via explicit caption and metadata attribution for overlay-safe imagery. Never detach and reattach a strip containing geography. For schematic coordinate maps without a street basemap, label as 'Schematic coordinate map — no street basemap' directly in caption and metadata.
- **Traceable data integrity:** Every pin on every map must trace directly to a verified raw JSON observation. Displayed counts, found rates, and near-miss candidates must reconcile with underlying response digests.
- **Operational receipts:** Maintain a separate durable operational receipt recording API endpoints, call counts, cache reuses, costs, and output paths.

References: https://docs.dataforseo.com/v3/serp/google/maps/live/advanced/ ; https://support.google.com/business/answer/7091 ; https://developers.google.com/search/docs/monitor-debug/debugging-search-traffic-drops
