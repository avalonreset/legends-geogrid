# legends-geogrid agent instructions

legends-geogrid is an open-source google maps rank checker. Preserve that
lowercase positioning and the approved Legends banner style.

## Setup and dependencies

- Offline report: install `requirements-report.txt`, then run the README's
  synthetic report example. No provider credentials or API spending are needed.
- Browser demo: `pnpm install --frozen-lockfile`, then `pnpm dev`.
- Fresh scans: install `requirements-dataforseo.txt`. This installs the public
  [legends-dataforseo-kit](https://github.com/avalonreset/legends-dataforseo-kit)
  dependency. Run `python tools/geogrid_doctor.py --dataforseo` before collection.
  Release 0.3.2 pins kit v0.4.0 by immutable commit. Install the declared
  requirement rather than choosing an untested latest version independently.
  Do not install an MCP server or copy a second HTTP/authentication client.
- Credentials: `DATAFORSEO_LOGIN` (or `DATAFORSEO_USERNAME`) and
  `DATAFORSEO_PASSWORD`. Never print, commit, or embed credentials in reports.

## Research and collection

Read root `SKILL.md`, `docs/START_A_STUDY.md` and `docs/STUDY_CONTRACT.md` before collection.
Default to 3-5 distinct evidence-backed search themes, one representative query
per theme, following `docs/QUERY_SELECTION_POLICY.md`. Fewer requires a cited
explanation and focused scope; never pad with synonyms.
Given only a business, research and select queries from website, public GBP and
DataForSEO evidence; do not ask users to supply keywords by default. Use
`tools/study.py` for researched studies. Raw runners require explicit `--diagnostic`.
Read `docs/START_A_STUDY.md` before paid collection. Establish business identity,
query, location, language and the decision being studied. Estimate first. Paid
scans require both `--execute` and `--confirm-cost-usd`; retain these gates.
Use the kit for provider access and the GeoGrid runners for sampling/caching.
Never describe advisory estimates as a provider-enforced billing limit.

## Verification and publishing

Run `pnpm check` for code changes after installing report dependencies. Test the
shared transport with fixtures; no paid call is necessary for ordinary tests.
Preserve full basemaps and attribution. Inspect every final report page.
Keep user run folders and private reports out of commits. Maintain the distinction
between measured ranks, missing evidence, business hypotheses and recommendations.

## Street maps

Real report observations default to OpenFreeMap street maps (no API key).
Install `requirements-basemaps.txt` and run `python -m playwright install chromium`;
check `python tools/geogrid_doctor.py --reports --basemaps` before rendering.
See `docs/BASEMAPS.md`. Do not silently switch a failed real map to a schematic.
Synthetic examples remain offline. Google imagery is optional and requires
`GOOGLE_MAPS_API_KEY` plus explicit `--allow-google-maps-charge`; never expose the key.
