import { test } from 'node:test'
import assert from 'node:assert/strict'
import { strategyRoomHTML, strategySafeURL } from '../src/strategy-room.js'

function fixture() {
  const model = { name: 'Primary <unsafe>', targetId: 'target', points: Array(5).fill({}),
    queries: [{ id: 'q1', name: 'furnace repair' }], businesses: [{ id: 'target' }, { id: 'rival' }],
    sampling: { radius_km: 1.609344 } }
  const metric = { complete: 4, unknown: 1, top3: 1, top10: 3, near: 2, found: 4,
    top3Pct: 25, top10Pct: 75, serviceGap: 1, frontier: 1,
    rivals: [{ id: 'wrong', name: 'Not the pressure metric', count: 4, denominator: 4 }] }
  const region = { id: 'core', label: 'Core · 0–1 mi', count: 5, originIds: ['a', 'b', 'c', 'd', 'e'], perQuery: { q1: metric },
    completeDenominator: 4, nearDenominator: 2,
    rivals: [{ id: 'rival', name: 'Regional leader', top3Appearances: 2, top3CoveragePct: 60, completeDenominator: 4 }],
    nearRivals: [{ id: 'blocker', name: 'Actual blocker', nearAhead: 2, nearDenominator: 2, top3Appearances: 1 }] }
  const intelligence = { available: true, regions: [{ ...region, id: 'all' }, region], insights: [],
    method: { geography: 'Measured circle', unknown: 'Missing evidence excluded' } }
  return { model, intelligence }
}

test('strategy room separates local pressure from first-place or top-three appearances', () => {
  const { model, intelligence } = fixture()
  const html = strategyRoomHTML(model, intelligence, null)
  assert.match(html, /Actual blocker/)
  assert.match(html, /2<small>\/2<\/small>/)
  assert.doesNotMatch(html, /Not the pressure metric/)
  assert.match(html, /All studied services in this area · appearances ahead where you rank 4–10/)
})

test('matrix coverage uses complete denominators and leaves unavailable coverage unknown', () => {
  const { model, intelligence } = fixture()
  let html = strategyRoomHTML(model, intelligence, null)
  assert.match(html, /1\/4 complete search locations/)
  assert.match(html, /25\.0%/)
  assert.match(html, /1 incomplete/)
  assert.doesNotMatch(html, /1\/5 complete search locations/)
  const metric = intelligence.regions[1].perQuery.q1
  metric.complete = 0; metric.unknown = 5; metric.top3 = 0; metric.top3Pct = null
  html = strategyRoomHTML(model, intelligence, null)
  assert.match(html, /<strong>—<\/strong><span>0\/0<\/span>/)
})

test('regional standings display equal-query percentage rather than pretending pooled fraction is the ranking metric', () => {
  const { model, intelligence } = fixture()
  const html = strategyRoomHTML(model, intelligence, null, { rivalLens: 'regional' })
  assert.match(html, /Regional leader/)
  assert.match(html, /<strong>60\.0%<\/strong>/)
  assert.match(html, /2\/4 pairs/)
  assert.match(html, /equal-query top-three coverage/)
})

test('short-radius snapshots omit unavailable directional groups and render method values', () => {
  const { model, intelligence } = fixture()
  const html = strategyRoomHTML(model, intelligence, null)
  assert.doesNotMatch(html, /colspan="4"/)
  assert.doesNotMatch(html, /5–10 MI/)
  assert.match(html, /Measured circle Missing evidence excluded/)
  assert.doesNotMatch(html, /\[object Object\]/)
})

test('campaign draft escapes sources and rejects executable or credential-bearing URLs', () => {
  const { model, intelligence } = fixture()
  const research = { queries: { q1: { actionBrief: { title: '<script>bad()</script>', observed: '<img src=x>',
    action: 'Clarify booking', nextChecks: ['Confirm policy'], existingUrl: 'javascript:alert(1)',
    reason: 'Observed ambiguity', success: 'Qualified booked jobs', readiness: 'Draft only' } } } }
  const html = strategyRoomHTML(model, intelligence, research)
  assert.match(html, /&lt;script&gt;/)
  assert.doesNotMatch(html, /<script>|<img src=x>|javascript:/)
  assert.match(html, /Confirm policy/)
  assert.match(html, /Clarify booking/)
  assert.equal(strategySafeURL('https://example.com/page'), 'https://example.com/page')
  assert.equal(strategySafeURL('https://name:secret@example.com'), null)
  assert.equal(strategySafeURL('data:text/html,hello'), null)
})

test('no top-three observations produce undefined concentration instead of a false zero', () => {
  const { model, intelligence } = fixture()
  intelligence.regions.forEach(region => { region.perQuery.q1.top3 = 0 })
  const html = strategyRoomHTML(model, intelligence, null)
  assert.match(html, /Top-three concentration<\/span><strong>—<\/strong>/)
})


test('researched campaign portfolio is distinct from spatial patterns and replaces duplicate draft blocks', () => {
  const { model, intelligence } = fixture()
  const research = { reviewedAt: '2026-10-18', queries: { q1: { query: 'furnace repair', actionBrief: { title: 'Duplicate old draft' } } },
    campaignPlans: [{ id: 'furnace', title: 'Clarify repair booking', baselineQuery: 'furnace repair',
      stage: 'Copy draft available', goal: 'Booked diagnostics', evidence: 'Verified offer discrepancy',
      steps: ['Prepare the corrected message'], gate: 'Confirm current pricing', measure: 'Qualified bookings' }] }
  const html = strategyRoomHTML(model, intelligence, research)
  assert.match(html, /Clarify repair booking/)
  assert.match(html, /Patterns worth checking/)
  assert.match(html, /not additional ready-to-launch campaigns/)
  assert.match(html, /Confirm current pricing/)
  assert.doesNotMatch(html, /Duplicate old draft/)
})
