# Sampling adequacy policy

Choose the decision and meaningful territory first, point spacing second, total
point count third, price fourth. A square's point count alone says nothing about
coverage quality. Radius is a half-side parameter in the current square runner,
not a circular catchment; disclose actual span and spacing.

## Planning

- Use website/GBP location and service evidence, settlement pattern, physical
  barriers, relevant competitors and pilot results to justify territory. Do not
  infer a customer catchment from rank alone or a universal radius by industry.
- For a neighborhood-level initial study, use 0.75 km maximum neighbor spacing as
  an explicit product planning heuristic. Dense/walkable contexts can justify
  smaller spacing; broad service areas can justify a larger value. Record why.
- At a 3 km half-side, 5x5 has 1.5 km spacing, 9x9 has 0.75 km, and 11x11 has
  0.6 km. Prefer 9x9 at that extent unless evidence calls for another resolution.
  Do not demand 9x9 for a tiny territory where 5x5 already resolves the question.
- Choose 3-5 themes at comparable origins/settings. Present point count, extent,
  spacing and the combined research/collection estimate, not merely grid size.

## Review after measurement

The offline sampling_review.py and report sampling-review.json identify:

1. Coarse spacing: add locations within the existing extent.
2. Sharp observed transitions: inspect and refine those neighborhoods. Four rank
   positions crossing top3/top10 is a heuristic trigger, not statistical proof.
3. Review each directional boundary and all themes together. Green/yellow supports
   a relevant-territory probe; red needs context. Confirmed full-depth NR holds by
   default, but evidence-backed sentinel probes and shared comparison bands remain
   legitimate exceptions. Three strong maps can justify including a fourth NR map
   as a control. See ENHANCE.md for the collective rubric and bounded stop rules.
4. Excluded observations: fix missing/error/empty evidence, not geographic size.
5. Irregular grids: require geographic gap review instead of square assumptions.

No trigger is proof of completeness; absence of a trigger is not certification.
For persistently poor ranks, investigate identity/query/local competitors before
buying farther-away samples. Narrowly scoped studies can intentionally stop at a
relevant boundary, with an explicit reason and no comprehensive-coverage claim.

Keep the original baseline. Extend or densify with comparable shared origins
across themes, and never pool changes in time/settings as if simultaneous. Reuse
only exact cached origins/query/settings at an appropriate observation age. A
5x5 to 9x9 at unchanged extent nests existing points geometrically, but that does
not prove a particular baseline is reusable. The enhance command verifies source
integrity, settings and freshness, then estimates only new/refreshed observations.
It executes nested same-extent refinement up to 25x25. Outward directional probes
remain agent-reviewed proposals; this command does not execute territorial growth.
