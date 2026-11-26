// Campaigns rail, Vision-Agent brief, legend, finding strip, and research attachment validation.
// Zero compass naming, zero lens dropdown, zero boilerplate repetition.
const escape = text => String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
const finite = v => typeof v === 'number' && Number.isFinite(v)

export const EMBER_RAMP = ['#3a2400', '#5c3807', '#7f4d0f', '#b8741a', '#db901d', '#ffb020', '#ffc444', '#ffd76a', '#ffe699', '#fff1c4']

export const ZONE_COLORS = {
  hold: '#00e5dc',
  strike: '#ffd76a',
  contest: '#ffb020',
  long: '#b8741a',
  fortress: '#e3232d',
  detached: '#8a8a8a',
  out_of_reach: 'transparent',
  absent: 'transparent',
  unknown: 'transparent',
}

export const ZONE_LABELS = {
  hold: 'Hold (ranks 1 to 3)',
  strike: 'Strike (W 60+)',
  contest: 'Contest (W 40 to 59)',
  long: 'Long climb (W under 40)',
  fortress: 'Fortress (150+ reviews on block)',
  detached: 'Detached landmass',
  out_of_reach: 'Out of reach (<10% ring reach)',
  absent: 'Outside top 30',
  unknown: 'Incomplete evidence',
}

export const MECHANISM_LABELS = {
  service_gap: 'service gap',
  weak_pack: 'weak pack',
  seam: 'seam',
  long_climb: 'long climb',
  hold_thin: 'thin hold',
}

export function emberColorForW(w) {
  if (!finite(w) || w <= 0) return { color: 'transparent', opacity: 0 }
  const idx = Math.max(0, Math.min(9, Math.floor((w - 1) / 10)))
  const t = idx / 9
  return { color: EMBER_RAMP[idx], opacity: 0.25 + t * 0.65 }
}

// Legacy thin helpers retained for backwards compatibility with existing pure unit tests.
export function cellMatchesLens(cell, lens) {
  return lens === 'overview' || (lens === 'serviceGap' ? cell.serviceGap : lens === 'frontier' ? cell.frontier : cell.band === lens)
}

export function campaignAreas(intelligence, lens) {
  if (lens === 'serviceGap') return intelligence.serviceGapAreas || []
  if (lens === 'frontier') return intelligence.frontierAreas || []
  if (lens === 'overview') return intelligence.featuredAreas || []
  return (intelligence.areas || []).filter(area => area.band === lens)
}

export function campaignSourceURL(value) {
  if (typeof value !== 'string') return null
  if (/^\/runs\/[a-zA-Z0-9_./-]+$/.test(value) && !value.split('/').includes('..')) return value
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && !url.username && !url.password ? url.href : null
  } catch {
    return null
  }
}

const VALID_AVOID_KINDS = new Set([
  'detached_landmass', 'fortress', 'out_of_reach',
  'non_serviceable_land_use', 'not_your_blocker', 'low_evidence',
])
const VALID_GEO_SOURCES = new Set(['vector', 'vision', 'none'])

export function validateCampaignResearch(input, model, engine = null) {
  const primary = model.businesses.find(b => b.id === model.targetId)
  if (input?.schema !== 'geogrid-campaign-research/v1' || !primary?.cid ||
      String(input.primaryCid) !== String(primary.cid)) {
    throw new Error('Campaign research does not match this primary profile.')
  }
  const pointIds = new Set((model.points || []).map(p => p.id))
  const businessCids = new Set((model.businesses || []).map(b => b.cid ? String(b.cid) : null).filter(Boolean))
  const enginePlayIds = new Set()
  const engineAvoidIds = new Set()
  if (engine?.queries) {
    for (const qd of Object.values(engine.queries)) {
      for (const p of qd.plays || []) enginePlayIds.add(p.id)
      for (const a of qd.avoid || []) engineAvoidIds.add(a.id)
    }
  }

  const queries = {}
  for (const q of model.queries) {
    const entry = input.queries?.[q.id]
    if (!entry || entry.query !== q.name) continue
    const pages = (entry.pages || []).filter(p => {
      try { return typeof p.label === 'string' && !!campaignSourceURL(p.url) && new URL(p.url).protocol === 'https:' } catch { return false }
    })
    queries[q.id] = { ...entry, pages, nextChecks: (entry.nextChecks || []).filter(v => typeof v === 'string').slice(0, 4) }
  }

  const geoObservations = (Array.isArray(input.vision?.geoObservations) ? input.vision.geoObservations : [])
    .filter(g => g && typeof g.id === 'string' && typeof g.feature === 'string')
    .slice(0, 200)
  const geoObsIds = new Set(geoObservations.map(g => g.id))

  const campaignPlans = (Array.isArray(input.campaignPlans) ? input.campaignPlans : []).filter(plan => {
    if (!plan || typeof plan.id !== 'string' || typeof plan.title !== 'string') return false
    if (plan.baselineQuery && !Object.values(queries).some(entry => entry.query === plan.baselineQuery)) return false
    if (Array.isArray(plan.originIds) && plan.originIds.length && pointIds.size && !plan.originIds.every(id => pointIds.has(id))) {
      return false
    }
    return true
  }).map(plan => {
    const blockers = Array.isArray(plan.blockers)
      ? plan.blockers.filter(b => b && (!b.cid || !businessCids.size || businessCids.has(String(b.cid))))
      : []
    const geography = plan.geography && VALID_GEO_SOURCES.has(plan.geography.source)
      ? plan.geography
      : null
    const engineBacked = !plan.mechanism || !engine?.available
      ? true
      : Boolean(plan.enginePlayId && enginePlayIds.has(plan.enginePlayId))
    return { ...plan, blockers, geography, engineBacked }
  })

  const avoidZones = (Array.isArray(input.avoidZones) ? input.avoidZones : []).filter(z => {
    if (!z || typeof z.id !== 'string' || typeof z.title !== 'string') return false
    if (!VALID_AVOID_KINDS.has(z.kind)) return false
    if (Array.isArray(z.originIds) && z.originIds.length && pointIds.size && !z.originIds.every(id => pointIds.has(id))) {
      return false
    }
    if (z.kind === 'non_serviceable_land_use') {
      const refs = Array.isArray(z.geoObservationIds) ? z.geoObservationIds.filter(id => geoObsIds.has(id)) : []
      if (!refs.length) return false
    }
    return true
  }).slice(0, 12).map(z => ({
    ...z,
    engineBacked: !z.engineAvoidId || !engine?.available || engineAvoidIds.has(z.engineAvoidId),
  }))

  return { ...input, queries, campaignPlans, avoidZones }
}

export function campaignPlanMapAction(research, planId) {
  const plan = (Array.isArray(research?.campaignPlans) ? research.campaignPlans : []).find(p => p?.id === planId)
  if (!plan?.baselineQuery) return null
  const baseline = Object.entries(research.queries || {}).find(([, entry]) => entry?.query === plan.baselineQuery)
  if (!baseline) return null
  return {
    campaignId: `plan:${plan.id}`,
    planId: plan.id,
    queryId: baseline[0],
    lens: 'overview',
    regionId: 'all',
    originIds: Array.isArray(plan.originIds) ? plan.originIds : [],
    enginePlayId: plan.enginePlayId || null,
  }
}

function campaignMapButton(research, plan) {
  const action = campaignPlanMapAction(research, plan.id)
  if (!action) return ''
  return `<button class="campaign-read-plans" data-campaign-baseline="${escape(plan.id)}" data-plan-query="${escape(action.queryId)}" data-plan-lens="${escape(action.lens)}">View ${escape(plan.baselineQuery)} baseline on map ↗</button>`
}

export function campaignPlansHTML(research, queryId, { compact = false } = {}) {
  const plans = (Array.isArray(research?.campaignPlans) ? research.campaignPlans : [])
    .filter(plan => plan && typeof plan.title === 'string' && typeof plan.id === 'string')
  if (!plans.length) return ''
  const query = research.queries?.[queryId]?.query
  return `<section class="campaign-plans ${compact ? 'campaign-plans-compact' : ''}" aria-label="Researched campaign options">
    <div class="campaign-plans-heading"><span class="eyebrow">AGENT PLANS · ${escape(research.reviewedAt || 'ATTACHED')}</span><h2>${plans.length} campaign options</h2>
    <p>${escape(research.recommendation || 'Choose a proposed campaign, review its evidence and confirm the launch requirements before committing work or spending.')}</p>${compact ? '<button class="campaign-read-plans" data-open-strategy>Read plans in Strategy room ↗</button>' : ''}</div>
    <div class="campaign-plan-list">${plans.map((plan, index) => `<details class="campaign-plan${plan.baselineQuery === query ? ' campaign-plan-relevant' : ''}" data-plan-id="${escape(plan.id)}">
      <summary><span class="campaign-plan-number">${String(index + 1).padStart(2, '0')}</span><span><strong>${escape(plan.title)}</strong><small>${escape(plan.area || plan.geography?.label || '')}${plan.stage ? ` · ${escape(plan.stage)}` : ''}${plan.engineBacked === false ? ' · <em class="campaign-chip-warn">not engine-backed</em>' : ''}</small></span></summary>
      <div class="campaign-plan-body"><p class="campaign-plan-outcome"><b>Goal:</b> ${escape(plan.goal)}</p>
      <p><b>Why this is on the list:</b> ${escape(plan.evidence)}</p>
      <div class="campaign-plan-work"><b>Proposed work</b><ol>${(Array.isArray(plan.steps) ? plan.steps : []).map(step => `<li>${escape(step)}</li>`).join('')}</ol></div>
      <p><b>Before launch:</b> ${escape(plan.gate)}</p><p><b>Judge it by:</b> ${escape(plan.measure)}</p>
      <p class="campaign-plan-boundary">${escape(plan.boundary)}</p>${campaignMapButton(research, plan)}
      <div class="campaign-plan-sources">${(Array.isArray(plan.sources) ? plan.sources : []).filter(source => source && campaignSourceURL(source.url)).map(source => `<a href="${escape(campaignSourceURL(source.url))}" target="_blank" rel="noopener noreferrer">${escape(source.label)} ↗</a>`).join('')}</div>
      </div></details>`).join('')}</div>
    <p class="campaign-plan-footer">Prepared recommendations, not work already published. Engine plays below rank observed structure; they do not prove demand or ranking probability.</p>
  </section>`
}

export function campaignResearchHTML(research, queryId) {
  const entry = research?.queries?.[queryId]
  if (!entry) {
    return `<details class="campaign-research"><summary>What to check before acting</summary><p>Confirm service demand and operating reach. Compare the local rivals' profiles and pages, then check indexing, search traffic and booked jobs. Rankings alone do not identify the cause.</p></details>`
  }
  return `<details class="campaign-research"><summary>Website &amp; campaign research</summary>
    <p>${escape(research.summary)}</p><p><strong>${escape(entry.area)} research</strong> · ${escape(research.reviewedAt)}</p>
    <p>${escape(entry.hypothesis)}</p>
    <ul>${entry.nextChecks.map(check => `<li>${escape(check)}</li>`).join('')}</ul>
    ${entry.pages.map(page => `<a href="${escape(page.url)}" target="_blank" rel="noopener noreferrer">${escape(page.label)} ↗</a>`).join('')}
    <p>${escape(entry.success)}</p>
    <p>This area-specific research does not establish that every highlighted location lies in that city.</p></details>`
}

function whyWinnableSentences(play, engine) {
  const target = engine.target
  const lead = play.leadHolder
  const lines = []

  if (lead) {
    const revTarget = target?.reviews ?? 0
    const revLead = lead.reviews ?? 0
    const distTxt = finite(lead.milesFromBase) ? `, ${lead.milesFromBase.toFixed(2)} mi from base` : ''
    const ratingTxt = finite(lead.rating) ? `${lead.rating.toFixed(1)} stars` : 'unrated'
    const revRatio = revLead > 0 && revTarget >= revLead * 2
      ? ` You have ${Math.floor(revTarget / revLead)} times their reviews (${revTarget.toLocaleString('en-US')} vs ${revLead.toLocaleString('en-US')}).`
      : ''
    lines.push(`${lead.name} (${ratingTxt}, ${revLead.toLocaleString('en-US')} reviews${distTxt}, Pm ${lead.pm.toFixed(2)} vs your ${target.pm.toFixed(2)}) sits in the top three at ${lead.packCount} of ${play.points} points.${revRatio}`)

    if (lead.aheadWhereBothAppear && lead.aheadWhereBothAppear[1] > 0) {
      const [ahead, both] = lead.aheadWhereBothAppear
      if (play.diagnosis === 'relevance_not_reputation') {
        lines.push(`Ahead of you at ${ahead} of ${both} shared points despite weaker reputation. Google does not read you strongly enough for ${play.queryName} here: fix relevance. More generic reviews will not move this.`)
      } else {
        lines.push(`Ahead of you at ${ahead} of ${both} points where both profiles appear.`)
      }
    }
  }

  if (play.mechanism === 'hold_thin') {
    lines.push(`You hold ${play.points} top-three points here with ${play.rank1Count} first places. Treat this hold as exposed until first-place blockers are checked.`)
  } else if (play.strongQueryName && play.mechanism === 'service_gap') {
    const ringReachPct = Math.round((play.ringReach ?? 0) * 100)
    lines.push(`You already hold the top three for ${play.strongQueryName} at these exact ${play.points} points (ring reach for ${play.queryName}: ${ringReachPct}%).`)
  } else if (lines.length < 3) {
    const ringReachPct = Math.round((play.ringReach ?? 0) * 100)
    lines.push(`Measured ${play.queryName} top-ten reach in this ring (${play.minRing} to ${play.minRing + 1} mi) is ${ringReachPct}%.`)
  }

  return lines.slice(0, 3)
}

function playActionSteps(play) {
  if (play.mechanism === 'service_gap') {
    return [
      `Add ${play.queryName} to the GBP services list with a clear service description.`,
      `Publish or repair one dedicated service page for ${play.queryName} and link it from the profile.`,
      `Ask the next 10 ${play.queryName} customers to name the service in their review and add 5 photos of that work.`,
    ]
  }
  if (play.mechanism === 'weak_pack' && play.categoryMismatch) {
    return [
      'Run a fresh exact-CID profile check to confirm live primary and secondary categories.',
      `Add ${play.categoryMismatch.dominantCategory} as a secondary category if absent.`,
      'Decide the primary category by which query pays, using the category trade-off table below.',
    ]
  }
  if (play.mechanism === 'hold_thin') {
    return [
      'Capture a clean baseline across these held pins before changing profile or page copy.',
      'Identify who holds first place at the held pins and inspect their title, category, and service page.',
      'Treat this thin hold as an active play rather than a settled win.',
    ]
  }
  return [
    `Open ${play.leadHolder?.name || 'the lead holder'}'s Google Business Profile and website page beside yours.`,
    `List what their profile and page state about ${play.queryName} that yours do not.`,
    'Close the listed gaps on your profile and service page before buying external links or ads.',
  ]
}

function categoryTradeoffHTML(play, engine) {
  if (!play.categoryMismatch) return ''
  const rows = Object.values(engine.queries || {}).map(qd => {
    const topCat = Object.entries(qd.categoryShareTop3 || {})[0]
    const sharePct = topCat ? `${Math.round(topCat[1] * 100)}% ${topCat[0]}` : 'n/a'
    const rank1 = qd.cells.filter(c => c.rank === 1).length
    return `<tr><td>${escape(qd.queryName)}</td><td>${escape(sharePct)}</td><td>${rank1}</td></tr>`
  }).join('')
  return `<div class="campaign-tradeoff">
    <div class="eyebrow">CATEGORY TRADE-OFF</div>
    <p>${Math.round(play.categoryMismatch.share * 100)}% of ${escape(play.queryName)} top-three slots use <b>${escape(play.categoryMismatch.dominantCategory)}</b>; your observed profile uses <b>${escape(play.categoryMismatch.targetCategory)}</b>.</p>
    <table><thead><tr><th>Query</th><th>Dominant top-3 category</th><th>Your #1s</th></tr></thead><tbody>${rows}</tbody></table>
  </div>`
}

export function campaignFindingInfo(engine, queryId, selectedPlayId = null) {
  const qd = engine?.queries?.[queryId]
  if (!engine?.available || !qd) {
    return { text: 'Campaign engine requires a complete regular study with depth-30 evidence.', playId: null, buttonLabel: 'Open play' }
  }
  const play = (selectedPlayId && qd.plays.find(p => p.id === selectedPlayId)) || qd.plays[0] || null
  if (!play) {
    return { text: `No high-leverage home-landmass play found for ${qd.queryName}. Review Where not to spend in the Campaigns rail.`, playId: null, buttonLabel: 'Review avoids' }
  }
  const lead = play.leadHolder
  if (lead && lead.aheadWhereBothAppear?.[1] > 0) {
    const [ahead, both] = lead.aheadWhereBothAppear
    const revStr = finite(lead.reviews) ? `, ${lead.reviews.toLocaleString('en-US')} reviews,` : ''
    const detail = play.mechanism === 'service_gap' && play.strongQueryName
      ? ` ${lead.packCount} of those points are inside your ${play.strongQueryName} stronghold.`
      : ` Mean W ${play.meanW ?? 'n/a'}, leverage ${play.leverage.toLocaleString('en-US')}.`
    return {
      text: `${lead.name}${revStr} outranks you at ${ahead} of ${both} points on ${qd.queryName}.${detail}`,
      playId: play.id,
      buttonLabel: 'Open play',
    }
  }
  return {
    text: `${play.title} (${play.points} points, mean W ${play.meanW ?? 'n/a'}, leverage ${play.leverage.toLocaleString('en-US')}).`,
    playId: play.id,
    buttonLabel: 'Open play',
  }
}

export function campaignLegendHTML(activeIsolation = null) {
  const chip = (key, cls, label, title = '') =>
    `<button type="button" class="campaign-legend-chip" data-campaign-isolate="${key}" aria-pressed="${activeIsolation === key}"${title ? ` title="${title}"` : ''}><i class="${cls}"></i><span>${label}</span></button>`
  return `<div class="campaign-ember-key" title="Win next (Winnability index W). Weighted contours at 35, 50, 65, and 80.">
      <span class="campaign-ember-label">Win next</span>
      <span class="campaign-ember-bar"><em style="left:35%">35</em><em style="left:65%">65</em></span>
    </div>`
    + chip('hold', 'key-hold', 'Hold (1-3)', 'Your current Google Maps 3-pack territory')
    + chip('fortress', 'key-fortress', 'Don\'t spend', 'Entrenched fortress competitors to avoid')
    + chip('seams', 'key-seam', 'Flip seams', 'Contoured rank 4-5 borders touching your 3-pack')
    + chip('service_gap', 'key-gap', 'Service gap', 'Pockets strong on another service but weak here')
    + chip('detached', 'key-detached', 'Detached', 'Water-separated islands outside mainland reach')
    + chip('weak_blocker', 'key-blocker', 'Blockers', 'Weak pack blockers you can outrank')
}

export function mergedAvoidList(engine, queryId, research = null) {
  const qd = engine?.queries?.[queryId]
  const qName = qd?.queryName || ''
  const engineAvoids = (qd?.avoid || []).map(a => ({ ...a, sourceTag: 'engine' }))
  const agentAvoids = (Array.isArray(research?.avoidZones) ? research.avoidZones : [])
    .filter(z => !Array.isArray(z.appliesToQueries) || !qName || z.appliesToQueries.includes(qName))
    .map(z => ({
      id: `agent:${z.id}`,
      engineAvoidId: z.engineAvoidId || null,
      kind: z.kind,
      title: z.title,
      pins: Array.isArray(z.originIds) ? z.originIds.length : 0,
      originIds: Array.isArray(z.originIds) ? z.originIds : [],
      reason: z.reason,
      sourceTag: 'agent',
    }))
  const coveredEngineIds = new Set(agentAvoids.map(a => a.engineAvoidId).filter(Boolean))
  const remainingEngine = engineAvoids.filter(a => !coveredEngineIds.has(a.id))
  return [...agentAvoids, ...remainingEngine]
}

export function visionAgentCampaignBrief(engine, model, queryId) {
  const qd = engine?.queries?.[queryId]
  const qName = qd?.queryName || queryId
  const planSha = model.evidence?.plan_sha256 || 'not_recorded'
  const compactPlays = (qd?.plays || []).slice(0, 5).map(p => ({
    id: p.id,
    mechanism: p.mechanism,
    points: p.points,
    meanW: p.meanW,
    leverage: p.leverage,
    diagnosis: p.diagnosis,
    categoryMismatch: p.categoryMismatch,
    leadHolder: p.leadHolder ? {
      cid: p.leadHolder.cid,
      name: p.leadHolder.name,
      rating: p.leadHolder.rating,
      reviews: p.leadHolder.reviews,
      pm: p.leadHolder.pm,
      packCount: p.leadHolder.packCount,
      milesFromBase: p.leadHolder.milesFromBase,
      aheadWhereBothAppear: p.leadHolder.aheadWhereBothAppear,
    } : null,
  }))
  const compactAvoids = (qd?.avoid || []).map(a => ({
    id: a.id,
    kind: a.kind,
    title: a.title,
    pins: a.pins,
    reason: a.reason,
  }))
  const slug = String(model.name || 'study').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || 'study'

  return [
    'LEGENDS GEOGRID VISION-AGENT CAMPAIGN BRIEF',
    `Study: ${model.name}`,
    `Study Plan SHA-256: ${planSha}`,
    `Selected Query: ${qName} (${queryId})`,
    `Target: ${engine.target?.name || model.name} | CID ${engine.target?.cid || 'n/a'} | ${engine.target?.rating ?? 'n/a'} stars | ${engine.target?.reviews ?? 'n/a'} reviews | Pm ${engine.target?.pm ?? 'n/a'} | Observed category: ${engine.target?.category || 'n/a'}`,
    ...(engine.target?.categoryConflict ? [`Category conflict: business record says "${engine.target.categoryConflict.business}", observed GBP profile says "${engine.target.categoryConflict.profile}".`] : []),
    '',
    '1. GENERATE VISION BUNDLE',
    `python tools/study.py vision-brief --study runs/${slug}/companion-study.json --query ${queryId} --out runs/${slug}/vision/`,
    '',
    '2. ENGINE SUMMARY (geogrid-campaign-engine/v1)',
    JSON.stringify({
      weights: engine.weights,
      landmass: {
        homePins: engine.landmass?.home?.pins ?? 0,
        detached: (engine.landmass?.detached || []).map(d => ({ id: d.id, pins: d.pins, offsetMiles: d.offsetMiles })),
      },
      reachByQuery: engine.reachByQuery,
      topPlays: compactPlays,
      avoid: compactAvoids,
    }, null, 2),
    '',
    '3. TASKS',
    'Task 1 (Look): Open map-context.png, map-plays.png, and map-grid.png. For each play, avoid entry, and detached landmass, state what is physically there, citing grid squares (A1 to H8) and geo-features.json ids. Flag anything vector tags missed.',
    'Task 2 (Check blockers): For each leadHolder, compare its Google Business Profile and website with the target for the play query. State the observable relevance difference or state that none was found.',
    'Task 3 (Synthesize): Write at most 3 campaignPlans in geogrid-campaign-research/v1 schema. Each plan must reference one enginePlayId. Add avoidZones the engine could not know (airport, port, stadium, water crossing, non-residential land) with geoObservationIds.',
    '',
    '4. HARD RULES',
    '- Copy every number from engine.json with its exact field path.',
    '- Do not invent neighborhood names: use a geo-features.json name or write "unnamed".',
    '- No demand, revenue, or ranking probability claims.',
    '- If any PNG cannot be opened, say so and stop.',
  ].join('\n')
}

function avoidMetricLabel(item) {
  if (item.kind === 'out_of_reach' && finite(item.reachPct)) return `reach ${item.reachPct}%`
  if (item.kind === 'not_your_blocker') return 'not your blocker'
  return `${item.pins} ${item.pins === 1 ? 'pin' : 'pins'}`
}

function humanizeAvoidTitle(item) {
  const raw = String(item.title || '')
  if (item.kind === 'detached_landmass') {
    const cleaned = raw.replace(/^Detached landmass\s+C(\d+)\s*/i, 'Separated island #$1 ')
    return cleaned.trim()
  }
  return raw
}

export function campaignPanelHTML(engine, model, queryId, { selectedPlayId = null, selectedAvoidId = null, research = null } = {}) {
  if (!engine?.available) {
    return `<div class="side-intro"><h2>Campaign analysis unavailable</h2><p>${escape(engine?.reason || 'Use a complete regular circular study with depth-30 evidence.')}</p></div>`
  }
  const qd = engine.queries[queryId]
  if (!qd) {
    return `<div class="side-intro"><h2>Query unavailable</h2><p>Select a measured query to view plays and avoid zones.</p></div>`
  }

  const plays = qd.plays || []
  const avoids = mergedAvoidList(engine, queryId, research)
  const conflict = engine.target?.categoryConflict

  const conflictBanner = conflict
    ? `<div class="campaign-conflict" role="note"><b>Category conflict:</b> business record says "${escape(conflict.business)}", observed GBP profile says "${escape(conflict.profile)}". Run a fresh exact-CID check before changing categories.</div>`
    : ''

  const planByEnginePlayId = new Map()
  for (const plan of Array.isArray(research?.campaignPlans) ? research.campaignPlans : []) {
    if (plan?.enginePlayId && !planByEnginePlayId.has(plan.enginePlayId)) {
      planByEnginePlayId.set(plan.enginePlayId, plan)
    }
  }
  const hasAttachedResearch = Boolean(research && (Object.keys(research.queries || {}).length || planByEnginePlayId.size))

  const playsHTML = plays.map((play, idx) => {
    const isSelected = selectedPlayId === play.id
    const mechLabel = MECHANISM_LABELS[play.mechanism] || play.mechanism
    const matchedPlan = planByEnginePlayId.get(play.id) || null
    const whyLines = whyWinnableSentences(play, engine)
    const steps = (matchedPlan && Array.isArray(matchedPlan.steps) && matchedPlan.steps.length)
      ? matchedPlan.steps
      : playActionSteps(play)
    const leverNote = matchedPlan
      ? `<span class="campaign-lever-note campaign-lever-verified">agent researched · ${escape(research.reviewedAt || 'attached')}</span>`
      : hasAttachedResearch
        ? '<span class="campaign-lever-note">engine levers · see attached Agent Plans below</span>'
        : '<span class="campaign-lever-note">standard levers, unverified until agent research is attached</span>'
    const targetSuccess = Math.ceil(play.points / 3)
    const judgeText = matchedPlan?.measure
      ? matchedPlan.measure
      : `Rescan ${play.queryName} on this same lattice in 30 days. Success: ${targetSuccess} of ${play.points} ${play.points === 1 ? 'point' : 'points'} move into the top three.`
    const num = String(idx + 1).padStart(2, '0')
    const ptWord = play.points === 1 ? 'point' : 'points'
    return `<details class="campaign-play-card${isSelected ? ' selected' : ''}" data-play-card="${escape(play.id)}"${isSelected ? ' open' : ''}>
      <summary data-play-summary="${escape(play.id)}">
        <div class="campaign-play-top">
          <span class="campaign-play-num">${num}</span>
          <span class="campaign-play-mech">${escape(mechLabel)}</span>
          ${matchedPlan ? '<span class="campaign-tag campaign-tag-agent">agent plan</span>' : ''}
          <span class="campaign-play-query">${escape(play.queryName)}</span>
        </div>
        <div class="campaign-play-title">${escape(play.title)}</div>
        <div class="campaign-play-metrics">
          <span><b>${play.points}</b> ${ptWord}</span>
          <span title="Mean structural winnability index W (0 to 100)">score <b>${play.meanW ?? 'n/a'}</b></span>
          <span title="Leverage = points x mean W">impact <b>${play.leverage.toLocaleString('en-US')}</b></span>
        </div>
      </summary>
      <div class="campaign-play-body">
        <div class="campaign-block">
          <div class="eyebrow">WHY THIS IS WINNABLE</div>
          ${whyLines.map(line => `<p>${escape(line)}</p>`).join('')}
        </div>
        ${categoryTradeoffHTML(play, engine)}
        <div class="campaign-block">
          <div class="eyebrow">DO THIS ${leverNote}</div>
          <ol>${steps.map(s => `<li>${escape(s)}</li>`).join('')}</ol>
        </div>
        <div class="campaign-block">
          <div class="eyebrow">JUDGE IT BY</div>
          <p>${escape(judgeText)}</p>
          ${matchedPlan?.boundary ? `<p class="campaign-plan-boundary">${escape(matchedPlan.boundary)}</p>` : ''}
        </div>
        <div class="campaign-play-actions">
          <button type="button" data-focus-play="${escape(play.id)}">${isSelected ? 'Show full map' : 'Isolate play on map'}</button>
          ${play.leadHolder ? `<button type="button" data-campaign-rival="${escape(play.leadHolder.id)}">Inspect ${escape(play.leadHolder.name)}</button>` : ''}
        </div>
      </div>
    </details>`
  }).join('') || '<p class="list-caption">No home-landmass plays qualified on this query. Check Where not to spend below or switch queries.</p>'

  const avoidsHTML = avoids.slice(0, 10).map(item => {
    const isSelected = selectedAvoidId === item.id
    const displayTitle = humanizeAvoidTitle(item)
    return `<details class="campaign-avoid-row${isSelected ? ' selected' : ''}" data-avoid-card="${escape(item.id)}"${isSelected ? ' open' : ''}>
      <summary data-avoid-summary="${escape(item.id)}">
        <span class="campaign-avoid-title" title="${escape(displayTitle)}">${escape(displayTitle)}</span>
        <span class="campaign-avoid-meta"><em class="campaign-tag campaign-tag-${escape(item.sourceTag)}">${escape(item.sourceTag)}</em><b>${escape(avoidMetricLabel(item))}</b></span>
      </summary>
      <div class="campaign-avoid-body">
        <p>${escape(item.reason)}</p>
        <button type="button" data-focus-avoid="${escape(item.id)}">${isSelected ? 'Clear isolation' : 'Show avoid zone on map'}</button>
      </div>
    </details>`
  }).join('') || '<p class="list-caption">No avoid zones flagged for this query.</p>'

  return `<div class="campaign-rail">
    <div class="campaign-rail-head">
      <div class="eyebrow">CAMPAIGNS · ${escape(qd.queryName)}</div>
      ${conflictBanner}
    </div>
    <section class="campaign-section" aria-label="Engine plays">
      <div class="campaign-section-head"><span class="eyebrow">PLAYS <b>${plays.length}</b></span><small>click to isolate</small></div>
      ${selectedPlayId || selectedAvoidId ? '<button type="button" class="campaign-clear-btn" data-clear-campaign-focus>Show all layers</button>' : ''}
      <div class="campaign-play-list">${playsHTML}</div>
    </section>
    <section class="campaign-section" aria-label="Where not to spend">
      <div class="campaign-section-head"><span class="eyebrow">WHERE NOT TO SPEND <b>${avoids.length}</b></span><small>avoid list</small></div>
      <div class="campaign-avoid-list">${avoidsHTML}</div>
    </section>
    ${campaignPlansHTML(research, queryId, { compact: true })}
    <div class="campaign-rail-footer">
      <button type="button" id="copy-vision-brief" class="campaign-brief-btn" data-copy-vision-brief>Copy Vision-Agent Campaign Brief</button>
      <p class="campaign-limit-note">${escape(engine.limitations)}</p>
    </div>
  </div>`
}
