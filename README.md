<a id="top"></a>

<p align="center"><img src="assets/banner.webp" width="100%" alt="legends-geogrid: an open source local rank tracker and Google Maps rank checker that maps every search point around a business"></p>

# legends-geogrid: an open source local rank tracker that maps every search point instead of reporting one number

[![release](https://img.shields.io/github/v/release/avalonreset/legends-geogrid?label=release&sort=date&style=flat-square&labelColor=000000&color=ff0000)](https://github.com/avalonreset/legends-geogrid/releases/latest)
[![checks](https://img.shields.io/github/actions/workflow/status/avalonreset/legends-geogrid/ci.yml?branch=main&label=checks&style=flat-square&labelColor=000000)](https://github.com/avalonreset/legends-geogrid/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-ff0000?style=flat-square&labelColor=000000)](#reference)
[![License: MIT](https://img.shields.io/badge/license-MIT-ff0000?style=flat-square&labelColor=000000)](LICENSE)

Home Slice Pizza ranks in the top three at 549 of 1,249 search points around Austin for one search, and at 21 of them for another. Ask a single-point rank tracker where that business stands on Google Maps and it gives you one number that hides the other 1,248 neighborhoods.

**The human is the controller. The agents do the operating.**

`legends-geogrid` turns your coding agent into a local rank tracker, circular-lattice Google Maps study engine, Street View signage auditor, and 19-page vector PDF strategy studio. Clone the repository or install it through [`cto-legends`](https://github.com/avalonreset/cto-legends), and the complete 1,249-point Austin pizza territory opens in your browser with no API keys and zero spend.

**Specification & local visibility guide:** [cto-legends.com/modules/legends-geogrid](https://cto-legends.com/modules/legends-geogrid) · [The 60-Minute AI Visibility Audit and Fix Scorecard](https://cto-legends.com/blog?post=ai-visibility-audit)

<p align="center"><img src="assets/cards/r1/slot-1-agent-handoff.svg" width="100%" alt="Agent handoff: paste this into Claude Code, Codex, or any coding agent and it does the setup"></p>

```text
Use cto-legends to install legends-geogrid, then open the example pizza map
so I can explore it without spending credits.
```

<p align="center"><img src="assets/cards/r1/slot-2-three-pillars.svg" width="100%" alt="Three pillars of legends-geogrid: 01 Circular territory lattice, 02 Interactive and PDF studio, and 03 Street View signage audit"></p>

[Plain english](#hand-this-local-seo-tool-to-your-agent-in-plain-english) · [1,249 ranks](#you-do-not-have-a-rank-you-have-1249-of-them) · [Measurement honesty](#a-google-maps-rank-checker-has-to-show-its-measurements) · [In the box](#in-the-box) · [Views & viewer](#views) · [Cost](#cost) · [Boundaries](#boundaries) · [FAQ](#faq) · [Reference](#reference)

---

## Hand this local SEO tool to your agent in plain english

None of this asks you to memorize command flags. You describe what you want in plain english, and [`cto-legends`](https://github.com/avalonreset/cto-legends) routes the job to `legends-geogrid` and its sibling modules.

<p align="center"><img src="assets/cards/r1/slot-3-plain-english-chains.svg" width="100%" alt="Say the job in plain words: four spoken requests routing directly into legends-geogrid territory studies"></p>

Start with the free part. Say **"Open the example pizza map"** and your agent builds one self-contained HTML file and opens it in your browser, with no server running, no port open, and no account anywhere.

Then name a business. Your agent reads its website, its public Google Business Profile, and live search demand, and comes back with a proposal: the 3 to 5 search themes it would study, the circular lattice of points, and the exact dollar cost ceiling.

Nothing is bought until you approve that proposal. After you do, the points are collected at raw provider rates, every response is cached on your disk with SHA-256 verification, and an interrupted run resumes from its local ledger without paying twice.

If you have ever had to explain why a business looks number one from its own front counter and vanishes two miles down the road, flip between the four searches on the bundled Austin map and star the repo if the territory changes your answer. Prefer to watch first? The [31-minute walkthrough](https://www.youtube.com/watch?v=0G7IF3yBxcM) runs the whole study on screen.

---

## You do not have a rank. You have 1,249 of them

Stand at the front counter of a pizza shop on South Congress Avenue and search for pizza. Now drive two miles, run the same search, and a different list comes back.

Ask where a business ranks on Google Maps and the only accurate answer is two more questions. Ranked from where, and for which search?

Google answers a map search from the coordinate where the searcher is standing. Change two words in the query and the list shifts again.

The study bundled with this repository measured that around one real restaurant using public Google Maps results. Home Slice Pizza sits on South Congress in Austin, and 1,249 search points surround it on a 10-mile circle, half a mile apart, each one running the same four searches thirty results deep.

For "new york style pizza," Home Slice ranks in the top three at 549 of those points. For "pizza by the slice," it is 470. On "pizza restaurant," the count is 21. Under "pizza takeout," it is 6.

<p align="center">
  <img src="examples/starter-home-slice/report/map-001.png" width="49%" alt="Rank map for the search pizza restaurant: Home Slice Pizza is top three at 21 of 1,249 search points around Austin">
  <img src="examples/starter-home-slice/report/map-002.png" width="49%" alt="Rank map for the search new york style pizza: Home Slice Pizza is top three at 549 of 1,249 search points around Austin">
</p>
<p align="center"><sub>Left: "pizza restaurant," top three at 21 of 1,249 points and top ten at 261. Right: "new york style pizza," top three at 549 and top ten at 1,023. One business, one collection, one set of search controls.</sub></p>

So which one is its rank? Any single number has to pick one of those maps and throw the others away. It also throws away the two things an owner can act on: the neighborhood and the search theme. "We rank number four" tells nobody which streets to defend or which service page to write.

<p align="center"><img src="assets/cards/r1/slot-4-circular-vs-square.svg" width="100%" alt="Why circular territory geometry beats square rank grids: The Square Grid Trap (+41% corner stretch) versus True Circular Lattice in legends-geogrid"></p>

That is why `legends-geogrid` reports territory on a true circular lattice clipped by distance from the business. In a traditional square grid, the four corners sit 41 percent farther from the storefront than the top, bottom, left, or right edges, skewing visibility scores toward distant corner zip codes.

The searches are selected as carefully as the coordinates. A study covers 3 to 5 researched themes with one representative query each, chosen from the business's website, its public Google profile, and real search demand, never padded with synonyms.

---

## A Google Maps rank checker has to show its measurements

Maps are persuasive, and that makes a wrong one expensive. This repository keeps a written record of the day one of its own maps misled.

In one regional HVAC study, a recurring competitor disappeared along a perfectly straight line. Markets do not end in straight lines, so on October 18, 2026 a diagnostic went back to four existing points with four searches under three settings: 48 Standard requests, $0.0288.

At one of those points, with the "Search this area" viewport restriction on, the competitor was missing from all four top-30 responses. Switch the restriction off and it came back at positions 5, 14, 8, and 10. That straight edge was a search setting masquerading as the market.

Three rules came out of those 48 requests, and the engine enforces them automatically:

- **Open search is the default.** The collector sends every point with the viewport restriction off, and a restricted plan is rejected unless it states the displayed-area question it is asking.
- **Missing is never drawn as losing.** A point with incomplete evidence cannot appear on the map as "not ranked."
- **Blanks stay blank.** No rank is invented or interpolated to make the picture look finished, and the soft diamonds between markers are visual blending, never extra searches.

You can read those rules straight off the canvas. Every measured rank is an eight-sided stop sign: cyan at first place through green to yellow at tenth, then red fading out toward thirtieth. A hollow outline means the business was absent from a complete top 30, and a dashed outline means the evidence is incomplete.

Before a study expands past an edge that looks suspiciously clean, your agent reruns paired points on both sides under different settings and keeps each setting as its own run so ranks are never patched together.

Collection travels through [`legends-dataforseo`](https://github.com/avalonreset/legends-dataforseo), the sibling module that dispatches each request to DataForSEO's Standard Queue for Google Maps. The collector never switches to the pricier Live mode on its own, and every paid command requires both an explicit execute flag and a dollar ceiling before opening a network connection.

---

## Territory campaigns, Local Leaders and the Street View signage audit

Finished studies open as interactive views. **Local Leaders** shows who holds first place in each neighborhood with distinct neighbor colors, and **Campaigns** splits your map into **Defend** (ranks 1 to 3), **Advance** (ranks 4 to 10), and **Build** (ranks 11 to 30) zones, while points where the business is absent from the top 30 sit in their own **Outside top 30** band.

<p align="center">
  <img src="assets/companion-local-leaders.webp" width="49%" alt="Local leaders view: first-place winners shown as colored territories across 1,249 Austin search points">
  <img src="assets/companion-campaigns.webp" width="49%" alt="Campaigns view: Defend, Advance and Build zones for the selected business">
</p>

Another view audits competitor business names. When a first-place holder's title looks packed with extra keywords, your agent refreshes that exact profile, reads the branding on its website, pulls outdoor Street View from up to three angles aimed at the building, and, with [`legends-jev`](https://github.com/avalonreset/legends-jev) installed, reads the physical lettering on the storefront sign.

Two Austin profiles in the bundled study share one title, "Pedroso's Pizza- Slice Shop & Take Out," while the website brand is simply Pedroso's Pizza. On Airport Boulevard the physical logo badge really does carry the words SLICE SHOP and TAKE OUT, so that profile rates 2 of 5 across its 61 first-place wins. At Justin Lane no storefront sign has confirmed the extra words yet, so the same title rates 4 of 5 across 124.

<p align="center">
  <img src="assets/companion-keyword-stuffing.webp" width="49%" alt="Keyword stuffing view: first-place profiles rated 0 to 5 for name concern, with the evidence beside each rating">
  <img src="assets/companion-photo-lightbox.webp" width="49%" alt="Photo Lightbox: a storefront capture opened at full size for a closer read of the sign">
</p>

Same title, different physical evidence, different rating. A human still validates each reading, and the tool never files an edit or a complaint with Google on your behalf.

<p align="center"><img src="assets/cards/r1/slot-5-saas-vs-geogrid.svg" width="100%" alt="Comparison: Monthly local rank SaaS versus Your own territory engine with legends-geogrid"></p>

Looking for an open source Local Falcon alternative? Here is the trade. There is no hosted subscription dashboard and nothing runs behind your back on a schedule; in exchange you pay raw provider data costs (all 4,996 searches in the 10-mile Austin study cost $2.9976 in data, and a 5-mile study at the same spacing is 309 points and 1,236 searches, about $0.74), keep every raw response on your own disk, and can inspect the evidence behind every pin.

Watch the entire Austin study run on screen in the 31-minute walkthrough below:

<p align="center"><a href="https://www.youtube.com/watch?v=0G7IF3yBxcM"><img src="assets/youtube-walkthrough.webp" width="100%" alt="Watch the 31-minute walkthrough of the Austin pizza study on YouTube"></a></p>

---

<a id="in-the-box"></a>

## In the box

Everything in this table ships with the repository, collected on October 19, 2026 from public Google Maps results. Open it before you configure anything.

| Bundled Austin study | What you get |
| --- | --- |
| Business | Home Slice Pizza, 1415 S Congress Ave, Austin, TX (a public-data case study) |
| Footprint | 10-mile radius, 0.5-mile spacing, 1,249 search points |
| Searches | pizza restaurant, new york style pizza, pizza by the slice, pizza takeout |
| Observations | 4,996 point-and-search results, each to depth 30 |
| Field | 702 business profiles observed |
| Name check | 165 first-place profiles refreshed and screened, 79 recurring leaders individually rated 0 to 5 |
| Report | 19-page vector PDF plus a standalone HTML edition |
| Cost to open | No keys, no account, $0.00 |

Read the finished report at [`examples/starter-home-slice/report/report.pdf`](examples/starter-home-slice/report/report.pdf) and the study guide at [`examples/starter-home-slice/README.md`](examples/starter-home-slice/README.md).

<a id="views"></a>

## Views and the embeddable viewer

| View | The question it answers |
| --- | --- |
| Local leaders | Who holds first place in each neighborhood, with adjacent winners kept in clearly different colors |
| Rankings | Where the business ranks at every point, 1 through 30, for the selected search |
| Keyword stuffing | Whether a first-place holder's profile name matches its website and its real storefront sign |
| Campaigns | Which ground to Defend (ranks 1 to 3), Advance (ranks 4 to 10) or Build (ranks 11 to 30). Points absent from the top 30 sit in their own Outside top 30 band |
| Strategy Room | What the selected area, its rank context and the campaign plans say, in a side panel beside the map, with head-to-head comparisons between two profiles |
| Photo Lightbox | What the storefront photo, Street View capture or logo shows at full size |
| Strategy report | How the whole study reads on paper, as a vector PDF and HTML report with maps and scorecards |

<p align="center">
  <img src="assets/companion-rankings.webp" width="49%" alt="Rankings view: the selected business's rank at every search point for one search">
  <img src="assets/companion-strategy-room.webp" width="49%" alt="Strategy Room panel open beside the map with area context and campaign plans">
</p>

### Embeddable report viewer (`GeoGridViewer.mount`)

Running `pnpm build:viewer` also builds a standalone, Content Security Policy safe report viewer in `dist-viewer/` (`geogrid-viewer.js`, `geogrid-viewer.css`, and `geogrid-viewer-worker.js`). Mounted with `GeoGridViewer.mount(element, model, options)`, it renders the rank pin map, scores, zone statistics, competitor table, and change since the previous scan from a lean `geogrid-viewer/v1` model or a full `geogrid-companion/v1` study. With `perPointListings` enabled on a full study, the **Location** tab lists every captured ranking at the selected coordinate (top 20 first with a show-all toggle and the primary business pinned even beyond rank 20), and the **Competitors** tab lists every business seen across the grid and recolors the map to any competitor you select. See [`docs/VIEWER.md`](docs/VIEWER.md) and [`docs/viewer-model.md`](docs/viewer-model.md).

<a id="cost"></a>

## Cost

Fresh studies bill directly to your own DataForSEO account at wholesale provider task rates. This tool adds zero markup.

| Study | Search tasks | Standard Queue data cost |
| --- | --- | --- |
| Bundled Austin study | 4,996, already collected | $0.00 to open |
| 5-mile radius, 0.5-mile spacing | 309 points x 4 searches = 1,236 | about $0.74 |
| 10-mile radius, 0.5-mile spacing | 1,249 points x 4 searches = 4,996 | about $3.00 |
| Name check on 165 first-place profiles | 165 profile refreshes | about $0.25 |

Rates in the code: $0.0006 per Standard Queue Maps search at depth 30, $0.0012 for Priority, $0.0020 for Live, and $0.0015 per profile refresh. Check the preflight estimate and the provider's current pricing before approving a run. Every DataForSEO command requires both `--execute` and `--confirm-cost-usd <ceiling>` and aborts before any network call if the estimate exceeds your ceiling.

<a id="ask-your-agent"></a>

## Ask your agent

| Say this | What your agent does |
| --- | --- |
| "Open the example pizza map so I can explore it without spending credits." | Runs `python tools/study.py --open`, builds a static Companion file, and opens it. No keys, no network calls. |
| "Study `<business name>` on Google Maps." | Researches the website, public profile, and search demand, proposes 3 to 5 search themes, shows the circular lattice and cost ceiling, and waits for your approval. |
| "Check why a competitor disappears along a straight line on the east edge of our map." | Reruns paired points on both sides of the edge with the search restriction on and off, saves that as a separate diagnostic run, and reports who comes back. |
| "Check the first-place holders in this study for keyword stuffing and read their signs." | Refreshes exact profiles through the Standard Queue, captures website branding and multi-angle Street View, and runs the optional `legends-jev` sign check. |
| "Expand this study out to 10 miles." | Plans the larger circle at the same spacing with `radius_sampling.py`, collects only the new outer points on the Standard Queue within your approved budget, composes one complete 10-mile study from the saved scans, and banks it as an expansion of the original. |
| "Render the report." | Builds the vector PDF and HTML strategy report and runs page-by-page layout checks on the result. |

Full agent instructions live in [`AGENTS.md`](AGENTS.md) and [`docs/STUDY-RECIPE.md`](docs/STUDY-RECIPE.md).

## Zero-Keys Hosted Option ($10 PAYG)

Want a local rank grid and a client-ready PDF without wiring up data sources?

This module is free, MIT licensed, and runs on your own accounts. That does not change.

If you would rather not manage provider accounts or API keys at all, [CTO Legends Recon](https://cto-legends.com/recon) is a separate hosted MCP server that answers the same kind of questions from one endpoint:

- One URL and one API key. Works in Claude Code, Cursor, Antigravity, Claude Desktop, and OpenCode
- Pay as you go from a $10 prepaid wallet. No subscription
- From $0.05 a run. Anything above your limit is quoted first
- Failed runs and 24-hour repeats cost $0.00

```bash
claude mcp add --transport http recon-concierge https://recon.cto-legends.com/mcp --header "Authorization: Bearer YOUR_API_KEY"
```

Create a key at [recon.cto-legends.com](https://recon.cto-legends.com/login). Prefer to self-host? Keep reading. Everything below needs nothing from us.

<a id="boundaries"></a>

## Boundaries

- Hosted dashboards, white-label portals, and background scheduled tracking are out of scope. You run it locally, and nothing runs in the background behind your back.
- API keys are never bundled. Fresh scans use your own DataForSEO account.
- Profile edits and competitor complaints are never submitted to Google for you.
- Rank share is never converted into invented revenue, call volume, or conversion claims.
- "Not returned" means absent from this top-30 Maps response under the recorded settings. It is not proof of invisibility in every Google experience.
- Results describe Google Maps searches at a recorded zoom and depth. They are not presented as personalized, organic-web, or local-pack rankings.
- Turning the "Search this area" restriction off widens what comes back. It does not guarantee that every business appears.
- Name check ratings are research findings for a person to validate, never an automated violation verdict.

<a id="faq"></a>

## FAQ

<details><summary><strong>How does a local rank tracker measure a whole territory?</strong></summary>

<br>

Position decides the answer on Google Maps, so one check from a city center describes one spot. This tool searches from hundreds of points on a true circle around the business (309 at five miles and 1,249 at ten with half-mile spacing) and records the top 30 at each coordinate.

</details>

<details><summary><strong>Is this an open source Local Falcon alternative?</strong></summary>

<br>

Yes, if you would rather run the study yourself. Local Falcon is a hosted product, while this is MIT-licensed code that runs on your machine with your own DataForSEO account and leaves every raw response on your disk. It is independent software, not affiliated with or endorsed by Local Falcon.

</details>

<details><summary><strong>Can I try this Google Maps rank checker without API keys?</strong></summary>

<br>

Keys are optional for the first look. The full Austin study and its 19-page report ship in the repo, and `python tools/study.py --open` opens them with no account and no spend.

</details>

<details><summary><strong>Which searches does this local SEO tool study?</strong></summary>

<br>

Usually 3 to 5 researched themes, with one representative query per theme. Fewer needs a stated reason, and synonyms are never added to pad the count.

</details>

<details><summary><strong>Does it track rankings on a schedule?</strong></summary>

<br>

No. Tracking over time means banking a baseline study and running a monitoring study when you want a new reading, linked in the study library with `--relationship monitoring`.

</details>

<details><summary><strong>What does the keyword stuffing check conclude?</strong></summary>

<br>

Each individually reviewed profile gets a 0 to 5 concern rating tied to its exact current title, with sources, timestamps, and counterevidence kept. It is a research finding for human review, and missing evidence stays unscored.

</details>

<details><summary><strong>What are the diamonds between the markers?</strong></summary>

<br>

Visual blending only. A diamond mixes the colors of the four measured points around it and is never an extra search or a predicted rank.

</details>

<a id="setup"></a>
<a id="family"></a>
<a id="reference"></a>

---

## Reference

Everything you need to run `legends-geogrid` through your coding agent is in the guide above. Open these drawers for the CLI command reference, environment setup, disk layout, and attribution details.

<details><summary><strong>CLI reference and agent setup (click to expand)</strong></summary>

<br>

### Agent setup (via `cto-legends`)

Part of the [`cto-legends`](https://github.com/avalonreset/cto-legends) ecosystem. `cto-legends` is the only registered agent skill; this repository vendors a pinned copy at [`skills/cto-legends/SKILL.md`](skills/cto-legends/SKILL.md). Do not register this module as its own standalone skill folder.

| Module | Its job in a study |
| --- | --- |
| [cto-legends](https://github.com/avalonreset/cto-legends) | The router. Previews and installs this module, then loads its recipe with `cto-legends handoff legends-geogrid`. |
| [legends-dataforseo](https://github.com/avalonreset/legends-dataforseo) | Carries Maps searches, search demand checks, and profile refreshes to DataForSEO. |
| [legends-jev](https://github.com/avalonreset/legends-jev) | Optional. Reads storefront signs in profile photos and Street View captures for the name check. |

```sh
python -m pip install cto-legends
cto-legends install legends-geogrid
cto-legends install legends-geogrid --apply
cto-legends handoff legends-geogrid

git clone https://github.com/avalonreset/legends-geogrid.git
cd legends-geogrid
python tools/study.py --open
```

Python 3.11 or newer is all the free map needs. Fresh scans, report rendering, and street basemaps each add one requirements file, and one offline doctor command checks all of it:

```sh
python -m pip install -r requirements-dataforseo.txt -r requirements-report.txt -r requirements-basemaps.txt
python -m playwright install chromium
python tools/geogrid_doctor.py --dataforseo --jev --reports --basemaps --check-playwright --json
```

Commands marked "Both gates" spend nothing unless `--execute` and `--confirm-cost-usd <ceiling>` are both passed. Every `tools/study.py` subcommand also accepts `--vault-dir`.

| Command | What it does | Spend |
| --- | --- | --- |
| `python tools/study.py --open` | Builds and opens the static Companion. Options: `--study`, `--research`, `--name-review`, `--output`, `--no-browser`, `--pdf`. | None |
| `python tools/study.py website --url <url> --output <file>` | Fetches public business website context over HTTPS. | None |
| `python tools/study.py lookup --query <query> --output-dir <dir>` | Looks up the business identity (CID and place ID) before collection. Options: `--near`, `--tier`. | No DataForSEO spend |
| `python tools/study.py research --request <json> --output-dir <dir>` | Runs search demand research and writes a research ledger. `--allow-live` is an explicit opt-in. | Both gates |
| `python tools/study.py query-review --plan <plan.json>` | Audits search themes, categories, and observation age before collection. | None |
| `python tools/study.py validate --plan <plan.json>` | Validates the study contract. Writes nothing. | None |
| `python tools/study.py proposal --plan <plan.json> --output-dir <dir>` | Renders the pre-collection proposal with points, searches, and cost ceiling. | None |
| `python tools/study.py run --plan <plan.json> --output-dir <dir>` | Validates, then collects and banks checkpoints. | Both gates |
| `python tools/study.py assemble --run-dir <dir> --output-config <file>` | Assembles `report-config.json` from a run directory. | None |
| `python tools/study.py battlefield --run-dir <dir> --output-dir <dir>` | Writes the offline territory model, console, and report. | None |
| `python tools/study.py enhance --run-dir <dir> --output-dir <dir>` | Adds detail inside an existing square grid without changing its extent (5 x 5 becomes 9 x 9). Reuses fresh banked observations and collects only the added points through Maps Live. | Both gates |
| `python tools/study.py bank --plan <plan.json>` | Banks artifacts into the study library with SHA-256 hashes. `--relationship baseline`, `expansion`, or `monitoring`. | None |
| `python tools/study.py library-init` | Initializes the study library. | None |
| `python tools/competitive_sampling.py --battlefield <model>` | Plans an irregular exploratory footprint around the business and its rivals: citadels, corridor midpoints, 3x3 micro-grids, and compass sentinels. | None |
| `python tools/competitive_collect.py --plan <plan.json> --output-dir <dir>` | Collects Google Maps results on the Standard Queue. `--allow-live` is an explicit opt-in. | Both gates |
| `python tools/competitive_export.py --run-dir <dir> --output <file> --compact` | Exports a `geogrid-companion/v1` dataset for the Companion. | None |
| `python tools/business_name_review.py plan` | Lists first-place profiles and estimates the refresh cost. | None |
| `python tools/business_name_review.py submit` | Submits Standard Queue profile refreshes. | Both gates |
| `python tools/business_name_review.py retrieve`, `websites`, `photos`, `export`, `attach` | Retrieves results, captures branding and photos, exports the review, and attaches it to the study. `photos --jev` adds the sign check. | No DataForSEO spend |
| `python tools/strategy_report.py --config <report-config.json> --output-dir <dir>` | Renders the vector PDF and HTML report with layout QA. `--basemap`, `--proof`, `--require-pdf-qa`. | No DataForSEO spend |
| `python tools/geogrid_doctor.py` | Offline readiness check. `--reports`, `--dataforseo`, `--jev`, `--basemaps`, `--check-playwright`, `--json`. | None |
| `python tools/radius_sampling.py` | Calculates a circular lattice and its cost estimate, for a new study or a radius expansion. | None |
| `python tools/radius_compose.py` | Composes one complete radius study from saved scans, such as an inner study plus a newly collected outer ring. Makes no paid requests. | None |
| `python tools/sampling_review.py` | Reviews sampling adequacy and boundary cliffs after measurement. | None |
| `python tools/verify_pins.py` | Verifies report pins against the raw results. | None |
| `python tools/pollution_gate.py` | Probes spread points to reject a polluted keyword. Calls Live directly. | Both gates |
| `pnpm dev`, `pnpm build`, `pnpm build:viewer`, `pnpm test`, `pnpm check` | UI development server, production build, standalone CSP-safe viewer bundle, Python/Node tests, and the full local check suite. | None |

Raw single-grid and batch runners (`tools/local_heatmap_poc.py`, `tools/bulk_geogrid_runner.py`, `tools/adaptive_geogrid.py`) also require an explicit `--diagnostic` flag before they will execute. Basemap imagery from Google is optional in reports and needs your own key plus `--allow-google-maps-charge`. Street maps default to OpenFreeMap with no key.

</details>

<details><summary><strong>Disk layout, verification and license (click to expand)</strong></summary>

<br>

Where things land:

- `runs/` and `bulk-runs/` hold fresh run folders and are ignored by Git.
- Static Companion builds from `python tools/study.py --open` land at `runs/starter-home-slice/companion.html`.
- Report directories hold `report.pdf`, `report.html`, `report-model.json`, `report-qa.json`, `sampling-review.json`, `leaders-map.png`, and one `map-NNN.png` per search.
- `~/.legends-geogrid/vault/GeoGrid` is the study library, movable with `--vault-dir` or `GEOGRID_VAULT_DIR`. It keeps a catalog, one folder per business, and a hashed manifest per study revision.

Verification:

- `pnpm check` runs the dependency audit, build, Python and viewer tests, the report doctor, a sample dry run, and the report smoke test.
- `report-qa.json` is the page-by-page layout receipt for every rendered report.
- Pin checks run through `python tools/verify_pins.py` against the raw results.

Credentials and guardrails:

- DataForSEO credentials are read from the environment: `DATAFORSEO_LOGIN` or `DATAFORSEO_USERNAME`, plus `DATAFORSEO_PASSWORD`. `tools/pollution_gate.py` reads only `DATAFORSEO_LOGIN`, so set that name if you run it. The optional sign check reads `TYPESAFE_API_KEY` or an explicit `--typesafe-api-key-file`.
- Secrets are never printed, logged, or embedded in a report.
- Symlink paths are refused on file inputs, key files, and output paths.
- Agent instructions require ordinary visible processes, with no hidden consoles and no hidden background dev servers.

Only public Maps observations, public profile metadata, and public website branding excerpts are in the bundled starter study. It holds no credentials and no account identifiers.

License and attribution:

- MIT licensed. See [LICENSE](LICENSE), [CONTRIBUTING.md](CONTRIBUTING.md), and [SECURITY.md](SECURITY.md).
- [Leaflet](https://github.com/Leaflet/Leaflet) provides the interactive map library, and [OpenStreetMap](https://www.openstreetmap.org/copyright) ([github.com/openstreetmap](https://github.com/openstreetmap)) contributors provide the default map data.
- Optional Google Maps and Google Business Profile APIs for new scans come from [DataForSEO](https://dataforseo.com/apis/serp-api/google-maps-api) ([github.com/dataforseo](https://github.com/dataforseo)).
- [Vite](https://github.com/vitejs/vite) and [PostCSS](https://github.com/postcss/postcss) are the MIT-licensed build tools; production builds generate `dist/third-party-licenses.md`.
- [Claude SEO](https://github.com/AgriciDaniel/claude-seo) by Daniel Agrici contributes the vendored reference skills under `third_party/claude-seo/`.
- [ReportLab](https://www.reportlab.com/) and [Pillow](https://python-pillow.org/) power local PDF generation and image processing.
- Complete detail is in [docs/PROVENANCE.md](docs/PROVENANCE.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Independence note: `legends-geogrid` is not affiliated with or endorsed by DataForSEO, Google, OpenStreetMap, Leaflet, [Local Falcon](https://github.com/local-falcon), [Search Atlas](https://github.com/search-atlas-group), or [BrightLocal](https://github.com/BrightLocal).

</details>

<details><summary><strong>Documentation map (click to expand)</strong></summary>

<br>

- [`AGENTS.md`](AGENTS.md): agent instructions, the free demo launch, and the spend-gate rules.
- [`docs/AGENT-RECIPE.md`](docs/AGENT-RECIPE.md), [`docs/STUDY-RECIPE.md`](docs/STUDY-RECIPE.md), and [`docs/START_A_STUDY.md`](docs/START_A_STUDY.md): discovery, search selection, collection, and export from end to end.
- [`docs/QUERY_SELECTION_POLICY.md`](docs/QUERY_SELECTION_POLICY.md) and [`docs/STUDY_CONTRACT.md`](docs/STUDY_CONTRACT.md): how the 3 to 5 search themes are chosen and validated.
- [`docs/SEARCH_WINDOW_POLICY.md`](docs/SEARCH_WINDOW_POLICY.md) and [`docs/COMPETITIVE_SAMPLING.md`](docs/COMPETITIVE_SAMPLING.md): the straight-edge diagnostic, open search, circular sampling, and radius expansion.
- [`docs/COMPANION.md`](docs/COMPANION.md), [`docs/VIEWER.md`](docs/VIEWER.md), and [`docs/viewer-model.md`](docs/viewer-model.md): every map view, color rule, marker state, and the standalone CSP-safe embeddable viewer.
- [`docs/BATTLEFIELD_INTELLIGENCE.md`](docs/BATTLEFIELD_INTELLIGENCE.md): the Strategy Room, territory campaigns, and head-to-head comparisons.
- [`docs/BUSINESS_NAME_REVIEW.md`](docs/BUSINESS_NAME_REVIEW.md): the name check rubric and its evidence limits.
- [`docs/ENHANCE.md`](docs/ENHANCE.md) and [`docs/STUDY_LIBRARY.md`](docs/STUDY_LIBRARY.md): adding detail inside an existing grid at the same extent, and how baselines, expansions, and monitoring studies are linked in the study library.
- [`docs/BASEMAPS.md`](docs/BASEMAPS.md) and [`docs/TECHNICAL_NOTES.md`](docs/TECHNICAL_NOTES.md): street maps, optional Google tiles, and cache verification.

</details>

---

## Start here

Paste the [agent handoff block](#top) at the top of this page into your coding agent, open the 1,249-point Austin pizza territory map in your browser, and see what a true circular Google Maps rank study looks like before spending a cent.

<p align="center"><a href="https://github.com/stars/avalonreset/lists/cto-legends"><img src="assets/cards/r1/slot-collection-star-shrine.svg" width="100%" alt="GitHub Star List: The complete cto-legends collection on one page. Bookmark or star the router and every module from a single GitHub list."></a></p>

Running a multi-location business or agency and want circular-lattice territory intelligence and Street View signage dossiers applied directly to your markets? Message Avalon Reset at [cto-legends.com/dm](https://cto-legends.com/dm). The desk is async, so the conversation starts the moment you write and nobody forces you onto a sales call.

<p align="center"><a href="https://cto-legends.com/dm"><img src="assets/cards/r1/slot-7-message-avalon-reset.svg" width="100%" alt="Want this way of working applied to your own stack? Message Avalon Reset at cto-legends.com/dm"></a></p>

---

**Specification & benchmarks on cto-legends.com:**
- **Module specification & architecture matrix:** [cto-legends.com/modules/legends-geogrid](https://cto-legends.com/modules/legends-geogrid)
- **Related engineering dispatches:** [The 60-Minute AI Visibility Audit and Fix Scorecard](https://cto-legends.com/blog?post=ai-visibility-audit) · [How to Choose MCP vs CLI Tools Without Context Bloat](https://cto-legends.com/blog?post=mcp-vs-cli) · [AI Agent Governance: Markdown Knowledge Base & Vault Architecture](https://cto-legends.com/blog?post=ai-agent-governance)
- **Ecosystem hub:** [cto-legends.com/home](https://cto-legends.com/home)
