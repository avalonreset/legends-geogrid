import { createOsmLayer } from './osm-tiles.js'
import { maplibreWorkerUrl } from './maplibre-worker.js'
import { visibleTimeout } from './visible-timeout.js'

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
export const OFM_STYLES_URL = 'https://tiles.openfreemap.org/styles'
export const OFM_ATTRIBUTION_TEXT = 'OpenFreeMap © OpenMapTiles © OpenStreetMap contributors'
const escapeText = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
const openCredit = '<a href="https://openfreemap.org/">OpenFreeMap</a> · © <a href="https://openmaptiles.org/">OpenMapTiles</a> · © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'

// basemaps: selectable list (shared with the caller, which may remove Google entries). fallbackId: default background.
// googleSessionPath: enables the Google client against a host-provided session endpoint. onGoogleUnavailable: when given,
// a failed Google session or tile (HTTP 403/429/5xx) silently returns to fallbackId and ends Google for this session.
// A layer that failed half-way (for example no WebGL) can throw while detaching; teardown must never mask the real error.
function removeLayerSafely(map, layer) {
  try { if (layer && map.hasLayer(layer)) map.removeLayer(layer) } catch { /* already detached */ }
}

// Vector styles need WebGL. Probing first fails fast, leaving the neutral map background and the evidence
// overlays in place instead of waiting for MapLibre to time out.
let webglSupported = null
function hasWebGL() {
  if (webglSupported !== null) return webglSupported
  try {
    const canvas = document.createElement('canvas')
    const gl = canvas.getContext('webgl2') || canvas.getContext('webgl')
    webglSupported = !!gl
    gl?.getExtension?.('WEBGL_lose_context')?.loseContext()
  } catch { webglSupported = false }
  return webglSupported
}

export function createBasemapSwitcher(map, { announce, onChange, onStatus = () => {}, basemaps = BASEMAPS, fallbackId = null,
  googleSessionPath, tileStyleBase = OFM_STYLES_URL, attribution = null, onGoogleUnavailable = null }) {
  let current, currentSource = null, version = 0, googleDown = false
  let cancelPending = null
  let pendingLayer = null
  let destroyed = false
  // Leaflet fires 'unload' only when _loaded (after setView), but map.remove() always deletes _mapPane.
  const isDestroyed = () => destroyed || !map?._mapPane
  map.once('unload', () => { destroyed = true; version++; cancelPending?.(); cancelPending = null })
  const silentGoogle = typeof onGoogleUnavailable === 'function'
  const credit = attribution ? escapeText(attribution) : openCredit
  const googleFailed = () => {
    if (isDestroyed() || googleDown) return
    googleDown = true
    onGoogleUnavailable()
    if (fallbackId && (!current || currentSource?.google)) void api.set(fallbackId)
  }
  const api = {
    async set(id) {
      const source = basemaps.find(s => s.id === id)
      if (!source) throw new Error('Unknown basemap')
      if (source.google && googleDown) return
      if (isDestroyed()) return
      const revision = ++version
      cancelPending?.(); cancelPending = null
      if (pendingLayer) { removeLayerSafely(map, pendingLayer); pendingLayer = null }
      // If the requested basemap is already active (or another OSM style shares the active OSM tile layer),
      // switch/confirm immediately so returning from a failed Google attempt never hangs or stays stuck.
      if (current && map.hasLayer(current)) {
        if (currentSource?.id === id) {
          onChange(id)
          onStatus({ phase: 'ready', id })
          return
        }
        if (currentSource?.kind === 'osm' && source.kind === 'osm') {
          const container = current.getContainer()
          if (container) {
            container.classList.toggle('osm-inverted', !!source.dark)
            container.classList.toggle('osm-legends', !!source.muted)
          }
          currentSource = source
          onChange(id)
          onStatus({ phase: 'ready', id })
          return
        }
      }
      onStatus({ phase: 'loading', id })
      let layer
      try {
        // Load WebGL only when requested, keeping the raster startup small.
        if (source.google) {
          const { createGoogleTiles } = await import('./google-tiles.js')
          layer = await createGoogleTiles(map, source.google, announce, { sessionPath: googleSessionPath, onFailure: silentGoogle ? googleFailed : null })
          if (isDestroyed() || revision !== version) { removeLayerSafely(map, layer); return }
        } else if (source.style) {
          if (!hasWebGL()) throw new Error('WebGL is unavailable in this browser.')
          const [{ MaplibreGL }, , maplibre, workerUrl] = await Promise.all([
            import('@maplibre/maplibre-gl-leaflet'), import('maplibre-gl/dist/maplibre-gl.css'),
            import('maplibre-gl'), maplibreWorkerUrl(),
          ])
          if (isDestroyed() || revision !== version) return
          maplibre.setWorkerUrl(workerUrl)
          layer = new MaplibreGL({ style: `${tileStyleBase}/${source.style}`,
            interactive: false, attributionControl: false, pane: 'tilePane' })
          layer.getAttribution = () => credit
        } else {
          layer = createOsmLayer(source)
        }
        const previous = current
        pendingLayer = layer
        let loadDetached = false
        const readyPromise = new Promise((resolve, reject) => {
          let settled = false
          let stopTimer = () => {}
          let offAll = () => {}
          const cleanup = () => {
            try { stopTimer() } catch { /* timer already stopped */ }
            try { offAll() } catch { /* listeners already detached */ }
            if (cancelPending === cancel) cancelPending = null
            if (pendingLayer === layer) pendingLayer = null
          }
          const settleResolve = () => { if (settled) return; settled = true; cleanup(); resolve() }
          const settleReject = error => { if (settled) return; settled = true; cleanup(); reject(error) }
          const cancel = () => {
            if (settled) return
            settled = true
            cleanup()
            removeLayerSafely(map, layer)
            resolve()
          }
          const onRemove = () => { loadDetached = true; settleResolve() }
          cancelPending = cancel
          try {
            if (source.style) {
              layer.addTo(map)
              const gl = layer.getMaplibreMap()
              const onLoad = () => settleResolve()
              const onError = () => settleReject(new Error('Map resources could not load.'))
              stopTimer = visibleTimeout(25000, () => settleReject(new Error('Map loading timed out.')))
              gl.once('load', onLoad)
              gl.once('error', onError)
              layer.once('remove', onRemove)
              offAll = () => { gl.off?.('load', onLoad); gl.off?.('error', onError); layer.off?.('remove', onRemove) }
            } else if (source.google) {
              const onLoad = () => settleResolve()
              const onTileError = () => settleReject(new Error('Street tiles could not load'))
              stopTimer = visibleTimeout(20000, () => settleReject(new Error('Map loading timed out.')))
              layer.once('load', onLoad)
              layer.once('tileerror', onTileError)
              layer.once('remove', onRemove)
              offAll = () => { layer.off?.('load', onLoad); layer.off?.('tileerror', onTileError); layer.off?.('remove', onRemove) }
              layer.addTo(map)
            } else {
              const timer = setTimeout(settleResolve, 1200)
              stopTimer = () => clearTimeout(timer)
              layer.once('load', settleResolve)
              layer.once('tileload', settleResolve)
              layer.once('remove', onRemove)
              offAll = () => { layer.off?.('load', settleResolve); layer.off?.('tileload', settleResolve); layer.off?.('remove', onRemove) }
              layer.addTo(map)
              if (!layer.isLoading?.()) settleResolve()
            }
          } catch (error) { settleReject(error) }
        })
        let container = null
        try { container = layer.getContainer() } catch { container = null }
        if (container) container.style.opacity = '0'
        await readyPromise
        if (isDestroyed() || revision !== version || loadDetached || !map.hasLayer(layer)) { removeLayerSafely(map, layer); return }
        current = layer
        currentSource = source
        const duration = matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 300
        if (container) {
          container.style.transition = `opacity ${duration}ms ease`
          container.style.opacity = '1'
        }
        if (previous && previous !== layer) setTimeout(() => { if (!isDestroyed()) removeLayerSafely(map, previous) }, duration)
        onChange(id)
        onStatus({ phase: 'ready', id })
      } catch (error) {
        removeLayerSafely(map, layer)
        if (pendingLayer === layer) pendingLayer = null
        if (isDestroyed() || revision !== version) return
        if (source.google && silentGoogle) { googleFailed(); return }
        if (revision === version) {
          const detail = error?.message || (source.google ? 'Google Maps could not load.' : 'Street map resources could not load.')
          const message = `${source.name} is unavailable. ${detail} ${current ? 'The previous background remains visible.' : 'The ranking evidence is loaded; choose another background or retry.'}`
          onStatus({ phase: 'error', id, message })
          announce(message)
        }
      }
    },
  }
  return api
}
