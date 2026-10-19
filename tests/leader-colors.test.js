import { test } from 'node:test'
import assert from 'node:assert/strict'
import { leaderIdentity, perceptualColor } from '../src/leader-colors.js'
import { localLeaders } from '../src/local-leaders.js'

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
