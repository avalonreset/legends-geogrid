// Side panels for the full rankings of a study: one location's listings, and who shows up across the grid.
// Pure HTML builders. Names and categories come from the model and are always escaped. Competitor keys are
// opaque strings: they are only echoed into data attributes, never parsed or linked.
import { pointListing, competitorStats, LISTING_WINDOW } from './study-model.js'

const escape = text => String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
const percent = value => `${(value * 100).toFixed(value > 0 && value < 0.1 ? 1 : 0)}%`
export const RIVAL_PAGE = 25

function detailLine(business) {
  const parts = []
  if (business?.category) parts.push(escape(business.category))
  if (typeof business?.rating === 'number' && Number.isFinite(business.rating)) {
    const reviews = Number.isFinite(business.reviews) ? ` (${Number(business.reviews).toLocaleString('en-US')})` : ''
    parts.push(`${business.rating.toFixed(1)} rating${reviews}`)
  }
  return parts.length ? `<span class="business-address">${parts.join(' · ')}</span>` : ''
}

function listingRow(item, business, state, model) {
  const target = item.id === model.targetId
  return `<button class="business-row listing-row ${target ? 'primary' : ''} ${item.id === state.business ? 'selected' : ''}" data-business="${escape(item.id)}" aria-pressed="${item.id === state.business}" data-listing-rank="${item.rank}">
    <span class="leaderboard-position listing-rank" aria-label="Rank ${item.rank}">${item.rank}</span>
    <span class="business-info"><span class="business-name">${escape(business?.name || item.name || 'Unnamed profile')}</span>${detailLine(business || item)}</span>
    ${target ? '<span class="business-score"><em>PRIMARY</em></span>' : ''}
  </button>`
}

// state: { business, query, point } plus ui: { allListings, allRivals }
export function pointPanelHTML(model, state, ui) {
  const query = model.queries.find(q => q.id === state.query)
  const listing = state.point ? pointListing(model, state.point, state.query) : null
  if (!listing) {
    return `<div class="side-intro"><div class="eyebrow">LOCATION RANKINGS</div><h2>Select a location</h2>
      <p>Choose a point on the map to see who ranks there, with the top ${LISTING_WINDOW} listed first.</p></div>`
  }
  const directory = new Map(model.businesses.map(b => [b.id, b]))
  const expanded = ui.allListings === true && listing.extra.length > 0
  const shown = expanded ? listing.items : listing.top
  const rows = shown.map(item => listingRow(item, directory.get(item.id), state, model))
  const t = listing.target
  // Where the primary business ranks, including positions beyond the default window.
  const beyond = t.rank && t.rank > LISTING_WINDOW
  const targetName = escape(model.name || 'Your business')
  const targetLine = t.rank
    ? `${targetName} ranks <strong data-target-rank>${t.rank}</strong> here${beyond ? ` (beyond the top ${LISTING_WINDOW})` : ''}.`
    : `${targetName}: ${escape(t.label)}.`
  const pinned = !expanded && beyond && !listing.items.slice(0, listing.top.length).some(i => i.id === model.targetId)
    ? `<p class="listing-gap" aria-hidden="true">· · ·</p>
       <button class="business-row listing-row primary ${model.targetId === state.business ? 'selected' : ''}" data-business="${escape(model.targetId)}" data-listing-rank="${t.rank}" aria-pressed="${model.targetId === state.business}">
         <span class="leaderboard-position listing-rank">${t.rank}</span>
         <span class="business-info"><span class="business-name">${escape(directory.get(model.targetId)?.name || model.name)}</span></span>
         <span class="business-score"><em>PRIMARY</em></span></button>`
    : ''
  const count = listing.captured
  const expander = listing.extra.length
    ? `<div class="listing-expander"><button class="text-button" data-listing-all="${expanded ? '0' : '1'}" aria-expanded="${expanded}">${expanded ? `Show top ${LISTING_WINDOW}` : `Show all ${count}`}</button></div>`
    : ''
  const empty = count === 0 ? '<p class="list-caption">No results were captured for this location and query.</p>' : ''
  return `<div class="side-intro"><div class="eyebrow">LOCATION RANKINGS</div><h2>${escape(listing.point.id)}</h2>
    <p>${escape(query?.name || '')} · ${count} ${count === 1 ? 'listing' : 'listings'} captured${listing.extra.length && !expanded ? `, top ${LISTING_WINDOW} shown` : ''}</p>
    <p class="listing-target" data-target-line>${targetLine}</p></div>
    <div class="business-list listing-list" data-listing-count="${shown.length}">${rows.join('')}${pinned}${empty}</div>${expander}
    <p class="list-caption">Scores on this map stay anchored to the top ${model.scoreWindow || LISTING_WINDOW}. Deeper positions are shown for context.</p>`
}

export function competitorPanelHTML(model, state, ui) {
  const stats = competitorStats(model, state.query)
  const query = model.queries.find(q => q.id === state.query)
  const expanded = ui.allRivals === true
  const rows = expanded ? stats.rows : stats.rows.slice(0, RIVAL_PAGE)
  const measured = stats.measured
  const rowHTML = row => {
    const b = row.business
    return `<button class="business-row rival-row ${b.id === state.business ? 'selected' : ''}" data-business="${escape(b.id)}" aria-pressed="${b.id === state.business}" data-appearances="${row.appearances}">
      <span class="business-info"><span class="business-name">${escape(b.name)}</span>${detailLine(b)}
        <span class="rival-meta">${percent(row.share)} of points · avg rank ${row.averageRank.toFixed(1)}</span></span>
      <span class="business-score">${row.appearances}<small>/${measured}</small></span>
    </button>`
  }
  const you = stats.target
  const youHTML = you
    ? `<button class="business-row rival-row primary ${model.targetId === state.business ? 'selected' : ''}" data-business="${escape(model.targetId)}" aria-pressed="${model.targetId === state.business}" data-appearances="${you.appearances}">
        <span class="business-info"><span class="business-name">${escape(model.businesses.find(b => b.id === model.targetId)?.name || model.name)}</span>
        <span class="rival-meta">${percent(you.share)} of points · avg rank ${you.averageRank.toFixed(1)}</span></span>
        <span class="business-score">${you.appearances}<small>/${measured}</small><em>PRIMARY</em></span></button>`
    : ''
  const expander = stats.rows.length > RIVAL_PAGE
    ? `<div class="listing-expander"><button class="text-button" data-rivals-all="${expanded ? '0' : '1'}" aria-expanded="${expanded}">${expanded ? `Show top ${RIVAL_PAGE}` : `Show all ${stats.rows.length}`}</button></div>`
    : ''
  return `<div class="side-intro"><div class="eyebrow">COMPETITORS ACROSS THE GRID</div><h2>${stats.rows.length} other ${stats.rows.length === 1 ? 'business' : 'businesses'} appear</h2>
    <p>${escape(query?.name || '')} · ${measured} measured ${measured === 1 ? 'location' : 'locations'}, most frequent first. Select one to highlight where it ranks on the map.</p></div>
    <div class="business-list competitor-list" data-competitor-count="${rows.length}">${youHTML}${rows.map(rowHTML).join('')}${stats.rows.length ? '' : '<p class="list-caption">No other businesses were captured.</p>'}</div>${expander}
    <p class="list-caption">Appearances count every captured position, including beyond the top ${LISTING_WINDOW}. Average rank is taken where the business appears.</p>`
}
