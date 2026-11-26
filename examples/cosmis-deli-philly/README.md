# Cosmi's Deli (South Philadelphia) Starter Study

This bundled public-data case study ships with `legends-geogrid v0.3.0` so you can explore every interactive view and the 30-layer vector-hex PDF report without API keys or spend.

## Study summary

| Field | Value |
| --- | --- |
| Business | Cosmi's Deli, 1501 S 8th St, Philadelphia, PA 19147 |
| Footprint | 6.0-mile radius, 0.5-mile uniform circular honeycomb (`hex_radius`) |
| Dry-land origins | 458 pins clipped against 8 OSM Delaware and Schuylkill river polygons (291 Pennsylvania home-landmass pins, 167 detached New Jersey pins) |
| Queries (depth 30) | `sandwich shop`, `hoagie`, `cheesesteak` |
| Observed field | 1,170 distinct Google Business Profiles |
| Campaigns | 4 grounded agent campaign plans + 5 avoid zones (including Vision non-serviceable land-use flagging the Point Breeze / PES Refinery industrial tract) |
| Keyword stuffing | All 250 `#1` winners audited (`Pending 0`): 14 corroborated discrepancies, 165/178 websites captured, 245/250 GBP storefront photos, 250/250 official keyless Google Maps Street View links |
| Vector PDF report | [`report/report.pdf`](report/report.pdf) (5 pages, 30-layer marching-squares topography + river-clipped Local Leaders hex grid) |

## Regenerate the PDF report locally

```sh
python tools/report_builder.py --hex-study src/data/cosmis-deli-philly-study.json --pdf examples/cosmis-deli-philly/report/report.pdf --overwrite
```
