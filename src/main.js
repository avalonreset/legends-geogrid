import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import proof17Run from './data/home-slice-17x17.json'
import proofRun from './data/home-slice-5x5.json'
import './styles.css'

const austinCenter = { lat: 30.249711, lng: -97.749132 }

const queueRates = {
  standard: 0.0006,
  priority: 0.0012,
  live: 0.002,
}

let leafletMap = null

const RankCanvasLayer = L.Layer.extend({
  initialize(points, selected, options = {}) {
    this.points = points
    this.selected = selected
    this.view = options.view || 'pins'
    this.onSelect = options.onSelect
  },

  onAdd(map) {
    this._map = map
    this._canvas = L.DomUtil.create('canvas', 'rank-canvas-layer')
    this._context = this._canvas.getContext('2d')
    map.getPanes().overlayPane.appendChild(this._canvas)
    map.on('moveend zoomend resize viewreset', this._reset, this)
    map.on('click', this._handleClick, this)
    this._reset()
  },

  onRemove(map) {
    map.off('moveend zoomend resize viewreset', this._reset, this)
    map.off('click', this._handleClick, this)
    L.DomUtil.remove(this._canvas)
  },

  _reset() {
    const topLeft = this._map.containerPointToLayerPoint([0, 0])
    const size = this._map.getSize()
    const ratio = window.devicePixelRatio || 1
    this._canvas.width = Math.round(size.x * ratio)
    this._canvas.height = Math.round(size.y * ratio)
    this._canvas.style.width = `${size.x}px`
    this._canvas.style.height = `${size.y}px`
    L.DomUtil.setPosition(this._canvas, topLeft)
    this._context.setTransform(ratio, 0, 0, ratio, 0, 0)
    this._draw(topLeft, size)
  },

  _draw(topLeft, size) {
    const ctx = this._context
    ctx.clearRect(0, 0, size.x, size.y)

    if (this.view === 'heat') {
      for (const point of this.points) {
        const layerPoint = this._map.latLngToLayerPoint([point.lat, point.lng])
        const x = layerPoint.x - topLeft.x
        const y = layerPoint.y - topLeft.y
        const radius = point.rank === null ? 34 : Math.max(20, 46 - point.rank * 1.5)
        const gradient = ctx.createRadialGradient(x, y, 1, x, y, radius)
        gradient.addColorStop(0, `${rankColor(point.rank)}cc`)
        gradient.addColorStop(1, `${rankColor(point.rank)}00`)
        ctx.fillStyle = gradient
        ctx.beginPath()
        ctx.arc(x, y, radius, 0, Math.PI * 2)
        ctx.fill()
      }
      return
    }

    for (const [index, point] of this.points.entries()) {
      const layerPoint = this._map.latLngToLayerPoint([point.lat, point.lng])
      const x = layerPoint.x - topLeft.x
      const y = layerPoint.y - topLeft.y
      const selected = point === this.selected
      const radius = selected ? 19 : 16
      ctx.beginPath()
      ctx.fillStyle = rankColor(point.rank)
      ctx.arc(x, y, radius, 0, Math.PI * 2)
      ctx.fill()
      ctx.lineWidth = selected ? 4 : 2
      ctx.strokeStyle = selected ? 'rgba(45, 212, 191, 0.88)' : 'rgba(255, 255, 255, 0.82)'
      ctx.stroke()

      if (selected) {
        ctx.beginPath()
        ctx.arc(x, y, radius + 7, 0, Math.PI * 2)
        ctx.lineWidth = 2
        ctx.strokeStyle = 'rgba(45, 212, 191, 0.38)'
        ctx.stroke()
      }

      ctx.fillStyle = point.rank !== null && point.rank <= 10 ? '#08111f' : '#ffffff'
      ctx.font = `900 ${labelRank(point.rank).length > 2 ? 11 : 13}px Inter, system-ui, sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(labelRank(point.rank), x, y + 0.5)
      point._canvasIndex = index
    }
  },

  _handleClick(event) {
    const clicked = this._map.latLngToLayerPoint(event.latlng)
    let bestIndex = -1
    let bestDistance = Infinity

    for (const [index, point] of this.points.entries()) {
      const layerPoint = this._map.latLngToLayerPoint([point.lat, point.lng])
      const distance = clicked.distanceTo(layerPoint)
      if (distance < bestDistance) {
        bestDistance = distance
        bestIndex = index
      }
    }

    if (bestIndex === -1 || bestDistance > 22) return

    if (this.view === 'evidence') {
      const point = this.points[bestIndex]
      L.popup()
        .setLatLng([point.lat, point.lng])
        .setContent(`
          <strong>${point.id}: ${labelRank(point.rank)}</strong><br>
          Top result: ${point.topResult}<br>
          Top three: ${(point.topThree || []).join(', ')}
        `)
        .openOn(this._map)
    }

    this.onSelect?.(bestIndex)
  },
})

const keywordScans = [
  { business: 'Summit Building Group - Remodeling services', address: '1401 21st Street #7958, Sacramento, CA', keyword: 'home improvement', avgScore: null, lastScan: 'Jun 19 2026 12:16 PM', timezone: 'America/Los_Angeles', shape: 'Circle', points: 39, duration: '15 minutes', cadence: 'Once at 9:00 AM' },
  { business: 'Summit Building Group - Remodeling services', address: '1401 21st Street #7958, Sacramento, CA', keyword: 'roofing services', avgScore: null, lastScan: 'Jun 19 2026 12:18 PM', timezone: 'America/Los_Angeles', shape: 'Circle', points: 39, duration: '15 minutes', cadence: 'Once at 9:00 AM' },
  { business: 'Summit Building Group - Remodeling services', address: '1401 21st Street #7958, Sacramento, CA', keyword: 'adu contractor', avgScore: 20.4, lastScan: 'Jun 19 2026 12:19 PM', timezone: 'America/Los_Angeles', shape: 'Circle', points: 39, duration: '15 minutes', cadence: 'Once at 9:00 AM' },
  { business: 'Summit Building Group - Remodeling services', address: '1401 21st Street #7958, Sacramento, CA', keyword: 'bathroom remodeling', avgScore: 16.7, lastScan: 'Jun 19 2026 12:20 PM', timezone: 'America/Los_Angeles', shape: 'Circle', points: 39, duration: '15 minutes', cadence: 'Once at 9:00 AM' },
  { business: 'Summit Building Group - Remodeling services', address: '1401 21st Street #7958, Sacramento, CA', keyword: 'kitchen remodeling', avgScore: 16.1, lastScan: 'Jun 19 2026 12:15 PM', timezone: 'America/Los_Angeles', shape: 'Circle', points: 39, duration: '15 minutes', cadence: 'Once at 9:00 AM' },
  { business: 'Summit Building Group - Remodeling services', address: '1401 21st Street #7958, Sacramento, CA', keyword: 'general contractor', avgScore: 12.2, lastScan: 'Jun 19 2026 12:18 PM', timezone: 'America/Los_Angeles', shape: 'Circle', points: 39, duration: '15 minutes', cadence: 'Once at 9:00 AM' },
  { business: 'Summit Building Group - Remodeling services', address: '1401 21st Street #7958, Sacramento, CA', keyword: 'general contractor', avgScore: 11.7, lastScan: 'Jun 19 2026 12:17 PM', timezone: 'America/Los_Angeles', shape: 'Circle', points: 39, duration: '15 minutes', cadence: 'Once at 9:00 AM' },
  { business: 'Summit Building Group - Remodeling services', address: '1401 21st Street #7958, Sacramento, CA', keyword: 'home remodeling', avgScore: 10.4, lastScan: 'Jun 19 2026 12:18 PM', timezone: 'America/Los_Angeles', shape: 'Circle', points: 39, duration: '15 minutes', cadence: 'Once at 9:00 AM' },
  { business: 'Summit Building Group - Remodeling services', address: '1401 21st Street #7958, Sacramento, CA', keyword: 'home remodeling', avgScore: 9.9, lastScan: 'Jun 19 2026 12:18 PM', timezone: 'America/Los_Angeles', shape: 'Circle', points: 39, duration: '15 minutes', cadence: 'Once at 9:00 AM' },
]

const state = {
  dataset: 'proof17',
  gridSize: 17,
  shape: 'square',
  queue: 'standard',
  view: 'pins',
  selectedIndex: 144,
  selectedKeywordIndex: 2,
  plannerProspects: 1,
  mapCenter: null,
  mapZoom: null,
}

function rankClass(rank) {
  if (rank === null || rank === undefined) return 'rank-none'
  if (rank <= 3) return 'rank-good'
  if (rank <= 10) return 'rank-mid'
  if (rank <= 20) return 'rank-low'
  return 'rank-none'
}

function scoreClass(score) {
  if (score === null || score === undefined) return 'score-nr'
  if (score <= 10) return 'score-good'
  if (score <= 15) return 'score-mid'
  return 'score-low'
}

function labelRank(rank) {
  if (rank === null || rank === undefined) return '20+'
  return rank > 20 ? '20+' : String(rank)
}

function labelScore(score) {
  return score === null || score === undefined ? 'NR' : score.toFixed(1)
}

function rankColor(rank) {
  if (rank === null || rank === undefined || rank > 20) return '#dc2626'
  if (rank <= 3) return '#059669'
  if (rank <= 10) return '#eab308'
  return '#f97316'
}

function coordinateForCell(row, col, size, center, radiusKm = 2) {
  const centerIndex = (size - 1) / 2
  const stepKm = size === 1 ? 0 : (2 * radiusKm) / (size - 1)
  const northKm = (centerIndex - row) * stepKm
  const eastKm = (col - centerIndex) * stepKm
  const kmPerLatDegree = 110.574
  const kmPerLngDegree = 111.32 * Math.cos((center.lat * Math.PI) / 180)
  return {
    lat: center.lat + northKm / kmPerLatDegree,
    lng: center.lng + eastKm / kmPerLngDegree,
  }
}

function deterministicNoise(row, col, salt = 0) {
  const value = Math.sin((row + 1) * 12.9898 + (col + 1) * 78.233 + salt * 37.719) * 43758.5453
  return value - Math.floor(value)
}

function gaussian(dx, dy, width) {
  return Math.exp(-((dx * dx + dy * dy) / width))
}

function clampRank(rank) {
  return Math.max(1, Math.min(24, rank))
}

function makeSimulation(size, shape) {
  const center = Math.floor(size / 2)
  const points = []
  for (let row = 0; row < size; row += 1) {
    for (let col = 0; col < size; col += 1) {
      const dx = col - center
      const dy = row - center
      const distance = Math.sqrt(dx * dx + dy * dy)
      if (shape === 'circle' && distance > center + 0.35) continue
      const organicDistance = Math.sqrt(Math.pow((dx + 0.7) * 0.92, 2) + Math.pow((dy - 0.4) * 1.08, 2))
      const diagonalCorridorBoost = Math.exp(-Math.pow(dy - dx * 0.34 - 1.25, 2) / 7) * 3.3
      const westPocketBoost = gaussian(dx + 4.1, dy - 1.4, 10) * 2.6
      const southPocketBoost = gaussian(dx - 0.8, dy - 4.6, 12) * 2.1
      const eastRiverPenalty = Math.exp(-Math.pow(dx - 5.1, 2) / 5) * Math.exp(-Math.pow(dy + 0.3, 2) / 22) * 4.0
      const northeastCompetition = gaussian(dx - 3.6, dy + 4.2, 11) * 4.2
      const southwestGap = gaussian(dx + 5.4, dy - 5.2, 11) * 3.5
      const microVariation =
        (deterministicNoise(row, col) - 0.5) * 3.8 +
        Math.sin(row * 0.82 + col * 0.31) * 1.1 +
        Math.cos(col * 1.17 - row * 0.43) * 0.9
      const rawRank =
        organicDistance * 2.05 +
        4.2 -
        diagonalCorridorBoost -
        westPocketBoost -
        southPocketBoost +
        eastRiverPenalty +
        northeastCompetition +
        southwestGap +
        microVariation
      const rank = clampRank(Math.round(rawRank))
      const edgeVolatility = distance > center * 0.86 && deterministicNoise(row, col, 2) > 0.28
      const missing = rank > 19 || edgeVolatility
      const coordinate = coordinateForCell(row, col, size, austinCenter, 2)
      points.push({
        id: `r${row}c${col}`,
        row,
        col,
        ...coordinate,
        rank: missing ? null : rank,
        topResult: missing ? 'Show Me Pizza' : rank <= 4 ? 'Home Slice Pizza' : 'Via 313 Pizza',
        topThree: rank <= 4 ? ['Home Slice Pizza', 'Show Me Pizza', 'Via 313 Pizza'] : ['Show Me Pizza', 'Via 313 Pizza', 'DeSano Downtown'],
      })
    }
  }
  const centerPoint = points.find((point) => point.row === center && point.col === center)
  if (centerPoint) {
    centerPoint.rank = 3
    centerPoint.topResult = 'Home Slice Pizza'
  }
  return {
    size,
    points,
    center: austinCenter,
    label: `Modeled ${size} x ${size} demo`,
    source: 'Modeled rank response - no new API cost',
  }
}

function gridFromRun(run, size, label, source) {
  const points = run.results.map((result) => ({
    id: result.point.tag,
    row: result.point.row,
    col: result.point.col,
    lat: result.point.lat,
    lng: result.point.lng,
    rank: result.rank,
    topResult: result.matched_item?.title || result.top_items?.[0]?.title || 'Not found',
    topThree: (result.top_items || []).slice(0, 3).map((item) => item.title || 'Unknown'),
  }))
  return {
    size,
    points,
    center: austinCenter,
    label,
    source,
  }
}

function activeGrid() {
  if (state.dataset === 'proof5') {
    return gridFromRun(proofRun, 5, 'Real cached proof 5 x 5', 'Historical saved DataForSEO receipt - 25 paid coordinate results')
  }
  if (state.dataset === 'simulation') {
    return makeSimulation(state.gridSize, state.shape)
  }
  return gridFromRun(proof17Run, 17, 'Real DataForSEO proof 17 x 17', 'Saved DataForSEO Standard Queue receipt - 289 paid coordinate results')
}

function activeProject() {
  if (state.dataset === 'proof17') {
    return {
      kind: 'Real paid proof project',
      name: 'Home Slice Pizza 17 x 17 DataForSEO proof',
      badge: 'Real paid rank data',
      scope: '1 real proof scan',
      note: 'This is the live 289-coordinate Standard Queue scan. The browser reuses the saved receipt and does not spend again.',
      plannerNote: 'This is the showpiece proof scan. Use the planner to estimate bulk spend before approving any prospect list.',
    }
  }

  if (state.dataset === 'proof5') {
    return {
      kind: 'Real cached proof project',
      name: 'Home Slice Pizza 5 x 5 DataForSEO proof',
      badge: 'Cached paid rank data',
      scope: '1 cached proof scan',
      note: 'This uses the saved 25-coordinate DataForSEO receipt. No new API spend happens in the browser.',
      plannerNote: 'Use this mode to model the original 1,000-prospect triage idea at low cost.',
    }
  }

  return {
    kind: 'Modeled visual project',
    name: 'Home Slice Pizza 17 x 17 one-prospect demo',
    badge: 'Modeled rank data',
    scope: '1 modeled prospect',
    note: 'This is the dense Local Falcon-style visual. It shows the experience without buying 289 coordinate results.',
    plannerNote: 'Use this mode for showpiece visuals. The 1,000-prospect line is only a paid-equivalent scenario.',
  }
}

function metrics(points) {
  const ranks = points.map((point) => point.rank).filter((rank) => rank !== null && rank !== undefined)
  const top3 = ranks.filter((rank) => rank <= 3).length
  const top10 = ranks.filter((rank) => rank <= 10).length
  const avg = ranks.length ? ranks.reduce((sum, rank) => sum + rank, 0) / ranks.length : 0
  return {
    top3,
    top10,
    missing: points.length - ranks.length,
    solv: points.length ? (top3 / points.length) * 100 : 0,
    visible: points.length ? (top10 / points.length) * 100 : 0,
    avg,
  }
}

function keywordMetrics(rows) {
  const found = rows.filter((row) => row.avgScore !== null && row.avgScore !== undefined)
  const best = [...found].sort((a, b) => a.avgScore - b.avgScore)[0]
  const weak = [...rows].sort((a, b) => (b.avgScore || 99) - (a.avgScore || 99))[0]
  return {
    count: rows.length,
    missing: rows.length - found.length,
    avg: found.length ? found.reduce((sum, row) => sum + row.avgScore, 0) / found.length : 0,
    best,
    weak,
  }
}

function competitorPressure(points) {
  const counts = new Map()
  for (const point of points) {
    for (const name of point.topThree || []) {
      counts.set(name, (counts.get(name) || 0) + 1)
    }
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6)
}

function csvEscape(value) {
  const text = String(value ?? '')
  return `"${text.replaceAll('"', '""')}"`
}

function exportKeywordCsv() {
  const headers = ['business', 'address', 'keyword', 'avg_score', 'last_scan', 'settings']
  const rows = keywordScans.map((row) => [
    row.business,
    row.address,
    row.keyword,
    labelScore(row.avgScore),
    `${row.lastScan} (${row.timezone})`,
    `${row.shape} - ${row.points} pts - ${row.duration} - ${row.cadence}`,
  ])
  const csv = [headers, ...rows].map((row) => row.map(csvEscape).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'geogriddy-keyword-scan-list.csv'
  link.click()
  URL.revokeObjectURL(url)
}

function rememberMapView() {
  if (!leafletMap) return
  const center = leafletMap.getCenter()
  state.mapCenter = [center.lat, center.lng]
  state.mapZoom = leafletMap.getZoom()
  leafletMap.remove()
  leafletMap = null
}

function renderLeafletMap(grid, selected) {
  const mapEl = document.querySelector('#rankMap')
  if (!mapEl) return

  const center = state.mapCenter || [grid.center.lat, grid.center.lng]
  const zoom = state.mapZoom || (grid.size >= 15 ? 13 : 14)
  leafletMap = L.map(mapEl, {
    zoomControl: true,
    scrollWheelZoom: true,
    doubleClickZoom: true,
    dragging: true,
    attributionControl: true,
    preferCanvas: true,
  }).setView(center, zoom)

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(leafletMap)

  new RankCanvasLayer(grid.points, selected, {
    view: state.view,
    onSelect: (index) => {
      const c = leafletMap.getCenter()
      state.mapCenter = [c.lat, c.lng]
      state.mapZoom = leafletMap.getZoom()
      state.selectedIndex = index
      render()
    },
  }).addTo(leafletMap)

  if (!state.mapCenter && grid.points.length) {
    const bounds = L.latLngBounds(grid.points.map((point) => [point.lat, point.lng]))
    leafletMap.fitBounds(bounds, { padding: [38, 38], maxZoom: 14 })
  }

  leafletMap.on('moveend zoomend', () => {
    const c = leafletMap.getCenter()
    state.mapCenter = [c.lat, c.lng]
    state.mapZoom = leafletMap.getZoom()
  })

  mapEl.dataset.mapReady = 'true'
  mapEl.dataset.project = state.dataset
  mapEl.dataset.markerCount = String(grid.points.length)
  window.__geogriddyMapState = () => {
    const c = leafletMap.getCenter()
    return {
      center: { lat: c.lat, lng: c.lng },
      markerCount: grid.points.length,
      project: state.dataset,
      title: grid.label,
      zoom: leafletMap.getZoom(),
    }
  }
}

function renderKeywordReport() {
  const selected = keywordScans[state.selectedKeywordIndex] || keywordScans[0]
  const km = keywordMetrics(keywordScans)
  const rows = keywordScans
    .map((row, index) => {
      const activeClass = index === state.selectedKeywordIndex ? ' selected-row' : ''
      return `
        <tr class="${activeClass}">
          <td><input type="checkbox" aria-label="Select ${row.keyword}"></td>
          <td><button class="business-link" data-keyword-index="${index}">${row.business}<span>${row.address}</span></button></td>
          <td>${row.keyword}</td>
          <td><span class="score-pill ${scoreClass(row.avgScore)}"><i></i>${labelScore(row.avgScore)}</span></td>
          <td><strong>${row.lastScan} (${row.timezone})</strong><span>${row.shape} - ${row.points} pts - ${row.duration} - ${row.cadence}</span></td>
          <td><button class="table-button" data-keyword-index="${index}">View</button></td>
        </tr>
      `
    })
    .join('')

  return `
    <section class="report-card">
      <div class="section-head">
        <div>
          <div class="filter-row"><span>Business: <b>1 selected</b></span><span>Keyword</span><span>Avg score</span></div>
          <h2>Keyword Scan List</h2>
          <p>Built for Alana's request: the lead can receive one visual package with every keyword, score, scan setting, and map drilldown.</p>
        </div>
        <button class="export-button" id="exportKeywords">Export CSV</button>
      </div>
      <div class="keyword-summary">
        <article><strong>${km.count}</strong><span>Keyword scans</span></article>
        <article><strong>${km.missing}</strong><span>Not ranking</span></article>
        <article><strong>${km.avg.toFixed(1)}</strong><span>Avg found score</span></article>
        <article><strong>${km.best?.keyword || 'None'}</strong><span>Best opportunity</span></article>
      </div>
      <div class="selected-keyword">
        <b>${selected.keyword}</b>
        <span>${selected.business} needs a map proof, a keyword score, and a plain-English outreach note in the same report.</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th><input type="checkbox" aria-label="Select all keyword scans"></th>
              <th>Business</th>
              <th>Keyword</th>
              <th>Avg. score</th>
              <th>Last scan / settings</th>
              <th></th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </section>
  `
}

function render() {
  rememberMapView()
  const grid = activeGrid()
  const project = activeProject()
  const { size, points } = grid
  const selected = points[Math.min(state.selectedIndex, points.length - 1)] || points[0]
  const m = metrics(points)
  const cost = points.length * queueRates[state.queue]
  const isProof = state.dataset === 'proof5' || state.dataset === 'proof17'
  const scanCostLabel = state.dataset === 'simulation' ? 'paid equivalent' : 'real scan'
  const pressureRows = competitorPressure(points)
    .map(([name, count]) => `<div class="pressure-row"><span>${name}</span><b>${count}</b></div>`)
    .join('')

  document.querySelector('#app').innerHTML = `
    <div class="shell">
      <aside class="sidebar">
        <div class="brand">GeoGriddy</div>
        <nav>
          <a class="active">Studio</a>
          <a href="/docs/local-seo-geogrid-executive-report.html">Executive Report</a>
          <a href="/docs/local-seo-geogrid-executive-report.pdf">Executive PDF</a>
          <a href="/docs/DANIEL_HANDOFF.md">Daniel Handoff</a>
          <a href="/docs/PRODUCT_STATUS.md">Product Status</a>
          <a href="/docs/ROADMAP.md">Roadmap</a>
          <a href="/docs/TECHNICAL_NOTES.md">Technical Notes</a>
        </nav>
      </aside>
      <main>
        <header class="hero">
          <div>
            <div class="badges"><span>${project.badge}</span><span>Interactive map display</span><span>Keyword list reports</span><span>$${cost.toFixed(3)} ${scanCostLabel}</span></div>
            <h1>Local SEO GeoGriddy Studio</h1>
            <p>Interactive map rank pins, Alana-style keyword scan lists, raw proof receipts, and prospect economics in one focused workflow.</p>
            <div class="hero-actions">
              <a href="/docs/local-seo-geogrid-executive-report.html" target="_blank" rel="noreferrer">Open Executive Report</a>
              <a href="/docs/local-seo-geogrid-executive-report.pdf" target="_blank" rel="noreferrer">Open PDF</a>
            </div>
          </div>
          <div class="controls">
            <label>Project<select id="dataset"><option value="proof17">17 x 17 real proof</option></select></label>
            <label class="${isProof ? 'control-disabled' : ''}">Grid<select id="gridSize" ${isProof ? 'disabled' : ''}><option>7</option><option>9</option><option>15</option><option selected>17</option><option>21</option></select></label>
            <label class="${isProof ? 'control-disabled' : ''}">Shape<select id="shape" ${isProof ? 'disabled' : ''}><option value="square">Square</option><option value="circle">Circle</option></select></label>
            <label>Queue<select id="queue"><option value="standard">Standard</option><option value="priority">Priority</option><option value="live">Live</option></select></label>
          </div>
        </header>
        <section class="report-cta">
          <div>
            <span>Executive brief</span>
            <h2>Cost model, build-vs-buy reasoning, and source notes</h2>
            <p>The report explains why DataForSEO is the rank-data backbone, what 3 x 3 through 17 x 17 scans cost, and how this becomes a Local SEO Brain feature instead of another SaaS.</p>
          </div>
          <div>
            <a href="/docs/local-seo-geogrid-executive-report.html" target="_blank" rel="noreferrer">Open designed HTML</a>
            <a href="/docs/local-seo-geogrid-executive-report.pdf" target="_blank" rel="noreferrer">Open PDF</a>
          </div>
        </section>
        <section class="metrics">
          <article><strong>${m.solv.toFixed(1)}%</strong><span>Top 3 coverage</span></article>
          <article><strong>${m.visible.toFixed(1)}%</strong><span>Top 10 coverage</span></article>
          <article><strong>${m.avg.toFixed(1)}</strong><span>Average found rank</span></article>
          <article><strong>${m.missing}</strong><span>Beyond depth</span></article>
        </section>
        <section class="layout">
          <div class="primary-stack">
            <div class="map-card">
              <div class="tabs"><button data-view="pins">Rank pins</button><button data-view="heat">Smooth heat</button><button data-view="evidence">Evidence</button><span>${points.length} coordinates</span></div>
              <div class="project-strip">
                <span>${project.kind}</span>
                <strong>${project.name}</strong>
                <em>${project.scope}</em>
              </div>
              <div class="map-meta">
                <strong>${grid.label}</strong>
                <span>${grid.source}. ${project.note}</span>
              </div>
              <div class="map-shell">
                <div class="map-actions">
                  <button id="zoomIn" type="button">+</button>
                  <button id="zoomOut" type="button">-</button>
                  <button id="resetMap" type="button">Reset</button>
                </div>
                <div id="rankMap" class="leaflet-map" aria-label="Interactive local SEO rank map"></div>
                <div class="map-help">Drag to pan. Scroll or use controls to zoom.</div>
              </div>
            </div>
            <aside class="panel planner">
              <h2>Bulk Planner</h2>
              <label>Prospects<input id="plannerProspects" type="number" min="1" step="1" value="${state.plannerProspects}"></label>
              <dl>
                <div><dt>Grid</dt><dd>${size} x ${size}</dd></div>
                <div><dt>Total coordinate tasks</dt><dd>${(points.length * state.plannerProspects).toLocaleString()}</dd></div>
                <div><dt>Estimated rank-data cost</dt><dd>$${(cost * state.plannerProspects).toFixed(2)}</dd></div>
              </dl>
              <pre>python tools/bulk_geogrid_runner.py --prospects prospects.csv --method ${state.queue} --grid-size ${size} --radius-km 2 --depth 20 --confirm-cost-usd ${(cost * state.plannerProspects).toFixed(2)}
# Dry-run by default. Add --execute only after the prospect list and spend ceiling are approved.</pre>
            </aside>
          </div>
          <div class="side-stack">
            <aside class="panel">
              <h2>Selected Coordinate</h2>
              <dl>
                <div><dt>Rank</dt><dd>${labelRank(selected.rank)}</dd></div>
                <div><dt>Cell</dt><dd>${selected.id}</dd></div>
                <div><dt>Top result</dt><dd>${selected.topResult}</dd></div>
              </dl>
              <h3>Top three at this point</h3>
              ${(selected.topThree || []).map((name, index) => `<div class="mini-row"><span>${name}</span><b>${index + 1}</b></div>`).join('')}
            </aside>
            <aside class="panel">
              <h2>Prospect Economics</h2>
              <dl>
                <div><dt>Pins per scan</dt><dd>${points.length}</dd></div>
                <div><dt>Current project</dt><dd>${project.scope}</dd></div>
                <div><dt>Paid equivalent</dt><dd>$${cost.toFixed(4)}</dd></div>
                <div><dt>1,000 paid equivalent</dt><dd>$${(cost * 1000).toFixed(2)}</dd></div>
              </dl>
              <p class="note">${project.plannerNote} This ${size} x ${size} ${state.queue} view is about $${cost.toFixed(3)} per business-keyword scan.</p>
            </aside>
            <aside class="panel">
              <h2>Competitor Pressure</h2>
              ${pressureRows}
            </aside>
          </div>
        </section>
        ${renderKeywordReport()}
      </main>
    </div>
  `

  document.querySelector('#dataset').value = state.dataset
  document.querySelector('#gridSize').value = String(state.gridSize)
  document.querySelector('#shape').value = state.shape
  document.querySelector('#queue').value = state.queue
  document.querySelectorAll('[data-view]').forEach((button) => {
    button.classList.toggle('active', button.dataset.view === state.view)
    button.addEventListener('click', () => {
      state.view = button.dataset.view
      render()
    })
  })
  document.querySelector('#dataset').addEventListener('change', (event) => {
    state.dataset = event.target.value
    state.mapCenter = null
    state.mapZoom = null
    state.plannerProspects = state.dataset === 'simulation' ? 1 : 1000
    state.selectedIndex = state.dataset === 'proof5' ? 12 : Math.floor((state.gridSize * state.gridSize) / 2)
    render()
  })
  document.querySelector('#gridSize').addEventListener('change', (event) => {
    state.gridSize = Number(event.target.value)
    state.mapCenter = null
    state.mapZoom = null
    state.selectedIndex = Math.floor((state.gridSize * state.gridSize) / 2)
    render()
  })
  document.querySelector('#shape').addEventListener('change', (event) => {
    state.shape = event.target.value
    state.mapCenter = null
    state.mapZoom = null
    render()
  })
  document.querySelector('#queue').addEventListener('change', (event) => {
    state.queue = event.target.value
    render()
  })
  document.querySelector('#plannerProspects').addEventListener('input', (event) => {
    state.plannerProspects = Math.max(1, Number(event.target.value || 1))
    render()
  })
  document.querySelector('#exportKeywords').addEventListener('click', exportKeywordCsv)
  document.querySelector('#zoomIn').addEventListener('click', () => leafletMap?.zoomIn())
  document.querySelector('#zoomOut').addEventListener('click', () => leafletMap?.zoomOut())
  document.querySelector('#resetMap').addEventListener('click', () => {
    state.mapCenter = null
    state.mapZoom = null
    render()
  })
  document.querySelectorAll('[data-keyword-index]').forEach((button) => {
    button.addEventListener('click', () => {
      state.selectedKeywordIndex = Number(button.dataset.keywordIndex)
      state.dataset = 'proof17'
      state.shape = 'square'
      state.gridSize = 17
      state.mapCenter = null
      state.mapZoom = null
      state.selectedIndex = Math.floor((state.gridSize * state.gridSize) / 2)
      render()
    })
  })
  renderLeafletMap(grid, selected)
}

render()
