---
loop: checkpoint
step: 0
title: "Goal"
cut: "intent"
prev: "[[09 - Undo & Loop]]"
next: "[[01 - Read]]"
goal: "Upgrade GeoGrid with Alana-style keyword list reports and a citation opportunity module"
slug: upgrade-geogrid-with-alana-style-keyword-list-reports-and-a-citation-opportunity-module
---
# Goal

> [!todo] Intent first
> Define **Upgrade GeoGrid with Alana-style keyword list reports and a citation opportunity module** before touching anything. Work that solves the wrong problem is worse than none.

**This is the command center.** Every loop returns here.

## Acceptance criteria
Each criterion needs a verification method. **Do not proceed past this checkpoint while any criterion is blank or has no verification method.**

| # | Criterion (what "done" means) | How it will be verified |
|---|---|---|
| 1 | The app exposes an Alana-style keyword scan list with business, keyword, score, scan settings, drilldown, and export affordance. | `pnpm build`, browser DOM check for `Keyword Scan List`, `Export CSV`, and table rows. |
| 2 | Citation research is demoted out of the core app and parked as optional future context. | Browser DOM check confirms no core citation module; docs review confirms `docs/CITATION_MODULE_NOTES.md` is optional/parked. |
| 3 | Citation research is saved with source links and a clear separate-service boundary. | Read `docs/CITATION_MODULE_NOTES.md`; verify source URLs are present. |
| 4 | The package remains share-ready for Daniel. | `pnpm doctor`, `pnpm build`, `git status --short`, and updated handoff docs. |

## Scope & constraints
- In scope: Vite dashboard UI, keyword scan list, docs, product status, Daniel handoff, doctor checks, parked research notes.
- Out of scope: paid API calls, direct citation submissions, visible citation module in the core app, real backend/API implementation, live Google Maps credentials, new PDF generation.
- Blast radius (what this could affect): browser demo rendering, public docs served by Vite, local doctor readiness checks.

## Feeds
- Refined intent on each loop (set at step 09, Undo & Loop).

## Runs
<!-- newest first: YYYY-MM-DD — what changed -->
- 2026-06-26 — acceptance criteria updated after product pivot: keyword-list UI is core; citation work is parked as optional research.

---
↩ [[_core]]  ·  ◀ [[09 - Undo & Loop|Undo & Loop]]  ·  [[01 - Read|Read]] ▶
