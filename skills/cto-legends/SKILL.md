---
name: cto-legends
description: Route ordinary requests to the matching Legends module without per-module skills. Discover, preview, and apply module installs for keyword research, local visibility studies, repository improvement, music and sound effects, OBS recording, voice typing, vault memory, grants, web search, video pulls, ambient capture, and captions. Also use for Legends setup and updates.
---

# cto-legends

This is the single registered skill for the Legends ecosystem. It routes a
user goal to the right module and loads that module recipe on demand. No
module registers its own skill. Every module repo vendors a byte-exact copy
of this file at `skills/cto-legends/SKILL.md`; this copy in the `cto-legends`
router repo is canonical.

Install the router from source:

```sh
git clone https://github.com/avalonreset/cto-legends.git
cd cto-legends
python -m pip install .
```

Start with the user's request, including in an empty working directory. A chat
request is a task specification; do not require a project manifest or a
separate task file to run catalog, status, or readiness. Read this entry point
before unrelated desktop, browser, or community skills for matching Legends
goals.

## Intent first, one registered skill

Do not ask users to name a module or install its skill: this recipe is the
single-skill router. Read the capability directory below and select the
narrowest capability that fits the requested outcome. Module recipes are
ordinary Markdown loaded from their installed source, not separately
registered skills. A question in chat is sufficient context to begin
discovery.

<!-- capability-directory:start -->
| Outcome | Module |
|---------|--------|
| Search and keyword research through DataForSEO. | `legends-dataforseo-kit` |
| Google Maps ranking grids and local visibility research. | `legends-geogrid` |
| Research search demand and improve repository copy, metadata, presentation, and releases. | `legends-github` |
| Create instrumental music, sound effects, and continuous mixes. | `legends-stable-audio-3` |
| Inspect, configure, and verify OBS Studio recording workflows, plus an optional cursor overlay extra. | `legends-obs-kit` |
| Local voice typing, dictation, and app-focused paste. | `legends-hyperyap` |
| Source-cited Empire memory, research evidence, retrieval and recoverable knowledge transactions. | `legends-empire` |
| Find, qualify, and apply for US business grants with agent assistance. | `legends-grant` |
| Live web search, scraping, crawling, and offline provider catalog with credit-efficient routing. | `legends-firecrawl` |
| Repeatable yt-dlp source pulls, verification, transcripts, search, and clip-building with pacing and bulk guardrails. | `legends-yt-dlp` |
| Passive ambient audio capture, deduplicated archiving, offline transcription, and vault distillation. | `legends-ambient-intelligence` |
| Agentic video caption QA and rendering with contextual correction, alignment timing, and proof evidence. | `legends-captions` |
<!-- capability-directory:end -->

## Module recipes

Module recipes are plain Markdown with no skill frontmatter. Resolve the
exact paths with `cto-legends handoff <module>` and read them in order:

- `legends-dataforseo-kit`: `README.md`, `docs/RESEARCH-MEMORY.md`
- `legends-geogrid`: `README.md`, `docs/STUDY-RECIPE.md`
- `legends-github`: `README.md` plus `docs/`
- `legends-stable-audio-3`: `README.md` plus `docs/`
- `legends-obs-kit`: `README.md` plus `docs/`
- `legends-hyperyap`: `README.md`
- `legends-empire`: `README.md` plus `docs/`
- `legends-grant`: `README.md`, `docs/GRANT-RECIPE.md`
- `legends-firecrawl`: `README.md` plus `docs/`
- `legends-yt-dlp`: `README.md` plus `docs/`
- `legends-ambient-intelligence`: `README.md` plus `docs/`
- `legends-captions`: `README.md` plus `docs/`

Compatibility aliases: `hyperyap` routes to `legends-hyperyap`;
`legends-ultimate-captions` routes to `legends-captions`.

For "can we generate some AI music?", choose `legends-stable-audio-3`,
resolve its handoff, read its audio recipe, and check its generation setup.
Do not detour to OBS recording or require a project manifest. Do not claim
model weights or a working generator merely because the planning CLI is
installed.

Use `cto-legends capabilities --markdown` for examples, boundaries and setup.
`cto-legends route "<user goal>"` offers offline lexical hints, not semantic
judgment. No lexical match is not proof that no capability fits: read the
index. For several outcomes, choose a small ordered set of modules. Do not
install all matches. Clarify only a meaningful ambiguity, not the user's
choice of tool.

Run `cto-legends handoff <module>` to resolve the active recipe paths. If
missing, preview and perform authorized setup, then repeat the handoff. Read
returned files in order and use `status` for the isolated runtime. A missing
recipe is a setup defect, not permission to substitute unrelated installed
global skills. Read only the selected workflow and references; do not preload
every module.

Only cataloged public modules and explicitly registered local guides are
known. Unsupported requests must remain unsupported rather than being forced
into a nearby match. Discovery never grants paid, destructive, or publishing
authority.

`status` may also list explicitly registered `local_guides`. These are
existing user-selected Markdown instructions, not catalog installs or proof
of readiness. Read a matching guide when the user requests that capability;
follow its own prerequisites. Never execute a guide path as a command or
automatically publish its contents. The manager does not update or roll back
these local products.

One central skill is sufficient: read only the selected product's
instructions on demand, without installing all its subskills into every host.
Use `agent-setup codex|gemini|claude|cursor|grok|muse|windsurf|aider` to
preview host registration, then `--apply` when authorized. `--directory`
overrides the skill root. Registration is not live discovery proof; reload
the host and invoke doctor.

Run `agent-audit <host>` in the actual execution environment. Windows, WSL,
remote Linux and temporary agent homes are separate discovery environments.
When explicitly consolidating registrations, preview `isolate-skills <host>`,
then apply it. It moves only known replaced registrations to a restorable
backup. Host plugins and injected tool catalogs may remain; inspect the fresh
session's advertised skills before declaring a central-only test. Never
confuse an empty `local_guides` object with evidence that standalone skills
are absent.

Run `task-readiness` before describing the complete workflow as ready. It
checks the report browser, provider credential presence, evidence module and
artwork dependencies separately. A missing selected vault or target Git
repository is an input requirement, not a failure to discover the installed
tools. For an offline acceptance task, perform the available checks and write
the requested receipt, including blockers; do not stop because the workspace
is empty.

Before promising a GeoGrid report, run `report-readiness`. If the map browser
is missing, follow the installed GeoGrid basemap setup instructions; do not
silently substitute a bare grid. A credentials warning still requires
resolution before fresh collection. Empire vault writes require a POSIX or
WSL host; check that separately before promising a vault transaction.

## Install law: suggest, never seize

1. The router may propose a module install. Every install is explicit per
   module: `cto-legends install <module>` previews, and nothing is written
   until the user runs with `--apply` (or otherwise explicitly authorizes
   that module).
2. No bundles: never install all matches, never install a second module as a
   side effect of the first.
3. No background or silent installs. Native applications (such as
   `legends-hyperyap` installers or OBS extras) use their own installers
   after platform and intent checks; manager rollback does not cover native
   apps or scene changes.
4. Grant, `legends-empire`, and spending modules keep their own preview and
   spending gates; installation never grants paid, destructive, or publishing
   authority.

## Install what the task needs

1. Match the goal using the capability directory above.
2. Preview: `cto-legends install <module>`.
3. When installation is within the user's request, run the same command with
   `--apply`. Otherwise explain the proposed install and ask before doing it.
4. Run `cto-legends doctor`, then read that module's recipe paths returned by
   `cto-legends handoff <module>` at the source path returned by `status`.
   Follow its workflow and credential rules.
5. Use `cto-legends run <module> -- <arguments>` or the exact isolated Python
   path from `status`. Do not use a global Python for managed module
   commands.

For `legends-hyperyap` and other native products, `install` returns a guided
setup handoff. Use `guide <module>` to read the pinned README, release
assets, platform support, and SHA-256 values. Do not call these native
applications installed merely because the guide was returned. Native
installation and upgrades use their own installers after platform and user
intent checks; manager rollback does not roll back native applications or
scene changes. Close OBS and preserve scene backups before applying its
cursor installer.

OBS Kit requires Node.js 22+ and uses a prebuilt package; its manifest probe
does not certify an OBS connection. Live operation targets Windows and
requires the module's own doctor and authenticated WebSocket setup. Audio
setup installs the lightweight CLI and skill, not GPU runtimes or model
weights. Follow its model access, hardware, license, and paid-generation
rules separately.

GeoGrid's managed install includes the Python scan runner and pinned provider
dependency plus report libraries. Browser binaries, system libraries, and
credentials still require module setup. Its default run entrypoint is
study.py. GitHub's managed install includes its headless CLI and pinned
optional research transport. Installing native agent skills is a separate
optional step.

## Startup and host registration

For dependable discovery, connect the central index to startup instructions
as well as registering its skill:

```sh
cto-legends startup-setup codex
cto-legends startup-setup codex --apply
cto-legends startup-status codex
```

This preserves existing instructions and provides a checked restoration
manifest. Use `gemini` or `claude` for their documented user instruction
files. Registration alone does not prove that a fresh agent loads or follows
the instructions.

## Update and recover

`cto-legends check-updates` compares upstream public tags but does not trust
new versions automatically. Obtain the latest `cto-legends` release from
https://github.com/avalonreset/cto-legends/releases to update the manager
and its reviewed catalog. Use the interpreter that owns this installation,
preview `cto-legends update`, then run `cto-legends update --apply` when
authorized. Only installed modules are updated. Independently maintained
module releases are adopted through a new verified catalog, with declared
dependencies retained.

If needed, preview `cto-legends rollback <module>` and apply it with
`--apply`. Previous environments remain on disk. Never erase user reports or
credentials to fix an installation. Do not modify managed source checkouts;
save outputs outside them. Managed installs live under the manager home
(`~/.cto-legends` by default, or `CTO_LEGENDS_HOME` / `--home PATH`): keep
that home at its original path because Python environments are not
relocatable.

## Research and credentials

Installation and doctor do not call paid provider endpoints. Module execution
can: retain each module's preview, execute and spending gates. Credentials
stay in user-provided environment variables. Never print or persist secret
values. Do not subscribe to an MCP server just to discover these modules. No
background service is required. Route matching is a hint, not an
authoritative judgment.

## Writing style

Use plain punctuation. Do not use em dashes in generated copy,
documentation, or release titles.
