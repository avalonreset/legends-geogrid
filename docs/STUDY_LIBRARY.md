# Persistent study library

The study CLI automatically saves local checkpoints for successful research and
website captures, generated proposals, collection startup, each completed lane,
interrupted collector exits, assembly and completed researched reports. No MCP,
Obsidian application or extra provider call is required. Low-level diagnostic
runners do not auto-bank; use the explicit bank command for those saved studies.

## Setup

Default: `~/Documents/legends-geogrid-vault/GeoGrid`. Override with `--vault-dir`,
then `GEOGRID_VAULT_DIR`, then the saved user config. Configure once:

```sh
python tools/study.py library-init --vault-dir /path/to/your/vault
```

This creates a dedicated user config and refuses to overwrite an existing one.
For another destination, use the explicit flag. Never assume the user's vault location. An existing vault needs no conversion or plugins.

## Structure

`GeoGrid/catalog.md` links every checkpoint. Business dossiers are keyed by hashed
Google CID, not fuzzy name. `businesses/<id>/studies/<study>/<revision>/` holds an
immutable Markdown note, hash manifest and portable copies of selected artifacts.
Research collected before business identification is explicitly unassigned; when
a plan identifies the CID its cited sources are also saved under that business.
No automatic identity merge is inferred from a similar business name or address.

Notes contain identity limitations, study intent, selected searches and links to
raw evidence. Final report notes include normalized results, proposed actions and
unknowns. Costs remain in the source receipts: never sum checkpoint copies as new
purchases. No outcomes are invented. Personal edits to dossiers are preserved;
an edited generated catalog is preserved and its regeneration warning is reported.

## Recovery and report attachment

```sh
python tools/study.py bank --plan PATH/study-plan.json --run-dir PATH/run --report-dir PATH/report --stage report-complete
```

Reports generated from the normal `report-config.json` automatically detect the
adjacent `evidence/study-plan.json`. Collection banking is rooted at that plan’s
parent collection folder, never an unrelated configuration directory. Override
with `--study-run-dir` for a nonstandard layout. For other configs use
`strategy_report.py --study-plan PATH --config CONFIG --output-dir NEW_FOLDER`.
Synthetic reports without a research plan are not added to a real business history.
A bank failure must be recovered locally with `bank`, never by repeating paid calls.
Partial acquisition remains partial; saving it does not certify completion.

Link an expansion/monitoring checkpoint using `bank --parent-study STUDY_ID
--relationship expansion` (or `monitoring`). The parent must belong to the same CID.
The [enhance workflow](ENHANCE.md) automatically records this lineage when it
plans and executes same-extent refinement. Manual banking remains available for
separately planned geographic expansions and monitoring studies.

## Integrity and portability

Files are explicitly selected, not a recursive copy of the entire workspace.
No `.env` or credential config is included. Study source hashes must match before
banking. Same artifact set/stage is idempotent; altered archived artifacts produce
an integrity error. A lock prevents concurrent writers and snapshots stage before
becoming visible. Copy the GeoGrid folder to another vault to retain relative links.
Evidence JSON may still contain local provider/output path metadata; the bank does
not claim redaction of arbitrary private source text. Treat the library as private.
Nothing is committed, synced, published or sent externally by this feature.
