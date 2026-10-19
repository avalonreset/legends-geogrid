import L from 'leaflet'
import { PersistentTileLayer } from './persistent-tiles.js'

export const BASEMAPS = [
  { id: 'osm-dark', name: 'OpenStreetMap · inverted', kind: 'osm', dark: true },
  { id: 'osm-legends', name: 'OpenStreetMap · Legends dark', kind: 'osm', dark: true, muted: true },
  { id: 'osm-light', name: 'OpenStreetMap · original', kind: 'osm' },
  { id: 'google-roadmap', name: 'Google Maps · Streets', google: 'roadmap' },
  { id: 'google-dark', name: 'Google Maps · Dark', google: 'dark' },
  { id: 'google-satellite', name: 'Google Maps · Satellite + labels', google: 'satellite' },
  { id: 'ofm-fiord', name: 'OpenFreeMap · Fiord', style: 'fiord' },
  { id: 'ofm-dark', name: 'OpenFreeMap · Dark', style: 'dark' },
  { id: 'ofm-liberty', name: 'OpenFreeMap · Liberty', style: 'liberty' },
  { id: 'ofm-positron', name: 'OpenFreeMap · Positron', style: 'positron' },
]
const openCredit = '<a href="https://openfreemap.org/">OpenFreeMap</a> · © <a href="https://openmaptiles.org/">OpenMapTiles</a> · © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'

export function createBasemapSwitcher(map, { announce, onChange, onStatus = () => {} }) {
  let current, version = 0
  return {
    async set(id) {
      const source = BASEMAPS.find(s => s.id === id)
      if (!source) throw new Error('Unknown basemap')
      const revision = ++version
      onStatus({ phase: 'loading', id })
      let layer
      try {
        // Load WebGL only when requested, keeping the raster startup small.
        if (source.google) {
          const { createGoogleTiles } = await import('./google-tiles.js')
          layer = await createGoogleTiles(map, source.google, announce)
          if (revision !== version) return
        } else if (source.style) {
          const [{ MaplibreGL }, , maplibre, worker] = await Promise.all([
            import('@maplibre/maplibre-gl-leaflet'), import('maplibre-gl/dist/maplibre-gl.css'),
            import('maplibre-gl'), import('maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'),
          ])
          if (revision !== version) return
          maplibre.setWorkerUrl(worker.default)
          layer = new MaplibreGL({ style: `https://tiles.openfreemap.org/styles/${source.style}`,
            interactive: false, attributionControl: false, pane: 'tilePane' })
          layer.getAttribution = () => openCredit
        } else {
          layer = new PersistentTileLayer(import.meta.env.VITE_MAP_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: import.meta.env.VITE_MAP_TILE_ATTRIBUTION || '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
            maxZoom: 19, maxNativeZoom: 19,
            className: source.muted ? 'osm-inverted osm-legends' : source.dark ? 'osm-inverted' : '',
          })
        }
        const previous = current
        layer.addTo(map)
        const container = layer.getContainer()
        container.style.opacity = '0'
        if (source.style) {
          await new Promise((resolve, reject) => {
            const gl = layer.getMaplibreMap()
            const timer = setTimeout(() => reject(new Error('Map loading timed out')), 25000)
            gl.once('load', () => { clearTimeout(timer); resolve() })
            gl.once('error', () => { clearTimeout(timer); reject(new Error('Map resources could not load')) })
          })
        } else {
          await new Promise((resolve, reject) => {
            const timer = setTimeout(() => reject(new Error('Map loading timed out')), 20000)
            layer.once('load', () => { clearTimeout(timer); resolve() })
            layer.once('tileerror', () => { clearTimeout(timer); reject(new Error('Street tiles could not load')) })
          })
        }
        if (revision !== version) { map.removeLayer(layer); return }
        current = layer
        const duration = matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 300
        container.style.transition = `opacity ${duration}ms ease`
        container.style.opacity = '1'
        if (previous) setTimeout(() => { if (map.hasLayer(previous)) map.removeLayer(previous) }, duration)
        onChange(id)
        onStatus({ phase: 'ready', id })
      } catch (error) {
        if (layer && map.hasLayer(layer)) map.removeLayer(layer)
        if (revision === version) {
          const detail = source.google ? error.message || 'Google Maps could not load.' : 'Street map resources could not load.'
          const message = `${source.name} is unavailable. ${detail} ${current ? 'The previous background remains visible.' : 'The ranking evidence is loaded; choose another background or retry.'}`
          onStatus({ phase: 'error', id, message })
          announce(message)
        }
      }
    },
  }
}
