# Daniel Handoff

## One Sentence

GeoGrid is a private local SEO heatmap prototype that shows we can build the practical core of Local Falcon or Search Atlas using DataForSEO rank data, Google Maps display assets, and our own dashboard/report layer.

## What To Review First

1. Run the dashboard:

```powershell
pnpm install
pnpm dev
```

2. Open the executive report:

```text
docs/local-seo-geogrid-executive-report.pdf
```

3. Review the product status:

```text
docs/PRODUCT_STATUS.md
```

## Why It Matters

The original business question was whether an agency could produce many local SEO heatmaps for prospecting without paying SaaS pricing. The answer is yes in principle. DataForSEO Standard Queue makes 1,000 prospects at 5 x 5 cost about $15 in raw rank-check data.

## What Works

- Standalone dark-mode dashboard.
- Real Home Slice Pizza 5 x 5 proof data.
- Dense 17 x 17 simulation for Local Falcon-style visuals.
- Python runner for live/priority/standard DataForSEO scans.
- Cache-aware bulk-run scaffold.
- Executive report PDF.

## What Needs Product Work

The biggest missing piece is a backend. Today the browser app visualizes data and the Python CLI retrieves data. To make this normal software, add a local API and SQLite store so the browser can launch scans and load results.

## Recommended Decision

Keep this repo private. Use it as the seed for a real product if local SEO prospecting becomes a priority. The next build should be a local end-to-end scan flow: form input, dry-run estimate, paid execution, cached result, and PDF export.
