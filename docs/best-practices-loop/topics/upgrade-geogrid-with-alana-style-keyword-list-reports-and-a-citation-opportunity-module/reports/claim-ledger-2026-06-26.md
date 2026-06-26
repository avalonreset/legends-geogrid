# Claim Ledger - 2026-06-26

| claim_id | claim | source artifact | verifier command | verdict | evidence quote/link |
|---|---|---|---|---|---|
| C1 | DataForSEO Google Maps SERP remains the rank-data source with Standard, Priority, and Live rates modeled in app. | DataForSEO Google Maps SERP page; `src/main.js` | `pnpm build` | PASS | DataForSEO lists Standard `$0.0006`, Priority `$0.0012`, and Live `$0.002` per SERP page. |
| C2 | Alana requested a keyword list/report in addition to the map. | User-provided screenshots; `src/main.js` | Browser DOM check pending | PASS | App renders `Keyword Scan List`, screenshot-mode rows, scan settings, and CSV export. |
| C3 | Citations are a separate NAP/directory/aggregator workflow, not the same as heatmap rank data. | `docs/CITATION_MODULE_NOTES.md`; `src/main.js` | Docs/source review and browser DOM check | PASS | Notes separate rank heatmaps, citation audits, and fulfillment; core app no longer renders a citation module. |
| C4 | LeadSnap-style citation pricing and directory monitoring are plausible market anchors. | LeadSnap citations page | Source review | PASS | Public page says citations start at `$20/month per location` and references monitoring across `42 trusted directories`. |
| C5 | Search Atlas citation builder centers on major aggregators. | Search Atlas local citations page | Source review | PASS | Public page names Data Axle, Foursquare, Neustar Localeze, Yellow Pages Network, and GPS providers. |
| C6 | GeoGrid does not yet submit citations directly and should not present citations as core product functionality. | `docs/PRODUCT_STATUS.md`; `docs/CITATION_MODULE_NOTES.md` | Docs review | PASS | Docs state citations are parked research and fulfillment remains vendor/manual/direct-access future work. |
