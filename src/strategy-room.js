import { strategyIntelligence } from './strategy-engine.js'
import { campaignPlansHTML, campaignPlanMapAction } from './campaign-panel.js'

const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
const number = value => Number.isFinite(value) ? value : 0
const pct = value => `${number(value).toFixed(1)}%`
const queryName = (model, id) => model.queries.find(q => q.id === id)?.name || 'Selected service'
const shortRegion = region => region.id === 'core' ? 'Core' : region.id.split('-').at(-1).toUpperCase()
const countValue = value => Array.isArray(value) ? value.length : number(value)

export function strategySafeURL(value) {
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null
  } catch { return null }
}

function metricFor(region, queryId) {
  return region?.perQuery?.[queryId] || { complete: 0, unknown: region?.count || 0, top3: 0, top10: 0, near: 0, found: 0, top3Pct: 0, top10Pct: 0 }
}

function regionTotal(region, key) {
  return Object.values(region?.perQuery || {}).reduce((sum, metric) => sum + number(metric[key]), 0)
}

function heatmap(model, intelligence, state) {
  const regions = intelligence.regions.filter(region => region.id !== 'all')
  const label = state.metric === 'top10' ? 'Top 10' : 'Top 3'
  const innerCount = regions.filter(r => r.id.startsWith('inner')).length, outerCount = regions.filter(r => r.id.startsWith('outer')).length
  const radius = number(model.sampling?.radius_km) / 1.609344
  const miles = value => value.toLocaleString('en-US', { maximumFractionDigits: 1 })
  return `<section class="sr-section sr-matrix-section" aria-labelledby="sr-matrix-title">
    <div class="sr-section-heading"><div><span class="sr-overline">THE WHOLE FIELD</span><h2 id="sr-matrix-title">Your reach, by service and area</h2><p>Choose a cell to investigate. Percentages use complete observations in each area.</p></div>
      <div class="sr-segment" role="group" aria-label="Visibility measure"><button data-sr-metric="top3" aria-pressed="${state.metric === 'top3'}">Top 3</button><button data-sr-metric="top10" aria-pressed="${state.metric === 'top10'}">Top 10</button></div></div>
    <div class="sr-matrix-scroll"><table class="sr-matrix"><caption class="sr-sr-only">${label} coverage by service and radial area</caption><thead>
      <tr class="sr-radius-head"><th scope="col">SEARCH SERVICE</th><th scope="col">CORE</th>${innerCount ? `<th colspan="${innerCount}" scope="colgroup">2–${miles(Math.min(5, radius))} MI</th>` : ''}${outerCount ? `<th colspan="${outerCount}" scope="colgroup">5–${miles(radius)} MI</th>` : ''}</tr>
      <tr><th scope="col">Ranked reach, not customer demand</th>${regions.map(region => `<th scope="col" title="${esc(region.label)}">${esc(shortRegion(region))}<small>${region.count} search locations</small></th>`).join('')}</tr>
    </thead><tbody>${model.queries.map(query => `<tr><th scope="row">${esc(query.name)}</th>${regions.map(region => {
      const metric = metricFor(region, query.id), value = number(metric[`${state.metric}Pct`]), count = number(metric[state.metric])
      const selected = state.regionId === region.id && state.queryId === query.id
      const strength = Math.min(1, Math.sqrt(Math.max(0, value) / 100))
      const title = `${query.name} · ${region.label}: ${count}/${metric.complete} complete search locations in ${label.toLowerCase()}${metric.unknown ? `; ${metric.unknown} incomplete` : ''}`
      return `<td><button class="sr-heat-cell${selected ? ' selected' : ''}${count ? '' : ' zero'}" data-sr-region="${esc(region.id)}" data-sr-query="${esc(query.id)}" aria-pressed="${selected}" aria-label="${esc(title)}" title="${esc(title)}" style="--heat:${(.07 + strength * .64).toFixed(3)}">
        <strong>${metric.complete ? pct(value) : '—'}</strong><span>${count}/${metric.complete}</span>${metric.unknown ? '<i title="Some evidence is incomplete">!</i>' : ''}</button></td>`
    }).join('')}</tr>`).join('')}</tbody></table></div>
    <div class="sr-matrix-key"><span><i></i> Brighter = more measured reach</span><span>NE / SE / SW / NW are directions from the primary business</span><button data-sr-all>Inspect whole circle →</button></div>
  </section>`
}

function rankBar(metric, total) {
  const bands = [
    ['Top 3', number(metric.top3), 'top3'],
    ['4–10', Math.max(0, number(metric.top10) - number(metric.top3)), 'near'],
    ['11–30', Math.max(0, number(metric.found) - number(metric.top10)), 'deep'],
    ['Outside 30', Math.max(0, number(metric.complete) - number(metric.found)), 'absent'],
    ['Unknown', number(metric.unknown), 'unknown'],
  ]
  return `<div class="sr-rank-bar" aria-label="Rank distribution">${bands.map(([label, count, cls]) => count ? `<span class="${cls}" style="width:${total ? count / total * 100 : 0}%" title="${esc(label)}: ${count} search locations"></span>` : '').join('')}</div>
    <div class="sr-band-key">${bands.filter(([, count, cls]) => count || cls !== 'unknown').map(([label, count, cls]) => `<span><i class="${cls}"></i>${esc(label)} <b>${count}</b></span>`).join('')}</div>`
}

function rivals(model, region, state) {
  const pressure = state.rivalLens !== 'regional'
  const rows = (pressure ? region.nearRivals || [] : region.rivals || []).filter(row => row.id !== model.targetId && (pressure ? row.nearAhead : row.top3Appearances) > 0).slice(0, 5)
  return `<section class="sr-rivals"><div class="sr-rival-heading"><div><span class="sr-overline">WHO YOU FACE HERE</span><h3>${pressure ? 'Ahead at your near-top-three locations' : 'Regional top-three leaders'}</h3></div></div>
    <div class="sr-segment sr-rival-switch" role="group" aria-label="Rival comparison"><button data-sr-rivals="pressure" aria-pressed="${pressure}">Local pressure</button><button data-sr-rivals="regional" aria-pressed="${!pressure}">Regional standings</button></div>
    <p class="sr-rival-caption">${pressure ? 'All studied services in this area · appearances ahead where you rank 4–10.' : 'All studied services in this area · ranked by equal-query top-three coverage.'} Compare opens the selected service on the map.</p>
    <ol class="sr-rival-list">${rows.map((rival, index) => {
      const count = number(pressure ? rival.nearAhead : rival.top3Appearances)
      const denominator = number(pressure ? rival.nearDenominator : rival.completeDenominator ?? region.completeDenominator)
      const ratio = pressure ? (denominator ? count / denominator * 100 : 0) : number(rival.top3CoveragePct)
      return `<li><span class="sr-rival-number">${index + 1}</span><div class="sr-rival-name"><strong>${esc(rival.name)}</strong><small>${esc(rival.address || 'Listing address not supplied')}</small><span class="sr-rival-meter"><i style="width:${Math.min(100, ratio)}%"></i></span></div><div class="sr-rival-score"><strong>${pressure ? `${count}<small>/${denominator}</small>` : pct(rival.top3CoveragePct)}</strong>${pressure ? '' : `<small class="sr-score-denominator">${count}/${denominator} pairs</small>`}<button data-sr-rival="${esc(rival.id)}" aria-label="Compare with ${esc(rival.name)} on the map">Compare ↗</button></div></li>`
    }).join('') || '<li class="sr-empty">No qualifying rival comparisons in this cohort. Choose another area or service.</li>'}</ol>
    <p class="sr-footnote">Profiles come from the full observed field. A returned profile still needs a relevance check.</p>
  </section>`
}

function inspector(model, intelligence, research, state) {
  const region = intelligence.regions.find(r => r.id === state.regionId) || intelligence.regions.find(r => r.id === 'core') || intelligence.regions[0]
  const metric = metricFor(region, state.queryId)
  const query = queryName(model, state.queryId)
  const checked = research?.queries?.[state.queryId]
  const pages = (checked?.pages || []).map(page => ({ ...page, safeURL: strategySafeURL(page.url) })).filter(page => page.safeURL)
  return `<section class="sr-section sr-inspector" aria-labelledby="sr-area-title"><div class="sr-area-details">
    <span class="sr-overline">SELECTED AREA</span><h2 id="sr-area-title">${esc(region.label)}</h2>
    <label class="sr-sr-only" for="sr-query">Service to inspect</label><select id="sr-query">${model.queries.map(q => `<option value="${esc(q.id)}" ${q.id === state.queryId ? 'selected' : ''}>${esc(q.name)}</option>`).join('')}</select>
    <div class="sr-area-score"><strong>${metric.complete ? pct(metric[`${state.metric}Pct`]) : '—'}</strong><span>${state.metric === 'top10' ? 'Top 10' : 'Top 3'} coverage<br>${number(metric[state.metric])} of ${metric.complete} complete search locations${metric.unknown ? `<br>${metric.unknown} incomplete` : ''}</span></div>
    ${rankBar(metric, region.count)}
    <div class="sr-area-facts"><div><b>${number(metric.near)}</b><span>ranks 4–10</span></div><div><b>${countValue(metric.serviceGap)}</b><span>service differences</span></div><div><b>${countValue(metric.frontier)}</b><span>beside top-ten results</span></div></div>
    <button class="sr-primary-button" data-sr-inspect>Inspect this area on the map <span>↗</span></button>
    ${pages.length ? `<div class="sr-existing-pages"><span class="sr-overline">EXISTING WEBSITE ASSETS</span>${pages.slice(0, 2).map(page => `<a href="${esc(page.safeURL)}" target="_blank" rel="noopener noreferrer">${esc(page.label)} ↗</a>`).join('')}<p>Review these pages before commissioning more content.</p></div>` : '<p class="sr-footnote">Connect website and job evidence to turn this geographic pattern into a campaign.</p>'}
    <p class="sr-footnote">Service gap: another studied query reaches top 3 at this location while this query ranks 4–10. Beside top ten: ranks 11–30 next to top-ten locations.</p>
  </div>${rivals(model, region, state)}</section>`
}

function investigationCards(model, intelligence, research) {
  const insights = (intelligence.insights || []).slice(0, 3)
  return `<section class="sr-section sr-investigations" aria-labelledby="sr-investigations-title"><div class="sr-section-heading"><div><span class="sr-overline">TURN EVIDENCE INTO A NEXT STEP</span><h2 id="sr-investigations-title">Patterns worth checking</h2><p>These are map findings that support the campaign options, not additional ready-to-launch campaigns.</p></div></div>
    <div class="sr-investigation-grid">${insights.map((insight, index) => {
      const checked = research?.queries?.[insight.queryId]
      const firstPage = (checked?.pages || []).map(page => ({ ...page, safeURL: strategySafeURL(page.url) })).find(page => page.safeURL)
      return `<article class="sr-investigation-card"><span class="sr-card-number">0${index + 1}</span><div class="sr-card-tag">${esc(queryName(model, insight.queryId))}</div><h3>${esc(insight.title)}</h3>
        <p class="sr-card-trigger">${esc(insight.reason)}</p><div class="sr-next-action"><span class="sr-overline">NEXT AGENT CHECK</span><p>${esc(insight.nextAction)}</p></div>
        ${checked?.checkedWebsiteFacts?.[0] ? `<p class="sr-checked-fact"><span>WEBSITE CHECKED</span>${esc(checked.checkedWebsiteFacts[0])}</p>` : ''}
        ${firstPage ? `<a class="sr-source-link" href="${esc(firstPage.safeURL)}" target="_blank" rel="noopener noreferrer">${esc(firstPage.label)} ↗</a>` : ''}
        <button class="sr-card-action" data-sr-campaign="${esc(insight.id)}">Show the supporting locations <span>→</span></button>
      </article>`
    }).join('') || '<p class="sr-empty">No supported investigation cohort is available in this snapshot. Complete the evidence before prioritizing an area.</p>'}</div></section>`
}

function campaignAction(model, research, state) {
  const entry = research?.queries?.[state.queryId], brief = entry?.actionBrief
  if (!brief) return ''
  const url = strategySafeURL(brief.existingUrl)
  return `<section class="sr-section sr-action-brief" aria-labelledby="sr-action-title"><div class="sr-action-main"><span class="sr-overline">WEBSITE CAMPAIGN DRAFT · ${esc(entry.area || 'RESEARCHED SERVICE AREA')}</span><h2 id="sr-action-title">${esc(brief.title)}</h2><p class="sr-footnote">Scope: ${esc(entry.area || 'the researched service area')} · ${esc(queryName(model, state.queryId))}. This website draft is separate from the selected map sector.</p><p class="sr-action-observed">${esc(brief.observed)}</p>
    <div class="sr-action-proposal"><span class="sr-overline">PROPOSED CHANGE</span><p>${esc(brief.action)}</p></div>
    ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">Review the existing page ↗</a>` : ''}
    <p class="sr-footnote">${esc(brief.readiness)}</p></div><div class="sr-action-validation"><span class="sr-overline">WHY THIS CHECK</span><p>${esc(brief.reason)}</p><span class="sr-overline">VALIDATE BEFORE CHANGING</span><ol>${(brief.nextChecks || entry.nextChecks || []).slice(0, 3).map(check => `<li>${esc(check)}</li>`).join('')}</ol><span class="sr-overline">MEASURE THE RESULT</span><p>${esc(brief.success)}</p></div></section>`
}

export function strategyRoomHTML(model, intelligence, research, state = {}) {
  state = { metric: 'top3', regionId: 'core', queryId: model.queries?.[0]?.id, rivalLens: 'pressure', ...state }
  const core = intelligence.regions?.find(region => region.id === 'core')
  const all = intelligence.regions?.find(region => region.id === 'all')
  const totalTop3 = regionTotal(all, 'top3'), coreTop3 = regionTotal(core, 'top3')
  const concentration = totalTop3 ? Math.round(coreTop3 / totalTop3 * 100) : 0
  const topBandLabel = state.metric === 'top10' ? 'top 10' : 'top 3'
  return `<header class="sr-header"><div><span class="sr-overline">LEGENDS GEOGRID / STRATEGY</span><h1 id="sr-dialog-title">${esc(model.name)} <span>Where to compete next</span></h1></div><div class="sr-header-actions"><button data-sr-copy>Copy brief</button><button data-sr-expand aria-label="${state.docked ? 'Expand strategy room' : 'Dock strategy beside map'}">${state.docked ? 'Expand ↗' : 'Split view'}</button><button class="sr-close" data-sr-close aria-label="Close strategy room">${state.docked ? 'Hide' : 'Back to map'} <span>×</span></button></div></header>
    ${state.pointLabel ? `<div class="sr-map-context" role="status"><span>MAP SELECTION</span>${esc(state.pointLabel)}</div>` : ''}
    <div class="sr-body">${!intelligence.available ? '<section class="sr-section sr-empty"><h2>Strategy needs a complete, regular study</h2><p>This snapshot cannot support reliable geographic comparisons. Keep using the measured map and review the study evidence.</p></section>' : `
      <div class="sr-overview"><div class="sr-intro"><span class="sr-overline">YOUR BUSINESS. THE ENTIRE OBSERVED FIELD.</span><h2>Choose a campaign.<br><span>Check the evidence.</span></h2><p>Review the proposed work, then use the map to see where the ranking evidence is strongest.</p></div>
      <div class="sr-summary-grid"><div class="sr-summary-card"><span>Measured footprint</span><strong>${model.points.length.toLocaleString()}</strong><small>search locations · ${model.queries.length} services</small></div><div class="sr-summary-card"><span>Observed field</span><strong>${model.businesses.length.toLocaleString()}</strong><small>profiles, beyond the shortlist</small></div><div class="sr-summary-card sr-summary-accent"><span>Top-three concentration</span><strong>${totalTop3 ? `${concentration}%` : '—'}</strong><small>of your top-three appearances lie within 2 mi</small></div></div></div>
      ${campaignPlansHTML(research, state.queryId)}
      ${heatmap(model, intelligence, state)}
      ${inspector(model, intelligence, research, state)}
      ${research?.campaignPlans?.length ? '' : campaignAction(model, research, state)}
      ${investigationCards(model, intelligence, research)}
      <details class="sr-method"><summary>How to read this strategy</summary><div><p>${esc(typeof intelligence.method === 'object' ? Object.values(intelligence.method).join(' ') : intelligence.method || 'Each service is compared on the same measured search locations. Coverage is the fraction of search locations where the primary profile reaches the selected rank band.')}</p><p>The matrix shows ${topBandLabel} coverage. Geographical area is not population, revenue, customer demand or ranking difficulty. Adjacent observations are correlated; this snapshot does not measure ranking stability.</p><p>Core and directional bands partition the studied circle. Outer areas contain more sampled search locations, so the matrix compares percentages within each area. Missing evidence is not a confirmed absence. No profile beyond the returned top 30 receives an invented rank.</p><p>${esc(research?.summary || 'Website findings, completed jobs, margins and capacity are separate evidence inputs. None is inferred from map color.')}</p></div></details>
    `}<div class="sr-status" role="status" aria-live="polite"></div></div>`
}

export function createStrategyRoom({ mount = document.body, startDocked = false, getModel, getResearch = () => null, getQueryId = () => null, onInspectRegion, onMatchup, onCampaign, onClose, onLayout } = {}) {
  const dialog = document.createElement('dialog')
  dialog.id = 'strategy-room'
  dialog.className = 'strategy-room'
  dialog.setAttribute('aria-labelledby', 'sr-dialog-title')
  mount.append(dialog)
  let state = { metric: 'top3', regionId: 'core', queryId: null, rivalLens: 'pressure' }
  let model, intelligence, opener
  let opened = false, expanded = false
  let forceDock = startDocked
  const wide = matchMedia('(min-width: 1200px)')
  const canSplit = matchMedia('(min-width: 900px)')
  const docked = () => opened && !expanded && (wide.matches || (forceDock && canSplit.matches))
  const currentRegion = () => intelligence.regions.find(r => r.id === state.regionId) || intelligence.regions.find(r => r.id === 'core')
  function render() {
    const scrollTop = dialog.querySelector('.sr-body')?.scrollTop || 0
    const matrixScroll = dialog.querySelector('.sr-matrix-scroll')?.scrollLeft || 0
    const openPlans = new Set([...dialog.querySelectorAll('.campaign-plan[open]')].map(el => el.dataset.planId))
    model = getModel()
    intelligence = strategyIntelligence(model)
    if (!model.queries.some(q => q.id === state.queryId)) state.queryId = model.queries[0]?.id
    if (!intelligence.regions?.some(r => r.id === state.regionId)) state.regionId = 'core'
    state.docked = docked()
    dialog.innerHTML = strategyRoomHTML(model, intelligence, getResearch(), state)
    dialog.querySelectorAll('.campaign-plan').forEach(el => { el.open = openPlans.has(el.dataset.planId) })
    dialog.querySelector('[data-sr-expand]').hidden = !canSplit.matches
    dialog.querySelector('.sr-body').scrollTop = scrollTop
    const matrix = dialog.querySelector('.sr-matrix-scroll')
    if (matrix) matrix.scrollLeft = matrixScroll
  }
  function layout() {
    if (dialog.open) dialog.close()
    dialog.classList.toggle('sr-docked', docked())
    onLayout?.({ open: opened, docked: docked(), expanded, forceDock })
    if (opened) {
      render()
      if (docked()) dialog.show()
      else dialog.showModal()
    }
  }
  function close() {
    if (!opened) return
    opened = false
    layout()
    opener?.focus?.({ preventScroll: true })
    onClose?.()
  }
  function open() {
    if (opened) return
    opener = document.activeElement
    state.queryId = getQueryId() || state.queryId
    opened = true
    layout()
    dialog.querySelector('[data-sr-close]')?.focus()
  }
  function focusAfterRender(selector) {
    render()
    dialog.querySelector(selector)?.focus({ preventScroll: true })
  }
  dialog.addEventListener('cancel', event => { event.preventDefault(); close() })
  dialog.addEventListener('keydown', event => { if (event.key === 'Escape' && docked()) { event.preventDefault(); close() } })
  wide.addEventListener('change', () => { if (opened) layout() })
  canSplit.addEventListener('change', () => { if (opened) layout() })
  const payload = () => ({ regionId: state.regionId, queryId: state.queryId, originIds: currentRegion()?.originIds || [] })
  const handoff = (callback, value) => { if (!docked()) close(); callback?.(value) }
  dialog.addEventListener('click', async event => {
    if ((!docked() && event.target === dialog) || event.target.closest('[data-sr-close]')) { close(); return }
    if (event.target.closest('[data-sr-expand]')) {
      if (docked()) { expanded = true; forceDock = false }
      else { expanded = false; forceDock = true }
      layout(); dialog.querySelector('[data-sr-expand]').focus(); return
    }
    const metric = event.target.closest('[data-sr-metric]')
    if (metric) { state.metric = metric.dataset.srMetric; focusAfterRender(`[data-sr-metric="${state.metric}"]`); return }
    const cell = event.target.closest('[data-sr-region]')
    if (cell) {
      state.regionId = cell.dataset.srRegion; state.queryId = cell.dataset.srQuery
      focusAfterRender(`[data-sr-region="${CSS.escape(state.regionId)}"][data-sr-query="${CSS.escape(state.queryId)}"]`)
      if (docked()) onInspectRegion?.(payload())
      return
    }
    if (event.target.closest('[data-sr-all]')) { state.regionId = 'all'; focusAfterRender('[data-sr-all]'); if (docked()) onInspectRegion?.(payload()); return }
    const rivalLens = event.target.closest('[data-sr-rivals]')
    if (rivalLens) { state.rivalLens = rivalLens.dataset.srRivals; focusAfterRender(`[data-sr-rivals="${state.rivalLens}"]`); return }
    if (event.target.closest('[data-sr-inspect]')) { handoff(onInspectRegion, payload()); return }
    const rival = event.target.closest('[data-sr-rival]')
    if (rival) { handoff(onMatchup, { ...payload(), rivalId: rival.dataset.srRival }); return }
    const preparedPlan = event.target.closest('[data-campaign-baseline]')
    if (preparedPlan) {
      const action = campaignPlanMapAction(getResearch(), preparedPlan.dataset.campaignBaseline)
      if (action && model.queries.some(query => query.id === action.queryId && query.name === getResearch()?.queries?.[action.queryId]?.query)) {
        state.queryId = action.queryId; state.regionId = 'all'
        handoff(onCampaign, action)
        if (opened) render()
      }
      return
    }
    const campaign = event.target.closest('[data-sr-campaign]')
    if (campaign) {
      const insight = intelligence.insights.find(i => i.id === campaign.dataset.srCampaign)
      if (insight) { handoff(onCampaign, { campaignId: insight.id, lens: insight.id.startsWith('service-gap:') ? 'serviceGap' : insight.id.startsWith('frontier:') ? 'frontier' : 'advance', queryId: insight.queryId, regionId: insight.regionId, originIds: insight.originIds || [], insight }) }
      return
    }
    if (event.target.closest('[data-sr-copy]')) {
      const region = currentRegion(), metric = metricFor(region, state.queryId), research = getResearch()?.queries?.[state.queryId]
      const brief = `${model.name} — strategy investigation\n${region?.label}: ${queryName(model, state.queryId)}\nTop 3: ${metric.top3}/${metric.complete}; top 10: ${metric.top10}/${metric.complete}; ranks 4–10: ${metric.near}.\nComplete search locations: ${metric.complete}/${region?.count}; incomplete: ${metric.unknown}.\n${research ? `Separate website investigation (${research.area || 'researched service area'}): ${research.nextChecks?.[0] || ''}` : 'Review local rivals and service relevance before choosing a campaign.'}\n${research?.pages?.map(p => strategySafeURL(p.url)).filter(Boolean).join('\n') || ''}\nRanked reach, not customer demand. Validate actual jobs, margin and capacity.`
      try { await navigator.clipboard.writeText(brief); dialog.querySelector('.sr-status').textContent = 'Brief copied. Bring it to your agent or campaign notes.' }
      catch { dialog.querySelector('.sr-status').textContent = 'Clipboard unavailable. The evidence and next checks remain visible here.' }
    }
  })
  dialog.addEventListener('change', event => {
    if (event.target.id === 'sr-query') { state.queryId = event.target.value; focusAfterRender('#sr-query'); if (docked()) onInspectRegion?.(payload()) }
  })
  return { open, close, toggle() { if (opened) close(); else open() }, refresh() { if (opened) render() },
    sync(selection) {
      const changed = Object.entries(selection).some(([key, value]) => state[key] !== value)
      Object.assign(state, selection)
      if (opened && changed) render()
    },
  }
}
