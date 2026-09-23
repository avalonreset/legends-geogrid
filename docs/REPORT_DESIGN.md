# Report design contract

Version: `legends-editorial-v5`. Tokens and HTML rules live in
`tools/report_design.py`; PDF and HTML consume the same normalized model in
`tools/strategy_report.py`. Do not write customer-specific CSS or renderer branches.

The supplied Alpha Mechanical v7 reference establishes the editorial direction:
decision first, explicit measurement geography, repeatable map sections, supported
actions, method and traceable evidence. It is a visual reference, not a source of
facts, recommendations, fonts or imagery for other customers.

## Shared rules

## Dark-only Legends policy

The Legends Design Bible applies to dark report presentation only, including
proposals and findings in HTML and PDF. Its portable rules are recorded here;
users do not need a private vault. Use pure black #000000 for the page, white headings, off-white body text, readable neutral grays, and
pure red #FF0000 for links and deliberate brand accents. Use white major rules,
left-aligned branding, deliberate whitespace and readable editorial typography.
Use semantic surfaces: charcoal for related information, slightly lighter charcoal for actions. Restrained black/charcoal gradients, dark-red tints and inset edge highlights are permitted. No fake badges, arbitrary accent colors, heavy shadows or translucent text backgrounds.
Set `GEOGRID_LEGENDS_FONT` to the licensed Legends Regular TTF when rendering
the branded dark edition. It is embedded in PDF and copied alongside HTML for
portable viewing. The private font is not included in source distributions.
Without that setting, portable fallback typography is used; do not describe
such output as the fully branded Legends edition. Light uses the same typography and layout with print-safe colors.
Keep the banner legible and left-aligned; do not repeat the product name directly
under a banner that already contains it. Use the stage label alone there.

### Dark title copyfit

Titles use the full editorial column, never an arbitrary character-width cap.
Use responsive 28-44px HTML display type and natural word wrapping; do not force
balanced lines into a narrow block or insert customer-specific line breaks.
Preserve the complete business name. Long names may use additional lines rather
than clipping, ellipsis or shrinking below the readable floor. On mobile, use
the available width; only an unbroken token may wrap within a word. PDF titles
also use the full column and flow naturally. Review short names, long names,
hyphenated subtitles and long tokens at desktop and mobile widths. Do not
promise every arbitrary title will fit on one line.
Report headings use intentional case; preserve business names and source text.
Dark text hierarchy: white for decisions, selected queries, measured results,
cost qualifications and material limitations. Gray for stage labels, metric
labels, source records and sampling
method detail. Links remain red. Never dim an unresolved identity conflict or
turn every paragraph gray; hierarchy follows meaning, not alternating rows.
The compact-utility 11px rule is not a report body-type rule.

Light mode is the print palette of this same template: pure-white pages and panels,
black primary text, readable gray secondary text, red links and thin borders.
Typography, content order, cards, copyfit and disclosure behavior match dark mode.
Do not retain a separate Jev layout or decorative header strip.
Cartographic imagery and semantic rank colors are evidence, exempt from the
brand palette in both themes. Never recolor or crop them to satisfy branding.

Both proposal themes open with the study decision, selected queries, shared origins,
grid-only estimate and material scope limits. Detailed evidence is expandable
in HTML and retained after the opening summary in PDF. Decision, selected-theme,
geography and cost drawers start open; only excluded queries and source records
start collapsed. Use one divider between adjacent sections, not stacked borders.
Do not conceal identity
conflicts in a collapsed section. Both findings themes include a computed query summary
before the full-sized maps. Customer-need descriptions and map legends use primary ink (white in dark, black in light). No fabricated performance or commercial claims.

## Common evidence and layout rules

- Dark means pitch black `#000000`, with white text, neutral gray secondary text
  and separators. Light is a separate supported palette. Rank marker colors retain
  their evidence meaning and never depend on the customer's industry.
- Keep branding, headings, maps, captions and copy on one left-aligned column.
- Data selects content, never CSS, page geometry or arbitrary layout variants.
- Preserve hypotheses, measured findings, unknowns and recommendations as distinct
  labeled content. Never manufacture a decision or fill an optional section with
  invented content to satisfy layout.
- Maps keep their full aspect ratio, readable markers and attribution. Basemap
  colors are cartographic assets; black page chrome does not recolor evidence maps.

## Findings output modes

Both formats and palettes use the same evidence model and content sequence:
business, scope and measured comparison, interpretation, full-sized maps,
actions, verification and evidence appendix. Switching palette must not hide
summaries or change the meaning of the study.

Both HTML themes use a 1080 px maximum container, 48 px desktop gutters and
22 px mobile gutters. Light panels have white fills and thin gray outlines;
dark gradients and glass effects do not carry into the printing palette.
Query navigation links use generated stable IDs, not untrusted business names.
Maps occupy the column; long observation ledgers expand independently and scroll
inside their container. The downloadable PDF is the canonical paginated edition;
browser printing is a convenience, not a promise of identical pagination.

PDF uses US Letter, 48 pt horizontal margins and a 516 pt column. Retain readable
body type and continuation pages. Do not shrink long reports into predetermined
page counts. Run collision, glyph-boundary and background checks on every page.

## Proposal stage

Use the same palette, column, heading hierarchy and left-aligned approved banner.
Its content order is scope/identity and decision, theme/query/evidence rationale,
measurement settings and limitations, estimated cost and deliverables/sources.
Never show pilot data as completed findings. Preserve the original precollection
proposal and hashes; styling revisions are separate reading editions.

Run `python tools/study.py proposal --plan PLAN --output-dir NEW_FOLDER`.
The generic proposal renderer validates source lineage before producing HTML,
PDF and a receipt. Both formats use the same ordered content and shared palette.
It displays identity reconciliation and restricted-evidence limitations, and
distinguishes grid estimates from research costs. It makes no provider calls.
Existing output folders are refused, protecting frozen precollection proposals.
Use `--theme light` for the pure-white alternative. Semantic quality still needs
review; structured presentation does not certify agent judgments.

## Acceptance

Test both palettes, multiple query counts, long content and missing evidence using
offline fixtures. Inspect desktop and mobile HTML, including an open ledger, and
every final PDF page. Record the design version in report QA. Compare new visual
revisions with the approved reference; do not treat passing tests as visual approval.

## Editorial formula (dark v3)

One brand header, one complete business title, one stage label. Proposal: decision,
3-5 selected themes, shared sample size, qualified cost and material scope limits.
Findings: measured comparison, qualified assessment, material limitations, maps,
actions, supporting evidence. Never imply rank counts measure customers. Show
measured/sample denominators and distinguish zero evidence from zero visibility.

White carries meaning: customer needs, map legends, open section headings and
limitations. Gray is reserved for secondary metadata, never essential reading.
Red is a link or disclosure affordance, not a substitute for heading hierarchy.
Closed evidence drawers remain red; open sections have white headings. Preserve
keyboard focus. Main proposal sections start open; evidence appendices may close.

Avoid repeating the same decision as a second section. Keep technical map
provenance available in a drawer; attribution inside the image stays visible.
Never repair source business-name casing by guessing; a display-name override
requires an explicit editorial input distinct from original evidence.

## Shared graphic vocabulary, v4

- Search themes use numbered, square-corner keyword cards with a gray keyline
  and short red registration mark. Two columns on wide screens, one on mobile.
  Each card explains customer need and rationale; limitations remain accessible.
- Search labels use outlined query tokens. They are text labels, not buttons.
- The top-three summary includes a white proportional rail over a gray track.
  Its length is exactly top3 / measured origins; the printed fraction remains
  authoritative. Unknown denominators show no bar. Never call this market share.
- Actions use a white left edge, category label, ordinal and separately labeled
  rationale, next step, success check and uncertainty. Red marks the category,
  not severity. No ornamental icons or heavy drop shadows; see v5 surface rules.
- PDF uses restrained outlined headings for query themes and action groups.
  It retains readable linear flow rather than shrinking cards to fit columns.
- Map status colors retain their measurement meaning. Brand red never replaces
  the map legend. Light-mode styling remains independent.

Use these elements by content type, not everywhere. Whitespace and plain prose
remain the default. Keep exact text alongside graphics, preserve keyboard focus,
allow long terms to wrap, and keep core findings visible without opening drawers.

## Shared hierarchy; palette-specific surfaces, v5

- HTML: display title 28–44px responsive; section 32px; subheading/card title 24px; body 17px; card body 16px; labels/evidence toggles 13–14px. Mobile section/subhead sizes are 28/22px.
- Major headings have 48px preceding space inside long sections and 24px following space. Subheads use 32/16px. Never use body-size text as a structural heading or depend on synthesized font weight.
- Headings are white; body #E0E0E0; metadata #A3A3A3. Essential limitations remain readable body copy, never muted away.
- Query panels use a charcoal gradient; action panels use a restrained dark-red-to-charcoal gradient. A faint inset top highlight provides a glass-like edge without transparency, backdrop blur, animation or reduced contrast.
- Surfaces group meaning, not alternating decoration. Plain narrative and maps remain unboxed. Red tint does not encode urgency or a numerical score.
- PDF uses solid charcoal category bands, 16pt section headings, 14pt group headings and 11pt body. Screen gradients flatten when printed. Light theme remains independent.
- Actual font, complete text and reliable wrapping take priority over effects. Review mobile overflow and every PDF page after typography changes.

## Brand credits

Proposal and findings documents carry exactly two brand credits: lowercase cto-legends (https://cto-legends.com) at the top right, and ai-marketing-hub-pro (https://www.skool.com/ai-marketing-hub-pro/about) at the bottom right. HTML uses document start/end; PDF uses first/last page only. Keep them small, red and clickable. Center PDF page numbers to avoid footer collisions. Never repeat these credits on every page.


### Search keyword identity

Repeated search phrases in evidence sections use a SEARCH KEYWORD label above the exact query in a shaded panel, not a generic section heading. HTML uses a restrained dark-red/charcoal gradient; PDF uses a solid tinted band. Query text remains selectable and never implies a button. The selected-theme introduction explains why these queries were chosen. Missing-data messages use plain language; exact schema keys remain in machine-readable exports.


Canonical design source: Legends Design Bible, Editorial Report Design v2.0.
This portable contract contains the rules required for rendering; no private
vault is required. The light-palette unification supersedes earlier instructions
to maintain a separate light layout.
