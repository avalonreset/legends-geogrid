import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { DEFAULT_NAME_REVIEW_SCOPE, reviewBracket, reviewCasesInScope, titleConcernSummary, titleConcernOverviewHTML, caseBriefHTML, highlightedTitleHTML, brandingEvidenceHTML, brandingSourceLabel, validateNameReview, safeSourceURL, reportingReadiness, reviewBrief, importReviewDrafts, sourceReviewHTML, NAME_REVIEW_SCHEMA, NAME_DRAFT_SCHEMA } from '../src/name-review.js'

const model = { name: 'Test study', evidence: { plan_sha256: 'abc123' }, businesses: [{ id: 'cid:123', cid: '123', name: 'Repair Business' }] }
const reviewCase = { id: 'cid:123', cid: '123', cid_verified: true, name: 'Repair Business HVAC', address: 'One Street', status: 'needs_review', signals: [{ code: 'service_words', reason: 'Service terms present; branding may support them.' }], profile: { status: 'complete', name: 'Repair Business HVAC', checked_at: new Date().toISOString() }, website_evidence: { names: [{ name: 'Repair Business', source: 'Header' }] }, limitations: ['Signage not verified'] }
const fixture = () => ({ schema: NAME_REVIEW_SCHEMA, study_plan_sha256: 'abc123', cases: [structuredClone(reviewCase)] })
const draft = { decision: 'concern', observed_name: 'Repair Business HVAC', proposed_name: 'Repair Business', notes: 'Header and dated signage use Repair Business; verify the trade name.', sources: 'https://example.org/signage', counterevidence: 'Reviewed official website trade-name uses; signage remains disputed.', profile_confirmed: true, counterevidence_reviewed: true, reviewed_at: new Date().toISOString() }
describe('Business-name review', () => {
  it('binds evidence to the study and observed identity rather than a similar name', () => {
    assert.equal(validateNameReview(fixture(),model).cases[0].businessId, 'cid:123')
    assert.throws(() => validateNameReview({ ...fixture(), study_plan_sha256: 'other' },model), /different study/)
    assert.throws(() => validateNameReview(fixture(), { ...model, evidence: {} }), /different study/)
    assert.throws(() => validateNameReview({ ...fixture(), cases: [{ ...reviewCase, id: 'unobserved', cid: '999' }] },model), /observed study/)
    assert.throws(() => validateNameReview({ ...fixture(), cases: [{ ...reviewCase, cid: '999' }] },model), /CID/)
    const alternate = validateNameReview({ ...fixture(), cases: [{ ...reviewCase, id: 'provider:123' }] },model)
    assert.equal(alternate.cases[0].businessId, 'cid:123')
  })
  it('rejects ambiguous duplicates and invalid screening states', () => {
    assert.throws(() => validateNameReview({ ...fixture(), cases: [reviewCase,reviewCase] },model), /duplicated/)
    assert.throws(() => validateNameReview({ ...fixture(), cases: [{ ...reviewCase, status: 'violation' }] },model), /Invalid/)
    assert.throws(() => validateNameReview({ ...fixture(), cases: [{ ...reviewCase, status: 'toString' }] },model), /Invalid/)
  })
  it('rejects executable, credential-bearing, and relative evidence links', () => {
    for (const value of ['javascript:alert(1)', 'data:text/html,hello', '/relative', 'https://user:password@example.org', 'file:///private']) assert.equal(safeSourceURL(value), null)
    assert.equal(safeSourceURL('https://example.org/about'), 'https://example.org/about')
  })
  it('does not turn an automated text signal into a report or legal-name finding', () => {
    assert.equal(reportingReadiness(reviewCase, { decision: 'investigate' }).ready, false)
    assert.throws(() => reviewBrief(reviewCase, {}, { reporting: true }), /reviewer/)
    assert.equal(reportingReadiness(reviewCase, { ...draft, sources: 'No sources' }).ready, false)
    assert.equal(reportingReadiness(reviewCase, { ...draft, proposed_name: draft.observed_name }).ready, false)
    assert.equal(reportingReadiness(reviewCase, { ...draft, reviewed_at: '' }).ready, false)
    assert.equal(reportingReadiness(reviewCase, { ...draft, counterevidence_reviewed: false }).ready, false)
    assert.equal(reportingReadiness(reviewCase, { ...draft, profile_confirmed: false }).ready, false)
    assert.equal(reportingReadiness({ ...reviewCase, profile: { ...reviewCase.profile, checked_at: '2000-01-01' } }, draft).ready, false)
    assert.equal(reportingReadiness({ ...reviewCase, cid_verified: false }, draft).ready, false)
    assert.equal(reportingReadiness(reviewCase, draft).ready, true)
    const text = reviewBrief(reviewCase, draft, { reporting: true, study: 'Study' })
    assert.match(text, /No submission has been made/)
    assert.match(text, /legal name or DBA alone is not/)
    assert.match(text, /not a policy verdict/)
    assert.match(text, /Signage not verified/)
  })
  it('exports investigations without presuming a complaint is justified', () => {
    const text = reviewBrief(reviewCase, null)
    assert.match(text, /INVESTIGATION BRIEF/)
    assert.match(text, /Not established/)
    assert.doesNotMatch(text, /business_redressal_form/)
  })
  it('requires fresh profile identity and the unchanged currently observed name', () => {
    for (const checked_at of [undefined, 'bad date', '2000-01-01', new Date(Date.now()+86400000).toISOString()]) {
      assert.equal(reportingReadiness({ ...reviewCase, profile: { ...reviewCase.profile, checked_at } },draft).ready,false)
    }
    assert.equal(reportingReadiness({ ...reviewCase, profile: { ...reviewCase.profile, status:'unavailable' } },draft).ready,false)
    assert.equal(reportingReadiness(reviewCase,{ ...draft,observed_name:'Older profile name' }).ready,false)
  })
  it('escapes analyst findings, counterevidence, labels and malicious source URLs', () => {
    const html = sourceReviewHTML({ finding:'<img src=x onerror=alert(1)>',counterevidence:'<script>bad()</script>',next_action:'Read <branding>',sources:[{url:'javascript:alert(1)',label:'<click>'},{url:'https://example.org',label:'Safe source'}] })
    assert.doesNotMatch(html, /<img|<script|href="javascript:/)
    assert.match(html, /&lt;img/)
    assert.match(html, /&lt;script/)
    assert.match(html, /https:\/\/example.org/)
    assert.match(html, /does not establish a policy violation/)
  })
  it('merges imported notes without overwriting existing reviewer work', () => {
    const imported = { schema: NAME_DRAFT_SCHEMA, study_plan_sha256: 'abc123', drafts: { 'cid:123': draft } }
    const first = importReviewDrafts(imported, 'abc123', {}, ['cid:123'])
    assert.equal(first.added,1)
    assert.equal(first.drafts['cid:123'].profile_confirmed,false)
    assert.equal(first.drafts['cid:123'].counterevidence_reviewed,false)
    assert.equal(reportingReadiness(reviewCase,first.drafts['cid:123']).ready,false)
    const saved = { ...draft, notes: 'Keep this newer local evidence' }
    const merge = importReviewDrafts(imported,'abc123', { 'cid:123': saved },['cid:123'])
    assert.equal(merge.preserved,1)
    assert.equal(merge.drafts['cid:123'].notes,saved.notes)
    assert.throws(() => importReviewDrafts(imported,'other', {},['cid:123']), /match/)
    assert.throws(() => importReviewDrafts(imported,'abc123', {},['elsewhere']), /outside/)
    assert.throws(() => importReviewDrafts({ ...imported, drafts: { 'cid:123': { decision: 'violation' } } },'abc123',{},['cid:123']), /decision/)
  })
})


describe('Recurring leader title investigations', () => {
  it('defaults every count to all recurring profiles regardless of the map keyword', () => {
    const cases = [
      {id:'other',name:'Example HVAC City',address:'Other branch',wins_by_query:{q1:1,q2:4},source_review:{bracket:'possible_concern',suspect_terms:['City']}},
      {id:'local',name:'Supported brand',wins_by_query:{q1:3},source_review:{bracket:'name_supported'}},
      {id:'single',name:'Single winner',wins_by_query:{q1:1},source_review:{bracket:'supported_concern'}},
    ]
    const summary=titleConcernSummary(cases,'q1')
    assert.equal(DEFAULT_NAME_REVIEW_SCOPE,'priority')
    assert.equal(summary.total,2)
    assert.equal(summary.assessed,2)
    assert.equal(summary.concerns.length,1)
    assert.equal(summary.supported,0)
    assert.equal(summary.possible,1)
    assert.equal(summary.namesSupported,1)
    assert.deepEqual(titleConcernSummary(cases,'q2'),summary)
    assert.equal(reviewCasesInScope(cases,'q1').length,summary.total)
    const html=titleConcernOverviewHTML(cases,'q1')
    assert.match(html,/<b>1<\/b><span>Possible naming concerns/)
    assert.match(html,/<b>1<\/b><span>Names supported by branding/)
    assert.match(html,/not confirmed violations/)
    assert.doesNotMatch(html,/Source-supported concerns/)
    const selected=titleConcernSummary(cases,'q1','query')
    assert.equal(selected.total,reviewCasesInScope(cases,'q1','query').length)
    assert.equal(selected.possible,0)
    assert.equal(selected.namesSupported,1)
    const selectedHTML=titleConcernOverviewHTML(cases,'q1','query')
    assert.match(selectedHTML,/<b>0<\/b><span>Possible naming concerns/)
    assert.doesNotMatch(selectedHTML,/All queries|all queries|titles need follow-up/)
  })
  it('keeps unresolved evidence distinct from a pending investigation and supported concern', () => {
    const rows = [
      {wins_by_query:{q1:3},source_review:{bracket:'supported_concern'}},
      {wins_by_query:{q2:4},source_review:{bracket:'insufficient_evidence'}},
      {wins_by_query:{q1:3},status:'branding_consistent'},
    ]
    const summary=titleConcernSummary(rows,'q1')
    assert.deepEqual([summary.total,summary.assessed,summary.supported,summary.unresolved,summary.pending],[3,2,1,1,1])
    const html=titleConcernOverviewHTML(rows,'q1')
    for(const label of ['Source-supported concerns','Unresolved','Awaiting investigation'])assert.ok(html.includes(`<b>1</b><span>${label}`))
  })
  it('keeps historical naming leads in priority scope even when they never win a point', () => {
    const rows = [
      {id:'leader',wins_by_query:{q1:3},source_review:{bracket:'name_supported'}},
      {id:'historic',wins_by_query:{},historical_report:{historical_name:'Earlier business name'},source_review:{bracket:'possible_concern'}},
      {id:'single',wins_by_query:{q2:1}},
    ]
    assert.deepEqual(reviewCasesInScope(rows,'q4').map(c=>c.id),['leader','historic'])
    assert.deepEqual(reviewCasesInScope(rows,'q4','history').map(c=>c.id),['historic'])
    assert.deepEqual(reviewCasesInScope(rows,'q4','recurring').map(c=>c.id),['leader'])
    assert.equal(titleConcernSummary(rows,'q4').possible,1)
    assert.equal(titleConcernSummary(rows,'q4','recurring').possible,0)
  })
  it('highlights exact disputed wording without treating it as a replacement name or executable markup', () => {
    assert.equal(highlightedTitleHTML('Example Heating and AC Repair',['AC Repair']),'Example Heating and <mark>AC Repair</mark>')
    assert.equal(highlightedTitleHTML('Example A+C <script>',['A+C','<script>']),'Example <mark>A+C</mark> <mark>&lt;script&gt;</mark>')
    const html=caseBriefHTML({...reviewCase,source_review:{bracket:'possible_concern',suspect_terms:['HVAC'],finding:'<finding>',next_action:'Find current signage.',counterevidence:'Official footer supports longer name.',sources:[]}})
    assert.match(html,/Google business title/)
    assert.match(html,/Repair Business <mark>HVAC<\/mark>/)
    assert.match(html,/Captured website wording/)
    assert.match(html,/a proposed replacement name/)
    assert.ok(html.indexOf('Next agent action')<html.indexOf('What the sources show'))
    assert.match(html,/Official footer supports longer name/)
    assert.doesNotMatch(html,/<finding>/)
  })
  it('distinguishes extracted metadata and image descriptions from verified real-world branding', () => {
    const html=brandingEvidenceHTML({status:'captured',checked_at:'2026-10-19T03:36:09Z',names:[{name:'Template Brand',source:'og:site_name'}]})
    assert.match(html,/trading name is not verified/)
    assert.match(html,/Website metadata/)
    assert.doesNotMatch(html,/og:site_name/)
    assert.match(html,/Captured .+?\.<\/p><p class="nr-evidence-note">/)
    assert.match(brandingSourceLabel('logo alt text'),/not the inspected image/)
    const unavailable=brandingEvidenceHTML({status:'unavailable',checked_at:'2026-10-19T03:36:09Z',names:[]})
    assert.match(unavailable,/Website could not be retrieved/)
    assert.match(unavailable,/Attempted /)
    assert.doesNotMatch(unavailable,/Captured Oct/)
  })
  it('decodes readable website entities but still escapes injected markup', () => {
    const html=brandingEvidenceHTML({names:[{name:'Example Heating &amp; Air &lt;script&gt; &quot;Brand&quot;',source:'JSON-LD name'}]})
    assert.match(html,/Example Heating &amp; Air &lt;script&gt; &quot;Brand&quot;/)
    assert.doesNotMatch(html,/&amp;amp;|<script>|JSON-LD/)
  })
  it('uses the same selected-query threshold as Local leaders, without a location restriction', () => {
    const rows = [
      {id:'outside',wins_by_query:{q1:3,q2:1},address:'Outside circle'},
      {id:'other-query',wins_by_query:{q1:2,q2:5}},
      {id:'singleton',wins_by_query:{q1:1}},
    ]
    assert.deepEqual(reviewCasesInScope(rows,'q1','query').map(c=>c.id),['outside'])
    assert.deepEqual(reviewCasesInScope(rows,'q2','query').map(c=>c.id),['other-query'])
    assert.equal(reviewCasesInScope(rows,'q1','recurring').length,2)
    assert.equal(reviewCasesInScope(rows,'q1','all').length,3)
  })
  it('never counts automated branding matches as individual investigation', () => {
    assert.equal(reviewBracket({status:'branding_consistent'}),'not_investigated')
    assert.equal(reviewBracket({status:'needs_review',source_review:{bracket:'possible_concern'}}),'possible_concern')
    assert.equal(reviewBracket({status:'needs_review',source_review:{}}),'insufficient_evidence')
  })
  it('retains analyst brackets and exact suspect words', () => {
    const input=fixture()
    input.cases[0].source_review={bracket:'possible_concern',suspect_terms:['AC Repair'],finding:'Branding differs',sources:[]}
    const c=validateNameReview(input,model).cases[0]
    assert.equal(reviewBracket(c),'possible_concern')
    assert.deepEqual(c.source_review.suspect_terms,['AC Repair'])
  })
})
