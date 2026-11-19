// Captured while the viewer script is executing, before any lazy import runs.
const scriptSrc = typeof document !== 'undefined' && document.currentScript && document.currentScript.src || ''

export const viewerRuntime = {
  scriptSrc,
  workerOverride: null,
  workerUrl() {
    if (this.workerOverride) return this.workerOverride
    if (!scriptSrc) throw new Error('Cannot locate geogrid-viewer-worker.js. Pass workerUrl to GeoGridViewer.mount().')
    return new URL('geogrid-viewer-worker.js', scriptSrc).href
  },
}
