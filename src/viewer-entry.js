// Entry for the reusable GeoGrid report viewer (global: GeoGridViewer).
// It never reads window.__GEOGRID_BOOTSTRAP__ or any other page global: the host passes everything to mount().
import { createCompanion } from './companion-app.js'
import { mountLeanViewer } from './viewer/viewer-lean.js'
import { viewerRuntime } from './viewer/viewer-runtime.js'
import { BASEMAPS } from './basemap-switcher.js'
import { LEAN_SCHEMA, COMPANION_SCHEMAS } from './viewer/lean-model.js'
import './viewer/viewer-overrides.css'

export const version = __VIEWER_VERSION__
export const schemas = [LEAN_SCHEMA, ...COMPANION_SCHEMAS]

const CAPABILITY_KEYS = ['perPointListings', 'profiles', 'nameReview', 'campaignResearch', 'strategyRoom']
const DEFAULT_BASEMAP = 'ofm-dark'

function resolveElement(el) {
  const node = typeof el === 'string' ? document.querySelector(el) : el
  if (!node || node.nodeType !== 1) throw new Error('GeoGridViewer.mount: el must be an element or a selector that matches one')
  return node
}

function resolveBasemaps(options) {
  // Raster OpenStreetMap tiles are not part of this build; only OpenFreeMap vector styles and the optional Google client.
  const googleOn = typeof options.googleSessionPath === 'string' && options.googleSessionPath.length > 0
  const usable = BASEMAPS.filter(b => b.kind !== 'osm' && (googleOn || !b.google))
  const wanted = Array.isArray(options.basemaps) && options.basemaps.length ? options.basemaps : usable.map(b => b.id)
  const list = wanted.map(id => usable.find(b => b.id === id)).filter(Boolean)
  if (!list.length) throw new Error('GeoGridViewer.mount: no usable basemaps in options.basemaps')
  const fallback = (list.find(b => b.id === DEFAULT_BASEMAP) || list.find(b => !b.google) || list[0]).id
  const preferred = list.some(b => b.id === options.defaultBasemap) ? options.defaultBasemap : fallback
  return { list, fallback, preferred }
}

// mount(el, model, options) -> { destroy() } (the full study also returns selectPoint(tag))
//   model: "geogrid-viewer/v1" (lean hosted model) or "geogrid-companion/v1" (full study)
//   options.capabilities: { perPointListings, profiles, nameReview, campaignResearch, strategyRoom }. A panel is shown only when its flag is true;
//     a missing flag means off. Flags matter for geogrid-companion/v1 models; the lean model never shows these panels.
//   options.basemaps: ids to offer, default every OpenFreeMap style (plus Google when googleSessionPath is set)
//   options.defaultBasemap: id, default "ofm-dark"
//   options.googleSessionPath: same-origin session URL; enables the Google tile client
//   options.attribution: plain-text credit shown on the map, default OpenFreeMap / OpenMapTiles / OpenStreetMap contributors
//   options.workerUrl: optional URL of geogrid-viewer-worker.js when it is not next to this script
//   options.units: "mi" (default) or "km" for the lean model
function mount(el, model, options = {}) {
  const node = resolveElement(el)
  if (!model || typeof model !== 'object') throw new Error('GeoGridViewer.mount: model must be an object')
  if (options.workerUrl) viewerRuntime.workerOverride = String(options.workerUrl)
  const { list, fallback, preferred } = resolveBasemaps(options)
  const common = { basemaps: list, fallbackBasemap: fallback, defaultBasemap: preferred,
    googleSessionPath: options.googleSessionPath || undefined, attribution: options.attribution || undefined }
  if (model.schema === LEAN_SCHEMA) return mountLeanViewer(node, model, { ...common, units: options.units })
  if (COMPANION_SCHEMAS.includes(model.schema)) {
    const capabilities = Object.fromEntries(CAPABILITY_KEYS.map(k => [k, options.capabilities?.[k] === true]))
    const app = createCompanion({ embedded: true, root: node, study: model, capabilities, basemaps: list.map(b => b.id),
      defaultBasemap: preferred, googleSessionPath: common.googleSessionPath, attribution: common.attribution,
      campaignResearch: options.campaignResearch, nameReview: options.nameReview })
    // selectPoint(tag) opens that location's rankings (needs capabilities.perPointListings); it throws for an unknown tag.
    return { destroy: () => app.destroy(), selectPoint: id => app.selectPoint(id) }
  }
  throw new Error(`GeoGridViewer.mount: unsupported model schema ${String(model.schema)}`)
}

export { mount }
