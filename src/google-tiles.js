import { PersistentTileLayer } from './persistent-tiles.js'

const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
const DEFAULT_SESSION_PATH = '/api/maps/google/session'
const DEFAULT_CREDIT_IMAGE = '/google-maps-attribution.svg'
const badStatus = status => status === 403 || status === 429 || status >= 500

// sessionPath: URL that accepts POST {style} and answers {id}. Tiles are read from
// <dirname(sessionPath)>/<id>/tiles/{z}/{x}/{y} and attribution from <dirname>/<id>/viewport.
// onFailure: when given, an HTTP 403/429/5xx tile (or a network error) calls it once instead of showing a warning.
export async function createGoogleTiles(map, style, announce, { sessionPath = DEFAULT_SESSION_PATH, attributionImage, onFailure = null } = {}) {
  const base = sessionPath.replace(/\/session\/?$/, '')
  const image = attributionImage !== undefined ? attributionImage : sessionPath === DEFAULT_SESSION_PATH ? DEFAULT_CREDIT_IMAGE : null
  const credit = `<a href="https://maps.google.com/" target="_blank" rel="noopener" class="google-map-credit">${image
    ? `<img src="${escape(image)}" alt="Google Maps" height="16">` : 'Google Maps'}</a>`
  const response = await fetch(sessionPath, {
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
    const result = await fetch(`${base}/${session.id}/viewport?${params}`)
    const info = await result.json()
    if (!result.ok || !info.copyright) throw new Error('Google map attribution could not load.')
    return info
  }
  const info = await viewport()
  const layer = new PersistentTileLayer(`${base}/${session.id}/tiles/{z}/{x}/{y}`, {
    attribution: `${credit}<span class="google-data-credit">${escape(info.copyright)}</span>`,
    maxZoom: 18, maxNativeZoom: 18, keepBuffer: 6, updateWhenZooming: false, updateWhenIdle: true,
    className: 'google-interactive-tiles',
  })
  let timer, revision = 0, warned = false, failed = false
  const updateCredit = () => {
    if (map._smoothZooming) return
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
        if (onFailure && map.hasLayer(layer) && id === revision && !failed) { failed = true; onFailure('attribution') }
        else if (!onFailure && map.hasLayer(layer) && id === revision) announce('Google map attribution could not refresh. Reselect the map to retry.')
      }
    }, 350)
  }
  layer.on('add', () => { map.on('moveend', updateCredit); map.on('smoothzoomend', updateCredit) })
  layer.on('remove', () => { clearTimeout(timer); revision++; map.off('moveend', updateCredit); map.off('smoothzoomend', updateCredit) })
  layer.on('tileerror', event => {
    if (onFailure) {
      if (failed) return
      const src = event.tile?.src || ''
      // Leaflet reports no status, so ask the same URL again: 403, 429, 5xx or a network failure ends Google for the session.
      fetch(src, { cache: 'no-store' }).then(result => badStatus(result.status), () => true).then(bad => {
        if (bad && !failed) { failed = true; onFailure('tiles') }
      })
      return
    }
    if (!warned && map.hasLayer(layer)) {
      warned = true
      announce('Some Google tiles could not load. Reselect Google Maps to retry; ranking evidence is unchanged.')
    }
  })
  return layer
}
