# Choosing what to study

Default: **3-5 evidence-backed search themes**, one representative query per theme.
This is a product research policy, not a Google recommendation about keyword count.
The agent recommends the scope; the user need not supply keywords or technical settings.

## 1. Build the business inventory

Read the official home, service/menu, location and booking/order pages as relevant.
Reconcile those offerings with the public GBP primary/secondary categories,
description, services/products, address and linked website. Record contradictions,
seasonal/obsolete offerings and unavailable pages rather than choosing whichever
source supports a more exciting report. Confirm the exact business identity first.

Useful supplementary inputs include customer review language, recurring competitor
categories/offerings in actual local results, and existing Search Console/GBP
performance or conversion data if already available with authorized access. These
help generate or prioritize hypotheses. Competitor offerings and review mentions
alone do not prove that the target currently offers a service. Private analytics
are not required for first use; do not interview the user for unavailable accounts.

## 2. Generate and group candidates

Start with the evidenced offerings, not a universal keyword list. Consider category,
service, product/specialty and use-case discovery where relevant. Write the customer
need each theme represents and the business decision it could inform. Group synonyms
and near-identical wording together before selecting a representative phrase.

A restaurant might support category, delivery and catering themes; a repair business
might support general repair, emergency help and a specific system. These are examples,
not mandatory lanes. Never infer availability, qualifications, dietary suitability,
24-hour service, geographic reach or profitability from the business type.

Brand searches are identity controls, not a way to fill the theme quota. Adding
"near me" or swapping "food" for "restaurant" does not automatically create a new
theme. Separate wording variants only when observed intent and the decision differ;
keep sensitivity experiments separate from the baseline.

## 3. Check demand and actual local intent

Use DataForSEO demand research with explicit country/location, language and update
date. Prefer relevant geography when available. A broad national estimate is context,
not an estimate of town-level customers. Ads competition is not organic difficulty.
Unknown/zero demand is a limitation, not automatic rejection of a verified offering.

Pilot the strongest candidates at shared center/edge origins with the same controls.
Read the returned businesses/categories, recurring competitors, sparse results and
mixed intent. Consult organic results when Maps alone does not resolve the ambiguity.
Do not default to picking only phrases where the business already ranks well, or only
phrases where it ranks poorly. Both conceal useful parts of the business's situation.

Three origins are an initial calibration, not proof of representative market coverage.
Geography must fit the decision, catchment evidence and practical travel constraints.
Do not infer commercial service territory from a rank radius.

## 4. Select the smallest useful portfolio

Choose 3-5 distinct themes using these qualitative judgments, with sources:

- Offering is real and current; conflicts are resolved or explicitly limited.
- Customer intent is relevant in the local results.
- The theme answers a different discovery question from the other selected themes.
- Measuring it can inform a feasible decision, without invented revenue estimates.
- Added information justifies the cost, uncertainty and report complexity.

Do not invent a numeric opportunity score or weight formula. Explain the tradeoffs
in ordinary language. Retain rejection/deferral reasons for plausible alternatives.
A theme is not accepted merely because its volume is largest.

Fewer than three themes is allowed only with an explicit supported scope explanation:
for example a narrow verified offering, a specifically requested focused study, or
insufficient evidence for other lanes. Label it **focused**, describe what is missing,
and never call it a complete business study by default. Do not pad it with synonyms.
The baseline validator caps selection at five; larger commissioned studies need a
separately designed scope, not disguised duplicate themes.

Website research remains required in the current candidate. A failed website lookup
must not be mistaken for universal downtime or absent offerings. Record the failure
and attempt independent browser retrieval. If both fail, an explicit
`profile_supported` study may proceed using current public GBP offering citations
for every selected lane, with demand/pilots unchanged. Preserve dated failure
evidence and disclose the missing website verification in the proposal and report.
This does not resolve conflicting addresses, relocation, identity or service availability;
reconcile those independently and never transfer offerings across unverified locations.
If identity cannot be resolved, provide a discovery brief or an explicitly scoped
listing measurement, never a falsely verified current-business study.

## 5. Present and execute

Run `python tools/study.py query-review --plan <study-plan.json>` before proposing or
buying a grid scan. Review its machine-readable output (`geogrid-query-review/v1`)
and Markdown summary for:

- **Source observation ages and mixed vintage:** Check individual source timestamps
  and age spread (for example, older website/GBP captures paired with fresh SERP
  pilots). Elapsed time since capture warns when a pre-scan refresh is advisable
  (default warning at 14 days, hard contract cutoff at 30 days for new paid scans),
  without claiming that age proves external business facts changed. Historical
  completed studies remain frozen and valid; never rewrite or auto-substitute their
  historical query IDs.
- **Service-theme coverage and synonym overlap:** Verify how observed GBP categories
  and website service pages map to selected themes (direct match, indirect synonym
  coverage, or unselected categories). When two selected queries share core service
  or equipment concepts (such as cooling repair vs. cooling contractor), verify and
  document why their local SERP intent or business decision differs, or mark them
  as explicit `user_requested` comparisons.
- **Accepted, rejected, and deferred candidates:** Record non-selected candidate
  queries in `queries` with `selected: false`, `reason`, and optional
  `disposition: "rejected"` or `"deferred"` so future study iterations do not
  re-spend on already evaluated candidates.
- **Known missing business inputs:** Keep unmeasured private inputs (Search Console,
  private GBP owner call/click metrics, CRM job mix, service margins, dispatch
  travel constraints) explicit so reports do not fabricate local demand or ROI.
- **Standalone and optional Library/Home evidence boundary:** `legends-geogrid`
  operates standalone without AI Marketing Hub Home. When prior Study Library
  checkpoints or Home evidence files are available, attach them via local
  hash-verified `external_evidence` links in `study-plan.json` rather than runtime
  dependencies or copied private logic.

Show a concise study preview: business/location, selected theme -> representative
query -> evidence -> decision, omitted/deferred candidates, geography, limitations and total
research/grid cost estimate. If the user has already authorized the scope and budget,
proceed within them; do not add another routine approval conversation. Preserve the
CLI spending gates. If spending is not authorized, request the concrete estimate.

Compare themes at the same origins and settings. Report supported findings, alternative
explanations, a few specific actions and a repeat measurement plan. A weak rank is an
observation, not a diagnosis; a strong rank can justify maintaining a baseline rather
than recommending changes. A useful study can conclude that more SEO work is not yet
supported by the evidence.

## Implementation and limits

The study recipe (docs/STUDY-RECIPE.md) applies this policy. The study contract requires theme id/label,
customer_need, distinct_value, selection coverage_summary, citations to both website
and GBP, and a cited explanation for fewer than three themes. Every lane retains its
existing demand/pilot/source requirements. The receipt and report handoff expose the
themes, `query_review`, and scope rationale. Duplicate theme IDs are rejected; semantic duplication
and relevance are surfaced by `tools/query_review.py` and still require agent review. Renaming an ID is not proof of distinctness.

Google describes relevance, distance and prominence as local-ranking considerations;
this supports researching business fit and geographic context but does not justify
attributing a specific rank to one factor. [Google Business Profile guidance](https://support.google.com/business/answer/7091?hl=en), checked 22 September 2026.
