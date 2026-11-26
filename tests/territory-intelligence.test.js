import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { territoryIntelligence } from '../src/territory-intelligence.js'

const MILE_KM = 1.609344
function observation(rank = null, queryId = 'q1') {
  const items = Array.from({ length: 30 }, (_, i) => ({
    id: i + 1 === rank ? 'TARGET' : `cid:${queryId}-${i + 1}`,
    cid: i + 1 === rank ? 'primary' : `${queryId}-${i + 1}`,
    name: i < 2 ? 'Same brand, separate location' : `Profile ${queryId}-${i + 1}`, rank: i + 1,
  }))
  return { status: rank ? 'found' : 'not_returned_depth_reached', targetRank: rank, items }
}
function fixture() {
  const center = { lat: 38, lng: -121 }, spacing = .5 * MILE_KM, step = spacing / 111.195
  const points = []
  // A radius just over one mile safely includes axial cells after rounding.
  for (let y = -2; y <= 2; y++) for (let x = -2; x <= 2; x++) {
    if (Math.hypot(x, y) > 2) continue
    points.push({ id: `${x},${y}`, lat: Number((center.lat + y * step).toFixed(7)),
      lng: Number((center.lng + x * step / Math.cos(center.lat * Math.PI / 180)).toFixed(7)),
      observations: { q1: observation(), q2: observation(null, 'q2') } })
  }
  return { depth: 30, targetId: 'TARGET', businesses: [{ id: 'TARGET', name: 'Primary', cid: 'primary', target: true }],
    queries: [{ id: 'q1', name: 'Service one' }, { id: 'q2', name: 'Service two' }],
    sampling: { geometry: 'radius_grid', center, spacing_km: spacing, radius_km: 1.01 * MILE_KM }, points }
}
function set(model, id, rank, query = 'q1') {
  model.points.find(p => p.id === id).observations[query] = observation(rank, query)
}

describe('Territory intelligence evidence and spatial rules', () => {
  it('classifies a complete circular lattice and retains exact rank bands', () => {
    const m = fixture()
    set(m, '0,0', 1); set(m, '1,0', 10); set(m, '-1,0', 11); set(m, '0,1', 30)
    const r = territoryIntelligence(m, 'q1')
    assert.equal(r.available, true)
    assert.deepEqual(r.counts, { defend: 1, advance: 1, build: 2, outside30: 9, unknown: 0, serviceGap: 0, frontier: 2 })
    assert.equal(r.expectedOrigins, 13)
    assert.equal(r.cells.find(c => c.id === '0,1').rank, 30)
    assert.equal(r.cells.find(c => c.id === '0,-1').rank, null)
  })
  it('never treats incomplete, missing, queued or contradictory evidence as rank failure', () => {
    const m = fixture()
    m.points[0].observations.q1.items.pop()
    m.points[1].observations.q1.status = 'pending'
    m.points[2].observations.q1.targetRank = 7
    m.points[3].observations.q1.items[0].rank = 2
    delete m.points[4].observations.q1
    m.points[5].observations.q1.items[1].cid = m.points[5].observations.q1.items[0].cid
    const r = territoryIntelligence(m, 'q1')
    assert.equal(r.counts.unknown, 6)
    assert.equal(r.counts.outside30, 7)
    assert.ok(r.featuredAreas.every(a => !['outside30', 'unknown'].includes(a.band)))
  })
  it('requires known depth30 even for apparently ranked cells', () => {
    for (const depth of [undefined, null, 20]) {
      const m = fixture()
      m.depth = depth
      set(m, '0,0', 2)
      assert.equal(territoryIntelligence(m, 'q1').counts.unknown, 13)
    }
  })
  it('reconstructs missing lattice cells as unknown and does not bridge them', () => {
    const m = fixture()
    set(m, '-1,0', 5); set(m, '1,0', 6)
    m.points = m.points.filter(p => p.id !== '0,0')
    const r = territoryIntelligence(m, 'q1')
    assert.equal(r.missingOrigins, 1)
    assert.equal(r.counts.unknown, 1)
    assert.equal(r.cells.find(c => c.missing).id, 'missing:0,0')
    assert.equal(r.areas.filter(a => a.band === 'advance').length, 2)
    assert.ok(r.areas.filter(a => a.band === 'advance').every(a => a.isolated && !a.featured))
  })
  it('matches the collector at the geodesic circle boundary rather than inventing four missing edge origins', () => {
    const m = fixture()
    m.points = []
    m.sampling.radius_km = 10 * MILE_KM
    const r = territoryIntelligence(m, 'q1')
    // Verified against radius_sampling.radial_origins(38, -121, 10, .5).
    // A rounded Earth radius of 6371 falsely includes the four axial edge cells.
    assert.equal(r.expectedOrigins, 1249)
    assert.equal(r.missingOrigins, 1249)
    assert.equal(r.counts.unknown, 1249)
    assert.ok(r.cells.every(c => Math.abs(c.x) < 20 && Math.abs(c.y) < 20))
  })
  it('joins orthogonal neighbors only, keeps deterministic members and a measured representative', () => {
    const m = fixture()
    set(m, '0,0', 4); set(m, '1,0', 6); set(m, '-1,-1', 8)
    const r = territoryIntelligence(m, 'q1'), areas = r.areas.filter(a => a.band === 'advance')
    assert.deepEqual(areas.map(a => a.count), [2, 1])
    assert.deepEqual(areas[0].originIds, ['0,0', '1,0'])
    assert.equal(areas[0].medianRank, 5)
    assert.ok(areas[0].originIds.includes(areas[0].representative.id))
    assert.ok(areas[0].distanceMiles.max > .49 && areas[0].distanceMiles.max < .51)
    assert.equal(areas[0].direction, 'E of the primary business')
  })
  it('counts all local top-three identities regardless of shortlist, preserving separate brand locations', () => {
    const m = fixture()
    set(m, '0,0', 4); set(m, '1,0', 7)
    const r = territoryIntelligence(m, 'q1'), a = r.areas.find(a => a.band === 'advance')
    assert.equal(a.rivals.length, 3)
    assert.equal(a.rivals[0].name, a.rivals[1].name)
    assert.notEqual(a.rivals[0].id, a.rivals[1].id)
    assert.ok(a.rivals.every(r => r.count === 2 && r.denominator === 2 && r.share === 1))
    assert.equal(a.competition.distinctProfiles, 3)
  })
  it('requires another complete top-three query for service gaps', () => {
    const m = fixture()
    set(m, '0,0', 5); set(m, '1,0', 6); set(m, '-1,0', 7); set(m, '0,1', 12)
    set(m, '0,0', 2, 'q2'); set(m, '1,0', 3, 'q2'); set(m, '-1,0', 1, 'q2'); set(m, '0,1', 1, 'q2')
    m.points.find(p => p.id === '-1,0').observations.q2.items.pop()
    const r = territoryIntelligence(m, 'q1')
    assert.equal(r.counts.serviceGap, 2)
    assert.deepEqual(r.cells.find(c => c.id === '0,0').supportingQueries, ['q2'])
    assert.equal(r.serviceGapAreas[0].count, 2)
    assert.equal(r.serviceGapAreas[0].label, 'Service gap')
    assert.equal(r.serviceGapAreas[0].lens, 'serviceGap')
  })
  it('frontier uses only direct top-ten adjacency, not an entire connected rank11-30 patch', () => {
    const m = fixture()
    set(m, '0,0', 3); set(m, '1,0', 12); set(m, '2,0', 20); set(m, '1,1', 21)
    const r = territoryIntelligence(m, 'q1')
    assert.equal(r.counts.build, 3)
    assert.equal(r.counts.frontier, 1)
    assert.deepEqual(r.frontierAreas[0].originIds, ['1,0'])
    assert.equal(r.frontierAreas[0].adjacentCoreCount, 1)
    assert.equal(r.frontierAreas[0].adjacentTopTenCount, 1)
    assert.ok(r.frontierAreas[0].nearestCoreMiles > .49)
    assert.equal(r.frontierAreas[0].featured, false)
  })
  it('rejects irregular or duplicate-coordinate geometry instead of inventing contiguous areas', () => {
    for (const mutate of [
      m => { m.sampling.geometry = 'rings' },
      m => { m.points[0].lat += .0001 },
      m => { m.points.push({ ...m.points[0], id: 'duplicate' }) },
    ]) {
      const m = fixture()
      mutate(m)
      const r = territoryIntelligence(m, 'q1')
      assert.equal(r.available, false)
      assert.deepEqual(r.areas, [])
    }
  })
  it('caches immutable evidence, leaves source unchanged, and distinguishes queries', () => {
    const m = fixture(), before = JSON.stringify(m)
    const r = territoryIntelligence(m, 'q1')
    assert.equal(r, territoryIntelligence(m, 'q1'))
    assert.notEqual(r, territoryIntelligence(m, 'q2'))
    assert.equal(JSON.stringify(m), before)
    assert.equal(territoryIntelligence(m, 'invalid').available, false)
  })
})

describe('Territory intelligence on hex_radius lattices (including coastal water-clipped grids)', () => {
  function hexFixture({ dropEastOcean = false, omitHexMeta = false } = {}) {
    const center = { lat: 25.8043047, lng: -80.1955704 }
    const spacingKm = 0.5 * MILE_KM
    const radiusKm = 1.55 * MILE_KM
    const cosLat = Math.cos((center.lat * Math.PI) / 180)
    const points = []
    for (let q = -3; q <= 3; q++) {
      for (let r = -3; r <= 3; r++) {
        const eastKm = spacingKm * (q + r / 2)
        const northKm = spacingKm * (Math.sqrt(3) / 2) * r
        if (Math.hypot(eastKm, northKm) > radiusKm) continue
        if (dropEastOcean && eastKm > spacingKm * 0.4) continue
        const pt = {
          id: `hex_${q}_${r}`,
          lat: Number((center.lat + northKm / 111.195).toFixed(7)),
          lng: Number((center.lng + eastKm / (111.195 * cosLat)).toFixed(7)),
          observations: { q1: observation(), q2: observation(null, 'q2') },
        }
        if (!omitHexMeta) pt.hex = { unit_q: q, unit_r: r, rung_miles: 0.5 }
        points.push(pt)
      }
    }
    return {
      depth: 30,
      targetId: 'TARGET',
      businesses: [{ id: 'TARGET', name: 'Primary', cid: 'primary', target: true }],
      queries: [{ id: 'q1', name: 'car detailing' }, { id: 'q2', name: 'car wash' }],
      sampling: { geometry: 'hex_radius', center, spacing_km: spacingKm, radius_km: radiusKm, hex: { step: 1, unit_miles: 0.5 } },
      points,
    }
  }

  it('clusters 6-neighbor hex adjacencies (including diagonal axial neighbors [1,-1] and [-1,1])', () => {
    const m = hexFixture()
    // (0,0) and (1,-1) are direct hex neighbors (not orthogonal on a square grid!)
    set(m, 'hex_0_0', 1); set(m, 'hex_1_-1', 2)
    // (-1,1) touches (0,0) -> advance; (-1,0) touches (-1,1) -> advance -> connected 2-pin advance area!
    set(m, 'hex_-1_1', 5); set(m, 'hex_-1_0', 7)
    // Service gap: (-1,1) ranks #2 on q2
    set(m, 'hex_-1_1', 2, 'q2')
    // Frontier: (-2,1) is build (rank 15) touching (-1,1) and (-1,0)
    set(m, 'hex_-2_1', 15)
    // Non-frontier build: (0,2) has no neighbor in top-10
    set(m, 'hex_0_2', 22)

    const r = territoryIntelligence(m, 'q1')
    assert.equal(r.available, true)
    assert.equal(r.counts.defend, 2)
    assert.equal(r.counts.advance, 2)
    assert.equal(r.counts.serviceGap, 1)
    assert.equal(r.counts.frontier, 1)
    assert.equal(r.counts.build, 2)
    assert.equal(r.missingOrigins, 0)

    const defendAreas = r.areas.filter(a => a.band === 'defend')
    assert.equal(defendAreas.length, 1, '(0,0) and (1,-1) must form one connected hex defend cluster')
    assert.deepEqual(defendAreas[0].originIds.sort(), ['hex_0_0', 'hex_1_-1'])

    const advanceAreas = r.areas.filter(a => a.band === 'advance')
    assert.equal(advanceAreas.length, 1)
    assert.equal(advanceAreas[0].count, 2)
    assert.equal(advanceAreas[0].serviceGapCount, 1)
    assert.ok(r.featuredAreas.length >= 2)
    assert.equal(r.frontierAreas.length, 1)
    assert.deepEqual(r.frontierAreas[0].originIds, ['hex_-2_1'])
  })

  it('handles coastal water-clipped hex grids cleanly without inventing missing ocean cells', () => {
    const m = hexFixture({ dropEastOcean: true })
    set(m, 'hex_0_0', 2); set(m, 'hex_-1_0', 3)
    set(m, 'hex_-2_0', 6); set(m, 'hex_-1_1', 8)
    set(m, 'hex_-2_1', 14); set(m, 'hex_-3_1', 18)
    const r = territoryIntelligence(m, 'q1')
    assert.equal(r.available, true)
    assert.equal(r.missingOrigins, 0, 'clipped ocean pins must not become synthetic missing cells')
    assert.equal(r.counts.unknown, 0)
    assert.equal(r.expectedOrigins, m.points.length)
    assert.ok(r.featuredAreas.length >= 2)
    assert.ok(r.frontierAreas.some(a => a.originIds.includes('hex_-2_1')))
  })

  it('supports spacing-based fallback adjacency when p.hex metadata is absent', () => {
    const m = hexFixture({ dropEastOcean: true, omitHexMeta: true })
    set(m, 'hex_0_0', 4); set(m, 'hex_-1_0', 6); set(m, 'hex_-1_1', 9)
    const r = territoryIntelligence(m, 'q1')
    assert.equal(r.available, true)
    const adv = r.areas.filter(a => a.band === 'advance')
    assert.equal(adv.length, 1)
    assert.equal(adv[0].count, 3)
  })

  it('populates featured areas, frontiers, and service gaps on the bundled Cosmi Deli South Philadelphia hex study', async () => {
    const { readFileSync } = await import('node:fs')
    const { resolve } = await import('node:path')
    const { normalizeStudy } = await import('../src/study-model.js')
    const raw = JSON.parse(readFileSync(resolve(import.meta.dirname, '../src/data/cosmis-deli-philly-study.json'), 'utf8'))
    const model = normalizeStudy(raw)
    for (const q of model.queries) {
      const intel = territoryIntelligence(model, q.id)
      assert.equal(intel.available, true, `territoryIntelligence must be available for ${q.name}`)
      assert.equal(intel.expectedOrigins, 458)
      assert.equal(intel.missingOrigins, 0)
      if (q.id !== 'q2') assert.equal(intel.counts.unknown, 0)
      assert.ok(intel.featuredAreas.length >= 1, `expected featured areas for ${q.name}`)
    }
  })
})
