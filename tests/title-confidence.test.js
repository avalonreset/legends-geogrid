import { it } from 'node:test'
import assert from 'node:assert/strict'
import { titleConfidence } from '../src/title-confidence.js'
import { confidenceHTML } from '../src/name-review.js'

const now=Date.parse('2026-10-19T14:00:00Z')
function fixture() {
  const timestamp=new Date(now).toISOString()
  return {cid:'123',cid_verified:true,profile:{status:'complete',name:'Example City HVAC',checked_at:timestamp},
    source_review:{checked_at:timestamp,bracket:'possible_concern'},
    confidence:{rubric:'title-evidence-v1',cid:'123',profile_name:'Example City HVAC',level:2,
      rationale:'An added city conflicts with the visible brand; branch naming remains unresolved.',
      checked_at:timestamp,factors:[{label:'Brand conflict',met:true,reason:'The official branch page uses a shorter name.'}]}}
}
it('uses an explicit analyst score without inventing a probability or promoting the finding',()=>{
  const c=fixture()
  assert.equal(titleConfidence(c,now).level,2)
  assert.equal(titleConfidence(c,now).label,'Limited concern')
  assert.equal(c.source_review.bracket,'possible_concern')
  c.confidence.level=0
  assert.equal(titleConfidence(c,now).label,'Branding supports the title')
  c.confidence.level=null
  assert.equal(titleConfidence(c,now),null)
})
it('suppresses confidence for stale, future, failed or mismatched identity evidence',()=>{
  for(const mutate of [
    c=>c.profile.name='New current brand',
    c=>c.confidence.cid='456',
    c=>c.cid_verified=false,
    c=>c.profile.status='unavailable',
    c=>c.source_review=null,
    c=>c.profile.checked_at='2026-09-25T00:00:00Z',
    c=>c.source_review.checked_at='2026-09-25T00:00:00Z',
    c=>c.confidence.checked_at='2027-01-01T00:00:00Z',
    c=>c.confidence.factors=[],
    c=>c.confidence.rationale=123,
    c=>c.confidence.level=90,
  ]) {
    const c=fixture(); mutate(c)
    assert.equal(titleConfidence(c,now),null)
  }
})
it('renders absent confidence as unscored, never zero or a clean bill of health',()=>{
  const html=confidenceHTML({})
  assert.match(html,/Not scored/)
  assert.match(html,/Missing evidence is not a low likelihood/)
  assert.doesNotMatch(html,/0\/5|0%/)
})
