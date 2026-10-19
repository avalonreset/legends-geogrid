import { test } from 'node:test'
import assert from 'node:assert/strict'
import { localLeaders, profileColor } from '../src/local-leaders.js'
import { normalizeStudy } from '../src/study-model.js'

const fixture = () => ({
  targetId: 'primary', sampling: { spacing_km: 1, radius_km: 5 },
  businesses: [
    { id: 'primary', name: 'Primary', lat: 0, lng: 0, target: true },
    { id: 'outside', name: 'Outside', lat: .2, lng: .2, shortlisted: false },
    { id: 'minor', name: 'Small', lat: 0, lng: 0 },
    { id: 'unknown', name: 'Unknown' },
  ],
  points: Array.from({ length: 10 }, (_, i) => ({
    id: `p${i}`, lat: 0, lng: i * .009,
    observations: { q1: { status: 'found', items: [{ id: i < 7 ? 'outside' : i < 8 ? 'minor' : 'unknown', rank: 1 }] },
      q2: { status: 'found', items: [{ id: 'primary', rank: 1 }] } },
  })),
})
test('major first-place profiles are chosen by wins, not shortlist or base distance', () => {
  const model = fixture(), leaders = localLeaders(model, 'q1')
  assert.equal(leaders.threshold, 3)
  assert.deepEqual([...leaders.majorIds], ['outside'])
  const outside = leaders.byId.get('outside')
  assert.equal(outside.wins, 7)
  assert.equal(outside.outside, true)
  assert.equal(outside.connector, true)
  assert.equal(outside.clusterSize, 7)
  assert.ok(Math.abs(outside.center.lng - .027) < .00001)
  assert.equal(leaders.byId.get('unknown').hasBase, false)
  assert.equal(leaders.coloredPoints, 7)
  assert.deepEqual([...localLeaders(model, 'q2').majorIds], ['primary'])
  assert.equal(localLeaders(model, 'q1'), leaders)
  assert.equal(outside.color, profileColor(model, 'outside'))
})
test('connector aims at largest connected patch, not mean of disconnected wins', () => {
  const model = fixture()
  model.points[6].lng = 2
  const row = localLeaders(model, 'q1').byId.get('outside')
  assert.equal(row.clusterSize, 6)
  assert.ok(row.center.lng < .03)
})
test('inside and nearby-outside bases have diamonds but never connectors', () => {
  for (const lat of [0, .05]) {
    const model = fixture()
    Object.assign(model.businesses[1], { lat, lng: 0 })
    const row = localLeaders(model, 'q1').byId.get('outside')
    assert.equal(row.major, true)
    assert.equal(row.hasBase, true)
    assert.equal(row.outside, lat > 0)
    assert.equal(row.connector, false)
  }
})
test('recurring threshold stays at three and pending searches cannot supply winners', () => {
  const model = fixture()
  model.points = Array.from({ length: 1249 }, (_, i) => ({ ...model.points[0], id: `p${i}`,
    observations: { q1: { status: 'pending', items: [{ id: 'outside', rank: 1 }] } } }))
  const result = localLeaders(model, 'q1')
  assert.equal(result.threshold, 3)
  assert.equal(result.rows.length, 0)
})
test('all-winners mode exposes single wins without changing recurring membership or IDs', () => {
  const model = fixture(), recurring = localLeaders(model, 'q1'), all = localLeaders(model, 'q1', 1)
  assert.equal(all.threshold, 1)
  assert.equal(all.coloredPoints, 10)
  assert.equal(all.majorIds.size, 3)
  assert.equal(recurring.majorIds.size, 1)
  for (const row of all.rows) {
    assert.equal(row.badge, recurring.byId.get(row.business.id).badge)
    assert.equal(row.color, recurring.byId.get(row.business.id).color)
  }
})
test('outside coordinates survive normalization without merging separate profiles', () => {
  const model = normalizeStudy({
    schema: 'geogrid-companion/v1', factions: [{ faction_id: 'T', name: 'Target', is_target: true }],
    lanes: [{ lane_id: 'q', query: 'repair' }],
    points: [{ tag: 'p', lat: 0, lng: 0, by_lane: { q: { status: 'found', top_items: [
      { title: 'Same chain', cid: '1', rank: 1, latitude: 10, longitude: 20 },
      { title: 'Same chain', cid: '2', rank: 2, latitude: 11, longitude: 21 },
      { title: 'Bad coordinate', cid: '3', rank: 3, latitude: 300, longitude: 0 },
    ] } } }],
  })
  assert.equal(model.businesses.find(b => b.cid === '1').lat, 10)
  assert.equal(model.businesses.find(b => b.cid === '2').lng, 21)
  assert.equal(model.businesses.find(b => b.cid === '3').lat, null)
})
