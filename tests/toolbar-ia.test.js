import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import vm from 'node:vm'
import { JSDOM } from 'jsdom'
import { buildViewer, createWindow } from './helpers/viewer-window.js'

const root = resolve(import.meta.dirname, '..')
const readJson = rel => JSON.parse(readFileSync(join(root, rel), 'utf8'))
const hexFixture = readJson('tests/helpers/hex-circle-study.json')
const squareFixture = readJson('examples/viewer-companion-depth100-fixture.json')
const phillyStarter = readJson('src/data/cosmis-deli-philly-study.json')
const ON = { perPointListings: true, profiles: true, nameReview: false, campaignResearch: false, strategyRoom: false }

function makeRadiusGridFixture() {
  const center = { lat: 25.8043047, lng: -80.1955704 }
  const spacingKm = 0.804672
  const step = spacingKm / 111.195
  const cosLat = Math.cos((center.lat * Math.PI) / 180)
  const points = []
  for (let y = -1; y <= 1; y++) {
    for (let x = -1; x <= 1; x++) {
      if (Math.hypot(x, y) > 1.05) continue
      points.push({
        tag: `r_${x}_${y}`,
        lat: Number((center.lat + y * step).toFixed(7)),
        lng: Number((center.lng + (x * step) / cosLat).toFixed(7)),
        distance_from_target_km: Math.hypot(x, y) * spacingKm,
        by_lane: {
          q1: {
            status: 'found',
            target_rank: x === 0 && y === 0 ? 1 : 4,
            top_items: [
              { cid: '100', title: 'Primary Shop', rank: x === 0 && y === 0 ? 1 : 4 },
              { cid: '200', title: 'Nearby Rival', rank: x === 0 && y === 0 ? 2 : 1 },
            ],
          },
        },
      })
    }
  }
  return {
    schema: 'geogrid-companion/v1',
    generated_at: '2026-11-25T18:00:00+00:00',
    business: { name: 'Primary Shop', cid: '100' },
    target: { name: 'Primary Shop', cid: '100', lat: center.lat, lng: center.lng },
    location: 'Miami, FL',
    factions: [
      { faction_id: 'TARGET', name: 'Primary Shop', is_target: true, cid: '100', lat: center.lat, lng: center.lng },
      { faction_id: 'cid:200', name: 'Nearby Rival', is_target: false, cid: '200', lat: center.lat, lng: center.lng },
    ],
    lanes: [{ lane_id: 'q1', query: 'car detailing' }],
    points,
    study: {
      geometry: 'radius_grid',
      depth: 30,
      sampling: { geometry: 'radius_grid', center, radius_km: 1.01 * spacingKm, spacing_km: spacingKm },
    },
  }
}
const radiusFixture = makeRadiusGridFixture()

let bundle
before(() => { bundle = buildViewer() })
after(() => bundle?.cleanup())

const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', { bubbles: true, cancelable: true }))
const slotButtons = host => [...host.querySelectorAll('.map-options button')]

function mountStandalone(study, search = '') {
  const runtimeJs = readFileSync(join(root, 'assets/companion-runtime.js'), 'utf8')
  const dom = new JSDOM('<!doctype html><html><body><div id="app"></div></body></html>', {
    pretendToBeVisual: true,
    runScripts: 'outside-only',
    url: `https://app.example.test/${search}`,
  })
  const w = dom.window
  const ctx = new Proxy({}, {
    get(target, key) {
      if (key === 'measureText') return () => ({ width: 0 })
      if (key === 'createImageData') return (width, height) => ({ width, height, data: new Uint8ClampedArray(width * height * 4) })
      if (key === 'getImageData') return (x, y, width, height) => ({ width, height, data: new Uint8ClampedArray(width * height * 4) })
      return key in target ? target[key] : () => ctx
    },
    set(target, key, value) { target[key] = value; return true },
  })
  w.HTMLCanvasElement.prototype.getContext = type => (type === '2d' ? ctx : null)
  w.MessageChannel = MessageChannel
  Object.defineProperty(w.HTMLElement.prototype, 'clientWidth', { get: () => 900 })
  Object.defineProperty(w.HTMLElement.prototype, 'clientHeight', { get: () => 600 })
  w.HTMLElement.prototype.getBoundingClientRect = () => ({ x: 0, y: 0, left: 0, top: 0, right: 900, bottom: 600, width: 900, height: 600 })
  w.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} })
  w.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
  w.Worker = class { postMessage() {} terminate() {} addEventListener() {} removeEventListener() {} }
  w.fetch = async () => { throw new Error('offline test window') }
  w.__GEOGRID_BOOTSTRAP__ = { study }
  new vm.Script(runtimeJs).runInContext(dom.getInternalVMContext())
  return { dom, w, root: w.document.querySelector('#app'), api: w.GeoGrid }
}

test('5-slot fixed toolbar stays anchored with zero retired buttons and live triangles across Rankings, Local leaders and Campaigns on hex studies', () => {
  const { dom, w } = createWindow(bundle.js)
  try {
    const host = w.document.querySelector('#host')
    const viewer = w.GeoGridViewer.mount(host, hexFixture, { capabilities: ON })

    // Retired buttons must not exist anywhere in the toolbar.
    for (const removed of ['#coverage-dots', '#translucent', '#corner-blends', '#clip-circle']) {
      assert.equal(host.querySelector(removed), null, `${removed} should be removed`)
    }
    assert.ok(host.querySelector('.map-options .map-options-divider'), 'hairline divider separates the two groups')

    const expectedOrderFor = (contestedLabel = 'contested') => [
      ['elevation-contours', 'topography'],
      ['triangle-estimates', 'triangles'],
      ['contested-ground', contestedLabel],
      ['grid-dots', 'pins'],
      ['distance-rings', 'rings'],
    ]

    const assertFixedSlots = (label, contestedLabel = 'contested') => {
      const buttons = slotButtons(host)
      assert.deepEqual(
        buttons.map(b => [b.id, b.textContent.trim()]),
        expectedOrderFor(contestedLabel),
        `fixed 5-slot order in ${label}`,
      )
      for (const b of buttons) {
        assert.equal(b.hidden, false, `${b.id} must never be hidden in ${label}`)
        assert.ok(!/[\u2013\u2014]/.test(b.title), `${b.id} tooltip must have no em/en-dash`)
      }
    }

    // Default Rankings state on hex_radius: topography ON, triangles OFF, contested disabled, pins OFF, rings ON.
    assertFixedSlots('Rankings')
    const topo = host.querySelector('#elevation-contours')
    const triangles = host.querySelector('#triangle-estimates')
    const contested = host.querySelector('#contested-ground')
    const pins = host.querySelector('#grid-dots')
    const rings = host.querySelector('#distance-rings')

    assert.equal(topo.disabled, false)
    assert.equal(topo.getAttribute('aria-pressed'), 'true')
    assert.equal(triangles.disabled, false)
    assert.equal(triangles.getAttribute('aria-pressed'), 'false')
    assert.equal(contested.disabled, true)
    assert.equal(contested.getAttribute('aria-pressed'), 'false')
    assert.equal(contested.title, 'Available in Local leaders, Campaigns and Keyword stuffing')
    assert.equal(pins.disabled, false)
    assert.equal(pins.getAttribute('aria-pressed'), 'false')
    assert.equal(rings.disabled, false)
    assert.equal(rings.getAttribute('aria-pressed'), 'true')
    assert.equal(host.querySelector('#focus-pill').hidden, false, 'elevation summary pill renders when topography is ON')

    // topography, triangles, and pins are 100% independent layer toggles (any combination allowed!).
    click(w, triangles)
    assert.equal(triangles.getAttribute('aria-pressed'), 'true')
    assert.equal(topo.getAttribute('aria-pressed'), 'true', 'triangles never forces topography off')
    assert.equal(pins.getAttribute('aria-pressed'), 'false', 'triangles never forces pins on')
    assert.equal(pins.disabled, false, 'pins is never locked or disabled')
    assert.equal(host.querySelector('#focus-pill').hidden, false, 'elevation pill stays visible while topography is on')

    // Enable pins alongside triangles + topography (all three active at once).
    click(w, pins)
    assert.equal(pins.getAttribute('aria-pressed'), 'true')
    assert.equal(triangles.getAttribute('aria-pressed'), 'true')
    assert.equal(topo.getAttribute('aria-pressed'), 'true')

    // Turn topography OFF: triangles + pins stay active and pins remains freely toggleable!
    click(w, topo)
    assert.equal(topo.getAttribute('aria-pressed'), 'false')
    assert.equal(triangles.getAttribute('aria-pressed'), 'true')
    assert.equal(pins.getAttribute('aria-pressed'), 'true')
    assert.equal(pins.disabled, false)
    assert.equal(host.querySelector('#focus-pill').hidden, true, 'elevation pill hides while topography is off')

    // Turn pins OFF while keeping triangles ON (triangles alone without pins).
    click(w, pins)
    assert.equal(pins.getAttribute('aria-pressed'), 'false')
    assert.equal(triangles.getAttribute('aria-pressed'), 'true')

    // Turn triangles OFF and restore topography ON.
    click(w, triangles)
    assert.equal(triangles.getAttribute('aria-pressed'), 'false')
    click(w, topo)
    assert.equal(topo.getAttribute('aria-pressed'), 'true')
    assert.equal(pins.disabled, false)
    assert.equal(pins.getAttribute('aria-pressed'), 'false')

    // Toggling pins ON over topography works cleanly.
    click(w, pins)
    assert.equal(pins.getAttribute('aria-pressed'), 'true')
    click(w, pins)
    assert.equal(pins.getAttribute('aria-pressed'), 'false')

    // Switch to Local leaders: exact same 5 slots; triangles disabled with tooltip; topography & contested LIVE.
    click(w, host.querySelector('[data-view="factions"]'))
    assertFixedSlots('Local leaders')
    assert.equal(topo.disabled, false)
    assert.equal(topo.getAttribute('aria-pressed'), 'true')
    assert.equal(triangles.disabled, true)
    assert.equal(triangles.getAttribute('aria-pressed'), 'false')
    assert.equal(triangles.title, 'Available in Rankings, Campaigns and Keyword stuffing')
    assert.equal(contested.disabled, false)
    assert.equal(contested.getAttribute('aria-pressed'), 'false')
    assert.equal(pins.disabled, false)
    assert.equal(pins.getAttribute('aria-pressed'), 'false')
    assert.equal(rings.disabled, false)
    assert.equal(rings.getAttribute('aria-pressed'), 'true')

    // Toggle topography OFF in Local leaders: pins remain interactive over flat territory polygons.
    click(w, topo)
    assert.equal(topo.getAttribute('aria-pressed'), 'false')
    assert.equal(pins.disabled, false)
    click(w, topo)
    assert.equal(topo.getAttribute('aria-pressed'), 'true')

    // Toggle contested ON and pins ON in Local leaders.
    click(w, contested)
    assert.equal(contested.getAttribute('aria-pressed'), 'true')
    click(w, pins)
    assert.equal(pins.getAttribute('aria-pressed'), 'true')

    // Switch to Campaigns: ALL 5 buttons are LIVE on a hex study (zero disabled buttons!).
    click(w, host.querySelector('[data-view="campaigns"]'))
    assertFixedSlots('Campaigns', 'flip seams')
    assert.equal(topo.disabled, false)
    assert.equal(topo.getAttribute('aria-pressed'), 'true')
    assert.equal(triangles.disabled, false)
    assert.equal(triangles.getAttribute('aria-pressed'), 'false')
    assert.equal(contested.disabled, false)
    assert.equal(pins.disabled, false)
    assert.equal(rings.disabled, false)
    click(w, pins)
    assert.equal(pins.getAttribute('aria-pressed'), 'false')

    // Rings toggle works across views.
    click(w, rings)
    assert.equal(rings.getAttribute('aria-pressed'), 'false')

    viewer.destroy()
  } finally {
    dom.window.close()
  }
})

test('fitStudy centers dead-on [anchor.lat, anchor.lng] even when eastern points are clipped by water', () => {
  // Clone starter and drop eastern points past the anchor to simulate asymmetric coastal clipping.
  const waterClipped = structuredClone(phillyStarter)
  const anchorLat = waterClipped.target.lat
  const anchorLng = waterClipped.target.lng
  waterClipped.points = waterClipped.points.filter(p => p.lng <= anchorLng + 0.01)
  // Confirm points themselves are indeed skewed west of the anchor!
  const lngs = waterClipped.points.map(p => p.lng)
  const rawMidLng = (Math.min(...lngs) + Math.max(...lngs)) / 2
  assert.ok(Math.abs(rawMidLng - anchorLng) > 0.015, `expected water-clipped points midpoint (${rawMidLng}) to be skewed west of anchor (${anchorLng})`)

  const { dom, w, root: appRoot, api } = mountStandalone(waterClipped)
  try {
    const initial = api.getCenter()
    assert.ok(Math.abs(initial.lat - anchorLat) < 0.001, `initial lat ${initial.lat} should match anchor ${anchorLat}`)
    assert.ok(Math.abs(initial.lng - anchorLng) < 0.001, `initial lng ${initial.lng} should match anchor ${anchorLng}`)

    // Clicking Fit study re-centers dead-on [anchor.lat, anchor.lng].
    api.fitStudy(false)
    const afterFit = api.getCenter()
    assert.ok(Math.abs(afterFit.lat - anchorLat) < 0.001, `fitStudy lat ${afterFit.lat} should match anchor ${anchorLat}`)
    assert.ok(Math.abs(afterFit.lng - anchorLng) < 0.001, `fitStudy lng ${afterFit.lng} should match anchor ${anchorLng}`)

    click(w, appRoot.querySelector('#fit'))
    const afterBtn = api.getCenter()
    assert.ok(Math.abs(afterBtn.lat - anchorLat) < 0.002, `#fit button lat ${afterBtn.lat} should stay centered on anchor ${anchorLat}`)
    assert.ok(Math.abs(afterBtn.lng - anchorLng) < 0.002, `#fit button lng ${afterBtn.lng} should stay centered on anchor ${anchorLng}`)
  } finally {
    dom.window.close()
  }
})

test('default circle clipping and URL overrides behave cleanly across hex_radius, radius_grid and square_grid', () => {
  // hex_radius defaults: clipCircle ON, showDots OFF, contours ON, blends (triangles) OFF, contested OFF, rings ON.
  const hex = mountStandalone(hexFixture)
  try {
    const s = hex.api.getState()
    assert.equal(s.clipCircle, true, 'hex_radius defaults clipCircle to true')
    assert.equal(s.showDots, false, 'hex_radius defaults pins OFF')
    assert.equal(s.contours, true, 'hex_radius defaults topography ON')
    assert.equal(s.blends, false, 'hex_radius defaults triangles OFF')
    assert.equal(s.contested, false, 'hex_radius defaults contested OFF')
    assert.equal(s.rings, true, 'rings default ON')
  } finally {
    hex.dom.window.close()
  }

  // ?triangles=1 enables triangles independently without forcing topography off or pins on.
  const triUrl = mountStandalone(hexFixture, '?triangles=1')
  try {
    const s = triUrl.api.getState()
    assert.equal(s.blends, true, '?triangles=1 enables triangles')
    assert.equal(s.contours, true, '?triangles=1 keeps topography independent')
    assert.equal(s.showDots, false, '?triangles=1 keeps pins independent')
  } finally {
    triUrl.dom.window.close()
  }

  // ?triangles=1&dots=1&contours=0 restores triangles + pins without topography.
  const triPinsUrl = mountStandalone(hexFixture, '?triangles=1&dots=1&contours=0')
  try {
    const s = triPinsUrl.api.getState()
    assert.equal(s.blends, true, '?triangles=1&dots=1&contours=0 enables triangles')
    assert.equal(s.contours, false, 'contours=0 turns topography off')
    assert.equal(s.showDots, true, 'dots=1 turns pins on')
  } finally {
    triPinsUrl.dom.window.close()
  }

  // ?clip=0 still disables circle clipping for debugging.
  const unclipped = mountStandalone(hexFixture, '?clip=0')
  try {
    assert.equal(unclipped.api.getState().clipCircle, false, '?clip=0 disables circle clipping')
  } finally {
    unclipped.dom.window.close()
  }

  // radius_grid defaults: clipCircle ON, blends ON, topography/triangles/contested disabled.
  const radius = mountStandalone(radiusFixture)
  try {
    const s = radius.api.getState()
    assert.equal(s.clipCircle, true, 'radius_grid defaults clipCircle to true')
    assert.equal(s.blends, true, 'legacy radius_grid keeps blends enabled')
    assert.equal(radius.root.querySelector('#elevation-contours').disabled, true)
    assert.equal(radius.root.querySelector('#triangle-estimates').disabled, true)
    assert.equal(radius.root.querySelector('#contested-ground').disabled, true)
    assert.equal(radius.root.querySelector('#grid-dots').disabled, false)
    assert.equal(radius.root.querySelector('#distance-rings').disabled, false)
  } finally {
    radius.dom.window.close()
  }

  // square_grid defaults: clipCircle OFF, blends ON, 5 slots intact.
  const square = mountStandalone(squareFixture)
  try {
    const s = square.api.getState()
    assert.equal(s.clipCircle, false, 'square_grid leaves clipCircle false')
    assert.equal(s.blends, true, 'legacy square_grid keeps blends enabled')
    assert.equal(slotButtons(square.root).length, 5)
  } finally {
    square.dom.window.close()
  }

  // ?clip=1 on non-circular square_grid stays consistent with circular-only clipping.
  const squareClipParam = mountStandalone(squareFixture, '?clip=1')
  try {
    assert.equal(squareClipParam.api.getState().clipCircle, false, '?clip=1 does not enable circle clip on square_grid')
    assert.equal(new URL(squareClipParam.w.location.href).searchParams.has('clip'), false)
  } finally {
    squareClipParam.dom.window.close()
  }
})

test('destroy() removes document keydown listener, cancels tauFrame, and does not throw on Escape after focusing a leader', () => {
  const { dom, w } = createWindow(bundle.js)
  try {
    const host = w.document.querySelector('#host')
    let keydownAdded = 0
    let keydownRemoved = 0
    const origAdd = w.document.addEventListener.bind(w.document)
    const origRemove = w.document.removeEventListener.bind(w.document)
    w.document.addEventListener = (type, fn, opts) => {
      if (type === 'keydown') keydownAdded++
      return origAdd(type, fn, opts)
    }
    w.document.removeEventListener = (type, fn, opts) => {
      if (type === 'keydown') keydownRemoved++
      return origRemove(type, fn, opts)
    }

    const viewer = w.GeoGridViewer.mount(host, hexFixture, { capabilities: ON })
    click(w, host.querySelector('[data-view="factions"]'))
    const leaderRow = host.querySelector('[data-leader]')
    assert.ok(leaderRow, 'Local leaders renders at least one leader row')
    click(w, leaderRow)
    assert.equal(host.querySelector('#focus-pill').hidden, false, 'leader focus is active prior to destroy')

    // Start contested ground animation (tauFrame) before destroy.
    click(w, host.querySelector('#contested-ground'))

    viewer.destroy()
    assert.ok(keydownAdded >= 1, 'keydown listener was registered')
    assert.equal(keydownRemoved, keydownAdded, 'all document keydown listeners removed on destroy')

    // Pressing Escape after destroy must not throw TypeError against emptied root.
    assert.doesNotThrow(() => {
      w.document.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }))
    })
  } finally {
    dom.window.close()
  }
})
