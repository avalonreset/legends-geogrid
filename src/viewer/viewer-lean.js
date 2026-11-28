import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { RANK_COLORS, rankFillOpacity } from '../study-model.js'
import { cellSpacings, destination } from '../map-geometry.js'
import { distanceLabel, distanceRings } from '../distance-units.js'
import { installWheelZoom } from '../wheel-zoom.js'
import { BASEMAPS, createBasemapSwitcher } from '../basemap-switcher.js'
import { RankCanvasLayer } from '../rank-canvas.js'
import { normalizeLeanModel, formatShare, formatRank, formatSigned, formatDate, escapeHtml } from './lean-model.js'
import './viewer-lean.css'

const esc = escapeHtml
const SCORE_CARDS = [
  { key: 'foundShare', label: 'Found', kind: 'share', hint: 'Share of grid points where the business appears', better: 1 },
  { key: 'solv', label: 'SoLV', kind: 'share', hint: 'Share of local voice', better: 1 },
  { key: 'visibleShare', label: 'Top 3', kind: 'share', hint: 'Share of grid points in the top 3', better: 1 },
  { key: 'arp', label: 'ARP', kind: 'rank', hint: 'Average rank where found', better: -1 },
  { key: 'atrp', label: 'ATRP', kind: 'rank', hint: 'Average rank across all grid points', better: -1 },
  { key: 'centerRank', label: 'Center', kind: 'rank', hint: 'Rank at the center point', better: -1 },
]
const fmt = (kind, v) => (kind === 'share' ? formatShare(v) : formatRank(v))

function pointCells(map, model) {
  const projected = model.points.map(p => {
    const xy = map.project([p.lat, p.lng], 0)
    return [xy.x, xy.y]
  })
  const spacings = cellSpacings(projected)
  let spacing = Math.min(...spacings.filter(s => s > 0))
  if (!Number.isFinite(spacing)) spacing = .001
  const cells = model.points.map((p, i) => {
    const ranked = p.rank !== null && p.rank <= 30
    const where = p.hex ? `Hex ${p.hex.unitQ}, ${p.hex.unitR} · first rung ${p.hex.firstRungMiles} mi` : p.row !== null && p.col !== null ? `Row ${p.row}, column ${p.col}` : `Point ${i + 1}`
    return {
      id: `p${i}`, lat: p.lat, lng: p.lng, x: projected[i][0], y: projected[i][1], spacing: spacings[i] || spacing,
      leaderId: null,
      color: ranked ? RANK_COLORS[p.rank - 1] : '#10080b',
      opacity: ranked ? rankFillOpacity(p.rank) : 1,
      kind: ranked ? 'ranked' : 'nr',
      active: false, muted: false, coverage: false, dominant: p.rank === 1,
      label: `${esc(where)} · ${esc(p.label)}`, plain: `${where} · ${p.label}`,
    }
  })
  return { cells, spacing }
}

function legendHTML() {
  const swatch = (rank, text) => `<span><i style="background:${RANK_COLORS[rank - 1]}"></i>${text}</span>`
  return `${swatch(1, '1 to 3')}${swatch(5, '4 to 10')}${swatch(10, '11 to 20')}${swatch(20, '21 to 30')}<span><i class="ggl-nr"></i>Not found</span>`
}

function zoneTable(title, zones, caption) {
  if (!zones.length) return ''
  const rows = zones.map(z => `<tr><th scope="row">${esc(z.label)}</th><td>${z.points}</td><td>${formatShare(z.foundShare)}</td><td>${formatRank(z.avgRank)}</td></tr>`).join('')
  return `<section class="ggl-section"><h3>${esc(title)}</h3><table class="ggl-table"><caption>${esc(caption)}</caption>
    <thead><tr><th scope="col">Zone</th><th scope="col">Points</th><th scope="col">Found</th><th scope="col">Avg rank</th></tr></thead><tbody>${rows}</tbody></table></section>`
}

function competitorRows(rows, withAverage = true) {
  return rows.map(c => `<tr><th scope="row">${esc(c.name)}</th><td>${formatShare(c.presenceShare)}</td><td>${formatShare(c.top3Share)}</td><td>${formatShare(c.outrankShare)}</td>${withAverage ? `<td>${formatRank(c.avgRank)}</td>` : ''}</tr>`).join('')
}

function deltaHTML(delta) {
  if (!delta) return ''
  const cells = SCORE_CARDS.map(card => {
    const v = delta.scores[card.key]
    const direction = !Number.isFinite(v) || v === 0 ? 'flat' : (v * card.better > 0 ? 'good' : 'bad')
    return `<div class="ggl-delta ggl-${direction}"><span>${card.label}</span><b>${formatSigned(v, card.kind)}</b></div>`
  }).join('')
  const counts = [['improved', delta.improved], ['declined', delta.declined], ['unchanged', delta.unchanged]]
    .filter(([, n]) => Number.isFinite(n)).map(([name, n]) => `${n} ${name}`).join(' · ')
  const since = formatDate(delta.previousCreatedAt)
  return `<section class="ggl-section"><h3>Change since last scan</h3>${since ? `<p class="ggl-note">Compared with ${esc(since)}</p>` : ''}
    <div class="ggl-delta-grid">${cells}</div>${counts ? `<p class="ggl-note">Grid points: ${esc(counts)}</p>` : ''}</section>`
}

export function mountLeanViewer(el, input, options = {}) {
  const model = normalizeLeanModel(input)
  const units = options.units === 'km' ? 'km' : 'mi'
  const basemapList = options.basemaps.map(b => ({ ...b }))
  const fallbackId = options.fallbackBasemap
  const preferredId = basemapList.some(b => b.id === options.defaultBasemap) ? options.defaultBasemap : fallbackId
  const scan = model.scan
  const radiusKm = scan.radiusM ? scan.radiusM / 1000 : null
  const meta = [scan.keyword && `“${esc(scan.keyword)}”`,
    scan.gridSize && `${scan.gridSize} × ${scan.gridSize} grid`,
    radiusKm && `${esc(distanceLabel(radiusKm, units))} radius`,
    formatDate(scan.createdAt) && esc(formatDate(scan.createdAt)),
    scan.device && esc(scan.device)].filter(Boolean).join(' · ')

  el.classList.add('ggv-root')
  el.innerHTML = `<div class="ggl">
    <div class="ggl-head"><div><h2>${esc(model.business.name)}</h2><p>${meta}</p></div>
      <div class="ggl-actions"><select class="ggl-basemap" aria-label="Map source">${basemapList.map(b => `<option value="${esc(b.id)}">${esc(b.name)}</option>`).join('')}</select>
      <button type="button" class="ggl-fit" title="Show every sampled location">Fit grid</button></div></div>
    <div class="ggl-body">
      <div class="ggl-mapwrap"><div class="ggl-map"></div><div class="ggl-legend" aria-label="Rank colors">${legendHTML()}</div>
        <div class="ggl-status" role="status" aria-live="polite"></div></div>
      <aside class="ggl-side">
        <section class="ggl-section"><h3>Scores</h3><div class="ggl-cards">${SCORE_CARDS.map(c => `<div class="ggl-card" title="${esc(c.hint)}"><span>${c.label}</span><b>${fmt(c.kind, model.scores[c.key])}</b></div>`).join('')}</div></section>
        ${deltaHTML(model.delta)}
        ${zoneTable('Distance rings', model.zones.rings, 'Results by distance from the business')}
        ${zoneTable('Quadrants', model.zones.quadrants, 'Results by direction from the business')}
        ${model.competitors.length ? `<section class="ggl-section"><h3>Competitors</h3><table class="ggl-table ggl-competitors"><caption>Businesses that appear across the grid</caption>
          <thead><tr><th scope="col">Business</th><th scope="col">Presence</th><th scope="col">Top 3</th><th scope="col">Outranks you</th><th scope="col">Avg rank</th></tr></thead><tbody>${competitorRows(model.competitors)}</tbody></table></section>` : ''}
        ${model.zoneCompetitors.length ? `<section class="ggl-section"><h3>Competitors by zone</h3><label class="ggl-zone-pick">Zone <select class="ggl-zone" aria-label="Zone"></select></label>
          <table class="ggl-table ggl-zone-table"><caption>Leading businesses in the selected zone</caption>
          <thead><tr><th scope="col">Business</th><th scope="col">Presence</th><th scope="col">Top 3</th><th scope="col">Outranks you</th></tr></thead><tbody></tbody></table></section>` : ''}
      </aside></div></div>`
  const $ = selector => el.querySelector(selector)

  const map = L.map($('.ggl-map'), { zoomControl: false, minZoom: 3, maxZoom: 18, zoomSnap: 0, zoomDelta: 0.5, preferCanvas: true,
    scrollWheelZoom: false, zoomAnimation: false, fadeAnimation: !matchMedia('(prefers-reduced-motion: reduce)').matches })
  const cancelWheelZoom = installWheelZoom(map)
  map.createPane('referencePane').style.zIndex = '605'
  map.createPane('rankingPane').style.zIndex = '450'
  map.createPane('referenceLabelPane').style.zIndex = '610'
  for (const name of ['rankingPane', 'referencePane', 'referenceLabelPane']) map.getPane(name).style.pointerEvents = 'none'
  L.control.zoom({ position: 'bottomleft' }).addTo(map)

  const status = $('.ggl-status')
  let destroyed = false
  let announceTimer = 0
  const announce = message => {
    if (destroyed) return
    status.textContent = message
    clearTimeout(announceTimer)
    announceTimer = setTimeout(() => { if (destroyed) return; status.textContent = '' }, 4000)
  }

  const ranges = L.layerGroup().addTo(map)
  const { lat, lng } = model.business
  if (radiusKm) {
    L.circle([lat, lng], { pane: 'referencePane', radius: scan.radiusM, color: '#969696', weight: 1, opacity: .65, dashArray: '4 6', fill: false, interactive: false }).addTo(ranges)
    for (const { km, label } of distanceRings(units, radiusKm)) {
      if (km > radiusKm + .00001) continue
      L.circle([lat, lng], { pane: 'referencePane', radius: km * 1000, color: '#cccccc', weight: 1, opacity: .4, fill: false, interactive: false }).addTo(ranges)
      L.marker(destination(lat, lng, km, 45), { pane: 'referenceLabelPane', interactive: false, keyboard: false, ringKm: km,
        icon: L.divIcon({ className: 'distance-label', html: label, iconSize: [38, 18], iconAnchor: [19, 9] }) }).addTo(ranges)
    }
  }
  L.circleMarker([lat, lng], { pane: 'referenceLabelPane', radius: 6, color: '#ffffff', weight: 2, fillColor: '#ff4d4d', fillOpacity: 1, interactive: false }).addTo(map)

  const { cells, spacing } = pointCells(map, model)
  const layer = new RankCanvasLayer({ onSelect: id => {
    const hit = cells.find(c => c.id === id)
    for (const c of cells) c.active = c.id === id
    layer.setData(cells, [], spacing, false, null, [], false)
    if (hit) announce(hit.plain)
  } }).addTo(map)
  layer.setData(cells, [], spacing, false, null, [], false)

  const updateRingLabels = () => {
    const zoom = map.getZoom()
    ranges.eachLayer(item => {
      if (!item.options.ringKm) return
      const pixels = map.project([lat, lng], zoom).distanceTo(map.project(item.getLatLng(), zoom))
      const icon = item.getElement()
      if (icon) icon.style.display = pixels >= 38 ? '' : 'none'
    })
  }
  map.on('zoom', updateRingLabels)
  const fit = animate => {
    map.fitBounds(L.latLngBounds(model.points.map(p => [p.lat, p.lng])), { padding: [35, 40], maxZoom: 13.5, animate })
    updateRingLabels()
  }
  fit(false)
  $('.ggl-fit').addEventListener('click', () => fit(false))

  const select = $('.ggl-basemap')
  const switcher = createBasemapSwitcher(map, {
    announce, basemaps: basemapList, fallbackId, googleSessionPath: options.googleSessionPath, attribution: options.attribution,
    onChange: id => { if (destroyed) return; select.value = id },
    // Hosts and tests can read the background state from data-basemap-state (loading, ready or error).
    onStatus: ({ phase }) => { if (destroyed) return; const node = $('.ggl-map'); if (node) node.dataset.basemapState = phase },
    onGoogleUnavailable: () => {
      if (destroyed) return
      // A failed Google request hides every Google option for this session; the switcher returns to the default background.
      for (let i = basemapList.length - 1; i >= 0; i--) if (basemapList[i].google) basemapList.splice(i, 1)
      select.querySelectorAll('option').forEach(o => { if (!basemapList.some(b => b.id === o.value)) o.remove() })
      select.value = fallbackId
    },
  })
  select.value = preferredId
  select.addEventListener('change', () => { void switcher.set(select.value).catch(() => { select.value = fallbackId; void switcher.set(fallbackId).catch(() => {}) }) })
  void switcher.set(preferredId).catch(() => { select.value = fallbackId; void switcher.set(fallbackId).catch(() => {}) })

  const zoneSelect = $('.ggl-zone')
  if (zoneSelect) {
    const labels = new Map([...model.zones.rings, ...model.zones.quadrants].map(z => [z.id, z.label]))
    zoneSelect.innerHTML = model.zoneCompetitors.map((z, i) => `<option value="${i}">${esc(labels.get(z.zoneId) || z.zoneId)}</option>`).join('')
    const body = $('.ggl-zone-table tbody')
    const show = () => { body.innerHTML = competitorRows(model.zoneCompetitors[Number(zoneSelect.value)].top, false) }
    zoneSelect.addEventListener('change', show)
    show()
  }

  const resizeObserver = new ResizeObserver(() => map.invalidateSize({ pan: false }))
  resizeObserver.observe($('.ggl-map'))

  return {
    destroy() {
      if (destroyed) return
      destroyed = true
      clearTimeout(announceTimer)
      resizeObserver.disconnect()
      cancelWheelZoom?.()
      // A basemap that never finished starting (for example no WebGL) can leave a detached node; teardown must still finish.
      try { map.remove() } catch { /* Already detached. */ }
      el.replaceChildren()
      el.classList.remove('ggv-root')
    },
  }
}

export { BASEMAPS }
