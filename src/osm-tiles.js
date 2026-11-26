import { PersistentTileLayer } from './persistent-tiles.js'

// OpenStreetMap raster tiles live in their own module so the viewer package can drop them entirely:
// tile.openstreetmap.org is a best-effort service with no SLA and is not used by the viewer build.
export function createOsmLayer(source) {
  const env = import.meta.env || {}
  return new PersistentTileLayer(env.VITE_MAP_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: env.VITE_MAP_TILE_ATTRIBUTION || '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
    maxZoom: 19, maxNativeZoom: 19,
    keepBuffer: 6, updateWhenZooming: false, updateWhenIdle: false,
    className: source.muted ? 'osm-inverted osm-legends' : source.dark ? 'osm-inverted' : '',
  })
}
