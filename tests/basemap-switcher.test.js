import { test } from 'node:test'
import assert from 'node:assert/strict'
import { JSDOM } from 'jsdom'

const dom = new JSDOM('<!doctype html><html><body><div id="m"></div></body></html>', { url: 'http://127.0.0.1/' })
globalThis.window = dom.window
globalThis.document = dom.window.document
globalThis.HTMLElement = dom.window.HTMLElement
globalThis.SVGElement = dom.window.SVGElement
globalThis.Image = dom.window.Image
globalThis.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} })

const L = (await import('leaflet')).default
const { createBasemapSwitcher } = await import('../src/basemap-switcher.js')

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

function makeMap() {
  const el = document.createElement('div')
  Object.defineProperty(el, 'clientWidth', { value: 800, configurable: true })
  Object.defineProperty(el, 'clientHeight', { value: 600, configurable: true })
  document.body.appendChild(el)
  const map = L.map(el, { zoomControl: false, zoomAnimation: false, fadeAnimation: false, preferCanvas: true })
  map.setView([25.76, -80.19], 12, { animate: false })
  return { map, el }
}

function tileLayers(map) {
  const found = []
  map.eachLayer(layer => { if (layer instanceof L.TileLayer) found.push(layer) })
  return found
}

test('superseding a pending basemap cancels it, detaches its layer and stays silent', async () => {
  const { map, el } = makeMap()
  const statuses = []
  const changes = []
  const announcements = []
  try {
    const switcher = createBasemapSwitcher(map, {
      announce: message => announcements.push(message),
      onChange: id => changes.push(id),
      onStatus: status => statuses.push(status),
      basemaps: [
        { id: 'light', name: 'Light', kind: 'osm' },
        { id: 'vector', name: 'Vector', style: 'fiord' },
      ],
      fallbackId: 'light',
    })
    const first = switcher.set('light')
    assert.equal(tileLayers(map).length, 1, 'first basemap layer is mounted while pending')
    // Supersede before the first load settles. The vector style fails fast in jsdom (no WebGL),
    // which is fine: the point is that the pending raster load is cancelled immediately.
    const started = Date.now()
    const second = switcher.set('vector')
    await first
    const elapsed = Date.now() - started
    assert.ok(elapsed < 1100, `superseded load settled promptly (${elapsed}ms), not on its 1200ms fallback timer`)
    assert.equal(tileLayers(map).length, 0, 'superseded in-flight layer was detached, not left mounted')
    await second
    assert.deepEqual(changes, [])
    assert.deepEqual(statuses.filter(s => s.phase === 'ready'), [])
    assert.deepEqual(announcements.filter(text => text.includes('Light')), [])
  } finally {
    map.remove()
    el.remove()
  }
})

test('map unload cancels a pending basemap and suppresses every later callback', async () => {
  const { map, el } = makeMap()
  const statuses = []
  const announcements = []
  const switcher = createBasemapSwitcher(map, {
    announce: message => announcements.push(message),
    onChange: () => statuses.push({ phase: 'change' }),
    onStatus: status => statuses.push(status),
    basemaps: [{ id: 'light', name: 'Light', kind: 'osm' }],
    fallbackId: 'light',
  })
  const pending = switcher.set('light')
  assert.deepEqual(statuses, [{ phase: 'loading', id: 'light' }])
  map.remove()
  await pending
  await sleep(50)
  assert.deepEqual(statuses, [{ phase: 'loading', id: 'light' }], 'no ready or error status after unload')
  assert.deepEqual(announcements, [])
  await switcher.set('light')
  assert.deepEqual(statuses, [{ phase: 'loading', id: 'light' }], 'set after unload is a no-op')
  el.remove()
})
