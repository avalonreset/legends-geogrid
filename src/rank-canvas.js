import L from 'leaflet'
import { OCTAGON_CUT, STOP_SIGN_SCALE, DIAMOND_HALF } from './map-geometry.js'

const OCTAGON_VERTICES = [[OCTAGON_CUT, 0], [1 - OCTAGON_CUT, 0], [1, OCTAGON_CUT],
  [1, 1 - OCTAGON_CUT], [1 - OCTAGON_CUT, 1], [OCTAGON_CUT, 1], [0, 1 - OCTAGON_CUT], [0, OCTAGON_CUT]]

// Shared textures: generate once, stamp for every visible rank-one cell.
let dominanceSprites
function getDominanceSprites() {
  if (dominanceSprites) return dominanceSprites
  const halo = document.createElement('canvas'), sparkle = document.createElement('canvas')
  halo.width = halo.height = sparkle.width = sparkle.height = 96
  const glow = halo.getContext('2d')
  const gradient = glow.createRadialGradient(48, 48, 0, 48, 48, 48)
  gradient.addColorStop(0, 'rgba(0,255,255,0)')
  gradient.addColorStop(.34, 'rgba(0,255,255,0)')
  gradient.addColorStop(.48, 'rgba(150,255,255,.85)')
  gradient.addColorStop(.64, 'rgba(0,255,255,.55)')
  gradient.addColorStop(1, 'rgba(0,255,255,0)')
  glow.fillStyle = gradient
  glow.fillRect(0, 0, 96, 96)
  const star = sparkle.getContext('2d')
  const aura = star.createRadialGradient(48, 48, 0, 48, 48, 46)
  aura.addColorStop(0, 'rgba(255,255,255,.95)')
  aura.addColorStop(.2, 'rgba(180,255,255,.65)')
  aura.addColorStop(1, 'rgba(0,255,255,0)')
  star.fillStyle = aura
  star.fillRect(0, 0, 96, 96)
  star.beginPath()
  ;[[48, 2], [55, 41], [94, 48], [55, 55], [48, 94], [41, 55], [2, 48], [41, 41]]
    .forEach(([x, y], i) => star[i ? 'lineTo' : 'moveTo'](x, y))
  star.closePath()
  star.fillStyle = '#fff'
  star.fill()
  dominanceSprites = { halo, sparkle }
  return dominanceSprites
}

// One viewport bitmap replaces thousands of individually positioned SVG nodes.
// Geographic coordinates and evidence stay unchanged; hover uses the same shapes.
export const RankCanvasLayer = L.Layer.extend({
  initialize({ onSelect }) {
    this.onSelect = onSelect
    this.cells = []
    this.diamonds = []
    this.spacing = 0
    this.hits = []
    this.frame = 0
    this.focusIndex = -1
  },
  onAdd(map) {
    this._map = map
    this.canvas = L.DomUtil.create('canvas', 'ranking-canvas', map.getPane('rankingPane'))
    this.canvas.style.pointerEvents = 'none'
    // Animate only the rank-one sheen, never the map or the full data layer.
    this.rankOneCanvas = L.DomUtil.create('canvas', 'ranking-canvas rank-one-canvas', map.getPane('rankingPane'))
    this.rankOneCanvas.style.pointerEvents = 'none'
    this.motionPreference = matchMedia('(prefers-reduced-motion: reduce)')
    this.rankOneVisibility = () => {
      this.stopRankOneAnimation()
      this.drawRankOne(performance.now())
      this.animateRankOne()
    }
    document.addEventListener('visibilitychange', this.rankOneVisibility)
    this.motionPreference.addEventListener('change', this.rankOneVisibility)
    this.tooltip = L.tooltip({ direction: 'top', offset: [0, -8] })
    this.queueDraw = () => {
      if (!this.frame) this.frame = requestAnimationFrame(() => { this.frame = 0; this.draw() })
    }
    this.hover = event => {
      const hit = this.hitAt(event.containerPoint)
      if (hit?.id === this.hoverId) return
      this.hideTooltip()
      if (hit) this.showTooltip(hit)
      map.getContainer().style.cursor = hit ? 'pointer' : ''
    }
    this.click = event => {
      const hit = this.hitAt(event.containerPoint)
      if (hit) this.onSelect(hit.id)
    }
    this.hide = () => this.hideTooltip()
    map.on('move zoom resize', this.queueDraw)
    map.on('movestart zoomstart mouseout', this.hide)
    map.on('mousemove', this.hover)
    map.on('click', this.click)
    map.getContainer().addEventListener('keydown', this.keydown = event => {
      if (event.target !== map.getContainer()) return
      if (['ArrowRight', 'ArrowLeft', 'ArrowDown', 'ArrowUp'].includes(event.key)) {
        event.preventDefault()
        event.stopImmediatePropagation()
        const delta = ['ArrowRight', 'ArrowDown'].includes(event.key) ? 1 : -1
        this.focusIndex = (this.focusIndex + delta + this.cells.length) % this.cells.length
        const cell = this.cells[this.focusIndex]
        if (cell) {
          map.panInside([cell.lat, cell.lng], { padding: [35, 35], animate: false })
          this.showTooltip(cell)
        }
      } else if (event.key === 'Enter' && this.cells[this.focusIndex]) {
        event.preventDefault()
        this.onSelect(this.cells[this.focusIndex].id)
      } else if (event.key === 'Escape') this.hideTooltip()
    }, true)
    map.getContainer().setAttribute('aria-label', 'Ranking map. Arrow keys explore measured locations; Enter opens evidence.')
    this.draw()
  },
  onRemove(map) {
    cancelAnimationFrame(this.frame)
    this.stopRankOneAnimation()
    document.removeEventListener('visibilitychange', this.rankOneVisibility)
    this.motionPreference.removeEventListener('change', this.rankOneVisibility)
    map.off('move zoom resize', this.queueDraw)
    map.off('movestart zoomstart mouseout', this.hide)
    map.off('mousemove', this.hover)
    map.off('click', this.click)
    map.getContainer().removeEventListener('keydown', this.keydown, true)
    this.hideTooltip()
    this.canvas.remove()
    this.rankOneCanvas.remove()
  },
  setData(cells, diamonds, spacing, translucent, blendBoundary = null) {
    this.hideTooltip()
    this.cells = cells
    this.diamonds = diamonds
    this.spacing = spacing
    this.translucent = translucent
    this.blendBoundary = blendBoundary
    this.focusIndex = -1
    this.draw()
  },
  hideTooltip() {
    if (this.tooltip) this.tooltip.remove()
    this.hoverId = null
  },
  showTooltip(cell) {
    this.hoverId = cell.id
    this.tooltip.setLatLng([cell.lat, cell.lng]).setContent(cell.label).addTo(this._map)
  },
  hitAt({ x, y }) {
    return this.hits.find(cell => {
      const dx = Math.abs(x - cell.sx), dy = Math.abs(y - cell.sy)
      return dx <= cell.size / 2 && dy <= cell.size / 2 &&
        dx + dy <= cell.size * (1 - OCTAGON_CUT)
    })
  },
  pointPosition(id) {
    const cell = this.cells.find(c => c.id === id)
    return cell ? this._map.latLngToContainerPoint([cell.lat, cell.lng]) : null
  },
  stopRankOneAnimation() {
    clearTimeout(this.rankOneTimer)
    cancelAnimationFrame(this.rankOneFrame)
    this.rankOneTimer = this.rankOneFrame = 0
  },
  animateRankOne() {
    if (this.rankOneTimer || this.rankOneFrame || document.hidden || this.motionPreference?.matches ||
        !this.hits.some(cell => cell.dominant && cell.size >= 3)) return
    // Twenty overlay-only frames per second; pan/zoom still redraw at native speed.
    this.rankOneTimer = setTimeout(() => {
      this.rankOneTimer = 0
      this.rankOneFrame = requestAnimationFrame(time => {
        this.rankOneFrame = 0
        this.drawRankOne(time)
        this.animateRankOne()
      })
    }, 50)
  },
  drawRankOne(time = 0) {
    if (!this.rankOneCanvas || !this._map) return
    const started = performance.now()
    const ctx = this.rankOneCanvas.getContext('2d')
    const dpr = Math.min(devicePixelRatio || 1, 2)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, this.rankOneCanvas.width / dpr, this.rankOneCanvas.height / dpr)
    const reduced = this.motionPreference?.matches
    const sprites = getDominanceSprites()
    let highlighted = 0
    for (const cell of this.hits) {
      if (!cell.dominant) continue
      highlighted++
      const size = cell.size
      ctx.save()
      // Strong halo and staggered glints around all eight corners. The face
      // stays cyan; all instances reuse the same two cached textures.
      const phase = reduced || cell.size < 3 ? .25 :
        ((time / 3600 + cell.lat * .37 + cell.lng * .23) % 1 + 1) % 1
      const pulse = .5 - .5 * Math.cos(phase * Math.PI * 2)
      const strength = cell.muted ? .15 : 1
      ctx.globalAlpha = strength * (.65 + pulse * .35)
      const radius = size * .82 + Math.min(4, size * .3)
      ctx.drawImage(sprites.halo, cell.sx - radius, cell.sy - radius, radius * 2, radius * 2)
      OCTAGON_VERTICES.forEach(([vx, vy], i) => {
        const twinkle = reduced || size < 3 ? .55 :
          Math.pow(.5 - .5 * Math.cos((phase + i * .381966) * Math.PI * 2), 3)
        const arm = Math.max(2.8, Math.min(12, size * .24)) * (.65 + twinkle * .55)
        const x = cell.sx + (vx - .5) * size * 1.08
        const y = cell.sy + (vy - .5) * size * 1.08
        ctx.globalAlpha = strength * (.06 + twinkle * .94)
        ctx.drawImage(sprites.sparkle, x - arm, y - arm, arm * 2, arm * 2)
      })
      ctx.restore()
    }
    if (this.stats) Object.assign(this.stats, {
      highlightedPoints: highlighted, shimmerDrawMs: performance.now() - started,
      shimmerAnimating: !document.hidden && !reduced && this.hits.some(cell => cell.dominant && cell.size >= 3),
    })
  },
  draw() {
    if (!this._map || !this.canvas) return
    const started = performance.now()
    const map = this._map, viewport = map.getSize(), dpr = Math.min(devicePixelRatio || 1, 2)
    const width = Math.round(viewport.x * dpr), height = Math.round(viewport.y * dpr)
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width; this.canvas.height = height
    }
    Object.assign(this.canvas.style, { width: `${viewport.x}px`, height: `${viewport.y}px` })
    L.DomUtil.setPosition(this.canvas, map.containerPointToLayerPoint([0, 0]))
    const ctx = this.canvas.getContext('2d'), scale = 2 ** map.getZoom()
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, viewport.x, viewport.y)
    const origin = map.project(map.containerPointToLatLng([0, 0]), map.getZoom())
    const size = this.spacing * scale * STOP_SIGN_SCALE
    const diamondSize = this.spacing * scale * 2 * DIAMOND_HALF
    const stroke = size * .015
    const visible = (x, y, s) => x + s / 2 >= 0 && y + s / 2 >= 0 && x - s / 2 <= viewport.x && y - s / 2 <= viewport.y
    ctx.save()
    if (this.blendBoundary?.length) {
      ctx.beginPath()
      this.blendBoundary.forEach((p, i) => ctx[i ? 'lineTo' : 'moveTo'](p.x * scale - origin.x, p.y * scale - origin.y))
      ctx.closePath()
      ctx.clip()
    }
    for (const diamond of this.diamonds) {
      const x = diamond.x * scale - origin.x, y = diamond.y * scale - origin.y
      if (!visible(x, y, diamondSize)) continue
      ctx.save()
      ctx.beginPath()
      ctx.moveTo(x, y - diamondSize / 2); ctx.lineTo(x + diamondSize / 2, y)
      ctx.lineTo(x, y + diamondSize / 2); ctx.lineTo(x - diamondSize / 2, y); ctx.closePath()
      ctx.save()
      ctx.clip()
      // Texture already contains each contributor's display alpha.
      ctx.globalAlpha = 1
      ctx.drawImage(diamond.texture, x - diamondSize / 2, y - diamondSize / 2, diamondSize, diamondSize)
      ctx.restore()
      ctx.strokeStyle = 'rgba(0,0,0,.5)'; ctx.lineWidth = stroke; ctx.stroke()
      ctx.restore()
    }
    ctx.restore()
    this.hits = []
    for (const cell of this.cells) {
      const x = cell.x * scale - origin.x, y = cell.y * scale - origin.y
      if (!visible(x, y, size)) continue
      this.hits.push({ ...cell, sx: x, sy: y, size })
      ctx.save()
      ctx.beginPath()
      OCTAGON_VERTICES.forEach(([vx, vy], i) => ctx[i ? 'lineTo' : 'moveTo'](x + (vx - .5) * size, y + (vy - .5) * size))
      ctx.closePath()
      if (!['nr', 'unknown', 'other'].includes(cell.kind)) {
        ctx.fillStyle = cell.color
        ctx.globalAlpha = (cell.opacity ?? 1) * (cell.muted ? .15 : 1)
        ctx.fill()
      }
      ctx.globalAlpha = cell.muted ? .15 : 1
      const coverageOutline = cell.coverage && ['nr', 'unknown', 'other'].includes(cell.kind)
      ctx.strokeStyle = coverageOutline ? (cell.kind === 'unknown' ? 'rgba(225,184,105,.65)' : 'rgba(163,177,195,.55)') : 'rgba(0,0,0,.5)'
      ctx.lineWidth = coverageOutline ? Math.max(.8, Math.min(1.5, size * .025)) : size * (cell.active ? .03 : cell.kind === 'unknown' ? .02 : .015)
      if (cell.kind === 'unknown') ctx.setLineDash([Math.max(1, size * .06), Math.max(1, size * .06)])
      ctx.stroke()
      ctx.restore()
    }
    this.stats = { renderer: 'canvas', points: this.cells.length, diamonds: this.diamonds.length,
      visiblePoints: this.hits.length, drawMs: performance.now() - started }
    if (this.rankOneCanvas) {
      if (this.rankOneCanvas.width !== width || this.rankOneCanvas.height !== height) {
        this.rankOneCanvas.width = width; this.rankOneCanvas.height = height
      }
      Object.assign(this.rankOneCanvas.style, { width: `${viewport.x}px`, height: `${viewport.y}px` })
      L.DomUtil.setPosition(this.rankOneCanvas, map.containerPointToLayerPoint([0, 0]))
      this.stopRankOneAnimation()
      this.drawRankOne(performance.now())
      this.animateRankOne()
    }
  },
})
