# Required business research before GeoGrid collection

Status: proposed implementation plan, 22 September 2026. No release or live scan authorized by this document. Existing measurement tools remain useful for expert-directed work; end-to-end newcomer readiness is not established.

## Product contract

A user supplies a business name with enough location context, a domain, or a Maps URL. The agent establishes the business, researches its public Google Business Profile and website, obtains DataForSEO evidence, selects justified queries and sampling, then explains the intended measurement and cost. It does not interview the user for keywords, grid dimensions, or SEO strategy. Explicit user keywords take precedence and remain labeled user-directed, including limitations.

The default decision is: identify current visibility for the business's evidenced offerings in its immediate market. Ask only for facts that cannot be reliably resolved: ambiguous branch, conflicting business identity, private service constraints, or spending authorization not already provided. Unknown profitability does not prevent a descriptive visibility baseline, but prevents profitability claims.

Required research means required evidence, not mandatory purchase of every possible API field. Missing GBP/business-profile or DataForSEO evidence blocks the researched-study path with a precise remediation; it never silently becomes model-generated keyword research. Authorized dated exports may satisfy evidence requirements after validation and freshness review. Unavailable metrics stay unavailable, not zero. Synthetic demonstrations and explicitly requested raw-query diagnostics remain separate modes, never a bypass into a researched client report.

## Findings in the current candidate

- tools/local_heatmap_poc.py requires --keyword. Collection is functional but selection is external.
- docs/keyword-formula.md already says offered services, customer language, site content and owner priorities should nominate queries. It also hardcodes a consumer repair query, an HVAC-specific assumption that must go.
- docs/START_A_STUDY.md requires bounded discovery in prose, then explicitly says this is operator guidance rather than enforced behavior.
- README labels GBP and keyword research references optional and says they are not an automatic pipeline.
- Vendored reference instructions mention MCP access; the current product transport uses legends-dataforseo-kit. Reconcile first-party routing; retain upstream attribution and do not casually rewrite vendor files.
- tools/pollution_gate.py contains a legacy direct authenticated HTTP client and rigid category rejection. Retire it from the default path; do not use it as query validation or a second provider transport.
- The fresh Gemini run installed reporting/provider packages and generated an offline sample. It did not research and select restaurant queries before asking the user. Linux shared-drive executable/symlink restrictions and missing libnspr4.so independently blocked browser setup.

## Mandatory preparation sequence

1. Readiness: verify isolated environment, provider authentication without paid queries where supported, writable evidence store, and a functioning street-map renderer. On Linux, keep executable environments off mounts that cannot support execution/symlinks. Distinguish missing Python packages, missing Chromium and missing OS libraries. Give one actionable failure rather than a generic reinstall loop. Do not ask for Google imagery credentials when free maps suffice.
2. Identity: reconcile domain/contact/location with public profile evidence. Record CID/Place ID, canonical domain, source URLs and retrieval times. Handle branches, hidden addresses and service-area businesses explicitly. Never equate geocoded street address with verified GBP pin.
3. Business evidence: capture relevant homepage, service/menu, location/contact pages and public profile fields. Extract actual offerings and stated geography. Preserve contradictions. A query-dependent Maps category is not proof of the profile's primary category. Owner-only GBP management access is not a prerequisite for public research; identify inaccessible fields rather than inventing them.
4. Candidate queries: generate a bounded initial shortlist (typically 5-10) from that evidence. Use vertical-appropriate concepts, not fixed repair templates. Separate brand control, category, service/product, and explicit user queries. Every candidate needs an offering source and an intent rationale. Reject unsupported offerings; don't infer catering, delivery, emergency availability or replacement work from business type alone.
5. DataForSEO validation: inspect demand estimates at a stated locale/language/period, and representative Google search/Maps results. Use the shared kit only. Separate Maps, Search local pack and website organic measurements. Validate exact endpoint and field contracts before coding adapters. Demand alone does not determine selection; national volume is not neighborhood demand, and Ads competition is not SEO difficulty.
6. Bounded Maps pilot: test the strongest few candidates at a small common set of origins with stable settings. Record actual returned competitors and mixed intent. Preserve original organic ranks; never filter and renumber. Low volume does not disqualify a well-supported category control. A missing target is not a reason to discard an otherwise useful query. Choose on relevance and intent, not on which gives flattering ranks.
7. Study plan: recommend usually 2-4 complementary nonbrand lanes, with evidence and rejected alternatives, plus a separate brand identity check if needed. Derive a modest geographic baseline from business type and verified location context; explain assumptions. Do not infer profitable travel territory. Freeze common origins/settings for comparisons, separate controls, and estimate discovery, pilot, grid and optional imagery charges separately.
8. Collection/report: execute the frozen plan within existing execution/cost gates. Persist exact requests, statuses, source hashes, timestamps, cached/new distinctions and unique charged calls. Generate street maps and source-backed narrative. Include a short 'Why these searches?' section with offering evidence, intent validation, metric provenance and limitations. Attach the machine-readable study and research ledger.

No dense grid may start in researched mode until the plan passes validation. A plan change invalidates its execution binding. Resume pending paid tasks by saved ID; never blindly resubmit ambiguous POSTs. Polling repeats must not count the same task charge repeatedly. Budgets remain advisory caller controls, not provider billing caps.

## Small implementation surface

Proposed, not existing commands:

- study_prepare.py: identity/evidence collection, provider research and agent-authored candidate decisions, with bounded resumable stages.
- study_validate.py: deterministic schema and evidence-reference validation, readiness, freshness/contradiction checks and allowed state transitions.
- study_run.py: translates the validated plan into existing collectors and report config; no duplicate scan or authentication engine.

Artifacts: business-evidence.json, query-decisions.json, pilot-observations.json, study-plan.json, research-receipt.json and a short research-brief.md. All carry schema version and stable IDs; evidence records include source, observed time, content digest and public/private classification. Query decisions include exact query, role, supporting evidence IDs, demand scope or unavailable status, observed intent, selection/rejection rationale and user override. The run binds the plan digest and source snapshot IDs. A nonempty rationale field is not sufficient: referenced evidence must exist and support the claim. Model interpretation remains reviewable; deterministic validation cannot prove semantic correctness alone.

States: needs_identity -> researching -> needs_evidence / pilot_ready -> pilot_complete -> plan_ready -> collecting -> report_ready. Cost approval is separate from research completeness; approval never manufactures missing evidence. Missing access yields a useful research brief and setup action, not a fabricated client study.

## Reuse the Hub components without importing every dependency

Inspected Library local-domination workflow routes local/maps research, Local SEO Brain and Marketing Brain. It currently accepts <primary-keyword> and makes live DataForSEO optional. Reusing it unchanged would reproduce this gap. The inspected Marketing Brain keyword-workbook prompt assumes raw keyword JSON already exists; it is not a discovery engine.

- DataForSEO Kit: required shared provider transport and cost/status envelopes.
- Codex SEO local/maps/DataForSEO capabilities: reuse focused research methods, adapt through the current agent-neutral provider contract. Respect Codex routing; do not require a Claude installation.
- Website capture: reuse available evidence capture capability, with a portable ordinary HTTP/browser path. A specific paid crawling service must not be required merely to read a public menu.
- Marketing Brain: reuse query/source/intent organization and competitor reasoning where verified; do not treat a workbook generator as proof of research.
- Local SEO Brain: reuse source/claim separation and export adapters; it remains an evidence consumer, not secretly the live provider caller.
- Hub Library: add a researched GeoGrid handoff with automatic discovery before primary-keyword selection. Its broad optional-evidence workflow can continue elsewhere; this product's required evidence contract must be explicit.

First implementation must inventory exact versions, available commands, licenses and input/output contracts before claiming these integrations exist. Preserve GeoGrid's standalone install and no-MCP requirement. Do not make users install the entire Hub or several vaults for a restaurant baseline.

## Alpha Mechanical retrospective: observations, not a completed audit

Reviewed all 21 pages of alpha-mechanical-local-search-20260919-v7.pdf as extracted text. Located the v2 evidence ZIP (952 entries) and earlier reconciliation ZIP (3 entries). Inspected measurement plans and prior factual-review text. These are earlier artifacts: their reviews do not certify v7. No raw-response replay or final v7 bundle reconciliation has been completed in this pass.

What exists: explicit query lanes, matched geography, viewport controls, source notes, exact entity ID in an earlier plan, raw-response files and earlier independent review receipts. That is meaningful measurement lineage, not proof that the four queries were selected through a complete GBP/website/demand research process. The inspected plans encode chosen queries/settings but do not explain all inclusion/exclusion decisions.

Specific v7 review items:

- Pages 2 and 11 say 9 AC-repair near misses; page 5 says 10, despite top-10=10 and top-3=1 implying 9 if denominators are the same. Recompute from final observations.
- Page 2 says over 85% of near-miss repair candidates are within 2 miles. Page 7 says ten furnace near misses within 2 miles plus one additional candidate; top-10=11 and top-3=1 implies ten total. Prior v2 review instead says nine of ten within 2 miles. Verify against v7 data, do not silently transfer earlier verdicts.
- Pages 6 and 10 treat air conditioning contractor as replacement intent. Category wording alone does not establish that. Require observed intent evidence or qualify/remove the interpretation.
- Page 2 asserts much higher commercial return from nearby searchers. The report also states private conversion data was not accessed. Recast as a testable prioritization hypothesis unless commercial evidence exists.
- Page 12 describes city-qualified searches, then identifies the only hit as unqualified furnace repair; reconcile exact requests. Its Maps mobile-navigation versus desktop-pack framing needs verification against actual device settings.
- $0.650 is described as total actual spend in v7; an older review reconciles $1.627 for a different historical scope. This is not itself a discrepancy: reconcile incremental versus cumulative scopes and label them explicitly.

Retrospective completion requires locating the exact v7 config, observations, research captures, source generation code and ledger; verifying hashes/requests; mapping each selected query to pre-collection evidence; recomputing every metric; and creating a correction log. Evidence not found is 'unverified provenance', not proof the work never occurred. Preserve original files. Correct a new version only after review; do not overwrite or send anything now.

## Ordered delivery milestones and acceptance

M0: Freeze claims. Treat current newcomer flow as incomplete; preserve the working collectors and local map improvements. No release in this planning task.
M1: Business/query evidence schemas, validator and agent instructions. Fixtures cover restaurants, HVAC and a service-area business; conflicting identity, user keywords, missing evidence, stale evidence, unsupported offerings, unknown demand and prompt injection in source pages. All factual output links to source evidence.
M2: Provider/capture integration. Verify kit endpoint schemas and live availability with bounded authorized canaries, plus offline response fixtures. All paid stages estimate first; no duplicate client or hidden spend. Resume and error behavior tested.
M3: Wire all default agent and CLI entry points to preparation. No normal researched scan bypass. Keep explicit diagnostic/offline modes honestly labeled. Generate 'why these queries' from the ledger, not post-hoc persuasive copy. Add story/metric consistency checks and source support review.
M4: Fresh-user acceptance on Madness of Masala at the confirmed Trooper address. Prompt only supplies business/domain; system researches, selects queries and geography, proposes cost, and produces a real street-map report after spending is authorized. No keyword/grid interview. Preserve the uncoached transcript, interruptions, costs and artifacts. Repeat on HVAC and a service-area fixture to catch restaurant-specific hardcoding.
M5: Alpha retrospective and independent evidence review. Verify calculations against final source observations and review selection provenance separately from layout. Inspect every final PDF page.
M6: Release candidate review. Full pnpm check plus new research contract tests, clean installs on Windows and Linux, missing-browser/dependency guidance, bounded live integration proof, no exposed secrets, and user review of actual output. Publication remains a separate explicit decision.

Definition of done: business input -> traceable required research -> justified queries -> calibrated bounded plan -> approved collection -> correctly sourced report, reproducible from saved evidence. No zero-data 'success', arbitrary keywords, fabricated primary categories, unsupported commercial promises or mapless real reports.

## Implementation receipt: 22 September 2026

Local candidate only, in E:\legends-geogrid-jev-demo. No publication.

- Root SKILL.md now defines business-first research and interpretation without a
  default keyword/grid interview. README and AGENTS route to it.
- tools/study.py implements website capture, bounded shared-kit research,
  cumulative reservation ledger, no ambiguous POST retry, plan validation,
  evidence snapshots and matched-lane collection/report handoff.
- tools/study_contract.py checks required source types, hashes/dates, exact CID,
  profile coordinates/domain, quoted evidence, demand request inclusion, shared
  three-origin pilot controls and collection estimates. This establishes lineage,
  not independent source authenticity or semantic truth.
- Raw single/bulk/adaptive paid collection requires explicit --diagnostic.
- 211 tests and full pnpm check passed, including four offline PDF workflows;
  19 new study tests include the collector-to-report configuration handoff.
- Live Madness of Masala test verified exact CID/category, obtained demand and
  three category pilots for $0.03116 provider-reported cost. Website capture and
  Chromium both returned HTTP 500/empty body. Validator stopped the incomplete
  plan before a dense grid. Evidence/brief are under ignored runs/madness-study.

Still open before release: successful business-only fresh-agent acceptance with
complete website evidence; contrasting HVAC/service-area research fixtures;
independent semantic review of selection/action quality; complete Alpha v7
retrospective; clean candidate installation checks and final output review.
No claim that the entire reconciliation plan or live newcomer acceptance passed.
