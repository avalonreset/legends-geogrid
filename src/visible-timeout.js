// A load deadline that only counts time while the page is visible. Chrome pauses
// requestAnimationFrame in background tabs, so a map opened behind another tab
// cannot fire its first render (and its load event) until the user looks at it.
// A wall-clock timer would report a healthy basemap as unavailable in that case.
export function visibleTimeout(ms, onTimeout, doc = globalThis.document) {
  let remaining = ms
  let startedAt = 0
  let timer = null
  let finished = false
  const fire = () => { timer = null; stop(); onTimeout() }
  const start = () => {
    if (finished || timer !== null || doc?.hidden) return
    startedAt = Date.now()
    timer = setTimeout(fire, Math.max(0, remaining))
  }
  const pause = () => {
    if (timer === null) return
    clearTimeout(timer)
    timer = null
    remaining -= Date.now() - startedAt
  }
  const onVisibility = () => (doc.hidden ? pause() : start())
  function stop() {
    finished = true
    if (timer !== null) clearTimeout(timer)
    timer = null
    doc?.removeEventListener?.('visibilitychange', onVisibility)
  }
  doc?.addEventListener?.('visibilitychange', onVisibility)
  start()
  return stop
}
