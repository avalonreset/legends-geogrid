import { winnerAt, leaderIdentity } from './leader-colors.js'
import { profileColor } from './local-leaders.js'
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

const MILE_KM = 1.609344
const finite = v => typeof v === 'number' && Number.isFinite(v)
const territoryCache = new WeakMap()

function haversineKm(a, b) {
  const rad = Math.PI / 180
  const dLat = (b.lat - a.lat) * rad
  const dLng = (b.lng - a.lng) * rad
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) ** 2
  return 6371.0088 * 2 * Math.asin(Math.sqrt(Math.min(1, h)))
}

function medianNum(values) {
  if (!values.length) return null
  const sorted = [...values].sort((a, b) => a - b)
  const mid = sorted.length >> 1
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
}

const round1 = v => Math.round(v * 10) / 10

// Pure territory metrics for a suspect business (Section 6.4).
// Wording rule: "holds", "overlaps you", "you would inherit". Never "stolen" or "stealing".
export function suspectTerritory(model, suspectId) {
  if (!model || !suspectId) {
    return {
      suspectId,
      strongestQueryId: model?.queries?.[0]?.id || null,
      byQuery: {},
      total: { firstPlaces: 0, topThree: 0, overlap: 0, directDamage: 0, inherit: 0, runnersUp: [], milesFromPrimary: null },
    }
  }
  if (!territoryCache.has(model)) territoryCache.set(model, new Map())
  const bySuspect = territoryCache.get(model)
  if (bySuspect.has(suspectId)) return bySuspect.get(suspectId)

  const target = model.businesses?.find(b => b.id === model.targetId) || null
  const center = (finite(target?.lat) && finite(target?.lng))
    ? { lat: target.lat, lng: target.lng }
    : model.sampling?.center || null
  const businessById = new Map((model.businesses || []).map(b => [b.id, b]))

  const pinMiles = p => {
    if (finite(p.distance)) return p.distance / MILE_KM
    if (center && finite(p.lat) && finite(p.lng)) return haversineKm(center, p) / MILE_KM
    return null
  }

  const byQuery = {}
  const totalRunners = new Map()
  const totalFpMiles = []
  let totalFirstPlaces = 0
  let totalTopThree = 0
  let totalOverlap = 0
  let totalDirectDamage = 0
  let totalInherit = 0
  let strongestQueryId = model.queries?.[0]?.id || null
  let strongestFp = -1
  let strongestTop3 = -1

  for (const q of model.queries || []) {
    let firstPlaces = 0
    let topThree = 0
    let overlap = 0
    let directDamage = 0
    let inherit = 0
    const runners = new Map()
    const fpMiles = []
    const firstPlaceIds = []
    const topThreeIds = []
    const overlapIds = []
    const inheritIds = []

    for (const p of model.points || []) {
      const o = p.observations?.[q.id]
      if (!o || ['pending', 'missing', 'missing_result', 'error', 'provider_error', 'empty_results'].includes(o.status)) continue
      const items = o.items || []
      const sItem = items.find(i => i.id === suspectId)
      const sRank = sItem?.rank ?? null
      const pRank = o.targetRank ?? items.find(i => i.id === model.targetId)?.rank ?? null

      if (sRank !== null && sRank <= 30 && pRank !== null && pRank <= 10 && sRank < pRank) {
        directDamage++
      }
      if (sRank !== null && sRank <= 3) {
        topThree++
        topThreeIds.push(p.id)
        if (pRank !== null && pRank <= 30) {
          overlap++
          overlapIds.push(p.id)
        }
      }
      if (sRank === 1) {
        firstPlaces++
        firstPlaceIds.push(p.id)
        const m = pinMiles(p)
        if (finite(m)) { fpMiles.push(m); totalFpMiles.push(m) }
        if (pRank === 2) {
          inherit++
          inheritIds.push(p.id)
        }
        const runner = items.find(i => i.rank === 2)
        if (runner) {
          const rName = businessById.get(runner.id)?.name || runner.name || runner.id
          const entry = runners.get(runner.id) || { id: runner.id, name: rName, count: 0 }
          entry.count++
          runners.set(runner.id, entry)
          const tEntry = totalRunners.get(runner.id) || { id: runner.id, name: rName, count: 0 }
          tEntry.count++
          totalRunners.set(runner.id, tEntry)
        }
      }
    }

    const runnersUp = [...runners.values()].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
    const milesFromPrimary = fpMiles.length ? {
      min: round1(Math.min(...fpMiles)),
      median: round1(medianNum(fpMiles)),
      max: round1(Math.max(...fpMiles)),
    } : null

    byQuery[q.id] = {
      queryId: q.id,
      queryName: q.name,
      firstPlaces,
      topThree,
      overlap,
      directDamage,
      inherit,
      runnersUp,
      milesFromPrimary,
      firstPlaceIds,
      topThreeIds,
      overlapIds,
      inheritIds,
    }

    totalFirstPlaces += firstPlaces
    totalTopThree += topThree
    totalOverlap += overlap
    totalDirectDamage += directDamage
    totalInherit += inherit

    if (firstPlaces > strongestFp || (firstPlaces === strongestFp && topThree > strongestTop3)) {
      strongestFp = firstPlaces
      strongestTop3 = topThree
      strongestQueryId = q.id
    }
  }

  const total = {
    firstPlaces: totalFirstPlaces,
    topThree: totalTopThree,
    overlap: totalOverlap,
    directDamage: totalDirectDamage,
    inherit: totalInherit,
    runnersUp: [...totalRunners.values()].sort((a, b) => b.count - a.count || a.name.localeCompare(b.name)),
    milesFromPrimary: totalFpMiles.length ? {
      min: round1(Math.min(...totalFpMiles)),
      median: round1(medianNum(totalFpMiles)),
      max: round1(Math.max(...totalFpMiles)),
    } : null,
  }

  const out = { suspectId, strongestQueryId, byQuery, total }
  bySuspect.set(suspectId, out)
  return out
}

export function evidenceState(c) {
  if (c?.profile?.jev_optical?.verdict) return 'signage checked'
  const profileCollected = c?.profile?.status === 'complete'
  const siteCaptured = (c?.website_evidence?.names?.length || 0) > 0 || c?.website_evidence?.status === 'captured'
  const nonOfflineReview = Boolean(c?.source_review && c.source_review.reviewed_by && c.source_review.reviewed_by !== 'GeoGrid Offline Triage' && (c.source_review.sources?.length || 0) > 0)
  if (profileCollected || siteCaptured || nonOfflineReview) return 'sources reviewed'
  if (c?.source_review) return 'lexical screen only'
  return 'not investigated'
}

export function reviewBracket(c) {
  const review = c.source_review
  if (!review) return 'not_investigated'
  if (Object.hasOwn(REVIEW_BRACKETS, review.bracket)) return review.bracket
  if (c.status === 'corroborated_discrepancy') return 'supported_concern'
  if (c.status === 'branding_consistent') return 'name_supported'
  return 'insufficient_evidence'
}

export const DEFAULT_NAME_REVIEW_SCOPE = 'priority'

export function reviewCasesInScope(cases, queryId, scope = DEFAULT_NAME_REVIEW_SCOPE) {
  return cases.filter(c => scope === 'all' || (scope === 'history' ? Boolean(c.historical_report) : scope === 'priority'
    ? Boolean(c.historical_report) || Object.values(c.wins_by_query || {}).some(n => n >= 3) : scope === 'recurring'
    ? Object.values(c.wins_by_query || {}).some(n => n >= 3)
    : (c.wins_by_query?.[queryId] || 0) >= 3))
}

export const isTitleConcern = c => ['supported_concern', 'possible_concern'].includes(reviewBracket(c))

export function titleConcernSummary(cases, queryId, scope = DEFAULT_NAME_REVIEW_SCOPE) {
  const rows = reviewCasesInScope(cases, queryId, scope)
  const concerns = rows.filter(isTitleConcern)
  return {
    total: rows.length,
    assessed: rows.filter(c => c.source_review).length,
    concerns,
    supported: concerns.filter(c => reviewBracket(c) === 'supported_concern').length,
    possible: concerns.filter(c => reviewBracket(c) === 'possible_concern').length,
    namesSupported: rows.filter(c => reviewBracket(c) === 'name_supported').length,
    unresolved: rows.filter(c => reviewBracket(c) === 'insufficient_evidence').length,
    pending: rows.filter(c => reviewBracket(c) === 'not_investigated').length,
  }
}

export function titleConcernOverviewHTML(cases, queryId, scope = DEFAULT_NAME_REVIEW_SCOPE, filter = 'all') {
  const s = titleConcernSummary(cases, queryId, scope)
  const items = [
    ...(s.supported ? [['supported_concern', s.supported, 'Source-supported concerns']] : []),
    ['possible_concern', s.possible, 'Possible naming concerns'],
    ['name_supported', s.namesSupported, 'Names supported by branding'],
    ['insufficient_evidence', s.unresolved, 'Unresolved'],
    ...(s.pending ? [['not_investigated', s.pending, 'Awaiting investigation']] : []),
  ]
  return `<div class="nr-findings-summary" aria-label="Findings for the selected scope">${items.map(([value, count, label]) => `<button data-nr-filter="${value}" aria-pressed="${filter === value}"><b>${count}</b><span>${label}</span></button>`).join('')}</div><p class="nr-summary-note">Possible concerns identify conflicting name evidence, not confirmed violations. "Unresolved" means the available evidence cannot settle the name.</p>`
}

const decisions = { pending: 'Not reviewed', investigate: 'Gather more evidence', consistent: 'Real-world branding supported', concern: 'Documented naming concern' }
const esc = text => String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
const date = value => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'Not recorded'

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
  return `<section class="nr-next-action"><h3>Next agent action</h3><p>${esc(review.next_action || 'The agent needs to establish the next evidence check.')}</p></section><section class="nr-analyst"><span class="nr-kicker">EVIDENCE REVIEW · ${date(review.checked_at)}</span>${review.finding === alreadyDisplayed ? '' : `<h3>What the sources show</h3><p>${esc(review.finding)}</p>`}<h3>What supports the current name</h3><p>${esc(review.counterevidence || 'No counterevidence recorded. This is a research gap.')}</p><div class="nr-links">${(Array.isArray(review.sources) ? review.sources : []).filter(plain).map(s => link(s.url, s.label || 'Source')).join('')}</div><small>An unresolved discrepancy does not establish a policy violation.</small></section>`
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
    const sourceReview = plain(c.source_review) ? {
      bracket: str(c.source_review.bracket, 100),
      suspect_terms: Array.isArray(c.source_review.suspect_terms) ? c.source_review.suspect_terms.filter(v => typeof v === 'string').slice(0, 30) : [],
      checked_at: str(c.source_review.checked_at, 100),
      reviewed_by: str(c.source_review.reviewed_by, 200),
      finding: str(c.source_review.finding),
      counterevidence: str(c.source_review.counterevidence),
      next_action: str(c.source_review.next_action),
      visual_review: str(c.source_review.visual_review),
      sources: Array.isArray(c.source_review.sources) ? c.source_review.sources.filter(plain).slice(0, 100).map(s => ({ url: str(s.url, 4000), label: str(s.label, 500) })) : [],
    } : null
    const profile = plain(c.profile) ? Object.fromEntries(Object.entries(c.profile).filter(([k]) => k !== 'jev_optical').map(([k, v]) => [k, str(v, k === 'name' ? 500 : 2000)])) : {}
    if (plain(c.profile?.jev_optical)) {
      const j = c.profile.jev_optical
      profile.jev_optical = {
        verdict: str(j.verdict, 64),
        best_image: str(j.best_image, 32),
        best_streetview: str(j.best_streetview, 32),
        physical_sign_visible: typeof j.physical_sign_visible === 'number' && Number.isFinite(j.physical_sign_visible) ? j.physical_sign_visible : null,
        suspect_terms_shown: typeof j.suspect_terms_shown === 'number' && Number.isFinite(j.suspect_terms_shown) ? j.suspect_terms_shown : null,
        latency_ms: typeof j.latency_ms === 'number' && Number.isFinite(j.latency_ms) ? j.latency_ms : null,
        ...(typeof j.core_brand === 'string' && j.core_brand.trim() ? { core_brand: str(j.core_brand.trim(), 200) } : {}),
        ...(typeof j.core_brand_shown === 'number' && Number.isFinite(j.core_brand_shown) ? { core_brand_shown: j.core_brand_shown } : {}),
        ...(typeof j.verdict_confidence === 'number' && Number.isFinite(j.verdict_confidence) ? { verdict_confidence: j.verdict_confidence } : {}),
        ...(typeof j.schema === 'string' && j.schema.trim() ? { schema: str(j.schema.trim(), 64) } : {}),
      }
    }
    return {
      ...c,
      businessId: business.id,
      cid_verified: true,
      signals: Array.isArray(c.signals) ? c.signals.filter(plain) : [],
      limitations: Array.isArray(c.limitations) ? c.limitations.filter(s => typeof s === 'string') : [],
      source_review: sourceReview,
      profile,
      website_evidence: {
        ...website,
        evidence_path: str(website.evidence_path, 2000),
        title: str(website.title, 2000),
        excerpt: str(website.excerpt),
        names: Array.isArray(website.names) ? website.names.filter(plain).slice(0, 100).map(n => ({ name: str(n.name, 500), source: str(n.source, 2000) })) : [],
      },
    }
  })
  return { ...input, cases, collection: plain(input.collection) ? input.collection : {}, policy: plain(input.policy) ? input.policy : {} }
}

export function validateDraft(input) {
  if (!plain(input) || !Object.hasOwn(decisions, input.decision)) throw new Error('Invalid reviewer decision')
  return {
    decision: input.decision,
    observed_name: str(input.observed_name, 500),
    proposed_name: str(input.proposed_name, 500),
    notes: str(input.notes),
    sources: str(input.sources, 10000),
    counterevidence: str(input.counterevidence),
    profile_confirmed: false,
    counterevidence_reviewed: false,
    updated_at: str(input.updated_at, 100),
    reviewed_at: str(input.reviewed_at, 100),
  }
}

export function reportingReadiness(c, draft, now = Date.now()) {
  const age = now - Date.parse(c.profile?.checked_at)
  if (c.profile?.status !== 'complete' || !Number.isFinite(age) || age < -300000 || age > 7 * 86400000 || !c.cid_verified) return { ready: false, reason: 'A CID-matched complete profile check from the past seven days is required.' }
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
    `Limitations: ${(c.limitations || []).join('; ') || 'Real-world storefront signage and customer-facing branding require verification.'}`,
    'Next: independently inspect the live profile, storefront or vehicle signage, website branding, and printed menus or stationery.',
    'Policy: Google requires the business name used consistently in the real world on storefront signage, website, and stationery. Service words in a genuine brand are not automatically stuffing.',
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

export function observedReviewScope(model, { includeIds = [] } = {}) {
  const wins = new Map(), byQuery = new Map()
  const included = new Set(includeIds)
  for (const point of model.points) for (const [queryId, observation] of Object.entries(point.observations)) {
    const winner = winnerAt(observation)
    if (winner) {
      wins.set(winner.id, (wins.get(winner.id) || 0) + 1)
      const counts = byQuery.get(winner.id) || {}
      counts[queryId] = (counts[queryId] || 0) + 1
      byQuery.set(winner.id, counts)
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
  const words = terms.filter(t => typeof t === 'string' && t.trim()).map(t => t.trim()).sort((a, b) => b.length - a.length)
  if (!words.length) return esc(name)
  const pattern = new RegExp(`(${words.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi')
  return String(name || '').split(pattern).map((part, index) => index % 2 ? `<mark>${esc(part)}</mark>` : esc(part)).join('')
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

const readableWebsiteText = value => String(value || '').replace(/&(amp|quot|apos|lt|gt|#\d+|#x[\da-f]+);/gi, (match, entity) => {
  const named = { amp: '&', quot: '"', apos: "'", lt: '<', gt: '>' }
  if (named[entity.toLowerCase()]) return named[entity.toLowerCase()]
  const code = entity.toLowerCase().startsWith('#x') ? parseInt(entity.slice(2), 16) : Number(entity.slice(1))
  return code > 0 && code <= 0x10ffff && !(code >= 0xd800 && code <= 0xdfff) ? String.fromCodePoint(code) : match
})

export function brandingEvidenceHTML(site = {}) {
  const names = site.names || []
  const metadataOnly = names.length && names.every(n => /^(og:|JSON-LD)/.test(n.source || ''))
  const unavailable = site.status === 'unavailable'
  return `<section><h3>Captured website wording</h3>${metadataOnly ? '<p class="nr-evidence-limit">Metadata only in this extract. The trading name is not verified.</p>' : ''}${names.length ? names.map(n => `<p><strong>${esc(readableWebsiteText(n.name))}</strong><small>${esc(brandingSourceLabel(n.source))}</small></p>`).join('') : `<p>${unavailable ? 'Website could not be retrieved.' : 'No branding text extracted.'} See the individual source review below.</p>`}<p class="nr-source-date">${site.checked_at ? `${unavailable ? 'Attempted' : 'Captured'} ${date(site.checked_at)}.` : 'Website check not attached.'}</p><p class="nr-evidence-note">Extracted wording is not verified signage or a proposed replacement name.</p></section>`
}

export function safePhotoURL(value) {
  const href = safeSourceURL(value)
  if (!href) return null
  try {
    const host = new URL(href).hostname.toLowerCase()
    if (host.endsWith('googleapis.com') && host.includes('streetviewpixels')) return null
  } catch { return null }
  return href
}

export function visualEvidenceHTML(c) {
  const profile = c.profile || {}, review = c.source_review || {}, jev = plain(profile.jev_optical) ? profile.jev_optical : null
  const photos = [
    ['GBP main photo', safePhotoURL(profile.main_image_url)],
    ['Google Street View', safePhotoURL(profile.streetview_url)],
    ['GBP logo badge', safePhotoURL(profile.logo_url)],
  ].filter(([, url]) => Boolean(url))
  const note = str(review.visual_review, 4000).trim()
  const jevLabels = {
    supports_full_title: 'Supports full title',
    omits_suspect_terms: 'Omits suspect terms',
    obstructed_or_no_sign: 'Obstructed or no sign',
    different_business: 'Different business',
  }
  const coreBrand = str(jev?.core_brand, 200).trim()
  const coreBrandPct = typeof jev?.core_brand_shown === 'number' && Number.isFinite(jev.core_brand_shown) ? `${(jev.core_brand_shown * 100).toFixed(0)}%` : ''
  const coreBrandDetail = coreBrand && coreBrandPct ? ` · core brand "${coreBrand}" ${coreBrandPct}` : coreBrand ? ` · core brand "${coreBrand}"` : coreBrandPct ? ` · core brand ${coreBrandPct}` : ''
  const jevSummary = jev?.verdict ? `Jev 1.14 optical check: ${jevLabels[jev.verdict] || jev.verdict}${jev.best_streetview && jev.best_streetview !== 'none' ? ` · vantage ${jev.best_streetview}` : ''}${typeof jev.physical_sign_visible === 'number' && Number.isFinite(jev.physical_sign_visible) ? ` · outdoor sign ${(jev.physical_sign_visible * 100).toFixed(0)}%` : ''}${coreBrandDetail}${typeof jev.suspect_terms_shown === 'number' && Number.isFinite(jev.suspect_terms_shown) ? ` · suspect terms ${(jev.suspect_terms_shown * 100).toFixed(0)}%` : ''}` : ''
  if (!photos.length && !note && !jevSummary) return ''
  return `<section class="nr-visual"><span class="nr-kicker">STOREFRONT, STREET VIEW &amp; LOGO INSPECTION</span>${jevSummary ? `<p class="nr-jev-badge"><b>${esc(jevSummary)}</b></p>` : ''}${note ? `<p class="nr-visual-note">${esc(note)}</p>` : ''}${photos.length ? `<div class="nr-visual-grid">${photos.map(([label, url]) => `<a class="nr-visual-card" href="${esc(url)}" target="_blank" rel="noopener noreferrer" data-nr-photo="${esc(url)}" data-nr-label="${esc(label)}"><img src="${esc(url)}" alt="${esc(label)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.closest('.nr-visual-card')?.remove()"><span>${esc(label)}</span></a>`).join('')}</div>` : ''}</section>`
}

export function caseBriefHTML(c, now = Date.now()) {
  const site = c.website_evidence || {}, profile = c.profile || {}, terms = c.source_review?.suspect_terms || []
  return `<div class="nr-detail-heading"><span class="nr-status">${esc(REVIEW_BRACKETS[reviewBracket(c)])}</span><h2>${esc(profile.name || c.name)}</h2><p>${esc(c.address || 'Address not supplied')} · ${c.total_wins || 0} first-place observations across the study</p><div class="nr-links">${link(c.map_url || profile.source_url, 'Google profile')}${link(c.website || site.url, 'Business website')}<button data-nr="map">Show on map</button></div></div>
    ${confidenceHTML(c, now)}
    ${historicalCaseHTML(c)}
    <div class="nr-comparison"><section><h3>Google business title</h3><strong>${highlightedTitleHTML(profile.name || c.name, terms)}</strong>${terms.length ? `<p class="nr-disputed"><b>Words to verify:</b> ${terms.map(t => `"${esc(t)}"`).join(', ')}</p>` : ''}<small>${profile.checked_at ? `Checked ${date(profile.checked_at)}.` : 'Historical scan name; a current profile check is missing.'}</small></section>${brandingEvidenceHTML(site)}</div>
    ${visualEvidenceHTML(c)}
    ${sourceReviewHTML(c.source_review) || `<section class="nr-next-action"><h3>Agent investigation needed</h3><p>${esc(c.assessment || 'Resolve the current profile name and public branding before proposing a correction.')}</p><p>The agent needs to investigate this profile; no conclusion follows from an automated text match.</p></section>`}
    ${c.scan_name && profile.name && c.scan_name !== profile.name ? `<p class="nr-name-change">Name changed since the ranking scan: ${esc(c.scan_name)} -> ${esc(profile.name)}</p>` : ''}
    <details><summary>Collection records and limitations</summary><p>Profile CID: ${esc(c.cid)}</p><p>Profile record: <code>${esc(profile.evidence_path || 'Not attached')}</code></p><p>Profile SHA-256: <code>${esc(profile.sha256 || 'Not attached')}</code></p><p>Website record: <code>${esc(site.evidence_path || 'Not attached')}</code></p><p>Website SHA-256: <code>${esc(site.sha256 || 'Not attached')}</code></p><ul>${(c.signals || []).map(s => `<li>${esc(s.reason || s.code)}</li>`).join('')}${(c.limitations || []).map(s => `<li>${esc(s)}</li>`).join('')}</ul></details>`
}

// Preserved for legacy unit test compatibility (tests/title-confidence.test.js).
// The Inspector UI uses confidencePipsHTML, which omits unscored confidence completely (zero "Not scored" nodes).
export function confidenceHTML(c, now = Date.now()) {
  const score = titleConfidence(c, now)
  if (!score) return `<section class="nr-confidence" data-level="unrated"><div class="nr-confidence-label">Concern confidence <strong>Not scored</strong></div><p>${c.confidence ? 'A fresh identity-matched profile and complete assessment are needed to use this score.' : 'No individual confidence score is attached. Missing evidence is not a low likelihood of stuffing.'}</p></section>`
  return `<section class="nr-confidence" data-level="${score.tone}"><div class="nr-confidence-label">Concern confidence <strong>${score.level}/5 · ${esc(score.label)}</strong></div><div class="nr-confidence-track" role="meter" aria-label="Evidence supporting a title concern, not violation probability" aria-valuemin="0" aria-valuemax="5" aria-valuenow="${score.level}"><i style="width:${score.level * 20}%"></i></div><p>${esc(score.rationale)}</p><details><summary>Why this score?</summary><ul class="nr-confidence-factors">${score.factors.map(f => `<li><b>${esc(f.label)}</b><span>${esc(f.reason)}</span></li>`).join('')}</ul><p>Analyst judgement on a 0-5 evidence scale, not a percentage chance of a violation or Google action. A higher score does not automatically authorize a report.</p></details></section>`
}

export function historicalCaseHTML(c) {
  const h = c.historical_report
  if (!h) return ''
  return `<section class="nr-history"><span class="nr-kicker">HISTORICAL REPORT · ${esc(h.pages || '')}</span><h3>Then -> now</h3><p><b>Prior title:</b> ${esc(h.historical_name)}</p><p>${esc(h.summary)}</p><p>${Number.isFinite(h.distance_miles) ? `${h.distance_miles.toFixed(1)} miles from base · ` : ''}${Number.isFinite(h.returned_observations) ? `${h.returned_observations} returned search observations · ` : ''}${c.total_wins || 0} first-place wins. Inclusion does not require a first-place win.</p><small>The report is a historical lead, not proof of a current violation. Address and duplicate-listing allegations are outside this title review.</small></section>`
}

function confidencePipsHTML(c, now) {
  const score = titleConfidence(c, now)
  if (!score) return ''
  const pips = Array.from({ length: 5 }, (_, i) => `<i class="nr-pip${i < score.level ? ' filled' : ''}"></i>`).join('')
  return `<div class="nr-pips-row" title="${esc(score.rationale || '')}"><span class="nr-pips" aria-label="Confidence ${score.level} of 5">${pips}</span><span>${score.level}/5 ${esc(score.label.toLowerCase())}</span></div>`
}

function titleWebsiteDiffHTML(title, siteNames) {
  const siteTokens = new Set()
  for (const entry of siteNames) {
    for (const tok of readableWebsiteText(entry.name).toLowerCase().split(/[^a-z0-9]+/).filter(Boolean)) {
      siteTokens.add(tok)
    }
  }
  return String(title || '').split(/([A-Za-z0-9]+)/).map(part => {
    if (!/^[A-Za-z0-9]+$/.test(part)) return esc(part)
    return siteTokens.has(part.toLowerCase()) ? esc(part) : `<mark>${esc(part)}</mark>`
  }).join('')
}

function isOfflineTriageCounterevidence(c) {
  const rev = c.source_review
  if (!rev) return true
  if (rev.reviewed_by === 'GeoGrid Offline Triage') return true
  const text = (rev.counterevidence || '').trim()
  if (!text) return true
  return /offline deterministic screen|concise title structure without obvious separator stuffing|still requires live profile and signage check|some legitimate brands include/i.test(text)
}

function inspectorSignageHTML(c) {
  const profile = c.profile || {}, review = c.source_review || {}, jev = plain(profile.jev_optical) ? profile.jev_optical : null
  const visualNote = str(review.visual_review, 1000).trim()
  const photos = [
    ['GBP main', safePhotoURL(profile.main_image_url)],
    ['Street View', safePhotoURL(profile.streetview_url)],
    ['Logo', safePhotoURL(profile.logo_url)],
  ].filter(([, url]) => Boolean(url))

  if (!jev?.verdict && !photos.length && !visualNote) {
    const hasWebsite = Boolean((c.website_evidence?.names || []).length)
    if (!hasWebsite && !c.source_review) {
      return `<section class="nr-insp-section nr-uninspected-callout">
        <div class="eyebrow">EVIDENCE NOT YET COLLECTED</div>
        <p class="nr-visual-note">No live profile photos, website branding, or storefront check is attached for this business yet. Click <strong>Copy investigation brief</strong> below to ask your agent to run a live profile, website, and visual review pass, or inspect directly via Google profile and Street View.</p>
      </section>`
    }
    return `<div class="nr-status-row"><span>Signage not inspected</span><small>No storefront photos attached</small></div>`
  }

  const verdictWords = {
    omits_suspect_terms: 'Sign omits the flagged words',
    supports_full_title: 'Sign shows the full title',
    obstructed_or_no_sign: 'No readable sign',
    different_business: 'Different business on the sign',
  }
  const verdictText = jev?.verdict
    ? (verdictWords[jev.verdict] || jev.verdict)
    : (visualNote ? 'Signage reviewed visually' : 'Signage photos attached')
  return `<section class="nr-insp-section">
    <div class="eyebrow">SIGNAGE VERDICT</div>
    <p class="nr-signage-verdict">${esc(verdictText)}</p>
    ${photos.length ? `<div class="nr-photo-strip">${photos.map(([label, url]) => `<a class="nr-photo-thumb" href="${esc(url)}" target="_blank" rel="noopener noreferrer" data-nr-photo="${esc(url)}" data-nr-label="${esc(label)}"><img src="${esc(url)}" alt="${esc(label)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.closest('.nr-photo-thumb')?.remove()"><span>${esc(label)}</span></a>`).join('')}</div>` : ''}
    ${visualNote ? `<p class="nr-visual-note">${esc(visualNote)}</p>` : ''}
  </section>`
}

function inspectorWebsiteDiffHTML(c) {
  const site = c.website_evidence || {}
  const names = site.names || []
  const title = c.profile?.name || c.name
  if (!names.length) {
    return `<div class="nr-status-row"><span>Website not captured</span><small>${site.status === 'unavailable' ? 'retrieval failed' : 'not collected'}</small></div>`
  }
  return `<section class="nr-insp-section">
    <div class="eyebrow">TITLE AGAINST WEBSITE</div>
    <table class="nr-diff-table">
      <tbody>
        <tr><th>Google title</th><td>${titleWebsiteDiffHTML(title, names)}</td></tr>
        <tr><th>Website names</th><td>${names.map(n => `<div><strong>${esc(readableWebsiteText(n.name))}</strong> <small>${esc(brandingSourceLabel(n.source))}</small></div>`).join('')}</td></tr>
      </tbody>
    </table>
  </section>`
}

function inspectorMethodHTML() {
  return `<div class="nr-insp-head">
      <div><span class="eyebrow">METHOD &amp; POLICY</span><h2>Scope, confidence and naming rule</h2></div>
      <button type="button" class="nr-insp-close" data-nr-close-inspector aria-label="Close method panel">×</button>
    </div>
    <div class="nr-insp-body">
      <section class="nr-insp-section">
        <p>Recurring leaders hold at least three first-place locations in any studied keyword. Historical leads remain included even with no first-place wins. Businesses outside the study circle remain included if they win inside it.</p>
        <p>Evidence-state chips distinguish signage-checked profiles, source-reviewed profiles, lexical screens only, and uninvestigated profiles. A lexical screen is a research prompt, not a finding.</p>
        <p>Confidence (0 to 5) appears only when an individual fresh identity-matched assessment is attached. Unscored cases show no confidence score. These are analyst judgements, not violation probabilities.</p>
        <p>Google uses the business name displayed consistently in the real world on storefront signage, website, and stationery. Service words inside a genuine real-world brand are not automatically stuffing. ${link('https://support.google.com/business/answer/3038177', 'Google naming policy')}</p>
        <p>This viewer is read-only and submits nothing to Google.</p>
      </section>
    </div>`
}

export function createNameReview({
  getModel,
  getQuery = () => getModel().queries[0]?.id,
  onSelectQuery = null,
  onSelectCase = null,
  onFilterChange = null,
  onMessage = () => {},
  onOpen = () => {},
  onClose = null,
  inspectorHost = null,
  lightboxHost = null,
}) {
  let baseScope = 'priority' // 'priority' (Recurring leaders) | 'all' (All winners) | 'history' (Prior report)
  let thisKeywordOnly = false
  let evidence = null
  let cases = []
  let error = ''
  let selected = null
  let search = ''
  let filter = 'all'
  let loading = false
  let version = 0
  let openFlag = false
  let showingMethod = false
  let sheetCollapsed = false
  let pointOverrideHTML = null
  let lastQuery = null

  const refNow = () => Date.parse(evidence?.generated_at) || Date.now()
  const effectiveScope = () => thisKeywordOnly ? 'query' : baseScope
  const current = () => cases.find(c => c.id === selected) || null

  const territoryOf = c => suspectTerritory(getModel(), c.businessId || c.id)

  const ordered = rows => rows.slice().sort((a, b) => {
    const ta = territoryOf(a).total
    const tb = territoryOf(b).total
    return (tb.directDamage - ta.directDamage) ||
      (tb.firstPlaces - ta.firstPlaces) ||
      a.name.localeCompare(b.name)
  })

  const scoped = () => reviewCasesInScope(cases, getQuery(), effectiveScope())

  const filteredRows = () => {
    const inScope = scoped()
    const needle = search.trim().toLowerCase()
    const matchesFilter = c => filter === 'all' || (filter === 'concerns' ? isTitleConcern(c) : reviewBracket(c) === filter)
    return ordered(inScope.filter(c => (!needle || `${c.name} ${c.address || ''} ${c.cid || ''}`.toLowerCase().includes(needle)) && matchesFilter(c)))
  }

  function ensureLightboxEl() {
    const parent = lightboxHost || inspectorHost?.parentElement || document.body
    let box = parent.querySelector('#nr-lightbox')
    if (!box) {
      box = document.createElement('div')
      box.id = 'nr-lightbox'
      box.className = 'nr-lightbox'
      box.hidden = true
      box.setAttribute('role', 'dialog')
      box.setAttribute('aria-modal', 'true')
      box.setAttribute('aria-label', 'Inspection photo viewer')
      box.addEventListener('click', e => {
        if (e.target === box || e.target.closest('[data-nr-lightbox="close"]')) closeLightbox()
      })
      parent.append(box)
    }
    return box
  }

  function openLightbox(url, label) {
    if (!safeSourceURL(url)) return
    const box = ensureLightboxEl()
    const c = current()
    const title = c?.profile?.name || c?.name || 'Profile photo'
    box.innerHTML = `<div class="nr-lightbox-card"><header class="nr-lightbox-header"><div><span class="nr-kicker">${esc(label || 'INSPECTION PHOTO')}</span><h3>${esc(title)}</h3></div><div class="nr-lightbox-actions"><a href="${esc(safeSourceURL(url))}" target="_blank" rel="noopener noreferrer">Open original ↗</a><button type="button" data-nr-lightbox="close">Close (Esc)</button></div></header><div class="nr-lightbox-stage"><img src="${esc(safeSourceURL(url))}" alt="${esc(label || title)}" referrerpolicy="no-referrer"></div><p class="nr-lightbox-hint">Click anywhere outside the image or press Esc to return to the inspector.</p></div>`
    box.hidden = false
    box.querySelector('[data-nr-lightbox="close"]')?.focus()
  }

  function closeLightbox() {
    const parent = lightboxHost || inspectorHost?.parentElement || document.body
    const box = parent?.querySelector('#nr-lightbox')
    if (box && !box.hidden) { box.hidden = true; box.innerHTML = ''; return true }
    return false
  }

  function renderRailHTML() {
    const model = getModel()
    const qId = getQuery()
    const scope = effectiveScope()
    const summary = titleConcernSummary(cases, qId, scope)
    const rows = filteredRows()
    const historyCount = cases.filter(c => c.historical_report).length
    const identities = leaderIdentity(model).identities
    const concernCount = summary.supported + summary.possible

    const filterButtons = [
      ...(summary.supported > 0 ? [['supported_concern', `Supported ${summary.supported}`]] : []),
      ['concerns', `Concerns ${concernCount}`],
      ['insufficient_evidence', `Unresolved ${summary.unresolved}`],
      ['not_investigated', `Pending ${summary.pending}`],
      ['all', `All ${summary.total}`],
    ]

    const scopeButtons = [
      ['priority', 'Recurring leaders'],
      ['all', 'All winners'],
      ...(historyCount > 0 ? [['history', 'Prior report']] : []),
    ]

    const rowsHTML = rows.map(row => {
      const bizId = row.businessId || row.id
      const badge = identities.get(bizId)?.badge || 'L?'
      const color = profileColor(model, bizId)
      const terr = territoryOf(row)
      const qTerr = thisKeywordOnly ? terr.byQuery[qId] : terr.total
      const fp = qTerr?.firstPlaces ?? 0
      const ov = qTerr?.overlap ?? 0
      const dmg = qTerr?.directDamage ?? 0
      const stateChip = evidenceState(row)
      const terms = row.source_review?.suspect_terms || []
      const title = row.profile?.name || row.name
      const isSelected = selected === row.id
      const terrLine = dmg > 0
        ? `${fp} first places · overlaps you at ${ov} · above you at ${dmg}`
        : `${fp} first places · overlaps you at ${ov}`
      return `<button type="button" class="nr-rail-row${isSelected ? ' selected' : ''}" data-nr-case="${esc(row.id)}" aria-pressed="${isSelected}">
        <div class="nr-rail-row-top">
          <span class="nr-l-chip" style="--leader-color:${esc(color)}">${esc(badge)}</span>
          <strong class="nr-rail-title">${highlightedTitleHTML(title, terms)}</strong>
        </div>
        <div class="nr-rail-territory">${esc(terrLine)}</div>
        <div class="nr-rail-state"><span class="nr-state-chip nr-state-${stateChip.replace(/\s+/g, '-')}">${esc(stateChip)}</span></div>
      </button>`
    }).join('') || '<p class="list-caption">No profiles match this filter. This is not a finding that every business name is compliant.</p>'

    return `<div class="nr-rail">
      <div class="nr-rail-head">
        <div class="nr-rail-title-bar">
          <span class="eyebrow">KEYWORD STUFFING</span>
          <button type="button" class="nr-help-btn" data-nr-method aria-label="Scope, confidence and naming rule" aria-pressed="${showingMethod}" title="Scope, confidence and naming rule">?</button>
        </div>
        <p class="nr-rail-summary"><b>${concernCount}</b> possible concerns in <b>${summary.total}</b> profiles</p>
        ${loading || error || !evidence ? `<p class="nr-rail-status" role="status">${esc(loading ? 'Loading saved investigation...' : error || 'Individual research not attached. Observed leaders remain listed below.')}</p>` : ''}
        <div class="nr-seg-group nr-filter-seg" role="group" aria-label="Findings filter">${filterButtons.map(([val, label]) =>
          `<button type="button" data-nr-filter="${val}" aria-pressed="${filter === val}">${esc(label)}</button>`
        ).join('')}</div>
        <div class="nr-scope-row">
          <div class="nr-seg-group nr-scope-seg" role="group" aria-label="Investigation scope">${scopeButtons.map(([val, label]) =>
            `<button type="button" data-nr-scope="${val}" aria-pressed="${baseScope === val && !thisKeywordOnly}">${esc(label)}</button>`
          ).join('')}</div>
          <button type="button" class="nr-keyword-chip" data-nr-this-keyword aria-pressed="${thisKeywordOnly}" title="Filter counts and rows to the selected map keyword">This keyword</button>
        </div>
        <input id="nr-search" class="nr-search-input" type="search" value="${esc(search)}" placeholder="Find a business" autocomplete="off" aria-label="Find a business">
      </div>
      <div class="nr-rail-list" role="list">${rowsHTML}</div>
    </div>`
  }

  function renderInspector() {
    if (!inspectorHost) return
    const isVisible = openFlag && Boolean(selected || showingMethod || pointOverrideHTML)
    inspectorHost.hidden = !isVisible
    inspectorHost.classList.toggle('nr-sheet-collapsed', sheetCollapsed)
    if (!isVisible) {
      inspectorHost.innerHTML = ''
      return
    }

    if (pointOverrideHTML) {
      inspectorHost.innerHTML = `<div class="nr-insp-head">
          <button type="button" class="nr-back-case" data-nr-back-case>← Back to case</button>
          <button type="button" class="nr-insp-close" data-nr-close-inspector aria-label="Close inspector">×</button>
        </div>
        <div class="nr-insp-body nr-point-override">${pointOverrideHTML}</div>`
      return
    }

    if (showingMethod) {
      inspectorHost.innerHTML = inspectorMethodHTML()
      return
    }

    const c = current()
    if (!c) { inspectorHost.hidden = true; inspectorHost.innerHTML = ''; return }

    const model = getModel()
    const qId = getQuery()
    const now = refNow()
    const title = c.profile?.name || c.name
    const terms = c.source_review?.suspect_terms || []
    const stateChip = evidenceState(c)
    const bracketLabel = REVIEW_BRACKETS[reviewBracket(c)]
    const terr = territoryOf(c)
    const qTerr = terr.byQuery[qId] || terr.total
    const maxQueryFp = Math.max(1, ...model.queries.map(q => terr.byQuery[q.id]?.firstPlaces || 0))
    const activeFp = qTerr.firstPlaces
    const activeOverlap = qTerr.overlap
    const activeInherit = qTerr.inherit
    const activeDamage = qTerr.directDamage
    const miles = qTerr.milesFromPrimary || terr.total.milesFromPrimary
    const runners = qTerr.runnersUp || []

    let honestTerritoryNote = ''
    if (activeDamage === 0 && activeFp > 0) {
      const distPart = miles ? ` Its footprint is ${miles.min.toFixed(1)} to ${miles.max.toFixed(1)} miles from your base.` : ''
      const runnerPart = runners.length
        ? ` If this title changed, first-place points would pass mainly to ${runners.slice(0, 3).map(r => `${r.name} (${r.count})`).join(', ')}.`
        : ''
      honestTerritoryNote = `This profile does not currently sit above you.${distPart}${runnerPart}`
    } else if (activeDamage > 0) {
      honestTerritoryNote = `This profile ranks above you at ${activeDamage} ${activeDamage === 1 ? 'point' : 'points'} where you are in the top 10, and overlaps your top-30 reach at ${activeOverlap} ${activeOverlap === 1 ? 'point' : 'points'}.`
    } else if (activeFp === 0) {
      honestTerritoryNote = `Zero first-place observations on ${model.queries.find(q => q.id === qId)?.name || 'this query'} (${terr.total.firstPlaces} across all studied queries).`
    }

    const counterHTML = isOfflineTriageCounterevidence(c)
      ? `<p class="nr-muted-line">No counterevidence collected yet. That is a research gap, not a finding.</p>`
      : `<p class="nr-counter-text">${esc(c.source_review.counterevidence)}</p>`

    const profileUrl = safeSourceURL(c.map_url || c.profile?.source_url)
    const websiteUrl = safeSourceURL(c.website || c.website_evidence?.url)
    const bizRec = model.businesses.find(b => b.id === (c.businessId || c.id))
    const lat = finite(c.location?.lat) ? c.location.lat : bizRec?.lat
    const lng = finite(c.location?.lng) ? c.location.lng : bizRec?.lng
    const streetViewUrl = (finite(lat) && finite(lng))
      ? `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat.toFixed(6)},${lng.toFixed(6)}`
      : null
    const site = c.website_evidence || {}
    const profile = c.profile || {}

    inspectorHost.innerHTML = `<div class="nr-sheet-bar">
        <button type="button" class="nr-sheet-toggle" data-nr-toggle-sheet aria-expanded="${!sheetCollapsed}">
          <span class="nr-sheet-handle" aria-hidden="true"></span>
          <span>${esc(title)}</span>
        </button>
        <button type="button" class="nr-insp-close" data-nr-close-inspector aria-label="Close inspector">×</button>
      </div>
      <div class="nr-insp-head">
        <div class="nr-insp-title-block">
          <div class="nr-insp-meta-row">
            <span class="nr-state-chip nr-state-${stateChip.replace(/\s+/g, '-')}">${esc(stateChip)}</span>
            <span class="nr-bracket-label">${esc(bracketLabel)}</span>
          </div>
          <h2>${highlightedTitleHTML(title, terms)}</h2>
          <p class="nr-insp-addr">${esc(c.address || 'Address not supplied')}</p>
          ${confidencePipsHTML(c, now)}
        </div>
        <button type="button" class="nr-insp-close" data-nr-close-inspector aria-label="Close inspector">×</button>
      </div>
      <div class="nr-insp-body">
        <section class="nr-insp-section nr-territory-section">
          <div class="nr-territory-strip">
            <div><span class="nr-terr-label">First places</span><strong>${activeFp}</strong></div>
            <div><span class="nr-terr-label">Overlaps you</span><strong>${activeOverlap}</strong></div>
            <div><span class="nr-terr-label">You would inherit</span><strong>${activeInherit}</strong></div>
          </div>
          <div class="nr-query-bars">${model.queries.map(q => {
            const qfp = terr.byQuery[q.id]?.firstPlaces || 0
            const pct = Math.round((qfp / maxQueryFp) * 100)
            return `<button type="button" class="nr-qbar-row${q.id === qId ? ' active' : ''}" data-nr-switch-query="${esc(q.id)}" aria-pressed="${q.id === qId}">
              <span class="nr-qbar-name">${esc(q.name)}</span>
              <span class="nr-qbar-track"><i style="width:${pct}%"></i></span>
              <span class="nr-qbar-val">${qfp}</span>
            </button>`
          }).join('')}</div>
          ${honestTerritoryNote ? `<p class="nr-terr-note">${esc(honestTerritoryNote)}</p>` : ''}
          <p class="nr-terr-caption">Counts are from this snapshot. Inheriting a point assumes nothing else changes.</p>
        </section>
        ${historicalCaseHTML(c)}
        ${inspectorSignageHTML(c)}
        ${inspectorWebsiteDiffHTML(c)}
        <section class="nr-insp-section">
          <div class="eyebrow">WHAT SUPPORTS THE CURRENT NAME</div>
          ${counterHTML}
        </section>
        <p class="nr-boundary-line">Google checks the real-world name shown consistently on storefront signage, website, and stationery. Service words inside a real brand are not automatically stuffing. This tool submits nothing.</p>
        <details class="nr-records">
          <summary>Records</summary>
          <p>Profile CID: <code>${esc(c.cid || 'n/a')}</code></p>
          <p>Profile record: <code>${esc(profile.evidence_path || 'Not attached')}</code></p>
          <p>Profile SHA-256: <code>${esc(profile.sha256 || 'Not attached')}</code></p>
          <p>Website record: <code>${esc(site.evidence_path || 'Not attached')}</code></p>
          <p>Website SHA-256: <code>${esc(site.sha256 || 'Not attached')}</code></p>
          ${(c.signals || []).length ? `<ul>${c.signals.map(s => `<li>${esc(s.reason || s.code)}</li>`).join('')}</ul>` : ''}
          ${(c.limitations || []).length ? `<ul>${c.limitations.map(s => `<li>${esc(s)}</li>`).join('')}</ul>` : ''}
        </details>
      </div>
      <div class="nr-insp-actions">
        <button type="button" data-nr-copy-brief>Copy investigation brief</button>
        ${profileUrl ? `<a href="${esc(profileUrl)}" target="_blank" rel="noopener noreferrer">Open Google profile ↗</a>` : ''}
        ${streetViewUrl ? `<a href="${esc(streetViewUrl)}" target="_blank" rel="noopener noreferrer">Street View ↗</a>` : ''}
        ${websiteUrl ? `<a href="${esc(websiteUrl)}" target="_blank" rel="noopener noreferrer">Open website ↗</a>` : ''}
      </div>`
  }

  function selectCaseById(caseOrBizId, { autoSwitchQuery = true, fromRail = false } = {}) {
    const match = cases.find(c => c.id === caseOrBizId || c.businessId === caseOrBizId)
    if (!match) return false
    selected = match.id
    showingMethod = false
    pointOverrideHTML = null
    sheetCollapsed = false

    const model = getModel()
    const terr = territoryOf(match)
    const curQ = getQuery()
    const curFp = terr.byQuery[curQ]?.firstPlaces || 0
    if (autoSwitchQuery && curFp === 0 && terr.strongestQueryId && terr.strongestQueryId !== curQ) {
      const strongFp = terr.byQuery[terr.strongestQueryId]?.firstPlaces || 0
      if (strongFp > 0) {
        const strongName = model.queries.find(q => q.id === terr.strongestQueryId)?.name || terr.strongestQueryId
        onSelectQuery?.(terr.strongestQueryId)
        onMessage(`Showing ${strongName}: ${strongFp} of this profile's ${terr.total.firstPlaces} first places`)
      }
    }
    renderInspector()
    onSelectCase?.(match, terr, { fromRail })
    return true
  }

  function clearSelection() {
    selected = null
    showingMethod = false
    pointOverrideHTML = null
    renderInspector()
    onSelectCase?.(null, null)
  }

  function handleRailClick(event) {
    const methodBtn = event.target.closest('[data-nr-method]')
    if (methodBtn) {
      showingMethod = !showingMethod
      pointOverrideHTML = null
      if (showingMethod) selected = null
      renderInspector()
      onSelectCase?.(null, null)
      return true
    }
    const filterBtn = event.target.closest('[data-nr-filter]')
    if (filterBtn) {
      const next = filterBtn.dataset.nrFilter
      filter = (filter === next && next !== 'all') ? 'all' : next
      onFilterChange?.()
      return true
    }
    const scopeBtn = event.target.closest('[data-nr-scope]')
    if (scopeBtn) {
      baseScope = scopeBtn.dataset.nrScope
      thisKeywordOnly = false
      onFilterChange?.()
      return true
    }
    const kwBtn = event.target.closest('[data-nr-this-keyword]')
    if (kwBtn) {
      thisKeywordOnly = !thisKeywordOnly
      onFilterChange?.()
      return true
    }
    const rowBtn = event.target.closest('[data-nr-case]')
    if (rowBtn) {
      const id = rowBtn.dataset.nrCase
      if (selected === id && !pointOverrideHTML && !showingMethod) {
        clearSelection()
      } else {
        selectCaseById(id, { fromRail: true })
      }
      return true
    }
    return false
  }

  function handleRailInput(event) {
    if (event.target.id !== 'nr-search') return false
    search = event.target.value
    onFilterChange?.({ preserveSearchFocus: true, cursor: event.target.selectionStart })
    return true
  }

  if (inspectorHost) {
    inspectorHost.addEventListener('click', event => {
      const photoCard = event.target.closest('[data-nr-photo]')
      if (photoCard && !event.metaKey && !event.ctrlKey && !event.shiftKey) {
        event.preventDefault()
        openLightbox(photoCard.dataset.nrPhoto, photoCard.dataset.nrLabel)
        return
      }
      if (event.target.closest('[data-nr-close-inspector]')) {
        clearSelection()
        return
      }
      if (event.target.closest('[data-nr-toggle-sheet]')) {
        sheetCollapsed = !sheetCollapsed
        renderInspector()
        return
      }
      if (event.target.closest('[data-nr-back-case]')) {
        pointOverrideHTML = null
        renderInspector()
        return
      }
      const qBtn = event.target.closest('[data-nr-switch-query]')
      if (qBtn) {
        onSelectQuery?.(qBtn.dataset.nrSwitchQuery)
        return
      }
      if (event.target.closest('[data-nr-copy-brief]')) {
        const c = current()
        if (!c) return
        const text = reviewBrief(c, null, { study: getModel().name })
        navigator.clipboard?.writeText(text)
          .then(() => onMessage('Investigation brief copied to clipboard.'))
          .catch(() => onMessage('Clipboard access is unavailable in this browser context.'))
      }
    })
  }

  function open() {
    onOpen()
    openFlag = true
    lastQuery = getQuery()
    renderInspector()
  }

  function close() {
    closeLightbox()
    openFlag = false
    pointOverrideHTML = null
    showingMethod = false
    renderInspector()
  }

  function showPointEvidence(html) {
    pointOverrideHTML = html
    showingMethod = false
    sheetCollapsed = false
    renderInspector()
  }

  return {
    open,
    close,
    dismiss() { close(); onClose?.() },
    renderRailHTML,
    renderInspector,
    handleRailClick,
    handleRailInput,
    selectCase: selectCaseById,
    clearSelection,
    showPointEvidence,
    closeLightbox,
    getFlaggedCases() { return filteredRows() },
    getSelectedCase() { return current() },
    getSelectedTerritory() { const c = current(); return c ? territoryOf(c) : null },
    hasOpenInspector() { return openFlag && Boolean(selected || showingMethod || pointOverrideHTML) },
    sync() {
      if (openFlag) {
        if (lastQuery !== getQuery()) lastQuery = getQuery()
        renderInspector()
      }
    },
    savePending() {},
    async load(path, { studyURL, fallbackInput = null } = {}) {
      const token = ++version, study = getModel()
      evidence = null
      cases = observedReviewScope(study)
      error = ''
      loading = true
      selected = null
      filter = 'all'
      if (openFlag) { renderInspector(); onFilterChange?.() }
      try {
        let input = null
        const resolved = await resolveReviewAttachment({ explicit: path, studyURL, model: study, baseURL: location.href })
        if (token !== version) return
        if (resolved) {
          const response = await fetch(resolved, { cache: 'no-store' })
          if (!response.ok) throw new Error(`Evidence request failed (HTTP ${response.status})`)
          input = await response.json()
          if (token !== version) return
        } else if (fallbackInput && !path && !studyURL) {
          input = fallbackInput
        } else {
          return
        }
        evidence = validateNameReview(input, study)
        const attached = new Map(evidence.cases.map(c => [c.businessId, c]))
        cases = observedReviewScope(study, { includeIds: [...attached.keys()] })
          .map(c => attached.has(c.businessId) ? { ...attached.get(c.businessId), wins_by_query: c.wins_by_query, total_wins: c.total_wins } : c)
        filter = cases.some(isTitleConcern) ? 'concerns' : 'all'
      } catch (e) {
        if (token === version) error = `Agent evidence could not load: ${e.message}. Observed leaders remain listed below; they are not cleared of name stuffing.`
      } finally {
        if (token === version) {
          loading = false
          if (openFlag) { renderInspector(); onFilterChange?.() }
        }
      }
    },
    getState() {
      return {
        loaded: Boolean(evidence),
        cases: cases.length,
        scope: effectiveScope(),
        visibleCases: scoped().length,
        query: getQuery(),
        selected,
        error,
        open: openFlag,
        loading,
        inspectorOpen: openFlag && Boolean(selected || showingMethod || pointOverrideHTML),
      }
    },
  }
}
