// Resolves the MapLibre worker URL. The viewer package replaces this module so the worker is loaded
// from a same-origin file next to the viewer script instead of a bundler-generated asset URL.
export async function maplibreWorkerUrl() {
  return (await import('maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url')).default
}
