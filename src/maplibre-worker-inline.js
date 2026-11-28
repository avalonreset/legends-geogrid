// Static Companion (file://) build: a page opened from disk cannot load a worker script from a file URL,
// so the MapLibre worker source is bundled as text and started from a Blob URL created by this page.
//
// Chrome reports location.origin as "file://" while a blob URL made there has origin "null", so MapLibre
// treats a plain blob URL as cross-origin and wraps it in a module shim that cannot import it. A URL that
// ends in ".cjs" tells MapLibre to start a classic worker instead (it re-reads the blob into a fresh one),
// which works on file:// and http(s) alike. The worker's only module syntax is its trailing default export.
import workerSource from 'maplibre-gl/dist/maplibre-gl-worker.mjs?raw'
import { classicWorkerSource } from './classic-worker-source.js'

export { classicWorkerSource }

let blobUrl = null

export async function maplibreWorkerUrl() {
  if (!blobUrl) {
    let url = null
    try {
      url = URL.createObjectURL(new Blob([classicWorkerSource(workerSource)], { type: 'text/javascript' }))
      const probe = new Worker(url)
      probe.terminate()
    } catch {
      if (url) { try { URL.revokeObjectURL?.(url) } catch { /* already revoked */ } }
      throw new Error('Web Workers are unavailable in this browser.')
    }
    blobUrl = `${url}#maplibre-gl-worker.cjs`
  }
  return blobUrl
}
