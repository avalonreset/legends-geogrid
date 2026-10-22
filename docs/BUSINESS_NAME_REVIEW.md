# Business-name review

GeoGrid's Business-name review is an evidence workbench for possible Google
Business Profile name discrepancies. It is not a list of proven offenders or a
probability model. Its output is an individually researched case file and, when
supported, a proposed name correction for a human to review.

## Agent-owned findings, read-only viewer

The agent performs collection, individual source review, synthesis, and case-file
updates. **Keyword stuffing** displays the resulting findings beside the map
modes. It is not an owner-operated review application: do not add import/export
wizards, evidence-entry forms, decision checkboxes, or an expectation that the
owner finish the investigation. Filtering cases, inspecting source links, and
showing an identity on the map are navigation only.

The agent reports what was checked, which discrepancies are corroborated,
what counterevidence exists, and the next justified action. Profile retrieval,
automated text screening, and individual source investigation are distinct.
Do not mark a case complete merely because its profile was fetched. Missing
signage/identity evidence remains an agent research gap, not a complaint draft
or an instruction for the owner to do the research. Legacy local drafts remain
preserved but are no longer exposed as the viewer workflow.

After collecting, reviewing and exporting, attach the artifact:

```powershell
python tools/business_name_review.py attach --output-dir "<private-audit-folder>"
```

This creates `companion-study.attachments.json` beside the study (using its actual
stem), links the review by a relative URL, and binds it to the study fingerprint.
It does not modify the hashed scan. Serve both the study and its attached files
under the same origin. Explicit older study URLs discover the sidecar without a
`name_review` query parameter. A user-selected attachment is still validated;
never silently substitute an unrelated audit.

If research is missing or fails validation, show all observed first-place profiles
as **Agent investigation not attached**, along with the loading error. An empty
attachment cannot be interpreted as zero naming concerns. Acceptance requires
opening the owner's existing study link in their actual browser and checking the
visible findings, not only a fresh root URL in a test browser.

## Collection commands

Run from the repository root. Use a new private output directory for each fresh
audit and a completed companion study as the input. Planning is offline:

```powershell
python tools/business_name_review.py plan --study "<companion-study.json>" --output-dir "<private-audit-folder>"
```

The plan prints the number of distinct profiles and the Standard estimate,
then writes an exclusive `seed.json` bound to the source study's SHA-256 and
plan fingerprint. Review the estimate before the paid step:

```powershell
python tools/business_name_review.py submit --output-dir "<private-audit-folder>" --execute --confirm-cost-usd <approved-budget>
python tools/business_name_review.py retrieve --output-dir "<private-audit-folder>"
python tools/business_name_review.py websites --output-dir "<private-audit-folder>"
python tools/business_name_review.py photos --output-dir "<private-audit-folder>"
# Optional speed boost when legends-jev v0.2.0+ (jev-1.14.0 optical recognition) is installed:
python tools/business_name_review.py photos --output-dir "<private-audit-folder>" --jev
python tools/business_name_review.py export --output-dir "<private-audit-folder>"
```

Replace placeholders with real paths and the approved numeric budget. Omitting
`--execute` on submit shows scope without purchasing tasks. This command has no
Live mode or fallback: it uses Standard business-profile task submission with
priority 1 through the shared provider kit. The supplied budget must be finite
and nonnegative. Cost checks are local safeguards, not a provider billing cap.

`retrieve` reuses saved task IDs and may be repeated until the queue completes.
`websites` captures public HTML from websites returned by identity-matched
profile results. `export` writes `name-review.json` with individual profiles,
source timestamps, source hashes, screening signals, and collection counts.
An unavailable website or incomplete profile remains visible as an evidence gap.
No command edits profiles or files complaints.

Submission locks, exclusive intent reservations and receipt hashes prevent
accidental duplicate purchasing. If a POST times out after an intent is written,
reconcile provider task IDs before resuming; do not delete the reservation and
try again. Receipt validation checks accepted task IDs, profile tags and costs.
Changed source studies or identities invalidate the binding. Preserve the run
and create a new audit when refreshing stale evidence; the website cache does
not overwrite old captures.

Record an actual policy check in `policy-review.json` with its URL, date and
summary. An offline export must not claim it re-read Google's current policy.

## What Google's rule actually says

Google expects the name customers recognize in the real world, supported by
consistent branding. Unnecessary services, place names, promotional phrases,
hours, or contact details may be inappropriate additions; descriptive words can
also belong to a legitimate brand. Legal entity names are not automatically the
required display name. Evaluate real-world representation, including applicable
branch-name exceptions. See the [official naming guidelines](https://support.google.com/business/answer/3038177?hl=en).

A DBA is useful identity evidence, not an automatic Google-policy exemption.
Conversely, no matching DBA record is not proof of stuffing. Do not infer intent
from a company's name, rankings, or registration timing.

For a straightforward inaccurate name, Google's [Maps editing workflow](https://support.google.com/maps/answer/7084895?hl=en)
is the relevant starting point. Google's [reporting guidance](https://support.google.com/maps/answer/16109801?hl=en)
directs misleading names raising suspicion of fraud to the
[Business Redressal Complaint form](https://support.google.com/business/contact/business_redressal_form).
A name discrepancy alone does not establish that a business is fake or closed.
Google decides outcomes; neither correction nor a ranking benefit is guaranteed.

## Scope and selection

Create one case per distinct CID/place ID for every first-place winner observed
in any study query, including single-point winners and businesses based outside
the study circle. Preserve branches separately. Include the primary business
under the same criteria; the owner is not exempt from review.

Use query-specific wins and locations to explain why a case matters to the
study. These metrics can prioritize reviewer effort, but are not evidence of a
name violation. Never multiply a keyword heuristic by market share and label
the result "likelihood."

Retain a complete review queue even when the map defaults to recurring winners.
Expose counts for total cases, current profiles inspected, evidence gaps,
counterevidence, and actionable drafts. "All screened" means automated screening
only; it must never be described as "all profiles individually investigated."

## Case record

Each case retains:

- Stable profile identity, observed name, address or hidden-address status,
  website, profile URL, and source observation time.
- Study provenance and review scope: query/location wins and source run.
- Automated name signals, each explained as a research prompt, not a finding.
- An evidence ledger: URL, source type, captured-at time, observed-at time when
  different, exact relevant fact or short excerpt, and saved artifact/hash.
- Evidence supporting a discrepancy and evidence supporting legitimate naming.
- A proposed real-world name only when sourced; never strip service words
  algorithmically and present the remainder as the correct name.
- Outstanding questions, review status, reviewer identity, review timestamp,
  and reasons for the decision.
- If eventually submitted: exact approved text, submission date, route, receipt
  when available, and later observed outcome. No submission is implied by
  exporting a draft.

## Investigation procedure

1. **Open the actual current profile.** Match CID/place ID and branch, then
   record the displayed name and URL. A saved ranking title is historical
   evidence; it is not proof of the current profile name. Where direct access
   fails, mark the case "Current profile check needed." Do not silently turn a
   search snippet or generated Maps link into a verified inspection.
2. **Check the business's current primary sources.** Inspect its visible logo,
   contact/location page, about page, and recent customer-facing branding.
   Differentiate an SEO page title from the displayed company name. A website
   footer may identify a parent entity, not its trading name. Record branch
   identity using address, phone, license or profile link.
3. **Seek physical-world corroboration (Standard Operating Procedure).** Run `photos`
   to pull high-resolution GBP `main_image` and `logo` files plus a **multi-vantage
   Google Street View search quest** (`streetview`, `streetview_v1`, `streetview_v2`)
   into `<private-audit-folder>/photos/` (requires no extra API keys or paid calls).
   - **Multi-Vantage Street View Search Quest rules**:
     - Query `SingleImageSearch` at progressive radii (`18m`, `30m`, `50m`, `85m`) so
       corner buildings lock onto the front street rather than a rear alley.
     - Detect and skip isolated indoor 360 photospheres (`<= 2` connected road nodes)
       so shopping-center pins step out to the outdoor street graph.
     - Exclude historical time-machine indices (`info[5][0][8]`) and select up to 3
       spatially distinct current-year road panoramas (`>= 10m` apart, preferring the
       `13m..38m` standoff sweet spot) aiming their compass bearing (`yaw`) at `(lat, lng)`
       to step around trees, utility poles, and side walls.
   - **Optional `legends-jev` Optical Accelerator (`--jev`)**:
     - The pipeline works 100% standalone without `legends-jev` using agent multimodal
       file reading.
     - When `legends-jev` (`v0.2.0+`, `jev-1.14.0` with `TypeSafe-Danger-Zone-Images: true`)
       is installed and `--jev` is passed, `photos` batch-screens the downloaded
       storefront, Street View, and logo images in ~200ms per profile (`sign_visible`,
       `suspect_terms_shown`, `best_image`, `sign_box`, and `verdict`), automatically
       promotes an unobstructed alternate Street View vantage (`streetview_v1`/`v2`) when
       `v0` is blocked by a tree, and records the typed receipt in `photos-manifest.json`
       for operator verification.
   - Visually inspect the downloaded storefront, Street View, and logo images before
     scoring a case: immediately clear false positives where physical building signage
     or the official logo badge supports the displayed title, record confirmed signage
     mismatches in `visual_review`, and leave obstructed or indoor-only photos as open
     questions to investigate.
   A service-area business may not have a public storefront; lack of a sign is
   not automatically adverse evidence. Do not expose private residential details.
4. **Check identity records where useful.** For California contractors, start
   with the displayed license number at [CSLB](https://www.cslb.ca.gov/onlineservices/checklicenseII/checklicense.aspx).
   Search legal entities at the [California Secretary of State](https://www.sos.ca.gov/business-programs/business-entities/information-requests)
   and trade names in the relevant county. California's Secretary of State does
   not hold county FBN filings or all sole proprietorship records.
   [Sacramento County explains](https://finance.saccounty.gov/us/en/tax/faqs/fbn.html)
   that an absent local filing has several possible explanations. Log searched
   jurisdiction, spelling variants, date and result; do not equate a no-match
   with illegitimacy. Do not reproduce owner home addresses or other irrelevant
   personal data in the workbench.
5. **Reconcile counterevidence.** A new brand, acquisition, multi-location
   variation, DBA, logo variation, or recently changed profile may explain the
   mismatch. An accessible business website alone does not establish what
   signage says. Record conflicts rather than picking the name that helps the primary business.
6. **Make a bounded decision.** Identify exact disputed additions and cite the
   evidence for a replacement. Require a current profile check plus corroborated
   real-world name evidence before preparing a correction-ready draft. Where
   evidence is insufficient or contradictory, keep the next research step.

## Status model and evidence quality

Suggested user-facing stages:

| Stage | Meaning |
| --- | --- |
| Not reviewed | Only a saved study listing or automated signals exist. |
| Research needed | One or more checks ran; current identity or branding remains unresolved. |
| Name supported | Available current evidence supports the displayed name; no discrepancy established. |
| Conflicting evidence | Sources disagree or a plausible branding/DBA explanation remains unresolved. |
| Discrepancy supported | Current profile and corroborated naming evidence support a specific mismatch. |
| Draft ready for review | A factual proposed correction and evidence packet have been prepared. |
| Submitted / monitoring | Used only after a human-authorized submission actually occurred. |

Implementations may use equivalent internal enum names, but must preserve these
distinctions. "Name supported" is a review conclusion, not a guarantee of Google
compliance; "Discrepancy supported" is not a verdict on intent or legality.

An imported manual status must not outrun its evidence. Empty evidence arrays,
generic source URLs without observed facts, stale profile checks, placeholder
reviewers, and unsupported proposed names cannot create correction-ready cases.
Keyword signals alone must never create a report-ready state. No numerical
violation probability is permitted.

## Freshness and persistence

Store timestamps per source; the study timestamp is not the profile-inspection
timestamp. GeoGrid's working freshness window is seven days for current profile
and website observations; this is a product choice, not a Google requirement.
Refresh immediately before any submission, regardless of the window. Older
signage can remain contextual evidence if visibly dated and not asserted current.
Unknown timestamps are unknown freshness, not fresh.

Keep source runs immutable. Rebuilding a review queue preserves manual evidence,
counterevidence and decisions keyed by stable profile identity; any newly changed
name reopens review. External evidence belongs in the user's private run folder,
not committed examples. Synthetic fixtures must use invented businesses.

### Analyst source reviews

An optional `manual-review-*.json` file in the audit directory uses schema
`geogrid-manual-name-review/v1`. Its `cases` object is keyed by CID. Each entry
records `current_profile_name`, `checked_at`, `reviewer`, `findings`,
`counterevidence`, `next_action` and `sources`. Local evidence references carry
`evidence_path` and `sha256`; sources also carry public URLs, source types and
short relevant facts or excerpts. Use one entry per CID across all attached
manual-review files.

Supported analyst outcomes are `name_supported`, `research_needed` and
`source_discrepancy`. These mean an analyst compared particular sources. They
do not imply signage was inspected, a government record was checked, or a person
opened Google Maps directly unless the review explicitly records that work.
A current identity-matched provider profile response is a profile source check,
not proof of those other activities.

Export attaches validated notes as `source_review`, retains `automated_status`
and `automated_assessment`, and exposes counterevidence alongside findings. The
review must bind to the current profile name and saved response, with unchanged
local evidence files inside the audit directory. Unknown/duplicate CIDs,
superseded names and changed hashes are rejected. Stale analyst notes or stale
profile evidence must not promote a current assessment. Source reviews never
set `report_ready` true, regardless of an imported value.

Seven-day freshness applies to both current profile and website checks. Missing,
invalid or future timestamps cannot certify freshness. A human's new note cannot
make an old provider response current. Legacy browser-saved reviewer decisions remain a
separate checkpoint; copying any brief is preparation, not submission.

## Draft playbook

The per-business playbook should answer:

1. Which exact current listing and branch are we reviewing?
2. What observed words or discrepancy prompted investigation?
3. What do current profile, visible branding and identity records establish?
4. What supports the current name, and what remains unresolved?
5. What is the proposed next step and why?
6. If justified, what exact replacement name and short factual explanation
   should a human review, with the supporting links?

Prepare drafts without external submission. Do not call the complaint form,
click Submit, impersonate a customer, coordinate mass edits, or mark a business
closed merely to address its name. User authorization to research competitors
and build the feature is not authorization to file reports. A new submission
requires explicit owner direction identifying the cases or reviewed batch.

After an authorized correction, record subsequent observed names without
assuming causation or competitive gains. Name changes do not mechanically move
the primary business into the next ranking slot. Measure outcomes with unchanged scan settings.

## Acceptance checks

- All observed leaders are represented, independent of map threshold and address.
- Same-name branches remain separate; primary business is reviewed consistently.
- Keywords, city names, punctuation, long names and good rankings cannot alone
  create a supported-discrepancy classification.
- A real trading name can contain service and geographic terms.
- DBA evidence is retained without automatic exoneration or accusation.
- Blocked websites, short captures and unchecked profiles remain unresolved.
- Supporting and contradicting evidence are both visible in the same case.
- Exports show provenance, freshness and draft-only state without submitting.
- Historical names are not presented as current solely because the UI is new.


## Recurring leader investigations

The default case scope is **recurring Local leaders plus matched historical
title leads**. Recurring means three or more first-place locations in at least one query, without
restricting a business base to the study circle. Business names do not change with
the map keyword, so switching that keyword must not hide findings by default.
Agents individually assess this union. A selected-keyword-only scope remains an
explicit option; selecting it changes the summary counts and case list together.
All observed winners remain accessible, including singleton profiles, but their
presence does not imply completed investigation.

Use one scope-consistent executive summary, with separate counts for possible
concerns, source-supported concerns when present, supported names, unresolved
evidence, and pending investigations when present. Do not lead with a zero
supported-concern count while hiding the possible concerns elsewhere. Do not
show an all-query headline above selected-query metrics. Case filters narrow the
list; the summary continues to describe the clearly labeled investigation scope.
Prioritize concern cases once in the list instead of repeating them in a second
card wall. Show the current Google title with exact disputed words highlighted,
captured branding, the next agent action, findings and counterevidence, and
source links. Branding differences are not automatically proposed corrections.
Use human-readable source dates and keep the viewer read-only.

Assessment brackets are supported naming concern, possible concern, branding
supports name, insufficient evidence, and investigation pending. Record exact
suspect words, source-backed findings, counterevidence, and the next evidence
needed. Fetching a profile or matching metadata alone is not an individual review.
A possible concern must identify a specific discrepancy, not just a service or
city word. Insufficient evidence is not clearance. Keep separate profiles separate.
This workflow examines business names/titles only; reviews and unrelated abuse
are outside scope. The companion displays agent research and requires no owner
forms, imports, or exported drafts.

## Historical leads and explained concern confidence

A supplied report can identify a business which ranks below first place everywhere.
Such a lead must not disappear because of the Local leaders color threshold.
Match exact Google profile IDs against all observed study participants, retain
separate branches, and record distance from the study center, returned observations,
first-place wins and report pages. Refresh the profile through Standard queue.
Show historical allegations as leads, not current verdicts. Exclude unrelated
address/duplicate allegations from this title-only workflow.

For a bounded refresh, use repeatable `--only-cid` with
`tools/business_name_review.py plan`; use `--include-cid` to supplement a winner
plan. Unknown IDs fail validation. Preserve the old evidence and compose a new
derived artifact rather than rewriting original captures.

An individually reasoned `title-evidence-v1` confidence score may describe
**support for a naming concern**, never a statistical violation probability:

| Level | Meaning |
|---|---|
| Unscored | Insufficient, stale or identity-mismatched evidence |
| 0 | Reviewed branding supports the title; not guaranteed compliance |
| 1 | Weak lead with substantial counterevidence |
| 2 | Specific documented naming conflict, material alternatives unresolved |
| 3 | Corroborated conflict, including real-world branding, alternatives unresolved |
| 4 | Strong current corroboration with plausible alternative explanations checked |
| 5 | Very strong verified discrepancy; Google outcome still unknown |

Record the rationale, supporting and contrary factors, exact CID and profile
title, and timestamp. Do not add up source counts, review completeness, wins,
service words or city names to manufacture a score. Show the explanation beside
the score. Suppress a score if the title/identity changes or its profile,
assessment or scoring evidence is older than seven days. An unscored case must
never display 0/5. Scores never promote reporting readiness or submit corrections.
Do not infer market-wide prevalence from this selected review.
