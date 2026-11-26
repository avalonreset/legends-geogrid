// Retain every wheel delta while easing smoothly toward the accumulated zoom
// target with inertial exponential damping. Coordinates with PersistentTileLayer
// via map._smoothZooming + smoothzoomend so parent tiles stay painted while
// zooming and target-zoom tiles load cleanly once motion settles.
export function installWheelZoom(map, { wheelPxPerZoomLevel = 200, dampingMs = 65 } = {}) {
  let frame = 0, target = map.getZoom(), anchor, lastTime = 0
  const container = map.getContainer()
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)')
  const pxPerZoom = Math.max(40, Number(wheelPxPerZoomLevel) || 200)
  const tauMs = Math.max(16, Number(dampingMs) || 65)

  function finish() {
    const wasZooming = !!map._smoothZooming
    map._smoothZooming = false
    if (wasZooming) map.fire?.('smoothzoomend')
  }

  function cancel() {
    if (frame) {
      cancelAnimationFrame(frame)
      frame = 0
    }
    target = map.getZoom()
    lastTime = 0
    finish()
  }

  function tick(time) {
    // Ease by elapsed time, not frame count. Dense grids can miss a frame;
    // clamping each interval to 40ms made the same wheel gesture take longer.
    const dt = lastTime ? Math.max(0, time - lastTime) : 16
    lastTime = time
    const current = map.getZoom()
    const next = reducedMotion.matches ? target : current + (target - current) * (1 - Math.exp(-dt / tauMs))
    if (Math.abs(target - next) < .001) {
      frame = 0
      lastTime = 0
      map._smoothZooming = false
      map.setZoomAround(anchor, target, { animate: false })
      map.fire?.('smoothzoomend')
      return
    }
    map._smoothZooming = true
    map.setZoomAround(anchor, next, { animate: false })
    frame = requestAnimationFrame(tick)
  }

  const onWheel = event => {
    if (event.target.closest('.map-options')) return
    event.preventDefault()
    if (!frame) { target = map.getZoom(); lastTime = 0 }
    const pixels = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? container.clientHeight : 1)
    target = Math.max(map.getMinZoom(), Math.min(map.getMaxZoom(), target - pixels / pxPerZoom))
    anchor = map.mouseEventToContainerPoint(event)
    map._smoothZooming = true
    if (!frame) frame = requestAnimationFrame(tick)
  }
  container.addEventListener('wheel', onWheel, { passive: false })
  container.addEventListener('pointerdown', cancel)
  cancel.destroy = () => {
    cancel()
    container.removeEventListener?.('wheel', onWheel)
    container.removeEventListener?.('pointerdown', cancel)
  }
  return cancel
}
