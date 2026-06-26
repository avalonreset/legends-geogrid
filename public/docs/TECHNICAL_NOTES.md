# GeoGrid Technical Notes

## Data Backbone

GeoGrid uses DataForSEO Google Maps SERP as the rank source. Each coordinate in the grid is a separate task. The target business is matched against returned map results by CID, place ID, domain, exact name, partial name, and fuzzy name score.

## Why Square Grids

Square grids are the audit baseline because the scan is a repeatable coordinate lattice. Radius defines how far the grid extends from the business center. A circular display can be added later, but the paid evidence should stay square so scans compare cleanly over time.

## Cost Model

DataForSEO Google Maps SERP rates used by this prototype:

- Standard Queue: $0.0006 per coordinate.
- Priority Queue: $0.0012 per coordinate.
- Live Mode: $0.0020 per coordinate.

Standard Queue is the bulk affordability mode.

## Current Proof

The included Home Slice Pizza proof scan is a 5 x 5 Standard Queue run:

- Keyword: pizza.
- Location: South Congress, Austin, TX.
- Reported API cost: $0.0150.
- Found points: 12 of 25.
- Top 3 points: 7 of 25.
- Average found rank: 3.83.

## PDF Performance Note

Tall PDFs are allowed. For browser performance, embedded screenshots should be JPEG streams, not lossless PNG-style PDF image streams. Avoid CSS image filters during PDF export because Chrome can rasterize filtered images into expensive Flate streams.
