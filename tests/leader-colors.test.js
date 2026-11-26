import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { coreBrandKey, leaderIdentity, perceptualColor, TARGET_SIGNATURE_COLOR } from '../src/leader-colors.js'
import { localLeaders } from '../src/local-leaders.js'
import { normalizeStudy } from '../src/study-model.js'

function model() {
  const businesses = Array.from({ length: 8 }, (_, i) => ({ id: `b${i}`, name: `Business ${i}` }))
  return { businesses, targetId: 'b0', queries: [{ id: 'q1' }, { id: 'q2' }],
    sampling: { spacing_km: 1 }, points: Array.from({ length: 64 }, (_, i) => ({
      id: `p${i}`, lat: Math.floor(i / 8) * .009, lng: i % 8 * .009,
      observations: Object.fromEntries(['q1', 'q2'].map((q, j) => [q, {
        status: 'found', items: [{ id: `b${(i + j) % 8}`, rank: 1 }],
      }])),
    })) }
}

test('adjacency coloring separates neighboring winners and is stable across queries and input ordering', () => {
  const input = model(), identity = leaderIdentity(input)
  assert.equal(identity.identities.get('b0').color, TARGET_SIGNATURE_COLOR)
  for (const [id, neighbors] of identity.graph) for (const neighbor of neighbors.keys()) {
    const a = identity.identities.get(id), b = identity.identities.get(neighbor)
    assert.notEqual(a.badge, b.badge)
    const ca = perceptualColor(a.color), cb = perceptualColor(b.color)
    assert.ok(Math.hypot(...ca.map((v, i) => v - cb[i])) > .15)
  }
  for (const row of localLeaders(input, 'q1').rows) {
    const other = localLeaders(input, 'q2').byId.get(row.business.id)
    assert.equal(row.color, other.color)
    assert.equal(row.badge, other.badge)
  }
  const reordered = { ...input, points: [...input.points].reverse(), businesses: [...input.businesses].reverse() }
  assert.deepEqual(leaderIdentity(reordered).identities, identity.identities)
  assert.equal(leaderIdentity(input), identity)
})

test('missing first-place evidence stays uncolored even in All winners', () => {
  const input = model()
  input.points[0].observations.q1 = { status: 'missing_result', items: [{ id: 'b7', rank: 1 }] }
  assert.equal(localLeaders(input, 'q1', 1).coloredPoints, 63)
})

test('cartographic hierarchy on real 955-point Austin study: exclusive target, unique top-15 brands, franchise families', () => {
  const studyPath = 'runs/home-slice-hex-10mi-20261125/companion-study.json'
  if (!fs.existsSync(studyPath)) return
  const study = normalizeStudy(JSON.parse(fs.readFileSync(studyPath, 'utf8')))
  const { identities, graph } = leaderIdentity(study)

  // 1. Target owns exclusive signature crimson; zero unrelated rivals share it.
  const targetIdentity = identities.get(study.targetId)
  assert.equal(targetIdentity.color, TARGET_SIGNATURE_COLOR)
  for (const [id, info] of identities) {
    if (info.brandKey !== targetIdentity.brandKey) {
      assert.notEqual(info.color, TARGET_SIGNATURE_COLOR, `Rival ${id} stole target color`)
    }
  }

  // 2. Top 15 distinct competitor brands ALL have globally unique colors (zero Cyan/Cyan collisions like L01 vs L05!).
  const byBrand = new Map()
  for (const [id, info] of identities) {
    if (!byBrand.has(info.brandKey)) byBrand.set(info.brandKey, [])
    byBrand.get(info.brandKey).push({ id, ...info })
  }
  const leaders = localLeaders(study, study.queries[0].id, 1).rows
  const top15Brands = []
  const seenColors = new Set()
  for (const row of leaders) {
    const info = identities.get(row.business.id)
    if (top15Brands.includes(info.brandKey)) continue
    top15Brands.push(info.brandKey)
    assert.ok(!seenColors.has(info.color), `Duplicate color ${info.color} among top brands (${row.business.name})`)
    seenColors.add(info.color)
    if (top15Brands.length >= 16) break
  }

  // 3. Multi-branch franchises are grouped cleanly (Home Slice, Pedroso's, Little Deli, Brooklyn Pie, Yaghi's, Via 313).
  assert.equal(coreBrandKey("Yaghi's Pizzeria"), coreBrandKey("Yaghi's New York Pizzeria"))
  assert.equal(coreBrandKey('Brooklyn Pie Co.'), coreBrandKey("Brooklyn Pie Co. @ LaLa's South Pole"))
  assert.notEqual(coreBrandKey('Dough Valley'), coreBrandKey('Dough You Want It Pizza'))
  assert.equal(byBrand.get(targetIdentity.brandKey).length, 2, 'Both Home Slice branches paired')

  // 4. Zero adjacent territories share an identical color.
  for (const [id, nbrs] of graph) {
    const c1 = identities.get(id).color
    for (const nid of nbrs.keys()) {
      assert.notEqual(c1, identities.get(nid).color, `Adjacent collision between ${id} and ${nid}`)
    }
  }
})
