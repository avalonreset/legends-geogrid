# Evidence-backed study contract (local candidate)

The root [agent recipe](../SKILL.md) selects and interprets. `tools/study.py`
provides credential-free validation, bounded research and collection orchestration.
This is a candidate interface, not a declaration that the live acceptance test passed.

## Website capture

```sh
python tools/study.py website --url https://example.org/ --output runs/business/evidence/website.json
```

This saves readable page text and returns a source entry. HTTP failures and empty
pages stop without manufacturing evidence. If a site needs JavaScript, use the
agent browser to capture its actual rendered text with URL/date provenance.

## Research

A request file contains one provider task:

```json
{
  "kind": "demand",
  "estimated_cost_usd": 0.02,
  "body": [{"keywords": ["pizza restaurant"], "location_code": 2840, "language_code": "en"}]
}
```

Use a current endpoint estimate for the actual request; the number above is an
example, not a price quotation. Kinds: `gbp`, `demand`, `maps_probe`, `organic_probe`.
The shared kit handles authentication. Never put credentials in request files.

```sh
python tools/study.py research --request request.json --output-dir runs/business/evidence
python tools/study.py research --request request.json --output-dir runs/business/evidence --execute --confirm-cost-usd 0.50
```

The ceiling covers cumulative reserved research in that folder, including known
actual overages. Reservations survive network failure: inspect task IDs/results
instead of resubmitting an ambiguous paid POST. A folder lock prevents concurrent
reservations. It is an advisory preflight, not provider-enforced spending control.
Responses and source sidecars are saved even for failed/pending provider tasks;
those tasks cannot qualify a researched study. Keep all research for a study in
one folder. The grid estimate is separate; include both when budgeting.

## Plan

Create `study-plan.json` beside the evidence. Schema: `geogrid-study/v1`.
Required fields:

- `business`: name, exact cid (string), domain (hostname), location_label, lat, lng.
- `sources`: objects with id, kind, relative file, sha256, observed_at (UTC ISO), url.
  Kinds include website plus the research kinds above. Files must stay within the
  plan folder, hashes match, timestamps be within 30 days. Capture website text
  in JSON, for example `{ "text": "original fetched page text" }`.
- `identity`: source_id of GBP response, JSON pointer to its business item,
  website_reference citation, reconciliation explanation. CID, profile coordinates
  and domain must agree with business. Match the actual address and name too.
- `settings`: method (standard/priority/live), odd grid_size 3..11, radius_km
  0.1..25, integer depth 1..100, integer zoom 1..21, device, language_code,
  se_domain, boolean search_this_area, geography_reason, decision.
- `selection`: coverage_summary and evidence citations covering both website and
  GBP. If fewer than three themes are selected, include fewer_themes with reason
  and supporting evidence citations. See [selection policy](QUERY_SELECTION_POLICY.md).
- `queries`: query, boolean selected, reason. Selected entries also need role
  (category/service/product/user_requested), offering_evidence citations,
  demand_source, demand_scope, pilot_sources, intent_evidence citations,
  intent_assessment and limitations. Each selected query also requires a `theme`
  object with id, label, customer_need and distinct_value. One query per theme;
  select 3-5 themes normally, or 1-2 with the cited scope exception above.
  user_requested also requires user_instruction.

A citation is `{ "source_id": "site", "pointer": "/text", "quote": "Pizza delivery" }`.
It must match source text. Provider pointers typically use
`/tasks/0/result/0/items/0/category`. Demand request must include the query. Each
selected lane needs three distinct pilot origins, shared across lanes, with
matching collection controls and returned-result evidence for intent. Pilot
queries with no results require a discovery brief or more calibration, not a
fabricated intent citation. Retain rejected queries and their reasons.

The validator is deliberately narrow: it checks cited lineage and settings. It
does not authenticate locally edited evidence or certify semantic conclusions.
An agent must review identity, actual offerings, result relevance and source scope.

Example theme and narrower-scope declaration (citations must match actual files):

```json
{
  "theme": {
    "id": "delivery",
    "label": "Delivery discovery",
    "customer_need": "Find a restaurant that delivers this cuisine",
    "distinct_value": "Separate delivery discovery from general dining discovery"
  },
  "selection": {
    "coverage_summary": "Describe the verified offerings considered and portfolio tradeoffs.",
    "evidence": [
      {"source_id":"site","pointer":"/text","quote":"Pizza delivery"},
      {"source_id":"gbp","pointer":"/tasks/0/result/0/items/0/category","quote":"Pizza restaurant"}
    ],
    "fewer_themes": {
      "reason": "Explain why only one or two themes are justified; omit this object for a normal 3-5 theme study.",
      "evidence": [{"source_id":"site","pointer":"/text","quote":"Pizza delivery"}]
    }
  }
}
```

This is a structural example, not evidence that a particular business offers delivery.
Old unpublished plans need these fields added before validation; no paid requests
are made by migration/validation. Selection remains an agent judgment.

## Validate, collect and render

```sh
python tools/study.py validate --plan runs/business/evidence/study-plan.json
python tools/study.py run --plan runs/business/evidence/study-plan.json --output-dir runs/business/baseline
# After inspecting the estimate, add --execute --confirm-cost-usd <grid budget>.
python tools/strategy_report.py --config runs/business/baseline/report-config.json --output-dir runs/business/report
```

Execution requires a new output directory, freezes source evidence, and stops on
failure without blind retries. Partial lanes/task IDs remain available. Before
each lane the source hashes and original plan are revalidated. The wrapper uses
the existing collector internally; its diagnostic flag is an explicit low-level
adapter, not evidence that an arbitrary raw query was researched.

For schema examples used in credential-free tests see `tests/test_study.py`.
Never pass its fictitious business data to a paid provider.


## Website unavailable: restricted profile-supported study

Default evidence_mode is `website_and_profile`. An explicit `profile_supported`
plan may proceed when official-site HTTP and browser retrieval both fail. Add
website_limitation explaining the gap. Replace the required website source with
at least two `website_attempt` sources, one per method, retaining normal hashes,
UTC timestamps and URLs. Their JSON payloads use this shape:

```json
{"url":"https://example.org/", "status":"unavailable", "http_status":500, "method":"http"}
```

The second uses method browser. A transport failure may use http_status null plus
an error string. A successful 200 is not a failure receipt. The URL's hostname must
match the profile-linked business domain. Preserve original browser/HTTP captures;
these normalized receipts describe actual attempts, not fabricated website text.

In this mode identity.website_reference is not required. Exact GBP CID, coordinates,
linked domain and identity reconciliation remain required. Each selected offering
citation MUST reference GBP evidence; selection.evidence must include GBP. Demand,
shared pilots, theme policy, cost gates and all other checks remain unchanged.
The generated report includes the website limitation automatically. A focused
one/two-theme exception is separate and still needs evidence.

This route does not resolve address/identity conflicts or prove universal downtime.
Third-party ordering menus may reveal useful facts and contradictions, but do not
silently replace the current profile location or prove service availability at it.


## Recover a collected run without paid requests

The collector returns its actual unique child output directory on stdout. The
study wrapper records that receipt per lane and uses outputs.parsed_json, not an
assumed flat filename. If collection finished under an older wrapper but report
handoff failed, preserve the run and use:

```sh
python tools/study.py assemble --run-dir runs/business/baseline --output-config runs/business/baseline/recovered-report-config.json
```

This command never calls the provider or collector. It validates the archived
study/evidence and each saved lane's business, query, exact CID, settings and grid
origins. It consumes saved collector receipts, or accepts exactly one unique child
parsed-grid.json for a legacy lane. Missing/ambiguous lanes stop; they are never
recollected automatically. Existing report configs are preserved; choose a new
filename. Then render the recovered config normally. The assembly_provider_calls
receipt field refers only to this local assembly, not the preceding paid study.
