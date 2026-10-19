import { PersistentTileLayer } from './persistent-tiles.js'

const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
const credit = '<a href="https://maps.google.com/" target="_blank" rel="noopener" class="google-map-credit"><img src="/google-maps-attribution.svg" alt="Google Maps" height="16"></a>'

export async function createGoogleTiles(map, style, announce) {
  const response = await fetch('/api/maps/google/session', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ style }),
  })
  const session = await response.json()
  if (!response.ok) throw new Error(session.error || 'Google Maps session unavailable.')
  const viewport = async () => {
    const bounds = map.getBounds()
    const wrap = lng => ((lng + 180) % 360 + 360) % 360 - 180
    const params = new URLSearchParams({
      zoom: Math.round(map.getZoom()), north: Math.min(90, bounds.getNorth()), south: Math.max(-90, bounds.getSouth()),
      east: wrap(bounds.getEast()), west: wrap(bounds.getWest()),
    })
    const result = await fetch(`/api/maps/google/${session.id}/viewport?${params}`)
    const info = await result.json()
    if (!result.ok || !info.copyright) throw new Error('Google map attribution could not load.')
    return info
  }
  const info = await viewport()
  const layer = new PersistentTileLayer(`/api/maps/google/${session.id}/tiles/{z}/{x}/{y}`, {
    attribution: `${credit}<span class="google-data-credit">${escape(info.copyright)}</span>`,
    maxZoom: 18, maxNativeZoom: 18, keepBuffer: 0, updateWhenIdle: true,
    className: 'google-interactive-tiles',
  })
  let timer, revision = 0, warned = false
  const updateCredit = () => {
    clearTimeout(timer)
    const id = ++revision
    timer = setTimeout(async () => {
      // Switching to the title-review workspace hides the map. Leaflet emits a
      // resize/move with a zero-area viewport; that is not an attribution error.
      const size = map.getSize()
      if (!map.hasLayer(layer) || size.x <= 0 || size.y <= 0) return
      try {
        const next = await viewport()
        if (!map.hasLayer(layer) || id !== revision) return
        map.attributionControl.removeAttribution(layer.options.attribution)
        layer.options.attribution = `${credit}<span class="google-data-credit">${escape(next.copyright)}</span>`
        map.attributionControl.addAttribution(layer.options.attribution)
      } catch {
        if (map.hasLayer(layer) && id === revision) announce('Google map attribution could not refresh. Reselect the map to retry.')
      }
    }, 350)
  }
  layer.on('add', () => map.on('moveend', updateCredit))
  layer.on('remove', () => { clearTimeout(timer); revision++; map.off('moveend', updateCredit) })
  layer.on('tileerror', () => {
    if (!warned && map.hasLayer(layer)) {
      warned = true
      announce('Some Google tiles could not load. Reselect Google Maps to retry; ranking evidence is unchanged.')
    }
  })
  return layer
}
