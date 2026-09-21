# Third-Party Notices

legends-geogrid's own source code is released under the MIT License in `LICENSE`. The following components, services, data, and trademarks remain subject to their own terms.

## Runtime software

### Leaflet 1.9.4

- Project: https://leafletjs.com/
- Source: https://github.com/Leaflet/Leaflet/tree/v1.9.4
- License: BSD 2-Clause

```text
BSD 2-Clause License

Copyright (c) 2010-2023, Volodymyr Agafonkin
Copyright (c) 2010-2011, CloudMade
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## Build software

- [Vite 8.2.2](https://github.com/vitejs/vite), MIT License.
- [PostCSS 8.5.27](https://github.com/postcss/postcss), MIT License.

`pnpm build` generates `dist/third-party-licenses.md` from the exact bundled dependency graph. Installed packages also retain their upstream licence files under `node_modules`.

## Map data and tiles

The default interactive map uses OpenStreetMap data and the OpenStreetMap Foundation's standard raster tile service.

- Attribution: © OpenStreetMap contributors
- GitHub: https://github.com/openstreetmap
- Data licence: [Open Data Commons Open Database License](https://www.openstreetmap.org/copyright)
- Tile-server policy: https://operations.osmfoundation.org/policies/tiles/

The application displays linked attribution on the map and requests only tiles needed for normal human interactive viewing. It does not provide tile prefetching, scraping, bulk download, or offline packaging. Deployers are responsible for using a suitable provider and preserving that provider's attribution and usage terms, especially for public or high-traffic deployments.

## Optional data service

Fresh scans require a user-supplied DataForSEO account and call the DataForSEO Google Maps SERP API.

- API: https://dataforseo.com/apis/serp-api/google-maps-api
- GitHub: https://github.com/dataforseo
- Terms: https://dataforseo.com/terms-of-service

DataForSEO is not bundled with or affiliated with legends-geogrid. Users are responsible for their credentials, billing, quotas, and compliance with DataForSEO and applicable search-provider terms. The repository does not contain DataForSEO credentials.

## Google services and trademarks

Generated reports can optionally display a Google Maps embed or a user-supplied Google Static Maps image. Google Maps content and brand features remain subject to Google's terms and attribution requirements. legends-geogrid does not bundle a Google API key or remove provider attribution.

Google, Google Maps, DataForSEO, OpenStreetMap, Leaflet, Local Falcon, Search Atlas, LeadSnap, and BrightLocal are names or marks of their respective owners. Their mention identifies interoperability, data sources, or historical product research; it does not imply endorsement or affiliation.

## Bundled Claude SEO skills (report layer)

`third_party/claude-seo/` vendors two skills from
[Claude SEO](https://github.com/AgriciDaniel/claude-seo) by Daniel Agrici
([agricidaniel.com](https://agricidaniel.com)), version 2.3.1:

- `skills/seo-dataforseo` — live keyword volume, difficulty, intent, and SERP
  data procedures plus `references/cost-tiers.md`, `references/tool-catalog.md`.
- `skills/seo-maps` — maps intelligence procedures plus the shared
  `skills/seo/references/` files it loads.
- `scripts/dataforseo_costs.py` — API cost guardrail (run from
  `third_party/claude-seo/scripts/`; the skill text says `scripts/`, which
  means this directory in the vendored layout).
- `LICENSE` (MIT, copyright 2026 agricidaniel) and `CITATION.cff`, kept intact.
  See `third_party/claude-seo/VENDORED_FROM.txt` for the source revision.

These skills are procedures and documentation consumed with the user's own
DataForSEO account. No credentials ship with them.

## Python strategy report dependencies

The strategy report engine (`tools/strategy_report.py`) requires optional Python libraries declared in `requirements-report.txt`. These packages are installed by the user via pip and are not vendored into the repository source tree:

### ReportLab 4.x and Bitstream Vera Fonts

- Project: https://www.reportlab.com/
- License: ReportLab License (BSD-style; copyright (c) 2000-2024, ReportLab Inc.)

ReportLab bundles the Bitstream Vera font family (`Vera.ttf`, `VeraBd.ttf`), which `tools/strategy_report.py` registers and embeds into generated strategy report PDFs.

- Font License: Bitstream Vera License

```text
Copyright (c) 2003 by Bitstream, Inc. All Rights Reserved.
Bitstream Vera is a trademark of Bitstream, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of the fonts accompanying this license ("Fonts") and associated documentation
files (the "Font Software"), to reproduce and distribute the Font Software,
including without limitation the rights to use, copy, merge, publish, distribute,
and/or sell copies of the Font Software, and to permit persons to whom the Font
Software is furnished to do so, subject to the following conditions:

The above copyright and trademark notices and this permission notice shall be
included in all copies of one or more of the Font Software typefaces.

The Font Software may be modified, altered, or added to, and in such form
distributed, but only on the condition that the trademark "Bitstream" or
"Vera" shall not be used in any modified Software.
```

### Pillow (PIL Fork)

- Project: https://python-pillow.org/
- Source: https://github.com/python-pillow/Pillow
- License: HPND (Historical Permission Notice and Disclaimer; MIT-CMU style)
- Copyright: (c) 1997-2011 by Secret Labs AB, (c) 1995-2011 by Fredrik Lundh, (c) 2010 by Alex Clark and contributors

### pypdfium2 and PDFium Binaries

- Project: https://github.com/pypdfium2-team/pypdfium2
- License: Apache-2.0 or BSD-3-Clause (dual-licensed)
- Bundled Binaries: Pre-built wheels bundle Google's PDFium library (BSD 3-Clause, copyright 2014 The PDFium Authors). PDFium binaries incorporate third-party notices from embedded libraries (including FreeType, ICU, libjpeg, libpng, and zlib).

### Distribution notice guidance

When distributing binary wheels, container images, or bundled environments containing these dependencies, retain upstream license texts for ReportLab, Pillow, and pypdfium2, along with PDFium third-party notices and the Bitstream Vera font notice for fonts embedded into generated PDFs. No AGPL dependencies (such as PyMuPDF) are introduced.

## legends-dataforseo-kit

Fresh scans use the separately installed [legends-dataforseo-kit](https://github.com/avalonreset/legends-dataforseo-kit), distributed under the MIT license. Its license is included with its distribution. No MCP server is required.
