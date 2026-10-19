import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import sample from './data/home-slice-study.json'
import sampleResearch from './data/home-slice-campaign-research.json'
import sampleNameReview from './data/home-slice-name-review.json'
import { normalizeStudy, observationFor, businessMetrics, businessLeaderboard, businessPage, rankPresentation, RANK_COLORS, RANK_OPACITIES, rankFillOpacity } from './study-model.js'
import { cellSpacings, destination, blendColor, latticeIntersections } from './map-geometry.js'
import { installWheelZoom } from './wheel-zoom.js'
import { BASEMAPS, createBasemapSwitcher } from './basemap-switcher.js'
import { RankCanvasLayer } from './rank-canvas.js'
import { localLeaders, profileColor } from './local-leaders.js'
import { winnerAt } from './leader-colors.js'
import { distanceLabel, distanceText, distanceRings } from './distance-units.js'
import { territoryIntelligence } from './territory-intelligence.js'
import { strategyIntelligence, strategyMatchup } from './strategy-engine.js'
import { createStrategyRoom } from './strategy-room.js'
import { createNameReview } from './name-review.js'
import { resolveStudyAttachment } from './review-attachment.js'
import './name-review.css'
import { MATCHUP_STYLES, matchupLabel, regionPanelHTML, matchupPanelHTML } from './strategy-map-panel.js'
import './strategy-room.css'
import { CAMPAIGN_LENSES, TERRITORY_COLORS, TERRITORY_LABELS, cellMatchesLens, campaignAreas, campaignPanelHTML, campaignPlanMapAction, validateCampaignResearch } from './campaign-panel.js'
import './companion.css'

const $ = selector => document.querySelector(selector)
const escape = text => String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
const formatDate = value => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }) : 'Not recorded'
const params = new URLSearchParams(location.search)
const initialParams = new URLSearchParams(location.search)
let model = normalizeStudy(sample)
const state = { query: 'q1', business: 'TARGET', point: null, view: 'visibility', tab: 'factions', region: 'all', rival: null, rings: true, translucent: false, blends: true, coverage: true, units: 'mi', leaderMinimum: initialParams.get('leaders') === 'all' ? 1 : 3 }
const fieldBrowser = { scope: 'shortlist', search: '', page: 0 }
const campaign = { lens: 'overview', area: null, research: null }
let investigationIds = null
let investigationId = null
let scaleControl, scaleUnits
let map, pointsLayer, basesLayer, rangeLayer, coverageLayer
let strategyRoom
let nameReview
let preferredBasemap = 'osm-legends'
try { preferredBasemap = localStorage.getItem('geogrid-basemap') || preferredBasemap } catch { /* Use default. */ }
state.basemap = BASEMAPS.some(s => s.id === initialParams.get('basemap')) ? initialParams.get('basemap') :
  BASEMAPS.some(s => s.id === preferredBasemap) ? preferredBasemap : 'osm-legends'
let spacing = 0, gridCorners = [], cancelWheelZoom = () => {}
let followStudyBounds = true, fittingStudy = false
const colorFor = id => profileColor(model, id)
const names = { visibility: 'Rankings', factions: 'Local leaders', strike: 'Strike zones', campaigns: 'Campaigns', 'keyword-stuffing': 'Keyword stuffing', matchup: 'Head-to-head' }
const explanations = {
  'keyword-stuffing': 'Investigate profile names. Compare evidence and prepare a review.',
  visibility: 'Rank by color. Hover for rank; click for results.',
  factions: 'Who ranks first. Colors identify businesses.',
  strike: 'Ranks 4–10: opportunities to investigate.',
  campaigns: 'Find a measured foothold, compare opponents, choose a next check.',
  matchup: 'Compare two profiles in the same searches. Hover for both ranks.',
}

$('#app').innerHTML = `
  <header class="app-bar"><a class="wordmark" href="./"><span class="brand-symbol" aria-hidden="true">✳</span> legends-geogrid <span class="edition">FIELD NOTES</span></a>
    <div class="app-actions"><button id="open-strategy" class="strategy-launch" aria-expanded="false" aria-controls="strategy-room">Strategy room</button><button id="open-study" class="quiet-button">Open study <span aria-hidden="true">↗</span></button></div>
    <input id="study-file" type="file" accept=".json,application/json" hidden>
  </header>
  <main>
    <section class="study-heading">
      <div><div class="eyebrow">LOCAL SEARCH · COMPETITIVE EXPLORER</div><h1 id="study-name"></h1><p id="study-location"></p></div>
      <div class="study-stamp"><span class="status-dot"></span><span id="study-kind"></span><small id="study-date"></small></div>
    </section>
    <section class="query-bar"><label for="query">Search query</label><select id="query"></select><select id="sampling-view" aria-label="Study footprint" hidden></select><span id="query-scope"></span><button id="evidence-toggle" class="quiet-button" aria-expanded="false">Details</button><button id="copy-brief" class="quiet-button">Copy context</button></section>
    <section class="workspace">
      <div class="map-column">
        <div class="map-heading"><div class="view-tabs" role="group" aria-label="Map lens">
          <button data-view="visibility">Rankings</button><button data-view="factions">Local leaders</button><button data-view="campaigns">Campaigns</button><button data-view="keyword-stuffing" aria-controls="name-review-host">Keyword stuffing</button><button data-view="matchup" hidden>Head-to-head</button>
        </div><div class="map-heading-actions"><select id="basemap" aria-label="Map source">${BASEMAPS.map(s => `<option value="${s.id}">${s.name}</option>`).join('')}</select><button id="fit" class="quiet-button" title="Show every sampled location">Fit study</button></div></div>
        <div class="map-description" id="view-description"></div>
        <div id="name-review-host" hidden></div>
        <div id="map"><div class="map-badge"><span id="map-business"></span><small id="map-subtitle">Organic Maps rankings</small></div>
          <div id="basemap-status" class="basemap-status" role="status" hidden><p></p><div><button id="retry-basemap">Retry map</button><button id="use-default-basemap">Use OpenStreetMap</button></div></div>
          <div class="map-options" role="group" aria-label="Map appearance"><button id="coverage-dots" aria-pressed="true">Coverage dots</button><button id="distance-rings" aria-pressed="true">Distance rings</button><button id="translucent" aria-pressed="false">Translucent markers</button><button id="corner-blends" aria-pressed="true">Gradient diamonds</button></div>
        </div>
        <div class="map-legend" id="legend"></div>
        <div class="finding-strip"><span class="eyebrow">READ THE MAP</span><p id="finding"></p><button id="inspect-near" class="text-button">Inspect a near miss →</button></div>
      </div>
      <aside class="sidebar">
        <div class="side-tabs" role="group" aria-label="Study details"><button data-tab="strategy" hidden>Area</button><button data-tab="campaigns">Campaigns</button><button data-tab="factions">Businesses</button><button data-tab="location">Location</button><button data-tab="study">Study</button></div>
        <div id="side-content"></div>
      </aside>
    </section>
    <footer><span>Built for the conversation. Select a business, explore a location, bring the evidence back to your agent.</span><span id="footer-state"></span></footer>
  </main>
  <div id="toast" role="status" aria-live="polite"></div>`

const workbench = document.createElement('div')
workbench.className = 'workbench'
$('#app').insertBefore(workbench, $('main'))
workbench.append($('main'))
workbench.insertAdjacentHTML('beforeend', '<div id="strategy-divider" role="separator" aria-label="Resize strategy panel" aria-orientation="vertical" aria-valuemin="35" aria-valuemax="60" aria-valuenow="50" tabindex="0"></div><div id="strategy-host"></div>')

function syncURL() {
  for (const key of ['query', 'business', 'point', 'view', 'region', 'rival']) {
    if (state[key]) params.set(key, state[key]); else params.delete(key)
  }
  params.set('rings', state.rings ? '1' : '0')
  params.set('translucent', state.translucent ? '1' : '0')
  params.set('blends', state.blends ? '1' : '0')
  params.set('coverage', state.coverage ? '1' : '0')
  params.set('units', state.units)
  params.set('leaders', state.leaderMinimum === 1 ? 'all' : 'recurring')
  params.set('basemap', state.basemap)
  if (state.view === 'campaigns') {
    params.set('lens', campaign.lens)
    if (campaign.area) params.set('area', campaign.area); else params.delete('area')
  } else { params.delete('lens'); params.delete('area') }
  if (state.view === 'campaigns' && investigationIds && investigationId) params.set('investigation', investigationId)
  else params.delete('investigation')
  history.replaceState(null, '', `${location.pathname}?${params}`)
}

function announce(message) {
  $('#toast').textContent = message
  $('#toast').classList.add('visible')
  clearTimeout(announce.timer)
  announce.timer = setTimeout(() => $('#toast').classList.remove('visible'), 6000)
}

function selectBusiness(id) {
  if (!model.businesses.some(b => b.id === id)) throw new Error('Unknown business')
  state.business = id
  state.region = 'all'
  investigationIds = null
  if (['campaigns', 'matchup'].includes(state.view)) { state.view = 'visibility'; state.tab = 'factions'; campaign.area = null; state.region = 'all'; state.rival = null }
  render()
}

function selectPoint(id) {
  if (!model.points.some(p => p.id === id)) throw new Error('Unknown location')
  state.point = id
  if (state.region !== 'all' && workbench.classList.contains('strategy-docked')) {
    state.region = strategyIntelligence(model).regions.find(r => r.id !== 'all' && r.originIds.includes(id))?.id || 'all'
  }
  state.tab = 'location'
  workbench.classList.add('evidence-open')
  render()
}

function setView(view) {
  if (!names[view]) throw new Error('Unknown view')
  if (view === 'matchup' && !state.rival) { strategyRoom.open(); return }
  if (view !== 'matchup') { state.region = 'all'; state.rival = null }
  if (view === 'keyword-stuffing') strategyRoom?.close()
  state.view = view
  investigationIds = null
  if (view === 'campaigns') { state.business = model.targetId; state.tab = 'campaigns'; state.point = null }
  else if (view === 'factions') state.tab = 'factions'
  else if (state.tab === 'campaigns') state.tab = 'factions'
  render()
  $('#side-content').scrollTop = 0
}

function setCampaignLens(lens) {
  if (!CAMPAIGN_LENSES[lens]) throw new Error('Unknown campaign lens')
  campaign.lens = lens
  campaign.area = null
  investigationIds = null
  state.region = 'all'
  state.rival = null
  state.point = null
  state.business = model.targetId
  state.view = 'campaigns'
  state.tab = 'campaigns'
  render()
  $('#side-content').scrollTop = 0
}

function focusCampaignArea(id) {
  const area = campaignAreas(territoryIntelligence(model, state.query), campaign.lens).find(a => a.id === id)
  if (!area) throw new Error('Unknown campaign area')
  campaign.area = id
  investigationIds = null
  state.point = null
  state.tab = 'campaigns'
  cancelWheelZoom()
  followStudyBounds = false
  render()
  const members = new Set(area.originIds)
  const points = model.points.filter(p => members.has(p.id))
  if (points.length) map.fitBounds(points.map(p => [p.lat, p.lng]), { padding: [65, 70], maxZoom: 14, animate: false })
}

function selectedRegion() {
  return strategyIntelligence(model).regions?.find(r => r.id === state.region)
}

function fitOrigins(ids) {
  const members = new Set(ids)
  const points = model.points.filter(p => members.has(p.id))
  if (!points.length) return
  cancelWheelZoom()
  followStudyBounds = false
  map.fitBounds(points.map(p => [p.lat, p.lng]), { padding: [55, 60], maxZoom: 14, animate: false })
}

function inspectRegion({ regionId = 'all', queryId = state.query, rivalId = null }) {
  const region = strategyIntelligence(model).regions?.find(r => r.id === regionId)
  if (!region || !model.queries.some(q => q.id === queryId)) throw new Error('Unknown study area or query')
  if (rivalId && (!model.businesses.some(b => b.id === rivalId) || rivalId === model.targetId)) throw new Error('Choose a distinct observed rival')
  Object.assign(state, { region: regionId, query: queryId, rival: rivalId, business: model.targetId,
    view: rivalId ? 'matchup' : 'visibility', tab: 'strategy', point: null })
  campaign.area = null
  investigationIds = null
  render()
  fitOrigins(region.originIds)
}

async function loadCampaignResearch(fallbackInput = null) {
  campaign.research = null
  if (model.limited) return
  const currentModel = model
  try {
    const url = await resolveStudyAttachment({ attachment: 'campaign_research',
      explicit: params.get('research'), studyURL: params.get('study'), model: currentModel, baseURL: location.href })
    if (model !== currentModel) return
    let input = null
    if (url) {
      const response = await fetch(url)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      input = await response.json()
      if (model !== currentModel) return
    } else if (fallbackInput && !params.get('research') && !params.get('study')) {
      input = fallbackInput
    } else {
      return
    }
    const research = validateCampaignResearch(input, currentModel)
    if (model === currentModel) { campaign.research = research; render(); strategyRoom?.refresh?.() }
  } catch (error) { if (model === currentModel) announce(`Campaign research unavailable: ${error.message}`) }
}

function metricHTML(b) {
  const m = businessMetrics(model, state.query, b.id)
  return `<div class="metrics"><div><strong>${m.top3Pct.toFixed(1)}<small>%</small></strong><span>Top 3 coverage</span></div>
    <div><strong>${m.found}<small>/${model.points.length}</small></strong><span>Locations found</span></div>
    <div><strong>${m.average?.toFixed(1) ?? '—'}</strong><span>Avg. when found</span></div></div>`
}

function renderBusinesses() {
  if (state.view === 'factions') return renderLeaders()
  const selected = model.businesses.find(b => b.id === state.business)
  const shortlistCount = model.businesses.filter(b => b.shortlisted !== false).length
  const result = businessPage(model, state.query, fieldBrowser)
  fieldBrowser.page = result.page
  const selectedPosition = businessLeaderboard(model, state.query).find(row => row.business.id === selected.id)?.position
  return `<div class="side-intro"><div class="eyebrow">THE COMPETITIVE FIELD</div><h2>${model.businesses.length} observed profiles</h2>
    <p>Field rank uses top 3 coverage for this query. Observed results; relevance and service area need review.</p>
    <div class="field-scope" role="group" aria-label="Business list scope"><button data-field-scope="shortlist" aria-pressed="${fieldBrowser.scope === 'shortlist'}">Shortlist · ${shortlistCount}</button><button data-field-scope="all" aria-pressed="${fieldBrowser.scope === 'all'}">All observed · ${model.businesses.length}</button></div>
    <label class="field-search-label" for="field-search">Find a business or address</label><input id="field-search" type="search" value="${escape(fieldBrowser.search)}" placeholder="Search all observed profiles" autocomplete="off">
    <button class="text-button" data-business="${escape(model.targetId)}">View primary business</button></div>
    <div class="business-list">${result.rows.map(({ business: b, metrics: m, position }) => {
      return `<button class="business-row ${b.target ? 'primary' : ''} ${b.id === state.business ? 'selected' : ''}" data-business="${escape(b.id)}" aria-pressed="${b.id === state.business}">
        <span class="leaderboard-position" aria-label="Observed field position ${position}" title="Rank ${position} across the full observed field">${position}</span>
        <span class="business-dot" style="--business-color:${state.view === 'factions' && (b.shortlisted !== false || b.id === state.business) ? colorFor(b.id) : b.id === state.business ? '#e3232d' : '#707070'}">${b.target ? '◎' : ''}</span>
        <span class="business-info"><span class="business-name">${escape(b.name)}</span>${b.address ? `<span class="business-address">${escape(b.address)}</span>` : ''}<span class="mini-track"><span style="width:${m.top3Pct}%"></span></span></span>
        <span class="business-score">${m.top3Pct.toFixed(1)}<small>%</small>${b.target ? '<em>PRIMARY</em>' : b.discovered ? '<em>NEW</em>' : ''}</span>
      </button>`
    }).join('') || '<p class="list-caption">No matching profiles.</p>'}</div>
    <div class="field-pagination"><button data-field-page="-1" ${result.page === 0 ? 'disabled' : ''}>Previous</button><span>${result.total} profiles · ${result.page + 1}/${result.pages}</span><button data-field-page="1" ${result.page + 1 >= result.pages ? 'disabled' : ''}>Next</button></div>
    <p class="list-caption">Positions refer to all ${model.businesses.length} observed profiles, including when filtered. Ties use top 20 visibility points (21 − rank); equal scores share a position. The shortlist is a saved comparison set, not the whole market.</p>
    <div class="selection-card"><span class="eyebrow">SELECTED BUSINESS · FIELD #${selectedPosition}</span><h3>${escape(selected.name)}</h3>${metricHTML(selected)}
      ${selected.address ? `<p>${escape(selected.address)}</p>` : ''}
      <p>${selected.rating ? `${escape(selected.rating)} rating · ${escape(selected.reviews ?? 'Unknown')} reviews` : 'Profile details not included in this sample.'}</p>
      ${selected.selection ? `<p>Saved shortlist selection #${escape(selected.selection.position)} · all-query visibility score ${escape(selected.selection.visibility_score.toLocaleString())}<br>${escape(selected.selection.categories?.join(' · ') || '')}</p>` : '<p>Observed profile. Appearance in search results does not establish service fit or business relevance.</p>'}</div>`
}

function renderLeaders() {
  const leaders = localLeaders(model, state.query, state.leaderMinimum)
  const rows = leaders.rows.filter(r => r.major || r.business.id === state.business)
  const selectedExtra = rows.find(r => !r.major)
  const coloredPoints = leaders.coloredPoints + (selectedExtra?.wins || 0)
  return `<div class="side-intro"><div class="eyebrow">LOCAL LEADERS</div><h2>${rows.length} highlighted winners</h2>
    <div class="field-scope" role="group" aria-label="Leader coverage"><button data-leader-minimum="3" aria-pressed="${state.leaderMinimum === 3}">Recurring · 3+ wins</button><button data-leader-minimum="1" aria-pressed="${state.leaderMinimum === 1}">All winners</button></div>
    <p>Neighboring groups get contrasting colors. Matching IDs identify each business across queries. Bases can be outside the circle.</p>
    <div class="leader-actions"><button class="text-button" data-fit-leaders>Fit circle + leader bases</button>
    <button class="text-button" data-open-name-review>Review business titles →</button></div>
    <p>${coloredPoints}/${model.points.length} points colored (${(100 * coloredPoints / model.points.length).toFixed(1)}%). ${state.leaderMinimum === 3 ? `One- and two-point winners stay hollow${selectedExtra ? ', except the selected business' : ''}; All winners reveals them.` : 'Every identified winner is colored. Dashed points lack usable first-place evidence.'}</p></div>
    <div class="business-list">${rows.map(r => `<button class="business-row ${r.business.target ? 'primary' : ''} ${r.business.id === state.business ? 'selected' : ''}" data-leader="${escape(r.business.id)}">
      <span class="leader-id" style="--business-color:${r.color}">${r.badge}</span>
      <span class="business-info"><span class="business-name">${escape(r.business.name)}</span>
      <span class="business-address">${escape(r.business.address || 'Address not supplied')}</span>
      <span class="business-location-status">${r.hasBase ? r.outside ? 'Base outside circle' : 'Supplied base' : 'Base coordinates unavailable'}${!r.major ? ' · selected exception' : ''}</span></span>
      <span class="business-score">${r.wins}<small> wins</small></span></button>`).join('')}</div>
    <p class="list-caption">Select a leader to fit its base and strongest winning cluster. Only bases more than 2 miles beyond the circle get a matching connector. Lines are not routes or territory boundaries. Colors identify profiles, not ranking strength.</p>`
}

function fitLeaders(id = null) {
  const leaders = localLeaders(model, state.query, state.leaderMinimum)
  const rows = leaders.rows.filter(r => id ? r.business.id === id : r.major)
  const locations = id ? [] : model.points.map(p => [p.lat, p.lng])
  for (const r of rows) {
    if (r.hasBase) locations.push([r.business.lat, r.business.lng])
    if (r.center) locations.push([r.center.lat, r.center.lng])
  }
  if (!locations.length) return
  cancelWheelZoom()
  followStudyBounds = false
  map.fitBounds(locations, { padding: [70, 70], maxZoom: 13, animate: false })
}

function renderLocation() {
  const p = model.points.find(p => p.id === state.point)
  if (!p) return `<div class="side-intro empty"><span class="empty-icon">⌖</span><h2>Start with a location</h2><p>Select any map point to see who appeared there and compare the actual returned rankings.</p></div>`
  const o = p.observations[state.query]
  const selected = model.businesses.find(b => b.id === state.business)
  const rank = observationFor(model, p, state.query, state.business)
  return `<div class="side-intro"><div class="eyebrow">SEARCH LOCATION ${escape(p.id)}</div><h2>${p.distance != null ? `${distanceLabel(p.distance, state.units)} from primary` : 'Measured search origin'}</h2>
    <p class="coordinates">${p.lat.toFixed(5)}, ${p.lng.toFixed(5)}</p><p>Observed ${escape(formatDate(o?.sampledAt))}${o?.collectionMethod ? ` · ${o.collectionMethod === 'standard' ? 'Standard queue' : 'Earlier Live archive'}` : ''}</p></div>
    <div class="location-result"><span class="eyebrow">${escape(selected.name)}</span><strong>${escape(rank.label)}</strong></div>
    <div class="query-comparison"><span class="eyebrow">SAME LOCATION · ALL QUERIES</span>${model.queries.map(q => `<button data-location-query="${escape(q.id)}" aria-pressed="${q.id === state.query}"><span>${escape(q.name)}</span><strong>${escape(observationFor(model, p, q.id, state.business).label)}</strong></button>`).join('')}</div>
    <div class="results-heading">Returned organic results <span>${o?.items.length ?? 0}</span></div>
    <ol class="result-list">${(o?.items || []).map(i => `<li class="${i.id === state.business ? 'highlight' : ''}"><span class="result-rank">${i.rank}</span>
      <div><strong>${escape(i.name)}</strong><small>${i.address ? `${escape(i.address)}<br>` : ''}${i.rating ? `${escape(i.rating)} ★ · ${escape(i.reviews ?? '?')} reviews` : 'Saved result'}</small></div></li>`).join('')}</ol>
    <p class="list-caption">Ranks describe this query at this location. Reviews and distance alone do not explain why a business ranks.</p>`
}

function renderStudy() {
  const m = businessMetrics(model, state.query, state.business)
  return `<div class="side-intro"><div class="eyebrow">EVIDENCE & DEFINITIONS</div><h2>What this map tells us</h2></div>
    <div class="study-notes">
      <h3>Rankings</h3><p>Ten bright shades run from pure cyan at rank 1 through green to pure yellow at rank 10. Opacity falls evenly from 100% at rank 1 to 75% at rank 10. Rank 11 switches to pure red at 25% opacity. Ranks 12–30 retain pure red and fade evenly to 2% opacity at rank 30. Translucent markers multiplies top-ten opacity by 45% (45% at rank 1 to 33.75% at rank 10); the red opacity scale stays unchanged. Rank-one cells have a prominent pulsing cyan halo and eight staggered white sparkles around their edges, marking the highest possible position at that location. Reduced motion keeps a static halo and sparkles. Gradient diamonds blend both color and opacity. Hollow stop signs indicate absence from the top 30; dashed outlines indicate incomplete evidence. Hover for rank and click for returned results.</p>
      <h3>Gradient diamonds</h3><p>Diamonds blend neighboring stop-sign colors, including intersections with two or three measured corners along a radial edge. Missing corners and incomplete results contribute transparency. Diamonds are clipped to the study circle. They are visual blends, not additional searches or predicted ranks. Translucent markers reveals more of the streets.</p>
      <h3>Distance rings</h3><p>Rings measure straight-line distance from the primary business, which anchors the study footprint. Selecting a rival changes rankings without moving the study center. Distances and guides are shown in miles; measured locations stay fixed. Rings are reference distances, not ranking or service-area boundaries.</p>
      <h3>Local leaders</h3><p>Recurring winners have at least three first places; All winners also includes one- and two-point profiles. Both ignore shortlist and base distance. Colors maximize separation between neighboring winners across all queries; matching IDs distinguish profiles when colors recur. Smaller winners remain hollow in Recurring mode, except the selected profile. Only bases more than 2 miles beyond the circle get a dashed connector to their largest connected winning cluster. Missing base coordinates are never inferred from rankings. This view measures first place, not market share.</p>
      <h3>Business locations</h3><p>The white outline marks the selected business base. Local leaders uses diamonds for supplied business locations. Estimated or missing locations are omitted. A location is not proof of ranking dominance.</p>
      <h3>Strike zones</h3><p>Observed ranks 4–10: a useful shortlist for investigation. No score predicts how easy it will be to improve.</p>
      <h3>Study footprint</h3><p>${escape(distanceText(model.sampling?.description || (model.geometry === 'competitive_irregular' ? 'Exploratory irregular sampling around the primary business and competitors.' : 'Saved search locations.'), state.units))} Every compared business and query uses the same locations. Each point retains its measured coordinate. Unsampled areas stay unmeasured.</p>
      <h3>Missing evidence</h3><p>${m.unknown} of ${model.points.length} locations have incomplete or unavailable evidence for the selected business. Amber dashed points are not confirmed ranking failures.</p>
      <h3>Coverage dots</h3><p>Visible hollow outlines mark searched locations where this business was not returned in the top 30. Amber dashed outlines mark incomplete evidence. Neither has a colored fill. Coverage dots can be hidden without changing the evidence or rankings.</p>
      <h3>Search window</h3><p>${model.controls?.search_this_area === true ? 'This archive used Search this area. Its rectangular Google viewport can exclude businesses abruptly. Do not interpret those cutoffs as a competitive or service boundary.' : model.controls?.search_this_area === false ? 'Search this area is disabled, allowing Google to return listings beyond its displayed window. Zoom and the search settings still affect results; these ranks describe this Maps search experience.' : 'Search-window controls were not recorded in this archive.'} ${model.controls?.zoom ? `Collection zoom: ${escape(model.controls.zoom)}. This is separate from the zoom used to view this map.` : ''}</p>
      <h3>Radius & resolution</h3><p>${model.sampling?.radius_km ? `${distanceLabel(model.sampling.radius_km, state.units)} radius centered on the primary profile. ` : 'This archive uses its original collection footprint. '}${model.sampling?.spacing_km ? `${distanceLabel(model.sampling.spacing_km, state.units, 2)} spacing between neighboring search origins. ` : ''}Spacing is chosen by this study, not a fixed provider limit. Smaller spacing means more searches. The provider receives a coordinate and a separate Maps zoom setting.</p>
      ${model.evidence?.composition ? `<h3>Scan cost</h3><p>${model.points.length * model.queries.length} shared searches on this footprint. A fresh scan using Standard queue is estimated at $${model.evidence.composition.fresh_standard_cost_usd.toFixed(3)}. This expansion cost $${model.evidence.composition.new_collection_cost_usd.toFixed(4)}, including retries of short result sets; ${model.evidence.composition.reused_observations} observations reuse the earlier archive. All new searches used Standard queue. Earlier archived observations used Live. Ten business profiles share each search; business research is separate.</p>` : model.evidence?.view_equivalent_scan_cost_usd != null ? `<h3>Scan cost</h3><p>This footprint: ${model.points.length * model.queries.length} shared searches; $${model.evidence.view_equivalent_scan_cost_usd.toFixed(3)} at the source scan's actual per-request rate. One request returns rankings for multiple businesses, so ten profiles do not multiply the cost by ten. ${model.evidence.export_is_subset ? `Reuses saved responses from the $${model.evidence.run_total_cost_usd.toFixed(3)} wider scan; no new collection charge.` : ''} Business research is separate.</p>` : ''}
      <h3>Collection context</h3><p>${model.points.length} locations · ${model.queries.length} queries · ${model.depth ? `requested depth ${model.depth}` : 'depth not recorded'}.
      ${model.evidence?.observed_from ? `Observed ${escape(formatDate(model.evidence.observed_from))} through ${escape(formatDate(model.evidence.observed_to))}. Provider timestamps saved for ${escape(model.evidence.observations_with_timestamp)} of ${escape(model.evidence.total_observations)} searches.` : model.limited ? 'Bundled historical sample. Rival ranks are limited to saved top results; identities use saved names.' : 'Saved study. The generated date is the export date, not a verified observation time. Consult the raw study for collection timestamps and settings.'}</p>
      ${model.controls ? `<h3>Common search controls</h3><p>Maps · ${escape(model.controls.device)} · ${escape(model.controls.language_code)} · ${escape(model.controls.se_domain)} · zoom ${escape(model.controls.zoom)}. Every business is compared at the same origins for each query.</p>` : ''}
      ${model.evidence?.roster_policy ? `<h3>Competitor selection</h3><p>${escape(model.evidence.roster_policy)}</p>` : ''}
      <h3>Coverage denominator</h3><p>Top 3 locations divided by all sampled locations. Average rank uses only locations where found. Neither is market share or customer demand.</p>
    </div>`
}

function render() {
  const reviewing = state.view === 'keyword-stuffing'
  const wasReviewing = $('.workspace').classList.contains('keyword-review-active')
  $('.workspace').classList.toggle('keyword-review-active', reviewing)
  $('#name-review-host').hidden = !reviewing
  if (reviewing && !nameReview?.getState().open) nameReview?.open()
  else if (!reviewing && nameReview?.getState().open) nameReview.close()
  if (wasReviewing && !reviewing) requestAnimationFrame(() => map.invalidateSize({ pan: false }))
  if (scaleUnits !== state.units) {
    scaleControl?.remove()
    scaleControl = L.control.scale({ position: 'bottomleft', imperial: true, metric: false }).addTo(map)
    scaleUnits = state.units
  }
  const selected = model.businesses.find(b => b.id === state.business)
  const m = businessMetrics(model, state.query, state.business)
  $('#study-name').textContent = model.name
  $('#study-location').textContent = model.location
  $('#study-kind').textContent = model.kind
  $('#study-date').textContent = model.evidence?.observed_from ? `Observed ${formatDate(model.evidence.observed_from)}` : model.generatedAt ? `Exported ${new Date(model.generatedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}` : 'Historical proof · date unavailable'
  $('#query').innerHTML = model.queries.map(q => `<option value="${escape(q.id)}" ${q.id === state.query ? 'selected' : ''}>${escape(q.name)}</option>`).join('')
  $('#query-scope').textContent = `${model.points.length} locations · ${model.queries.length} ${model.queries.length === 1 ? 'query' : 'queries'}`
  const views = model.studyViews || []
  $('#sampling-view').hidden = !views.length
  $('#sampling-view').innerHTML = views.map(v => `<option value="${escape(v.url)}" ${params.get('study') === v.url ? 'selected' : ''}>${escape(distanceText(v.label, state.units))}</option>`).join('')
  $('#map-business').textContent = state.view === 'factions' ? 'Local leaders' : state.view === 'campaigns' ? `${model.name} · ${CAMPAIGN_LENSES[campaign.lens].label}` : selected.name
  $('#map-subtitle').textContent = distanceText(model.sampling?.description || (model.geometry === 'competitive_irregular' ? 'Exploratory locations · irregular sampling' : 'Measured search locations'), state.units) + (state.view === 'factions' ? '' : ' · ◎ business base')
  const archiveWarning = model.controls?.search_this_area === true
    ? 'Viewport-restricted archive: straight edges may reflect the Google search window, not competitive reach.' : ''
  $('#view-description').innerHTML = (archiveWarning ? `<span class="archive-warning">${archiveWarning}</span>` : '')
    + `<span class="mode-description" title="${escape(state.view === 'campaigns' ? CAMPAIGN_LENSES[campaign.lens].description : explanations[state.view])}">${escape(state.view === 'campaigns' ? CAMPAIGN_LENSES[campaign.lens].description : explanations[state.view])}</span>`
  $('#coverage-dots').setAttribute('aria-pressed', state.coverage)
  $('#distance-rings').setAttribute('aria-pressed', state.rings)
  $('#translucent').setAttribute('aria-pressed', state.translucent)
  $('#corner-blends').setAttribute('aria-pressed', state.blends)
  $('#corner-blends').disabled = !gridCorners.length || state.view !== 'visibility'
  $('#map').classList.toggle('translucent-cells', state.translucent)
  document.querySelectorAll('[data-view]').forEach(b => b.setAttribute('aria-pressed', b.dataset.view === state.view))
  document.querySelectorAll('[data-tab]').forEach(b => b.setAttribute('aria-pressed', b.dataset.tab === state.tab))
  $('[data-view="matchup"]').hidden = state.view !== 'matchup'
  $('[data-tab="strategy"]').hidden = state.region === 'all' && state.view !== 'matchup' && state.tab !== 'strategy'
  $('#side-content').innerHTML = state.tab === 'strategy'
    ? state.view === 'matchup' ? matchupPanelHTML(strategyMatchup(model, state.query, state.rival, state.region), model, state.query) : regionPanelHTML(model, selectedRegion(), state.query)
    : state.tab === 'campaigns' ? campaignPanelHTML(territoryIntelligence(model, state.query), campaign.lens, campaign.area, model.name, campaign.research, state.query) : state.tab === 'factions' ? renderBusinesses() : state.tab === 'location' ? renderLocation() : renderStudy()
  $('#finding').textContent = `${selected.name} appears in the top 3 at ${m.top3} of ${model.points.length} sampled locations for “${model.queries.find(q => q.id === state.query).name}”. ${m.near} locations rank 4–10${m.unknown ? `; ${m.unknown} have incomplete evidence` : ''}.`
  $('#inspect-near').disabled = !m.near
  if (state.view === 'factions') {
    const leaders = localLeaders(model, state.query, state.leaderMinimum)
    const highlighted = leaders.rows.filter(r => r.major || r.business.id === state.business).length
    $('#finding').textContent = `${highlighted} highlighted first-place profiles, including bases outside the study circle. Select a leader in Businesses to trace its strongest cluster.`
  }
  $('#legend').innerHTML = state.view === 'factions'
    ? `<span>Winners: ${localLeaders(model, state.query, state.leaderMinimum).threshold}+ first places</span><span><i class="hollow-key"></i> Smaller winner</span><span><i class="unknown-key"></i> Leader unavailable</span><span>◇ Base · dashed line to strongest cluster</span>`
    : `<span class="rank-scale" aria-label="Ranking color scale, cyan through green to yellow for 1 through 10; fading red for 11 through 30">${RANK_COLORS.map((c, i) => `<span title="Rank ${i + 1} · ${Math.round(RANK_OPACITIES[i] * 100)}% opacity" style="background:${c}${Math.round(RANK_OPACITIES[i] * 255).toString(16).padStart(2, '0')};color:${i >= 10 ? '#eee' : '#050507'}">${i + 1}</span>`).join('')}</span><span><i class="hollow-key"></i> Outside top 30</span><span><i class="unknown-key"></i> Incomplete result set</span><span class="coverage-key">${state.blends && gridCorners.length && state.view === 'visibility' ? '◇ Blended colors · ' : ''}${model.geometry === 'radius_grid' ? 'Outside radius: excluded' : model.geometry === 'square_grid' ? 'Outside window: unmeasured' : 'Exploratory archive · irregular origins'}</span>`
  if (state.view === 'campaigns') {
    const intel = territoryIntelligence(model, state.query)
    const area = campaignAreas(intel, campaign.lens).find(a => a.id === campaign.area)
    $('#legend').innerHTML = ['defend', 'advance', 'build'].map(band => `<span><i style="background:${TERRITORY_COLORS[band]}"></i>${TERRITORY_LABELS[band]}</span>`).join('') + '<span>Unfilled: outside top 30 · dashed: incomplete</span>'
    $('#finding').textContent = investigationIds ? `${investigationIds.length} locations in this investigation; other observations dimmed. Review the selected service and local opponents before proposing a campaign.` : area ? `${area.reason} Demand and serviceability still need assessment.` : `${intel.counts.serviceGap} service gaps · ${intel.counts.frontier} frontier locations. Select a lens and an area to see its opponents and next checks.`
    $('#inspect-near').textContent = 'Open campaign workbench →'
    $('#inspect-near').disabled = false
  } else if (state.view === 'factions') {
    $('#inspect-near').textContent = 'Explore leader bases →'
    $('#inspect-near').disabled = false
  } else $('#inspect-near').textContent = 'Inspect a near miss →'
  if (state.region !== 'all') {
    const region = selectedRegion()
    $('#map-subtitle').textContent = `${region.label} · ${region.count} locations · outside area dimmed`
  }
  if (state.view === 'matchup') {
    const matchup = strategyMatchup(model, state.query, state.rival, state.region)
    $('#map-business').textContent = `${model.name} vs ${matchup.rival.name}`
    $('#legend').innerHTML = Object.values(MATCHUP_STYLES).map(s => `<span><i style="background:${s.color}"></i>${escape(s.label)}</span>`).join('')
    $('#finding').textContent = `${matchup.counts.primaryAhead} locations: primary ahead when both return. ${matchup.counts.rivalAhead}: rival ahead. Only-one-returned locations are separate; absence is not an exact rank.`
    $('#inspect-near').textContent = 'Open Strategy room →'
    $('#inspect-near').disabled = false
  }
  $('#footer-state').textContent = model.evidence?.observed_from ? 'Measured evidence · saved snapshot' : 'Saved evidence · no live scan'
  if (!reviewing) drawMap()
  nameReview?.sync()
  const point = model.points.find(p => p.id === state.point)
  const region = point && strategyIntelligence(model).regions?.find(r => r.id !== 'all' && r.originIds.includes(point.id))
  strategyRoom?.sync({
    queryId: state.query, regionId: region?.id || state.region,
    pointLabel: point ? `${point.id} · ${model.businesses.find(b => b.id === state.business)?.name}: ${rankPresentation(model, point, state.query, state.business).description}` : '',
  })
  $('#evidence-toggle').setAttribute('aria-expanded', workbench.classList.contains('evidence-open'))
  syncURL()
}

function drawMap() {
  if (!map) return
  basesLayer.clearLayers()
  rangeLayer.clearLayers()
  coverageLayer.clearLayers()
  const anchor = model.businesses.find(b => b.id === model.targetId)
  if (model.geometry === 'radius_grid') {
    L.circle([anchor.lat, anchor.lng], { pane: 'referencePane', radius: model.sampling.radius_km * 1000,
      color: '#969696', weight: 1, opacity: .65, dashArray: '4 6', fill: false, interactive: false }).addTo(coverageLayer)
  }
  if (state.rings && Number.isFinite(anchor?.lat) && Number.isFinite(anchor?.lng)) {
    for (const { km, label } of distanceRings(state.units)) {
      if (model.sampling?.radius_km && km > model.sampling.radius_km + .00001) continue
      L.circle([anchor.lat, anchor.lng], {
        pane: 'referencePane', radius: km * 1000, color: '#cccccc', weight: 1,
        opacity: .4, fill: false, interactive: false,
      }).addTo(rangeLayer)
      // Labels disappear when a ring is too small to read; the distance does not change.
      const labelPoint = destination(anchor.lat, anchor.lng, km, 45)
      L.marker(labelPoint, {
        pane: 'referenceLabelPane', interactive: false, keyboard: false,
        ringKm: km, ringCenter: [anchor.lat, anchor.lng],
        icon: L.divIcon({ className: 'distance-label', html: label, iconSize: [38, 18], iconAnchor: [19, 9] }),
      }).addTo(rangeLayer)
    }
  }
  const diamonds = state.blends && state.view === 'visibility' && state.region === 'all' ? drawBlends() : []
  const tactical = state.view === 'campaigns' ? territoryIntelligence(model, state.query) : null
  const tacticalCells = new Map((tactical?.cells || []).map(c => [c.id, c]))
  const focusedArea = tactical && campaignAreas(tactical, campaign.lens).find(a => a.id === campaign.area)
  const focusedIds = investigationIds ? new Set(investigationIds) : focusedArea && new Set(focusedArea.originIds)
  const regionIds = state.region !== 'all' ? new Set(selectedRegion()?.originIds || []) : null
  const matchupCells = state.view === 'matchup'
    ? new Map(strategyMatchup(model, state.query, state.rival, 'all').cells.map(c => [c.id, c])) : null
  const cells = []
  const leaders = localLeaders(model, state.query, state.leaderMinimum)
  for (const p of model.points) {
    const o = observationFor(model, p, state.query, state.business)
    const top = winnerAt(p.observations[state.query])
    const majorLeader = top && leaders.majorIds.has(top.id)
    const highlightedLeader = majorLeader || (top && top.id === state.business)
    const presentation = rankPresentation(model, p, state.query, state.business)
    let color = presentation.color
    if (state.view === 'factions') {
      color = highlightedLeader ? colorFor(top.id) : 'transparent'
    }
    const tacticalCell = tacticalCells.get(p.id)
    const tacticalMatch = tacticalCell && cellMatchesLens(tacticalCell, campaign.lens)
    const muted = !!(regionIds && !regionIds.has(p.id)) || (tactical ? !tacticalMatch || !!(focusedIds && !focusedIds.has(p.id)) : state.view === 'strike' && !(o.rank >= 4 && o.rank <= 10))
    if (tactical) color = TERRITORY_COLORS[tacticalCell?.band || 'unknown']
    const active = state.point === p.id
    const projected = map.project([p.lat, p.lng], 0)
    const comparison = matchupCells?.get(p.id)
    const comparisonStyle = comparison && MATCHUP_STYLES[comparison.state]
    cells.push({ id: p.id, lat: p.lat, lng: p.lng, x: projected.x, y: projected.y,
      color, opacity: tactical ? (state.translucent ? .45 : .9) : state.view === 'factions' ? (state.translucent ? .45 : 1) : rankFillOpacity(presentation.rank, state.translucent),
      kind: tactical ? (!tacticalCell || tacticalCell.band === 'unknown' ? 'unknown' : tacticalCell.band === 'outside30' ? 'nr' : 'ranked') : state.view === 'factions' ? (highlightedLeader ? 'ranked' : top ? 'other' : 'unknown') : presentation.kind, active, muted, coverage: state.coverage,
      dominant: state.view === 'visibility' && presentation.rank === 1,
      label: `${escape(p.id)} · ${escape(tactical ? `${TERRITORY_LABELS[tacticalCell?.band || 'unknown']}${tacticalCell?.rank ? ` · Rank ${tacticalCell.rank}` : ''}${tacticalCell?.serviceGap ? ' · another query reaches top 3' : ''}` : state.view === 'factions' ? (top ? `${leaders.byId.get(top.id)?.badge || ""} · ${top.name} · Rank 1 · ${leaders.byId.get(top.id)?.wins || 1} wins${majorLeader ? '' : ' · below highlight threshold'}` : 'First-place result unavailable') : presentation.description)}` })
    if (comparisonStyle) Object.assign(cells.at(-1), { color: comparisonStyle.color, kind: comparisonStyle.kind,
      opacity: state.translucent ? .45 : .9,
      label: `${escape(p.id)} · ${escape(matchupLabel(comparison, model.name, model.businesses.find(b => b.id === state.rival).name))}` })
  }
  const blendBoundary = model.geometry === 'radius_grid' && model.sampling?.radius_km
    ? Array.from({ length: 180 }, (_, i) => {
      const [lat, lng] = destination(anchor.lat, anchor.lng, model.sampling.radius_km, i * 2)
      return map.project([lat, lng], 0)
    }) : null
  pointsLayer.setData(cells, diamonds, spacing, state.translucent, blendBoundary)
  for (const b of model.businesses) {
    if (state.view === 'factions' && !leaders.majorIds.has(b.id) && b.id !== state.business) continue
    if (typeof b.lat !== 'number' || typeof b.lng !== 'number' || !Number.isFinite(b.lat) || !Number.isFinite(b.lng)) continue
    if (state.view !== 'factions' && b.id !== state.business) continue
    const isLeaderView = state.view === 'factions'
    const leader = leaders.byId.get(b.id)
    if (isLeaderView && leader?.connector) {
      L.polyline([[b.lat, b.lng], [leader.center.lat, leader.center.lng]], {
        color: colorFor(b.id), weight: 2, opacity: .75, dashArray: '6 7', interactive: false,
      }).addTo(basesLayer)
      L.circleMarker([leader.center.lat, leader.center.lng], {
        radius: 5, color: colorFor(b.id), weight: 2, fill: false,
      }).bindTooltip(`${escape(b.name)} · strongest cluster: ${leader.clusterSize} first places`).addTo(basesLayer)
    }
    const baseSize = isLeaderView ? 28 : 16
    L.marker([b.lat, b.lng], {
      icon: L.divIcon({ className: `base-marker ${isLeaderView ? '' : 'base-ring'}`, html: isLeaderView ? `<span class="leader-diamond" style="--business-color:${colorFor(b.id)}"><b>${leader?.badge || "◎"}</b></span>` : '<span class="business-crosshair"></span>', iconSize: [baseSize, baseSize], iconAnchor: [baseSize / 2, baseSize / 2] }),
      title: `${b.name}: supplied business location`, zIndexOffset: 1100,
    }).bindTooltip(`${escape(b.name)} · supplied location${leader?.outside ? ' · outside study circle' : ''}`).on('click', () => selectBusiness(b.id)).addTo(basesLayer)
  }
  updateZoomPresentation()
}

function drawBlends() {
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 32
  const ctx = canvas.getContext('2d')
  const textures = new Map()
  const diamonds = []
  for (const intersection of gridCorners) {
    const presentations = intersection.corners.map(p => p ? rankPresentation(model, p, state.query, state.business) : null)
    const rgba = presentations.map(p => !p || p.kind === 'nr' || p.kind === 'unknown' ? [0, 0, 0, 0] : [1, 3, 5].map(i => parseInt(p.color.slice(i, i + 2), 16)).concat(Math.round(255 * rankFillOpacity(p.rank, state.translucent))))
    const key = JSON.stringify(rgba)
    if (!textures.has(key)) {
      const image = ctx.createImageData(32, 32)
      for (let y = 0; y < 32; y++) for (let x = 0; x < 32; x++) {
        image.data.set(blendColor(rgba, x / 31, y / 31), (y * 32 + x) * 4)
      }
      ctx.putImageData(image, 0, 0)
      const texture = document.createElement('canvas')
      texture.width = texture.height = 32
      texture.getContext('2d').drawImage(canvas, 0, 0)
      textures.set(key, texture)
    }
    const a = map.project([intersection.north, intersection.west], 0)
    const b = map.project([intersection.south, intersection.east], 0)
    const center = a.add(b).divideBy(2)
    diamonds.push({ x: center.x, y: center.y, texture: textures.get(key) })
  }
  return diamonds
}

function updateZoomPresentation() {
  if (!map || !pointsLayer) return
  rangeLayer.eachLayer(layer => {
    if (!layer.options.ringKm) return
    const pixels = map.project(layer.options.ringCenter, map.getZoom()).distanceTo(map.project(layer.getLatLng(), map.getZoom()))
    const icon = layer.getElement()
    if (icon) icon.style.display = pixels >= 38 ? '' : 'none'
  })
}

function fitStudy() {
  cancelWheelZoom()
  followStudyBounds = true
  fittingStudy = true
  try {
    map.fitBounds(L.latLngBounds(model.points.map(p => [p.lat, p.lng])), { padding: [35, 40], animate: false })
  } finally {
    fittingStudy = false
  }
}

function loadStudy(input, restore = false) {
  const next = normalizeStudy(input)
  nameReview?.savePending()
  model = next
  campaign.area = null
  campaign.research = null
  investigationIds = null
  const spacings = cellSpacings(model.points.map(p => {
    const projected = map.project([p.lat, p.lng], 0)
    return [projected.x, projected.y]
  }))
  spacing = Math.min(...spacings.filter(s => s > 0))
  if (!Number.isFinite(spacing)) spacing = .001
  gridCorners = []
  if (['square_grid', 'radius_grid'].includes(model.geometry) || model.limited) {
    gridCorners = latticeIntersections(model.points, model.geometry === 'radius_grid')
  }
  state.query = restore && model.queries.some(q => q.id === initialParams.get('query')) ? initialParams.get('query') : model.queries[0].id
  state.business = restore && model.businesses.some(b => b.id === initialParams.get('business')) ? initialParams.get('business') : model.targetId
  state.point = restore && model.points.some(p => p.id === initialParams.get('point')) ? initialParams.get('point') : null
  state.view = restore && names[initialParams.get('view')] ? initialParams.get('view') : 'visibility'
  state.region = restore && strategyIntelligence(model).regions?.some(r => r.id === initialParams.get('region')) ? initialParams.get('region') : 'all'
  state.rival = restore && model.businesses.some(b => b.id === initialParams.get('rival') && b.id !== model.targetId) ? initialParams.get('rival') : null
  if (state.region !== 'all') state.business = model.targetId
  if (state.view === 'matchup') {
    if (state.rival && strategyIntelligence(model).available) state.business = model.targetId
    else state.view = 'visibility'
  }
  campaign.lens = restore && CAMPAIGN_LENSES[initialParams.get('lens')] ? initialParams.get('lens') : 'overview'
  if (state.view === 'campaigns') {
    state.business = model.targetId
    if (restore && campaignAreas(territoryIntelligence(model, state.query), campaign.lens).some(a => a.id === initialParams.get('area'))) campaign.area = initialParams.get('area')
    const insight = restore && strategyIntelligence(model).insights?.find(i => i.id === initialParams.get('investigation') && i.queryId === state.query)
    if (insight) {
      investigationId = insight.id
      investigationIds = insight.originIds
      campaign.area = null
      campaign.lens = insight.id.startsWith('service-gap:') ? 'serviceGap' : insight.id.startsWith('frontier:') ? 'frontier' : 'advance'
    }
  }
  if (restore) {
    state.rings = initialParams.get('rings') !== '0'
    state.translucent = initialParams.get('translucent') === '1'
    state.blends = initialParams.get('blends') !== '0'
    state.coverage = initialParams.get('coverage') !== '0'
  }
  state.tab = state.point ? 'location' : state.view === 'campaigns' ? 'campaigns' : 'factions'
  if (!state.point && (state.region !== 'all' || state.view === 'matchup')) state.tab = 'strategy'
  fieldBrowser.scope = model.businesses.find(b => b.id === state.business)?.shortlisted === false ? 'all' : 'shortlist'
  fieldBrowser.search = ''
  fieldBrowser.page = 0
  fitStudy()
  render()
  const isBundledSample = input === sample
  void loadCampaignResearch(isBundledSample ? sampleResearch : null)
  void nameReview?.load(params.get('name_review'), {
    studyURL: params.get('study'),
    fallbackInput: isBundledSample ? sampleNameReview : null,
  })
}

function contextText() {
  const b = model.businesses.find(b => b.id === state.business)
  const q = model.queries.find(q => q.id === state.query)
  const m = businessMetrics(model, q.id, b.id)
  const p = model.points.find(p => p.id === state.point)
  const area = state.view === 'campaigns' && campaignAreas(territoryIntelligence(model, q.id), campaign.lens).find(a => a.id === campaign.area)
  if (state.view === 'matchup' || state.region !== 'all') {
    const region = selectedRegion(), metric = region.perQuery[q.id]
    const matchup = state.view === 'matchup' ? strategyMatchup(model, q.id, state.rival, state.region) : null
    return `${model.name} — ${region.label}\nQuery: ${q.name}\nPrimary top 3: ${metric.top3}/${metric.complete}; top 10: ${metric.top10}/${metric.complete}; incomplete: ${metric.unknown}.\n${matchup ? `Compared with: ${matchup.rival.name} (${matchup.rival.address || matchup.rival.id})\n${Object.entries(matchup.counts).map(([key, count]) => `${MATCHUP_STYLES[key].label}: ${count}`).join('\n')}\n` : ''}Exact sampled origins: ${region.originIds.join(', ')}\nObserved: ${model.evidence?.observed_from || 'Not recorded'}\nComplete top-30 evidence only. Absence is censored, not an invented rank. This measures visibility, not demand, revenue, or ranking cause.`
  }
  return `${model.name} — ${model.location}\nSelected business: ${b.name}${b.discovered ? ' (emerging rival)' : ''}\nQuery: ${q.name}\n${m.top3}/${model.points.length} locations in top 3 (${m.top3Pct.toFixed(1)}%). ${m.found} found; ${m.unknown} incomplete. Average when found: ${m.average?.toFixed(2) ?? 'unknown'}.\n${area ? `Investigation area: ${area.label}, ${area.direction}; ${area.count} locations, median rank ${area.medianRank}.\nMembers: ${area.originIds.join(', ')}\nTop-three rivals: ${area.rivals.map(r => `${r.name} (${r.count}/${area.count})`).join('; ')}\nNext check: assess service demand, operating reach, and profile/page differences before recommending changes.\n` : ''}${model.evidence?.observed_from ? `Observed: ${model.evidence.observed_from} through ${model.evidence.observed_to}\n` : ''}${p ? `Selected origin: ${p.id} (${p.lat}, ${p.lng})\n${p.observations[q.id].items.map(i => `${i.rank}. ${i.name}`).join('\n')}\n` : ''}Saved evidence, not a live scan. Unsampled areas are unmeasured. Rank does not establish cause or ease of improvement. Coverage depends on this study's sampling footprint.`
}

map = L.map('map', { zoomControl: false, minZoom: 3, maxZoom: 18, zoomSnap: 0, zoomDelta: 0.5, preferCanvas: true, scrollWheelZoom: false, zoomAnimation: false, fadeAnimation: !matchMedia('(prefers-reduced-motion: reduce)').matches })
cancelWheelZoom = installWheelZoom(map)
map.createPane('referencePane').style.zIndex = '605'
map.createPane('rankingPane').style.zIndex = '450'
map.getPane('rankingPane').style.pointerEvents = 'none'
map.createPane('referenceLabelPane').style.zIndex = '610'
map.getPane('referencePane').style.pointerEvents = 'none'
map.getPane('referenceLabelPane').style.pointerEvents = 'none'
rangeLayer = L.layerGroup().addTo(map)
coverageLayer = L.layerGroup().addTo(map)
L.DomEvent.disableClickPropagation($('#map .map-options'))
L.DomEvent.disableScrollPropagation($('#map .map-options'))
L.control.zoom({ position: 'bottomleft' }).addTo(map)
let failedBasemap = null
let mapSourcesReady = false, basemapStarted = false
const basemaps = createBasemapSwitcher(map, { announce, onStatus(status) {
  $('#basemap-status').hidden = status.phase !== 'error'
  if (status.phase === 'error') {
    failedBasemap = status.id
    $('#basemap-status p').textContent = status.message
  }
}, onChange(id) {
  state.basemap = id
  $('#basemap').value = id
  try { localStorage.setItem('geogrid-basemap', id) } catch { /* URL still preserves it. */ }
  syncURL()
} })
function ensureBasemap() {
  if (!mapSourcesReady || basemapStarted || !$('#map').clientWidth || !$('#map').clientHeight) return
  basemapStarted = true
  void basemaps.set(state.basemap)
}
$('#basemap').value = state.basemap
L.DomEvent.disableClickPropagation($('#basemap-status'))
L.DomEvent.disableScrollPropagation($('#basemap-status'))
$('#retry-basemap').addEventListener('click', () => { if (failedBasemap) basemaps.set(failedBasemap) })
$('#use-default-basemap').addEventListener('click', () => basemaps.set('osm-legends'))
$('#basemap').addEventListener('change', async e => {
  const choice = e.target.value
  $('#basemap').disabled = true
  try { await basemaps.set(choice) }
  finally { $('#basemap').disabled = false; $('#basemap').value = state.basemap }
})
pointsLayer = new RankCanvasLayer({ onSelect: selectPoint }).addTo(map)
basesLayer = L.layerGroup().addTo(map)
map.on('zoom', updateZoomPresentation)
map.on('movestart', () => {
  if (!fittingStudy) followStudyBounds = false
})
new ResizeObserver(() => {
  map.invalidateSize({ pan: false })
  if (followStudyBounds) fitStudy()
  ensureBasemap()
}).observe($('#map'))

$('#query').addEventListener('change', e => { state.query = e.target.value; campaign.area = null; investigationIds = null; render() })
$('#distance-rings').addEventListener('click', () => { state.rings = !state.rings; render() })
$('#coverage-dots').addEventListener('click', () => { state.coverage = !state.coverage; render() })
$('#translucent').addEventListener('click', () => { state.translucent = !state.translucent; render() })
$('#corner-blends').addEventListener('click', () => { state.blends = !state.blends; render() })
$('#sampling-view').addEventListener('change', async e => {
  try {
    const url = new URL(e.target.value, location.href)
    if (url.origin !== location.origin) throw new Error('Study must use this origin')
    const response = await fetch(url)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const input = await response.json()
    normalizeStudy(input)
    params.set('study', e.target.value)
    loadStudy(input)
  } catch (error) { announce(`Could not load footprint: ${error.message}`) }
})
$('#fit').addEventListener('click', () => { state.region = 'all'; campaign.area = null; investigationIds = null; render(); fitStudy() })
document.querySelectorAll('[data-view]').forEach(b => b.addEventListener('click', () => setView(b.dataset.view)))
document.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', () => { if (b.dataset.tab === 'campaigns') setView('campaigns'); else { state.tab = b.dataset.tab; render() } }))
$('#side-content').addEventListener('click', e => {
  const coverageChoice = e.target.closest('[data-leader-minimum]')
  if (coverageChoice) { state.leaderMinimum = Number(coverageChoice.dataset.leaderMinimum); render(); return }
  if (e.target.closest('[data-fit-leaders]')) { fitLeaders(); return }
  const leader = e.target.closest('[data-leader]')
  if (leader) { selectBusiness(leader.dataset.leader); fitLeaders(leader.dataset.leader); return }
  if (e.target.closest('[data-open-strategy]')) { strategyRoom.open(); return }
  const planBaseline = e.target.closest('[data-campaign-baseline]')
  if (planBaseline) {
    const action = campaignPlanMapAction(campaign.research, planBaseline.dataset.campaignBaseline)
    if (action) { state.query = action.queryId; setCampaignLens(action.lens) }
    return
  }
  const regionQuery = e.target.closest('[data-region-query]')
  if (regionQuery) { state.query = regionQuery.dataset.regionQuery; render(); return }
  const mapRival = e.target.closest('[data-map-rival]')
  if (mapRival) { inspectRegion({ regionId: state.region, rivalId: mapRival.dataset.mapRival }); return }
  if (e.target.closest('[data-return-region]')) { inspectRegion({ regionId: state.region }); return }
  const focus = e.target.closest('[data-focus-area]')
  if (focus) { focusCampaignArea(focus.dataset.focusArea); return }
  const evidence = e.target.closest('[data-area-evidence]')
  if (evidence) { selectPoint(evidence.dataset.areaEvidence); return }
  if (e.target.closest('[data-clear-area]')) { campaign.area = null; render(); fitStudy(); return }
  const rival = e.target.closest('[data-campaign-rival]')
  if (rival) { selectBusiness(rival.dataset.campaignRival); return }
  const query = e.target.closest('[data-location-query]')
  if (query) { state.query = query.dataset.locationQuery; campaign.area = null; render(); return }
  const b = e.target.closest('[data-business]')
  if (b) selectBusiness(b.dataset.business)
  const scope = e.target.closest('[data-field-scope]')
  if (scope) { fieldBrowser.scope = scope.dataset.fieldScope; fieldBrowser.page = 0; $('#side-content').innerHTML = renderBusinesses() }
  const page = e.target.closest('[data-field-page]')
  if (page) { fieldBrowser.page += Number(page.dataset.fieldPage); $('#side-content').innerHTML = renderBusinesses() }
})
$('#side-content').addEventListener('change', e => {
  if (e.target.id === 'campaign-lens') setCampaignLens(e.target.value)
})
$('#side-content').addEventListener('input', e => {
  if (e.target.id !== 'field-search') return
  const position = e.target.selectionStart
  fieldBrowser.search = e.target.value
  fieldBrowser.scope = fieldBrowser.search ? 'all' : fieldBrowser.scope
  fieldBrowser.page = 0
  $('#side-content').innerHTML = renderBusinesses()
  const input = $('#field-search')
  input.focus()
  input.setSelectionRange(position, position)
})
$('#open-study').addEventListener('click', () => $('#study-file').click())
$('#study-file').addEventListener('change', async e => {
  const file = e.target.files[0]
  if (!file) return
  try {
    if (file.size > 75 * 1024 * 1024) throw new Error('Choose a study smaller than 75 MB.')
    const input = JSON.parse(await file.text())
    normalizeStudy(input)
    params.delete('study')
    loadStudy(input)
    announce(`Opened ${file.name}. This file stays in your browser.`)
  } catch (error) { announce(`Could not open study: ${error.message}`) }
  e.target.value = ''
})
$('#inspect-near').addEventListener('click', () => {
  if (state.view === 'factions') { fitLeaders(); return }
  if (state.view === 'matchup') { strategyRoom.open(); return }
  if (state.view === 'campaigns') { state.tab = 'campaigns'; render(); return }
  const near = model.points.filter(p => {
    const r = observationFor(model, p, state.query, state.business).rank
    return r >= 4 && r <= 10 && (state.region === 'all' || selectedRegion()?.originIds.includes(p.id))
  })
  const p = near[(near.findIndex(p => p.id === state.point) + 1) % near.length]
  if (p) { selectPoint(p.id); map.setView([p.lat, p.lng], Math.max(13, map.getZoom())) }
})
$('#copy-brief').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(contextText()); announce('Study context copied. Paste it into your agent conversation.') }
  catch { announce('Clipboard access is unavailable. Use GeoGrid.context() from your connected browser agent.') }
})
strategyRoom = createStrategyRoom({
  mount: $('#strategy-host'),
  startDocked: initialParams.get('strategyLayout') === 'split',
  getModel: () => model,
  getResearch: () => campaign.research,
  getQueryId: () => state.query,
  onLayout({ open, docked, forceDock }) {
    workbench.classList.toggle('strategy-docked', docked)
    $('#open-strategy').setAttribute('aria-expanded', open)
    $('#open-strategy').textContent = open ? 'Hide strategy' : 'Strategy room'
    if (open) params.set('strategy', '1'); else params.delete('strategy')
    if (forceDock) params.set('strategyLayout', 'split'); else params.delete('strategyLayout')
    if (docked) queueMicrotask(() => resizeStrategy(split))
    syncURL()
  },
  onInspectRegion: inspectRegion,
  onMatchup: inspectRegion,
  onCampaign({ campaignId, queryId, lens, originIds, insight }) {
    if (campaignId === 'local-vs-regional' && insight?.evidence?.nearLeader?.id) {
      inspectRegion({ regionId: 'all', queryId, rivalId: insight.evidence.nearLeader.id })
      return
    }
    state.query = queryId
    setCampaignLens(CAMPAIGN_LENSES[lens] ? lens : 'advance')
    const area = campaignAreas(territoryIntelligence(model, state.query), campaign.lens)
      .find(a => originIds?.length && originIds.every(id => a.originIds.includes(id)))
    if (area) focusCampaignArea(area.id)
    else if (originIds?.length) { investigationId = campaignId; investigationIds = originIds; render(); fitOrigins(originIds) }
  },
})
nameReview = createNameReview({
  getModel: () => model,
  getQuery: () => state.query,
  host: $('#name-review-host'),
  onClose: () => setView('factions'),
  onOpen: () => strategyRoom.close(),
  onMessage: announce,
  onMap(id) { selectBusiness(id); setView('factions'); fitLeaders(id) },
})
document.addEventListener('click', event => { if (event.target.closest('[data-open-name-review]')) setView('keyword-stuffing') })
$('#open-strategy').addEventListener('click', () => { if (state.view === 'keyword-stuffing') setView('visibility'); strategyRoom.toggle() })
$('#evidence-toggle').addEventListener('click', () => {
  workbench.classList.toggle('evidence-open')
  $('#evidence-toggle').setAttribute('aria-expanded', workbench.classList.contains('evidence-open'))
})
const divider = $('#strategy-divider')
let split = 50
try { split = Math.max(35, Math.min(60, Number(localStorage.getItem('geogrid-strategy-width')) || 50)) } catch { /* Use even split. */ }
function resizeStrategy(value) {
  const width = workbench.clientWidth
  const minPanel = width >= 1200 ? 480 : 400
  const minMap = width >= 1200 ? 560 : 400
  split = Math.max(Math.max(35, minPanel / width * 100), Math.min(Math.min(60, (width - minMap - 8) / width * 100), value))
  workbench.style.setProperty('--strategy-width', `${split}%`)
  divider.setAttribute('aria-valuenow', Math.round(split))
  try { localStorage.setItem('geogrid-strategy-width', split) } catch { /* Session still resizes. */ }
}
workbench.style.setProperty('--strategy-width', `${split}%`)
divider.setAttribute('aria-valuenow', Math.round(split))
divider.addEventListener('pointerdown', event => { if (event.button !== 0) return; divider.setPointerCapture(event.pointerId); workbench.classList.add('resizing'); event.preventDefault() })
divider.addEventListener('pointermove', event => {
  if (divider.hasPointerCapture(event.pointerId)) resizeStrategy((workbench.getBoundingClientRect().right - event.clientX) / workbench.clientWidth * 100)
})
divider.addEventListener('pointerup', event => { if (divider.hasPointerCapture(event.pointerId)) divider.releasePointerCapture(event.pointerId); workbench.classList.remove('resizing') })
divider.addEventListener('lostpointercapture', () => workbench.classList.remove('resizing'))
divider.addEventListener('keydown', event => {
  if (!['ArrowLeft', 'ArrowRight', 'Home'].includes(event.key)) return
  event.preventDefault()
  resizeStrategy(event.key === 'Home' ? 50 : split + (event.key === 'ArrowLeft' ? 2 : -2))
})
divider.addEventListener('dblclick', () => resizeStrategy(50))
window.addEventListener('resize', () => { if (workbench.classList.contains('strategy-docked')) resizeStrategy(split) })
window.GeoGrid = {
  loadStudy, selectBusiness, selectPoint,
  setQuery(id) { if (!model.queries.some(q => q.id === id)) throw new Error('Unknown query'); state.query = id; campaign.area = null; investigationIds = null; render() },
  setView, setCampaignLens, focusCampaignArea,
  campaignAnalysis: () => territoryIntelligence(model, state.query),
  strategyAnalysis: () => strategyIntelligence(model),
  leaderAnalysis: () => localLeaders(model, state.query, state.leaderMinimum),
  fitLeaders,
  inspectRegion,
  openStrategy: () => strategyRoom.open(),
  openNameReview: () => setView('keyword-stuffing'),
  nameReviewState: () => nameReview.getState(),
  getState: () => ({ ...state, lens: campaign.lens, area: campaign.area, study: model.name, zoom: map.getZoom() }),
  renderStats: () => pointsLayer.stats,
  pointPosition: id => pointsLayer.pointPosition(id),
  context: contextText,
}
loadStudy(sample, true)
// A private local pointer can select the working study without bundling client
// evidence in the open-source build. Explicit links always retain their study.
if (import.meta.env.DEV && initialParams.get('starter') !== '1') {
  try {
    const response = await fetch('/runs/current-study.json', { cache: 'no-store' })
    if (response.ok && response.headers.get('content-type')?.includes('application/json')) {
      const current = await response.json()
      if (typeof current.study === 'string' && !initialParams.has('study')) params.set('study', current.study)
      const sameStudy = typeof current.study === 'string' && new URL(current.study, location.href).href === new URL(params.get('study') || '/', location.href).href
      if (sameStudy && typeof current.research === 'string' && !params.has('research')) params.set('research', current.research)
      if (sameStudy && typeof current.name_review === 'string' && !params.has('name_review')) params.set('name_review', current.name_review)
    }
  } catch { /* No local active study: the bundled sample remains available. */ }
}
if (params.has('study')) {
  try {
    const url = new URL(params.get('study'), location.href)
    if (url.origin !== location.origin) throw new Error('Study URLs must use the same origin. Use Open study for local files.')
    const response = await fetch(url)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    loadStudy(await response.json(), true)
  } catch (error) { announce(`Could not load requested study (${error.message}). Showing the bundled sample.`) }
}
// A direct link to business-title evidence has no visible map viewport yet.
// Start map requests when the user returns to a map mode, not against 0×0 bounds.
mapSourcesReady = true
ensureBasemap()
if (initialParams.get('strategy') === '1') strategyRoom.open()
