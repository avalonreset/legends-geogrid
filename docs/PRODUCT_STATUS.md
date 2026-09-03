# Product Status

## Release state

Legends GeoGrid 0.1.0 is a usable local-first scanner and reference implementation.

Today it can:

- Run a no-credential browser demo with a saved real 17 x 17 proof scan.
- Switch between rank pins, a heat view, and point-level evidence.
- Estimate single or bulk scan cost without making an API call.
- Execute fresh DataForSEO scans only after `--execute` and a sufficient `--confirm-cost-usd` ceiling are supplied.
- Cache bulk scans by their full request identity and skip fresh matches.
- Write raw receipts, parsed JSON, Markdown, HTML, JSONL, and CSV artifacts locally.

## Honest limitations

- The browser studio does not yet load arbitrary run folders; it ships with bundled proof and modeled datasets.
- Business-name matching can be ambiguous. CID, place ID, or domain matching is recommended for paid work.
- Queue polling is synchronous and sequential after batched submission.
- The cache index is JSON, not transactional storage.
- There are no schedules, historical trend charts, multi-user accounts, hosted service, or support SLA.
- Generated reports need a separate print-to-PDF step.

## Proof dataset

The bundled Home Slice Pizza dataset is a historical demonstration scan for `pizza` in Austin, collected June 26, 2026:

- Grid: 17 x 17 / 289 coordinate tasks.
- DataForSEO method: Standard Queue.
- Historical reported raw API cost: $0.1734.
- Found: 225 of 289 points.
- Top 3: 100 of 289 points.
- Top 10: 201 of 289 points.
- Average rank where found: 4.97.

It is not a claim about current rankings.

## Recommended next milestone

Load any saved `parsed-grid.json` into the browser studio, then add SQLite-backed campaign history. That closes the most important gap between the working CLI and the working visualization without turning the project into a hosted SaaS.
