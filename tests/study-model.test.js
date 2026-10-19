import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { normalizeStudy, observationFor, businessMetrics, businessLeaderboard, businessPage, rankPresentation, RANK_COLORS, RANK_OPACITIES, rankFillOpacity } from '../src/study-model.js'
import { cellSpacings, cellSize, STOP_SIGN_SCALE, DIAMOND_HALF, destination, OCTAGON_POINTS, blendColor, latticeIntersections } from '../src/map-geometry.js'
import { distanceLabel, distanceText, distanceRings } from '../src/distance-units.js'
import { installWheelZoom } from '../src/wheel-zoom.js'

describe('Wheel zoom timing', () => {
  it('counts rapid input and eases by elapsed time even when drawing drops frames', () => {
    const saved = Object.fromEntries(['matchMedia', 'requestAnimationFrame', 'cancelAnimationFrame'].map(k => [k, globalThis[k]]))
    let callback, zoom = 12
    const handlers = {}
    const container = { clientHeight: 600, addEventListener(name, fn) { handlers[name] = fn } }
    const map = { getContainer: () => container, getZoom: () => zoom,
      getMinZoom: () => 3, getMaxZoom: () => 18, mouseEventToContainerPoint: () => [100, 100],
      setZoomAround: (_, next) => { zoom = next } }
    try {
      globalThis.matchMedia = () => ({ matches: false })
      globalThis.requestAnimationFrame = fn => { callback = fn; return 1 }
      globalThis.cancelAnimationFrame = () => {}
      installWheelZoom(map)
      const wheel = deltaY => handlers.wheel({ deltaY, deltaMode: 0,
        target: { closest: () => null }, preventDefault() {} })
      for (let i = 0; i < 4; i++) wheel(-100)
      callback(16)
      callback(216)
      assert.ok(zoom > 13.9 && zoom < 14, `Slow frames should not prolong easing: ${zoom}`)
      wheel(100)
      callback(616)
      callback(816)
      assert.equal(zoom, 13.5)
    } finally {
      for (const [key, value] of Object.entries(saved)) {
        if (value === undefined) delete globalThis[key]
        else globalThis[key] = value
      }
    }
  })
})

describe('Distance display units', () => {
  it('converts measured distances without rounding the grid to a different spacing', () => {
    assert.equal(distanceLabel(1.609344, 'mi'), '1 mi')
    assert.equal(distanceText('21 × 21 grid · 1 km spacing', 'mi'), '21 × 21 grid · 0.62 mi spacing')
    assert.equal(distanceText('21 × 21 grid · 1 km spacing', 'km'), '21 × 21 grid · 1 km spacing')
    assert.equal(distanceText('Exploratory sampling', 'mi'), 'Exploratory sampling')
  })
  it('uses round ring labels with the correct physical radii in each unit', () => {
    assert.deepEqual(distanceRings('mi').map(r => r.label), ['10 mi', '5 mi', '2 mi', '1 mi'])
    assert.equal(distanceRings('mi')[3].km, 1.609344)
    assert.deepEqual(distanceRings('km').map(r => r.km), [10, 5, 2, 1])
  })
})

const __dirname = path.dirname(fileURLToPath(import.meta.url))

describe('Competitive leaderboard', () => {
  const model = {
    targetId: 'TARGET', depth: 20,
    businesses: [{ id: 'TARGET', target: true }, { id: 'rival-a' }, { id: 'rival-b' }],
    points: [{ observations: {
      q1: { status: 'found', targetRank: 12, items: [{ id: 'rival-a', rank: 1 }, { id: 'rival-b', rank: 4 }] },
      q2: { status: 'found', targetRank: 1, items: [{ id: 'rival-a', rank: 7 }, { id: 'rival-b', rank: 7 }] },
    } }],
  }
  it('places the primary below better performers and changes order with the query', () => {
    assert.deepEqual(businessLeaderboard(model, 'q1').map(r => [r.business.id, r.position]),
      [['rival-a', 1], ['rival-b', 2], ['TARGET', 3]])
    assert.deepEqual(businessLeaderboard(model, 'q2').map(r => [r.business.id, r.position]),
      [['TARGET', 1], ['rival-a', 2], ['rival-b', 2]])
  })
  it('keeps missing observations out of visibility points and does not promote the primary on ties', () => {
    const empty = { ...model, points: [{ observations: { q1: { status: 'missing', items: [] } } }] }
    const rows = businessLeaderboard(empty, 'q1')
    assert.ok(rows.every(r => r.position === 1 && r.metrics.visibilityScore === 0))
    assert.equal(rows.at(-1).business.id, 'TARGET')
  })
})
const ROOT_DIR = path.resolve(__dirname, '..')

describe('Geographic marker spacing', () => {
  it('keeps missing radial corners transparent without relocating the intersection', () => {
    const points = [{ lat: 1, lng: 1 }, { lat: 0, lng: 0 }, { lat: 0, lng: 1 }]
    const cells = latticeIntersections(points, true)
    const corner = cells.find(c => c.north === 1 && c.west === 0)
    assert.deepEqual(corner.corners, [null, points[0], points[1], points[2]])
    assert.equal(corner.south, 0)
    assert.equal(corner.east, 1)
    assert.deepEqual(latticeIntersections(points), [])
    const fade = blendColor([[0, 0, 0, 0], [255, 0, 0, 255], [255, 0, 0, 255], [255, 0, 0, 255]], .1, .1)
    assert.equal(fade[0], 255)
    assert.ok(fade[3] < 60)
  })
  it('includes two-node outer edges, excludes single-node intersections, and never invents points', () => {
    const points = [{ lat: 1, lng: 0 }, { lat: 1, lng: 1 }, { lat: 0, lng: 0 }, { lat: 0, lng: 1 }]
    const cells = latticeIntersections(points, true)
    const outer = cells.find(c => c.north === 2 && c.west === 0)
    assert.deepEqual(outer.corners, [null, null, points[0], points[1]])
    assert.ok(cells.every(c => c.corners.filter(Boolean).length >= 2))
    assert.ok(cells.every(c => c.corners.every(p => p === null || points.includes(p))))
    assert.equal(latticeIntersections(points).length, 1)
  })
  it('uses eight equal sides and fills the square lattice with uniform cells', () => {
    const vertices = OCTAGON_POINTS.split(' ').map(p => p.split(',').map(Number))
    const edges = vertices.map((v, i) => Math.hypot(v[0] - vertices[(i + 1) % 8][0], v[1] - vertices[(i + 1) % 8][1]))
    assert.equal(edges.length, 8)
    assert.ok(edges.every(edge => Math.abs(edge - edges[0]) < 1e-10))
    const spacing = Math.min(...cellSpacings([[0, 0], [1, 0], [0, 1], [1, 1]]))
    assert.equal(cellSize(spacing, 5), 32)
    assert.equal(cellSize(spacing, 6), 64)
  })
  it('blends four corner colors without inventing a measured rank', () => {
    const colors = [[0, 200, 0, 255], [255, 200, 0, 255], [255, 0, 0, 255], [8, 8, 11, 150]]
    assert.deepEqual(blendColor(colors, 0, 0), colors[0])
    assert.deepEqual(blendColor(colors, 1, 0), colors[1])
    assert.deepEqual(blendColor(colors, 0, 1), colors[2])
    assert.deepEqual(blendColor(colors, 1, 1), colors[3])
    assert.deepEqual(blendColor(colors, .5, .5), [143, 113, 2, 229])
  })
  it('leaves NR gradients transparent and preserves colored edges without black halos', () => {
    const clear = [0, 0, 0, 0]
    assert.deepEqual(blendColor([clear, clear, clear, clear], .5, .5), clear)
    assert.deepEqual(blendColor([[255, 80, 0, 255], clear, clear, clear], .5, .5), [255, 80, 0, 64])
  })
  it('matches every diamond edge to each equal octagon edge at every zoom', () => {
    const vertices = OCTAGON_POINTS.split(' ').map(p => p.split(',').map(Number))
    for (const zoom of [3, 10, 14, 18]) {
      const spacing = cellSize(.005, zoom)
      const diamondEdge = Math.SQRT2 * DIAMOND_HALF * spacing
      vertices.forEach(([x, y], index) => {
        const [nextX, nextY] = vertices[(index + 1) % 8]
        const octagonEdge = Math.hypot(nextX - x, nextY - y) / 100 * STOP_SIGN_SCALE * spacing
        assert.ok(Math.abs(diamondEdge - octagonEdge) < 1e-9)
      })
    }
  })
  it('keeps octagon bounding boxes separate at all zooms, including irregular neighbors', () => {
    const points = [[0, 0], [.03, 0], [.03, .001], [.012, .025], [.4, .3], [0, 0]]
    const spacings = cellSpacings(points)
    for (const zoom of [3, 7, 10, 12, 18]) {
      for (let a = 0; a < points.length; a++) for (let b = a + 1; b < points.length; b++) {
        const distance = Math.max(Math.abs(points[a][0] - points[b][0]), Math.abs(points[a][1] - points[b][1])) * 2 ** zoom
        assert.ok((cellSize(spacings[a], zoom) + cellSize(spacings[b], zoom)) / 2 <= distance)
      }
    }
    assert.ok(cellSize(.001, 3) < 1, 'No minimum-pixel floor')
  })
  it('computes the same nearest spacing as a brute force comparison', () => {
    const points = Array.from({ length: 90 }, (_, i) => [Math.sin(i * 4.2), Math.cos(i * 1.7)])
    const nearest = cellSpacings(points)
    points.forEach((p, index) => {
      const expected = Math.min(...points.filter((_, j) => j !== index).map(q => Math.max(Math.abs(p[0] - q[0]), Math.abs(p[1] - q[1]))))
      assert.equal(nearest[index], expected)
    })
  })
  it('places ring labels at a geographic distance, independent of zoom', () => {
    const [lat, lng] = destination(0, 0, 10, 90)
    assert.ok(Math.abs(lat) < .000001)
    assert.ok(Math.abs(lng - .08993216) < .000001)
  })
})

describe('Top thirty presentation', () => {
  const point = (rank, items = [], status = 'found') => ({ observations: { q1: { targetRank: rank, items, status } } })
  const model = { targetId: 'TARGET', depth: 30 }
  it('uses cyan-green-yellow shades followed by twenty pure-red opacity levels', () => {
    assert.equal(new Set(RANK_COLORS.slice(0, 10)).size, 10)
    assert.equal(RANK_COLORS[0], '#00ffff')
    assert.equal(RANK_COLORS[3], '#00ff55')
    assert.equal(RANK_COLORS[6], '#55ff00')
    assert.equal(RANK_COLORS[9], '#ffff00')
    assert.ok(RANK_COLORS.slice(10).every(c => c === '#ff0000'))
    assert.equal(new Set(RANK_COLORS.map((c, i) => `${c}/${RANK_OPACITIES[i]}`)).size, 30)
    for (let rank = 1; rank <= 30; rank++) {
      const display = rankPresentation(model, point(rank), 'q1', 'TARGET')
      assert.equal(display.label, String(rank))
      assert.equal(display.kind, 'ranked')
      assert.equal(display.color, RANK_COLORS[rank - 1])
      assert.equal(display.opacity, RANK_OPACITIES[rank - 1])
    }
  })
  it('switches sharply at 11 and fades alpha, without darkening red or double-dimming it', () => {
    const p = point(11)
    assert.equal(rankPresentation(model, p, 'q1', 'TARGET').label, '11')
    assert.equal(observationFor(model, p, 'q1', 'TARGET').rank, 11)
    assert.equal(rankFillOpacity(1), 1)
    assert.ok(Math.abs(rankFillOpacity(10) - .75) < 1e-9)
    for (let rank = 1; rank < 10; rank++) {
      assert.ok(Math.abs(rankFillOpacity(rank) - rankFillOpacity(rank + 1) - 1 / 36) < 1e-9)
    }
    assert.equal(rankFillOpacity(1, true), .45)
    assert.ok(Math.abs(rankFillOpacity(10, true) - .3375) < 1e-9)
    assert.equal(rankFillOpacity(11), .25)
    assert.equal(rankFillOpacity(30), .02)
    for (let rank = 11; rank <= 30; rank++) {
      assert.equal(rankFillOpacity(rank, true), rankFillOpacity(rank, false))
      if (rank < 30) assert.ok(Math.abs(rankFillOpacity(rank) - rankFillOpacity(rank + 1) - (.25 - .02) / 19) < 1e-9)
    }
    assert.equal(rankFillOpacity(31), 0)
    const red11 = [255, 0, 0, Math.round(255 * rankFillOpacity(11, true))]
    const blended = blendColor(Array(4).fill(red11), .5, .5)
    assert.deepEqual(blended, [255, 0, 0, 64])
    assert.equal(rankPresentation(model, point(31), 'q1', 'TARGET').kind, 'nr')
  })
  it('requires thirty results to establish absence and preserves errors', () => {
    const items = Array.from({ length: 30 }, (_, i) => ({ rank: i + 1, id: `other${i}` }))
    assert.equal(rankPresentation(model, point(null, items), 'q1', 'TARGET').kind, 'nr')
    assert.equal(rankPresentation(model, point(null, items.slice(0, 9)), 'q1', 'TARGET').kind, 'unknown')
    assert.equal(rankPresentation(model, point(null, items.slice(0, 20)), 'q1', 'TARGET').kind, 'unknown')
    assert.equal(rankPresentation({ ...model, depth: 20 }, point(null, items.slice(0, 20), 'not_returned_depth_reached'), 'q1', 'TARGET').kind, 'unknown')
    assert.equal(rankPresentation(model, point(null, items.filter(i => i.rank !== 25)), 'q1', 'TARGET').kind, 'unknown')
    assert.equal(rankPresentation(model, point(null, items, 'error'), 'q1', 'TARGET').kind, 'unknown')
    assert.equal(rankPresentation({ ...model, depth: 5 }, point(null, [], 'not_returned_depth_reached'), 'q1', 'TARGET').kind, 'unknown')
  })
  it('keeps the central diamond clear of the four regular octagons', () => {
    const vertices = OCTAGON_POINTS.split(' ').map(p => p.split(',').map(Number))
    const diagonalEdge = Math.max(...vertices.map(([x,y]) => (x + y - 100) / 100)) * STOP_SIGN_SCALE
    const diamondEdge = 1 - DIAMOND_HALF
    assert.ok(STOP_SIGN_SCALE < 1)
    assert.ok(diagonalEdge < diamondEdge)
    assert.ok(DIAMOND_HALF > 0 && DIAMOND_HALF < .5)
  })
})

function createMinimalBattlefieldStudy(overrides = {}) {
  return {
    schema: 'geogrid-battlefield/v1',
    business: { name: 'Apex Mechanical' },
    location: 'Austin, TX',
    generated_at: '2026-10-15T20:48:23.889732+00:00',
    study: { depth: 20 },
    factions: [
      {
        faction_id: 'TARGET',
        name: 'Apex Mechanical',
        is_target: true,
        lat: 38.6441996,
        lng: -121.2677833,
        location_estimated: false,
        rating: 5.0,
        votes_count: 275,
        domain: 'apexmechanical.example',
        cid: '1000000000000000001',
        place_id: 'ChIJ_target_synthetic',
      },
      {
        faction_id: 'F01',
        name: 'Rival Plumbing Heating and Air',
        is_target: false,
        lat: 38.6200000,
        lng: -121.3100000,
        location_estimated: false,
        rating: 4.8,
        votes_count: 4890,
        domain: 'rivalhvac.example',
        cid: '13941586751234567890',
        place_id: 'ChIJ_abc123',
      },
    ],
    lanes: [
      { lane_id: 'q1', query: 'hvac contractor', keyword: 'hvac contractor' },
      { lane_id: 'q2', query: 'ac repair', keyword: 'ac repair' },
    ],
    points: [
      {
        tag: 'r0c0',
        lat: 38.6441996,
        lng: -121.2677833,
        distance_from_target_km: 0.0,
        by_lane: {
          q1: {
            status: 'found',
            target_rank: 1,
            top_items: [
              {
                faction_id: 'TARGET',
                title: 'Apex Mechanical',
                rank: 1,
                rating: 5.0,
                votes_count: 275,
              },
              {
                faction_id: 'F01',
                title: 'Rival Plumbing Heating and Air',
                rank: 2,
                rating: 4.8,
                votes_count: 4890,
              },
            ],
          },
          q2: {
            status: 'not_returned_depth_reached',
            target_rank: null,
            top_items: [
              {
                faction_id: 'F01',
                title: 'Rival Plumbing Heating and Air',
                rank: 1,
                rating: 4.8,
                votes_count: 4890,
              },
            ],
          },
        },
      },
    ],
    ...overrides,
  }
}

describe('study-model: Normalization & Exact Identity', () => {
  it('exposes non-shortlisted top-30 profiles without merging same-name physical listings', () => {
    const study = createMinimalBattlefieldStudy()
    study.points[0].by_lane.q1.top_items.push(
      { cid: '101', title: 'Same Name', rank: 21, address: 'North location' },
      { cid: '102', title: 'Same Name', rank: 30, address: 'South location' },
      { place_id: 'only-place', title: 'Place-only profile', rank: 24 })
    const model = normalizeStudy(study)
    assert.equal(model.businesses.filter(b => b.shortlisted).length, 2)
    assert.equal(model.businesses.length, 5)
    assert.equal(observationFor(model, model.points[0], 'q1', 'cid:101').rank, 21)
    assert.equal(observationFor(model, model.points[0], 'q1', 'cid:102').rank, 30)
    assert.equal(model.businesses.find(b => b.id === 'place:only-place').shortlisted, false)
    assert.equal(model.businesses.find(b => b.id === 'cid:101').lat, null)
    assert.equal(businessPage(model, 'q1').total, 2)
    const searched = businessPage(model, 'q1', { scope: 'all', search: 'South location' })
    assert.equal(searched.total, 1)
    assert.equal(searched.rows[0].business.id, 'cid:102')
    assert.equal(searched.rows[0].position, businessLeaderboard(model, 'q1').find(r => r.business.id === 'cid:102').position)
  })

  it('bounds full-field pages and reuses immutable metrics without changing query rank', () => {
    const study = createMinimalBattlefieldStudy()
    for (let n = 0; n < 60; n++) study.points[0].by_lane.q1.top_items.push(
      { cid: `profile-${n}`, title: `Profile ${n}`, rank: 4 })
    const model = normalizeStudy(study)
    const first = businessPage(model, 'q1', { scope: 'all' })
    assert.equal(first.rows.length, 25)
    assert.equal(first.total, 62)
    assert.equal(first.pages, 3)
    const last = businessPage(model, 'q1', { scope: 'all', page: 999 })
    assert.equal(last.page, 2)
    assert.equal(last.rows.length, 12)
    assert.strictEqual(businessMetrics(model, 'q1', 'TARGET'), businessMetrics(model, 'q1', 'TARGET'))
    assert.strictEqual(businessLeaderboard(model, 'q1'), businessLeaderboard(model, 'q1'))
    assert.notStrictEqual(businessLeaderboard(model, 'q1'), businessLeaderboard(model, 'q2'))
  })
  it('correctly maps target and rival exact identities in battlefield format', () => {
    const study = createMinimalBattlefieldStudy()
    const model = normalizeStudy(study)

    assert.equal(model.targetId, 'TARGET')
    assert.equal(model.businesses.length, 2)

    const target = model.businesses.find(b => b.target)
    assert.ok(target, 'Target business must exist')
    assert.equal(target.id, 'TARGET')
    assert.equal(target.name, 'Apex Mechanical')
    assert.equal(target.cid, '1000000000000000001')
    assert.equal(target.lat, 38.6441996)

    const rival = model.businesses.find(b => !b.target)
    assert.ok(rival, 'Rival business must exist')
    assert.equal(rival.id, 'F01')
    assert.equal(rival.name, 'Rival Plumbing Heating and Air')
  })

  it('nullifies base coordinates when rival location is marked as estimated', () => {
    const study = createMinimalBattlefieldStudy()
    study.factions[1].location_estimated = true
    const model = normalizeStudy(study)

    const rival = model.businesses.find(b => b.id === 'F01')
    assert.equal(rival.lat, null, 'Estimated rival latitude must be nullified for map base placement')
    assert.equal(rival.lng, null, 'Estimated rival longitude must be nullified for map base placement')
  })

  it('throws an error if no primary business is marked as target', () => {
    const study = createMinimalBattlefieldStudy()
    study.factions.forEach(f => { f.is_target = false })

    assert.throws(
      () => normalizeStudy(study),
      /This study has no identified primary business\./
    )
  })

  it('matches rival items in top_items by faction_id', () => {
    const study = createMinimalBattlefieldStudy()
    const model = normalizeStudy(study)
    const obs = observationFor(model, model.points[0], 'q1', 'F01')

    assert.equal(obs.state, 'ranked')
    assert.equal(obs.rank, 2)
    assert.equal(obs.label, 'Rank 2')
  })

  it('resolves rival item missing faction_id to faction by exact matching CID', () => {
    const study = createMinimalBattlefieldStudy()
    study.points[0].by_lane.q1.top_items[1] = {
      faction_id: null,
      cid: '13941586751234567890',
      title: 'Rival Plumbing Heating and Air',
      rank: 2,
    }
    const model = normalizeStudy(study)
    const obs = observationFor(model, model.points[0], 'q1', 'F01')
    assert.equal(obs.state, 'ranked', 'Item with matching CID should resolve to rival faction F01')
    assert.equal(obs.rank, 2)
  })

  it('resolves rival item missing faction_id to faction by exact matching place_id', () => {
    const study = createMinimalBattlefieldStudy()
    study.points[0].by_lane.q1.top_items[1] = {
      faction_id: null,
      cid: null,
      place_id: 'ChIJ_abc123',
      title: 'Rival Plumbing Heating and Air',
      rank: 2,
    }
    const model = normalizeStudy(study)
    const obs = observationFor(model, model.points[0], 'q1', 'F01')
    assert.equal(obs.state, 'ranked', 'Item with matching place_id should resolve to rival faction F01')
    assert.equal(obs.rank, 2)
  })

  it('does not resolve rival item when supplied CID or place_id mismatches', () => {
    const study = createMinimalBattlefieldStudy()
    study.points[0].by_lane.q1.top_items[1] = {
      faction_id: null,
      cid: '9999999999999999999',
      place_id: 'ChIJ_unrelated',
      title: 'Unrelated Business',
      rank: 2,
    }
    const model = normalizeStudy(study)
    const obs = observationFor(model, model.points[0], 'q1', 'F01')
    assert.notEqual(obs.state, 'ranked', 'Mismatched identity should not resolve to rival faction F01')
  })

  it('normalizes bundled sample format and handles strict target string matching', () => {
    const bundledSample = {
      target: 'Home Slice Pizza',
      keyword: 'pizza',
      location: 'Austin, TX',
      results: [
        {
          point: { tag: 'p0', lat: 30.25, lng: -97.75 },
          rank: 1,
          top_items: [
            { title: 'Home Slice Pizza' },
            { title: 'Via 313 Pizza' },
            { title: 'Bufalina' },
          ],
        },
      ],
    }

    const model = normalizeStudy(bundledSample)
    assert.equal(model.kind, 'Bundled sample')
    assert.equal(model.targetId, 'TARGET')
    assert.equal(model.limited, true)
    assert.equal(model.depth, null)

    const targetObs = observationFor(model, model.points[0], 'q1', 'TARGET')
    assert.equal(targetObs.state, 'ranked')
    assert.equal(targetObs.rank, 1)

    const rivalObs = observationFor(model, model.points[0], 'q1', 'name:Via 313 Pizza')
    assert.equal(rivalObs.state, 'ranked')
    assert.equal(rivalObs.rank, 2)
  })

  it('asserts bundled sample target title match is explicitly case-limited', () => {
    const bundledSample = {
      target: 'Home Slice Pizza',
      keyword: 'pizza',
      results: [
        {
          point: { tag: 'p0', lat: 30.25, lng: -97.75 },
          rank: 1,
          top_items: [
            { title: 'home slice pizza' },
          ],
        },
      ],
    }
    const model = normalizeStudy(bundledSample)
    const item = model.points[0].observations.q1.items[0]
    // In bundled samples, identity is explicitly limited to exact title match
    assert.equal(item.id, 'name:home slice pizza', 'Sample identity is explicitly limited; case mismatch does not match target')
  })
})

describe('study-model: Incomplete, Empty, Error vs Evidenced Absence', () => {
  it('labels queued searches as pending rather than absence or completed evidence', () => {
    const study = createMinimalBattlefieldStudy()
    study.evidence = { pending_tasks: 3, observed_from: '2026-10-18T20:00:00Z' }
    study.points[0].by_lane.q1 = { status: 'pending', top_items: [], target_rank: null }
    const model = normalizeStudy(study)
    assert.equal(model.kind, 'Collecting · 3 searches queued')
    assert.equal(observationFor(model, model.points[0], 'q1', model.targetId).state, 'unknown')
    assert.equal(rankPresentation(model, model.points[0], 'q1', model.targetId).description, 'Search queued · no result yet')
    assert.equal(rankPresentation(model, model.points[0], 'q1', model.targetId).kind, 'unknown')
  })
  it('does not infer full depth from a high rank when intervening ranks are missing', () => {
    const study = createMinimalBattlefieldStudy()
    study.study.depth = 20
    study.points[0].by_lane.q1.top_items = [{ title: 'Other business', cid: 'other', rank: 20 }]
    const model = normalizeStudy(study)
    const rival = model.businesses.find(b => !b.target)
    assert.equal(observationFor(model, model.points[0], 'q1', rival.id).state, 'unknown')
  })
  it('returns state "unknown" with label "No usable result" for missing, error, or empty_results', () => {
    const study = createMinimalBattlefieldStudy()
    const statuses = ['missing', 'error', 'empty_results']

    for (const status of statuses) {
      study.points[0].by_lane.q1.status = status
      const model = normalizeStudy(study)
      const obs = observationFor(model, model.points[0], 'q1', 'TARGET')
      assert.equal(obs.state, 'unknown')
      assert.equal(obs.rank, null)
      assert.equal(obs.label, 'No usable result')
    }
  })

  it('marks Target as "absent" when status is not_returned_depth_reached and depth is known', () => {
    const study = createMinimalBattlefieldStudy()
    study.study.depth = 20
    study.points[0].by_lane.q1.status = 'not_returned_depth_reached'
    study.points[0].by_lane.q1.target_rank = null

    const model = normalizeStudy(study)
    const obs = observationFor(model, model.points[0], 'q1', 'TARGET')
    assert.equal(obs.state, 'absent')
    assert.equal(obs.rank, null)
    assert.equal(obs.label, 'Not in returned top 20')
  })

  it('marks Rival as "absent" when target is found and items reach full requested depth', () => {
    const study = createMinimalBattlefieldStudy()
    study.study.depth = 20
    const items = Array.from({ length: 20 }, (_, i) => ({
      faction_id: i === 0 ? 'TARGET' : `OTH_${i}`,
      title: `Competitor ${i}`,
      rank: i + 1,
    }))
    study.points[0].by_lane.q1.top_items = items

    const model = normalizeStudy(study)
    const obs = observationFor(model, model.points[0], 'q1', 'F01')
    assert.equal(obs.state, 'absent')
    assert.equal(obs.rank, null)
    assert.equal(obs.label, 'Not in returned top 20')
  })

  it('marks Rival as "unknown" (Incomplete results) when items array does not reach requested depth', () => {
    const study = createMinimalBattlefieldStudy()
    study.study.depth = 20
    study.points[0].by_lane.q1.status = 'found'
    const items = Array.from({ length: 10 }, (_, i) => ({
      faction_id: i === 0 ? 'TARGET' : `OTH_${i}`,
      title: `Competitor ${i}`,
      rank: i + 1,
    }))
    study.points[0].by_lane.q1.top_items = items

    const model = normalizeStudy(study)
    const obs = observationFor(model, model.points[0], 'q1', 'F01')
    assert.equal(obs.state, 'unknown')
    assert.equal(obs.rank, null)
    assert.equal(obs.label, 'Incomplete results')
  })

  it('marks Rival as "unknown" when target status is full-depth but items array is truncated', () => {
    const study = createMinimalBattlefieldStudy()
    study.study.depth = 20
    study.points[0].by_lane.q1.status = 'not_returned_depth_reached'
    study.points[0].by_lane.q1.target_rank = null
    // Truncated items array (only 2 items returned)
    study.points[0].by_lane.q1.top_items = [
      { faction_id: 'OTH_1', title: 'Other 1', rank: 1 },
      { faction_id: 'OTH_2', title: 'Other 2', rank: 2 },
    ]

    const model = normalizeStudy(study)
    const obs = observationFor(model, model.points[0], 'q1', 'F01')
    // Corrected behavior: rival must remain unknown when organic items do not reach requested depth
    assert.equal(obs.state, 'unknown')
    assert.equal(obs.label, 'Incomplete results')
  })

  it('in bundled sample (depth=null), unranked business always returns state "unknown"', () => {
    const bundledSample = {
      target: 'Home Slice Pizza',
      keyword: 'pizza',
      results: [
        {
          point: { tag: 'p0', lat: 30.25, lng: -97.75 },
          rank: null,
          top_items: [{ title: 'Via 313 Pizza' }],
        },
      ],
    }
    const model = normalizeStudy(bundledSample)
    const obs = observationFor(model, model.points[0], 'q1', 'TARGET')
    assert.equal(obs.state, 'unknown')
    assert.equal(obs.label, 'Not in saved sample')
  })
})

describe('study-model: Rank Zero & Non-Integer String Handling', () => {
  it('treats rank 0 as invalid / unranked null', () => {
    const study = createMinimalBattlefieldStudy()
    study.points[0].by_lane.q1.target_rank = 0
    study.points[0].by_lane.q1.top_items = [
      { faction_id: 'TARGET', title: 'Apex Mechanical', rank: 0 },
      { faction_id: 'F01', title: 'Rival Heating', rank: 1 },
    ]

    const model = normalizeStudy(study)
    const targetObs = observationFor(model, model.points[0], 'q1', 'TARGET')
    assert.equal(targetObs.rank, null)

    const items = model.points[0].observations.q1.items
    assert.equal(items.length, 1)
    assert.equal(items[0].id, 'F01')
    assert.equal(items[0].rank, 1)
  })

  it('rejects string ranks ("1") and non-integer ranks (1.5) as null', () => {
    const study = createMinimalBattlefieldStudy()
    study.points[0].by_lane.q1.target_rank = '1'
    study.points[0].by_lane.q1.top_items = [
      { faction_id: 'TARGET', title: 'Apex Mechanical', rank: '1' },
      { faction_id: 'F01', title: 'Rival Heating', rank: 1.5 },
    ]

    const model = normalizeStudy(study)
    assert.equal(model.points[0].observations.q1.targetRank, null)
    assert.equal(model.points[0].observations.q1.items.length, 0)
  })

  it('falls back to integer rank_group when rank is null or undefined', () => {
    const study = createMinimalBattlefieldStudy()
    study.points[0].by_lane.q1.top_items = [
      { faction_id: 'F01', title: 'Rival Heating', rank: null, rank_group: 3 },
    ]

    const model = normalizeStudy(study)
    const item = model.points[0].observations.q1.items[0]
    assert.ok(item, 'Item with valid rank_group should be included')
    assert.equal(item.rank, 3)
  })
})

describe('study-model: Malicious Names & Identity Preservation', () => {
  it('preserves raw names verbatim in study-model without corrupting strings', () => {
    const study = createMinimalBattlefieldStudy()
    const xssPayload = '<script>alert("xss")</script>'
    study.factions[1].name = xssPayload
    study.points[0].by_lane.q1.top_items[1].title = xssPayload

    const model = normalizeStudy(study)
    assert.equal(model.businesses[1].name, xssPayload)
    assert.equal(model.points[0].observations.q1.items[1].name, xssPayload)
  })
})

describe('study-model: Coordinate Validation & Input Boundaries', () => {
  it('throws an error for non-finite latitude and longitude', () => {
    const testCases = [
      { lat: NaN, lng: -121.26 },
      { lat: Infinity, lng: -121.26 },
      { lat: 38.64, lng: -Infinity },
      { lat: '38.6441996', lng: -121.2677833 },
      { lat: null, lng: -121.26 },
    ]

    for (const coords of testCases) {
      const study = createMinimalBattlefieldStudy()
      study.points[0].lat = coords.lat
      study.points[0].lng = coords.lng

      assert.throws(
        () => normalizeStudy(study),
        /The study contains invalid map coordinates\./
      )
    }
  })

  it('throws an error for out-of-bounds geographic coordinates', () => {
    const outOfBounds = [
      { lat: 90.0001, lng: -121.26 },
      { lat: -90.0001, lng: -121.26 },
      { lat: 38.64, lng: 180.0001 },
      { lat: 38.64, lng: -180.0001 },
    ]

    for (const coords of outOfBounds) {
      const study = createMinimalBattlefieldStudy()
      study.points[0].lat = coords.lat
      study.points[0].lng = coords.lng

      assert.throws(
        () => normalizeStudy(study),
        /The study contains invalid map coordinates\./
      )
    }
  })

  it('throws an error when location identifiers (tags) are not unique', () => {
    const study = createMinimalBattlefieldStudy()
    study.points.push({
      tag: 'r0c0',
      lat: 38.6500000,
      lng: -121.2700000,
      distance_from_target_km: 1.0,
      by_lane: { q1: { status: 'found', target_rank: 2, top_items: [] } },
    })

    assert.throws(
      () => normalizeStudy(study),
      /Location identifiers must be unique\./
    )
  })

  it('throws an error when location count exceeds 15,000 limit', () => {
    const study = createMinimalBattlefieldStudy()
    const dummyPoint = {
      tag: 'p',
      lat: 38.64,
      lng: -121.26,
      distance_from_target_km: 0,
      by_lane: {},
    }
    const largePoints = []
    for (let i = 0; i <= 15000; i++) {
      largePoints.push({ ...dummyPoint, tag: `p${i}` })
    }
    study.points = largePoints

    assert.throws(
      () => normalizeStudy(study),
      /This viewer supports up to 15,000 locations\./
    )
  })

  it('omits invalid business coordinates by setting lat and lng to null', () => {
    const study = createMinimalBattlefieldStudy()
    study.factions[1].lat = 999.0
    study.factions[1].lng = -999.0

    const model = normalizeStudy(study)
    assert.equal(model.businesses[1].lat, null, 'Invalid latitude must be omitted as null')
    assert.equal(model.businesses[1].lng, null, 'Invalid longitude must be omitted as null')
  })
})

describe('study-model: Single-Query vs Cross-Query Metrics', () => {
  it('calculates single-query businessMetrics correctly with survivorship-biased average', () => {
    const study = createMinimalBattlefieldStudy()
    study.points = [
      {
        tag: 'p1', lat: 38.61, lng: -121.21, distance_from_target_km: 1,
        by_lane: { q1: { status: 'found', target_rank: 1, top_items: [{ faction_id: 'TARGET', rank: 1 }] } },
      },
      {
        tag: 'p2', lat: 38.62, lng: -121.22, distance_from_target_km: 2,
        by_lane: { q1: { status: 'found', target_rank: 3, top_items: [{ faction_id: 'TARGET', rank: 3 }] } },
      },
      {
        tag: 'p3', lat: 38.63, lng: -121.23, distance_from_target_km: 3,
        by_lane: { q1: { status: 'found', target_rank: 5, top_items: [{ faction_id: 'TARGET', rank: 5 }] } },
      },
      {
        tag: 'p4', lat: 38.64, lng: -121.24, distance_from_target_km: 4,
        by_lane: { q1: { status: 'not_returned_depth_reached', target_rank: null, top_items: [] } },
      },
    ]

    const model = normalizeStudy(study)
    const metrics = businessMetrics(model, 'q1', 'TARGET')

    assert.equal(metrics.top3, 2, '2 points in Top 3 (p1 rank 1, p2 rank 3)')
    assert.equal(metrics.top3Pct, 50.0, '2 out of 4 points = 50% Top 3 coverage')
    assert.equal(metrics.found, 3, '3 points found')
    assert.equal(metrics.near, 1, '1 point near miss (p3 rank 5 in 4..10)')
    assert.equal(metrics.unknown, 0, '0 unknown (p4 is evidenced absent)')
    assert.equal(metrics.average, 3.0, 'Average when found must exclude unranked point p4')
  })

  it('returns null average when a business is never found in the query lane', () => {
    const study = createMinimalBattlefieldStudy()
    study.points[0].by_lane.q1.status = 'not_returned_depth_reached'
    study.points[0].by_lane.q1.target_rank = null
    study.points[0].by_lane.q1.top_items = []

    const model = normalizeStudy(study)
    const metrics = businessMetrics(model, 'q1', 'TARGET')

    assert.equal(metrics.found, 0)
    assert.equal(metrics.top3, 0)
    assert.equal(metrics.average, null)
  })

  it('evaluates cross-query slot coverage across multiple search themes', () => {
    const study = createMinimalBattlefieldStudy()
    const model = normalizeStudy(study)

    const q1Metrics = businessMetrics(model, 'q1', 'TARGET')
    const q2Metrics = businessMetrics(model, 'q2', 'TARGET')

    assert.equal(q1Metrics.top3, 1)
    assert.equal(q2Metrics.top3, 0)

    const totalSlots = model.points.length * model.queries.length
    const totalTop3Slots = model.queries.reduce((sum, q) => {
      return sum + businessMetrics(model, q.id, 'TARGET').top3
    }, 0)
    const crossQuerySlotCoveragePct = (totalTop3Slots / totalSlots) * 100

    assert.equal(totalSlots, 2)
    assert.equal(totalTop3Slots, 1)
    assert.equal(crossQuerySlotCoveragePct, 50.0)
  })
})

describe('study-model: Real Sample Integration', () => {
  it('successfully loads and normalizes the bundled home-slice-17x17.json sample', () => {
    const samplePath = path.join(ROOT_DIR, 'src/data/home-slice-17x17.json')
    assert.ok(fs.existsSync(samplePath), 'Bundled home-slice-17x17.json must exist')

    const raw = JSON.parse(fs.readFileSync(samplePath, 'utf-8'))
    const model = normalizeStudy(raw)

    assert.equal(model.kind, 'Bundled sample')
    assert.equal(model.name, 'Home Slice Pizza')
    assert.equal(model.targetId, 'TARGET')
    assert.equal(model.points.length, 289, '17x17 grid should have 289 points')
    assert.equal(model.queries.length, 1)
    assert.equal(model.queries[0].id, 'q1')

    const m = businessMetrics(model, 'q1', 'TARGET')
    assert.ok(m.found > 0, 'Target should be found at multiple locations')
    assert.ok(m.top3 > 0, 'Target should have top 3 coverage')
  })

  it('normalizes a multi-query radial battlefield model with shortlist and discovered profiles', () => {
    const raw = createMinimalBattlefieldStudy({
      lanes: [
        { lane_id: 'q1', query: 'hvac contractor', keyword: 'hvac contractor' },
        { lane_id: 'q2', query: 'ac repair', keyword: 'ac repair' },
        { lane_id: 'q3', query: 'furnace repair', keyword: 'furnace repair' },
      ],
    })
    raw.points[0].by_lane.q3 = {
      status: 'found',
      target_rank: 2,
      top_items: [
        { cid: '999000333', title: 'Discovered Rival', rank: 1 },
        { faction_id: 'TARGET', title: 'Apex Mechanical', rank: 2 },
      ],
    }
    const model = normalizeStudy(raw)

    assert.equal(model.kind, 'Saved study')
    assert.equal(model.name, 'Apex Mechanical')
    assert.equal(model.targetId, 'TARGET')
    assert.equal(model.queries.length, 3, 'Study has 3 search queries')
    assert.equal(model.businesses.filter(b => b.shortlisted).length, 2)
    assert.equal(model.businesses.length, 3, 'Additional observed profiles remain available')
  })
})
