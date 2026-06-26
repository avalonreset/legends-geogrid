import proofRun from './data/home-slice-5x5.json'
import './styles.css'

const queueRates = {
  standard: 0.0006,
  priority: 0.0012,
  live: 0.002,
}

const state = {
  dataset: 'proof5',
  gridSize: 17,
  queue: 'standard',
  view: 'pins',
  selectedIndex: 12,
  plannerProspects: 1000,
}

function rankClass(rank) {
  if (rank === null || rank === undefined) return 'rank-none'
  if (rank <= 3) return 'rank-good'
  if (rank <= 10) return 'rank-mid'
  if (rank <= 20) return 'rank-low'
  return 'rank-none'
}

function labelRank(rank) {
  if (rank === null || rank === undefined) return '20+'
  return rank > 20 ? '20+' : String(rank)
}

function makeSimulation(size) {
  const center = Math.floor(size / 2)
  const points = []
  for (let row = 0; row < size; row += 1) {
    for (let col = 0; col < size; col += 1) {
      const dx = col - center
      const dy = row - center
      const distance = Math.sqrt(dx * dx + dy * dy)
      const wave = Math.sin(row * 1.15) + Math.cos(col * 0.9)
      const rank = Math.max(1, Math.round(distance * 2.25 + wave + 2))
      const missing = distance > center * 0.86 || rank > 18
      points.push({
        id: `r${row}c${col}`,
        row,
        col,
        rank: missing ? null : rank,
        topResult: missing ? 'Show Me Pizza' : rank <= 4 ? 'Home Slice Pizza' : 'Via 313 Pizza',
        topThree: rank <= 4 ? ['Home Slice Pizza', 'Show Me Pizza', 'Via 313 Pizza'] : ['Show Me Pizza', 'Via 313 Pizza', 'DeSano Downtown'],
      })
    }
  }
  points[center * size + center].rank = 3
  points[center * size + center].topResult = 'Home Slice Pizza'
  return { size, points }
}

function proofGrid() {
  const size = 5
  const points = proofRun.results.map((result) => ({
    id: result.point.tag,
    row: result.point.row,
    col: result.point.col,
    rank: result.rank,
    topResult: result.matched_item?.title || result.top_items?.[0]?.title || 'Not found',
    topThree: (result.top_items || []).slice(0, 3).map((item) => item.title || 'Unknown'),
  }))
  return { size, points }
}

function activeGrid() {
  return state.dataset === 'proof5' ? proofGrid() : makeSimulation(state.gridSize)
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

function competitorPressure(points) {
  const counts = new Map()
  for (const point of points) {
    for (const name of point.topThree || []) {
      counts.set(name, (counts.get(name) || 0) + 1)
    }
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6)
}

function render() {
  const { size, points } = activeGrid()
  const selected = points[Math.min(state.selectedIndex, points.length - 1)] || points[0]
  const m = metrics(points)
  const pins = points
    .map((point, index) => {
      const x = size === 1 ? 50 : 23 + (point.col / (size - 1)) * 54
      const y = size === 1 ? 50 : 10 + (point.row / (size - 1)) * 78
      const selectedClass = point === selected ? ' selected' : ''
      return `<button class="pin ${rankClass(point.rank)}${selectedClass}" style="left:${x}%;top:${y}%" data-index="${index}">${labelRank(point.rank)}</button>`
    })
    .join('')

  const heat = points
    .map((point) => {
      const x = size === 1 ? 50 : 23 + (point.col / (size - 1)) * 54
      const y = size === 1 ? 50 : 10 + (point.row / (size - 1)) * 78
      const opacity = point.rank === null ? 0.58 : Math.max(0.16, 0.78 - point.rank / 28)
      return `<span class="heat-dot ${rankClass(point.rank)}" style="left:${x}%;top:${y}%;opacity:${opacity}"></span>`
    })
    .join('')

  const cost = points.length * queueRates[state.queue]
  const pressureRows = competitorPressure(points)
    .map(([name, count]) => `<div class="pressure-row"><span>${name}</span><b>${count}</b></div>`)
    .join('')

  document.querySelector('#app').innerHTML = `
    <div class="shell">
      <aside class="sidebar">
        <div class="brand">GeoGrid</div>
        <nav>
          <a class="active">Studio</a>
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
            <div class="badges"><span>DataForSEO rank source</span><span>Google map display</span><span>$${cost.toFixed(3)} scan</span></div>
            <h1>Local SEO GeoGrid Studio</h1>
            <p>Local Falcon-style rank pins, smooth opportunity heat, raw proof receipts, and prospect economics in one workflow.</p>
          </div>
          <div class="controls">
            <label>Dataset<select id="dataset"><option value="proof5">Proof 5 x 5</option><option value="simulation">Simulation</option></select></label>
            <label>Grid<select id="gridSize"><option>9</option><option>15</option><option selected>17</option><option>21</option></select></label>
            <label>Queue<select id="queue"><option value="standard">Standard</option><option value="priority">Priority</option><option value="live">Live</option></select></label>
          </div>
        </header>
        <section class="metrics">
          <article><strong>${m.solv.toFixed(1)}%</strong><span>Top 3 coverage</span></article>
          <article><strong>${m.visible.toFixed(1)}%</strong><span>Top 10 coverage</span></article>
          <article><strong>${m.avg.toFixed(1)}</strong><span>Average found rank</span></article>
          <article><strong>${m.missing}</strong><span>Beyond depth</span></article>
        </section>
        <section class="layout">
          <div class="map-card">
            <div class="tabs"><button data-view="pins">Rank pins</button><button data-view="heat">Smooth heat</button><button data-view="evidence">Evidence</button><span>${points.length} coordinates</span></div>
            <div class="map">
              <img src="/assets/geo-grid-austin-map.png" alt="Austin map background">
              <div class="overlay ${state.view === 'heat' ? 'heat-mode' : ''}">${state.view === 'heat' ? heat : pins}</div>
            </div>
          </div>
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
              <div><dt>One prospect</dt><dd>$${cost.toFixed(4)}</dd></div>
              <div><dt>1,000 prospects</dt><dd>$${(cost * 1000).toFixed(2)}</dd></div>
            </dl>
            <p class="note">A 5 x 5 Standard scan is about $0.015. The expensive part is how many coordinates we decide to rank-check.</p>
          </aside>
          <aside class="panel">
            <h2>Competitor Pressure</h2>
            ${pressureRows}
          </aside>
          <aside class="panel planner">
            <h2>Bulk Planner</h2>
            <label>Prospects<input id="plannerProspects" type="number" min="1" step="1" value="${state.plannerProspects}"></label>
            <dl>
              <div><dt>Grid</dt><dd>${size} x ${size}</dd></div>
              <div><dt>Total coordinate tasks</dt><dd>${(points.length * state.plannerProspects).toLocaleString()}</dd></div>
              <div><dt>Estimated rank-data cost</dt><dd>$${(cost * state.plannerProspects).toFixed(2)}</dd></div>
            </dl>
            <pre>python tools/bulk_geogrid_runner.py --prospects prospects.csv --method ${state.queue} --grid-size ${size} --radius-km 2 --depth 20 --execute --confirm-cost-usd ${(cost * state.plannerProspects).toFixed(2)}</pre>
          </aside>
        </section>
      </main>
    </div>
  `

  document.querySelector('#dataset').value = state.dataset
  document.querySelector('#gridSize').value = String(state.gridSize)
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
    state.selectedIndex = state.dataset === 'proof5' ? 12 : Math.floor((state.gridSize * state.gridSize) / 2)
    render()
  })
  document.querySelector('#gridSize').addEventListener('change', (event) => {
    state.gridSize = Number(event.target.value)
    state.selectedIndex = Math.floor((state.gridSize * state.gridSize) / 2)
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
  document.querySelectorAll('.pin').forEach((button) => {
    button.addEventListener('click', () => {
      state.selectedIndex = Number(button.dataset.index)
      render()
    })
  })
}

render()
