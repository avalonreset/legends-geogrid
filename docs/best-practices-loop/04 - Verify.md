---
loop: checkpoint
step: 4
title: "Verify"
cut: "evidence over intuition"
prev: "[[03 - Write]]"
next: "[[05 - Gaps]]"
goal: "Upgrade GeoGrid with Alana-style keyword list reports and a citation opportunity module"
slug: upgrade-geogrid-with-alana-style-keyword-list-reports-and-a-citation-opportunity-module
---
# Verify

> [!success] Verify third
> Trust nothing unverified, including your own work an hour ago. No verification path? Refuse the task until it has one.

**Orchestrates:** `/deep-research` (adversarial), then `/wiki-lint`.
**Cut:** evidence over intuition.

## Do
- Build a claim ledger at `topics/upgrade-geogrid-with-alana-style-keyword-list-reports-and-a-citation-opportunity-module/reports/claim-ledger-2026-06-26.md` covering every material claim from Write.
- Lint the vault for dead links and stale claims.

## Claim ledger schema
| claim_id | claim | source artifact | verifier command | verdict (PASS/FAIL/UNKNOWN) | evidence quote/link |
|---|---|---|---|---|---|

**Gates (do not skip):**
- PASS requires a source quote or a command-output link. No evidence means not PASS.
- Any FAIL returns to **Write** (03). (red feedback arrow on Loop.canvas)
- Any UNKNOWN must be removed, scoped explicitly as unknown, or sent to **Gaps** (05).
- Do not proceed to Prune while any material claim is FAIL or UNKNOWN.

## Runs
<!-- newest first -->
- 2026-06-26 — verification completed: `pnpm build`, `pnpm check:python`, `python tools/geogrid_doctor.py`, and Chrome browser DOM check passed. Browser check found keyword list true, 9 rows, export true, citation module false, citation nav false, console errors empty.
- 2026-06-26 — claim ledger created at `topics/upgrade-geogrid-with-alana-style-keyword-list-reports-and-a-citation-opportunity-module/reports/claim-ledger-2026-06-26.md`; command verification still to be completed after browser QA.

---
↩ [[_core]]  ·  ◀ [[03 - Write|Write]]  ·  [[05 - Gaps|Gaps]] ▶
