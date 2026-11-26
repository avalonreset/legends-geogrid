import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { sample, sampleResearch, sampleNameReview } from './starter-data.js'


import { normalizeStudy, edgeSignalNote, observationFor, businessMetrics, businessLeaderboard, businessPage, rankPresentation, RANK_COLORS, RANK_OPACITIES, rankFillOpacity } from './study-model.js'
import { cellSpacings, destination, blendColor, latticeIntersections, territoryOutlines, prepareHexTerritory, hexTerritoryFromPrep, computeFocusOverlay, computeElevationStack, computeScalarElevation, computePinRegion, computeCampaignSeams, computeLeaderRelief } from './map-geometry.js'
import { installWheelZoom } from './wheel-zoom.js'
import { BASEMAPS, createBasemapSwitcher } from './basemap-switcher.js'
import { RankCanvasLayer } from './rank-canvas.js'
import { localLeaders, profileColor } from './local-leaders.js'
import { winnerAt, leaderIdentity } from './leader-colors.js'
import { pointPanelHTML, competitorPanelHTML } from './point-listings.js'
import { distanceLabel, distanceText, distanceRings } from './distance-units.js'
import { territoryIntelligence } from './territory-intelligence.js'
import { campaignEngine, CAMPAIGN_WEIGHTS } from './campaign-engine.js'
import { strategyIntelligence, strategyMatchup } from './strategy-engine.js'
import { createStrategyRoom } from './strategy-room.js'
import { createNameReview, suspectTerritory } from './name-review.js'
import { resolveStudyAttachment } from './review-attachment.js'
import './name-review.css'
import { MATCHUP_STYLES, matchupLabel, regionPanelHTML, matchupPanelHTML } from './strategy-map-panel.js'
import './strategy-room.css'
import { ZONE_COLORS, ZONE_LABELS, emberColorForW, campaignPanelHTML, campaignLegendHTML, campaignFindingInfo, mergedAvoidList, visionAgentCampaignBrief, campaignPlanMapAction, validateCampaignResearch } from './campaign-panel.js'
import './companion.css'

const escape = text => String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
const formatDate = value => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }) : 'Not recorded'

// Mountable companion. The local dev/runtime builds call createCompanion() with no arguments and keep the
// original behavior (document-level #app root, URL state, localStorage). The viewer package passes
// { embedded: true, root, study, capabilities, basemaps, ... } and gets no URL, storage or window globals.
export function createCompanion(config = {}) {
const embedded = config.embedded === true
const root = config.root || document.querySelector('#app')
const $ = selector => root.querySelector(selector)
const caps = { perPointListings: true, profiles: true, nameReview: true, campaignResearch: true, strategyRoom: true, ...(config.capabilities || {}) }
const params = new URLSearchParams(embedded ? '' : location.search)
const initialParams = new URLSearchParams(embedded ? '' : location.search)
let model = normalizeStudy(config.study ?? sample)
const state = { query: 'q1', business: 'TARGET', point: null, view: 'visibility', tab: 'factions', region: 'all', rival: null, rings: true, translucent: false, blends: true, contested: false, contours: true, focus: null, coverage: true, showDots: false, clipCircle: true, units: 'mi', leaderMinimum: 1 }
const fieldBrowser = { scope: 'shortlist', search: '', page: 0 }
let leaderSearch = ''
const listingsUi = { allListings: false, allRivals: false, point: null }
const campaign = { playId: null, avoidId: null, isolateLayer: null, research: null }
const attrEscape = value => typeof CSS !== 'undefined' && typeof CSS.escape === 'function'
  ? CSS.escape(String(value ?? ''))
  : String(value ?? '').replace(/["\\]/g, '\\$&')
function revealInRail(selector, { block = 'center', flash = true } = {}) {
  const rail = $('#side-content')
  const el = rail?.querySelector(selector)
  if (!el || !rail) return false
  const reduced = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
  if (typeof rail.scrollTo === 'function' && rail.clientHeight > 0) {
    const railRect = rail.getBoundingClientRect()
    const elRect = el.getBoundingClientRect()
    const currentTop = rail.scrollTop
    const offset = block === 'start' ? 12 : Math.max(12, (rail.clientHeight - elRect.height) / 2)
    const maxTop = Math.max(0, rail.scrollHeight - rail.clientHeight)
    const targetTop = Math.max(0, Math.min(maxTop, currentTop + (elRect.top - railRect.top) - offset))
    const behavior = reduced || Math.abs(targetTop - currentTop) > 1200 ? 'auto' : 'smooth'
    rail.scrollTo({ top: targetTop, behavior })
  } else if (typeof el.scrollIntoView === 'function') {
    el.scrollIntoView({ block, inline: 'nearest', behavior: reduced ? 'auto' : 'smooth' })
  }
  if (flash) {
    el.classList.remove('rail-reveal')
    void el.offsetWidth
    el.classList.add('rail-reveal')
    setTimeout(() => { if (!destroyed) el.classList.remove('rail-reveal') }, 900)
  }
  return true
}
function revealBusinessInBrowser(id) {
  const biz = model.businesses.find(b => b.id === id)
  if (!biz) return
  if (fieldBrowser.scope !== 'all' && biz.shortlisted === false) fieldBrowser.scope = 'all'
  const matches = (scope, search) => {
    const needle = search.trim().toLocaleLowerCase()
    return businessLeaderboard(model, state.query).filter(({ business: b }) =>
      (scope === 'all' || b.shortlisted !== false) &&
      (!needle || [b.name, b.address, b.cid, b.placeId].some(v => String(v || '').toLocaleLowerCase().includes(needle))))
  }
  let list = matches(fieldBrowser.scope, fieldBrowser.search)
  let idx = list.findIndex(r => r.business.id === id)
  if (idx < 0 && fieldBrowser.search) {
    fieldBrowser.search = ''
    list = matches(fieldBrowser.scope, '')
    idx = list.findIndex(r => r.business.id === id)
  }
  if (idx < 0 && fieldBrowser.scope !== 'all') {
    fieldBrowser.scope = 'all'
    list = matches('all', fieldBrowser.search)
    idx = list.findIndex(r => r.business.id === id)
  }
  if (idx >= 0) fieldBrowser.page = Math.floor(idx / 25)
}
let investigationIds = null
let investigationId = null
let scaleControl, scaleUnits
let map, pointsLayer, basesLayer, rangeLayer, coverageLayer
let strategyRoom
let nameReview
let inspectorTimer = 0
const basemapList = (Array.isArray(config.basemaps) ? BASEMAPS.filter(s => config.basemaps.includes(s.id)) : [...BASEMAPS])
  .filter(s => !(embedded && s.google && !config.googleSessionPath))
const fallbackBasemap = basemapList.some(s => s.id === 'osm-legends') ? 'osm-legends' : (basemapList.find(s => !s.google)?.id || basemapList[0]?.id)
let preferredBasemap = config.defaultBasemap || fallbackBasemap
if (!embedded) try { preferredBasemap = localStorage.getItem('geogrid-basemap') || preferredBasemap } catch { /* Use default. */ }
const isFileOrigin = !embedded && location.protocol === 'file:'
const selectableBasemap = id => basemapList.some(s => s.id === id && (!isFileOrigin || s.kind === 'osm'))
state.basemap = selectableBasemap(initialParams.get('basemap')) ? initialParams.get('basemap') :
  selectableBasemap(preferredBasemap) ? preferredBasemap : fallbackBasemap
let spacing = 0, pointSpacings = [], gridCorners = [], cancelWheelZoom = () => {}
let followStudyBounds = true, fittingStudy = false
let hoveredLeaderId = null, leaderBaseEntries = [], cameraFrame = 0
// Head-to-head territory: rank-independent prep, the current border gap (TAU) and its animation frame.
let territoryPrep = null, territoryTau = 0, tauFrame = 0
let destroyed = false, onVisibilityChange = null
const colorFor = id => profileColor(model, id)
const names = { visibility: 'Rankings', factions: 'Local leaders', strike: 'Strike zones', campaigns: 'Campaigns', 'keyword-stuffing': 'Keyword stuffing', matchup: 'Head-to-head' }
const explanations = {
  'keyword-stuffing': 'Inspect flagged profile titles alongside their live footprint.',
  visibility: 'Rank by color. Hover any location to inspect its rank.',
  factions: 'Who ranks first. Colors identify businesses.',
  strike: 'Ranks 4 to 10: opportunities to investigate.',
  campaigns: 'Winnability relief ranks observed strike zones and blockers without compass labels.',
  matchup: 'Compare two profiles in the same searches. Hover for both ranks.',
}

if (embedded) root.classList.add('ggv-root')
root.innerHTML = `
  <header class="app-bar">
    <div class="brand-cluster">
      <div class="wordmark"><span class="brand-symbol" aria-hidden="true">✳</span><div class="brand-text"><span>legends-geogrid</span><small class="eyebrow">LOCAL SEARCH EXPLORER</small></div></div>
      <div class="study-heading">
        <div class="study-title-row"><h1 id="study-name"></h1><span class="study-stamp"><span class="status-dot"></span><span id="study-kind"></span></span></div>
        <div class="study-sub-row"><p id="study-location"></p><small id="study-date"></small></div>
      </div>
    </div>
    <section class="query-bar"><label for="query">Query</label><select id="query"></select><select id="sampling-view" aria-label="Study footprint" hidden></select><span id="query-scope"></span></section>
    <div class="app-actions"><button id="evidence-toggle" class="quiet-button" aria-expanded="false">Details</button><button id="copy-brief" class="quiet-button">Copy context</button><button id="open-study" class="quiet-button">Open study <span aria-hidden="true">↗</span></button><button id="open-strategy" class="strategy-launch" aria-expanded="false" aria-controls="strategy-room">Strategy room</button></div>
    <input id="study-file" type="file" accept=".json,application/json" hidden>
  </header>
  <main>
    <section class="workspace">
      <div class="map-column">
        <div class="map-heading"><div class="view-tabs" role="group" aria-label="Map lens">
          <button data-view="visibility">Rankings</button><button data-view="factions">Local leaders</button><button data-view="campaigns">Campaigns</button><button data-view="keyword-stuffing" aria-controls="nr-inspector">Keyword stuffing</button><button data-view="matchup" hidden>Head-to-head</button>
        </div><div class="map-description" id="view-description"></div><div class="map-heading-actions"><select id="basemap" aria-label="Map source">${basemapList.map(s => `<option value="${s.id}"${isFileOrigin && s.kind !== 'osm' ? ' disabled' : ''}>${s.name}${isFileOrigin && s.kind !== 'osm' ? ' (HTTP server only)' : ''}</option>`).join('')}</select><button id="fit" class="quiet-button" title="Show every sampled location">Fit study</button></div></div>
        <div id="map"><div class="map-badge"><span id="map-business"></span><small id="map-subtitle">Organic Maps rankings</small></div>
          <div id="focus-pill" class="focus-pill" role="status" hidden></div>
          <div id="basemap-status" class="basemap-status" role="status" hidden><p></p><div><button id="retry-basemap">Retry map</button><button id="use-default-basemap">Use ${embedded ? escape(basemapList.find(s => s.id === fallbackBasemap)?.name || 'default map') : 'OpenStreetMap'}</button><button id="dismiss-basemap">Dismiss</button></div></div>
          <div class="map-options" role="group" aria-label="Map appearance"><button id="elevation-contours" type="button" aria-pressed="true">topography</button><button id="triangle-estimates" type="button" aria-pressed="false">triangles</button><button id="contested-ground" type="button" aria-pressed="false">contested</button><span class="map-options-divider" aria-hidden="true"></span><button id="grid-dots" type="button" aria-pressed="false">pins</button><button id="distance-rings" type="button" aria-pressed="true">rings</button></div>
        </div>
        <div class="map-legend" id="legend"></div>
        <div class="finding-strip"><span class="eyebrow">READ THE MAP</span><p id="finding"></p><button id="inspect-near" class="text-button">Explore campaign areas →</button></div>
      </div>
      <aside id="nr-inspector" aria-label="Keyword stuffing inspector" hidden></aside>
      <aside class="sidebar">
        <div class="side-tabs" role="group" aria-label="Study details"><button data-tab="strategy" hidden>Area</button><button data-tab="campaigns" hidden>Plays</button><button data-tab="factions">Businesses</button><button data-tab="point"${caps.perPointListings ? '' : ' hidden'}>Location</button><button data-tab="competitors"${caps.perPointListings ? '' : ' hidden'}>Competitors</button><button data-tab="study">Study</button></div>
        <div id="side-content"></div>
      </aside>
    </section>
    <footer><span>Built for the conversation. Select a business, explore a location, bring the evidence back to your agent.</span><span id="footer-state"></span></footer>
  </main>
  <div id="toast" role="status" aria-live="polite"></div>`

const workbench = document.createElement('div')
workbench.className = 'workbench'
root.insertBefore(workbench, $('main'))
workbench.append($('main'))
workbench.insertAdjacentHTML('beforeend', '<div id="strategy-divider" role="separator" aria-label="Resize strategy panel" aria-orientation="vertical" aria-valuemin="35" aria-valuemax="60" aria-valuenow="50" tabindex="0"></div><div id="strategy-host"></div>')

function syncURL() {
  if (embedded) return
  for (const key of ['query', 'business', 'point', 'view', 'region', 'rival']) {
    if (state[key]) params.set(key, state[key]); else params.delete(key)
  }
  params.set('rings', state.rings ? '1' : '0')
  if (state.translucent) params.set('translucent', '1'); else params.delete('translucent')
  if (model.geometry === 'hex_radius') {
    if (state.blends) params.set('triangles', '1'); else params.delete('triangles')
    params.delete('blends')
  } else {
    params.delete('triangles')
    if (!state.blends) params.set('blends', '0'); else params.delete('blends')
  }
  if (state.contested) params.set('contested', '1'); else params.delete('contested')
  if (state.focus) params.set('focus', state.focus); else params.delete('focus')
  params.set('coverage', state.coverage ? '1' : '0')
  params.set('dots', state.showDots ? '1' : '0')
  params.set('contours', state.contours ? '1' : '0')
  if (!state.clipCircle && ['radius_grid', 'hex_radius'].includes(model.geometry)) params.set('clip', '0'); else params.delete('clip')
  params.delete('reach')
  params.set('units', state.units)
  params.delete('leaders')
  params.set('basemap', state.basemap)
  if (state.view === 'campaigns') {
    if (campaign.playId) params.set('play', campaign.playId); else params.delete('play')
    if (campaign.avoidId) params.set('avoid', campaign.avoidId); else params.delete('avoid')
    params.delete('lens'); params.delete('area')
  } else { params.delete('play'); params.delete('avoid'); params.delete('lens'); params.delete('area') }
  if (state.view === 'campaigns' && investigationIds && investigationId) params.set('investigation', investigationId)
  else params.delete('investigation')
  try { history.replaceState(null, '', `${location.pathname}?${params}`) } catch { /* Restricted on some file:// origins. */ }
}

function announce(message) {
  if (!$('#toast')) return // a late background error after destroy()
  $('#toast').textContent = message
  $('#toast').classList.add('visible')
  clearTimeout(announce.timer)
  announce.timer = setTimeout(() => $('#toast').classList.remove('visible'), 6000)
}

function selectBusiness(id, { reveal = false, fromRail = false } = {}) {
  if (!model.businesses.some(b => b.id === id)) throw new Error('Unknown business')
  state.business = id
  state.region = 'all'
  investigationIds = null
  let shouldReveal = reveal
  if (['campaigns', 'matchup'].includes(state.view)) {
    state.view = 'visibility'; state.tab = 'factions'; campaign.playId = null; campaign.avoidId = null; state.region = 'all'; state.rival = null
    shouldReveal = true
  }
  if (shouldReveal && state.view !== 'factions' && state.tab === 'factions') {
    revealBusinessInBrowser(id)
  }
  render()
  if (shouldReveal && !fromRail && state.tab === 'factions') {
    const sel = state.view === 'factions'
      ? `[data-leader="${attrEscape(id)}"]`
      : `[data-business="${attrEscape(id)}"]`
    revealInRail(sel)
  }
}

function selectPoint(id) {
  if (!model.points.some(p => p.id === id)) throw new Error('Unknown location')
  state.point = id
  if (state.view === 'keyword-stuffing' && caps.perPointListings && nameReview) {
    listingsUi.point = id
    listingsUi.allListings = false
    nameReview.showPointEvidence(pointPanelHTML(model, state, listingsUi))
    syncInspectorLayout()
    return
  }
  // Opening a point from Rankings, Campaigns, or Head-to-head immediately shows who ranks there.
  if (caps.perPointListings && ['visibility', 'campaigns', 'matchup'].includes(state.view) && ['factions', 'campaigns', 'point', 'competitors', 'study', 'strategy'].includes(state.tab)) state.tab = 'point'
  if (state.region !== 'all' && workbench.classList.contains('strategy-docked')) {
    state.region = strategyIntelligence(model).regions.find(r => r.id !== 'all' && r.originIds.includes(id))?.id || 'all'
  }
  if (state.view === 'factions' && caps.perPointListings) { const p = model.points.find(pt => pt.id === id), top = winnerAt(p?.observations?.[state.query]); if (top && model.businesses.some(b => b.id === top.id)) { focusLeader(top.id); return } }
  workbench.classList.add('evidence-open')
  render()
}

function syncInspectorLayout() {
  const ws = $('.workspace')
  if (!ws) return
  const isOpen = state.view === 'keyword-stuffing' && Boolean(nameReview?.hasOpenInspector?.())
  const changed = ws.classList.contains('inspector-open') !== isOpen
  ws.classList.toggle('inspector-open', isOpen)
  if (changed && map) {
    clearTimeout(inspectorTimer)
    map.invalidateSize({ pan: false })
    inspectorTimer = setTimeout(() => { if (!destroyed && map) map.invalidateSize({ pan: false }) }, 180)
  }
}

function viewAllowed(view) {
  if (view === 'factions') return caps.perPointListings
  if (view === 'matchup') return caps.strategyRoom && caps.perPointListings
  if (view === 'keyword-stuffing') return caps.nameReview
  return true
}

function dismissToast() {
  clearTimeout(announce.timer)
  $('#toast')?.classList.remove('visible')
}

function setView(view) {
  if (!names[view]) throw new Error('Unknown view')
  if (!viewAllowed(view)) return
  dismissToast()
  if (view === 'matchup' && !state.rival) { strategyRoom.open(); return }
  if (view !== 'matchup') { state.region = 'all'; state.rival = null }
  if (view === 'keyword-stuffing') strategyRoom?.close()
  state.view = view
  investigationIds = null
  if (view === 'campaigns') { state.business = model.targetId; state.tab = 'campaigns'; state.point = null }
  else if (view === 'factions') state.tab = 'factions'
  else if (view === 'keyword-stuffing') state.tab = 'factions'
  else if (state.tab === 'campaigns') state.tab = 'factions'
  render()
  $('#side-content').scrollTop = 0
}

function focusCampaignPlay(playId, { fromRail = false } = {}) {
  const eng = campaignEngine(model)
  const play = eng.queries?.[state.query]?.plays?.find(p => p.id === playId)
  if (!play) return
  campaign.playId = campaign.playId === playId ? null : playId
  campaign.avoidId = null
  campaign.isolateLayer = null
  investigationIds = null
  state.point = null
  state.tab = 'campaigns'
  render()
  if (campaign.playId && !fromRail) revealInRail(`[data-play-card="${attrEscape(playId)}"]`)
  if (campaign.playId && play.originIds.length) {
    fitOrigins(play.originIds)
  } else {
    fitStudy(true)
  }
}

function focusCampaignAvoid(avoidId, { fromRail = false } = {}) {
  const eng = campaignEngine(model)
  const avoids = mergedAvoidList(eng, state.query, campaign.research)
  const item = avoids.find(a => a.id === avoidId)
  if (!item) return
  campaign.avoidId = campaign.avoidId === avoidId ? null : avoidId
  campaign.playId = null
  campaign.isolateLayer = null
  investigationIds = null
  state.point = null
  state.tab = 'campaigns'
  render()
  if (campaign.avoidId && !fromRail) revealInRail(`[data-avoid-card="${attrEscape(avoidId)}"]`)
  if (campaign.avoidId && item.originIds?.length) {
    fitOrigins(item.originIds)
  } else {
    fitStudy(true)
  }
}

function clearCampaignFocus() {
  campaign.playId = null
  campaign.avoidId = null
  campaign.isolateLayer = null
  investigationIds = null
  render()
  fitStudy(true)
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
  animateToBounds(points.map(p => [p.lat, p.lng]), { padding: [55, 60], maxZoom: 12.8 })
}

function inspectRegion({ regionId = 'all', queryId = state.query, rivalId = null }) {
  const region = strategyIntelligence(model).regions?.find(r => r.id === regionId)
  if (!region || !model.queries.some(q => q.id === queryId)) throw new Error('Unknown study area or query')
  if (rivalId && (!model.businesses.some(b => b.id === rivalId) || rivalId === model.targetId)) throw new Error('Choose a distinct observed rival')
  Object.assign(state, { region: regionId, query: queryId, rival: rivalId, business: model.targetId,
    view: rivalId ? 'matchup' : 'visibility', tab: 'strategy', point: null })
  campaign.playId = null
  campaign.avoidId = null
  investigationIds = null
  render()
  fitOrigins(region.originIds)
}

async function loadCampaignResearch(fallbackInput = null) {
  campaign.research = null
  if (model.limited || !caps.campaignResearch) return
  const currentModel = model
  try {
    const url = await resolveStudyAttachment({ attachment: 'campaign_research',
      explicit: params.get('research'), studyURL: params.get('study'), model: currentModel, baseURL: location.href })
    if (model !== currentModel) return
    let input = null
    if (url) {
      const response = await fetch(url, { cache: 'no-store' })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      input = await response.json()
      if (model !== currentModel) return
    } else if (fallbackInput && !params.get('research') && !params.get('study')) {
      input = fallbackInput
    } else {
      return
    }
    const research = validateCampaignResearch(input, currentModel, campaignEngine(currentModel))
    if (model === currentModel) {
      campaign.research = research
      const pendingAvoid = !embedded && state.view === 'campaigns' && !campaign.avoidId ? initialParams.get('avoid') : null
      if (pendingAvoid && mergedAvoidList(campaignEngine(currentModel), state.query, research).some(a => a.id === pendingAvoid)) {
        campaign.avoidId = pendingAvoid
        campaign.playId = null
      }
      render()
      if (pendingAvoid && campaign.avoidId === pendingAvoid) revealInRail(`[data-avoid-card="${attrEscape(pendingAvoid)}"]`)
      strategyRoom?.refresh?.()
    }
  } catch (error) { if (model === currentModel) announce(`Campaign research unavailable: ${error.message}`) }
}

function metricHTML(b) {
  const m = businessMetrics(model, state.query, b.id)
  return `<div class="metrics"><div><strong>${m.top3Pct.toFixed(1)}<small>%</small></strong><span>Top 3 coverage</span></div>
    <div><strong>${m.found}<small>/${m.scored ?? model.points.length}</small></strong><span>Locations found${m.limited ? ` · ${m.limited} can't see` : ''}</span></div>
    <div><strong>${m.average?.toFixed(1) ?? 'n/a'}</strong><span>Avg. when found</span></div></div>`
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
    <button class="text-button" data-business="${escape(model.targetId)}" data-business-primary="1">View primary business</button></div>
    <div class="business-list">${result.rows.map(({ business: b, metrics: m, position }) => {
      return `<button class="business-row ${b.target ? 'primary' : ''} ${b.id === state.business ? 'selected' : ''}" data-business="${escape(b.id)}" aria-pressed="${b.id === state.business}">
        <span class="leaderboard-position" aria-label="Observed field position ${position}" title="Rank ${position} across the full observed field">${position}</span>
        <span class="business-dot" style="--business-color:${state.view === 'factions' && (b.shortlisted !== false || b.id === state.business) ? colorFor(b.id) : b.id === state.business ? '#e3232d' : '#707070'}">${b.target ? '◎' : ''}</span>
        <span class="business-info"><span class="business-name">${escape(b.name)}</span>${caps.profiles && b.address ? `<span class="business-address">${escape(b.address)}</span>` : ''}<span class="mini-track"><span style="width:${m.top3Pct}%"></span></span></span>
        <span class="business-score">${m.top3Pct.toFixed(1)}<small>%</small>${b.target ? '<em>PRIMARY</em>' : ''}</span>
      </button>`
    }).join('') || '<p class="list-caption">No matching profiles.</p>'}</div>
    <div class="field-pagination"><button data-field-page="-1" ${result.page === 0 ? 'disabled' : ''}>Previous</button><span>${result.total} profiles · ${result.page + 1}/${result.pages}</span><button data-field-page="1" ${result.page + 1 >= result.pages ? 'disabled' : ''}>Next</button></div>
    <p class="list-caption">Positions refer to all ${model.businesses.length} observed profiles, including when filtered. Ties use top 20 visibility points (21 − rank); equal scores share a position. The shortlist is a saved comparison set, not the whole market.</p>
    <div class="selection-card"><span class="eyebrow">SELECTED BUSINESS · FIELD #${selectedPosition}</span><h3>${escape(selected.name)}</h3>${metricHTML(selected)}
      ${caps.profiles && selected.address ? `<p>${escape(selected.address)}</p>` : ''}
      <p>${!caps.profiles ? '' : selected.rating ? `${escape(selected.rating)} rating · ${escape(selected.reviews ?? 'Unknown')} reviews` : 'Profile details not included in this sample.'}</p>
      ${selected.selection ? `<p>Saved shortlist selection #${escape(selected.selection.position)} · all-query visibility score ${escape(selected.selection.visibility_score.toLocaleString())}<br>${escape(selected.selection.categories?.join(' · ') || '')}</p>` : '<p>Observed profile. Appearance in search results does not establish service fit or business relevance.</p>'}</div>`
}

function renderPoint() {
  if (listingsUi.point !== state.point) { listingsUi.point = state.point; listingsUi.allListings = false }
  return pointPanelHTML(model, state, listingsUi)
}

// Business focus in Local leaders: dim the rest and draw the focused profile's 3-pack
// plateau, top-10 reach and flip targets. Picking the focused business again clears it unless locked (double-click).
function focusesTerritory() { return state.view === 'factions' && model.geometry === 'hex_radius' }
function focusLeader(id, { fit = false, lock = false, fromRail = false } = {}) {
  if (!focusesTerritory()) {
    if (state.view === 'factions') state.tab = 'factions'
    selectBusiness(id, { reveal: !fromRail, fromRail })
    if (fit) fitLeaders(id)
    return
  }
  if (!lock && state.focus === id) { clearFocus(); return }
  state.focus = id
  state.tab = 'factions'
  if (!fromRail && leaderSearch.trim()) {
    const needle = leaderSearch.trim().toLocaleLowerCase()
    const match = localLeaders(model, state.query, 1).rows.find(r => r.business.id === id)
    const visible = match && [match.business.name, match.business.address, match.badge, match.business.cid]
      .some(v => String(v || '').toLocaleLowerCase().includes(needle))
    if (!visible) leaderSearch = ''
  }
  selectBusiness(id, { fromRail })
  if (!fromRail) revealInRail(`[data-leader="${attrEscape(id)}"]`)
  if (fit) fitLeaders(id)
}
function clearFocus() {
  if (!state.focus) return
  state.focus = null
  render()
}
function renderFocusPill(business, overlay, mode = 'focus') {
  const pill = $('#focus-pill')
  pill.hidden = !overlay
  if (!overlay) { pill.innerHTML = ''; return }
  const stats = overlay.stats, blocker = stats.topBlocker
  if (mode === 'elevation') {
    const has30 = (overlay.depth || 20) >= 30
    pill.style.setProperty('--business-color', '#00e5ff')
    pill.innerHTML = `<i style="background:#00e5ff"></i><b>${escape(business.name)}</b>`
      + `<span><b style="color:#00ffff">#1:</b> ${stats.wins}</span>`
      + `<span><b style="color:#00ff8e">3-Pack:</b> ${stats.top3Count}</span>`
      + `<span><b style="color:#facc15">Page 1 (1-10):</b> ${stats.page1Count}</span>`
      + `<span><b style="color:#ef4444">Page 2 (11-20):</b> ${stats.page2Count}</span>`
      + (has30 ? `<span><b style="color:#9f2c3c">Page 3 (21-30):</b> ${stats.page3Count}</span>` : '')
      + (blocker ? `<span class="focus-blocker">Top blocker at #2: ${escape(blocker.name)} (${blocker.count})</span>` : '')
      + `<small>30-layer topography: every single rank draws a contour line (packed lines = steep rank drop). Bold lines mark #1, 3-Pack, Page 1 (10), Page 2 (20)${has30 ? ', Page 3 (30)' : ''}.</small>`
    return
  }
  pill.style.setProperty('--business-color', colorFor(business.id))
  const eStats = overlay.elevation?.stats
  pill.innerHTML = `<i></i><b>${escape(business.name)}</b><span>Leads ${stats.wins} pts</span><span>#2 at ${stats.rank2Points.length} more</span><span>#3 at ${stats.rank3Points.length} more</span>`
    + (eStats ? `<span><b style="color:#facc15">P1:</b> ${eStats.page1Count}</span><span><b style="color:#ef4444">P2:</b> ${eStats.page2Count}</span>` : '')
    + (blocker ? `<span class="focus-blocker">Top blocker at #2: ${escape(blocker.name)} (${blocker.count})</span>` : '')
    + `<button id="clear-focus" type="button" aria-label="Clear business focus">Clear</button>`
    + `<small>${eStats ? '30-layer topography draped over rival empires (Cyan #1, Emerald 3-Pack, Gold Page 1, Crimson Page 2, Burgundy Page 3).' : 'Solid outline: 3-pack plateau. Dashed outline: top-10 reach.'} ${stats.adjacentRank2Count} of the #2 points touch its own territory.</small>`
}
function leaderChipsHTML() {
  if (model.geometry !== 'hex_radius') return ''
  const rows = localLeaders(model, state.query, 1).rows
  const chips = rows.slice().sort((a, b) => b.wins - a.wins).slice(0, 3)
  const focused = state.focus && rows.find(r => r.business.id === state.focus)
  if (focused && !chips.includes(focused)) chips.push(focused)
  return chips.map(r => `<button type="button" class="leader-chip" data-focus-leader="${escape(r.business.id)}" aria-pressed="${r.business.id === state.focus}" title="Focus ${escape(r.business.name)}"><i style="background:${r.color}"></i><span>${escape(r.badge)} ${escape(r.business.name)}</span></button>`).join('')
}
function territoriesAt(tau) {
  const { outlines, seams } = hexTerritoryFromPrep(territoryPrep, tau)
  outlines.seams = seams
  return outlines
}
// Contested ground: TAU eases between 0 (flush head-to-head borders) and 1, so borders
// crack open exactly where first place is one rank from flipping.
function animateContested() {
  cancelAnimationFrame(tauFrame)
  const from = territoryTau, to = state.contested ? 1 : 0, started = performance.now()
  const instant = matchMedia('(prefers-reduced-motion: reduce)').matches
  const step = now => {
    if (destroyed) return
    const t = instant ? 1 : Math.min(1, Math.max(0, (now - started) / 280))
    territoryTau = from + (to - from) * (1 - (1 - t) ** 3)
    if (territoryPrep && focusesTerritory()) pointsLayer.setTerritories(territoriesAt(territoryTau))
    tauFrame = t < 1 ? requestAnimationFrame(step) : 0
  }
  tauFrame = requestAnimationFrame(step)
}

function renderCompetitors() { return competitorPanelHTML(model, state, listingsUi) }

function renderLeaders() {
  const leaders = localLeaders(model, state.query, 1)
  const allRows = leaders.rows
  const needle = leaderSearch.trim().toLocaleLowerCase()
  const rows = needle
    ? allRows.filter(r => [r.business.name, r.business.address, r.badge, r.business.cid]
      .some(v => String(v || '').toLocaleLowerCase().includes(needle)))
    : allRows
  const coloredPoints = leaders.coloredPoints
  return `<div class="side-intro"><div class="eyebrow">LOCAL LEADERS</div><h2>${allRows.length} first-place winners</h2>
    <p>Target owns crimson; top 15 rival brands get unique high-contrast hues; multi-location branches share a hue family.</p>
    <div class="leader-actions"><button class="text-button" data-fit-leaders>Fit circle + leader bases</button>
    <button class="text-button" data-open-name-review>Review business titles →</button>${state.focus ? '<button class="text-button" data-clear-leader-focus>Clear focus</button>' : ''}</div>
    <label class="field-search-label" for="leader-search">Find a local leader, ID, or address</label><input id="leader-search" type="search" value="${escape(leaderSearch)}" placeholder="Search ${allRows.length} first-place winners" autocomplete="off">
    <p>${needle ? `Showing ${rows.length} of ${allRows.length} winners. ` : ''}${coloredPoints}/${model.points.length} points colored (${(100 * coloredPoints / model.points.length).toFixed(1)}%). Dashed points lack usable first-place evidence.</p></div>
    <div class="business-list">${rows.map(r => `<button class="business-row ${r.business.target ? 'primary' : ''} ${r.business.id === state.business ? 'selected' : ''} ${r.business.id === state.focus ? 'focused' : ''}" data-leader="${escape(r.business.id)}">
      <span class="leader-id" style="--business-color:${r.color}">${r.badge}</span>
      <span class="business-info"><span class="business-name">${escape(r.business.name)}</span>
      <span class="business-address">${escape(r.business.address || 'Address not supplied')}</span>
      <span class="business-location-status">${r.hasBase ? r.outside ? 'Base outside circle' : 'Supplied base' : 'Base coordinates unavailable'}</span></span>
      <span class="business-score">${r.wins}<small> wins</small></span></button>`).join('') || '<p class="list-caption">No matching local leaders.</p>'}</div>
    <p class="list-caption">Click any territory or base diamond to focus its 3-pack/top-10 reach and pull it up here; double-click a diamond or pick a row to frame its full empire. Every base outside the study circle points to its largest connected winning cluster.</p>`
}

function fitLeaders(id = null) {
  const leaders = localLeaders(model, state.query, 1)
  const rows = leaders.rows.filter(r => id ? r.business.id === id : r.major)
  const locations = id ? [] : model.points.map(p => [p.lat, p.lng])
  for (const r of rows) {
    if (id && r.points?.length) {
      for (const p of r.points) locations.push([p.lat, p.lng])
    }
    if (r.hasBase) locations.push([r.business.lat, r.business.lng])
    if (r.center) locations.push([r.center.lat, r.center.lng])
  }
  if (!locations.length) return
  cancelWheelZoom()
  followStudyBounds = false
  animateToBounds(locations, { padding: id ? [76, 76] : [65, 65], maxZoom: id ? 11.6 : 12.6 })
}


function renderStudy() {
  const m = businessMetrics(model, state.query, state.business)
  return `<div class="side-intro"><div class="eyebrow">EVIDENCE & DEFINITIONS</div><h2>What this map tells us</h2></div>
    <div class="study-notes">
      <h3>Rankings</h3><p>Ten bright shades run from pure cyan at rank 1 through green to pure yellow at rank 10. Opacity falls evenly from 100% at rank 1 to 75% at rank 10. Rank 11 switches to pure red at 25% opacity. Ranks 12-30 retain pure red and fade evenly to 2% opacity at rank 30. When pins are layered over topography or territories, balanced translucency and crisp outlines keep streets and contours readable. Hollow outlines indicate absence from the top 30; dashed outlines indicate incomplete evidence. Hover any point to inspect its exact rank.</p>
      ${model.geometry === 'hex_radius' ? '<h3>Topography, triangles &amp; clipping</h3><p>Honeycomb studies render 30-layer hypsometric elevation contours in Rankings and fortress relief contours in Local leaders, clipped by default to the study circle and real coastline. Switch to triangles in Rankings to inspect geometric between-pin estimates over measured pins, or turn topography off for raw pins in Rankings and flat territory polygons in Local leaders. Contested opens head-to-head borders where first place is one rank from flipping.</p><h3>Full circle</h3><p>Every base location inside the study radius is measured for every query. Refined locations sit inside the same view as smaller measured hexagons. A muted dotted mark means the business lies outside that search\'s screen (can\'t see from here): it is never counted as a loss and leaves the stats. Nothing outside the radius is ever searched. When the business still holds the top 3 at half or more of the outermost ring inside the radius, the summary notes that its territory likely extends past the circle and offers growing the circle: a new, larger full-circle study, run as an explicit paid step.</p>' : `<h3>Gradient diamonds</h3><p>Diamonds blend neighboring stop-sign colors, including intersections with two or three measured corners along a radial edge. Missing corners and incomplete results contribute transparency. Diamonds are clipped to the study circle. They are visual blends, not additional searches or predicted ranks.</p>`}
      <h3>Distance rings</h3><p>Rings measure straight-line distance from the primary business, which anchors the study footprint. Selecting a rival changes rankings without moving the study center. Distances and guides are shown in miles; measured locations stay fixed. Rings are reference distances, not ranking or service-area boundaries.</p>
      <h3>Local leaders</h3><p>All first-place winners are shown across the study footprint, ignoring shortlist and base distance. Target owns crimson; the top 15 rival brands get unique high-contrast hues and multi-location branches share a hue family; matching IDs distinguish profiles. Click any territory or base diamond to focus its 3-pack plateau and top-10 reach and bring that profile into view in the right rail. Bases outside the study circle draw a dashed connector to their largest connected winning cluster. Missing base coordinates are never inferred from rankings. This view measures first place, not market share.</p>
      <h3>Business locations</h3><p>The white outline marks the selected business base. Local leaders uses diamonds for supplied business locations. Estimated or missing locations are omitted. A location is not proof of ranking dominance.</p>
      <h3>Strike zones &amp; Winnability relief</h3><p>Campaigns scores every complete pin outside the top three with an ordinal structural index W = 100 * (${CAMPAIGN_WEIGHTS.gap.toFixed(2)}*Gap + ${CAMPAIGN_WEIGHTS.weak.toFixed(2)}*Weak + ${CAMPAIGN_WEIGHTS.lift.toFixed(2)}*Lift + ${CAMPAIGN_WEIGHTS.reach.toFixed(2)}*Reach) * (Fort ? ${CAMPAIGN_WEIGHTS.fortress} : 1) * (Detached ? ${CAMPAIGN_WEIGHTS.detached} : 1). W ranks observed structure only; it is not a ranking probability, demand estimate, or revenue forecast.</p>
      <h3>Study footprint</h3><p>${escape(distanceText(model.sampling?.description || (model.geometry === 'competitive_irregular' ? 'Exploratory irregular sampling around the primary business and competitors.' : 'Saved search locations.'), state.units))} Every compared business and query uses the same locations. Each point retains its measured coordinate. Unsampled areas stay unmeasured.</p>
      <h3>Missing evidence</h3><p>${m.unknown} of ${model.points.length} locations have incomplete or unavailable evidence for the selected business. Amber dashed points are not confirmed ranking failures.</p>
      <h3>Measured &amp; coverage pins</h3><p>Use pins to overlay measured search points over topography or territories, or to toggle unranked hollow outlines and amber dashed incomplete pins in Campaigns and non-hex studies without changing the underlying rankings.</p>
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
  if (destroyed) return
  const reviewing = state.view === 'keyword-stuffing'
  if (reviewing && !nameReview?.getState().open) nameReview?.open()
  else if (!reviewing && nameReview?.getState().open) nameReview.close()
  syncInspectorLayout()
  if (scaleUnits !== state.units) {
    scaleControl?.remove()
    scaleControl = L.control.scale({ position: 'bottomleft', imperial: true, metric: false }).addTo(map)
    scaleUnits = state.units
  }
  const selected = model.businesses.find(b => b.id === state.business)
  const m = businessMetrics(model, state.query, state.business)
  const qName = model.queries.find(q => q.id === state.query)?.name || state.query
  $('#study-name').textContent = model.name
  $('#study-location').textContent = model.location
  $('#study-kind').textContent = model.kind
  $('#study-date').textContent = model.evidence?.observed_from ? `Observed ${formatDate(model.evidence.observed_from)}` : model.generatedAt ? `Exported ${new Date(model.generatedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}` : 'Historical proof · date unavailable'
  $('#query').innerHTML = model.queries.map(q => `<option value="${escape(q.id)}" ${q.id === state.query ? 'selected' : ''}>${escape(q.name)}</option>`).join('')
  $('#query-scope').textContent = `${model.points.length} locations · ${model.queries.length} ${model.queries.length === 1 ? 'query' : 'queries'}`
  const views = isFileOrigin ? [] : (model.studyViews || [])
  $('#sampling-view').hidden = !views.length
  $('#sampling-view').innerHTML = views.map(v => `<option value="${escape(v.url)}" ${params.get('study') === v.url ? 'selected' : ''}>${escape(distanceText(v.label, state.units))}</option>`).join('')

  const eng = state.view === 'campaigns' ? campaignEngine(model) : null
  const qEng = eng?.queries?.[state.query] || null
  const selectedCase = reviewing ? nameReview?.getSelectedCase?.() : null
  const selectedSuspectTerr = selectedCase ? suspectTerritory(model, selectedCase.businessId || selectedCase.id) : null
  const selectedSuspectQ = selectedSuspectTerr?.byQuery?.[state.query] || null

  if (state.view === 'factions') {
    $('#map-business').textContent = 'Local leaders'
  } else if (state.view === 'campaigns') {
    $('#map-business').textContent = 'Winnability relief'
  } else if (reviewing) {
    if (selectedCase) {
      const cTitle = selectedCase.profile?.name || selectedCase.name
      $('#map-business').textContent = `${cTitle} / ${qName} / ${selectedSuspectQ?.firstPlaces ?? 0} first places`
    } else {
      $('#map-business').textContent = 'Keyword stuffing'
    }
  } else {
    $('#map-business').textContent = selected.name
  }

  const cleanSamplingSubtitle = raw => distanceText(raw, state.units).replace(/(\d+(?:\.\d+)?)\s*mi radius\s*\(\1(?:\.00)?\s*mi\)/i, '$1 mi radius')
  $('#map-subtitle').textContent = state.view === 'campaigns' && qEng
    ? `${model.name} · ${qName} · top score ${qEng.stats.maxW}`
    : reviewing
      ? (selectedCase ? `Suspect footprint vs your top 10 (${qName})` : `${nameReview?.getFlaggedCases?.().length ?? 0} flagged profiles · click a row or crimson diamond`)
      : cleanSamplingSubtitle(model.sampling?.description || (model.geometry === 'competitive_irregular' ? 'Exploratory locations · irregular sampling' : 'Measured search locations')) + (state.view === 'factions' ? '' : model.geometry === 'hex_radius' && state.view === 'visibility' ? ' · star marks the business' : ' · ◎ business base')

  const archiveWarning = model.controls?.search_this_area === true
    ? 'Viewport-restricted archive: straight edges may reflect the Google search window, not competitive reach.' : ''
  $('#view-description').innerHTML = (archiveWarning ? `<span class="archive-warning">${archiveWarning}</span>` : '')
    + `<span class="mode-description" title="${escape(explanations[state.view])}">${escape(explanations[state.view])}</span>`

  // Live 5-button toolbar per-view meaning table (Section 3.2):
  // Campaigns and Keyword stuffing have ZERO disabled buttons on hex studies!
  const isHex = model.geometry === 'hex_radius'
  const hexRankings = isHex && state.view === 'visibility'
  const isCampaigns = state.view === 'campaigns'
  const isKeyword = reviewing
  const contestedToggle = focusesTerritory() || (isHex && (isCampaigns || isKeyword))
  const topoAvailable = isHex && ['visibility', 'factions', 'campaigns', 'keyword-stuffing'].includes(state.view)
  const trianglesAvailable = isHex && ['visibility', 'campaigns', 'keyword-stuffing'].includes(state.view)

  const topoBtn = $('#elevation-contours')
  topoBtn.disabled = !topoAvailable
  topoBtn.setAttribute('aria-pressed', topoAvailable ? state.contours : false)
  topoBtn.title = !topoAvailable ? 'Available on hexagonal circular studies'
    : state.view === 'factions' ? 'Toggle fortress relief and focused-leader elevation contours'
    : isCampaigns ? 'Toggle Winnability relief contours (off shows flat zone-class pins)'
    : isKeyword ? 'Toggle 30-layer rank elevation for the selected profile'
    : 'Toggle 30-layer rank elevation contours'

  const trianglesBtn = $('#triangle-estimates')
  trianglesBtn.disabled = !trianglesAvailable
  trianglesBtn.setAttribute('aria-pressed', trianglesAvailable ? state.blends : false)
  trianglesBtn.title = !trianglesAvailable ? 'Available in Rankings, Campaigns and Keyword stuffing'
    : isCampaigns ? 'Toggle between-pin ember W estimate triangles'
    : isKeyword ? 'Toggle between-pin rank estimate triangles for the selected profile'
    : 'Toggle geometric between-pin estimate triangles'

  const contestedBtn = $('#contested-ground')
  contestedBtn.disabled = !contestedToggle
  contestedBtn.setAttribute('aria-pressed', contestedToggle ? state.contested : false)
  contestedBtn.textContent = isCampaigns ? 'flip seams' : isKeyword ? 'overlap only' : 'contested'
  contestedBtn.title = !contestedToggle ? 'Available in Local leaders, Campaigns and Keyword stuffing'
    : isCampaigns ? 'Animate flip seams and enable seam hover details'
    : isKeyword ? 'Overlap only: keep pins where selected profile is top three and primary is top 30'
    : 'Open borders where first place is one rank from flipping'

  const pinsBtn = $('#grid-dots')
  pinsBtn.disabled = false
  pinsBtn.setAttribute('aria-pressed', topoAvailable ? state.showDots : state.coverage)
  pinsBtn.title = isCampaigns ? 'Show measured pins colored by zone class with W decomposition on hover'
    : isKeyword ? 'Show measured search pins for the selected profile'
    : topoAvailable ? 'Show measured search pins over map layers'
    : 'Toggle unranked and incomplete coverage pins'

  const ringsBtn = $('#distance-rings')
  ringsBtn.disabled = false
  ringsBtn.setAttribute('aria-pressed', state.rings)
  ringsBtn.title = isCampaigns ? 'Toggle distance rings and out-of-reach boundary ring' : 'Toggle concentric mile distance rings'

  $('#map').classList.toggle('translucent-cells', state.translucent)
  root.querySelectorAll('[data-view]').forEach(b => b.setAttribute('aria-pressed', b.dataset.view === state.view))
  root.querySelectorAll('[data-tab]').forEach(b => b.setAttribute('aria-pressed', b.dataset.tab === state.tab))
  $('[data-view="matchup"]').hidden = state.view !== 'matchup'
  const showAreaTab = !(state.region === 'all' && state.view !== 'matchup' && state.tab !== 'strategy')
  $('[data-tab="strategy"]').hidden = !showAreaTab
  $('[data-tab="campaigns"]').hidden = !isCampaigns
  $('[data-tab="factions"]').hidden = isCampaigns || showAreaTab
  $('.side-tabs').hidden = reviewing
  if (map?.doubleClickZoom) {
    if (focusesTerritory()) map.doubleClickZoom.disable()
    else map.doubleClickZoom.enable()
  }

  const sideContent = $('#side-content')
  const prevScrollTop = sideContent.scrollTop
  const prevTabKey = sideContent.dataset.tabKey || ''
  const nextTabKey = `${state.view}:${state.tab}`
  if (reviewing && nameReview) {
    sideContent.innerHTML = nameReview.renderRailHTML()
  } else {
    sideContent.innerHTML = state.tab === 'strategy'
      ? state.view === 'matchup' ? matchupPanelHTML(strategyMatchup(model, state.query, state.rival, state.region), model, state.query) : regionPanelHTML(model, selectedRegion(), state.query)
      : state.tab === 'campaigns' ? campaignPanelHTML(eng || campaignEngine(model), model, state.query, { selectedPlayId: campaign.playId, selectedAvoidId: campaign.avoidId, research: campaign.research })
      : state.tab === 'factions' ? renderBusinesses()
      : state.tab === 'point' && caps.perPointListings ? renderPoint()
      : state.tab === 'competitors' && caps.perPointListings ? renderCompetitors()
      : renderStudy()
  }
  sideContent.dataset.tabKey = nextTabKey
  sideContent.scrollTop = prevTabKey === nextTabKey ? prevScrollTop : 0

  $('#finding').textContent = `${selected.name} appears in the top 3 at ${m.top3} of ${m.scored ?? model.points.length} sampled locations for "${qName}". ${m.near} locations rank 4 to 10${m.unknown ? `; ${m.unknown} have incomplete evidence` : ''}.`
  $('#inspect-near').disabled = false
  if (state.view === 'factions') {
    const leaders = localLeaders(model, state.query, state.leaderMinimum)
    $('#finding').textContent = `${leaders.rows.length} first-place profiles across ${leaders.coloredPoints} of ${model.points.length} locations. Select any leader in Businesses to frame its full territory and base.`
  }
  const edgeNote = edgeSignalNote(model, state.query)
  if (edgeNote && (selected?.target || state.view === 'factions')) $('#finding').textContent += ` ${edgeNote}`

  const defaultRankLegend = `<span class="rank-scale" aria-label="Ranking color scale, cyan through green to yellow for 1 through 10; fading red for 11 through 30">${RANK_COLORS.map((c, i) => `<span title="Rank ${i + 1} · ${Math.round(RANK_OPACITIES[i] * 100)}% opacity" style="background:${c}${Math.round(RANK_OPACITIES[i] * 255).toString(16).padStart(2, '0')};color:${i >= 10 ? '#eee' : '#050507'}">${i + 1}</span>`).join('')}</span><span><i class="hollow-key"></i> Outside top 30</span><span><i class="unknown-key"></i> Incomplete result set</span>`

  $('#legend').innerHTML = state.view === 'factions'
    ? `${leaderChipsHTML()}<span>${localLeaders(model, state.query, 1).rows.length} #1 leaders · click to focus, double-click to frame</span>`
    : defaultRankLegend

  if (state.view === 'campaigns') {
    const info = campaignFindingInfo(eng, state.query, campaign.playId)
    $('#legend').innerHTML = campaignLegendHTML(campaign.isolateLayer)
    $('#finding').textContent = investigationIds
      ? `${investigationIds.length} locations in this investigation; other observations dimmed.`
      : info.text
    $('#inspect-near').textContent = info.buttonLabel
    $('#inspect-near').dataset.topPlayId = info.playId || ''
    $('#inspect-near').disabled = false
  } else if (reviewing) {
    if (selectedCase && selectedSuspectQ) {
      $('#legend').innerHTML = `<span class="rank-scale" aria-label="Suspect rank scale">${RANK_COLORS.slice(0, 10).map((c, i) => `<span title="Rank ${i + 1}" style="background:${c}${Math.round(RANK_OPACITIES[i] * 255).toString(16).padStart(2, '0')};color:#050507">${i + 1}</span>`).join('')}</span><span><i class="kw-top10-key"></i> Your top 10</span><span><i class="kw-inherit-key"></i> You would inherit</span>`
      const cTitle = selectedCase.profile?.name || selectedCase.name
      $('#finding').textContent = `${cTitle} holds ${selectedSuspectQ.firstPlaces} first places on ${qName}, overlaps your top 30 at ${selectedSuspectQ.overlap}, and you would inherit ${selectedSuspectQ.inherit}.`
      $('#inspect-near').textContent = 'Close inspector'
    } else {
      $('#legend').innerHTML = `${defaultRankLegend}<span><i class="kw-flagged-key"></i> Flagged profile</span>`
      const flaggedCount = nameReview?.getFlaggedCases?.().length ?? 0
      $('#finding').textContent = `${flaggedCount} profiles in current filter. Click any row in the rail or a hollow crimson diamond on the map to inspect territory and evidence.`
      $('#inspect-near').textContent = 'Inspect top suspect →'
    }
    $('#inspect-near').disabled = false
  } else if (state.view === 'factions') {
    $('#inspect-near').textContent = 'Explore leader bases →'
    $('#inspect-near').disabled = false
  } else {
    $('#inspect-near').textContent = 'Explore campaign areas →'
  }

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
  drawMap()
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

function syncHoveredLeaderDOM() {
  const activeId = hoveredLeaderId || state.focus
  for (const entry of leaderBaseEntries) {
    const isHovered = hoveredLeaderId && entry.id === hoveredLeaderId
    const isFocused = state.focus && entry.id === state.focus
    const isLit = !!(isHovered || isFocused)
    const isDimmed = !!(activeId && !isLit)
    const el = entry.marker.getElement()
    if (el) {
      el.classList.toggle('leader-hovered', isLit)
      el.classList.toggle('leader-dimmed', isDimmed)
    }
    entry.marker.setZIndexOffset(isHovered ? 2600 : isFocused ? 2300 : entry.id === state.business ? 1500 : 1100)
    if (entry.polyline) {
      const show = entry.alwaysVisible || isLit
      entry.polyline.setStyle({
        opacity: !show ? 0 : isLit ? .95 : isDimmed ? .2 : .6,
        weight: isLit ? 2.6 : 1.8,
      })
    }
    if (entry.clusterCircle) {
      const show = entry.alwaysVisible || isLit
      entry.clusterCircle.setStyle({
        opacity: !show ? 0 : isLit ? 1 : isDimmed ? .22 : .8,
        weight: isLit ? 2.5 : 1.8,
      })
    }
  }
  root.querySelectorAll('#side-content [data-leader]').forEach(row => {
    row.classList.toggle('leader-row-hovered', !!(hoveredLeaderId && row.dataset.leader === hoveredLeaderId))
  })
}

function setHoveredLeader(id) {
  const next = state.view === 'factions' && id ? id : null
  if (hoveredLeaderId === next) {
    syncHoveredLeaderDOM()
    return
  }
  hoveredLeaderId = next
  pointsLayer?.setHoverLeader(hoveredLeaderId)
  syncHoveredLeaderDOM()
}

function humanPointLabel(p, anchor) {
  if (!p) return ''
  if (anchor && Number.isFinite(anchor.lat) && Number.isFinite(anchor.lng) && Number.isFinite(p.lat) && Number.isFinite(p.lng)) {
    const dLat = p.lat - anchor.lat
    const dLng = (p.lng - anchor.lng) * Math.cos(anchor.lat * Math.PI / 180)
    const miles = Math.hypot(dLat, dLng) * 69.0
    if (miles < 0.15) return 'Center'
    const angle = (Math.atan2(dLng, dLat) * 180 / Math.PI + 360) % 360
    const dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    const dir = dirs[Math.round(angle / 45) % 8]
    return `${miles.toFixed(1)} mi ${dir}`
  }
  return p.id
}

function campaignPinTooltip(cell, queryName) {
  if (!cell || cell.zone === 'unknown') return `${escape(queryName)} · incomplete evidence`
  if (cell.zone === 'hold') {
    return `<b>${escape(queryName)}</b> · rank ${cell.rank} · ${cell.thin ? 'thin hold (rank 3)' : 'hold'}`
  }
  const rankText = cell.rank ? `rank ${cell.rank}` : 'outside 30'
  const wText = cell.w !== null ? `Score ${cell.w}/100` : 'Score n/a'
  const partsLine = cell.w !== null
    ? `<br>Gap ${Math.round(cell.gap * 100)}% · Blocker weakness ${Math.round(cell.weak * 100)}% · Reach ${Math.round(cell.reach * 100)}%`
    : ''
  const mp = (cell.mustPass || []).slice(0, 3)
    .map(b => `${escape(b.name)} (${b.rating != null ? b.rating.toFixed(1) : 'n/a'}★, ${b.reviews != null ? b.reviews.toLocaleString('en-US') : '0'})`)
    .join(', ')
  const mpLine = mp ? `<br>Must pass: ${mp}` : ''
  return `<b>${escape(queryName)}</b> · ${rankText} · <b>${wText}</b> · ${escape(cell.zone.replace(/_/g, ' '))}${partsLine}${mpLine}`
}

function drawMap() {
  if (!map) return
  basesLayer.clearLayers()
  rangeLayer.clearLayers()
  coverageLayer.clearLayers()
  const anchor = model.businesses.find(b => b.id === model.targetId)
  const isCampaigns = state.view === 'campaigns'
  const isKeyword = state.view === 'keyword-stuffing'
  const eng = isCampaigns ? campaignEngine(model) : null
  const qEng = eng?.available ? eng.queries?.[state.query] : null
  const selectedCase = isKeyword ? nameReview?.getSelectedCase?.() : null
  const suspectId = selectedCase ? (selectedCase.businessId || selectedCase.id) : null
  const suspectTerr = suspectId ? suspectTerritory(model, suspectId) : null
  const suspectQ = suspectTerr?.byQuery?.[state.query] || null
  const activeBusinessId = isKeyword && suspectId ? suspectId : isCampaigns ? model.targetId : state.business

  if (['radius_grid', 'hex_radius'].includes(model.geometry)) {
    L.circle([anchor.lat, anchor.lng], { pane: 'referencePane', radius: model.sampling.radius_km * 1000,
      color: '#969696', weight: 1, opacity: .65, dashArray: '4 6', fill: false, interactive: false }).addTo(coverageLayer)
  }
  if (state.rings && Number.isFinite(anchor?.lat) && Number.isFinite(anchor?.lng)) {
    for (const { km, label } of distanceRings(state.units, model.sampling?.radius_km)) {
      if (model.sampling?.radius_km && km > model.sampling.radius_km + .00001) continue
      L.circle([anchor.lat, anchor.lng], {
        pane: 'referencePane', radius: km * 1000, color: '#cccccc', weight: 1,
        opacity: .4, fill: false, interactive: false,
      }).addTo(rangeLayer)
      const labelPoint = destination(anchor.lat, anchor.lng, km, 45)
      L.marker(labelPoint, {
        pane: 'referenceLabelPane', interactive: false, keyboard: false,
        ringKm: km, ringCenter: [anchor.lat, anchor.lng],
        icon: L.divIcon({ className: 'distance-label', html: label, iconSize: [38, 18], iconAnchor: [19, 9] }),
      }).addTo(rangeLayer)
    }
    // Campaigns: dashed ring at the selected query's out-of-reach boundary.
    const outMiles = qEng?.stats?.outOfReachFromMiles
    if (isCampaigns && Number.isFinite(outMiles) && outMiles > 0) {
      const outKm = outMiles * 1.609344
      if (!model.sampling?.radius_km || outKm <= model.sampling.radius_km + .00001) {
        L.circle([anchor.lat, anchor.lng], {
          pane: 'referencePane', radius: outKm * 1000, color: '#94a3b8', weight: 1.2,
          opacity: .50, dashArray: '5 6', fill: false, interactive: false,
        }).addTo(rangeLayer)
        const outLabelPt = destination(anchor.lat, anchor.lng, outKm, 315)
        L.marker(outLabelPt, {
          pane: 'referenceLabelPane', interactive: false, keyboard: false,
          icon: L.divIcon({ className: 'distance-label out-of-reach-label', html: `reach &lt;10% &gt;${outMiles} mi`, iconSize: [102, 18], iconAnchor: [51, 9] }),
        }).addTo(rangeLayer)
      }
    }
  }

  const focusedPlay = isCampaigns && campaign.playId ? qEng?.plays?.find(p => p.id === campaign.playId) : null
  const focusedAvoid = isCampaigns && campaign.avoidId ? mergedAvoidList(eng, state.query, campaign.research).find(a => a.id === campaign.avoidId) : null
  const focusedIds = investigationIds ? new Set(investigationIds)
    : focusedPlay ? new Set(focusedPlay.originIds)
    : focusedAvoid ? new Set(focusedAvoid.originIds || [])
    : null
  const regionIds = state.region !== 'all' ? new Set(selectedRegion()?.originIds || []) : null
  const matchupCells = state.view === 'matchup'
    ? new Map(strategyMatchup(model, state.query, state.rival, 'all').cells.map(c => [c.id, c])) : null
  const overlapSet = isKeyword && suspectId && state.contested ? new Set(suspectQ?.overlapIds || []) : null

  const cells = []
  const leaders = localLeaders(model, state.query, state.leaderMinimum)
  const hexStep = model.geometry === 'hex_radius' ? model.sampling?.hex?.step : null
  const hexTerritory = state.view === 'factions' && !!(hexStep || model.geometry === 'hex_radius')
  const hexRankings = state.view === 'visibility' && !!(hexStep || model.geometry === 'hex_radius')
  const hexCampaigns = isCampaigns && !!(hexStep || model.geometry === 'hex_radius')
  const hexKeyword = isKeyword && !!(hexStep || model.geometry === 'hex_radius')
  const pinsOverSurface = ((hexRankings || hexCampaigns || hexKeyword) && (state.contours || state.blends) && state.showDots) || (hexTerritory && state.showDots)
  const effectiveTranslucent = state.translucent || pinsOverSurface
  const emberTrianglesMode = isCampaigns && state.blends

  const drawn = model.points
  for (let pi = 0; pi < drawn.length; pi++) {
    const p = drawn[pi]
    if (hexStep && (!p.hex || p.observations[state.query]?.status === 'missing')) continue
    const o = observationFor(model, p, state.query, activeBusinessId)
    const top = winnerAt(p.observations[state.query])
    const majorLeader = top && leaders.majorIds.has(top.id)
    const highlightedLeader = majorLeader || (top && (top.id === state.business || top.id === state.focus))
    const presentation = rankPresentation(model, p, state.query, activeBusinessId)
    const ptLabel = humanPointLabel(p, anchor)
    let color = presentation.color
    let opacity = rankFillOpacity(presentation.rank, effectiveTranslucent)
    let kind = presentation.kind
    let label = `${escape(ptLabel)} · ${escape(presentation.description)}`
    let muted = !!(regionIds && !regionIds.has(p.id))

    if (state.view === 'factions') {
      color = highlightedLeader ? colorFor(top.id) : 'transparent'
      opacity = effectiveTranslucent ? .55 : 1
      kind = highlightedLeader ? 'ranked' : top ? 'other' : 'unknown'
      label = `${escape(ptLabel)} · ${escape(top ? `${leaders.byId.get(top.id)?.badge || ''} · ${top.name} · Rank 1 · ${leaders.byId.get(top.id)?.wins || 1} wins${majorLeader ? '' : ' · below highlight threshold'}` : 'First-place result unavailable')}`
    } else if (isCampaigns && qEng) {
      const cCell = qEng.cellById.get(p.id)
      const zone = cCell?.zone || 'unknown'
      if (emberTrianglesMode || (!hexStep && zone !== 'hold' && zone !== 'unknown' && zone !== 'fortress' && zone !== 'detached')) {
        const ember = emberColorForW(cCell?.w)
        color = zone === 'hold' ? ZONE_COLORS.hold : ember.color
        opacity = zone === 'hold' ? .85 : ember.opacity
      } else {
        color = ZONE_COLORS[zone] || 'transparent'
        opacity = zone === 'hold' ? .88 : zone === 'strike' ? .92 : zone === 'contest' ? .82 : zone === 'long' ? .62 : zone === 'fortress' ? .78 : zone === 'detached' ? .52 : 0
      }
      kind = zone === 'unknown' ? 'unknown' : (zone === 'absent' || zone === 'out_of_reach') ? 'nr' : 'ranked'
      if (focusedIds && !focusedIds.has(p.id)) muted = true
      if (campaign.isolateLayer) {
        const isoMatch = campaign.isolateLayer === 'hold' ? zone === 'hold'
          : campaign.isolateLayer === 'service_gap' ? cCell?.play === `${state.query}:service_gap`
          : campaign.isolateLayer === 'fortress' ? zone === 'fortress'
          : campaign.isolateLayer === 'detached' ? zone === 'detached'
          : true
        if (!isoMatch) muted = true
      }
      label = campaignPinTooltip(cCell, qEng.queryName)
    } else if (isKeyword) {
      if (overlapSet && !overlapSet.has(p.id)) muted = true
      if (suspectId) {
        const pObs = observationFor(model, p, state.query, model.targetId)
        const sRankTxt = presentation.rank ? `#${presentation.rank}` : 'outside 30'
        const pRankTxt = pObs.rank ? `#${pObs.rank}` : 'outside 30'
        label = `${escape(p.id)} · Suspect ${sRankTxt} · You ${pRankTxt}`
      }
    } else if (state.view === 'strike') {
      if (!(o.rank >= 4 && o.rank <= 10)) muted = true
    }

    const active = state.point === p.id
    const projected = map.project([p.lat, p.lng], 0)
    const comparison = matchupCells?.get(p.id)
    const comparisonStyle = comparison && MATCHUP_STYLES[comparison.state]
    cells.push({
      id: p.id, lat: p.lat, lng: p.lng, x: projected.x, y: projected.y, spacing: pointSpacings[pi] || spacing,
      leaderId: state.view === 'factions' && highlightedLeader ? top.id : null,
      winnerId: state.view === 'factions' ? top?.id ?? null : null,
      leaderName: top?.name,
      color, opacity, kind, active, muted, coverage: state.coverage,
      dominant: state.view === 'visibility' && presentation.rank === 1,
      label,
    })
    if (comparisonStyle) Object.assign(cells.at(-1), {
      color: comparisonStyle.color, kind: comparisonStyle.kind,
      opacity: state.translucent ? .45 : .9,
      label: `${escape(p.id)} · ${escape(matchupLabel(comparison, model.name, model.businesses.find(b => b.id === state.rival).name))}`,
    })
    if (hexStep) {
      const cell = cells.at(-1)
      const a = 3 * p.hex.unit_q / hexStep, b = 3 * p.hex.unit_r / hexStep
      const nested = Math.abs(a / 3 - Math.round(a / 3)) > 1e-6 || Math.abs(b / 3 - Math.round(b / 3)) > 1e-6
      const unitMiles = model.sampling?.hex?.unit_miles
      const scale = !nested ? 1 : p.hex.rung_miles && unitMiles ? Math.min(1, p.hex.rung_miles / (hexStep * unitMiles)) : .5
      cell.honeycomb = { a, b, state: o.state, nested, scale }
      if (!isCampaigns && !comparisonStyle && state.view !== 'factions' && o.state === 'limited') Object.assign(cell, { kind: 'limited', label: `${escape(p.id)} · ${escape(o.label)}` })
      if (!isCampaigns && !comparisonStyle && state.view !== 'factions' && o.state === 'absent') Object.assign(cell, { kind: 'nr', label: `${escape(p.id)} · ${escape(o.label)}` })
    }
  }

  const blendBoundary = ['radius_grid', 'hex_radius'].includes(model.geometry) && model.sampling?.radius_km
    ? Array.from({ length: 180 }, (_, i) => {
      const [lat, lng] = destination(anchor.lat, anchor.lng, model.sampling.radius_km, i * 2)
      return map.project([lat, lng], 0)
    }) : null
  const cellMap = new Map(cells.map(c => [c.id, c]))
  const diamonds = state.blends && !hexStep && ['visibility', 'factions', 'campaigns', 'keyword-stuffing'].includes(state.view) ? drawBlends(cells, cellMap) : []
  const extrapolateOffshore = Boolean(model.landMaskPolygons?.length)
  const proj = ll => map.project(ll, 0)

  territoryPrep = hexTerritory ? prepareHexTerritory(model.points.filter(p => cellMap.has(p.id)), cellMap, proj, {
    clipRadiusKm: model.sampling?.radius_km || null,
    anchorLatLng: anchor ? [anchor.lat, anchor.lng] : null,
    rankLookup: (pt, lid) => observationFor(model, pt, state.query, lid)?.rank ?? null,
    nameOf: lid => model.businesses.find(b => b.id === lid)?.name,
    extrapolateOffshore,
  }) : null
  if (!tauFrame) territoryTau = state.contested ? 1 : 0
  const territories = hexTerritory ? territoriesAt(territoryTau)
    : state.view === 'factions' ? territoryOutlines(model.points, cellMap, proj) : []
  const focusBusiness = hexTerritory && state.focus ? model.businesses.find(b => b.id === state.focus) : null
  const focusOverlay = focusBusiness ? computeFocusOverlay(model, state.query, state.focus, { project: proj, extrapolateOffshore }) : null
  const focusElevation = focusBusiness && state.contours ? computeElevationStack(model, state.query, state.focus, { project: proj, extrapolateOffshore }) : null
  if (focusOverlay && focusElevation) focusOverlay.elevation = focusElevation
  const leaderRelief = hexTerritory && state.contours ? computeLeaderRelief(model, state.query, { project: proj, extrapolateOffshore }) : null

  let elevOverlay = null
  let campaignOverlay = null
  let keywordOverlay = null

  if (hexRankings && state.contours) {
    elevOverlay = computeElevationStack(model, state.query, state.business, { project: proj, extrapolateOffshore })
  } else if (hexCampaigns && qEng) {
    if (state.contours) {
      const relief = computeScalarElevation(model, state.query, {
        valueAt: pt => {
          const c = qEng.cellById.get(pt.id)
          if (!c || c.wRaw === null) return 0
          if (focusedPlay && !focusedIds.has(pt.id)) return 0
          return c.wRaw
        },
        thresholds: [35, 50, 65, 80],
        compare: 'gte',
        missingValue: 0,
        project: proj,
        extrapolateOffshore,
      })
      relief.indexSpecs = [
        { value: 35, stroke: '#c97b16', alpha: .72, width: 1.3, dash: [] },
        { value: 50, stroke: '#ffb020', alpha: .90, width: 1.9, dash: [] },
        { value: 65, stroke: '#ffd76a', alpha: .96, width: 2.4, dash: [] },
        { value: 80, stroke: '#fff1c4', alpha: 1.0, width: 2.8, dash: [] },
      ]
      relief.dimAlpha = (campaign.avoidId || (campaign.isolateLayer && campaign.isolateLayer !== 'relief')) ? .30 : 1
      elevOverlay = relief
    }
    const holdPlateau = computePinRegion(model, state.query, pt => qEng.cellById.get(pt.id)?.zone === 'hold', { project: proj, extrapolateOffshore })
    const thinHoldParts = computePinRegion(model, state.query, pt => qEng.cellById.get(pt.id)?.thin === true, { project: proj, extrapolateOffshore })
    const fortressAvoids = (qEng.avoid || []).filter(a => a.kind === 'fortress')
    const fortressRegions = fortressAvoids.map(fa => {
      const idSet = new Set(fa.originIds)
      return { avoidId: fa.id, holderId: fa.holderId, name: fa.holderName, parts: computePinRegion(model, state.query, pt => idSet.has(pt.id), { project: proj, extrapolateOffshore }) }
    }).filter(r => r.parts.length > 0)
    const detachedRegions = (eng.landmass?.detached || []).map(comp => {
      const idSet = new Set(comp.originIds)
      const compPts = model.points.filter(pt => idSet.has(pt.id))
      const meanLat = compPts.reduce((s, pt) => s + pt.lat, 0) / Math.max(1, compPts.length)
      const meanLng = compPts.reduce((s, pt) => s + pt.lng, 0) / Math.max(1, compPts.length)
      return {
        avoidId: `${state.query}:detached:${comp.id}`,
        id: comp.id,
        label: comp.pins >= 5 ? `${comp.id} detached` : '',
        anchor: compPts.length ? proj([meanLat, meanLng]) : null,
        parts: computePinRegion(model, state.query, pt => idSet.has(pt.id), { project: proj, extrapolateOffshore }),
      }
    }).filter(r => r.parts.length > 0)

    const sgPlay = qEng.plays.find(p => p.mechanism === 'service_gap')
    let serviceGapRegion = null
    if (sgPlay) {
      const sgSet = new Set(sgPlay.originIds)
      const sgPts = model.points.filter(pt => sgSet.has(pt.id))
      const topPt = sgPts.slice().sort((a, b) => b.lat - a.lat)[0]
      serviceGapRegion = {
        playId: sgPlay.id,
        label: `service gap: ${qEng.queryName}`,
        anchor: topPt ? proj([topPt.lat, topPt.lng]) : null,
        parts: computePinRegion(model, state.query, pt => sgSet.has(pt.id), { project: proj, extrapolateOffshore }),
      }
    }
    const seams = computeCampaignSeams(model, state.query, qEng.cellById, { project: proj, extrapolateOffshore, targetName: model.name })
    campaignOverlay = {
      holdPlateau,
      thinHoldParts,
      fortressRegions,
      detachedRegions,
      serviceGapRegion,
      seams,
      animateSeams: state.contested,
      isolateLayer: campaign.isolateLayer,
      selectedPlayId: campaign.playId,
      selectedAvoidId: campaign.avoidId,
    }
  } else if (hexKeyword) {
    if (state.contours) {
      elevOverlay = computeElevationStack(model, state.query, activeBusinessId, { project: proj, extrapolateOffshore })
    }
    if (suspectId) {
      const primaryStack = computeElevationStack(model, state.query, model.targetId, { project: proj, extrapolateOffshore })
      const top10Level = primaryStack?.levels?.find(l => l.rank === 10)
      keywordOverlay = {
        primaryTop10Parts: top10Level?.parts || [],
        inheritIds: new Set(suspectQ?.inheritIds || []),
      }
    }
  } else if (isKeyword && suspectId) {
    keywordOverlay = {
      primaryTop10Parts: [],
      inheritIds: new Set(suspectQ?.inheritIds || []),
    }
  }

  pointsLayer.setLandMask(model.landMaskPolygons || null, false)
  pointsLayer.setLeaderRelief(leaderRelief, false)
  pointsLayer.setFocus(focusOverlay ? { leaderId: state.focus, color: colorFor(state.focus), plateau: focusOverlay.plateau, reach: focusOverlay.reach,
    elevation: focusElevation, rank2: new Set(focusOverlay.stats.rank2Points), rank3: new Set(focusOverlay.stats.rank3Points) } : null, false)
  pointsLayer.setElevation(elevOverlay, false)
  pointsLayer.setCampaignOverlay(campaignOverlay, false)
  pointsLayer.setKeywordOverlay(keywordOverlay, false)

  const elevBusiness = hexRankings && state.contours ? model.businesses.find(b => b.id === state.business) : null
  if (focusBusiness && focusOverlay) renderFocusPill(focusBusiness, focusOverlay, 'focus')
  else if (elevBusiness && elevOverlay) renderFocusPill(elevBusiness, elevOverlay, 'elevation')
  else renderFocusPill(null, null)

  if (state.view !== 'factions' && hoveredLeaderId) { hoveredLeaderId = null; pointsLayer.setHoverLeader(null) }
  pointsLayer.setHoneycomb(hexStep ? {
    radius: model.sampling.radius_km / model.sampling.spacing_km,
    estimates: (hexRankings || hexCampaigns || hexKeyword) && state.blends,
    marker: state.view === 'visibility' || isCampaigns || isKeyword,
    viewingTarget: isCampaigns || (isKeyword ? !suspectId : state.business === model.targetId),
    glow: state.view === 'visibility' && (!state.contours || state.showDots),
  } : null)

  const hideBulkDots = (state.view === 'factions' || hexRankings || hexCampaigns || hexKeyword) && !state.showDots
  pointsLayer.setData(cells, diamonds, spacing, effectiveTranslucent, blendBoundary, territories, state.clipCircle, hideBulkDots)

  // Interactive markers in basesLayer
  leaderBaseEntries = []
  if (isCampaigns && qEng) {
    // Layer 7: Weak-blocker hollow cracked white diamonds (progressive disclosure: shown when focusing a play or isolating weak_blocker).
    const showWeakBlockers = Boolean(focusedPlay || campaign.isolateLayer === 'weak_blocker')
    const seenWeak = new Set()
    const visiblePlays = showWeakBlockers ? (focusedPlay ? [focusedPlay] : qEng.plays) : []
    const dimWeak = (campaign.isolateLayer && campaign.isolateLayer !== 'weak_blocker') || Boolean(campaign.avoidId)
    for (const play of visiblePlays) {
      for (const h of (play.topHolders || []).slice(0, 3)) {
        if (!Number.isFinite(h.lat) || !Number.isFinite(h.lng) || seenWeak.has(h.id)) continue
        seenWeak.add(h.id)
        const sz = Math.max(10, Math.min(18, 10 + Math.round((h.packCount / Math.max(1, play.points)) * 8)))
        const ratingStr = h.rating != null ? h.rating.toFixed(1) : 'n/a'
        const revStr = h.reviews != null ? h.reviews.toLocaleString('en-US') : '0'
        const labelTxt = `${h.name}  ${ratingStr} / ${revStr}`
        const showPermanentLabel = Boolean(focusedPlay && play.leadHolder?.id === h.id)
        const svg = `<svg width="${sz}" height="${sz}" viewBox="0 0 18 18" aria-hidden="true"><polygon points="9,1 17,9 9,17 1,9" fill="rgba(8,8,8,0.82)" stroke="#ffffff" stroke-width="1.6"/><polyline points="6,5 10,9 8,11 12,14" fill="none" stroke="#ffffff" stroke-width="1.3"/></svg>`
        const html = `<span class="campaign-weak-marker${dimWeak ? ' dimmed' : ''}">${svg}${showPermanentLabel ? `<em class="campaign-marker-label">${escape(labelTxt)}</em>` : ''}</span>`
        L.marker([h.lat, h.lng], {
          icon: L.divIcon({ className: 'campaign-base-icon', html, iconSize: [sz, sz], iconAnchor: [sz / 2, sz / 2] }),
          zIndexOffset: 1700,
        }).bindTooltip(`${escape(labelTxt)} · pack blocker (${h.packCount}/${play.points} pts)`, { direction: 'top', offset: [0, -10] })
          .on('click', e => { L.DomEvent.stopPropagation(e); focusCampaignPlay(play.id) })
          .addTo(basesLayer)
      }
    }
    // Layer 8: Fortress solid crimson squares (subtle in overview, full prominence on avoid/fortress focus).
    const fortressAvoids = (qEng.avoid || []).filter(a => a.kind === 'fortress')
    const fortressFocused = Boolean(campaign.avoidId || campaign.isolateLayer === 'fortress')
    const dimFort = (campaign.isolateLayer && campaign.isolateLayer !== 'fortress') || Boolean(campaign.playId) || !fortressFocused
    for (const fa of fortressAvoids) {
      if (!Number.isFinite(fa.lat) || !Number.isFinite(fa.lng)) continue
      const ratingStr = fa.rating != null ? fa.rating.toFixed(1) : 'n/a'
      const revStr = fa.reviews != null ? fa.reviews.toLocaleString('en-US') : '0'
      const labelTxt = `${fa.holderName}  ${ratingStr} / ${revStr}`
      const isSelectedAvoid = campaign.avoidId === fa.id
      const isDim = dimFort || (campaign.avoidId && !isSelectedAvoid)
      L.marker([fa.lat, fa.lng], {
        icon: L.divIcon({
          className: 'campaign-base-icon',
          html: `<span class="campaign-fortress-sq${isDim ? ' dimmed' : ''}"></span>`,
          iconSize: [11, 11],
          iconAnchor: [5.5, 5.5],
        }),
        zIndexOffset: isSelectedAvoid ? 1850 : 1600,
      }).bindTooltip(`${escape(labelTxt)} · fortress (${fa.pins} guarded pins)`, { direction: 'top', offset: [0, -8] })
        .on('click', e => { L.DomEvent.stopPropagation(e); focusCampaignAvoid(fa.id) })
        .addTo(basesLayer)
    }
    // Square-lattice fallback base star
    if (!hexStep && Number.isFinite(anchor?.lat) && Number.isFinite(anchor?.lng)) {
      L.marker([anchor.lat, anchor.lng], {
        icon: L.divIcon({ className: 'base-marker base-ring', html: '<span class="business-crosshair"></span>', iconSize: [16, 16], iconAnchor: [8, 8] }),
        zIndexOffset: 2000,
      }).addTo(basesLayer)
    }
  } else if (isKeyword && nameReview) {
    const identities = leaderIdentity(model).identities
    if (selectedCase) {
      const biz = model.businesses.find(b => b.id === suspectId)
      if (biz && Number.isFinite(biz.lat) && Number.isFinite(biz.lng)) {
        const badge = identities.get(suspectId)?.badge || 'L?'
        L.marker([biz.lat, biz.lng], {
          icon: L.divIcon({
            className: 'base-marker',
            html: `<span class="kw-suspect-diamond"><b>${escape(badge)}</b></span>`,
            iconSize: [24, 24],
            iconAnchor: [12, 12],
          }),
          zIndexOffset: 2100,
        }).bindTooltip(`${escape(badge)} · ${escape(selectedCase.profile?.name || selectedCase.name)}`, { direction: 'top', offset: [0, -14] })
          .addTo(basesLayer)
      }
    } else {
      // No case selected: small hollow crimson diamond at every flagged profile's coordinates.
      for (const row of nameReview.getFlaggedCases()) {
        const biz = model.businesses.find(b => b.id === (row.businessId || row.id))
        const lat = Number.isFinite(biz?.lat) ? biz.lat : row.location?.lat
        const lng = Number.isFinite(biz?.lng) ? biz.lng : row.location?.lng
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue
        const badge = identities.get(row.businessId || row.id)?.badge || ''
        L.marker([lat, lng], {
          icon: L.divIcon({
            className: 'base-marker',
            html: '<span class="kw-flagged-diamond"></span>',
            iconSize: [14, 14],
            iconAnchor: [7, 7],
          }),
          zIndexOffset: 1650,
        }).bindTooltip(`${escape(badge ? `${badge} · ` : '')}${escape(row.profile?.name || row.name)} · click to inspect`, { direction: 'top', offset: [0, -10] })
          .on('click', e => { L.DomEvent.stopPropagation(e); nameReview.selectCase(row.id) })
          .addTo(basesLayer)
      }
    }
  } else {
    const prominentLeaderIds = state.view === 'factions'
      ? new Set(leaders.rows.filter(r => r.wins >= 3).slice(0, 15).map(r => r.business.id))
      : null
    for (const b of model.businesses) {
      if (state.view === 'factions' && !leaders.majorIds.has(b.id) && b.id !== state.business) continue
      if (typeof b.lat !== 'number' || typeof b.lng !== 'number' || !Number.isFinite(b.lat) || !Number.isFinite(b.lng)) continue
      if (state.view !== 'factions' && b.id !== state.business) continue
      if (hexStep && state.view === 'visibility' && b.target) continue
      const isLeaderView = state.view === 'factions'
      const leader = leaders.byId.get(b.id)
      const isProminent = !isLeaderView || b.target || b.id === state.business || b.id === state.focus || prominentLeaderIds?.has(b.id)
      let polyline = null, clusterCircle = null
      const alwaysVisible = !!(isLeaderView && leader?.outside && leader?.center)
      if (alwaysVisible) {
        polyline = L.polyline([[b.lat, b.lng], [leader.center.lat, leader.center.lng]], {
          color: colorFor(b.id), weight: 1.8, opacity: .65, dashArray: '6 7', interactive: false,
        }).addTo(basesLayer)
        clusterCircle = L.circleMarker([leader.center.lat, leader.center.lng], {
          radius: 5, color: colorFor(b.id), weight: 1.8, opacity: .85, fill: false, interactive: true,
        }).bindTooltip(`${escape(b.name)} · strongest cluster: ${leader.clusterSize} first places`).addTo(basesLayer)
      }
      const baseSize = isLeaderView ? (isProminent ? 28 : 14) : 16
      const marker = L.marker([b.lat, b.lng], {
        icon: L.divIcon({
          className: `base-marker ${isLeaderView ? (isProminent ? 'leader-major' : 'leader-minor') : 'base-ring'}`,
          html: isLeaderView
            ? `<span class="${isProminent ? 'leader-diamond' : 'leader-dot'}" style="--business-color:${colorFor(b.id)}"><b>${leader?.badge || '◎'}</b></span>`
            : '<span class="business-crosshair"></span>',
          iconSize: [baseSize, baseSize],
          iconAnchor: [baseSize / 2, baseSize / 2],
        }),
        title: `${b.name}: supplied business location`, zIndexOffset: b.id === state.business ? 1500 : isProminent ? 1100 : 800,
      }).bindTooltip(`${escape(leader?.badge ? `${leader.badge} · ` : '')}${escape(b.name)} · supplied base${leader?.wins ? ` · ${leader.wins} wins` : ''}${leader?.outside ? ' · outside circle' : ''}${isLeaderView ? ' · click to focus, double-click to frame' : ''}`, { direction: 'top', offset: [0, -14] }).on('click', e => {
        L.DomEvent.stopPropagation(e)
        if (isLeaderView && (e.originalEvent?.detail || 1) >= 2) return
        if (isLeaderView) focusLeader(b.id)
        else selectBusiness(b.id)
      })
      if (isLeaderView) {
        marker.on('dblclick', e => {
          L.DomEvent.stopPropagation(e)
          L.DomEvent.preventDefault(e)
          focusLeader(b.id, { fit: true, lock: true })
        })
        marker.on('mouseover', () => { pointsLayer?.hideTooltip(); setHoveredLeader(b.id) }).on('mouseout', () => setHoveredLeader(null))
      }
      marker.addTo(basesLayer)
      if (isLeaderView) leaderBaseEntries.push({ id: b.id, lat: b.lat, lng: b.lng, wins: leader?.wins || 0, alwaysVisible, marker, polyline, clusterCircle })
    }
  }
  updateZoomPresentation()
  syncHoveredLeaderDOM()
}

function drawBlends(cells, cellById = new Map(cells.map(c => [c.id, c]))) {
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 32
  const ctx = canvas.getContext('2d')
  const textures = new Map()
  const diamonds = []
  const isFactions = state.view === 'factions'
  for (const intersection of gridCorners) {
    const cornerCells = intersection.corners.map(p => p ? cellById.get(p.id) : null)
    let dominantLeaderId = null
    if (isFactions) {
      const counts = new Map()
      for (const c of cornerCells) {
        if (c && c.kind === 'ranked' && c.leaderId) counts.set(c.leaderId, (counts.get(c.leaderId) || 0) + 1)
      }
      if (!counts.size) continue
      const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1])
      const [topId, topCount] = sorted[0]
      const secondCount = sorted[1]?.[1] || 0
      // In Local leaders, only fill a gradient diamond when all 4 surrounding cells belong to the same leader
      // so diamonds never bleed across territory borders or enclave corners.
      if (topCount === 4 && secondCount === 0) {
        dominantLeaderId = topId
      } else {
        continue
      }
    }
    const rgba = cornerCells.map(cell => {
      if (!cell || ['nr', 'unknown', 'other'].includes(cell.kind) || !cell.color?.startsWith('#')) return [0, 0, 0, 0]
      if (isFactions && cell.leaderId !== dominantLeaderId) return [0, 0, 0, 0]
      const baseOpacity = isFactions ? (state.translucent ? .35 : .68) : (cell.opacity ?? 1)
      const alpha = baseOpacity * (cell.muted ? .15 : 1)
      return [1, 3, 5].map(i => parseInt(cell.color.slice(i, i + 2), 16)).concat(Math.round(255 * alpha))
    })
    if (rgba.every(c => c[3] === 0)) continue
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
    const dSpace = Math.min(Math.abs(b.x - a.x), Math.abs(b.y - a.y))
    diamonds.push({ x: center.x, y: center.y, spacing: dSpace > 0 ? dSpace : spacing, texture: textures.get(key), leaderId: dominantLeaderId })
  }
  return diamonds
}

function updateZoomPresentation() {
  if (!map || !pointsLayer) return
  const stepPx = spacing * (2 ** map.getZoom())
  if (Number.isFinite(stepPx) && stepPx > 0) {
    $('#map').style.setProperty('--grid-step-px', `${stepPx.toFixed(2)}px`)
    $('#map').classList.toggle('leaders-compact', stepPx < 15.5)
    $('#map').classList.toggle('leaders-mini', stepPx < 10.5)
  }
  rangeLayer.eachLayer(layer => {
    if (!layer.options.ringKm) return
    const pixels = map.project(layer.options.ringCenter, map.getZoom()).distanceTo(map.project(layer.getLatLng(), map.getZoom()))
    const icon = layer.getElement()
    if (icon) icon.style.display = pixels >= 38 ? '' : 'none'
  })
}

function cancelCameraAnimation() {
  if (cameraFrame) {
    cancelAnimationFrame(cameraFrame)
    cameraFrame = 0
    if (map?._smoothZooming) {
      map._smoothZooming = false
      map.fire('smoothzoomend')
    }
  }
}

function animateToBounds(latlngs, { padding = [65, 65], maxZoom = 12.6, animate = true, duration = 520 } = {}) {
  cancelCameraAnimation()
  if (!map || !latlngs?.length) return
  const bounds = L.latLngBounds(latlngs)
  if (!bounds.isValid()) return
  const target = map._getBoundsCenterZoom(bounds, { padding, maxZoom })
  if (!animate || matchMedia('(prefers-reduced-motion: reduce)').matches || !Number.isFinite(target?.zoom)) {
    fittingStudy = true
    try { map.fitBounds(bounds, { padding, maxZoom, animate: false }) } finally { fittingStudy = false }
    return
  }
  const startZoom = map.getZoom()
  const startPt = map.project(map.getCenter(), 0)
  const targetPt = map.project(target.center, 0)
  const distPx = startPt.distanceTo(targetPt) * (2 ** startZoom)
  if (distPx < 2 && Math.abs(target.zoom - startZoom) < .01) return
  const t0 = performance.now()
  map._smoothZooming = true
  const step = now => {
    const t = Math.min(1, Math.max(0, (now - t0) / duration))
    // Smooth cubic-bezier ease-in-out S-curve
    const ease = t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2
    const curPt = L.point(startPt.x + (targetPt.x - startPt.x) * ease, startPt.y + (targetPt.y - startPt.y) * ease)
    const curLatLng = map.unproject(curPt, 0)
    const curZoom = startZoom + (target.zoom - startZoom) * ease
    fittingStudy = true
    const done = t >= 1
    if (done) map._smoothZooming = false
    try { map.setView(curLatLng, curZoom, { animate: false }) } finally { fittingStudy = false }
    if (!done) {
      cameraFrame = requestAnimationFrame(step)
    } else {
      cameraFrame = 0
      map.fire('smoothzoomend')
    }
  }
  cameraFrame = requestAnimationFrame(step)
}

function fitStudy(animate = false) {
  cancelWheelZoom()
  followStudyBounds = true
  const anchor = model.businesses.find(b => b.id === model.targetId) || model.sampling?.center
  const radiusKm = model.sampling?.radius_km
  if (['hex_radius', 'radius_grid'].includes(model.geometry) &&
      Number.isFinite(anchor?.lat) && Number.isFinite(anchor?.lng) &&
      Number.isFinite(radiusKm) && radiusKm > 0) {
    const circleBounds = [0, 90, 180, 270].map(bearing => destination(anchor.lat, anchor.lng, radiusKm, bearing))
    animateToBounds(circleBounds, { padding: [35, 40], maxZoom: 13.5, animate })
    return
  }
  animateToBounds(model.points.map(p => [p.lat, p.lng]), { padding: [35, 40], maxZoom: 13.5, animate })
}

function loadStudy(input, restore = false) {
  const next = normalizeStudy(input)
  nameReview?.savePending()
  model = next
  campaign.playId = null
  campaign.avoidId = null
  campaign.isolateLayer = null
  campaign.research = null
  investigationIds = null
  pointSpacings = cellSpacings(model.points.map(p => {
    const projected = map.project([p.lat, p.lng], 0)
    return [projected.x, projected.y]
  }))
  spacing = Math.min(...pointSpacings.filter(s => s > 0))
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
  if (state.view === 'campaigns') {
    state.business = model.targetId
    const eng = campaignEngine(model)
    if (restore && eng.queries?.[state.query]?.plays?.some(p => p.id === initialParams.get('play'))) campaign.playId = initialParams.get('play')
    const wantedAvoid = restore ? initialParams.get('avoid') : null
    if (wantedAvoid && mergedAvoidList(eng, state.query, campaign.research).some(a => a.id === wantedAvoid)) {
      campaign.avoidId = wantedAvoid
      campaign.playId = null
    }
    const insight = restore && strategyIntelligence(model).insights?.find(i => i.id === initialParams.get('investigation') && i.queryId === state.query)
    if (insight) {
      investigationId = insight.id
      investigationIds = insight.originIds
      campaign.playId = null
      campaign.avoidId = null
    }
  }
  const isHex = model.geometry === 'hex_radius'
  const isCircular = ['radius_grid', 'hex_radius'].includes(model.geometry)
  if (restore) {
    state.rings = initialParams.get('rings') !== '0'
    state.translucent = initialParams.get('translucent') === '1'
    state.contours = initialParams.get('contours') !== '0'
    state.blends = isHex ? (initialParams.get('triangles') === '1' || initialParams.get('blends') === '1') : initialParams.get('blends') !== '0'
    state.showDots = initialParams.has('dots') ? initialParams.get('dots') !== '0' : !isHex
    state.coverage = initialParams.get('coverage') !== '0'
    state.clipCircle = isCircular && initialParams.get('clip') !== '0'
    state.contested = initialParams.get('contested') === '1'
    state.focus = model.businesses.some(b => b.id === initialParams.get('focus')) ? initialParams.get('focus') : null
  } else {
    state.contours = true
    state.blends = !isHex
    state.showDots = !isHex
    state.clipCircle = isCircular
  }
  state.tab = state.view === 'campaigns' ? 'campaigns' : 'factions'
  if (!state.point && (state.region !== 'all' || state.view === 'matchup')) state.tab = 'strategy'
  fieldBrowser.scope = model.businesses.find(b => b.id === state.business)?.shortlisted === false ? 'all' : 'shortlist'
  fieldBrowser.search = ''
  fieldBrowser.page = 0
  leaderSearch = ''
  listingsUi.allRivals = false
  fitStudy()
  render()
  const isBundledSample = input === sample
  void loadCampaignResearch(isBundledSample ? sampleResearch : embedded ? config.campaignResearch ?? null : null)
  if (caps.nameReview) void nameReview?.load(params.get('name_review'), {
    studyURL: params.get('study'),
    fallbackInput: isBundledSample ? sampleNameReview : embedded ? config.nameReview ?? null : null,
  })
}

function contextText() {
  const b = model.businesses.find(b => b.id === state.business)
  const q = model.queries.find(q => q.id === state.query)
  const m = businessMetrics(model, q.id, b.id)
  const p = model.points.find(p => p.id === state.point)
  const play = state.view === 'campaigns' ? campaignEngine(model).queries?.[q.id]?.plays?.find(pl => pl.id === campaign.playId) : null
  if (state.view === 'matchup' || state.region !== 'all') {
    const region = selectedRegion(), metric = region.perQuery[q.id]
    const matchup = state.view === 'matchup' ? strategyMatchup(model, q.id, state.rival, state.region) : null
    return `${model.name}: ${region.label}\nQuery: ${q.name}\nPrimary top 3: ${metric.top3}/${metric.complete}; top 10: ${metric.top10}/${metric.complete}; incomplete: ${metric.unknown}.\n${matchup ? `Compared with: ${matchup.rival.name} (${matchup.rival.address || matchup.rival.id})\n${Object.entries(matchup.counts).map(([key, count]) => `${MATCHUP_STYLES[key].label}: ${count}`).join('\n')}\n` : ''}Exact sampled origins: ${region.originIds.join(', ')}\nObserved: ${model.evidence?.observed_from || 'Not recorded'}\nComplete top-30 evidence only. Absence is censored, not an invented rank. This measures visibility, not demand, revenue, or ranking cause.`
  }
  return `${model.name} - ${model.location}\nSelected business: ${b.name}${b.discovered ? ' (emerging rival)' : ''}\nQuery: ${q.name}\n${m.top3}/${m.scored ?? model.points.length} locations in top 3 (${m.top3Pct.toFixed(1)}%). ${m.found} found; ${m.unknown} incomplete. Average when found: ${m.average?.toFixed(2) ?? 'unknown'}.\n${play ? `Campaign play: ${play.title}; ${play.points} points, mean W ${play.meanW ?? 'n/a'}, leverage ${play.leverage}.\nMembers: ${play.originIds.join(', ')}\n` : ''}${model.evidence?.observed_from ? `Observed: ${model.evidence.observed_from} through ${model.evidence.observed_to}\n` : ''}${p ? `Selected origin: ${p.id} (${p.lat}, ${p.lng})\n${p.observations[q.id].items.map(i => `${i.rank}. ${i.name}`).join('\n')}\n` : ''}Saved evidence, not a live scan. Unsampled areas are unmeasured. Rank does not establish cause or ease of improvement. Coverage depends on this study's sampling footprint.`
}

map = L.map($('#map'), { zoomControl: false, minZoom: 3, maxZoom: 18, zoomSnap: 0, zoomDelta: 0.5, preferCanvas: true, scrollWheelZoom: false, zoomAnimation: false, fadeAnimation: !matchMedia('(prefers-reduced-motion: reduce)').matches })
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
const basemaps = createBasemapSwitcher(map, { announce, basemaps: basemapList, fallbackId: fallbackBasemap, googleSessionPath: config.googleSessionPath, tileStyleBase: config.tileStyleBase, attribution: config.attribution,
  onGoogleUnavailable: !embedded ? undefined : () => {
    if (!$('#basemap-status')) return
    // A failed Google request hides every Google option for this session; the switcher returns to the default background.
    for (const s of [...basemapList]) if (s.google) basemapList.splice(basemapList.indexOf(s), 1)
    root.querySelectorAll('#basemap option').forEach(o => { if (!basemapList.some(s => s.id === o.value)) o.remove() })
    $('#basemap-status').hidden = true
    failedBasemap = null
    $('#basemap').value = state.basemap
  },
  onStatus(status) {
  if (!$('#basemap-status')) return // destroyed while a background was still loading
  $('#basemap-status').hidden = status.phase !== 'error'
  if (status.phase === 'error') {
    failedBasemap = status.id
    $('#basemap-status p').textContent = status.message
  } else if (status.phase === 'ready') {
    failedBasemap = null
  }
}, onChange(id) {
  state.basemap = id
  $('#basemap').value = id
  if (!embedded) try { localStorage.setItem('geogrid-basemap', id) } catch { /* URL still preserves it. */ }
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
$('#retry-basemap').addEventListener('click', () => { if (failedBasemap) void basemaps.set(failedBasemap) })
$('#use-default-basemap').addEventListener('click', () => {
  $('#basemap-status').hidden = true
  failedBasemap = null
  void basemaps.set(fallbackBasemap)
})
$('#dismiss-basemap').addEventListener('click', () => {
  $('#basemap-status').hidden = true
  failedBasemap = null
  $('#basemap').value = state.basemap
})
$('#basemap').addEventListener('change', async e => {
  const choice = e.target.value
  $('#basemap-status').hidden = true
  $('#basemap').disabled = true
  try { await basemaps.set(choice) }
  finally {
    $('#basemap').disabled = false
    $('#basemap').value = $('#basemap-status').hidden ? state.basemap : (failedBasemap || state.basemap)
  }
})
pointsLayer = new RankCanvasLayer({ onSelect: selectPoint, onHoverLeader: setHoveredLeader,
  onSelectLeader: id => {
    if (!focusesTerritory()) return
    if (!id) { clearFocus(); return }
    if (model.businesses.some(b => b.id === id)) focusLeader(id)
  },
  onDoubleClickLeader: id => {
    if (!focusesTerritory() || !id) return
    if (model.businesses.some(b => b.id === id)) focusLeader(id, { fit: true, lock: true })
  } }).addTo(map)
basesLayer = L.layerGroup().addTo(map)
map.on('zoom', updateZoomPresentation)
map.on('movestart', () => {
  if (!fittingStudy) { cancelCameraAnimation(); followStudyBounds = false }
})
$('#map').addEventListener('wheel', cancelCameraAnimation, { passive: true })
$('#map').addEventListener('pointerdown', cancelCameraAnimation, { passive: true })
const resizeObserver = new ResizeObserver(() => {
  map.invalidateSize({ pan: false })
  if (followStudyBounds) fitStudy()
  ensureBasemap()
})
resizeObserver.observe($('#map'))

$('#query').addEventListener('change', e => { state.query = e.target.value; campaign.playId = null; campaign.avoidId = null; investigationIds = null; render() })
$('#elevation-contours').addEventListener('click', () => {
  if (model.geometry !== 'hex_radius' || !['visibility', 'factions', 'campaigns', 'keyword-stuffing'].includes(state.view)) return
  state.contours = !state.contours
  render()
})
$('#triangle-estimates').addEventListener('click', () => {
  if (model.geometry !== 'hex_radius' || !['visibility', 'campaigns', 'keyword-stuffing'].includes(state.view)) return
  state.blends = !state.blends
  render()
})
$('#contested-ground').addEventListener('click', () => {
  const isHex = model.geometry === 'hex_radius'
  if (focusesTerritory()) {
    state.contested = !state.contested
    $('#contested-ground').setAttribute('aria-pressed', state.contested)
    syncURL()
    animateContested()
    return
  }
  if (isHex && (state.view === 'campaigns' || state.view === 'keyword-stuffing')) {
    state.contested = !state.contested
    render()
  }
})
$('#grid-dots').addEventListener('click', () => {
  const isHex = model.geometry === 'hex_radius'
  if (isHex && ['visibility', 'factions', 'campaigns', 'keyword-stuffing'].includes(state.view)) state.showDots = !state.showDots
  else state.coverage = !state.coverage
  render()
})
$('#distance-rings').addEventListener('click', () => { state.rings = !state.rings; render() })
L.DomEvent.disableClickPropagation($('#focus-pill'))
$('#focus-pill').addEventListener('click', e => { if (e.target.closest('#clear-focus')) clearFocus() })
$('#legend').addEventListener('click', e => {
  const chip = e.target.closest('[data-focus-leader]')
  if (chip) { focusLeader(chip.dataset.focusLeader, { fit: true }); return }
  const iso = e.target.closest('[data-campaign-isolate]')
  if (iso && state.view === 'campaigns') {
    const next = iso.dataset.campaignIsolate
    campaign.isolateLayer = campaign.isolateLayer === next ? null : next
    render()
  }
})
const onDocumentKeydown = e => {
  if (e.key === 'Escape' && !e.defaultPrevented) {
    if (nameReview?.closeLightbox?.()) return
    if (state.view === 'keyword-stuffing' && nameReview?.hasOpenInspector?.()) {
      nameReview.clearSelection()
      return
    }
    if (state.view === 'campaigns' && (campaign.playId || campaign.avoidId || campaign.isolateLayer || investigationIds)) {
      clearCampaignFocus()
      return
    }
    if (state.focus && focusesTerritory()) clearFocus()
  }
}
document.addEventListener('keydown', onDocumentKeydown)
$('#sampling-view').addEventListener('change', async e => {
  try {
    const url = new URL(e.target.value, location.href)
    if (url.origin !== location.origin) throw new Error('Study must use this origin')
    const response = await fetch(url, { cache: 'no-store' })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const input = await response.json()
    normalizeStudy(input)
    params.set('study', e.target.value)
    loadStudy(input)
  } catch (error) { announce(`Could not load footprint: ${error.message}`) }
})
$('#fit').addEventListener('click', () => { state.region = 'all'; campaign.playId = null; campaign.avoidId = null; campaign.isolateLayer = null; investigationIds = null; render(); fitStudy(true) })
root.querySelectorAll('[data-view]').forEach(b => b.addEventListener('click', () => setView(b.dataset.view)))
root.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', () => { if (b.dataset.tab === 'campaigns') setView('campaigns'); else { state.tab = b.dataset.tab; render() } }))
$('#side-content').addEventListener('pointerover', e => {
  const leader = e.target.closest('[data-leader]')
  if (leader) setHoveredLeader(leader.dataset.leader)
})
$('#side-content').addEventListener('pointerout', e => {
  const leader = e.target.closest('[data-leader]')
  if (!leader || !leader.isConnected) return
  if (!leader.contains(e.relatedTarget)) setHoveredLeader(null)
})
$('#side-content').addEventListener('click', e => {
  if (state.view === 'keyword-stuffing' && nameReview?.handleRailClick?.(e)) return
  const campaignQuery = e.target.closest('[data-campaign-query]')
  if (campaignQuery) { state.query = campaignQuery.dataset.campaignQuery; campaign.playId = null; campaign.avoidId = null; render(); return }
  const playSummary = e.target.closest('[data-play-summary]')
  if (playSummary) { e.preventDefault(); focusCampaignPlay(playSummary.dataset.playSummary, { fromRail: true }); return }
  const avoidSummary = e.target.closest('[data-avoid-summary]')
  if (avoidSummary) { e.preventDefault(); focusCampaignAvoid(avoidSummary.dataset.avoidSummary, { fromRail: true }); return }
  const focusPlay = e.target.closest('[data-focus-play]')
  if (focusPlay) { focusCampaignPlay(focusPlay.dataset.focusPlay, { fromRail: true }); return }
  const focusAvoid = e.target.closest('[data-focus-avoid]')
  if (focusAvoid) { focusCampaignAvoid(focusAvoid.dataset.focusAvoid, { fromRail: true }); return }
  if (e.target.closest('[data-clear-campaign-focus]')) { clearCampaignFocus(); return }
  if (e.target.closest('[data-copy-vision-brief]')) {
    const brief = visionAgentCampaignBrief(campaignEngine(model), model, state.query)
    navigator.clipboard?.writeText(brief)
      .then(() => announce('Brief copied. Run the vision-brief command, then hand both to your agent.'))
      .catch(() => announce('Clipboard access is unavailable. Use GeoGrid.visionBrief() from your agent.'))
    return
  }
  if (e.target.closest('[data-clear-leader-focus]')) { clearFocus(); return }
  if (e.target.closest('[data-fit-leaders]')) { fitLeaders(); return }
  const leader = e.target.closest('[data-leader]')
  if (leader) {
    const id = leader.dataset.leader
    if (focusesTerritory() && state.focus === id) { clearFocus(); return }
    if (focusesTerritory()) state.focus = id
    hoveredLeaderId = id; pointsLayer?.setHoverLeader(id); selectBusiness(id, { fromRail: true }); setHoveredLeader(id); fitLeaders(id); return
  }
  if (e.target.closest('[data-open-strategy]')) { strategyRoom.open(); return }
  const planBaseline = e.target.closest('[data-campaign-baseline]')
  if (planBaseline) {
    const action = campaignPlanMapAction(campaign.research, planBaseline.dataset.campaignBaseline)
    if (action) {
      state.query = action.queryId
      state.view = 'campaigns'
      state.tab = 'campaigns'
      if (action.enginePlayId) { focusCampaignPlay(action.enginePlayId); return }
      if (action.originIds?.length) { investigationIds = action.originIds; render(); fitOrigins(action.originIds); return }
      render()
    }
    return
  }
  const regionQuery = e.target.closest('[data-region-query]')
  if (regionQuery) { state.query = regionQuery.dataset.regionQuery; render(); return }
  const mapRival = e.target.closest('[data-map-rival]')
  if (mapRival) { inspectRegion({ regionId: state.region, rivalId: mapRival.dataset.mapRival }); return }
  if (e.target.closest('[data-return-region]')) { inspectRegion({ regionId: state.region }); return }
  const evidence = e.target.closest('[data-area-evidence]')
  if (evidence) { selectPoint(evidence.dataset.areaEvidence); return }
  const rival = e.target.closest('[data-campaign-rival]')
  if (rival) { selectBusiness(rival.dataset.campaignRival, { reveal: true }); return }
  const query = e.target.closest('[data-location-query]')
  if (query) { state.query = query.dataset.locationQuery; campaign.playId = null; campaign.avoidId = null; render(); return }
  const allListings = e.target.closest('[data-listing-all]')
  if (allListings) { listingsUi.allListings = allListings.dataset.listingAll === '1'; $('#side-content').innerHTML = renderPoint(); return }
  const allRivals = e.target.closest('[data-rivals-all]')
  if (allRivals) { listingsUi.allRivals = allRivals.dataset.rivalsAll === '1'; $('#side-content').innerHTML = renderCompetitors(); return }
  const b = e.target.closest('[data-business]')
  if (b) selectBusiness(b.dataset.business, b.hasAttribute('data-business-primary') ? { reveal: true } : { fromRail: true })
  const scope = e.target.closest('[data-field-scope]')
  if (scope) { fieldBrowser.scope = scope.dataset.fieldScope; fieldBrowser.page = 0; $('#side-content').innerHTML = renderBusinesses() }
  const page = e.target.closest('[data-field-page]')
  if (page) { fieldBrowser.page += Number(page.dataset.fieldPage); $('#side-content').innerHTML = renderBusinesses() }
})
$('#side-content').addEventListener('input', e => {
  if (state.view === 'keyword-stuffing' && nameReview?.handleRailInput?.(e)) return
  if (e.target.id === 'leader-search') {
    const position = e.target.selectionStart
    leaderSearch = e.target.value
    $('#side-content').innerHTML = renderLeaders()
    const input = $('#leader-search')
    if (input) { input.focus(); input.setSelectionRange(position, position) }
    return
  }
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
  if (state.view === 'campaigns') {
    const topPlayId = $('#inspect-near').dataset.topPlayId
    if (topPlayId) focusCampaignPlay(topPlayId)
    else { state.tab = 'campaigns'; render() }
    return
  }
  if (state.view === 'keyword-stuffing' && nameReview) {
    if (nameReview.hasOpenInspector()) nameReview.clearSelection()
    else {
      const first = nameReview.getFlaggedCases()[0]
      if (first) nameReview.selectCase(first.id)
    }
    return
  }
  if (state.view === 'visibility') { setView('campaigns'); return }
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
strategyRoom = !caps.strategyRoom ? { open() {}, close() {}, toggle() {}, sync() {}, refresh() {} } : createStrategyRoom({
  mount: $('#strategy-host'),
  startDocked: initialParams.get('strategyLayout') === 'split',
  getModel: () => model,
  getResearch: () => campaign.research,
  getQueryId: () => state.query,
  onLayout({ open, docked, forceDock }) {
    workbench.classList.toggle('strategy-docked', docked)
    if (docked) workbench.classList.remove('evidence-open')
    const ws = $('.workspace')
    if (ws) ws.scrollLeft = 0
    $('#evidence-toggle').setAttribute('aria-expanded', workbench.classList.contains('evidence-open'))
    $('#open-strategy').setAttribute('aria-expanded', open)
    $('#open-strategy').textContent = open ? 'Hide strategy' : 'Strategy room'
    if (open) params.set('strategy', '1'); else params.delete('strategy')
    if (forceDock) params.set('strategyLayout', 'split'); else params.delete('strategyLayout')
    if (docked) queueMicrotask(() => resizeStrategy(split))
    queueMicrotask(() => { if (!destroyed && map) map.invalidateSize({ pan: false }) })
    syncURL()
  },
  onInspectRegion: inspectRegion,
  onMatchup: inspectRegion,
  onCampaign({ campaignId, queryId, originIds, insight }) {
    if (campaignId === 'local-vs-regional' && insight?.evidence?.nearLeader?.id) {
      inspectRegion({ regionId: 'all', queryId, rivalId: insight.evidence.nearLeader.id })
      return
    }
    state.query = queryId
    state.view = 'campaigns'
    state.tab = 'campaigns'
    if (originIds?.length) { investigationId = campaignId; investigationIds = originIds; render(); fitOrigins(originIds) }
    else render()
  },
  onAvoid({ avoidId, queryNames = [] }) {
    state.view = 'campaigns'
    state.tab = 'campaigns'
    const currentName = model.queries.find(q => q.id === state.query)?.name
    if (queryNames.length && (!currentName || !queryNames.includes(currentName))) {
      const matched = model.queries.find(q => queryNames.includes(q.name))
      if (matched) state.query = matched.id
    }
    campaign.avoidId = null
    const fullId = `agent:${avoidId}`
    const matchedAvoid = mergedAvoidList(campaignEngine(model), state.query, campaign.research).some(a => a.id === fullId)
    if (matchedAvoid) focusCampaignAvoid(fullId)
    else render()
  },
})
nameReview = !caps.nameReview ? null : createNameReview({
  getModel: () => model,
  getQuery: () => state.query,
  inspectorHost: $('#nr-inspector'),
  lightboxHost: root,
  onClose: () => setView('factions'),
  onOpen: () => strategyRoom.close(),
  onMessage: announce,
  onSelectQuery(qId) {
    if (model.queries.some(q => q.id === qId) && state.query !== qId) {
      state.query = qId
      render()
    }
  },
  onFilterChange({ preserveSearchFocus = false, cursor = null } = {}) {
    render()
    if (preserveSearchFocus) {
      const input = $('#nr-search')
      if (input) { input.focus(); if (cursor !== null) input.setSelectionRange(cursor, cursor) }
    }
  },
  onSelectCase(selectedCase, terr, { fromRail = false } = {}) {
    render()
    if (selectedCase && !fromRail) {
      revealInRail(`[data-nr-case="${attrEscape(selectedCase.id)}"]`)
    }
    if (selectedCase && terr) {
      const qTerr = terr.byQuery?.[state.query]
      const anchor = model.businesses.find(b => b.id === model.targetId)
      const ptIds = new Set(qTerr?.topThreeIds || [])
      const coords = model.points.filter(p => ptIds.has(p.id)).map(p => [p.lat, p.lng])
      if (Number.isFinite(anchor?.lat) && Number.isFinite(anchor?.lng)) coords.push([anchor.lat, anchor.lng])
      if (coords.length >= 2) {
        cancelWheelZoom()
        followStudyBounds = false
        setTimeout(() => { if (!destroyed) animateToBounds(coords, { padding: [40, 40], maxZoom: 13 }) }, 180)
      }
    }
  },
})
root.addEventListener('click', event => { if (caps.nameReview && event.target.closest('[data-open-name-review]')) setView('keyword-stuffing') })
$('#open-strategy').addEventListener('click', () => { if (state.view === 'keyword-stuffing') setView('visibility'); strategyRoom.toggle() })
$('#evidence-toggle').addEventListener('click', () => {
  workbench.classList.toggle('evidence-open')
  $('#evidence-toggle').setAttribute('aria-expanded', workbench.classList.contains('evidence-open'))
})
const divider = $('#strategy-divider')
let split = 50
if (!embedded) try { split = Math.max(35, Math.min(60, Number(localStorage.getItem('geogrid-strategy-width')) || 50)) } catch { /* Use even split. */ }
function resizeStrategy(value) {
  const width = workbench.clientWidth
  const minPanel = width >= 1200 ? 480 : 400
  const minMap = width >= 1200 ? 560 : 400
  split = Math.max(Math.max(35, minPanel / width * 100), Math.min(Math.min(60, (width - minMap - 8) / width * 100), value))
  workbench.style.setProperty('--strategy-width', `${split}%`)
  divider.setAttribute('aria-valuenow', Math.round(split))
  if (!embedded) try { localStorage.setItem('geogrid-strategy-width', split) } catch { /* Session still resizes. */ }
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
const onWindowResize = () => { if (workbench.classList.contains('strategy-docked')) resizeStrategy(split) }
window.addEventListener('resize', onWindowResize)
const api = {
  loadStudy, selectBusiness, selectPoint,
  setQuery(id) { if (!model.queries.some(q => q.id === id)) throw new Error('Unknown query'); state.query = id; campaign.playId = null; campaign.avoidId = null; investigationIds = null; render() },
  setView, focusCampaignPlay, focusCampaignAvoid, clearCampaignFocus,
  campaignAnalysis: () => campaignEngine(model),
  territoryAnalysis: () => territoryIntelligence(model, state.query),
  strategyAnalysis: () => strategyIntelligence(model),
  leaderAnalysis: () => localLeaders(model, state.query, state.leaderMinimum),
  visionBrief: () => visionAgentCampaignBrief(campaignEngine(model), model, state.query),
  fitLeaders,
  fitStudy,
  getCenter: () => { const c = map.getCenter(); return { lat: c.lat, lng: c.lng } },
  inspectRegion,
  openStrategy: () => strategyRoom.open(),
  openNameReview: () => setView('keyword-stuffing'),
  selectNameReviewCase: id => nameReview?.selectCase?.(id),
  nameReviewState: () => nameReview?.getState?.(),
  getState: () => ({ ...state, playId: campaign.playId, avoidId: campaign.avoidId, study: model.name, zoom: map.getZoom() }),
  renderStats: () => pointsLayer.stats,
  pointPosition: id => pointsLayer.pointPosition(id),
  context: contextText,
}
if (!embedded) window.GeoGrid = api
// Hide whole panels for capabilities that are off (the flagged code paths also no-op defensively).
const hide = (selector, off) => { if (off) root.querySelectorAll(selector).forEach(el => { el.hidden = true; el.dataset.capabilityOff = '1' }) }
hide('[data-view="factions"]', !caps.perPointListings)
hide('[data-view="keyword-stuffing"]', !caps.nameReview)
hide('#open-strategy', !caps.strategyRoom)
hide('#open-study', embedded)
hide('#study-file', embedded)
hide('#copy-brief', embedded)
loadStudy(config.study ?? sample, !embedded); void (async () => {
if (!embedded) {
// A private local pointer can select the working study without bundling client
// evidence in the open-source build. Explicit links always retain their study.
if (import.meta.env.DEV && ['http:', 'https:'].includes(location.protocol) && initialParams.get('starter') !== '1') {
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
    const response = await fetch(url, { cache: 'no-store' })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    loadStudy(await response.json(), true)
  } catch (error) { announce(`Could not load requested study (${error.message}). Showing the bundled sample.`) }
}
}
// A direct link to business-title evidence has no visible map viewport yet.
// Start map requests when the user returns to a map mode, not against 0×0 bounds.
mapSourcesReady = true
ensureBasemap()
// Development screenshots can pin the camera after the study fit: ?at=lat,lng,zoom
const pinnedCamera = import.meta.env.DEV ? (initialParams.get('at') || '').split(',').map(Number) : []
if (pinnedCamera.length === 3 && pinnedCamera.every(Number.isFinite)) {
  // Pin only after the study has drawn and its fit has settled, and again whenever the tab
  // becomes visible, so a slow study load or a background tab cannot undo the pin.
  const pin = () => {
    if (destroyed || !map) return
    cancelCameraAnimation()
    followStudyBounds = false
    map.setView([pinnedCamera[0], pinnedCamera[1]], pinnedCamera[2], { animate: false })
    setTimeout(() => { if (!destroyed) pointsLayer?.queueDraw?.() }, 300)
  }
  const waitForStudy = (tries = 0) => {
    if (destroyed) return
    if (!pointsLayer?.stats && tries < 60) return setTimeout(() => waitForStudy(tries + 1), 250)
    setTimeout(pin, 1200)
  }
  waitForStudy()
  onVisibilityChange = () => { if (!destroyed && !document.hidden) setTimeout(pin, 400) }
  document.addEventListener('visibilitychange', onVisibilityChange)
}
// Development coverage probe: ?probe=coverage hides the basemap tiles over a flat #ff00ff
// background, so a screenshot counts exactly which map pixels the overlays cover.
if (import.meta.env.DEV && initialParams.get('probe') === 'coverage' && map) {
  map.getPane('tilePane').style.visibility = 'hidden'
  map.getContainer().style.background = '#ff00ff'
}
if (initialParams.get('strategy') === '1' && caps.strategyRoom) strategyRoom.open(); })()
function destroy() {
  if (destroyed) return
  destroyed = true
  cancelCameraAnimation()
  cancelAnimationFrame(tauFrame)
  tauFrame = 0
  if (cancelWheelZoom.destroy) cancelWheelZoom.destroy()
  else cancelWheelZoom()
  resizeObserver.disconnect()
  window.removeEventListener('resize', onWindowResize)
  document.removeEventListener('keydown', onDocumentKeydown)
  if (onVisibilityChange) {
    document.removeEventListener('visibilitychange', onVisibilityChange)
    onVisibilityChange = null
  }
  clearTimeout(announce.timer)
  clearTimeout(inspectorTimer)
  try { map.remove() } catch { /* Already detached. */ }
  root.replaceChildren()
  root.classList.remove('ggv-root')
  if (!embedded && window.GeoGrid === api) delete window.GeoGrid
}
return { ...api, destroy }
}
