# Daniel Handoff

## One Sentence

GeoGriddy is a private local SEO heatmap feature prototype that shows we can build the practical core of Local Falcon or Search Atlas using DataForSEO rank data, interactive map display, keyword-list reports, and our own dashboard/report layer.

## What To Review First

1. Run the dashboard:

```powershell
pnpm install
pnpm dev
```

2. Open the executive report:

```text
docs/local-seo-geogrid-executive-report.html
```

3. Review the product status:

```text
docs/PRODUCT_STATUS.md
```

4. Optional: review the parked citation research:

```text
docs/CITATION_MODULE_NOTES.md
```

## Why It Matters

The original business question was whether an agency could produce many local SEO heatmaps for prospecting without paying SaaS pricing. The answer is yes in principle. DataForSEO Standard Queue makes 1,000 prospects at 5 x 5 cost about $15 in raw rank-check data.

The likely product home is Local SEO Brain, not a standalone hosted SaaS. Treat this repo as a feature prototype that can become an invocable skill/command plus browser-rendered report artifact.

## What Works

- Standalone dark-mode dashboard.
- Interactive pan/zoom map.
- Real Home Slice Pizza 17 x 17 DataForSEO proof data.
- Saved raw receipt and parsed 289-coordinate grid.
- Alana-style keyword scan list with CSV export.
- Python runner for live/priority/standard DataForSEO scans.
- Cache-aware bulk-run scaffold.
- Executive report HTML and browser-safe PDF.

## What Needs Product Work

The biggest missing piece is the Local SEO Brain integration boundary. Today the browser app visualizes data and the Python CLI retrieves data. To make this normal Hub software, add a command/skill wrapper, a cached result store, and a browser report launcher.

Citations are parked as research only. They are a separate service line and should not be mixed into the first GeoGriddy feature unless we intentionally add a local SEO suite layer later.

## Recommended Decision

Keep this repo private. Use it as the seed for a Local SEO Brain feature if local SEO prospecting becomes a priority. The next build should be an agent-operated end-to-end scan flow: brain/client input, dry-run estimate, paid execution, cached result, browser report, and export.
