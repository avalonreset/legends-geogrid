# From measurements to useful decisions

A client report must answer: what did we learn, why does it matter, what should
we do next, and how will we know whether that helped?

Use two synchronized layers: readable HTML/PDF and `report-model.json` with
observations, denominators, limitations and the same decision brief. Bank both
in the study library. Never replace the evidence with an article.

## Editorial recipe

1. Identify the business, clickable official domain, listing location and scope.
   Website availability and address conflicts must remain visible.
2. Lead with a short, defensible interpretation. Explain what a rank dot means.
3. State computed findings in ordinary language, with denominators. Retain full
   maps and their legends. Do not call sampled-point shares market coverage.
4. Select one to five prioritized decisions. Each needs a reason, specific next
   step, suggested owner, success check, uncertainty, and report evidence pointers.
5. Keep detailed acquisition methods and observation ledgers accessible without
   making a business owner read them before understanding the conclusion.

The optional `decision_brief` input has `headline`, `explanation`, and `actions`.
Each action requires `title`, `why`, `next_step`, `owner`, `success_check`,
`uncertainty`, and a nonempty `evidence` list of JSON pointers into the validated
report model (`/lanes/0/metrics`, `/verification_notes/0`, etc.). The renderer
resolves references and stores the referenced values. It rejects nonexistent
references, but does NOT certify that a cited fact entails an analyst's prose.
An agent must review that entailment before calling the report client-ready.
Without authored decisions the system produces a descriptive reading guide;
it must not claim that a decision-quality interpretation has been completed.

## Targeted local research, not a full audit

Before selecting themes, establish business type and real offerings, reconcile
public profile and website identity, examine local search intent, and use demand
with its geography and limitations stated. National demand is not local revenue.
User priorities and available first-party performance can inform choices; absent
analytics are unknown, not zero. Preserve accepted and rejected query rationale.

After scanning, investigate only questions raised by the evidence: conflicting
directions, a verified offering that is hard to discover, or recurring competitors
at specific origins. Fetch and cite the relevant pages/profile fields; do not
launch a generic website audit. Reviews, categories and content differences are
hypotheses until supported, not explanations inferred from a rank chart.

Do not prescribe edits merely because one query performs worse. Consider no
change, information verification, denser sampling, wider extent, and monitoring.
An expansion recommendation is not a completed scan. Use the sampling rubric,
record the decision, retain exact origins/settings and separate new baselines.

## Learning over time

Bank proposed actions as proposed, not completed. A later monitoring study should
link its parent, record the actual intervention and date, and compare like with
like. Keep changed locations/settings in separate baselines. Rank improvement
alone establishes neither causation nor commercial success; measure leads/orders
separately when authorized first-party evidence is available.

## Method inspiration

This recipe borrows answer-first organization and evidence-led explanation from
the installed Claude Blog workflow, and identity/offerings/location checks from
Claude SEO's local workflow. No external skill code or assets are bundled here.
Their promotional statistics, ranking weights, article length targets and stock
image requirements are not adopted. Dark Legends styling remains independent of
the pure-white light theme.
