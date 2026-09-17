# Keyword-selection formula

Four gates pick every grid keyword, in this order, before any grid spend.
A keyword that fails any gate never gets a grid.

## Gate 1 — Site nominates

Steal keywords from the business's own site, never invent them. Homepage titles,
service pages, and money pages are the declared bets; the grid tests whether
those bets pay. Category terms only, never the brand name: searching the
business name proves nothing, since any business ranks for its own name.
A customer who types the name is already theirs. The grid simulates strangers
typing what they need.

## Gate 2 — Pollution test disqualifies

Run 4 probe points (spread across the lattice) per nominee on the standard
queue — a fraction of a cent. A nominee passes only with 4/4 results in the
business's own category. If auto shops rank for an HVAC query, the keyword is
poisoned at the category level: throw it out, no matter how good its volume
looks. Real rejections from production: `ac repair` and `air conditioning
repair` (auto-shop pollution in fringe cells).

## Gate 3 — Intent names the winner

Clean is necessary but not sufficient. A keyword that cannot name its buyer
intent cannot label its map. `hvac repair` passes 4/4 clean but is general,
not cooling — it was thrown out as a cooling-lane label and replaced with
`air conditioning contractor`. Cover each buyer intent once (repair, replace,
hire); if two intents paint the same map, that agreement is the diagnosis.

## Gate 4 — Volume prioritizes

A clean keyword nobody searches is trivia. Rank surviving nominees by
location-scoped demand (volume, difficulty, intent via the DataForSEO keyword
APIs; see `third_party/claude-seo/skills/seo-dataforseo`). Volume sets the
attack order; pollution sets the exclusion. High volume plus clean plus low
competition goes first.

## Standing rules

- Re-run all four gates before every new grid; never inherit an old approval.
- Far-field cells that return no pack for every keyword (including known-good
  ones) are dead geography, not keyword failure — they render blank.
- Pin only cells where the provider returned at least one in-category business.
  Blank means no market to measure, not a missed pull.
