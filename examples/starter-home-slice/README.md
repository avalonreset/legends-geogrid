# Home Slice Pizza: 10-Mile Starter Case Study (v0.2.0)

This directory and the bundled Companion datasets under `src/data/` provide a complete, pre-built **v0.2.0 starter case study** for **Home Slice Pizza** (`1415 S Congress Ave, Austin, TX 78704`, `homeslicepizza.com`, CID `12299280573550492680`).

Anyone cloning `legends-geogrid` can immediately launch the browser Companion or open the completed Strategy Report without configuring API credentials or paying for a fresh scan.

## What Is Included

1. **Bundled Companion Study (`src/data/home-slice-study.json`)**
   - **Footprint:** `10-mile` radius (`16.09344 km`) centered on `1415 S Congress Ave` (`30.2492286, -97.7495328`) with regular `0.5-mile` spacing (`0.804672 km`), producing `1,249` shared circular-lattice search origins (`radius_grid`).
   - **Search Controls:** DataForSEO Google Maps Standard Queue (`depth = 30`, `zoom = 13`, `search_this_area = false`, `language_code = en`, `device = desktop`).
   - **Queries (4 distinct search themes):**
     - `q1`: `pizza restaurant` (primary GBP category discovery: `21` top-3, `261` top-10, `917` found)
     - `q2`: `new york style pizza` (core culinary identity: `549` top-3, `1,023` top-10, `1,249` found)
     - `q3`: `pizza by the slice` (signature walk-in slice format: `470` top-3, `952` top-10, `1,183` found)
     - `q4`: `pizza takeout` (secondary GBP category and carry-out fulfillment: `6` top-3, `222` top-10, `850` found)
   - **Full Field:** `473` unique Google Business Profiles observed across all `4,996` coordinate-query searches, with an 11-profile comparison shortlist (`TARGET` + top 10 competitors).

2. **Bundled Campaign Research (`src/data/home-slice-campaign-research.json`)**
   - Attached automatically in the **Campaigns** and **Strategy room** views.
   - Includes query-specific action briefs (`q1` through `q4`) and four prioritized campaign plans:
     - Dedicated takeout and curbside pickup clarity on the South Congress location page (`q4`)
     - New York-style and slice-counter headings on `/location/south-congress/` (`q2` and `q3`)
     - Sister-profile coordination between `Home Slice Pizza` (`1415 S Congress Ave`) and `More Home Slice` (`1421 S Congress Ave`)
     - North Austin sister-location handoff analysis (`501 E 53rd St`, CID `5514358989167054199`)

3. **Bundled Business-Name Review (`src/data/home-slice-name-review.json`)**
   - Attached automatically in the **Keyword stuffing** view.
   - Covers all `165` first-place winning profiles across the 10-mile Austin market, with `79` recurring leaders individually source-reviewed and scored on the `0-5` `title-evidence-v1` ordinal confidence scale against live Google Business Profile checks and captured websites.

4. **Completed Portable Strategy Report (`examples/starter-home-slice/report/`)**
   - [`report/report.pdf`](./report/report.pdf): 18-page editorial PDF report with verified OpenFreeMap street basemaps, 1,249-point rank overlays, profile review, decision brief, and methodology disclosures (`pypdfium2` QA passed with `0` out-of-bounds glyphs).
   - [`report/report.html`](./report/report.html): Standalone HTML report companion.
   - [`report/map-001.png`](./report/map-001.png) .. [`report/map-004.png`](./report/map-004.png): High-resolution (`1548 x 1356` at `216 PPI`) georeferenced rank maps for all four queries.
   - [`report/report-model.json`](./report/report-model.json) and [`report/report-qa.json`](./report/report-qa.json): Machine-readable report model and layout/map QA verification receipt.

## How to Open

### 1. Interactive Browser Companion
```bash
pnpm install
pnpm dev
```
Open the local URL printed by Vite. The 10-mile Home Slice Pizza starter study, Campaign Research, and Business-Name Review load automatically by default (or add `?starter=1` if you have a local `/runs/current-study.json` pointer configured).

### 2. Completed Strategy Report
Open [`examples/starter-home-slice/report/report.pdf`](./report/report.pdf) in any PDF viewer, or open [`examples/starter-home-slice/report/report.html`](./report/report.html) in your browser.
