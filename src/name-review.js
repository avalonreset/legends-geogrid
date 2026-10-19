import { winnerAt } from './leader-colors.js'
import { resolveReviewAttachment } from './review-attachment.js'
import { titleConfidence } from './title-confidence.js'
// Evidence review only: this module never submits edits or complaints to Google.
export const NAME_REVIEW_SCHEMA = 'geogrid-name-review/v1'
export const NAME_DRAFT_SCHEMA = 'geogrid-name-review-drafts/v1'
export const NAME_STATUSES = {
  not_investigated: 'Agent investigation not attached',
  needs_review: 'Needs source review',
  branding_consistent: 'Branding text matches',
  corroborated_discrepancy: 'Source discrepancy',
  no_obvious_signal: 'No obvious text signal',
  unavailable: 'Evidence unavailable',
}
export const REVIEW_BRACKETS = {
  supported_concern: 'Supported naming concern',
  possible_concern: 'Possible concern',
  name_supported: 'Branding supports name',
  insufficient_evidence: 'Insufficient evidence',
  not_investigated: 'Investigation pending',
}
export function reviewBracket(c) {
  const review = c.source_review
  if (!review) return 'not_investigated'
  if (Object.hasOwn(REVIEW_BRACKETS,review.bracket)) return review.bracket
  if (c.status === 'corroborated_discrepancy') return 'supported_concern'
  if (c.status === 'branding_consistent') return 'name_supported'
  return 'insufficient_evidence'
}
export const DEFAULT_NAME_REVIEW_SCOPE = 'priority'
const CASE_PAGE_SIZE = 12
export function reviewCasesInScope(cases, queryId, scope = DEFAULT_NAME_REVIEW_SCOPE) {
  return cases.filter(c => scope === 'all' || (scope === 'history' ? Boolean(c.historical_report) : scope === 'priority'
    ? Boolean(c.historical_report) || Object.values(c.wins_by_query || {}).some(n => n >= 3) : scope === 'recurring'
    ? Object.values(c.wins_by_query || {}).some(n => n >= 3)
    : (c.wins_by_query?.[queryId] || 0) >= 3))
}
export const isTitleConcern = c => ['supported_concern','possible_concern'].includes(reviewBracket(c))
export function titleConcernSummary(cases, queryId, scope = DEFAULT_NAME_REVIEW_SCOPE) {
  const rows = reviewCasesInScope(cases,queryId,scope)
  const concerns = rows.filter(isTitleConcern)
  return {
    total: rows.length,
    assessed: rows.filter(c=>c.source_review).length,
    concerns,
    supported: concerns.filter(c=>reviewBracket(c)==='supported_concern').length,
    possible: concerns.filter(c=>reviewBracket(c)==='possible_concern').length,
    namesSupported: rows.filter(c=>reviewBracket(c)==='name_supported').length,
    unresolved: rows.filter(c=>reviewBracket(c)==='insufficient_evidence').length,
    pending: rows.filter(c=>reviewBracket(c)==='not_investigated').length,
  }
}
export function titleConcernOverviewHTML(cases, queryId, scope = DEFAULT_NAME_REVIEW_SCOPE, filter = 'all') {
  const s = titleConcernSummary(cases,queryId,scope)
  const items = [
    ...(s.supported ? [['supported_concern',s.supported,'Source-supported concerns']] : []),
    ['possible_concern',s.possible,'Possible naming concerns'],
    ['name_supported',s.namesSupported,'Names supported by branding'],
    ['insufficient_evidence',s.unresolved,'Unresolved'],
    ...(s.pending ? [['not_investigated',s.pending,'Awaiting investigation']] : []),
  ]
  return `<div class="nr-findings-summary" aria-label="Findings for the selected scope">${items.map(([value,count,label])=>`<button data-nr-filter="${value}" aria-pressed="${filter===value}"><b>${count}</b><span>${label}</span></button>`).join('')}</div><p class="nr-summary-note">Possible concerns identify conflicting name evidence, not confirmed violations. “Unresolved” means the available evidence cannot settle the name.</p>`
}
const bracketPriority = c => Object.keys(REVIEW_BRACKETS).indexOf(reviewBracket(c))
const decisions = { pending: 'Not reviewed', investigate: 'Gather more evidence', consistent: 'Real-world branding supported', concern: 'Documented naming concern' }
const esc = text => String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
const date = value => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}) : 'Not recorded'
export function safeSourceURL(value) {
  try {
    const u = new URL(value)
    return ['https:', 'http:'].includes(u.protocol) && !u.username && !u.password ? u.href : null
  } catch { return null }
}
const link = (url, label) => safeSourceURL(url) ? `<a href="${esc(safeSourceURL(url))}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>` : `<span>${esc(label)} unavailable</span>`
const str = (value, max = 20000) => typeof value === 'string' ? value.slice(0, max) : ''
const plain = value => value && typeof value === 'object' && !Array.isArray(value)
export function sourceReviewHTML(review, alreadyDisplayed = '') {
  if (!plain(review)) return ''
  return `<section class="nr-next-action"><h3>Next agent action</h3><p>${esc(review.next_action || 'The agent needs to establish the next evidence check.')}</p></section><section class="nr-analyst"><span class="nr-kicker">EVIDENCE REVIEW · ${date(review.checked_at)}</span>${review.finding === alreadyDisplayed ? '' : `<h3>What the sources show</h3><p>${esc(review.finding)}</p>`}<h3>What supports the current name</h3><p>${esc(review.counterevidence || 'No counterevidence recorded. This is a research gap.')}</p><div class="nr-links">${(Array.isArray(review.sources) ? review.sources : []).filter(plain).map(s => link(s.url,s.label || 'Source')).join('')}</div><small>An unresolved discrepancy does not establish a policy violation.</small></section>`
}
export function validateNameReview(input, model) {
  if (!plain(input) || (input.schema ?? input.schema_version) !== NAME_REVIEW_SCHEMA) throw new Error('Unsupported name-review evidence format')
  const fingerprint = model.evidence?.plan_sha256
  if (!fingerprint || input.study_plan_sha256 !== fingerprint) throw new Error('Name review belongs to a different study')
  if (!Array.isArray(input.cases) || input.cases.length > 10000) throw new Error('Invalid case list')
  const seen = new Set(), seenCids = new Set()
  const cases = input.cases.map(c => {
    if (!plain(c) || typeof c.id !== 'string' || !c.id || typeof c.name !== 'string' || seen.has(c.id) || !Object.hasOwn(NAME_STATUSES, c.status)) throw new Error('Invalid or duplicated review case')
    seen.add(c.id)
    const business = model.businesses.find(b => b.id === c.id) ??
      model.businesses.find(b => c.cid && b.cid && String(c.cid) === String(b.cid))
    if (!business) throw new Error('Review case is not part of the observed study')
    if (!c.cid || !business.cid || String(c.cid) !== String(business.cid)) throw new Error('Review profile CID does not match the observed business')
    if (seenCids.has(String(c.cid))) throw new Error('Duplicated review profile CID')
    seenCids.add(String(c.cid))
    const website = plain(c.website_evidence) ? c.website_evidence : {}
    const sourceReview = plain(c.source_review) ? { bracket: str(c.source_review.bracket,100), suspect_terms: Array.isArray(c.source_review.suspect_terms) ? c.source_review.suspect_terms.filter(v=>typeof v==='string').slice(0,30) : [], checked_at: str(c.source_review.checked_at,100), finding: str(c.source_review.finding),
      counterevidence: str(c.source_review.counterevidence), next_action: str(c.source_review.next_action),
      sources: Array.isArray(c.source_review.sources) ? c.source_review.sources.filter(plain).slice(0,100).map(s => ({url:str(s.url,4000),label:str(s.label,500)})) : [] } : null
    const profile = plain(c.profile) ? Object.fromEntries(Object.entries(c.profile).map(([k,v]) => [k, str(v,k === 'name' ? 500 : 2000)])) : {}
    return { ...c, businessId: business.id, cid_verified: true, signals: Array.isArray(c.signals) ? c.signals.filter(plain) : [],
      limitations: Array.isArray(c.limitations) ? c.limitations.filter(s => typeof s === 'string') : [],
      source_review: sourceReview, profile, website_evidence: { ...website, evidence_path: str(website.evidence_path,2000), title: str(website.title,2000), excerpt:str(website.excerpt), names: Array.isArray(website.names) ? website.names.filter(plain).slice(0,100).map(n => ({name:str(n.name,500),source:str(n.source,2000)})) : [] } }
  })
  return { ...input, cases, collection: plain(input.collection) ? input.collection : {}, policy: plain(input.policy) ? input.policy : {} }
}
export function validateDraft(input) {
  if (!plain(input) || !Object.hasOwn(decisions, input.decision)) throw new Error('Invalid reviewer decision')
  return { decision: input.decision, observed_name: str(input.observed_name, 500), proposed_name: str(input.proposed_name, 500),
    notes: str(input.notes), sources: str(input.sources, 10000), counterevidence: str(input.counterevidence), profile_confirmed: false, counterevidence_reviewed: false, updated_at: str(input.updated_at, 100), reviewed_at: str(input.reviewed_at, 100) }
}
export function reportingReadiness(c, draft, now = Date.now()) {
  const age = now - Date.parse(c.profile?.checked_at)
  if (c.profile?.status !== 'complete' || !Number.isFinite(age) || age < -300000 || age > 7*86400000 || !c.cid_verified) return { ready: false, reason: 'A CID-matched complete profile check from the past seven days is required.' }
  if (!draft || draft.decision !== 'concern') return { ready: false, reason: 'A reviewer must explicitly record a documented concern.' }
  if (!draft.profile_confirmed || !draft.counterevidence_reviewed || !draft.counterevidence?.trim()) return { ready: false, reason: 'Recheck the current profile name and record/review counterevidence in this session.' }
  if (draft.observed_name?.trim() !== c.profile.name?.trim()) return { ready: false, reason: 'Observed name differs from the checked profile. Refresh that source before preparing a review draft.' }
  if (!draft.observed_name?.trim() || !draft.proposed_name?.trim() || draft.observed_name.trim() === draft.proposed_name.trim()) return { ready: false, reason: 'Record the observed profile name and a different source-supported real-world name.' }
  if (!draft.notes?.trim()) return { ready: false, reason: 'Explain the discrepancy and the evidence supporting it.' }
  const urls = draft.sources?.split(/\s+/).filter(u => safeSourceURL(u)) || []
  if (!urls.length) return { ready: false, reason: 'Add at least one public supporting source URL.' }
  if (!draft.reviewed_at) return { ready: false, reason: 'Save the reviewed evidence before preparing a reporting brief.' }
  return { ready: true, reason: 'Review draft available. Recheck the live profile immediately before any manual submission; this is not a violation verdict.' }
}
export function reviewBrief(c, draft, { reporting = false, study = '' } = {}) {
  if (reporting && !reportingReadiness(c, draft).ready) throw new Error(reportingReadiness(c, draft).reason)
  return [
    reporting ? 'MANUAL BUSINESS-NAME REVIEW BRIEF' : 'BUSINESS-NAME INVESTIGATION BRIEF',
    `Study: ${study}`, `Profile: ${c.name}`, `Address: ${c.address || 'Not supplied'}`, `CID: ${c.cid || 'Not supplied'}`,
    `Google Maps: ${safeSourceURL(c.map_url || c.profile?.source_url) || 'Unavailable'}`,
    `Website: ${safeSourceURL(c.website) || 'Unavailable'}`,
    `Automated screen: ${NAME_STATUSES[c.automated_status || c.status]}. This is not a policy verdict.`,
    `Profile evidence checked: ${c.profile?.checked_at || 'Not recorded'}`,
    `Website evidence checked: ${c.website_evidence?.checked_at || 'Not recorded'}`,
    `Assessment: ${c.assessment || 'Pending'}`,
    `Text signals: ${c.signals.map(s => s.reason || s.code).join('; ') || 'None recorded'}`,
    `Website names: ${(c.website_evidence?.names || []).map(n => `${n.name} (${n.source})`).join('; ') || 'Unavailable'}`,
    `Reviewer decision: ${decisions[draft?.decision] || decisions.pending}`,
    `Observed name: ${draft?.observed_name || c.profile?.name || c.name}`,
    `Proposed real-world name: ${draft?.proposed_name || 'Not established'}`,
    `Reviewer notes: ${draft?.notes || 'None'}`, `Supporting sources: ${draft?.sources || 'None'}`,
    `Counterevidence: ${draft?.counterevidence || 'Not reviewed'}`,
    ...(c.source_review ? [`Analyst source review (${c.source_review.checked_at || 'Undated'}): ${c.source_review.finding || ''}`, `Analyst counterevidence: ${c.source_review.counterevidence || ''}`, `Next check: ${c.source_review.next_action || ''}`, `Analyst sources: ${(c.source_review.sources || []).map(s => safeSourceURL(s.url)).filter(Boolean).join('\n')}`] : []),
    `Limitations: ${(c.limitations || []).join('; ') || 'Real-world signage and trade-name usage require verification.'}`,
    'Next: independently inspect the profile, website/contact branding, dated storefront or vehicle signage, and relevant public trade-name records. A legal name or DBA alone is not the Google naming test.',
    'Policy: Google requires the name used consistently in the real world. Service words in a genuine brand are not automatically stuffing.',
    'https://support.google.com/business/answer/3038177',
    ...(reporting ? ['Ordinary factual correction: open the profile and use Suggest an edit. Redressal is for supported misleading-information or fraud concerns: https://support.google.com/business/contact/business_redressal_form', 'Recheck the live profile immediately before any submission. No submission has been made. Google determines the outcome; edits or ranking gains are not guaranteed.'] : []),
  ].join('\n\n')
}
export function importReviewDrafts(input, fingerprint, existing = {}, validIds = []) {
  if (!plain(input) || input.schema !== NAME_DRAFT_SCHEMA || input.study_plan_sha256 !== fingerprint || !plain(input.drafts)) throw new Error('Draft file does not match this study')
  const allowed = new Set(validIds), merged = { ...existing }
  let added = 0, preserved = 0
  for (const [id, value] of Object.entries(input.drafts)) {
    if (!allowed.has(id)) throw new Error('Draft contains a profile outside this evidence set')
    const draft = validateDraft(value)
    if (Object.hasOwn(merged, id)) { preserved++; continue }
    Object.defineProperty(merged, id, { value: draft, enumerable: true, writable: true, configurable: true }); added++
  }
  return { drafts: merged, added, preserved }
}
// Preserve legacy draft exports above for existing records; the viewer is read-only.
export function observedReviewScope(model, { includeIds = [] } = {}) {
  const wins = new Map(), byQuery = new Map()
  const included = new Set(includeIds)
  for (const point of model.points) for (const [queryId,observation] of Object.entries(point.observations)) {
    const winner = winnerAt(observation)
    if (winner) {
      wins.set(winner.id, (wins.get(winner.id) || 0) + 1)
      const counts = byQuery.get(winner.id) || {}
      counts[queryId] = (counts[queryId] || 0) + 1
      byQuery.set(winner.id,counts)
    }
  }
  return model.businesses.filter(b => wins.has(b.id) || included.has(b.id)).map(b => ({
    id: b.id, businessId: b.id, cid: b.cid, name: b.name, address: b.address,
    total_wins: wins.get(b.id) || 0, wins_by_query: byQuery.get(b.id) || {}, status: 'not_investigated',
    map_url: b.cid ? `https://www.google.com/maps?cid=${b.cid}` : null,
    profile: {}, website_evidence: {}, signals: [], limitations: [],
    assessment: 'This business ranked first in the saved study. No individual name investigation is attached. This is a research gap, not a clean bill of health.',
  }))
}
export function highlightedTitleHTML(name, terms = []) {
  const words = terms.filter(t=>typeof t==='string' && t.trim()).map(t=>t.trim()).sort((a,b)=>b.length-a.length)
  if (!words.length) return esc(name)
  const pattern = new RegExp(`(${words.map(t=>t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|')})`,'gi')
  return String(name || '').split(pattern).map((part,index)=>index%2?`<mark>${esc(part)}</mark>`:esc(part)).join('')
}
export function brandingSourceLabel(source) {
  const labels = {
    'og:site_name': 'Website metadata',
    'JSON-LD name': 'Website business-name data',
    'JSON-LD alternateName': 'Website alternate-name data',
    'logo alt text': 'Logo image description (text, not the inspected image)',
  }
  return labels[source] || 'Captured website text'
}
const readableWebsiteText = value => String(value || '').replace(/&(amp|quot|apos|lt|gt|#\d+|#x[\da-f]+);/gi,(match,entity)=>{
  const named = {amp:'&',quot:'"',apos:"'",lt:'<',gt:'>'}
  if (named[entity.toLowerCase()]) return named[entity.toLowerCase()]
  const code = entity.toLowerCase().startsWith('#x') ? parseInt(entity.slice(2),16) : Number(entity.slice(1))
  return code>0 && code<=0x10ffff && !(code>=0xd800 && code<=0xdfff) ? String.fromCodePoint(code) : match
})
export function brandingEvidenceHTML(site = {}) {
  const names = site.names || []
  const metadataOnly = names.length && names.every(n=>/^(og:|JSON-LD)/.test(n.source || ''))
  const unavailable = site.status === 'unavailable'
  return `<section><h3>Captured website wording</h3>${metadataOnly ? '<p class="nr-evidence-limit">Metadata only in this extract. The trading name is not verified.</p>' : ''}${names.length ? names.map(n=>`<p><strong>${esc(readableWebsiteText(n.name))}</strong><small>${esc(brandingSourceLabel(n.source))}</small></p>`).join('') : `<p>${unavailable?'Website could not be retrieved.':'No branding text extracted.'} See the individual source review below.</p>`}<p class="nr-source-date">${site.checked_at ? `${unavailable?'Attempted':'Captured'} ${date(site.checked_at)}.` : 'Website check not attached.'}</p><p class="nr-evidence-note">Extracted wording is not verified signage or a proposed replacement name.</p></section>`
}
export function caseBriefHTML(c, now = Date.now()) {
  const site = c.website_evidence || {}, profile = c.profile || {}, terms = c.source_review?.suspect_terms || []
  return `<div class="nr-detail-heading"><span class="nr-status">${esc(REVIEW_BRACKETS[reviewBracket(c)])}</span><h2>${esc(profile.name || c.name)}</h2><p>${esc(c.address || 'Address not supplied')} · ${c.total_wins || 0} first-place observations across the study</p><div class="nr-links">${link(c.map_url || profile.source_url, 'Google profile')}${link(c.website || site.url, 'Business website')}<button data-nr="map">Show on map</button></div></div>
    ${confidenceHTML(c, now)}
    ${historicalCaseHTML(c)}
    <div class="nr-comparison"><section><h3>Google business title</h3><strong>${highlightedTitleHTML(profile.name || c.name,terms)}</strong>${terms.length ? `<p class="nr-disputed"><b>Words to verify:</b> ${terms.map(t=>`“${esc(t)}”`).join(', ')}</p>` : ''}<small>${profile.checked_at ? `Checked ${date(profile.checked_at)}.` : 'Historical scan name; a current profile check is missing.'}</small></section>${brandingEvidenceHTML(site)}</div>
    ${sourceReviewHTML(c.source_review) || `<section class="nr-next-action"><h3>Agent investigation needed</h3><p>${esc(c.assessment || 'Resolve the current profile name and public branding before proposing a correction.')}</p><p>The agent needs to investigate this profile; no conclusion follows from an automated text match.</p></section>`}
    ${c.scan_name && profile.name && c.scan_name !== profile.name ? `<p class="nr-name-change">Name changed since the ranking scan: ${esc(c.scan_name)} → ${esc(profile.name)}</p>` : ''}
    <details><summary>Collection records and limitations</summary><p>Profile CID: ${esc(c.cid)}</p><p>Profile record: <code>${esc(profile.evidence_path || 'Not attached')}</code></p><p>Profile SHA-256: <code>${esc(profile.sha256 || 'Not attached')}</code></p><p>Website record: <code>${esc(site.evidence_path || 'Not attached')}</code></p><p>Website SHA-256: <code>${esc(site.sha256 || 'Not attached')}</code></p><ul>${(c.signals || []).map(s => `<li>${esc(s.reason || s.code)}</li>`).join('')}${(c.limitations || []).map(s => `<li>${esc(s)}</li>`).join('')}</ul></details>`
}
export function confidenceHTML(c, now = Date.now()) {
  const score = titleConfidence(c, now)
  if (!score) return `<section class="nr-confidence" data-level="unrated"><div class="nr-confidence-label">Concern confidence <strong>Not scored</strong></div><p>${c.confidence ? 'A fresh identity-matched profile and complete assessment are needed to use this score.' : 'No individual confidence score is attached. Missing evidence is not a low likelihood of stuffing.'}</p></section>`
  return `<section class="nr-confidence" data-level="${score.tone}"><div class="nr-confidence-label">Concern confidence <strong>${score.level}/5 · ${esc(score.label)}</strong></div><div class="nr-confidence-track" role="meter" aria-label="Evidence supporting a title concern, not violation probability" aria-valuemin="0" aria-valuemax="5" aria-valuenow="${score.level}"><i style="width:${score.level*20}%"></i></div><p>${esc(score.rationale)}</p><details><summary>Why this score?</summary><ul class="nr-confidence-factors">${score.factors.map(f=>`<li><b>${esc(f.label)}</b><span>${esc(f.reason)}</span></li>`).join('')}</ul><p>Analyst judgement on a 0–5 evidence scale, not a percentage chance of a violation or Google action. A higher score does not automatically authorize a report.</p></details></section>`
}
export function historicalCaseHTML(c) {
  const h = c.historical_report
  if (!h) return ''
  return `<section class="nr-history"><span class="nr-kicker">YOUR SEPTEMBER REPORT · ${esc(h.pages || '')}</span><h3>Then → now</h3><p><b>September title:</b> ${esc(h.historical_name)}</p><p>${esc(h.summary)}</p><p>${Number.isFinite(h.distance_miles) ? `${h.distance_miles.toFixed(1)} miles from Alpha · ` : ''}${Number.isFinite(h.returned_observations) ? `${h.returned_observations} returned search observations · ` : ''}${c.total_wins || 0} first-place wins. Inclusion does not require a first-place win.</p><small>The report is a historical lead, not proof of a current violation. Address and duplicate-listing allegations are outside this title review.</small></section>`
}
export function createNameReview({ getModel, getQuery = () => getModel().queries[0]?.id, onMap, onMessage = () => {}, onOpen = () => {}, host = null, onClose = null }) {
  const panel = document.createElement('section')
  panel.id = 'name-review'
  panel.className = host ? 'name-review nr-embedded' : 'name-review'
  panel.hidden = true
  panel.setAttribute('aria-label', 'Keyword stuffing findings');
  (host || document.body).append(panel)
  let scope = DEFAULT_NAME_REVIEW_SCOPE, lastQuery = null
  let evidence = null, cases = [], error = '', selected = null, search = '', filter = 'all', page = 0, loading = false, version = 0
  const refNow = () => Date.parse(evidence?.generated_at) || Date.now()
  const current = () => cases.find(c => c.id === selected)
  const ordered = rows => rows.slice().sort((a,b) => bracketPriority(a)-bracketPriority(b) || (titleConfidence(b, refNow())?.level ?? -1)-(titleConfidence(a, refNow())?.level ?? -1) || (b.total_wins || 0)-(a.total_wins || 0) || a.name.localeCompare(b.name))
  const scoped = () => reviewCasesInScope(cases,getQuery(),scope)
  function render() {
    const now = refNow()
    const inScope = scoped()
    const matchesFilter = c => filter === 'all' || (filter === 'concerns' ? isTitleConcern(c) : reviewBracket(c) === filter)
    const rows = ordered(inScope.filter(c => (!search || `${c.name} ${c.address || ''} ${c.cid || ''}`.toLowerCase().includes(search.toLowerCase())) && matchesFilter(c)))
    page = Math.min(page,Math.max(0,Math.ceil(rows.length/CASE_PAGE_SIZE)-1))
    const visibleRows = rows.slice(page*CASE_PAGE_SIZE,(page+1)*CASE_PAGE_SIZE)
    if (!visibleRows.some(c=>c.id===selected)) selected=visibleRows[0]?.id
    const c = current()
    const summary = titleConcernSummary(cases,getQuery(),scope)
    const queryName = getModel().queries.find(q=>q.id===getQuery())?.name || ''
    const historyCount = cases.filter(c=>c.historical_report).length
    const scopeDescription = scope === 'query' ? `Recurring leaders for “${esc(queryName)}” only.` : scope === 'recurring' ? `Recurring leaders across all ${getModel().queries.length} keywords.` : scope === 'history' ? 'Businesses from your September title report.' : scope === 'priority' ? 'Recurring leaders plus your historical report leads.' : 'All observed winners plus individually investigated leads.'
    panel.innerHTML = `<header class="nr-header"><div><span class="nr-kicker">LEGENDS · AGENT INTELLIGENCE</span><h1>Keyword stuffing</h1></div><button data-nr="close">Back to map</button></header>
      <div class="nr-body"><section class="nr-overview"><p class="nr-intro"><b>${summary.total} business profiles · ${summary.assessed} individually assessed</b> · ${scopeDescription} Names/titles only. Updated ${date(evidence?.generated_at)}.</p>
      ${loading || error || !evidence ? `<p class="nr-load-status" role="status">${esc(loading ? 'Loading the agent’s saved investigation…' : error || 'Individual research is not attached yet. The observed businesses below still show the investigation scope.')}</p>` : ''}
      ${titleConcernOverviewHTML(cases,getQuery(),scope,filter)}
      ${historyCount ? `<div class="nr-history-summary"><span><b>${historyCount} September-report leads matched.</b> First-place wins are not required for a naming investigation.</span><button data-nr="history">Review prior leads</button></div>` : ''}
      <details class="nr-method"><summary>Scope, confidence, and naming rule</summary><p>Recurring means at least three first-place locations in any studied keyword. Historical leads remain included even with no first-place wins. The optional keyword filter narrows every count and list together. Businesses outside the circle remain included if they compete within it. This is a selected investigation, not a count of all violations in the market.</p><p>Confidence measures support for a naming concern: 0 = branding supports the title; 1 = weak; 2 = limited; 3 = moderate; 4 = strong; 5 = very strong. Unscored means evidence is insufficient or stale. These are analyst judgements, not statistical probabilities or guarantees of a Google correction.</p><p>Google uses consistent real-world business names. A DBA or service word alone does not establish compliance or a violation. ${link('https://support.google.com/business/answer/3038177','Google naming policy')}</p><p>The agent owns the investigation. No correction has been submitted by this viewer.</p></details></section>
      <div class="nr-browser"><aside class="nr-cases"><label>Investigation scope<select id="nr-scope"><option value="priority">Recurring leaders + prior report</option><option value="history">September report · matched leads</option><option value="recurring">All keywords · recurring leaders</option><option value="query">Selected keyword only · recurring leaders</option><option value="all">All winners + investigated leads</option></select></label><label>Find a business<input id="nr-search" type="search" value="${esc(search)}" placeholder="Name, address, or profile ID"></label><label>Findings<select id="nr-filter"><option value="all">All profiles · concerns first</option><option value="concerns">All title concerns</option>${Object.entries(REVIEW_BRACKETS).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select></label><p>${rows.length} of ${summary.total} profiles · ${filter==='all'?'concerns first':'filtered findings'}</p><div class="nr-case-list">${visibleRows.map(row=>`<button data-case="${esc(row.id)}" aria-pressed="${selected===row.id}"><strong>${esc(row.profile?.name || row.name)}</strong><span>${esc(row.address || 'Address unavailable')}</span><small>${esc(REVIEW_BRACKETS[reviewBracket(row)])}${titleConfidence(row, now) ? ` · ${titleConfidence(row, now).level}/5` : ''}</small>${row.historical_report ? '<span class="nr-history-tag">September report</span>' : ''}${row.source_review?.suspect_terms?.length ? `<em>Verify: ${row.source_review.suspect_terms.map(t=>`“${esc(t)}”`).join(', ')}</em>` : ''}</button>`).join('') || '<p>No profiles match this filter. This is not a finding that every business name is compliant.</p>'}</div><div class="nr-buttons"><button data-nr="previous" ${page?'':'disabled'}>Previous</button><span>${page+1}/${Math.max(1,Math.ceil(rows.length/CASE_PAGE_SIZE))}</span><button data-nr="next" ${(page+1)*CASE_PAGE_SIZE<rows.length?'':'disabled'}>Next</button></div></aside><article class="nr-case-detail">${c ? caseBriefHTML(c, now) : '<h2>No case selected</h2><p>Choose an observed profile or return to all findings.</p>'}</article></div></div>`
    panel.querySelector('#nr-filter').value=filter
    panel.querySelector('#nr-scope').value=scope
    lastQuery=getQuery()
  }
  function open() { onOpen(); panel.hidden=false; render() }
  function close() { panel.hidden=true }
  function dismiss() { close(); onClose?.() }
  function chooseFilter(value) { filter=value;search='';page=0;selected=ordered(scoped().filter(c=>filter==='all'||(filter==='concerns'?isTitleConcern(c):reviewBracket(c)===filter)))[0]?.id;render() }
  panel.addEventListener('input',event=>{
    if(event.target.id==='nr-search') { search=event.target.value;page=0;const position=event.target.selectionStart;render();const input=panel.querySelector('#nr-search');input.focus();input.setSelectionRange(position,position) }
  })
  panel.addEventListener('change',event=>{if(event.target.id==='nr-filter')chooseFilter(event.target.value);if(event.target.id==='nr-scope'){scope=event.target.value;filter='all';search='';page=0;render()}})
  panel.addEventListener('click',event=>{
    const shortcut=event.target.closest('[data-nr-filter]'), row=event.target.closest('[data-case]')
    if(shortcut){chooseFilter(shortcut.dataset.nrFilter);return}
    if(row){selected=row.dataset.case;render();panel.querySelector('.nr-case-detail')?.scrollIntoView({block:'nearest'});return}
    const action=event.target.closest('[data-nr]')?.dataset.nr
    if(action==='close')dismiss()
    if(action==='history'){scope='history';filter='all';search='';page=0;render()}
    if(action==='map'&&current())onMap(current().businessId)
    if(action==='previous'||action==='next'){page+=action==='next'?1:-1;render()}
  })
  panel.addEventListener('keydown',event=>{if(event.key==='Escape')dismiss()})
  return {
    open,close,
    sync(){if(!panel.hidden && lastQuery!==getQuery()){if(scope==='query'){filter='all';search='';page=0}render()}},
    // Legacy local drafts remain untouched in browser storage. Agents own the case files.
    savePending() {},
    async load(path,{studyURL,fallbackInput=null}={}) {
      const token=++version, study=getModel()
      evidence=null;cases=observedReviewScope(study);error='';loading=true;selected=ordered(cases)[0]?.id;filter='all';page=0
      if(!panel.hidden)render()
      try {
        let input=null
        const resolved=await resolveReviewAttachment({explicit:path,studyURL,model:study,baseURL:location.href})
        if(token!==version)return
        if(resolved){
          const response=await fetch(resolved,{cache:'no-store'})
          if(!response.ok)throw new Error(`Evidence request failed (HTTP ${response.status})`)
          input=await response.json()
          if(token!==version)return
        } else if(fallbackInput && !path && !studyURL) {
          input=fallbackInput
        } else {
          return
        }
        evidence=validateNameReview(input,study)
        const attached=new Map(evidence.cases.map(c=>[c.businessId,c]))
        cases=observedReviewScope(study,{includeIds:[...attached.keys()]}).map(c=>attached.has(c.businessId) ? {...attached.get(c.businessId),wins_by_query:c.wins_by_query,total_wins:c.total_wins} : c)
        selected=ordered(cases)[0]?.id
      } catch(e) { if(token===version)error=`Agent evidence could not load: ${e.message}. Observed leaders remain listed below; they are not cleared of name stuffing.` }
      finally {if(token===version){loading=false;if(!panel.hidden)render()}}
    },
    getState(){return {loaded:Boolean(evidence),cases:cases.length,scope,visibleCases:scoped().length,query:getQuery(),selected,error,open:!panel.hidden,loading}},
  }
}
