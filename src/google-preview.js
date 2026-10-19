import L from 'leaflet'
import { RankCanvasLayer } from './rank-canvas.js'

export async function showGooglePreview(map, pointsLayer) {
  const dialog = document.createElement('dialog')
  dialog.className = 'google-preview-dialog'
  dialog.innerHTML = `<header><h2>Google Maps · snapshot preview</h2><button type="button">Close</button></header>
    <p>Same ranking evidence over Google imagery. This connection supplies a fixed snapshot; interactive Google tiles are not enabled. Google map requests are billed separately.</p>
    <div class="google-preview-status" role="status">Loading Google map…</div><div class="google-preview-map" hidden></div>`
  document.body.append(dialog)
  const abort = new AbortController()
  let preview, blobURL, observer
  dialog.querySelector('button').onclick = () => dialog.close()
  dialog.addEventListener('close', () => {
    abort.abort(); observer?.disconnect(); preview?.remove()
    if (blobURL) URL.revokeObjectURL(blobURL)
    dialog.remove()
  }, { once: true })
  dialog.showModal()
  try {
    const center = map.getCenter(), size = map.getSize()
    const zoom = Math.max(3, Math.min(18, Math.round(map.getZoom() - Math.log2(Math.max(size.x, size.y) / 640))))
    const response = await fetch('/api/maps/google-preview', { method: 'POST', signal: abort.signal,
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lat: center.lat, lng: center.lng, zoom }) })
    if (!response.ok) throw new Error('Google preview could not load. Check the server’s Maps Static API configuration.')
    blobURL = URL.createObjectURL(await response.blob())
    if (!dialog.open) return
    const box = dialog.querySelector('.google-preview-map')
    box.hidden = false
    preview = L.map(box, { zoomControl: false, attributionControl: false, zoomSnap: 0,
      dragging: false, scrollWheelZoom: false, doubleClickZoom: false, boxZoom: false,
      touchZoom: false, keyboard: false, zoomAnimation: false })
    const middle = map.project(center, zoom)
    const bounds = L.latLngBounds(map.unproject(middle.subtract([320, 320]), zoom),
      map.unproject(middle.add([320, 320]), zoom))
    const fit = () => { preview.invalidateSize(); preview.setView(center, zoom + Math.log2(box.clientWidth / 640)) }
    fit()
    L.imageOverlay(blobURL, bounds).addTo(preview)
    preview.createPane('rankingPane').style.zIndex = '450'
    preview.getPane('rankingPane').style.pointerEvents = 'none'
    const ranks = new RankCanvasLayer({ onSelect() {} }).addTo(preview)
    ranks.setData(pointsLayer.cells, pointsLayer.diamonds, pointsLayer.spacing, pointsLayer.translucent, pointsLayer.blendBoundary)
    observer = new ResizeObserver(fit)
    observer.observe(box)
    dialog.querySelector('[role=status]').textContent = 'Full Google image and attribution preserved. Hover over a marker for its rank.'
  } catch (error) {
    if (dialog.open) dialog.querySelector('[role=status]').textContent = error.message
  }
}
