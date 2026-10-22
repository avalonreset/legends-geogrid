// Tactical lenses describe observed visibility, never demand or ranking difficulty.
export const CAMPAIGN_LENSES = {
  overview: { label: 'All ranking areas', description: 'See existing strengths, nearby ranking gaps, and weaker coverage.' },
  advance: { label: 'Near top 3', description: 'Connected locations at ranks 4–10. Investigate the rivals ahead.' },
  serviceGap: { label: 'Services falling behind', description: 'This service ranks 4–10 where another studied service already reaches the top 3.' },
  frontier: { label: 'Next to your top 10', description: 'Ranks 11–30 beside current top-ten results. A place to investigate, not an empty market.' },
  defend: { label: 'Hold top 3', description: 'Existing top-three visibility to protect and convert into jobs.' },
}
export const TERRITORY_COLORS = { defend: '#00e5dc', advance: '#ffcf40', build: '#ff704d', outside30: 'transparent', unknown: 'transparent' }
export const TERRITORY_LABELS = { defend: 'Hold · ranks 1–3', advance: 'Improve · ranks 4–10', build: 'Build · ranks 11–30', outside30: 'Outside top 30', unknown: 'Incomplete evidence' }
const escape = text => String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))

export function cellMatchesLens(cell, lens) {
  return lens === 'overview' || (lens === 'serviceGap' ? cell.serviceGap : lens === 'frontier' ? cell.frontier : cell.band === lens)
}

export function campaignAreas(intelligence, lens) {
  if (lens === 'serviceGap') return intelligence.serviceGapAreas || []
  if (lens === 'frontier') return intelligence.frontierAreas || []
  if (lens === 'overview') return intelligence.featuredAreas || []
  return (intelligence.areas || []).filter(area => area.band === lens)
}

export function validateCampaignResearch(input, model) {
  const primary = model.businesses.find(b => b.id === model.targetId)
  if (input?.schema !== 'geogrid-campaign-research/v1' || !primary?.cid ||
      String(input.primaryCid) !== String(primary.cid)) throw new Error('Campaign research does not match this primary profile.')
  const queries = {}
  for (const q of model.queries) {
    const entry = input.queries?.[q.id]
    // A query ID is local to a study. Matching text prevents research being
    // silently applied to a new study with different keywords.
    if (!entry || entry.query !== q.name) continue
    const pages = (entry.pages || []).filter(p => {
      try { return typeof p.label === 'string' && !!campaignSourceURL(p.url) && new URL(p.url).protocol === 'https:' } catch { return false }
    })
    queries[q.id] = { ...entry, pages, nextChecks: (entry.nextChecks || []).filter(v => typeof v === 'string').slice(0, 4) }
  }
  const campaignPlans = (Array.isArray(input.campaignPlans) ? input.campaignPlans : []).filter(plan =>
    plan && typeof plan.id === 'string' && typeof plan.title === 'string' &&
    (!plan.baselineQuery || Object.values(queries).some(entry => entry.query === plan.baselineQuery)))
  return { ...input, queries, campaignPlans }
}


export function campaignSourceURL(value) {
  if (typeof value !== 'string') return null
  if (/^\/runs\/[a-zA-Z0-9_./-]+$/.test(value) && !value.split('/').includes('..')) return value
  try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password ? url.href : null } catch { return null }
}

export function campaignPlanMapAction(research, planId) {
  const plan = (Array.isArray(research?.campaignPlans) ? research.campaignPlans : []).find(plan => plan?.id === planId)
  if (!plan?.baselineQuery) return null
  const baseline = Object.entries(research.queries || {}).find(([, entry]) => entry?.query === plan.baselineQuery)
  if (!baseline) return null
  const lens = Object.hasOwn(CAMPAIGN_LENSES, plan.baselineLens) ? plan.baselineLens : 'overview'
  return { campaignId: `plan:${plan.id}`, planId: plan.id, queryId: baseline[0], lens, regionId: 'all', originIds: [] }
}

function campaignMapButton(research, plan) {
  const action = campaignPlanMapAction(research, plan.id)
  if (!action) return ''
  return `<button class="campaign-read-plans" data-campaign-baseline="${escape(plan.id)}" data-plan-query="${escape(action.queryId)}" data-plan-lens="${escape(action.lens)}">View ${escape(plan.baselineQuery)} baseline on map ↗</button>`
}

// Campaign plans are agent-authored research, not labels generated from a rank band.
// Every plan carries an evidence basis, proposed work and a result to measure.
export function campaignPlansHTML(research, queryId, { compact = false } = {}) {
  const plans = (Array.isArray(research?.campaignPlans) ? research.campaignPlans : []).filter(plan => plan && typeof plan.title === 'string' && typeof plan.id === 'string')
  if (!plans.length) return ''
  const query = research.queries?.[queryId]?.query
  return `<section class="campaign-plans ${compact ? 'campaign-plans-compact' : ''}" aria-label="Researched campaign options">
    <div class="campaign-plans-heading"><span class="eyebrow">AGENT RECOMMENDATIONS · ${escape(research.reviewedAt)}</span><h2>${plans.length} campaign options</h2>
    <p>${escape(research.recommendation || 'Choose a proposed campaign, review its evidence and confirm the launch requirements before committing work or spending.')}</p>${compact ? '<button class="campaign-read-plans" data-open-strategy>Read plans in Strategy room ↗</button>' : ''}</div>
    <div class="campaign-plan-list">${plans.map((plan, index) => `<details class="campaign-plan${plan.baselineQuery === query ? ' campaign-plan-relevant' : ''}" data-plan-id="${escape(plan.id)}">
      <summary><span class="campaign-plan-number">${String(index + 1).padStart(2, '0')}</span><span><strong>${escape(plan.title)}</strong><small>${escape(plan.area)} · ${escape(plan.stage)}</small></span></summary>
      <div class="campaign-plan-body"><p class="campaign-plan-outcome"><b>Goal:</b> ${escape(plan.goal)}</p>
      <p><b>Why this is on the list:</b> ${escape(plan.evidence)}</p>
      <div class="campaign-plan-work"><b>Proposed work</b><ol>${(Array.isArray(plan.steps) ? plan.steps : []).map(step => `<li>${escape(step)}</li>`).join('')}</ol></div>
      <p><b>Before launch:</b> ${escape(plan.gate)}</p><p><b>Judge it by:</b> ${escape(plan.measure)}</p>
      <p class="campaign-plan-boundary">${escape(plan.boundary)}</p>${campaignMapButton(research, plan)}
      <div class="campaign-plan-sources">${(Array.isArray(plan.sources) ? plan.sources : []).filter(source => source && campaignSourceURL(source.url)).map(source => `<a href="${escape(campaignSourceURL(source.url))}" target="_blank" rel="noopener noreferrer">${escape(source.label)} ↗</a>`).join('')}</div>
      </div></details>`).join('')}</div>
    <p class="campaign-plan-footer">Prepared recommendations, not work already published. Map filters below locate ranking patterns; they do not prove demand or easy wins.</p>
  </section>`
}

export function campaignResearchHTML(research, queryId) {
  const entry = research?.queries?.[queryId]
  if (!entry) return `<details class="campaign-research"><summary>What to check before acting</summary><p>Confirm service demand and operating reach. Compare the local rivals’ profiles and pages, then check indexing, search traffic and booked jobs. Rankings alone do not identify the cause.</p></details>`
  return `<details class="campaign-research"><summary>Website & campaign research</summary>
    <p>${escape(research.summary)}</p><p><strong>${escape(entry.area)} research</strong> · ${escape(research.reviewedAt)}</p>
    <p>${escape(entry.hypothesis)}</p>
    <ul>${entry.nextChecks.map(check => `<li>${escape(check)}</li>`).join('')}</ul>
    ${entry.pages.map(page => `<a href="${escape(page.url)}" target="_blank" rel="noopener noreferrer">${escape(page.label)} ↗</a>`).join('')}
    <p>${escape(entry.success)}</p>
    <p>This area-specific research does not establish that every highlighted location lies in that city.</p></details>`
}

export function campaignPanelHTML(intelligence, lens, selectedArea, primaryName, research, queryId) {
  const areas = campaignAreas(intelligence, lens)
  const counts = intelligence.counts
  if (!intelligence.available) return `<div class="side-intro"><h2>Campaign analysis unavailable</h2><p>${escape(intelligence.reason)}</p><p>Use a complete regular study to compare neighboring locations.</p></div>`
  return `${campaignPlansHTML(research, queryId, { compact: true })}<div class="side-intro"><div class="eyebrow">MAP EVIDENCE · PRIMARY BUSINESS</div><h2>Explore the ranking patterns</h2>
    <p>${escape(primaryName)} · these areas support investigation; they are not ready-made campaigns.</p>
    <label class="field-search-label" for="campaign-lens">Highlight on the map</label>
    <select id="campaign-lens">${Object.entries(CAMPAIGN_LENSES).map(([key, value]) => `<option value="${key}" ${key === lens ? 'selected' : ''}>${value.label}</option>`).join('')}</select>
    <div class="campaign-counts"><span><b>${counts.defend}</b> top 3</span><span><b>${counts.advance}</b> near top 3</span><span><b>${counts.frontier || 0}</b> frontier</span></div>
    <p class="campaign-explanation">${escape(CAMPAIGN_LENSES[lens].description)}</p>
    ${selectedArea ? '<button class="text-button" data-clear-area>Show all candidate areas</button>' : ''}
  </div>
  <div class="campaign-cards">${areas.slice(0, 8).map((area, i) => {
    const goal = lens === 'serviceGap' ? 'Investigate service relevance' : lens === 'frontier' || area.band === 'build' ? 'Evaluate adjacent expansion' : area.band === 'defend' ? 'Protect and convert visibility' : 'Investigate a top-three move'
    const action = area.band === 'defend' ? 'Check whether visibility produces qualified calls and bookings. Preserve a baseline before changing successful pages.'
      : lens === 'frontier' || area.band === 'build' ? 'Confirm these locations contain customers you can serve. Compare nearby leaders and existing service pages before choosing an expansion campaign.'
      : 'Compare the rivals ahead here with your relevant service page and Business Profile. Check indexing and query-to-page alignment before deciding what to change.'
    return `<article class="campaign-card ${selectedArea === area.id ? 'selected' : ''}">
      <div class="eyebrow">${area.isolated ? 'ISOLATED OBSERVATION' : escape(goal)}</div><h3>${escape(area.direction || area.label || `Area ${i + 1}`)}</h3>
      <p class="campaign-metric"><strong>${area.count} ${area.count === 1 ? 'location' : 'locations'}</strong> · median rank ${area.medianRank ?? '—'}</p>
      <p><b>Observed:</b> ${escape(area.reason)}</p>
      ${area.distanceMiles ? `<p>${area.distanceMiles.min.toFixed(1)}–${area.distanceMiles.max.toFixed(1)} mi from base${area.serviceGapCount ? ` · ${area.serviceGapCount} service gaps` : ''}</p>` : ''}
      ${lens === 'serviceGap' ? `<p class="campaign-comparison"><b>At a representative location:</b><br>${(area.representative.queries || []).filter(q => q.id === queryId || q.band === 'defend').map(q => `${escape(q.name)}: ${q.rank ? `#${q.rank}` : q.band === 'outside30' ? 'outside 30' : 'unknown'}`).join('<br>')}</p>` : ''}
      <div class="campaign-actions"><button data-focus-area="${escape(area.id)}">Show area on map</button></div>
      <p><b>Next agent check:</b> ${escape(action)}</p><details><summary>Who ranks ahead here?</summary>
        <p>Other profiles in the top 3 within this area:</p><ul>${area.rivals.slice(0, 3).map(rival => `<li><button class="text-button" data-campaign-rival="${escape(rival.id)}">${escape(rival.name)}</button> · ${rival.count}/${area.count} locations</li>`).join('') || '<li>No qualifying rival evidence.</li>'}</ul>
        <p>Demand and serviceability have not yet been assessed for this group of locations.</p>
      </details></article>`
  }).join('') || '<p class="list-caption">No connected area matches this lens. The map still shows any isolated measured locations. Try another query or lens.</p>'}</div>
  ${areas.length > 8 ? `<p class="list-caption">Showing the eight largest areas of ${areas.length}; all matching locations remain on the map.</p>` : ''}
  ${campaignResearchHTML(research, queryId)}
  <p class="list-caption">Adjacent samples form investigation areas, not proven market boundaries. Empty rankings do not establish unmet demand. ${counts.unknown} locations have incomplete evidence.</p>`
}
