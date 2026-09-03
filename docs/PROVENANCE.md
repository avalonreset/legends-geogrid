# Provenance and Research Sources

This record separates code dependencies, data/services, and product research so that an acknowledgment is never mistaken for a software licence or an affiliation claim.

## Code provenance

legends-geogrid is an original implementation maintained by Avalon Reset. Repository-history review found no copied source code, bundled assets, screenshots, or proprietary datasets from the commercial products listed below.

The shipped runtime code directly imports one third-party library:

- [Leaflet 1.9.4](https://github.com/Leaflet/Leaflet/tree/v1.9.4), BSD 2-Clause License, for interactive map rendering.

Vite and PostCSS are build-time dependencies. Their licences and the licences of exact bundled transitive dependencies are recorded in `THIRD_PARTY_NOTICES.md` and generated into `dist/third-party-licenses.md` during `pnpm build`.

## Data and service provenance

- Fresh rank scans use the user-authorized [DataForSEO Google Maps SERP API](https://dataforseo.com/apis/serp-api/google-maps-api); DataForSEO's official open-source projects are published on [GitHub](https://github.com/dataforseo). The coordinate-grid approach and initial cost model were informed by DataForSEO's [grid rank tracker guide](https://dataforseo.com/help-center/build-grid-rank-tracker-maps) and [Maps SERP pricing](https://dataforseo.com/pricing/serp/google-maps-serp-api).
- The browser studio uses [OpenStreetMap](https://www.openstreetmap.org/copyright) map data and the standard interactive tile service by default. OpenStreetMap's public source projects are on [GitHub](https://github.com/openstreetmap). OpenStreetMap data is ODbL-licensed; tile-server access is governed separately by the [tile usage policy](https://operations.osmfoundation.org/policies/tiles/).
- The bundled Home Slice Pizza examples are minimized historical demonstration results from June 26, 2026. They retain only the target name, keyword, general location, scan coordinates, rank values, and public business titles needed to demonstrate the interface. They exclude credentials, account identifiers, task IDs, raw responses, contact details, reviews, and private client information.

## Product research and acknowledgments

The June 2026 product exploration reviewed public pages from these products to understand existing geo-grid and citation workflows:

- [Local Falcon](https://www.localfalcon.com/) ([GitHub](https://github.com/local-falcon)) — geo-grid credit and workflow conventions.
- [Search Atlas Local SEO](https://searchatlas.com/local-seo-software/) ([GitHub](https://github.com/search-atlas-group)) — local heatmap, reporting, and agency workflow conventions.
- [LeadSnap Local Citations](https://leadsnap.com/features/local-citations/) — citation monitoring and fulfillment context.
- [BrightLocal Citation Builder](https://www.brightlocal.com/citation-builder/) ([GitHub](https://github.com/BrightLocal)) — citation ownership, reporting, and fulfillment context.
- [Search Atlas Local Citations](https://searchatlas.com/local-citations/) ([GitHub](https://github.com/search-atlas-group)) — aggregator and citation-service context.

These sources informed product-category analysis only. legends-geogrid does not use their APIs, code, branding, screenshots, or proprietary data. Their names and trademarks belong to their respective owners, and no endorsement or affiliation is implied.

The keyword-list/reporting workflow also came from user-provided product feedback and screenshots. Those private source screenshots are not included in the public repository.

## Review date

Links and terms were rechecked on September 3, 2026. Service terms and pricing can change; operators should review the current upstream terms before production or high-volume use.
