# Changelog

## 0.1.2 - 2026-09-03

- Standardized the product brand everywhere as lowercase `legends-geogrid`.

## 0.1.1 - 2026-09-03

- Added explicit software, service, data, trademark, and research-source attribution.
- Added a complete Leaflet BSD 2-Clause notice and a provenance record for the original market research.
- Switched the default OpenStreetMap layer to the exact policy endpoint with linked ODbL attribution.
- Documented tile-provider overrides and the no-prefetch/no-offline-use boundary.
- Generate a bundled-dependency licence file in every production build.
- Ignore local audit worktrees so release-verification artifacts cannot be committed accidentally.

## 0.1.0 - 2026-09-03

- Renamed the project to `legends-geogrid`.
- Prepared the first public MIT-licensed release.
- Made single scans estimate-only by default.
- Added explicit execution and cost-ceiling gates.
- Included DataForSEO depth multipliers in cost estimates.
- Removed the private Empire vault path from bulk-run defaults.
- Added automated tests, CI, security guidance, and public documentation.
- Rejects incomplete API grids instead of caching or scoring them as valid scans.
- Uses hostname-boundary matching and deduplicates identical rows within a bulk run.
