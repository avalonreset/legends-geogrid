import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { normalizeStudy, pointListing, competitorStats, businessMetrics } from '../src/study-model.js'
import { createValidator } from './helpers/json-schema.js'
import { buildViewer, createWindow } from './helpers/viewer-window.js'

const root = resolve(import.meta.dirname, '..')
const readJson = rel => JSON.parse(readFileSync(join(root, rel), 'utf8'))
const fixture = readJson('examples/viewer-companion-depth100-fixture.json')
const schema = readJson('docs/geogrid-companion-v1.schema.json')
const check = createValidator(schema)
const ON = { perPointListings: true, profiles: true, nameReview: false, campaignResearch: false, strategyRoom: false }
const OFF = { perPointListings: false, profiles: false, nameReview: false, campaignResearch: false, strategyRoom: false }
const TARGET = 'biz-0'

let bundle
before(() => { bundle = buildViewer() })
after(() => bundle?.cleanup())

// Independent tallies straight from the raw fixture, used to check the viewer's numbers.
const lane = p => p.by_lane.q1
function tally() {
  const rows = new Map()
  for (const p of fixture.points) for (const it of lane(p).top_items) {
    if (it.faction_id === TARGET) continue
    const row = rows.get(it.faction_id) || { n: 0, sum: 0 }
    row.n++; row.sum += it.rank
    rows.set(it.faction_id, row)
  }
  return rows
}

test('depth-100 fixture satisfies the published schema and really is deep', () => {
  assert.deepEqual(check(fixture), [])
  assert.equal(fixture.points.length, 49)
  assert.equal(fixture.study.depth, 100)
  assert.ok(fixture.points.filter(p => lane(p).top_items.length === 100).length >= 48)
  assert.ok(fixture.points.some(p => lane(p).target_rank > 20), 'a rank beyond 20 exists')
  assert.ok(fixture.points.some(p => lane(p).target_rank === null))
  assert.ok(!JSON.stringify(fixture).match(/"(cid|place_id)"/), 'no provider identifiers in the fixture')
})

test('schema rejects broken full-study models', () => {
  const broken = structuredClone(fixture)
  delete broken.lanes
  broken.points[0].by_lane.q1.top_items[0].rank = 0
  delete broken.points[1].by_lane.q1.top_items[0].faction_id
  broken.study.score_window = 0
  broken.lanes = [{ lane_id: 'q1', query: 'x', scores: { found_share: 1.5 } }]
  broken.points[2].by_lane.q1.target_rank = 0
  broken.schema = 'other/v1'
  const errors = check(broken)
  for (const part of ['points[0].by_lane.q1.top_items[0].rank', 'missing faction_id', 'study.score_window', 'found_share', 'target_rank', '$.schema']) {
    assert.ok(errors.some(e => e.includes(part)), `expected an error about ${part}: ${errors.join(' | ')}`)
  }
  assert.deepEqual(check({ ...fixture, schema: 'geogrid-battlefield/v1' }), [])
})

test('keeps opaque competitor keys, names, ratings and categories', () => {
  const model = normalizeStudy(fixture)
  const keys = new Set(fixture.points.flatMap(p => lane(p).top_items.map(i => i.faction_id)))
  assert.equal(model.businesses.length, keys.size)
  const rival = model.businesses.find(b => b.id !== TARGET)
  assert.match(rival.id, /^k-[0-9a-f]{8}$/)
  const profile = fixture.profiles[rival.id]
  assert.equal(rival.name, profile.title)
  assert.equal(rival.rating, profile.rating)
  assert.equal(rival.category, profile.category)
  assert.equal(rival.reviews, profile.votes_count)
  assert.equal(model.targetId, TARGET)
  assert.equal(model.scoreWindow, 20)
})

test('keys are never assumed to be provider ids: an unknown key without a profile still shows as a business', () => {
  const input = structuredClone(fixture)
  input.points[0].by_lane.q1.top_items.push({ faction_id: 'any string 42 / x', rank: 101, title: 'Inline Name', category: 'Plumber' })
  const model = normalizeStudy(input)
  const found = model.businesses.find(b => b.id === 'any string 42 / x')
  assert.equal(found.name, 'Inline Name')
  assert.equal(found.category, 'Plumber')
  input.points[1].by_lane.q1.top_items.push({ faction_id: 'bare-key', rank: 101 })
  assert.equal(normalizeStudy(input).businesses.find(b => b.id === 'bare-key').name, 'Unnamed profile')
})

test('listing for a point: top 20, the rest on request, and the true rank beyond 20', () => {
  const model = normalizeStudy(fixture)
  const deep = pointListing(model, 'p_00_03', 'q1')
  assert.equal(deep.captured, 100)
  assert.equal(deep.top.length, 20)
  assert.equal(deep.extra.length, 80)
  assert.equal(deep.target.rank, 37)
  assert.equal(deep.targetListed, true)
  assert.equal(deep.extra[0].rank, 21)
  const shallow = pointListing(model, 'p_06_06', 'q1')
  assert.equal(shallow.captured, 20)
  assert.equal(shallow.extra.length, 0)
  assert.equal(shallow.target.rank, 14)
  const miss = pointListing(model, 'p_00_00', 'q1')
  assert.equal(miss.target.rank, null)
  assert.match(miss.target.label, /top 100/)
  assert.equal(pointListing(model, 'nope', 'q1'), null)
})

test('competitor stats: appearances, average rank and share of points, sorted by appearances', () => {
  const model = normalizeStudy(fixture)
  const stats = competitorStats(model, 'q1')
  const expected = tally()
  assert.equal(stats.measured, 49)
  assert.equal(stats.rows.length, expected.size)
  for (let i = 1; i < stats.rows.length; i++) assert.ok(stats.rows[i - 1].appearances >= stats.rows[i].appearances, 'sorted by appearances')
  for (const row of stats.rows.slice(0, 40)) {
    const e = expected.get(row.business.id)
    assert.equal(row.appearances, e.n)
    assert.ok(Math.abs(row.averageRank - e.sum / e.n) < 1e-9)
    assert.ok(Math.abs(row.share - e.n / 49) < 1e-9)
  }
  assert.ok(stats.rows.some(r => r.appearances === 49), 'someone appears at every point')
  assert.equal(stats.target.appearances, fixture.points.filter(p => lane(p).target_rank).length)
})

test('scores stay anchored to the top 20 and never move with deeper ranks', () => {
  const ranks = fixture.points.map(p => lane(p).target_rank)
  const inWindow = ranks.filter(r => r && r <= 20)
  assert.ok(ranks.filter(r => r && r > 20).length >= 3)

  // Precomputed lane scores win for the primary business.
  const given = normalizeStudy(fixture)
  const m = businessMetrics(given, 'q1', TARGET)
  assert.equal(m.found, Math.round(fixture.lanes[0].scores.found_share * 49))
  assert.equal(m.average, fixture.lanes[0].scores.avg_rank)
  assert.ok(Math.abs(m.top3Pct - fixture.lanes[0].scores.top3_share * 100) < 1e-9)

  // Without them the viewer counts only ranks inside the window.
  const noScores = structuredClone(fixture)
  delete noScores.lanes[0].scores
  const derived = businessMetrics(normalizeStudy(noScores), 'q1', TARGET)
  assert.equal(derived.found, inWindow.length)
  assert.ok(Math.abs(derived.average - inWindow.reduce((a, b) => a + b, 0) / inWindow.length) < 1e-9)

  // Rivals follow the same window: a rank of 21 or deeper is not a found point.
  const rival = competitorStats(normalizeStudy(fixture), 'q1').rows[0].business.id
  const inside = fixture.points.filter(p => lane(p).top_items.some(i => i.faction_id === rival && i.rank <= 20)).length
  assert.equal(businessMetrics(normalizeStudy(noScores), 'q1', rival).found, inside)

  // Legacy studies with no window keep the old behavior (every captured rank counts).
  const legacy = structuredClone(noScores)
  delete legacy.study.score_window
  assert.equal(businessMetrics(normalizeStudy(legacy), 'q1', TARGET).found, ranks.filter(Boolean).length)
})

const text = el => el.textContent.replace(/\s+/g, ' ').trim()
const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', { bubbles: true, cancelable: true }))

test('mounts the depth-100 study: competitor panel, per-point expander and rank beyond 20', async () => {
  const { dom, w } = createWindow(bundle.js)
  try {
    const host = w.document.querySelector('#host')
    const viewer = w.GeoGridViewer.mount(host, fixture, { capabilities: ON, workerUrl: 'https://app.example.test/geogrid-viewer-worker.js' })
    assert.equal(typeof viewer.selectPoint, 'function')
    const tab = name => host.querySelector(`[data-tab="${name}"]`)
    assert.ok(!tab('point').hidden && !tab('competitors').hidden)

    // Competitor panel across the grid.
    click(w, tab('competitors'))
    const expected = tally()
    const panel = host.querySelector('.competitor-list')
    assert.equal(panel.querySelectorAll('.rival-row:not(.primary)').length, 25, 'first page of rivals')
    assert.match(text(host.querySelector('#side-content .side-intro')), new RegExp(`${expected.size} other businesses appear`))
    const first = panel.querySelector('.rival-row:not(.primary)')
    const [topKey, top] = [...expected].sort((a, b) => b[1].n - a[1].n || a[1].sum / a[1].n - b[1].sum / b[1].n)[0]
    assert.equal(first.dataset.business, topKey)
    assert.equal(first.dataset.appearances, String(top.n))
    assert.ok(text(first).includes(`${top.n}/49`))
    assert.ok(text(first).includes(`avg rank ${(top.sum / top.n).toFixed(1)}`))
    assert.ok(text(first).includes(`${Math.round(top.n / 49 * 100)}% of points`))
    const all = host.querySelector('[data-rivals-all]')
    assert.equal(text(all), `Show all ${expected.size}`)
    click(w, all)
    assert.equal(host.querySelectorAll('.competitor-list .rival-row:not(.primary)').length, expected.size)
    assert.equal(text(host.querySelector('[data-rivals-all]')), 'Show top 25')

    // Clicking a competitor highlights its points on the map.
    const row = host.querySelectorAll('.competitor-list .rival-row:not(.primary)')[1]
    const name = fixture.profiles[row.dataset.business].title
    click(w, row)
    assert.equal(host.querySelector('.competitor-list .rival-row.selected').dataset.business, row.dataset.business)
    assert.equal(text(host.querySelector('#map-business')), name)

    // One location: top 20 by default, the target pinned at its real rank, "show all N".
    viewer.selectPoint('p_00_03')
    assert.equal(tab('point').getAttribute('aria-pressed'), 'true')
    const list = host.querySelector('.listing-list')
    assert.equal(list.dataset.listingCount, '20')
    assert.equal(list.querySelectorAll('.listing-row[data-listing-rank]').length, 21, '20 listings plus the pinned primary business')
    assert.equal(host.querySelector('[data-target-rank]').textContent, '37')
    assert.match(text(host.querySelector('[data-target-line]')), /ranks 37 here \(beyond the top 20\)/)
    const pinned = list.querySelector('.listing-row.primary')
    assert.equal(pinned.dataset.listingRank, '37')
    const showAll = host.querySelector('[data-listing-all]')
    assert.equal(text(showAll), 'Show all 100')
    assert.match(text(host.querySelector('#side-content .side-intro')), /100 listings captured, top 20 shown/)
    click(w, showAll)
    assert.equal(host.querySelector('.listing-list').dataset.listingCount, '100')
    assert.equal(host.querySelectorAll('.listing-list .listing-row').length, 100)
    assert.equal(text(host.querySelector('[data-listing-all]')), 'Show top 20')
    assert.equal(host.querySelector('.listing-list .listing-row.primary').dataset.listingRank, '37')
    click(w, host.querySelector('[data-listing-all]'))
    assert.equal(host.querySelector('.listing-list').dataset.listingCount, '20')

    // A shallow capture has no expander; a miss says so plainly.
    viewer.selectPoint('p_06_06')
    assert.equal(host.querySelectorAll('.listing-list .listing-row').length, 20)
    assert.equal(host.querySelector('[data-listing-all]'), null)
    assert.match(text(host.querySelector('[data-target-line]')), /ranks 14 here\./)
    viewer.selectPoint('p_00_00')
    assert.match(text(host.querySelector('[data-target-line]')), /Not in returned top 100/)
    assert.throws(() => viewer.selectPoint('missing'), /Unknown location/)

    // The expander resets when another location is picked.
    viewer.selectPoint('p_00_03'); click(w, host.querySelector('[data-listing-all]'))
    viewer.selectPoint('p_00_04')
    assert.ok(host.querySelector('.listing-list').dataset.listingCount === '20')

    // Text only: rival names are rendered as text, and no vendor name appears in the viewer.
    assert.ok(!/dataforseo/i.test(host.textContent))
    viewer.destroy()
    assert.equal(host.children.length, 0)
  } catch (error) {
    throw new Error(`${error?.message ?? JSON.stringify(error)}\n${error?.stack ?? ''}`)
  } finally {
    dom.window.close()
  }
})

test('the ranking panels stay hidden when perPointListings is off', () => {
  const { dom, w } = createWindow(bundle.js)
  try {
    const host = w.document.querySelector('#host')
    const viewer = w.GeoGridViewer.mount(host, fixture, { capabilities: OFF })
    for (const name of ['point', 'competitors']) assert.ok(host.querySelector(`[data-tab="${name}"]`).hidden, `${name} tab is hidden`)
    viewer.selectPoint('p_00_03')
    assert.equal(host.querySelector('.listing-list'), null)
    assert.equal(host.querySelector('.competitor-list'), null)
    viewer.destroy()
  } finally {
    dom.window.close()
  }
})

test('names and categories from the model are escaped, never parsed as markup', () => {
  const input = structuredClone(fixture)
  const [key] = Object.keys(input.profiles)
  input.profiles[key].title = '<img src=x onerror="window.__pwned=1">Evil & Sons'
  input.profiles[key].category = '<script>window.__pwned=2</script>'
  const { dom, w } = createWindow(bundle.js)
  try {
    const host = w.document.querySelector('#host')
    const viewer = w.GeoGridViewer.mount(host, input, { capabilities: ON })
    viewer.selectPoint('p_03_03')
    const view = tag => { const el = host.querySelector('[data-tab="' + tag + '"]'); click(w, el) }
    view('point'); click(w, host.querySelector('[data-listing-all]'))
    view('competitors'); click(w, host.querySelector('[data-rivals-all]'))
    assert.equal(host.querySelectorAll('#side-content img, #side-content script').length, 0)
    assert.equal(w.__pwned, undefined)
    assert.ok(host.textContent.includes('<img src=x onerror="window.__pwned=1">Evil & Sons'))
    viewer.destroy()
  } finally {
    dom.window.close()
  }
})

test('new source and docs contain no em-dashes and name no data vendor in user-facing text', () => {
  for (const rel of ['src/point-listings.js', 'docs/geogrid-companion-v1.schema.json', 'scripts/make_viewer_depth_fixture.py']) {
    const body = readFileSync(join(root, rel), 'utf8')
    assert.ok(!body.includes('\u2014'), `${rel} has an em-dash`)
    assert.ok(!/dataforseo/i.test(body), `${rel} names a data vendor`)
  }
})
