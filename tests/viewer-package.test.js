import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import vm from 'node:vm'
import { JSDOM } from 'jsdom'
import postcss from 'postcss'
import { normalizeLeanModel, formatShare, formatSigned } from '../src/viewer/lean-model.js'

const root = resolve(import.meta.dirname, '..')
const readJson = rel => JSON.parse(readFileSync(join(root, rel), 'utf8'))
const fixture = readJson('examples/viewer-lean-fixture.json')
const schema = readJson('docs/geogrid-viewer-v1.schema.json')
const companionStudy = readJson('src/data/home-slice-study.json')
const OFF = { perPointListings: false, profiles: false, nameReview: false, campaignResearch: false, strategyRoom: false }

let outDir, js, css, worker

before(() => {
  outDir = mkdtempSync(join(tmpdir(), 'ggv-'))
  execFileSync(process.execPath, [join(root, 'node_modules/vite/bin/vite.js'), 'build', '--config', 'vite.viewer.config.js',
    '--outDir', outDir, '--emptyOutDir'], { cwd: root, stdio: 'pipe' })
  js = readFileSync(join(outDir, 'geogrid-viewer.js'), 'utf8')
  css = readFileSync(join(outDir, 'geogrid-viewer.css'), 'utf8')
  worker = readFileSync(join(outDir, 'geogrid-viewer-worker.js'), 'utf8')
})
after(() => { if (outDir) rmSync(outDir, { recursive: true, force: true }) })

// A small JSON Schema checker covering the keywords the model schema uses.
function validate(value, node, path = '$') {
  const errors = []
  if (node.$ref) return validate(value, node.$ref.split('/').slice(1).reduce((n, k) => n[k], schema), path)
  if (node.oneOf) {
    const ok = node.oneOf.some(option => validate(value, option, path).length === 0)
    return ok ? [] : [`${path}: matches no oneOf option`]
  }
  if ('const' in node && value !== node.const) errors.push(`${path}: expected ${node.const}`)
  if (node.type) {
    const types = [].concat(node.type)
    const kind = v => v === null ? 'null' : Array.isArray(v) ? 'array' : Number.isInteger(v) ? 'integer' : typeof v
    const matches = types.some(t => t === kind(value) || (t === 'number' && kind(value) === 'integer'))
    if (!matches) return [`${path}: expected ${types.join('|')}, got ${kind(value)}`]
  }
  if (typeof value === 'number') {
    if ('minimum' in node && value < node.minimum) errors.push(`${path}: below minimum`)
    if ('maximum' in node && value > node.maximum) errors.push(`${path}: above maximum`)
    if ('exclusiveMinimum' in node && value <= node.exclusiveMinimum) errors.push(`${path}: not above exclusive minimum`)
  }
  if (Array.isArray(value)) {
    if ('minItems' in node && value.length < node.minItems) errors.push(`${path}: too few items`)
    if (node.items) value.forEach((item, i) => errors.push(...validate(item, node.items, `${path}[${i}]`)))
  }
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    for (const key of node.required || []) if (!(key in value)) errors.push(`${path}: missing ${key}`)
    for (const [key, child] of Object.entries(node.properties || {})) if (key in value) errors.push(...validate(value[key], child, `${path}.${key}`))
  }
  return errors
}

test('fixture satisfies the published JSON Schema', () => {
  assert.deepEqual(validate(fixture, schema), [])
  assert.equal(fixture.points.length, fixture.scan.gridSize ** 2)
})

test('schema rejects a malformed model', () => {
  const broken = structuredClone(fixture)
  delete broken.scores
  broken.points[0].rank = 0
  broken.competitors[0].top3Share = 1.5
  const errors = validate(broken, schema)
  assert.ok(errors.some(e => e.includes('missing scores')))
  assert.ok(errors.some(e => e.includes('points[0].rank')))
  assert.ok(errors.some(e => e.includes('competitors[0].top3Share')))
})

test('lean model normalizes the fixture and tolerates absent optional data', () => {
  const full = normalizeLeanModel(fixture)
  assert.equal(full.points.length, 25)
  assert.equal(full.points.filter(p => p.rank === null).length, 3)
  assert.equal(full.delta.scores.arp, -0.9)
  assert.equal(full.zoneCompetitors.length, 2)

  const minimal = normalizeLeanModel({ schema: 'geogrid-viewer/v1', business: { name: 'A', lat: 1, lng: 2 },
    points: [{ lat: 1, lng: 2, rank: 3 }], delta: null })
  assert.equal(minimal.competitors.length, 0)
  assert.equal(minimal.zones.rings.length, 0)
  assert.equal(minimal.delta, null)
  assert.equal(minimal.scores.arp, null)
  // A delta may carry its score changes without the wrapper.
  assert.equal(normalizeLeanModel({ ...fixture, delta: { arp: -2 } }).delta.scores.arp, -2)
})

test('lean model rejects the wrong schema, missing business and empty grids', () => {
  assert.throws(() => normalizeLeanModel({ ...fixture, schema: 'other/v1' }), /schema/)
  assert.throws(() => normalizeLeanModel({ ...fixture, business: { name: 'x' } }), /business/)
  assert.throws(() => normalizeLeanModel({ ...fixture, points: [] }), /points/)
  assert.throws(() => normalizeLeanModel(null), /model/)
})

test('formatters print shares, ranks and signed changes', () => {
  assert.equal(formatShare(0.285), '28.5%')
  assert.equal(formatShare(null), 'n/a')
  assert.equal(formatSigned(0.08, 'share'), '+8 pts')
  assert.equal(formatSigned(-0.9, 'rank'), '-0.9')
  assert.equal(formatSigned(0, 'rank'), '0')
})

test('viewer bundle builds with the expected files', () => {
  assert.deepEqual(readdirSync(outDir).sort(), ['geogrid-viewer-worker.js', 'geogrid-viewer.css', 'geogrid-viewer.js'])
  assert.match(js, /var GeoGridViewer=/)
  assert.ok(js.length > 200000)
})

test('bundle contains no OpenStreetMap raster host, eval or Function constructor', () => {
  for (const [name, text] of [['geogrid-viewer.js', js], ['geogrid-viewer.css', css], ['geogrid-viewer-worker.js', worker]]) {
    assert.ok(!text.includes('tile.openstreetmap.org'), `${name} references tile.openstreetmap.org`)
    assert.ok(!text.includes('fonts.googleapis.com'), `${name} references a remote font host`)
    assert.ok(!text.includes('__GEOGRID_BOOTSTRAP__'), `${name} reads the bootstrap global`)
  }
  for (const [name, text] of [['geogrid-viewer.js', js], ['geogrid-viewer.css', css]]) {
    assert.ok(!/\beval\s*\(/.test(text), `${name} calls eval`)
    assert.ok(!/new\s+Function\s*\(/.test(text), `${name} constructs Function`)
    assert.ok(!/(^|[^.\w$])Function\s*\(/.test(text), `${name} calls Function`)
  }
  assert.ok(!/new\s+Function\s*\(/.test(worker), 'worker constructs Function')
  // The third party MapLibre worker keeps one dormant script loader that falls back to globalThis.eval.
  assert.equal(worker.match(/\beval\s*\(/g).length, 1)
  assert.equal(worker.match(/globalThis\.eval\(/g).length, 1)
})

test('stylesheet is confined to the viewer root', () => {
  const selectors = []
  postcss.parse(css).walkRules(rule => {
    for (let node = rule.parent; node; node = node.parent) if (node.type === 'atrule' && /keyframes$/i.test(node.name)) return
    selectors.push(...rule.selectors)
  })
  assert.ok(selectors.length > 100)
  assert.deepEqual(selectors.filter(sel => !sel.trim().startsWith('.ggv-root')).slice(0, 5), [])
  assert.ok(!/@import/.test(css), 'no remote stylesheet imports')
})

function createWindow() {
  const dom = new JSDOM('<!doctype html><html><body><div id="host"></div></body></html>', { pretendToBeVisual: true, runScripts: 'outside-only', url: 'https://app.example.test/report' })
  const w = dom.window
  const fetched = []
  const workers = []
  let bootstrapRead = false
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
  w.Worker = class { constructor(url, options) { workers.push({ url: String(url), options }) } postMessage() {} terminate() {} addEventListener() {} removeEventListener() {} }
  w.fetch = async url => { fetched.push(String(url)); throw new Error('offline test window') }
  Object.defineProperty(w, '__GEOGRID_BOOTSTRAP__', { get() { bootstrapRead = true; return {} }, configurable: true })
  new vm.Script(js).runInContext(dom.getInternalVMContext())
  return { dom, w, fetched, workers, bootstrapRead: () => bootstrapRead }
}

test('mounts the lean model in jsdom with every capability off, then destroys cleanly', async () => {
  const problems = []
  const onRejection = reason => problems.push(reason)
  process.on('unhandledRejection', onRejection)
  const { dom, w, fetched, workers, bootstrapRead } = createWindow()
  try {
    const host = w.document.querySelector('#host')
    assert.equal(typeof w.GeoGridViewer.mount, 'function')
    const viewer = w.GeoGridViewer.mount(host, fixture, { capabilities: OFF, workerUrl: 'https://app.example.test/geogrid-viewer-worker.js' })
    assert.equal(typeof viewer.destroy, 'function')
    assert.ok(host.classList.contains('ggv-root'))
    const text = host.textContent
    assert.match(text, /Example Plumbing Co/)
    assert.match(text, /emergency plumber/)
    for (const expected of ['88%', '28%', '59.8%', '7.5', '9.1']) assert.ok(text.includes(expected), `scores show ${expected}`)
    for (const expected of ['Distance rings', 'Inner ring', 'Quadrants', 'North west']) assert.ok(text.includes(expected), `zones show ${expected}`)
    assert.ok(text.includes('Harbor Pipe & Drain'), 'competitor table lists names as text')
    assert.ok(text.includes('Change since last scan') && text.includes('+8 pts'), 'delta is shown')
    assert.equal(host.querySelectorAll('.ggl-competitors tbody tr').length, 4)
    assert.equal(host.querySelectorAll('.ggl-zone-table tbody tr').length, 1 + 1)
    assert.equal(host.querySelectorAll('canvas.ranking-canvas').length, 2, 'rank pin canvases are mounted')
    assert.equal(host.querySelectorAll('[data-view="factions"], #open-strategy').length, 0)
    const options = [...host.querySelectorAll('.ggl-basemap option')].map(o => o.value)
    assert.deepEqual(options, ['ofm-fiord', 'ofm-dark', 'ofm-liberty', 'ofm-positron'])
    assert.equal(host.querySelector('.ggl-basemap').value, 'ofm-dark', 'defaults to OpenFreeMap dark')
    // MapLibre loads lazily; wait until the background settles (jsdom has no WebGL, so it ends in an error state).
    const map = host.querySelector('.ggl-map')
    for (let waited = 0; waited < 5000 && !['ready', 'error'].includes(map.dataset.basemapState); waited += 50) await new Promise(resolve => setTimeout(resolve, 50))
    assert.ok(['ready', 'error'].includes(map.dataset.basemapState), `background state ${map.dataset.basemapState}; status: ${host.querySelector('.ggl-status').textContent}; workers ${JSON.stringify(workers)}; fetched ${JSON.stringify(fetched)}; problems ${problems.map(String).join(' | ')}`)
    assert.ok(fetched.every(url => url.startsWith('https://tiles.openfreemap.org/')), `unexpected requests: ${fetched.join(', ')}`)
    assert.ok(workers.every(item => item.url === 'https://app.example.test/geogrid-viewer-worker.js'), `workers must load from the same-origin file: ${JSON.stringify(workers)}`)
    assert.equal(bootstrapRead(), false, 'the viewer must not read window.__GEOGRID_BOOTSTRAP__')
    viewer.destroy()
    viewer.destroy()
    assert.equal(host.children.length, 0)
    assert.ok(!host.classList.contains('ggv-root'))
    await new Promise(resolve => setTimeout(resolve, 50))
    assert.deepEqual(problems.map(String), [])
  } catch (error) {
    // Errors raised inside the jsdom realm are not instances of this realm's Error; surface their text.
    throw new Error(`${error?.message ?? JSON.stringify(error)}\n${error?.stack ?? ''}`)
  } finally {
    process.off('unhandledRejection', onRejection)
    dom.window.close()
  }
})

test('lean model hides the Google basemaps unless a session path is given', () => {
  const { dom, w } = createWindow()
  try {
    const host = w.document.querySelector('#host')
    const viewer = w.GeoGridViewer.mount(host, fixture, { capabilities: OFF })
    assert.ok(![...host.querySelectorAll('.ggl-basemap option')].some(o => o.value.startsWith('google')))
    viewer.destroy()
    const withGoogle = w.GeoGridViewer.mount(host, fixture, { capabilities: OFF, googleSessionPath: '/api/maps/google/session' })
    const ids = [...host.querySelectorAll('.ggl-basemap option')].map(o => o.value)
    assert.ok(ids.includes('google-roadmap') && ids.includes('ofm-dark'))
    withGoogle.destroy()
  } finally {
    dom.window.close()
  }
})

test('mount rejects unsupported models and bad elements', () => {
  const { dom, w } = createWindow()
  try {
    assert.throws(() => w.GeoGridViewer.mount(w.document.querySelector('#host'), { schema: 'nope/v9' }, {}), /unsupported model schema/)
    assert.throws(() => w.GeoGridViewer.mount('#missing', fixture, {}), /element/)
    assert.throws(() => w.GeoGridViewer.mount(w.document.querySelector('#host'), null, {}), /model/)
  } finally {
    dom.window.close()
  }
})

test('mounts a companion study with panels hidden when their capability is off, and shows them when on', async () => {
  const { dom, w } = createWindow()
  try {
    const host = w.document.querySelector('#host')
    const off = w.GeoGridViewer.mount(host, companionStudy, { capabilities: OFF, workerUrl: 'https://app.example.test/geogrid-viewer-worker.js' })
    assert.ok(host.querySelector('[data-view="visibility"]'))
    for (const selector of ['[data-view="factions"]', '[data-view="keyword-stuffing"]', '#open-strategy']) {
      const el = host.querySelector(selector)
      assert.ok(!el || el.hidden, `${selector} is hidden when its capability is off`)
    }
    assert.ok(host.querySelector('#open-study').hidden, 'file loading is hidden in the embedded viewer')
    assert.ok(!w.GeoGrid, 'the embedded viewer does not add a window.GeoGrid global')
    await new Promise(resolve => setTimeout(resolve, 100))
    off.destroy()
    assert.equal(host.children.length, 0)

    const on = w.GeoGridViewer.mount(host, companionStudy, { capabilities: { ...OFF, perPointListings: true, nameReview: true, strategyRoom: true } })
    for (const selector of ['[data-view="factions"]', '[data-view="keyword-stuffing"]', '#open-strategy']) {
      assert.ok(!host.querySelector(selector).hidden, `${selector} is shown when its capability is on`)
    }
    on.destroy()
  } catch (error) {
    throw new Error(`${error?.message ?? JSON.stringify(error)}\n${error?.stack ?? ''}`)
  } finally {
    dom.window.close()
  }
})
