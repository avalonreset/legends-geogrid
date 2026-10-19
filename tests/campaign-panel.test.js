import test from 'node:test'
import assert from 'node:assert/strict'
import { validateCampaignResearch, campaignResearchHTML, cellMatchesLens, campaignAreas, campaignPlansHTML, campaignSourceURL, campaignPlanMapAction } from '../src/campaign-panel.js'

const model = { targetId: 'TARGET', businesses: [{ id: 'TARGET', cid: '123' }], queries: [{ id: 'q1', name: 'furnace repair' }] }
test('research is bound to the actual primary profile and exact query, not reused query IDs', () => {
  const input = { schema: 'geogrid-campaign-research/v1', primaryCid: '123',
    queries: { q1: { query: 'furnace repair', pages: [], nextChecks: [] } } }
  assert.ok(validateCampaignResearch(input, model).queries.q1)
  assert.throws(() => validateCampaignResearch({ ...input, primaryCid: '456' }, model))
  assert.deepEqual(validateCampaignResearch(input, { ...model, queries: [{ id: 'q1', name: 'pizza' }] }).queries, {})
})
test('research rendering rejects unsafe URLs and escapes untrusted content', () => {
  const research = validateCampaignResearch({ schema: 'geogrid-campaign-research/v1', primaryCid: '123',
    summary: '<script>bad</script>', queries: { q1: { query: 'furnace repair', nextChecks: ['<b>check</b>'],
      pages: [{ label: 'Bad', url: 'javascript:alert(1)' }, { label: '<img>', url: 'https://example.com/' }] } } }, model)
  const html = campaignResearchHTML(research, 'q1')
  assert.ok(!html.includes('javascript:'))
  assert.ok(!html.includes('<script>'))
  assert.ok(html.includes('&lt;script&gt;'))
  assert.ok(html.includes('https://example.com/'))
})
test('frontier and service lenses use their strict subsets rather than all weak ranks', () => {
  assert.equal(cellMatchesLens({ band: 'build', frontier: false }, 'frontier'), false)
  assert.equal(cellMatchesLens({ band: 'build', frontier: true }, 'frontier'), true)
  assert.equal(cellMatchesLens({ band: 'advance', serviceGap: false }, 'serviceGap'), false)
  assert.equal(cellMatchesLens({ band: 'advance', serviceGap: true }, 'serviceGap'), true)
  const intel = { areas: [{ band: 'build', id: 'large' }], frontierAreas: [{ id: 'edge' }], serviceGapAreas: [{ id: 'gap' }] }
  assert.deepEqual(campaignAreas(intel, 'frontier'), [{ id: 'edge' }])
  assert.deepEqual(campaignAreas(intel, 'serviceGap'), [{ id: 'gap' }])
})


test('campaign research keeps unmeasured proposals separate and rejects a reused baseline query', () => {
  const input = { schema: 'geogrid-campaign-research/v1', primaryCid: '123',
    queries: { q1: { query: 'furnace repair' } }, campaignPlans: [
      { id: 'measured', title: 'Furnace offer', baselineQuery: 'furnace repair' },
      { id: 'unmeasured', title: 'Assess heat pumps', stage: 'Research next' },
      { id: 'wrong-query', title: 'Old study', baselineQuery: 'pizza' }, null ] }
  const verified = validateCampaignResearch(input, model)
  assert.deepEqual(verified.campaignPlans.map(p => p.id), ['measured', 'unmeasured'])
  const html = campaignPlansHTML(verified, 'q1')
  assert.match(html, /2 campaign options/)
  assert.match(html, /Research next/)
  assert.match(html, /not work already published/)
  assert.doesNotMatch(html, /Old study/)
})

test('campaign sources reject credentials, executable links and relative traversal', () => {
  assert.equal(campaignSourceURL('/runs/client/study/FINDINGS.md'), '/runs/client/study/FINDINGS.md')
  for (const url of ['//outside.test', '/runs/../secret', 'https://u:secret@example.com', 'javascript:alert(1)']) assert.equal(campaignSourceURL(url), null)
  const html = campaignPlansHTML({ campaignPlans: [{ id: 'a', title: '<script>bad</script>',
    steps: ['<img src=x>'], sources: [{ label: 'unsafe', url: 'javascript:alert(1)' },
      { label: 'Verified report', url: '/runs/client/study/FINDINGS.md' }] }] }, 'q1')
  assert.match(html, /&lt;script&gt;/)
  assert.match(html, /&lt;img src=x&gt;/)
  assert.match(html, /Verified report/)
  assert.doesNotMatch(html, /javascript:|<script>|<img src=x>/)
})

test('campaign rendering tolerates absent or malformed optional research fields', () => {
  assert.equal(campaignPlansHTML(null, 'q1'), '')
  assert.equal(campaignPlansHTML({ campaignPlans: [null, {}] }, 'q1'), '')
  assert.doesNotThrow(() => campaignPlansHTML({ campaignPlans: [{ id: 'a', title: 'Check', sources: 'invalid', steps: 'invalid' }] }, 'q1'))
})


test('prepared plans link only an exact studied baseline and keep proxy labels explicit', () => {
  const research = { queries: { q1: { query: 'hvac contractor' }, q3: { query: 'air conditioning contractor' }, q4: { query: 'furnace repair' } },
    campaignPlans: [{ id: 'furnace', title: 'Repair booking', baselineQuery: 'furnace repair' },
      { id: 'install', title: 'Installation research', baselineQuery: 'air conditioning contractor' },
      { id: 'heatpump', title: 'Unmeasured heat pumps' },
      { id: 'stale', title: 'Absent query', baselineQuery: 'air conditioning installation' }] }
  assert.deepEqual(campaignPlanMapAction(research, 'furnace'), { campaignId: 'plan:furnace', planId: 'furnace', queryId: 'q4', lens: 'overview', regionId: 'all', originIds: [] })
  assert.equal(campaignPlanMapAction(research, 'heatpump'), null)
  assert.equal(campaignPlanMapAction(research, 'stale'), null)
  const html = campaignPlansHTML(research, 'q1')
  assert.match(html, /data-campaign-baseline="furnace" data-plan-query="q4" data-plan-lens="overview"/)
  assert.match(html, /View air conditioning contractor baseline on map/)
  assert.doesNotMatch(html, /View air conditioning installation|data-campaign-baseline="heatpump"|data-campaign-baseline="stale"/)
})
