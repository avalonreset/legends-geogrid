---
loop: checkpoint
step: 9
title: "Undo & Loop"
cut: "an undo plan is not optional"
prev: "[[08 - Closeout]]"
next: "[[00 - Goal]]"
goal: "Upgrade GeoGrid with Alana-style keyword list reports and a citation opportunity module"
slug: upgrade-geogrid-with-alana-style-keyword-list-reports-and-a-citation-opportunity-module
---
# Undo & Loop

> [!quote] An undo plan is not optional
> Keep or roll back, then decide against a bounded contract.

**Cut:** undo / loop.

## Loop stop contract
- **max_passes: 3** unless the user sets another value.
- Exit only when **every** acceptance criterion in **00 Goal** has PASS evidence in the **04 Verify** claim ledger.
- If max_passes is reached with unmet criteria, **stop and ask the user**. Do not loop again silently.
- Record pass count, elapsed, and any unmet criteria below.

## Decision (criterion by criterion)
| criterion # | PASS evidence? | met? |
|---|---|---|

- Pass count:
- Unmet criteria:

## Undo plan
- How to reverse this iteration if it was wrong:

## Feeds
- Refined intent feeds back to step 00, Goal. **The loop closes here.**

## Runs
<!-- newest first -->
- 2026-06-26 — undo plan: revert the pending commit for this slice, or restore `src/main.js`, `src/styles.css`, docs, and public docs from the previous commit. The change is contained to dashboard UI, docs, and doctor required-file list.

---
↩ [[_core]]  ·  ◀ [[08 - Closeout|Closeout]]  ·  [[00 - Goal|Goal]] ▶
