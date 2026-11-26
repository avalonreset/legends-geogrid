import { describe, it } from 'node:test'
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
const { PersistentTileLayer } = await import('../src/persistent-tiles.js')
const { createOsmLayer } = await import('../src/osm-tiles.js')
const { installWheelZoom } = await import('../src/wheel-zoom.js')

describe('Zero-strobe persistent tile pyramid and smooth wheel zoom', () => {
  it('configures OSM layer with keepBuffer 6 and updateWhenZooming false', () => {
    const layer = createOsmLayer({ dark: true, muted: true })
    assert.equal(layer.options.keepBuffer, 6)
    assert.equal(layer.options.updateWhenZooming, false)
    assert.equal(layer.options.keepParentLevels, 3)
  })

  it('defers tile reloads during smooth zoom and reloads once on smoothzoomend', () => {
    const layer = new PersistentTileLayer('https://example.test/{z}/{x}/{y}.png', { maxZoom: 19 })
    let transformCalls = 0
    let setViewCalls = 0
    layer._tileZoom = 12
    layer._map = {
      _smoothZooming: true,
      getCenter: () => ({ lat: 25.76, lng: -80.19 }),
      getZoom: () => 12.6,
    }
    layer._setZoomTransforms = () => { transformCalls++ }
    layer._setView = () => { setViewCalls++ }

    layer._resetView()
    assert.equal(transformCalls, 1)
    assert.equal(setViewCalls, 0)

    layer._map._smoothZooming = false
    layer._onSmoothZoomEnd()
    assert.equal(setViewCalls, 1)
  })

  it('retains loaded parent pyramid tiles and orders active level above parent floor', () => {
    const layer = new PersistentTileLayer('https://example.test/{z}/{x}/{y}.png', {
      minZoom: 3, maxZoom: 19, keepParentLevels: 2, maxRetainedTiles: 180,
    })
    const removed = []
    layer._tileZoom = 13
    layer._map = { getZoom: () => 13 }
    layer._removeTile = key => { removed.push(key); delete layer._tiles[key] }
    layer._levels = {
      11: { el: { style: {}, children: [{}] } },
      12: { el: { style: {}, children: [{}] } },
      13: { el: { style: {}, children: [{}] } },
      14: { el: { style: {}, children: [{}] } },
    }
    layer._tiles = {
      '4:4:13': { coords: { x: 4, y: 4, z: 13 }, current: true, active: true, loaded: 1 },
      '2:2:12': { coords: { x: 2, y: 2, z: 12 }, current: false, active: true, loaded: 1 },
      '1:1:11': { coords: { x: 1, y: 1, z: 11 }, current: false, active: true, loaded: 1 },
      '0:0:10': { coords: { x: 0, y: 0, z: 10 }, current: false, active: true, loaded: 1 },
    }

    layer._pruneTiles()
    assert.ok('4:4:13' in layer._tiles, 'active tile kept')
    assert.ok('2:2:12' in layer._tiles, 'z-1 parent floor kept')
    assert.ok('1:1:11' in layer._tiles, 'z-2 parent floor kept')
    assert.ok(removed.includes('0:0:10'), 'older z-3 ancestor pruned past keepParentLevels')

    layer._updateLevels()
    const z13 = Number(layer._levels[13].el.style.zIndex)
    const z12 = Number(layer._levels[12].el.style.zIndex)
    const z11 = Number(layer._levels[11].el.style.zIndex)
    const z14 = Number(layer._levels[14].el.style.zIndex)
    assert.ok(z13 > z12 && z12 > z11, `expected active z13 (${z13}) > parent z12 (${z12}) > z11 (${z11})`)
    assert.ok(z12 > z14, `expected parent floor z12 (${z12}) above stale child z14 (${z14})`)
  })

  it('toggles map._smoothZooming and fires smoothzoomend when wheel easing settles', () => {
    let cb = null
    let zoom = 12
    const events = []
    const handlers = {}
    const savedRaf = globalThis.requestAnimationFrame
    const savedCancel = globalThis.cancelAnimationFrame
    globalThis.requestAnimationFrame = fn => { cb = fn; return 1 }
    globalThis.cancelAnimationFrame = () => { cb = null }
    try {
      const removed = []
      const container = {
        clientHeight: 600,
        addEventListener(name, fn) { handlers[name] = fn },
        removeEventListener(name, fn) { if (handlers[name] === fn) removed.push(name) },
      }
      const map = {
        getContainer: () => container,
        getZoom: () => zoom,
        getMinZoom: () => 3,
        getMaxZoom: () => 18,
        mouseEventToContainerPoint: () => [100, 100],
        setZoomAround: (_, next) => { zoom = next },
        fire: name => events.push(name),
      }
      const cancel = installWheelZoom(map)
      handlers.wheel({ deltaY: -100, deltaMode: 0, target: { closest: () => null }, preventDefault() {} })
      assert.equal(map._smoothZooming, true)
      cb(16)
      assert.equal(map._smoothZooming, true)
      assert.deepEqual(events, [])
      cb(1000)
      assert.equal(map._smoothZooming, false)
      assert.equal(zoom, 12.5)
      assert.deepEqual(events, ['smoothzoomend'])
      cancel.destroy()
      assert.deepEqual(removed.sort(), ['pointerdown', 'wheel'])
    } finally {
      globalThis.requestAnimationFrame = savedRaf
      globalThis.cancelAnimationFrame = savedCancel
    }
  })

  it('prevents _setView, _update, and _abortLoading during smooth multi-level zoom on a real L.Map', () => {
    const el = document.createElement('div')
    Object.defineProperty(el, 'clientWidth', { value: 800, configurable: true })
    Object.defineProperty(el, 'clientHeight', { value: 600, configurable: true })
    document.body.appendChild(el)
    const map = L.map(el, {
      zoomControl: false,
      zoomSnap: 0,
      zoomAnimation: false,
      fadeAnimation: false,
      preferCanvas: true,
    })
    const layer = new PersistentTileLayer('https://example.test/{z}/{x}/{y}.png', {
      maxZoom: 19,
      updateWhenZooming: false,
      updateWhenIdle: false,
    })
    try {
      map.setView([25.76, -80.19], 14, { animate: false })
      layer.addTo(map)
      assert.equal(layer._tileZoom, 14)

      let setViewCalls = 0
      let updateCalls = 0
      let abortCalls = 0
      const origSetView = layer._setView.bind(layer)
      const origUpdate = layer._update.bind(layer)
      const origAbort = layer._abortLoading.bind(layer)
      layer._setView = (...args) => { setViewCalls++; return origSetView(...args) }
      layer._update = (...args) => { updateCalls++; return origUpdate(...args) }
      layer._abortLoading = (...args) => { abortCalls++; return origAbort(...args) }

      map._smoothZooming = true
      for (const nextZoom of [13.5, 13.0, 12.5, 12.0]) {
        map.setView([25.76, -80.19], nextZoom, { animate: false })
      }
      assert.equal(setViewCalls, 0, '_setView must not run while _smoothZooming is true')
      assert.equal(updateCalls, 0, '_update must not run while _smoothZooming is true')
      assert.equal(abortCalls, 0, '_abortLoading must not run while _smoothZooming is true')

      map._smoothZooming = false
      map.fire('smoothzoomend')
      assert.equal(setViewCalls, 1, '_setView runs once when smooth zoom settles')
      assert.equal(layer._tileZoom, 12)
    } finally {
      map.remove()
      el.remove()
    }
  })

  it('survives enumerable properties on Object.prototype in _pruneTiles, _updateLevels, and _retainAncestorPyramid', () => {
    const key = '__geogridPollutedProtoKey'
    const protoObj = { bogus: true }
    Object.defineProperty(Object.prototype, key, {
      value: protoObj,
      enumerable: true,
      configurable: true,
      writable: true,
    })
    Object.defineProperty(Object.prototype, '2:2:12', {
      value: { active: true, loaded: 1 },
      enumerable: true,
      configurable: true,
      writable: true,
    })
    try {
      const layer = new PersistentTileLayer('https://example.test/{z}/{x}/{y}.png', {
        minZoom: 3, maxZoom: 19, keepParentLevels: 2, maxRetainedTiles: 180,
      })
      const removed = []
      layer._tileZoom = 13
      layer._map = { getZoom: () => 13 }
      layer._removeTile = k => { removed.push(k); delete layer._tiles[k] }
      layer._levels = {
        13: { el: { style: {}, children: [{}] } },
      }
      layer._tiles = {
        '4:4:13': { coords: { x: 4, y: 4, z: 13 }, current: true, active: true, loaded: 1 },
        '0:0:10': { coords: { x: 0, y: 0, z: 10 }, current: false, active: true, loaded: 1 },
      }

      layer._pruneTiles()
      layer._updateLevels()

      assert.deepEqual(removed, ['0:0:10'])
      assert.equal('retain' in protoObj, false, 'prototype object must not be mutated')
      assert.equal('retain' in Object.prototype['2:2:12'], false, 'prototype tile key must not be retained')
      assert.ok(Number(layer._levels[13].el.style.zIndex) > 0)
    } finally {
      delete Object.prototype[key]
      delete Object.prototype['2:2:12']
    }
  })
})
