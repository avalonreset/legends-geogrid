// Retain every wheel delta while easing toward the accumulated zoom target.
// Native Leaflet wheel debouncing/zoom-animation gating is disabled by the caller.
export function installWheelZoom(map) {
  let frame = 0, target = map.getZoom(), anchor, lastTime = 0
  const container = map.getContainer()
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)')
  function cancel() {
    cancelAnimationFrame(frame)
    frame = 0
    target = map.getZoom()
  }
  function tick(time) {
    // Ease by elapsed time, not frame count. Dense grids can miss a frame;
    // clamping each interval to 40ms made the same wheel gesture take longer.
    const dt = lastTime ? time - lastTime : 16
    lastTime = time
    const current = map.getZoom()
    const next = reducedMotion.matches ? target : current + (target - current) * (1 - Math.exp(-dt / 65))
    if (Math.abs(target - next) < .001) {
      map.setZoomAround(anchor, target, { animate: false })
      frame = 0
      return
    }
    map.setZoomAround(anchor, next, { animate: false })
    frame = requestAnimationFrame(tick)
  }
  container.addEventListener('wheel', event => {
    if (event.target.closest('.map-options')) return
    event.preventDefault()
    if (!frame) { target = map.getZoom(); lastTime = 0 }
    const pixels = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? container.clientHeight : 1)
    target = Math.max(map.getMinZoom(), Math.min(map.getMaxZoom(), target - pixels / 200))
    anchor = map.mouseEventToContainerPoint(event)
    if (!frame) frame = requestAnimationFrame(tick)
  }, { passive: false })
  container.addEventListener('pointerdown', cancel)
  return cancel
}
