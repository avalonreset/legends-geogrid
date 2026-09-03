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
- Data licence: [Open Data Commons Open Database License](https://www.openstreetmap.org/copyright)
- Tile-server policy: https://operations.osmfoundation.org/policies/tiles/

The application displays linked attribution on the map and requests only tiles needed for normal human interactive viewing. It does not provide tile prefetching, scraping, bulk download, or offline packaging. Deployers are responsible for using a suitable provider and preserving that provider's attribution and usage terms, especially for public or high-traffic deployments.

## Optional data service

Fresh scans require a user-supplied DataForSEO account and call the DataForSEO Google Maps SERP API.

- API: https://dataforseo.com/apis/serp-api/google-maps-api
- Terms: https://dataforseo.com/terms-of-service

DataForSEO is not bundled with or affiliated with legends-geogrid. Users are responsible for their credentials, billing, quotas, and compliance with DataForSEO and applicable search-provider terms. The repository does not contain DataForSEO credentials.

## Google services and trademarks

Generated reports can optionally display a Google Maps embed or a user-supplied Google Static Maps image. Google Maps content and brand features remain subject to Google's terms and attribution requirements. legends-geogrid does not bundle a Google API key or remove provider attribution.

Google, Google Maps, DataForSEO, OpenStreetMap, Leaflet, Local Falcon, Search Atlas, LeadSnap, and BrightLocal are names or marks of their respective owners. Their mention identifies interoperability, data sources, or historical product research; it does not imply endorsement or affiliation.
