import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { strategyIntelligence, strategyMatchup, rivalPressure } from '../src/strategy-engine.js'

const MILE_KM = 1.609344
function observation(primaryRank = null, rivalRank = null) {
  return { status: primaryRank === null ? 'not_returned_depth_reached' : 'found', targetRank: primaryRank,
    items: Array.from({ length: 30 }, (_, i) => {
      const rank = i + 1, id = rank === primaryRank ? 'TARGET' : rank === rivalRank ? 'RIVAL' : `cid:${rank}`
      return { id, cid: id, name: id === 'RIVAL' ? 'Same brand' : id, rank }
    }) }
}
function fixture() {
  const center = { lat: 38, lng: -121 }, spacing = .5 * MILE_KM, step = spacing / 111.195, points = []
  for (let y = -2; y <= 2; y++) for (let x = -2; x <= 2; x++) {
    if (Math.hypot(x, y) > 2) continue
    points.push({ id: `${x},${y}`, lat: Number((center.lat + y * step).toFixed(7)),
      lng: Number((center.lng + x * step / Math.cos(center.lat * Math.PI / 180)).toFixed(7)),
      observations: { q1: observation(), q2: observation() } })
  }
  return { depth: 30, targetId: 'TARGET',
    businesses: [{ id: 'TARGET', name: 'Primary', cid: 'TARGET' }, { id: 'RIVAL', name: 'Same brand', cid: 'RIVAL', address: 'Address one', shortlisted: false },
      ...Array.from({ length: 30 }, (_, i) => ({ id: `cid:${i + 1}`, name: i === 0 ? 'Same brand' : `Business ${i + 1}`, cid: `cid:${i + 1}`, address: `Address ${i + 2}` }))],
    queries: [{ id: 'q1', name: 'HVAC contractor' }, { id: 'q2', name: 'Repair' }],
    sampling: { geometry: 'radius_grid', center, spacing_km: spacing, radius_km: 1.01 * MILE_KM }, points }
}
describe('Strategy engine', () => {
  it('partitions the circle into nine nonoverlapping regions and preserves unknown origins', () => {
    const m = fixture()
    m.sampling.radius_km = 10 * MILE_KM
    const r = strategyIntelligence(m), all = r.regions.find(r => r.id === 'all'), sectors = r.regions.filter(r => r.id !== 'all')
    assert.equal(r.available, true)
    assert.equal(all.count, 1249)
    assert.equal(r.regions.find(r => r.id === 'core').count, 49)
    assert.equal(sectors.length, 9)
    assert.equal(sectors.reduce((n, r) => n + r.count, 0), all.count)
    assert.equal(new Set(sectors.flatMap(r => r.originIds)).size, all.count)
    assert.equal(all.perQuery.q1.unknown, 1236)
    assert.equal(r.queryMatrix.length, 2)
    assert.equal(r.queryMatrix[0].regions.length, 9)
    const memberOf = id => sectors.find(r => r.originIds.includes(id))?.id
    assert.equal(memberOf('missing:0,5'), 'inner-ne')
    assert.equal(memberOf('missing:5,0'), 'inner-ne')
    assert.equal(memberOf('missing:0,-5'), 'inner-se')
    assert.equal(memberOf('missing:-5,0'), 'inner-nw')
  })
  it('caps region bounds to the study radius and never shows a ten-mile sector on a small study', () => {
    const m = fixture(), r = strategyIntelligence(m)
    assert.deepEqual(r.regions.map(r => r.id), ['all', 'core'])
    assert.equal(r.regions[1].label, 'Core · 0–1 mi')
    const larger = fixture()
    larger.sampling.radius_km = 3 * MILE_KM
    const x = strategyIntelligence(larger)
    assert.equal(x.regions.length, 6)
    assert.ok(x.regions.filter(r => r.id.startsWith('inner')).every(r => r.label.endsWith('>2–3 mi')))
  })
  it('calculates exact service coverage, excludes unknowns from percentage denominators, and reports them', () => {
    const m = fixture()
    m.points[0].observations.q1 = observation(3)
    m.points[1].observations.q1 = observation(5)
    m.points[2].observations.q1 = observation(20)
    m.points[3].observations.q1.status = 'pending'
    const r = strategyIntelligence(m).regions[0].perQuery.q1
    assert.equal(r.complete, 12)
    assert.equal(r.unknown, 1)
    assert.equal(r.top3, 1)
    assert.equal(r.top10, 2)
    assert.equal(r.near, 1)
    assert.equal(r.found, 3)
    assert.equal(r.top10Pct, 2 / 12 * 100)
  })
  it('equal-weights per-query regional coverage even when query completeness differs', () => {
    const m = fixture()
    m.points[0].observations.q1 = observation(null, 1)
    for (const p of m.points) p.observations.q2.status = 'pending'
    m.points[0].observations.q2 = observation(null, 1)
    const r = strategyIntelligence(m).regions[0].rivals.find(r => r.id === 'RIVAL')
    assert.equal(r.top3Appearances, 2)
    assert.equal(r.completeDenominator, 14)
    assert.equal(r.top3CoveragePct, (1 / 13 + 1) / 2 * 100)
  })
  it('keeps actual unshortlisted profiles and separate same-name locations in rival pressure', () => {
    const m = fixture()
    for (const p of m.points) p.observations.q1 = observation(5, 2)
    const r = rivalPressure(m, 'core')
    assert.equal(r.available, true)
    assert.equal(r.nearDenominator, 13)
    const separate = r.local.filter(r => r.name === 'Same brand')
    assert.equal(separate.length, 2)
    assert.notEqual(separate[0].id, separate[1].id)
    assert.notEqual(separate[0].address, separate[1].address)
    assert.equal(r.local.find(r => r.id === 'RIVAL').nearAhead, 13)
    assert.equal(r.local.find(r => r.id === 'RIVAL').nearAheadPct, 100)
  })
  it('compares actual ranks, separates exclusive presence, and never assigns NR rank31 or ties', () => {
    const m = fixture()
    const cases = [[2, 5], [6, 1], [4, null], [null, 7], [null, null]]
    cases.forEach(([p, r], i) => { m.points[i].observations.q1 = observation(p, r) })
    m.points[5].observations.q1.status = 'pending'
    const r = strategyMatchup(m, 'q1', 'RIVAL')
    assert.equal(r.available, true)
    assert.deepEqual(r.counts, { primaryAhead: 1, rivalAhead: 1, tied: 0, primaryOnly: 1, rivalOnly: 1, neither: 8, unknown: 1 })
    assert.equal(r.leader, null)
    assert.equal(r.comparedOrigins, 12)
    assert.deepEqual(r.cells.slice(0, 5).map(c => [c.primaryRank, c.rivalRank]), cases)
    assert.equal(r.cells[5].primaryRank, null)
    assert.equal(r.cells[5].rivalRank, null)
    assert.equal(r.cells[4].state, 'neither')
    assert.equal(r, strategyMatchup(m, 'q1', 'RIVAL'))
  })
  it('keeps duplicate-rank corruption unknown in region and matchup evidence', () => {
    const m = fixture()
    m.points[0].observations.q1 = observation(5, 2)
    m.points[0].observations.q1.items[0].rank = 2
    const s = strategyIntelligence(m), h = strategyMatchup(m, 'q1', 'RIVAL')
    assert.equal(s.regions[0].perQuery.q1.unknown, 1)
    assert.equal(h.counts.unknown, 1)
    assert.equal(h.cells[0].rivalRank, null)
  })
  it('never treats an inconsistent exported primary rank as usable head-to-head evidence', () => {
    const m = fixture()
    m.points[0].observations.q1 = observation(5, 2)
    m.points[0].observations.q1.targetRank = 6
    assert.equal(strategyIntelligence(m).regions[0].perQuery.q1.unknown, 1)
    const bad = strategyMatchup(m, 'q1', 'RIVAL').cells[0]
    assert.equal(bad.state, 'unknown')
    assert.equal(bad.primaryRank, null)
    assert.equal(bad.rivalRank, null)
  })
  it('insight service gaps include exact member origins and do not fabricate demand evidence', () => {
    const m = fixture()
    for (const p of m.points.slice(0, 3)) {
      p.observations.q1 = observation(2)
      p.observations.q2 = observation(5, 1)
    }
    const r = strategyIntelligence(m), gap = r.insights.find(i => i.id.startsWith('service-gap'))
    assert.ok(gap)
    assert.equal(gap.queryId, 'q2')
    assert.equal(gap.regionId, 'core')
    assert.equal(gap.evidence.count, 3)
    assert.deepEqual(gap.originIds, m.points.slice(0, 3).map(p => p.id))
    assert.deepEqual(gap.evidence.supportingQueryIds, ['q1'])
    assert.match(gap.limitations, /do not identify the cause/)
    assert.equal(r, strategyIntelligence(m))
  })
  it('fails closed on invalid query, profile, region, or irregular geometry without mutating source', () => {
    const m = fixture(), before = JSON.stringify(m)
    assert.equal(strategyMatchup(m, 'bad', 'RIVAL').available, false)
    assert.equal(strategyMatchup(m, 'q1', 'TARGET').available, false)
    assert.equal(strategyMatchup(m, 'q1', 'missing').available, false)
    assert.equal(strategyMatchup(m, 'q1', 'RIVAL', 'bad').available, false)
    assert.equal(rivalPressure(m, 'bad').available, false)
    assert.equal(JSON.stringify(m), before)
    const irregular = fixture()
    irregular.sampling.geometry = 'rings'
    assert.equal(strategyIntelligence(irregular).available, false)
  })
})
