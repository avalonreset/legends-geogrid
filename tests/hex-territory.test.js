import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import {
  hexTerritoryOutlines, prepareHexTerritory, hexTerritoryFromPrep, headToHeadReach, computeFocusOverlay,
  computeElevationStack, computeLeaderRelief,
  flattenTerritoryRing, pointInRings, mercatorZoom0, territoryOutlines, TERRITORY_MIN_CLAIM,
} from '../src/map-geometry.js'
import { normalizeStudy, observationFor } from '../src/study-model.js'
import { winnerAt } from '../src/leader-colors.js'
import { localLeaders } from '../src/local-leaders.js'

const ANCHOR_LAT = 30.2294096
const ANCHOR_LNG = -97.7839239
const KM_PER_MILE = 1.609344
const projectZoom0 = mercatorZoom0

// Axial hex lattice around the anchor at spacingMiles within radiusMiles.
function makeHexGrid(spacingMiles, radiusMiles, { prefix = 'h', lattice = true } = {}) {
  const pts = []
  const maxStep = Math.ceil(radiusMiles / spacingMiles) + 2
  const spacingKm = spacingMiles * KM_PER_MILE
  const radiusKm = radiusMiles * KM_PER_MILE
  const cosLat = Math.cos((ANCHOR_LAT * Math.PI) / 180)
  for (let q = -maxStep; q <= maxStep; q++) {
    for (let r = -maxStep; r <= maxStep; r++) {
      const eastKm = spacingKm * (q + r / 2)
      const northKm = spacingKm * (Math.sqrt(3) / 2) * r
      if (Math.hypot(eastKm, northKm) > radiusKm + 1e-6) continue
      const point = { id: `${prefix}_${q}_${r}`, q, r, lat: ANCHOR_LAT + northKm / 111.32, lng: ANCHOR_LNG + eastKm / (111.32 * cosLat) }
      if (lattice) point.hex = { unit_q: q, unit_r: r, rung_miles: spacingMiles }
      pts.push(point)
    }
  }
  return pts
}

function signedArea(ring) {
  let a = 0
  for (let i = 0; i < ring.length; i++) {
    const p = ring[i], q = ring[(i + 1) % ring.length]
    a += p.x * q.y - q.x * p.y
  }
  return a * .5
}

const rendered = outline => outline.rings.map(ring => flattenTerritoryRing(ring))
const renderedArea = outline => rendered(outline).reduce((sum, ring) => sum + signedArea(ring), 0)
const contains = (outline, point) => {
  const xy = projectZoom0([point.lat, point.lng])
  return pointInRings(rendered(outline), xy.x, xy.y)
}

// Deterministic pseudo-random numbers for synthetic rank fields.
function seeded(seed) {
  let s = seed >>> 0
  return () => { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296 }
}

test('head-to-head reach reproduces tie fractions, the minimum claim and the lone-dot cap', () => {
  assert.deepEqual(headToHeadReach(1, 1, false, false, 0), [.5, .5])
  const [third, rest] = headToHeadReach(1, 2, false, false, 0)
  assert.ok(Math.abs(third - 1 / 3) < 1e-12 && Math.abs(rest - 2 / 3) < 1e-12)
  assert.deepEqual(headToHeadReach(1, 3, false, false, 0), [.25, .75])
  // A lead of 10 against 1 is clamped so the trailing dot keeps its minimum claim.
  const [strong, weak] = headToHeadReach(10, 1, false, false, 0)
  assert.ok(Math.abs(weak - TERRITORY_MIN_CLAIM) < 1e-12 && Math.abs(strong + weak - 1) < 1e-12)
  // An uncorroborated single dot never claims past the flat midpoint, and the border stays flush.
  assert.deepEqual(headToHeadReach(10, 1, true, false, 0), [.5, .5])
  // Both claims here sit on a clamp, so TAU has nothing rank-computed to open.
  assert.deepEqual(headToHeadReach(10, 1, true, false, 1), [.5, .5])
  // With a real lead on the neighbor's side, the seam opens only by that neighbor's retreat.
  const [cappedDot, neighbor] = headToHeadReach(6, 4, true, false, 1)
  assert.ok(Math.abs(cappedDot - .5) < 1e-12 && Math.abs(neighbor - .4) < 1e-12)
  // TAU = 1 with a one-rank lead on both sides opens the widest seam.
  const [a, b] = headToHeadReach(1, 1, false, false, 1)
  assert.ok(Math.abs(a - TERRITORY_MIN_CLAIM) < 1e-12 && Math.abs(b - TERRITORY_MIN_CLAIM) < 1e-12)
  for (let mi = 1; mi <= 10; mi++) {
    for (let mj = 1; mj <= 10; mj++) {
      for (const tau of [0, .25, .5, 1]) {
        for (const lone of [[false, false], [true, false], [false, true], [true, true]]) {
          const [x, y] = headToHeadReach(mi, mj, lone[0], lone[1], tau)
          assert.ok(x + y <= 1 + 1e-12, `reach sum ${x + y} for ${mi}, ${mj}, ${tau}`)
          assert.ok(x >= TERRITORY_MIN_CLAIM - 1e-12 && y >= TERRITORY_MIN_CLAIM - 1e-12)
          if (tau === 0) assert.ok(Math.abs(x + y - 1) < 1e-12, 'TAU = 0 is always flush')
        }
      }
    }
  }
})

for (const lattice of [true, false]) {
  const mode = lattice ? 'lattice mesh' : 'Delaunay mesh'
  test(`adjacent same-leader points merge into one loop (${mode})`, () => {
    const pts = makeHexGrid(1.125, 2.5, { lattice })
    const a = pts.find(p => p.q === 0 && p.r === 0)
    const b = pts.find(p => p.q === 1 && p.r === 0)
    const cellById = new Map([
      [a.id, { leaderId: 'L1', color: '#00ffff', kind: 'ranked' }],
      [b.id, { leaderId: 'L1', color: '#00ffff', kind: 'ranked' }],
    ])
    const outlines = hexTerritoryOutlines(pts, cellById, projectZoom0)
    assert.equal(outlines.length, 1)
    assert.equal(outlines[0].leaderId, 'L1')
    assert.equal(outlines[0].size, 2)
    assert.equal(outlines[0].rings.length, 1)
    assert.ok(signedArea(outlines[0].rings[0]) > 0)
    assert.ok(contains(outlines[0], a) && contains(outlines[0], b))
    for (const other of pts) if (other !== a && other !== b) assert.ok(!contains(outlines[0], other), `${other.id} has no result and stays outside`)
    assert.equal(outlines.seams.length, 0, 'borders against empty samples are not head-to-head seams')
  })

  test(`a single enclave gets its own loop inside a matching hole (${mode})`, () => {
    const pts = makeHexGrid(1.125, 2.5, { lattice })
    const cellById = new Map()
    const center = pts.find(p => p.q === 0 && p.r === 0)
    cellById.set(center.id, { leaderId: 'B', color: '#ff0000', kind: 'ranked' })
    for (const [dq, dr] of [[1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]]) {
      cellById.set(pts.find(p => p.q === dq && p.r === dr).id, { leaderId: 'A', color: '#00ff00', kind: 'ranked' })
    }
    const outlines = hexTerritoryOutlines(pts, cellById, projectZoom0)
    assert.equal(outlines.length, 2)
    const surround = outlines.find(o => o.leaderId === 'A'), enclave = outlines.find(o => o.leaderId === 'B')
    assert.equal(surround.size, 6)
    assert.equal(surround.rings.length, 2)
    const outer = signedArea(surround.rings[0]), hole = signedArea(surround.rings[1])
    assert.ok(outer > 0 && hole < 0, 'outer ring positive, hole negative')
    assert.equal(enclave.size, 1)
    assert.equal(enclave.rings.length, 1)
    assert.equal(enclave.rings[0].length, 6)
    // Flush at TAU = 0: the enclave fills its hole exactly, with no ranks supplied (flat tie).
    assert.ok(Math.abs(signedArea(enclave.rings[0]) + hole) / -hole < 1e-9)
    assert.equal(outlines.seams.length, 6)
    for (const seam of outlines.seams) assert.ok(Math.abs(seam.reachA - .5) < 1e-12 && seam.gapFrac < 1e-12)
    // Contested ground opens the same six seams by a rank-computed amount.
    const open = hexTerritoryOutlines(pts, cellById, projectZoom0, { tau: 1 })
    assert.ok(open.seams.every(seam => seam.gapFrac > .05))
    assert.ok(signedArea(open.find(o => o.leaderId === 'B').rings[0]) < signedArea(enclave.rings[0]))
  })
}

function syntheticField(pts, leaders, seed) {
  const random = seeded(seed)
  const cellById = new Map(), ranks = new Map()
  for (const p of pts) {
    // Smooth blobs plus noise, so the field has straight borders, triple junctions and lone dots.
    const blob = Math.floor((Math.sin(p.q * .9 + seed) + Math.cos(p.r * .8 - seed) + 2) / 4 * leaders.length)
    const leader = random() < .12 ? leaders[Math.floor(random() * leaders.length)] : leaders[Math.min(leaders.length - 1, blob)]
    cellById.set(p.id, { winnerId: leader, leaderId: leader, color: '#00ffff', kind: 'ranked' })
    const row = new Map()
    for (const other of leaders) if (other !== leader) row.set(other, random() < .15 ? null : 2 + Math.floor(random() * 14))
    ranks.set(p.id, row)
  }
  return { cellById, rankLookup: (pt, id) => ranks.get(pt.id).get(id) ?? null }
}

function assertPartition(pts, cellById, outlines, discArea, label) {
  const total = outlines.reduce((sum, o) => sum + renderedArea(o), 0)
  assert.ok(Math.abs(total - discArea) / discArea < 2e-3, `${label}: territories tile the study circle (${total / discArea})`)
  for (const p of pts) {
    const owners = outlines.filter(o => contains(o, p))
    assert.equal(owners.length, 1, `${label}: ${p.id} sits in exactly one territory`)
    assert.equal(owners[0].leaderId, cellById.get(p.id).winnerId, `${label}: ${p.id} sits in its own leader's territory`)
  }
}

test('flush TAU = 0 borders tile the clipped circle with no voids on lattice and mixed-rung meshes', () => {
  const radiusMiles = 4, center = [ANCHOR_LAT, ANCHOR_LNG]
  const edge = projectZoom0([ANCHOR_LAT, ANCHOR_LNG + radiusMiles * KM_PER_MILE / (111.32 * Math.cos(ANCHOR_LAT * Math.PI / 180))])
  const mid = projectZoom0(center)
  const base = makeHexGrid(.8, radiusMiles)
  // Mixed rungs: a finer nested rung over part of the study forces the Delaunay path.
  const nested = makeHexGrid(.4, 1.6, { prefix: 'n' }).filter(p => p.q % 2 || p.r % 2)
  for (const [label, pts] of [['lattice', base], ['mixed rungs', base.concat(nested)]]) {
    for (const seed of [3, 11]) {
      const { cellById, rankLookup } = syntheticField(pts, ['A', 'B', 'C', 'D'], seed)
      const prep = prepareHexTerritory(pts, cellById, projectZoom0, { clipRadiusKm: radiusMiles * KM_PER_MILE, anchorLatLng: center, rankLookup })
      const circle = prep.mesh.circle
      assert.ok(Math.abs(circle.r - Math.abs(edge.x - mid.x)) / circle.r < 1e-2)
      const flush = hexTerritoryFromPrep(prep, 0)
      assertPartition(pts, cellById, flush.outlines, Math.PI * circle.r * circle.r, `${label} seed ${seed}`)
      assert.ok(flush.seams.every(seam => seam.gapFrac < 1e-12))
      const open = hexTerritoryFromPrep(prep, 1)
      for (const p of pts) {
        const owners = open.outlines.filter(o => contains(o, p))
        assert.equal(owners.length, 1, `${label} seed ${seed}: ${p.id} keeps exactly one territory at TAU = 1`)
        assert.equal(owners[0].leaderId, cellById.get(p.id).winnerId)
      }
      // Every vertex stays inside the true circle: the perimeter clip is exact.
      for (const outline of open.outlines.concat(flush.outlines)) {
        for (const ring of outline.rings) for (const v of ring) assert.ok(Math.hypot(v.x - circle.x, v.y - circle.y) <= circle.r * (1 + 1e-9))
      }
    }
  }
})

test('square-grid territoryOutlines remains completely unchanged', () => {
  const pts = []
  const cellById = new Map()
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 3; c++) {
      const id = `sq_${r}_${c}`
      pts.push({ id, lat: 30.25 - r * 0.01, lng: -97.78 + c * 0.01 })
      cellById.set(id, { leaderId: r === 1 && c === 1 ? 'B' : 'A', color: r === 1 && c === 1 ? '#ff0000' : '#00ff00', kind: 'ranked' })
    }
  }
  const outlines = territoryOutlines(pts, cellById, projectZoom0)
  assert.equal(outlines.length, 2)
  const a = outlines.find(o => o.leaderId === 'A')
  assert.equal(a.size, 8)
  assert.equal(a.rings.length, 2)
  assert.equal(a.adaptiveRadius, undefined)
})

// ---------- Acceptance on the measured Home Slice 10 mile honeycomb study ----------
const STUDY_URL = new URL('../runs/home-slice-hex-10mi-20261125/companion-study.json', import.meta.url)
const hasStudy = fs.existsSync(STUDY_URL)
const LANE = 'q1'
const VIA_313 = 'cid:3272667789479186633'
const JOES = 'cid:712452448263783393'
const BROOKLYN_PIE = 'cid:14769761460167517920'
let study = null
function loadStudy() {
  if (study) return study
  const model = normalizeStudy(JSON.parse(fs.readFileSync(STUDY_URL, 'utf8')))
  const anchor = model.businesses.find(b => b.id === model.targetId)
  const rankLookup = (pt, id) => observationFor(model, pt, LANE, id)?.rank ?? null
  const options = { clipRadiusKm: model.sampling.radius_km, anchorLatLng: [anchor.lat, anchor.lng], rankLookup,
    nameOf: id => model.businesses.find(b => b.id === id)?.name }
  // The same cells the companion builds: every point carries its true winner; only
  // highlighted leaders (recurring, or all winners) are drawn.
  const cellsFor = minimumWins => {
    const leaders = localLeaders(model, LANE, minimumWins)
    const cells = new Map()
    for (const p of model.points) {
      const winner = winnerAt(p.observations[LANE])
      const row = winner && leaders.byId.get(winner.id)
      const shown = !!row && (minimumWins === 1 || row.major)
      cells.set(p.id, { winnerId: winner?.id ?? null, leaderId: shown ? winner.id : null, kind: shown ? 'ranked' : winner ? 'other' : 'unknown',
        color: shown ? row.color : null, leaderName: winner?.name })
    }
    return cells
  }
  const allCells = cellsFor(1), recurringCells = cellsFor(3)
  study = { model, options, allCells, recurringCells, index: new Map(model.points.map((p, i) => [p.id, i])),
    all: prepareHexTerritory(model.points, allCells, projectZoom0, options),
    recurring: prepareHexTerritory(model.points, recurringCells, projectZoom0, options) }
  return study
}

function indexOutlines(outlines) {
  return outlines.map(outline => {
    const rings = rendered(outline)
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    for (const ring of rings) for (const v of ring) { minX = Math.min(minX, v.x); maxX = Math.max(maxX, v.x); minY = Math.min(minY, v.y); maxY = Math.max(maxY, v.y) }
    return { outline, rings, minX, minY, maxX, maxY }
  })
}
const ownersAt = (indexed, x, y) => indexed.filter(o => x >= o.minX && x <= o.maxX && y >= o.minY && y <= o.maxY && pointInRings(o.rings, x, y))

test('all 955 measured first-place points sit strictly inside their own leader polygon at TAU = 0 and TAU = 1', { skip: !hasStudy && 'study run folder not present' }, () => {
  const { model, allCells, recurringCells, all, recurring } = loadStudy()
  assert.equal(model.points.length, 955)
  for (const tau of [0, .5, 1]) {
    const indexed = indexOutlines(hexTerritoryFromPrep(all, tau).outlines)
    let checked = 0
    for (const p of model.points) {
      const xy = projectZoom0([p.lat, p.lng])
      const owners = ownersAt(indexed, xy.x, xy.y)
      assert.equal(owners.length, 1, `TAU ${tau}: ${p.id} is inside exactly one rendered polygon`)
      assert.equal(owners[0].outline.leaderId, allCells.get(p.id).winnerId, `TAU ${tau}: ${p.id} is inside its own leader`)
      checked++
    }
    assert.equal(checked, 955)
    assert.equal(indexed.reduce((sum, o) => sum + o.outline.size, 0), 955)
    // Default recurring-winner view: smaller winners still shape the borders but draw nothing.
    const shown = indexOutlines(hexTerritoryFromPrep(recurring, tau).outlines)
    for (const p of model.points) {
      const xy = projectZoom0([p.lat, p.lng]), cell = recurringCells.get(p.id)
      const owners = ownersAt(shown, xy.x, xy.y)
      if (cell.kind === 'ranked') assert.deepEqual(owners.map(o => o.outline.leaderId), [cell.winnerId])
      else assert.equal(owners.length, 0, `TAU ${tau}: filtered winner ${p.id} is not claimed by a drawn leader`)
    }
  }
})

test('rendered polygons of distinct leaders never overlap, and TAU = 0 leaves no voids', { skip: !hasStudy && 'study run folder not present' }, () => {
  const { all } = loadStudy()
  const { verts, tris, meshVerts, circle } = all.mesh
  // Dense probes over every measured triangle. Seeded random barycentric positions keep
  // probes off the borders themselves (tie borders run exactly through edge midpoints).
  const probes = [], random = seeded(20261125)
  for (let t = 0; t < tris.length; t += 3) {
    const [a, b, c] = [tris[t], tris[t + 1], tris[t + 2]]
    if (a >= meshVerts || b >= meshVerts || c >= meshVerts) continue
    for (let k = 0; k < 16; k++) {
      let wa = random(), wb = random()
      if (wa + wb > 1) { wa = 1 - wa; wb = 1 - wb }
      const wc = 1 - wa - wb
      const x = wa * verts[a].x + wb * verts[b].x + wc * verts[c].x, y = wa * verts[a].y + wb * verts[b].y + wc * verts[c].y
      if (Math.hypot(x - circle.x, y - circle.y) < circle.r * .999) probes.push([x, y])
    }
  }
  assert.ok(probes.length > 20000)
  for (const tau of [0, .35, 1]) {
    const { outlines } = hexTerritoryFromPrep(all, tau)
    const indexed = indexOutlines(outlines)
    let claimed = 0
    for (const [x, y] of probes) {
      const owners = ownersAt(indexed, x, y)
      assert.ok(owners.length <= 1, `TAU ${tau}: (${x}, ${y}) is claimed by ${owners.map(o => o.outline.leaderId).join(' and ')}`)
      claimed += owners.length
    }
    const area = outlines.reduce((sum, o) => sum + renderedArea(o), 0), disc = Math.PI * circle.r * circle.r
    if (tau === 0) {
      assert.equal(claimed, probes.length, 'every probe inside the circle is claimed at TAU = 0')
      assert.ok(Math.abs(area - disc) / disc < 1e-3, `flush territories tile the study circle (${area / disc})`)
    } else {
      assert.ok(claimed < probes.length, 'contested ground opens seams')
      assert.ok(area < disc * .995)
    }
    // Razor-sharp perimeter: no vertex leaves the true study circle.
    for (const outline of outlines) for (const ring of outline.rings) for (const v of ring) assert.ok(Math.hypot(v.x - circle.x, v.y - circle.y) <= circle.r * (1 + 1e-9))
  }
})

test('locality: a rank change away from an edge moves zero vertices on that edge', { skip: !hasStudy && 'study run folder not present' }, () => {
  const { model, options, allCells, all, index } = loadStudy()
  const touched = new Set(model.points.filter((_, i) => i % 7 === 3).map(p => p.id))
  const rankLookup = (pt, id) => {
    const rank = options.rankLookup(pt, id)
    if (!touched.has(pt.id)) return rank
    return rank == null ? 4 : rank <= 2 ? rank + 3 : Math.max(2, rank - 2)
  }
  const changed = prepareHexTerritory(model.points, allCells, projectZoom0, { ...options, rankLookup })
  for (const tau of [0, 1]) {
    const before = hexTerritoryFromPrep(all, tau).seams, after = hexTerritoryFromPrep(changed, tau).seams
    assert.equal(before.length, after.length)
    let untouched = 0, moved = 0
    before.forEach((seam, i) => {
      const other = after[i]
      assert.equal(seam.aIdx, other.aIdx)
      assert.equal(seam.bIdx, other.bIdx)
      if (touched.has(model.points[seam.aIdx].id) || touched.has(model.points[seam.bIdx].id)) {
        if (seam.p1.x !== other.p1.x || seam.p1.y !== other.p1.y || seam.p2.x !== other.p2.x || seam.p2.y !== other.p2.y) moved++
        return
      }
      untouched++
      assert.deepEqual([other.p1, other.p2], [seam.p1, seam.p2], `TAU ${tau}: edge ${model.points[seam.aIdx].id} to ${model.points[seam.bIdx].id} must not move`)
    })
    assert.ok(untouched > 300 && moved > 50, `locality sample is meaningful (${untouched} fixed, ${moved} moved)`)
  }
  // A single edit: only edges that end at the edited point may move.
  const target = model.points[index.get('hex_-11_-1')]
  const single = prepareHexTerritory(model.points, allCells, projectZoom0, { ...options,
    rankLookup: (pt, id) => pt === target && id === JOES ? 9 : options.rankLookup(pt, id) })
  const before = hexTerritoryFromPrep(all, 1).seams, after = hexTerritoryFromPrep(single, 1).seams
  let moved = 0
  before.forEach((seam, i) => {
    const same = JSON.stringify([seam.p1, seam.p2]) === JSON.stringify([after[i].p1, after[i].p2])
    if (!same) { moved++; assert.ok(seam.aIdx === index.get('hex_-11_-1') || seam.bIdx === index.get('hex_-11_-1')) }
  })
  assert.ok(moved >= 1 && moved <= 6)
})

test('reference borders: Via 313 against Joe\'s tie fractions, and the lone Brooklyn Pie dot', { skip: !hasStudy && 'study run folder not present' }, () => {
  const { model, all, allCells, index } = loadStudy()
  const { seams } = hexTerritoryFromPrep(all, 0)
  const reachFrom = (id, dq, dr) => {
    const i = index.get(id), p = model.points[i]
    const j = index.get(`hex_${p.hex.unit_q + dq}_${p.hex.unit_r + dr}`)
    const seam = seams.find(s => (s.aIdx === i && s.bIdx === j) || (s.aIdx === j && s.bIdx === i))
    assert.ok(seam, `${id} has a seam toward (${dq}, ${dr})`)
    return seam.aIdx === i
      ? { reach: seam.reachA, self: seam.leaderA, other: seam.leaderB, otherName: seam.nameB, selfName: seam.nameA, otherHere: seam.rankBatA, selfThere: seam.rankAatB, gap: seam.gapFrac }
      : { reach: seam.reachB, self: seam.leaderB, other: seam.leaderA, otherName: seam.nameA, selfName: seam.nameB, otherHere: seam.rankAatB, selfThere: seam.rankBatA, gap: seam.gapFrac }
  }
  // ref2: hex_-11_-1 is Via 313 with Joe's Slice of Sicily on four sides.
  assert.equal(allCells.get('hex_-11_-1').winnerId, VIA_313)
  const expected = { E: [1, 0, .33], NE: [0, 1, .25], NW: [-1, 1, .5], W: [-1, 0, .5] }
  for (const [side, [dq, dr, fraction]] of Object.entries(expected)) {
    const edge = reachFrom('hex_-11_-1', dq, dr)
    assert.equal(edge.self, VIA_313)
    assert.equal(edge.other, JOES, `${side} neighbor is Joe's`)
    assert.equal(edge.otherHere, 2, 'Joe\'s ranks #2 at the Via 313 point')
    assert.ok(Math.abs(edge.reach - fraction) <= .02, `${side} reach ${edge.reach} is within 0.02 of ${fraction}`)
    assert.ok(Math.abs(edge.reach - 1 / (1 + edge.selfThere - 1)) < 1e-9, 'the fraction is exactly the head-to-head tie point')
    assert.ok(edge.gap < 1e-12)
    assert.match(edge.selfName, /Via 313/)
    assert.match(edge.otherName, /Joe/)
  }
  // ref3: hex_8_-13 is a single Brooklyn Pie dot ringed by six points of one other leader.
  assert.equal(allCells.get('hex_8_-13').winnerId, BROOKLYN_PIE)
  const ring = [[1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]].map(([dq, dr]) => reachFrom('hex_8_-13', dq, dr))
  assert.equal(new Set(ring.map(edge => edge.other)).size, 1, 'one leader surrounds the dot')
  for (const edge of ring) assert.ok(Math.abs(edge.reach - .5) < 1e-12, `uncorroborated dot reaches exactly 0.50, got ${edge.reach}`)
  // The cap only ever stops an overreach: uncapped, the dot would claim more than half.
  for (const edge of ring) assert.ok(edge.otherHere > edge.selfThere)
})

test('focus overlay: Brooklyn Pie 3-pack plateau and Home Slice flip counts', { skip: !hasStudy && 'study run folder not present' }, () => {
  const { model, index } = loadStudy()
  const brooklyn = computeFocusOverlay(model, LANE, BROOKLYN_PIE)
  const component = id => {
    const p = model.points[index.get(id)], xy = projectZoom0([p.lat, p.lng])
    return brooklyn.plateau.findIndex(c => pointInRings(c.rings.map(ring => flattenTerritoryRing(ring)), xy.x, xy.y))
  }
  // ref1: both Brooklyn Pie first-place islands sit on one connected 3-pack plateau.
  assert.ok(component('hex_8_-13') >= 0)
  assert.equal(component('hex_8_-13'), component('hex_10_-15'))
  const plateau = brooklyn.plateau[component('hex_8_-13')]
  assert.equal(plateau.size, 92)
  assert.equal(plateau.size, Math.max(...brooklyn.plateau.map(c => c.size)))
  // Every plateau point really is a top-three result, and nothing ranked 4 or worse is inside.
  const indexed = brooklyn.plateau.map(c => c.rings.map(ring => flattenTerritoryRing(ring)))
  let inside = 0
  for (const p of model.points) {
    const rank = observationFor(model, p, LANE, BROOKLYN_PIE)?.rank ?? null
    const xy = projectZoom0([p.lat, p.lng])
    const hit = indexed.some(rings => pointInRings(rings, xy.x, xy.y))
    assert.equal(hit, rank != null && rank <= 3, `${p.id} rank ${rank}`)
    if (hit) inside++
  }
  assert.equal(inside, brooklyn.plateau.reduce((sum, c) => sum + c.size, 0))
  assert.ok(brooklyn.reach.reduce((sum, c) => sum + c.size, 0) > inside, 'top-10 reach is wider than the 3-pack plateau')
  assert.equal(brooklyn.stats.wins, 57)

  const home = computeFocusOverlay(model, LANE, model.targetId)
  assert.equal(home.stats.wins, 90)
  assert.equal(home.stats.rank2Points.length, 174)
  assert.equal(home.stats.rank3Points.length, 260)
  assert.ok(home.stats.adjacentRank2Count > 0 && home.stats.adjacentRank2Count <= 174)
  assert.equal(home.stats.topBlocker.name, 'Joe\'s Slice of Sicily')
  assert.ok(home.stats.topBlocker.count > 0 && home.stats.topBlocker.count <= 174)
})

// ---------- Coastal offshore extrapolation & real-coastline land mask ----------
function makeIslandModel({ withLandMask = false, rank = 4, unrankedIsland = false } = {}) {
  const spacingMiles = 0.5
  const radiusMiles = 4.0
  // 7-point hex island at center surrounded by open water inside a 4-mile study circle.
  const full = makeHexGrid(spacingMiles, radiusMiles)
  const islandCoords = new Set(['0,0', '1,0', '0,1', '-1,1', '-1,0', '0,-1', '1,-1'])
  const islandPts = full.filter(p => islandCoords.has(`${p.q},${p.r}`))
  const points = islandPts.map(p => ({
    id: p.id, lat: p.lat, lng: p.lng, hex: p.hex,
    observations: {
      q1: {
        status: unrankedIsland ? 'not_returned_depth_reached' : 'found',
        targetRank: unrankedIsland ? null : rank,
        items: unrankedIsland
          ? [{ id: 'RIVAL', name: 'Island Rival', rank: 1 }]
          : [
              { id: 'RIVAL', name: 'Island Rival', rank: 1 },
              { id: 'RIVAL2', name: 'Runner Up', rank: 2 },
              { id: 'TARGET', name: 'Coastal Target', rank },
            ],
      },
    },
  }))
  const landMaskPolygons = withLandMask ? [{
    outer: [
      [ANCHOR_LNG - 0.015, ANCHOR_LAT - 0.015],
      [ANCHOR_LNG + 0.015, ANCHOR_LAT - 0.015],
      [ANCHOR_LNG + 0.015, ANCHOR_LAT + 0.015],
      [ANCHOR_LNG - 0.015, ANCHOR_LAT + 0.015],
      [ANCHOR_LNG - 0.015, ANCHOR_LAT - 0.015],
    ],
    holes: [],
  }] : undefined
  return {
    name: 'Synthetic Island',
    geometry: 'hex_radius',
    depth: 30,
    targetId: 'TARGET',
    sampling: { radius_km: radiusMiles * KM_PER_MILE, spacing_km: spacingMiles * KM_PER_MILE, center: { lat: ANCHOR_LAT, lng: ANCHOR_LNG } },
    businesses: [
      { id: 'TARGET', name: 'Coastal Target', target: true, lat: ANCHOR_LAT, lng: ANCHOR_LNG },
      { id: 'RIVAL', name: 'Island Rival', target: false, lat: ANCHOR_LAT, lng: ANCHOR_LNG },
    ],
    queries: [{ id: 'q1', name: 'coastal test' }],
    points,
    ...(landMaskPolygons ? { landMaskPolygons, land_mask_polygons: landMaskPolygons } : {}),
  }
}

test('offshore water extrapolation eliminates fake #10.5/#20.5 beach cliffs on a water-surrounded island', () => {
  const center = projectZoom0([ANCHOR_LAT, ANCHOR_LNG])
  const eastPin = makeHexGrid(0.5, 1.0).find(p => p.q === 1 && p.r === 0)
  const stepPx = Math.hypot(projectZoom0([eastPin.lat, eastPin.lng]).x - center.x, projectZoom0([eastPin.lat, eastPin.lng]).y - center.y)

  const minContourRadiusFromCenter = parts => {
    let minR = Infinity
    for (const part of parts) {
      for (const ring of part.rings) {
        for (const v of flattenTerritoryRing(ring)) {
          minR = Math.min(minR, Math.hypot(v.x - center.x, v.y - center.y))
        }
      }
    }
    return minR
  }

  // Without land_mask_polygons: skirt apexes sit 0.5 hops off the outermost island pins (~1.5 steps from center),
  // creating stacked fake #10.5 and #20.5 cliffs hugging the beach.
  const unmasked = makeIslandModel({ withLandMask: false, rank: 4 })
  const elevUnmasked = computeElevationStack(unmasked, 'q1', 'TARGET')
  const r10Unmasked = minContourRadiusFromCenter(elevUnmasked.levels.find(l => l.rank === 10).parts)
  const r20Unmasked = minContourRadiusFromCenter(elevUnmasked.levels.find(l => l.rank === 20).parts)
  assert.ok(r10Unmasked < 1.65 * stepPx, `unmasked #10.5 hugs beach at ${(r10Unmasked / stepPx).toFixed(2)} steps`)
  assert.ok(r20Unmasked < 1.65 * stepPx, `unmasked #20.5 hugs beach at ${(r20Unmasked / stepPx).toFixed(2)} steps`)

  // With land_mask_polygons: offshore extrapolation extends rank #4 out 3 hops into open water,
  // completely clearing the beach of fake #10.5 and #20.5 cliffs!
  const masked = makeIslandModel({ withLandMask: true, rank: 4 })
  const elevMasked = computeElevationStack(masked, 'q1', 'TARGET')
  const lvl4 = elevMasked.levels.find(l => l.rank === 4).parts
  const lvl10 = elevMasked.levels.find(l => l.rank === 10).parts
  const lvl20 = elevMasked.levels.find(l => l.rank === 20).parts
  assert.ok(lvl4.length > 0 && lvl10.length > 0 && lvl20.length > 0)
  const r4Masked = minContourRadiusFromCenter(lvl4)
  const r10Masked = minContourRadiusFromCenter(lvl10)
  const r20Masked = minContourRadiusFromCenter(lvl20)
  // All contours stay at least 3.0 hex steps from island center (> 2.0 steps past the outermost island pins!)
  assert.ok(r4Masked > 3.0 * stepPx, `masked #4.5 pushed offshore to ${(r4Masked / stepPx).toFixed(2)} steps`)
  assert.ok(r10Masked > 3.0 * stepPx, `masked #10.5 pushed offshore to ${(r10Masked / stepPx).toFixed(2)} steps`)
  assert.ok(r20Masked > 3.0 * stepPx, `masked #20.5 pushed offshore to ${(r20Masked / stepPx).toFixed(2)} steps`)

  // A shoreline probe 0.75 steps past the easternmost island pin (1.75 steps from center) sits cleanly inside rank #4!
  const shorelineX = center.x + 1.75 * stepPx
  const inRank4 = lvl4.some(part => pointInRings(part.rings.map(r => flattenTerritoryRing(r)), shorelineX, center.y))
  assert.equal(inRank4, true, 'pure emerald #4 extends past the shoreline before exact coastline clip')

  // Unranked island stays strictly unranked (> 30): offshore extrapolation never hallucinates a rank.
  const unranked = makeIslandModel({ withLandMask: true, unrankedIsland: true })
  const elevUnranked = computeElevationStack(unranked, 'q1', 'TARGET')
  assert.equal(elevUnranked.levels.length, 0, 'unranked island produces zero elevation bands')

  // Local Leaders & Fortress Core Relief also extend smoothly past the beach into the offshore buffer.
  const cellById = new Map(masked.points.map(p => [p.id, { winnerId: 'RIVAL', leaderId: 'RIVAL', color: '#00aaff', kind: 'ranked', leaderName: 'Island Rival' }]))
  const leaderOutlines = hexTerritoryOutlines(masked.points, cellById, projectZoom0, {
    clipRadiusKm: masked.sampling.radius_km,
    anchorLatLng: [ANCHOR_LAT, ANCHOR_LNG],
    extrapolateOffshore: true,
  })
  assert.equal(leaderOutlines.length, 1)
  assert.equal(pointInRings(rendered(leaderOutlines[0]), shorelineX, center.y), true, 'leader territory covers shoreline past coastal pin')
  const relief = computeLeaderRelief(masked, 'q1')
  assert.ok(relief.has('RIVAL'), 'fortress core relief computed for coastal leader')
  const reliefCoversShore = relief.get('RIVAL')[0].parts.some(p => pointInRings(p.rings.map(r => flattenTerritoryRing(r)), shorelineX, center.y))
  assert.equal(reliefCoversShore, true, 'fortress core relief extends cleanly to shoreline')
})

test('inland studies without land_mask_polygons keep identical elevation and relief output', { skip: !hasStudy && 'study run folder not present' }, () => {
  const { model } = loadStudy()
  assert.equal(model.landMaskPolygons, undefined)
  const defaultElev = computeElevationStack(model, LANE, model.targetId)
  const explicitOff = computeElevationStack(model, LANE, model.targetId, { extrapolateOffshore: false })
  assert.deepEqual(defaultElev.stats, explicitOff.stats)
  assert.equal(defaultElev.levels.length, explicitOff.levels.length)
  for (let i = 0; i < defaultElev.levels.length; i++) {
    assert.equal(defaultElev.levels[i].parts.length, explicitOff.levels[i].parts.length)
  }
  const defaultRelief = computeLeaderRelief(model, LANE)
  const explicitReliefOff = computeLeaderRelief(model, LANE, { extrapolateOffshore: false })
  assert.equal(defaultRelief.size, explicitReliefOff.size)
})

const PHILLY_URL = new URL('../src/data/cosmis-deli-philly-study.json', import.meta.url)
test('Bundled South Philadelphia river-clipped study normalizes land_mask_polygons and computes coastline-ready layers', () => {
  const raw = JSON.parse(fs.readFileSync(PHILLY_URL, 'utf8'))
  const model = normalizeStudy(raw)
  assert.equal(model.points.length, 458)
  assert.ok(Array.isArray(model.landMaskPolygons) && model.landMaskPolygons.length === 8)
  assert.equal(model.rawCirclePins, 513)
  const elev = computeElevationStack(model, 'q1', model.targetId)
  assert.equal(elev.levels.length, 30)
  const relief = computeLeaderRelief(model, 'q1')
  assert.ok(relief.size > 0)
})
