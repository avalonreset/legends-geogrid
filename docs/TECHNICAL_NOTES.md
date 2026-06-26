# GeoGriddy Technical Notes

## Data Backbone

GeoGriddy uses DataForSEO Google Maps SERP as the rank source. Each coordinate in the grid is a separate task. The target business is matched against returned map results by CID, place ID, domain, exact name, partial name, and fuzzy name score.

The browser map is a display layer. The current prototype renders an interactive Leaflet map with OpenStreetMap tiles so the demo can pan and zoom without spending Google Maps Platform quota. A Google Maps tile/geocoding layer can be swapped in later without changing the rank-data contract.

## Why Square Grids

Square grids are the audit baseline because the scan is a repeatable coordinate lattice. Radius defines how far the grid extends from the business center. A circular display can be added later, but the paid evidence should stay square so scans compare cleanly over time.

## Cost Model

DataForSEO Google Maps SERP rates used by this prototype:

- Standard Queue: $0.0006 per coordinate.
- Priority Queue: $0.0012 per coordinate.
- Live Mode: $0.0020 per coordinate.

Standard Queue is the bulk affordability mode.

## Current Proof

The main included Home Slice Pizza proof scan is a 17 x 17 Standard Queue run:

- Keyword: pizza.
- Location: South Congress, Austin, TX.
- Reported API cost: $0.1734.
- Found points: 225 of 289.
- Top 3 points: 100 of 289.
- Top 10 points: 201 of 289.
- Average found rank: 4.97.

The older 5 x 5 proof scan is retained as historical cache data, but the dashboard now opens on the real 17 x 17 proof.

## PDF Performance Note

Tall PDFs are allowed. For browser performance, embedded screenshots should be JPEG streams, not lossless PNG-style PDF image streams. Avoid CSS image filters during PDF export because Chrome can rasterize filtered images into expensive Flate streams.
