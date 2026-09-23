# Say enhance

After reading a study, the user can say **enhance**, **more detail**, or ask to
improve its resolution. The agent identifies the active business and most recent
compatible completed run; it must not ask the user to design a grid.

## Customer experience

Explain what the additional points will answer, the proposed dimensions, how many
observations can be reused, how many require refresh, and the incremental estimate.
Example: “Increase this footprint from 5 x 5 to 9 x 9 for better neighborhood
detail. Reuse 100 observations across four searches and collect 224 additional
points. Estimated additional ranking data: $0.448.” This is an example, not a
standing price or an assurance that a particular baseline is still fresh.

If that enhancement and its cost are already authorized, execute. Otherwise show
the estimate first. “Enhance” accepts the previously presented specific scope and
estimate, not unlimited spending. Account for the user's total remaining budget;
the command ceiling covers this enhancement only. All estimates are advisory.

## Agent commands

```sh
python tools/study.py enhance --run-dir runs/baseline --output-dir runs/enhanced-01
python tools/study.py enhance --run-dir runs/baseline --output-dir runs/enhanced-01 --execute --confirm-cost-usd 0.50
```

The first command is offline and banks both the baseline and enhancement proposal.
It writes `enhance.html`, `enhancement-plan.json` and a checksum. The execute
command uses that exact saved plan and rechecks research/source integrity and
freshness. A subsequent enhancement uses `runs/enhanced-01` as its baseline and
a new sibling folder. Never overwrite the previous report.

Execution automatically writes a new `report/report.html` and `report/report.pdf`.
The HTML's PDF link opens the same edition. Return these paths to the user. The
static report is not a server and does not call paid APIs when a reader clicks it.

## Selection and reuse rules

Optimize information value, not the smallest bill. Interpret all maps together.
As a review heuristic, when at least two themes and 60% of the study support the
same direction, pitch a small shared outward probe that can include every theme.
For example, three of four positive boundaries can justify carrying the fourth
NR theme as a comparison control. Keep its individual hold recommendation visible;
explain the study-level reason for the exception. This threshold guides judgment,
not a mandatory decision or a statistical claim.

Exceptions can use verified service territory, populated corridors, interior
patterns, nearby positive samples or a specific competitor/customer question.
An NR border is not proof that visibility cannot reappear farther away. A small
sentinel band can resolve that uncertainty before buying a large expansion.
State the per-theme incremental cost, what is reused, the question being tested,
and when to stop or reassess. Existing budget approval permits the bounded action;
do not repeatedly ask over pennies or imply that low cost alone justifies a scan.

Assess each selected theme and each north/south/east/west boundary separately.
Confirmed NR means the requested rank depth is fully evidenced; short lists,
errors, empty responses and missing samples are unknown, not negative borders.
A perimeter entirely of confirmed NR holds the extent by default. It does not
prove absence beyond that perimeter. An exception needs new geographic/business
evidence and a specific question, not a desire for a bigger picture.

Green/yellow edge observations support considering a small directional probe in
relevant territory; isolated hits are not permission to grow every side. Red edge
observations require supporting context or a useful trend to investigate. Select
directions and themes for a justified coverage experiment, then price that scope;
do not multiply every map outward because one keyword is strong.

Keep interior resolution separate: an NR border can surround useful interior
visibility. Shared-origin refinement can retain comparison themes, but the pitch
must explain that role. If every theme is absent everywhere, do not densify merely
to satisfy a spacing preference. The executable enhance path remains same-extent;
directional boundary review is a recommendation, not an implemented outward scan.

- Review actual spacing, neighboring rank transitions and excluded observations.
- When justified, subdivide the existing grid once: 5 x 5 becomes 9 x 9; existing
  coordinates remain shared across every query. Then reassess rather than loop.
- Preserve query, exact CID, language, depth, device, zoom and search-area controls.
  Incremental acquisition uses Maps Live, even when the original was queued;
  the report discloses that transport choice.
- Default reuse window is 24 hours. `--max-age-hours` is an explicit 1-168 hour
  policy setting, not proof that rankings stayed constant. Unknown, future, stale
  or failed observations are not reused. Provider observation timestamps are
  propagated; export timestamps are never substituted.
- The default spacing preference is 0.75 km, configurable with
  `--target-spacing-km`. It is a planning preference, not an SEO law.
- Same-extent refinement stops at 25 x 25 and does not auto-densify below 100 m.
  Irregular geometry requires a deliberate geographic plan. If no new detail is
  warranted and all observations are reusable, recommend no purchase.
- Strong boundary ranks prompt a review of relevant territory; they do not justify
  automatically expanding into water, irrelevant towns or an assumed service area.
  Automatic boundary extension is not part of this command.

## Evidence, budget and recovery

Each paid point is reserved in an append-only ledger before HTTP. Raw request,
response, cost and hash are preserved. Actual overruns reduce the remaining
allowance before the next call. A provider ceiling cannot be enforced by this
preflight ledger.

Rerunning the exact execution uses completed responses and never repurchases them.
An ambiguous submission or unresolved task stops with its saved ID/response for
inspection, not an automatic retry. If rendering fails, rerun locally to finish
the report. Expired reuse plans need a new estimate; do not force old observations
through validation. Partial acquisition is banked and remains explicitly partial.

The library links the enhanced edition to its same-CID parent. Original costs
stay in the original study; enhancement receipts report incremental costs only.
The report recomputes metrics and removes baseline rank-dependent recommendations.
The agent must review the new findings and produce updated evidence-backed advice.
Mixing eligible old and new points is spatial refinement, not a synchronized
before/after monitoring experiment or proof of a ranking improvement.

## Render saved acquisition after the reuse window

Once all observations are assembled and `report-config.json` exists, rendering
historical evidence needs no new provider calls or freshness override:

```sh
python tools/strategy_report.py --config runs/enhanced/report-config.json --output-dir runs/enhanced/report-recovered --proof --require-pdf-qa
```

Keep its original observation dates and mixed-age disclosure. This is historical
report recovery, not permission to resume unfinished acquisition with expired
reuse. Baseline source paths must remain available for acquisition continuation;
the vault is an evidence archive, not yet a relocatable execution environment.
