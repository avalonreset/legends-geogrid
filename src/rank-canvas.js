import L from 'leaflet'
import { OCTAGON_CUT, STOP_SIGN_SCALE, DIAMOND_HALF, HONEYCOMB_SHAPES, honeycombLayers, honeycombOutline,
  honeycombNest, honeycombRotation, honeycombVertices, premultipliedMix, traceTerritoryRing, flattenTerritoryRing,
  pointInRings, mercatorZoom0 } from './map-geometry.js'
import { CARTOGRAPHIC, innerShapeburstStrokes, cubicBezierEase, masterTierForRank, DOMINANCE_TIERS, CONTESTED_EDGE, dominanceTierAtAllowed, rankAtPointAllowed } from './cartographic.js'

const escapeText = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])

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

// Honeycomb halos keep the same color stops, measured along each shape's own outline
// (a polygon distance metric) so the glow follows hexagons, triangles and the marker star.
let honeycombHalos
function honeycombHalo(layer, rot) {
  honeycombHalos ||= new Map()
  const key = `${layer}:${rot}`
  if (honeycombHalos.has(key)) return honeycombHalos.get(key)
  const n = 192, canvas = document.createElement('canvas')
  canvas.width = canvas.height = n
  const g = canvas.getContext('2d'), img = g.createImageData(n, n)
  const outline = honeycombOutline(layer, rot)
  const P = outline.map(([a, r]) => [r * Math.cos(a * Math.PI / 180), r * Math.sin(a * Math.PI / 180)])
  const a0 = outline[0][0] * Math.PI / 180, step = 2 * Math.PI / outline.length
  const stops = layer === 'marker'
    ? [[0, [0, 255, 255, 0]], [.40, [0, 255, 255, 0]], [.48, [175, 255, 255, .92]],
      [.58, [0, 255, 255, .48]], [.82, [0, 255, 255, 0]], [1, [0, 255, 255, 0]]]
    : [[0, [0, 255, 255, 0]], [.34, [0, 255, 255, 0]], [.48, [150, 255, 255, .85]],
      [.64, [0, 255, 255, .55]], [1, [0, 255, 255, 0]]]
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
    const dx = (x - n / 2 + .5) / (n / 2), dy = -(y - n / 2 + .5) / (n / 2)
    const r = Math.hypot(dx, dy)
    const th = (((Math.atan2(dy, dx) - a0) % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI) + a0
    const i0 = Math.floor((th - a0) / step) % outline.length
    const A = P[i0], B = P[(i0 + 1) % outline.length], D = [B[0] - A[0], B[1] - A[1]]
    const m = r / ((A[0] * D[1] - A[1] * D[0]) / (Math.cos(th) * D[1] - Math.sin(th) * D[0]))
    if (m >= 1) continue
    let s = 0
    while (m > stops[s + 1][0]) s++
    const [r0, c0] = stops[s], [r1, c1] = stops[s + 1], t = (m - r0) / (r1 - r0)
    const i = (y * n + x) * 4
    for (let ch = 0; ch < 4; ch++) img.data[i + ch] = (c0[ch] + (c1[ch] - c0[ch]) * t) * (ch < 3 ? 1 : 255)
  }
  g.putImageData(img, 0, 0)
  honeycombHalos.set(key, canvas)
  return canvas
}
const rgbaOf = (color, opacity) => /^#[0-9a-f]{6}$/i.test(color || '')
  ? [1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16) / 255).concat(opacity ?? 1) : [0, 0, 0, 0]
const cssOf = c => `rgba(${Math.round(c[0] * 255)},${Math.round(c[1] * 255)},${Math.round(c[2] * 255)},${c[3].toFixed(3)})`
function tracePolygon(ctx, vertices) {
  vertices.forEach(([x, y], i) => ctx[i ? 'lineTo' : 'moveTo'](x, y))
  ctx.closePath()
}
function barycentric(x, y, A, B, C) {
  const den = (B[1] - C[1]) * (A[0] - C[0]) + (C[0] - B[0]) * (A[1] - C[1])
  const w1 = ((B[1] - C[1]) * (x - C[0]) + (C[0] - B[0]) * (y - C[1])) / den
  const w2 = ((C[1] - A[1]) * (x - C[0]) + (A[0] - C[0]) * (y - C[1])) / den
  return [w1, w2, 1 - w1 - w2]
}
function rasterTriangle(buffer, width, height, V, colorAt) {
  const x0 = Math.max(0, Math.floor(Math.min(V[0][0], V[1][0], V[2][0])))
  const x1 = Math.min(width - 1, Math.ceil(Math.max(V[0][0], V[1][0], V[2][0])))
  const y0 = Math.max(0, Math.floor(Math.min(V[0][1], V[1][1], V[2][1])))
  const y1 = Math.min(height - 1, Math.ceil(Math.max(V[0][1], V[1][1], V[2][1])))
  for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
    const w = barycentric(x + .5, y + .5, V[0], V[1], V[2])
    if (w[0] < -1e-6 || w[1] < -1e-6 || w[2] < -1e-6) continue
    const c = colorAt(w)
    if (c[3] <= 0) continue
    const i = (y * width + x) * 4
    buffer[i] = c[0] * 255; buffer[i + 1] = c[1] * 255; buffer[i + 2] = c[2] * 255; buffer[i + 3] = c[3] * 255
  }
}

// One viewport bitmap replaces thousands of individually positioned SVG nodes.
// Geographic coordinates and evidence stay unchanged; hover uses the same shapes.
export const RankCanvasLayer = L.Layer.extend({
  initialize({ onSelect, onHoverLeader = null, onSelectLeader = null, onDoubleClickLeader = null }) {
    this.onSelect = onSelect
    this.onHoverLeader = onHoverLeader
    this.onSelectLeader = onSelectLeader
    this.onDoubleClickLeader = onDoubleClickLeader
    this.cells = []
    this.diamonds = []
    this.territories = []
    this.seams = []
    this.focus = null
    this.hoverSeam = null
    this.seamFrame = 0
    this.hoverLeaderId = null
    this.hoverMix = 0
    this.leaderWeights = new Map()
    this.hoverAnimFrame = 0
    this.hoverLastTime = 0
    this.hoverTween = null
    this.hoverTierId = null
    this.tierWeights = new Map()
    this.hoverRank = null
    this.lastScale = 0
    this.lastOrigin = null
    this.shapeburstCache = new WeakMap()
    this.spacing = 0
    this.stepPx = 0
    this.hits = []
    this.frame = 0
    this.focusIndex = -1
    this.honeycomb = null
    this.honeycombData = null
    this.honeycombGlow = null
    this.landMaskRaw = null
    this.landMaskProjected = null
    this.campaignOverlay = null
    this.keywordOverlay = null
    this.campaignSeamAnimFrame = 0
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
    this.seamTooltip = L.tooltip({ direction: 'top', offset: [0, -12], className: 'seam-tooltip', opacity: 1 })
    this.queueDraw = () => {
      if (!this.frame) this.frame = requestAnimationFrame(() => { this.frame = 0; this.draw() })
    }
    this.hover = event => {
      const hit = this.pointAllowedAt(event.containerPoint) ? this.hitAt(event.containerPoint) : null
      // A border between unlike leaders explains itself: both endpoints and their head-to-head ranks.
      const seam = hit ? null : this.seamAt(event.containerPoint)
      this.setHoverSeam(seam, event.containerPoint)
      const hasTectonic = Boolean(this.territories?.some(t => t.tectonic))
      const near = hit || this.nearCellAt(event.containerPoint)
      // Rank Topography: smooth master-tier hover + exact interpolated rank at cursor.
      const topoRank = (!seam && this.elevation?.levels?.length && this.elevation.mode !== 'scalar' && typeof this.elevation.bandStyle !== 'function')
        ? this.rankAtPoint(event.containerPoint) : null
      const focusTopoRank = (!seam && !topoRank && this.focus?.elevation?.levels?.length)
        ? this.rankAtPoint(event.containerPoint, this.focus.elevation) : null
      const cursorRank = topoRank || focusTopoRank
      // Local Leaders relief: the territory polygon itself is hoverable, not only pin cells.
      // Clip-aware via territoryAt; resolved even without relief so flat tectonic
      // territories (contours off) still get polygon-wide hover.
      const terrLeader = (!seam && !cursorRank && !this.focus?.elevation?.levels?.length)
        ? this.territoryAt(event.containerPoint) : null
      // hit is clip-guarded across every view via pointAllowedAt, and
      // nearCellAt applies the same land and study-circle clips, so neither
      // can fire over open water or outside the study circle.
      const nextLeader = hasTectonic
        ? (seam || this.focus?.elevation?.levels?.length ? null : hit?.leaderId || terrLeader || null)
        : (seam ? null : near?.leaderId || terrLeader || null)
      if (this.onHoverLeader && nextLeader !== this.hoverLeaderId) {
        this.onHoverLeader(nextLeader)
      }
      this.setHoverTier(cursorRank ? masterTierForRank(cursorRank.rank)?.id || null : null)
      this.hoverRank = cursorRank?.rank ?? null
      if (cursorRank) {
        const tier = masterTierForRank(cursorRank.rank)
        const base = hit ? `${hit.label} · ` : ''
        this.hoverId = hit?.id ?? '__topo__'
        this.hoverWasTopo = true
        this.tooltip.setLatLng(event.latlng).setContent(`${base}Topography #${cursorRank.rank} · ${tier ? tier.label : ''}`).addTo(map)
        map.getContainer().style.cursor = hit || nextLeader ? 'pointer' : ''
        return
      }
      if (!hit && terrLeader && this.leaderRelief) {
        const tier = this.dominanceTierAt(event.containerPoint, terrLeader)
        if (tier) {
          const baseLabel = this.cells?.find(c => (c.winnerId || c.leaderId) === terrLeader)?.leaderName || terrLeader
          this.hoverId = '__relief__'
          this.hoverWasTopo = false
          this.tooltip.setLatLng(event.latlng).setContent(`${escapeText(baseLabel)} · ${tier.label}`).addTo(map)
          map.getContainer().style.cursor = hit || nextLeader ? 'pointer' : ''
          return
        }
      }
      if (hit?.id === this.hoverId) {
        // Refresh dominance tier as cursor moves across relief rings within one cell.
        // Leaving topography on the same cell restores the plain cell tooltip.
        if (hit && (this.hoverWasTopo || (this.leaderRelief && hit.leaderId))) this.showTooltip(hit, event.containerPoint)
        this.hoverWasTopo = false
        map.getContainer().style.cursor = hit || nextLeader ? 'pointer' : ''
        return
      }
      this.hideTooltip()
      if (hit) this.showTooltip(hit, event.containerPoint)
      map.getContainer().style.cursor = hit || nextLeader ? 'pointer' : ''
    }
    this.click = event => {
      const detail = event.originalEvent?.detail || 1
      const hit = this.pointAllowedAt(event.containerPoint) ? this.hitAt(event.containerPoint) : null
      if (detail >= 2 && this.onDoubleClickLeader) {
        const leaderId = hit?.leaderId || this.territoryAt(event.containerPoint)
        if (leaderId) return
      }
      if (hit) { this.onSelect(hit.id); return }
      if (!this.onSelectLeader) return
      const leaderId = this.territoryAt(event.containerPoint)
      this.onSelectLeader(leaderId || null)
    }
    this.dblclick = event => {
      if (!this.onDoubleClickLeader) return
      const hit = this.pointAllowedAt(event.containerPoint) ? this.hitAt(event.containerPoint) : null
      const leaderId = hit?.leaderId || this.territoryAt(event.containerPoint)
      if (!leaderId) return
      L.DomEvent.stop(event)
      this.onDoubleClickLeader(leaderId)
    }
    this.hide = () => {
      this.hideTooltip()
      this.setHoverSeam(null)
    }
    this.mouseOut = () => {
      this.hideTooltip()
      this.setHoverSeam(null)
      this.setHoverTier(null)
      this.hoverRank = null
      if (this.onHoverLeader && this.hoverLeaderId) this.onHoverLeader(null)
    }
    this.onCameraChange = () => {
      if (map._smoothZooming) {
        if (this.frame) { cancelAnimationFrame(this.frame); this.frame = 0 }
        this.draw()
      } else {
        this.queueDraw()
      }
    }
    map.on('move zoom resize', this.onCameraChange)
    map.on('movestart zoomstart', this.hide)
    map.on('mouseout', this.mouseOut)
    map.on('mousemove', this.hover)
    map.on('click', this.click)
    map.on('dblclick', this.dblclick)
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
    cancelAnimationFrame(this.hoverAnimFrame)
    cancelAnimationFrame(this.seamFrame)
    cancelAnimationFrame(this.campaignSeamAnimFrame)
    this.seamFrame = 0
    this.campaignSeamAnimFrame = 0
    this.hoverSeam = null
    this.seamTooltip?.remove()
    this.stopRankOneAnimation()
    document.removeEventListener('visibilitychange', this.rankOneVisibility)
    this.motionPreference.removeEventListener('change', this.rankOneVisibility)
    map.off('move zoom resize', this.onCameraChange)
    map.off('movestart zoomstart', this.hide)
    map.off('mouseout', this.mouseOut)
    map.off('mousemove', this.hover)
    map.off('click', this.click)
    map.off('dblclick', this.dblclick)
    map.getContainer().removeEventListener('keydown', this.keydown, true)
    this.hideTooltip()
    this.canvas.remove()
    this.rankOneCanvas.remove()
  },
  setData(cells, diamonds, spacing, translucent, blendBoundary = null, territories = [], clipTerritories = false, hideDots = false) {
    this.hideTooltip()
    this.cells = cells
    this.diamonds = diamonds
    this.territories = territories
    this.seams = territories?.seams?.length ? territories.seams : (this.campaignOverlay?.seams || [])
    this.setHoverSeam(null)
    if (this.clipTerritories !== clipTerritories) {
      if (this.canvas) this.canvas.width = this.canvas.width
      if (this.rankOneCanvas) this.rankOneCanvas.width = this.rankOneCanvas.width
    }
    this.clipTerritories = clipTerritories
    this.hideDots = !!hideDots
    this.spacing = spacing
    this.translucent = translucent
    this.blendBoundary = blendBoundary
    this.focusIndex = -1
    this.honeycombData = this.honeycomb ? this.buildHoneycomb(cells) : null
    this.draw()
  },

  // Swap only the territory outlines and seams (contested ground animation frames).
  setTerritories(territories) {
    this.territories = territories || []
    this.seams = territories?.seams || []
    if (this.hoverSeam) {
      this.hoverSeam = this.seams.find(s => s.aIdx === this.hoverSeam.aIdx && s.bIdx === this.hoverSeam.bIdx) || null
      if (!this.hoverSeam) this.seamTooltip?.remove()
    }
    this.draw()
  },
  // Business focus: { leaderId, color, plateau, reach, rank2: Set, rank3: Set } or null.
  setFocus(focus, redraw = true) {
    this.focus = focus || null
    if (redraw) this.draw()
  },
  // Rankings topographic elevation: { levels, depth } or null.
  setElevation(elevation, redraw = true) {
    this.elevation = elevation || null
    if (redraw) this.draw()
  },
  // Local Leaders internal Fortress Core relief: Map<leaderId, Array<{ tier, parts }>> or null.
  setLeaderRelief(relief, redraw = true) {
    this.leaderRelief = relief || null
    if (redraw) this.draw()
  },
  // Campaigns overlays: { holdPlateau, thinHoldParts, fortressRegions, detachedRegions, serviceGapRegion, seams, animateSeams, dimRelief, isolateLayer, selectedPlayId, selectedAvoidId } or null.
  setCampaignOverlay(overlay, redraw = true) {
    this.campaignOverlay = overlay || null
    if (overlay?.seams?.length) this.seams = overlay.seams
    if (redraw) this.draw()
  },
  // Keyword stuffing overlays: { primaryTop10Parts, inheritIds } or null.
  setKeywordOverlay(overlay, redraw = true) {
    this.keywordOverlay = overlay || null
    if (redraw) this.draw()
  },
  // Real coastline land polygons: Array<{ outer: [[lng, lat], ...], holes: [...] }> or null.
  setLandMask(polygons, redraw = true) {
    const next = Array.isArray(polygons) && polygons.length ? polygons : null
    if (this.landMaskRaw === next) {
      if (redraw) this.draw()
      return
    }
    this.landMaskRaw = next
    this.landMaskProjected = next ? next.map(poly => {
      const rings = []
      const projectRing = ring => ring.map(([lng, lat]) => mercatorZoom0([lat, lng]))
      if (Array.isArray(poly?.outer) && poly.outer.length >= 3) rings.push(projectRing(poly.outer))
      if (Array.isArray(poly?.holes)) {
        for (const hole of poly.holes) if (Array.isArray(hole) && hole.length >= 3) rings.push(projectRing(hole))
      }
      return rings
    }).filter(rings => rings.length > 0) : null
    if (redraw) this.draw()
  },
  buildLandPath(scale, origin) {
    if (!this.landMaskProjected?.length) return null
    if (typeof Path2D === 'function') {
      const path = new Path2D()
      for (const poly of this.landMaskProjected) {
        for (const ring of poly) {
          if (ring.length < 3) continue
          path.moveTo(ring[0].x * scale - origin.x, ring[0].y * scale - origin.y)
          for (let i = 1; i < ring.length; i++) {
            path.lineTo(ring[i].x * scale - origin.x, ring[i].y * scale - origin.y)
          }
          path.closePath()
        }
      }
      return path
    }
    return true
  },
  traceLandPath(ctx, scale, origin) {
    ctx.beginPath()
    for (const poly of this.landMaskProjected || []) {
      for (const ring of poly) {
        if (ring.length < 3) continue
        ctx.moveTo(ring[0].x * scale - origin.x, ring[0].y * scale - origin.y)
        for (let i = 1; i < ring.length; i++) {
          ctx.lineTo(ring[i].x * scale - origin.x, ring[i].y * scale - origin.y)
        }
        ctx.closePath()
      }
    }
  },
  clipLand(ctx, landPath, scale, origin) {
    if (!landPath) return
    if (landPath === true) {
      this.traceLandPath(ctx, scale, origin)
      ctx.clip('evenodd')
    } else {
      ctx.clip(landPath, 'evenodd')
    }
  },
  strokeLandHairline(ctx, landPath, scale, origin) {
    if (!landPath) return
    ctx.save()
    if (this.blendBoundary?.length) {
      ctx.beginPath()
      this.blendBoundary.forEach((p, i) => ctx[i ? 'lineTo' : 'moveTo'](p.x * scale - origin.x, p.y * scale - origin.y))
      ctx.closePath()
      ctx.clip()
    }
    ctx.strokeStyle = 'rgba(125, 211, 252, 0.32)'
    ctx.lineWidth = 1.1
    ctx.lineJoin = 'round'
    if (landPath === true) {
      this.traceLandPath(ctx, scale, origin)
      ctx.stroke()
    } else {
      ctx.stroke(landPath)
    }
    ctx.restore()
  },
  screenFrame() {
    const zoom = this._map.getZoom(), scale = 2 ** zoom
    return { scale, origin: this._map.project(this._map.containerPointToLatLng([0, 0]), zoom) }
  },
  // Nearest unlike-leader border under the cursor, in zoom-0 projected space.
  seamAt({ x, y }) {
    if (!this.seams?.length || !this._map) return null
    const { scale, origin } = this.screenFrame()
    const px = (x + origin.x) / scale, py = (y + origin.y) / scale
    if (this.landMaskProjected?.length && !this.landMaskProjected.some(rings => pointInRings(rings, px, py))) return null
    if (this.clipTerritories && this.blendBoundary?.length && !pointInRings([this.blendBoundary], px, py)) return null
    const limit = Math.max(7, Math.min(16, (this.stepPx || 0) * .16)) / scale
    let best = null, bestDist = limit
    for (const seam of this.seams) {
      const dx = seam.p2.x - seam.p1.x, dy = seam.p2.y - seam.p1.y, len2 = dx * dx + dy * dy
      const t = len2 > 0 ? Math.max(0, Math.min(1, ((px - seam.p1.x) * dx + (py - seam.p1.y) * dy) / len2)) : 0
      const d = Math.hypot(px - seam.p1.x - dx * t, py - seam.p1.y - dy * t)
      if (d < bestDist) { bestDist = d; best = seam }
    }
    return best
  },
  setHoverSeam(seam, cursor = null) {
    const same = (seam && this.hoverSeam && seam.aIdx === this.hoverSeam.aIdx && seam.bIdx === this.hoverSeam.bIdx) || (!seam && !this.hoverSeam)
    this.hoverSeam = seam || null
    if (same && !cursor) return
    if (!seam) {
      this.seamTooltip?.remove()
      cancelAnimationFrame(this.seamFrame)
      this.seamFrame = 0
      if (!same) this.drawRankOne(performance.now())
      return
    }
    // Speak from the measured point nearer the cursor.
    const { scale, origin } = this.screenFrame()
    const px = cursor ? (cursor.x + origin.x) / scale : seam.mid.x, py = cursor ? (cursor.y + origin.y) / scale : seam.mid.y
    const fromA = Math.hypot(px - seam.a.x, py - seam.a.y) <= Math.hypot(px - seam.b.x, py - seam.b.y)
    const side = fromA ? 'A' : 'B'
    if (same && this.hoverSeamSide === side) return
    this.hoverSeamSide = side
    if (seam.campaignSeam) {
      const gapText = seam.gapRanks === 1 ? '1 rank from pack' : `${seam.gapRanks} ranks from pack`
      const rivalHold = Number.isFinite(seam.rankBatA) ? `#${seam.rankBatA}` : 'outside 30'
      this.seamTooltip.setLatLng(this._map.unproject([seam.mid.x, seam.mid.y], 0))
        .setContent(`<b>Flip seam:</b> ${escapeText(seam.nameA)} #${seam.rankAatHold} -> #${seam.rankAatSeam} (${gapText}).<br>Pack blocker: <b>${escapeText(seam.nameB)}</b> #${seam.rivalRankAtSeam} at seam (${rivalHold} at held pin).`)
        .addTo(this._map)
      this.drawRankOne(performance.now())
      this.animateSeam()
      return
    }
    const here = fromA ? seam.nameA : seam.nameB, there = fromA ? seam.nameB : seam.nameA
    const thereHere = fromA ? seam.rankBatA : seam.rankAatB, hereThere = fromA ? seam.rankAatB : seam.rankBatA
    const rank = value => Number.isFinite(value) ? `#${value}` : 'not ranked'
    const gap = seam.gapFrac > .005 ? `<small>Contested ground: ${Math.round(seam.gapFrac * 100)}% of the span between these two points.</small>` : ''
    this.seamTooltip.setLatLng(this._map.unproject([seam.mid.x, seam.mid.y], 0))
      .setContent(`<b>${escapeText(here)}</b> is #1 here (${escapeText(there)} ${rank(thereHere)}).<br>Adjacent point: <b>${escapeText(there)}</b> #1 (${escapeText(here)} ${rank(hereThere)}).${gap}`)
      .addTo(this._map)
    this.drawRankOne(performance.now())
    this.animateSeam()
  },
  animateSeam() {
    if (this.seamFrame || !this.hoverSeam || document.hidden || this.motionPreference?.matches) return
    this.seamFrame = requestAnimationFrame(time => {
      this.seamFrame = 0
      if (!this.hoverSeam) return
      this.drawRankOne(time)
      this.animateSeam()
    })
  },
  // Pulse both measured endpoints of the hovered border and mark the border span itself.
  drawSeamHighlight(ctx, time) {
    const seam = this.hoverSeam
    if (!seam || !this._map) return
    const { scale, origin } = this.screenFrame()
    const at = p => [p.x * scale - origin.x, p.y * scale - origin.y]
    const phase = this.motionPreference?.matches ? .5 : (time / 900) % 1
    const base = Math.max(5, (this.dotSize || 10) / 2 + 3)
    ctx.save()
    ctx.lineCap = 'round'
    const [x1, y1] = at(seam.p1), [x2, y2] = at(seam.p2)
    ctx.beginPath(); ctx.moveTo(...at(seam.a)); ctx.lineTo(x1, y1); ctx.moveTo(x2, y2); ctx.lineTo(...at(seam.b))
    ctx.strokeStyle = 'rgba(255,255,255,.55)'; ctx.lineWidth = 1.25; ctx.setLineDash([3, 4]); ctx.stroke()
    ctx.setLineDash([])
    for (const [x, y] of [[x1, y1], [x2, y2]]) {
      ctx.beginPath(); ctx.arc(x, y, 2.6, 0, Math.PI * 2)
      ctx.fillStyle = '#ffffff'; ctx.fill()
      ctx.strokeStyle = '#000000'; ctx.lineWidth = 1; ctx.stroke()
    }
    for (const p of [seam.a, seam.b]) {
      const [x, y] = at(p)
      ctx.beginPath(); ctx.arc(x, y, base, 0, Math.PI * 2)
      ctx.strokeStyle = 'rgba(0,0,0,.8)'; ctx.lineWidth = 3.5; ctx.globalAlpha = 1; ctx.stroke()
      ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 1.75; ctx.stroke()
      ctx.beginPath(); ctx.arc(x, y, base + 2 + phase * 9, 0, Math.PI * 2)
      ctx.globalAlpha = (1 - phase) * .8; ctx.lineWidth = 1.5; ctx.stroke()
    }
    ctx.restore()
  },
  // Drawn leader whose rendered territory contains the container point.
  territoryAt({ x, y }) {
    if (!this._map) return null
    const { scale, origin } = this.screenFrame()
    const px = (x + origin.x) / scale, py = (y + origin.y) / scale
    if (this.landMaskProjected?.length && !this.landMaskProjected.some(rings => pointInRings(rings, px, py))) return null
    if (this.clipTerritories && this.blendBoundary?.length && !pointInRings([this.blendBoundary], px, py)) return null
    for (const t of this.territories || []) {
      if (!t.tectonic) continue
      t.flat ||= t.rings.map(ring => flattenTerritoryRing(ring))
      if (pointInRings(t.flat, px, py)) return t.leaderId
    }
    return null
  },
  // Honeycomb studies draw the locked 12 -> 6 -> 3 layers. Square studies never set this.
  setHoneycomb(config) {
    this.honeycomb = config || null
  },
  buildHoneycomb(cells) {
    // Only the view lattice feeds the estimate layers. Nested-rung points never do.
    const nodes = cells.filter(c => c.honeycomb && !c.honeycomb.nested)
      .map(c => ({ a: c.honeycomb.a, b: c.honeycomb.b, x: c.x, y: c.y, cell: c,
        color: c.kind === 'ranked' ? rgbaOf(c.color, c.opacity) : [0, 0, 0, 0],
        won: !!c.dominant, failed: c.honeycomb.state === 'unknown' }))
    // Nested rungs: a measured refined point replaces every estimate within half its own spacing.
    const nested = cells.filter(c => c.honeycomb?.nested)
    const hex = honeycombNest(honeycombLayers(nodes, this.honeycomb.radius), nested.map(c => c.honeycomb))
    if (hex) hex.nested = nested.filter(c => c.dominant)
    return hex
  },
  honeycombUnitScale(hex) {
    // Match public v0.2.11 STOP_SIGN_SCALE (0.30 of finest spacing) across every real hexagon
    // so mixed-rung studies never balloon into chunky dots over the street map.
    let minScale = 1
    for (const c of this.cells) {
      const s = c.honeycomb?.scale
      if (s && s > 0 && s < minScale) minScale = s
    }
    return minScale
  },
  drawHoneycombEstimates(ctx, hex, scale, origin, S, visible, realR, line) {
    // Crisp, strictly smaller 3-sided triangles at Layer 2 centers (the hex equivalent of
    // public v0.2.11's smaller 4-sided gradient diamonds between 4 square-grid octagons).
    const r = realR * .58
    if (r < .6) return
    for (const e of hex.estimates[2]) {
      const [px, py] = hex.position(e.a, e.b), x = px * scale - origin.x, y = py * scale - origin.y
      if (!visible(x, y, r * 2)) continue
      // Alternate triangle orientation by parity so tips point cleanly toward the 3 real parents.
      const rot = (((e.a - e.b) % 3) + 3) % 3 === 0 && (((e.a % 3) + 3) % 3) === 1 ? 30 : 90
      ctx.beginPath()
      tracePolygon(ctx, honeycombVertices(x, y, r, 3, rot))
      ctx.lineWidth = Math.max(.4, line * .65)
      if (e.failed) {
        ctx.strokeStyle = 'rgba(225,184,105,.55)'; ctx.stroke(); continue
      }
      ctx.fillStyle = cssOf(e.color); ctx.fill()
      ctx.strokeStyle = `rgba(0,0,0,${(.6 * e.color[3]).toFixed(3)})`; ctx.stroke()
    }
  },
  // Blended sharp 6-point business star (rot 0 deg, inner 0.36): all 6 tips aim directly
  // at the 6 surrounding hexagons (0, 60, ..., 300 deg), blending 25% own / 75% the aimed
  // neighbor; 6 inner valleys blend half center plus a quarter of each adjacent tip.
  // Zero opaque black outline so the dark street grid shines through; when inspecting a rival,
  // stays distinct and luminous as the Precision Noir target-business anchor star.
  drawHoneycombMarker(ctx, hex, scale, origin, S, viewport, realR) {
    const [px, py] = hex.position(0, 0), x = px * scale - origin.x, y = py * scale - origin.y
    const r = realR * 1.55
    if (x + r < 0 || y + r < 0 || x - r > viewport.x || y - r > viewport.y) return
    const outline = honeycombVertices(x, y, r, 'marker', HONEYCOMB_SHAPES.marker.rot)
    const viewingTarget = this.honeycomb?.viewingTarget !== false
    const centerDotR = Math.max(1.35, Math.min(2.3, r * .21))
    if (!viewingTarget || !hex.center || hex.center.color[3] <= 0) {
      ctx.save()
      ctx.beginPath(); tracePolygon(ctx, outline)
      ctx.fillStyle = 'rgba(239,68,68,.28)'
      ctx.fill()
      ctx.strokeStyle = 'rgba(255,255,255,.85)'
      ctx.lineWidth = .95
      ctx.lineJoin = 'round'
      ctx.stroke()
      ctx.beginPath(); ctx.arc(x, y, centerDotR, 0, Math.PI * 2)
      ctx.fillStyle = 'rgba(255,255,255,.95)'
      ctx.fill()
      ctx.restore()
      return
    }
    const own = hex.center.color
    const tips = hex.markerColor(own), tipCount = tips.length, vertCount = outline.length, colors = []
    for (let k = 0; k < tipCount; k++) colors.push(tips[k], premultipliedMix([.5, .25, .25], [own, tips[k], tips[(k + 1) % tipCount]]))
    const dpr = Math.min(devicePixelRatio || 1, 2), pad = 2
    // Raster only the on-screen part of the star in device pixels.
    const bx = Math.max(0, Math.floor((x - r) * dpr) - pad), by = Math.max(0, Math.floor((y - r) * dpr) - pad)
    const bw = Math.min(Math.round(viewport.x * dpr), Math.ceil((x + r) * dpr) + pad) - bx
    const bh = Math.min(Math.round(viewport.y * dpr), Math.ceil((y + r) * dpr) + pad) - by
    if (bw > 0 && bh > 0) {
      this.markerCanvas ||= document.createElement('canvas')
      const off = this.markerCanvas
      if (off.width !== bw || off.height !== bh) { off.width = bw; off.height = bh }
      const octx = off.getContext('2d'), img = octx.createImageData(bw, bh)
      const local = ([vx, vy]) => [vx * dpr - bx, vy * dpr - by]
      const c0 = local([x, y])
      for (let i = 0; i < vertCount; i++) {
        const j = (i + 1) % vertCount
        rasterTriangle(img.data, bw, bh, [c0, local(outline[i]), local(outline[j])],
          w => premultipliedMix(w.map(v => Math.max(0, v)), [own, colors[i], colors[j]], .82))
      }
      octx.putImageData(img, 0, 0)
      ctx.drawImage(off, bx / dpr, by / dpr, bw / dpr, bh / dpr)
    }
    ctx.save()
    ctx.beginPath(); tracePolygon(ctx, outline)
    ctx.strokeStyle = 'rgba(255,255,255,.52)'
    ctx.lineWidth = .9
    ctx.lineJoin = 'round'
    ctx.stroke()
    ctx.beginPath(); ctx.arc(x, y, Math.max(1.2, centerDotR * .85), 0, Math.PI * 2)
    ctx.fillStyle = 'rgba(255,255,255,.92)'
    ctx.fill()
    ctx.restore()
  },
  honeycombGlowCells(hex, scale, origin, S, viewport, realR) {
    const out = [], config = this.honeycomb
    const add = (a, b, layer, rot, tips, strength = 1) => {
      const r = layer === 'marker' ? realR * 1.55 : realR
      const [px, py] = hex.position(a, b), x = px * scale - origin.x, y = py * scale - origin.y
      if (x < -r * 4 || y < -r * 4 || x > viewport.x + r * 4 || y > viewport.y + r * 4) return
      const e = (a + b / 2) / 3, n = Math.sqrt(3) / 2 * b / 3
      const tipScale = layer === 'marker' ? 1.0 : 1.04
      const haloScale = layer === 'marker' ? 1.02 : 1.15
      out.push({ x, y, p0: e * .37 + n * .23, halo: honeycombHalo(layer, rot), haloR: haloScale * r / .48, strength,
        corners: tips.map(t => [x + tipScale * r * Math.cos(t * Math.PI / 180), y - tipScale * r * Math.sin(t * Math.PI / 180)]),
        arm0: Math.max(2.6, Math.min(layer === 'marker' ? 10 : 12, (layer === 'marker' ? .26 : .35) * r)) })
    }
    if (config.marker && config.viewingTarget !== false && hex.glow.marker) add(0, 0, 'marker', HONEYCOMB_SHAPES.marker.rot, hex.glow.marker.tips)
    for (const { x, tips } of hex.glow.real) {
      if (config.marker && !x.a && !x.b) continue
      add(x.a, x.b, 1, HONEYCOMB_SHAPES[1].rot, tips, x.cell?.muted ? .15 : 1)
    }
    // Estimates never emit rank-one glints.
    for (const c of hex.nested || []) {
      add(c.honeycomb.a, c.honeycomb.b, 1, HONEYCOMB_SHAPES[1].rot, [], c.muted ? .15 : 1)
    }
    return out
  },
  drawHoneycombGlow(ctx, time, reduced, sparkle) {
    for (const c of this.honeycombGlow) {
      const still = reduced || c.haloR < 3
      const phase = still ? .25 : ((time / 3600 + c.p0) % 1 + 1) % 1
      const pulse = .5 - .5 * Math.cos(phase * Math.PI * 2)
      ctx.globalAlpha = c.strength * (.65 + pulse * .35)
      ctx.drawImage(c.halo, c.x - c.haloR, c.y - c.haloR, c.haloR * 2, c.haloR * 2)
      c.corners.forEach(([x, y], i) => {
        const twinkle = still ? .55 : Math.pow(.5 - .5 * Math.cos((phase + i * .381966) * Math.PI * 2), 3)
        const arm = c.arm0 * (.65 + twinkle * .55)
        ctx.globalAlpha = c.strength * (.06 + twinkle * .94)
        ctx.drawImage(sparkle, x - arm, y - arm, arm * 2, arm * 2)
      })
    }
    ctx.globalAlpha = 1
    return this.honeycombGlow.length
  },
  glowing() {
    return this.honeycombGlow ? this.honeycombGlow.some(c => c.haloR >= 3) : this.hits.some(cell => cell.dominant && cell.size >= 3)
  },
  // 200ms cubic-bezier(0.22, 1, 0.36, 1) hover tween for leaders and rank master tiers.
  beginHoverTween() {
    if (this.motionPreference?.matches) {
      this.hoverMix = this.hoverLeaderId ? 1 : 0
      this.leaderWeights.clear()
      if (this.hoverLeaderId) this.leaderWeights.set(this.hoverLeaderId, 1)
      this.tierWeights.clear()
      if (this.hoverTierId) this.tierWeights.set(this.hoverTierId, 1)
      this.hoverTween = null
      this.queueDraw()
      return
    }
    this.hoverTween = {
      started: performance.now(),
      fromMix: this.hoverMix || 0,
      fromLeaders: new Map(this.leaderWeights),
      fromTiers: new Map(this.tierWeights),
    }
    if (!this.hoverAnimFrame) this.hoverAnimFrame = requestAnimationFrame(t => this.stepHoverAnimation(t))
  },
  setHoverLeader(leaderId) {
    const next = leaderId || null
    if (this.hoverLeaderId === next) return
    this.hoverLeaderId = next
    if (next && !this.leaderWeights.has(next)) this.leaderWeights.set(next, 0)
    this.beginHoverTween()
  },
  setHoverTier(tierId) {
    const next = tierId || null
    if (this.hoverTierId === next) return
    this.hoverTierId = next
    if (next && !this.tierWeights.has(next)) this.tierWeights.set(next, 0)
    this.beginHoverTween()
  },
  stepHoverAnimation(now) {
    this.hoverAnimFrame = 0
    const tween = this.hoverTween
    if (!tween) return
    const raw = Math.max(0, Math.min(1, (now - tween.started) / CARTOGRAPHIC.hoverDurationMs))
    const e = cubicBezierEase(raw)
    const targetMix = this.hoverLeaderId ? 1 : 0
    this.hoverMix = tween.fromMix + (targetMix - tween.fromMix) * e
    const apply = (weights, from, activeId) => {
      const ids = new Set([...from.keys(), ...weights.keys(), ...(activeId ? [activeId] : [])])
      for (const id of ids) {
        const start = from.get(id) || 0
        const target = id === activeId ? 1 : 0
        const w = start + (target - start) * e
        if (target === 0 && w < .008) weights.delete(id); else weights.set(id, w)
      }
    }
    apply(this.leaderWeights, tween.fromLeaders, this.hoverLeaderId)
    apply(this.tierWeights, tween.fromTiers, this.hoverTierId)
    this.draw()
    if (raw < 1 && this._map) this.hoverAnimFrame = requestAnimationFrame(t => this.stepHoverAnimation(t))
    else this.hoverTween = null
  },
  containerToZoom0({ x, y }) {
    if (!this._map || !this.lastScale || !this.lastOrigin) return null
    return { x: (x + this.lastOrigin.x) / this.lastScale, y: (y + this.lastOrigin.y) / this.lastScale }
  },
  // Shared clip check: container point must sit on land and inside the
  // study circle when clipping applies. Pre-first-draw points stay allowed.
  pointAllowedAt(containerPoint) {
    const p = this.containerToZoom0(containerPoint)
    if (!p) return true
    if (this.landMaskProjected?.length && !this.landMaskProjected.some(rings => pointInRings(rings, p.x, p.y))) return false
    if (this.clipTerritories && this.blendBoundary?.length && !pointInRings([this.blendBoundary], p.x, p.y)) return false
    return true
  },
  // Exact interpolated rank band at cursor: smallest rank contour containing the point.
  // Coastline and study-circle clips run first: no rank over clipped water.
  rankAtPoint(containerPoint, elevation = this.elevation) {
    const levels = elevation?.levels
    if (!levels?.length) return null
    const p = this.containerToZoom0(containerPoint)
    if (!p) return null
    const hasLandMask = Boolean(this.landMaskProjected?.length)
    const insideLand = hasLandMask ? this.landMaskProjected.some(rings => pointInRings(rings, p.x, p.y)) : true
    const hasBoundary = Boolean(this.blendBoundary?.length)
    const insideBoundary = hasBoundary ? pointInRings([this.blendBoundary], p.x, p.y) : true
    if (!rankAtPointAllowed({ point: p, hasLandMask, insideLand, clipTerritories: Boolean(this.clipTerritories), hasBoundary, insideBoundary })) return null
    const sorted = [...levels].filter(l => l.parts?.length).sort((a, b) => a.rank - b.rank)
    for (const level of sorted) {
      for (const part of level.parts) {
        const rings = part.rings.map(r => flattenTerritoryRing(r))
        if (pointInRings(rings, p.x, p.y)) return { rank: level.rank }
      }
    }
    return null
  },
  // Fortress Core dominance tier at cursor for a leader (innermost relief ring wins).
  // Clip-aware: null outside the leader territory, off land, or under draped
  // focus topography. Contested Edge only strictly inside the territory.
  dominanceTierAt(containerPoint, leaderId) {
    if (!leaderId || !this.leaderRelief) return null
    const p = this.containerToZoom0(containerPoint)
    if (!p) return null
    const draped = Boolean(this.focus?.elevation?.levels?.length)
    const hasLandMask = Boolean(this.landMaskProjected?.length)
    const insideLand = hasLandMask ? this.landMaskProjected.some(rings => pointInRings(rings, p.x, p.y)) : true
    const insideTerritory = Boolean(this.territories?.some(t => t.tectonic && t.leaderId === leaderId && pointInRings((t.flat ||= t.rings.map(r => flattenTerritoryRing(r))), p.x, p.y)))
    const hasBoundary = Boolean(this.blendBoundary?.length)
    const insideBoundary = hasBoundary ? pointInRings([this.blendBoundary], p.x, p.y) : true
    if (!dominanceTierAtAllowed({ point: p, draped, hasLandMask, insideLand, insideTerritory, clipTerritories: Boolean(this.clipTerritories), hasBoundary, insideBoundary })) return null
    const tiers = this.leaderRelief.get(leaderId)
    if (!tiers?.length) return CONTESTED_EDGE
    const sorted = [...tiers].sort((a, b) => b.tier - a.tier)
    for (const rt of sorted) {
      for (const part of rt.parts) {
        const rings = part.rings.map(r => flattenTerritoryRing(r))
        if (pointInRings(rings, p.x, p.y)) return DOMINANCE_TIERS[rt.tier] || CONTESTED_EDGE
      }
    }
    return CONTESTED_EDGE
  },
  // Cached Path2D in screen space for contour parts (rebuilt when scale/origin changes).
  buildScreenPath(parts, scale, origin) {
    const cacheKey = `${Math.round(scale * 1000)}:${Math.round(origin.x)}:${Math.round(origin.y)}`
    let byKey = this.shapeburstCache.get(parts)
    if (byKey?.key === cacheKey) return byKey.path
    const path = new Path2D()
    const sink = {
      moveTo: (x, y) => path.moveTo(x * scale - origin.x, y * scale - origin.y),
      lineTo: (x, y) => path.lineTo(x * scale - origin.x, y * scale - origin.y),
      quadraticCurveTo: (cx, cy, x, y) => path.quadraticCurveTo(cx * scale - origin.x, cy * scale - origin.y, x * scale - origin.x, y * scale - origin.y),
      closePath: () => path.closePath(),
    }
    for (const part of parts) for (const ring of part.rings) traceTerritoryRing(ring, sink)
    this.shapeburstCache.set(parts, { key: cacheKey, path })
    return path
  },
  buildRingsPath(rings, scale, origin) {
    const path = new Path2D()
    const sink = {
      moveTo: (x, y) => path.moveTo(x * scale - origin.x, y * scale - origin.y),
      lineTo: (x, y) => path.lineTo(x * scale - origin.x, y * scale - origin.y),
      quadraticCurveTo: (cx, cy, x, y) => path.quadraticCurveTo(cx * scale - origin.x, cy * scale - origin.y, x * scale - origin.x, y * scale - origin.y),
      closePath: () => path.closePath(),
    }
    for (const ring of rings) traceTerritoryRing(ring, sink)
    return path
  },
  // Inward-only shapeburst: clip to shape, then incremental inward strokes (0% exterior bleed).
  drawInnerShapeburst(ctx, clipPath, color, { widthPx = CARTOGRAPHIC.innerWidth, maxOpacity = CARTOGRAPHIC.innerOpacity, dim = 1 } = {}) {
    if (!clipPath || widthPx <= 0 || maxOpacity <= 0 || dim <= 0) return
    const strokes = innerShapeburstStrokes(widthPx, maxOpacity * dim)
    if (!strokes.length) return
    ctx.save()
    ctx.clip(clipPath, 'evenodd')
    ctx.lineJoin = 'round'
    ctx.strokeStyle = color
    for (const s of strokes) {
      ctx.globalAlpha = s.alpha
      ctx.lineWidth = s.lineWidth
      ctx.stroke(clipPath)
    }
    ctx.restore()
  },
  nearCellAt({ x, y }) {
    const halfStep = (this.stepPx || 0) * .54
    if (!halfStep) return null
    const p = this.containerToZoom0({ x, y })
    if (p) {
      if (this.landMaskProjected?.length && !this.landMaskProjected.some(rings => pointInRings(rings, p.x, p.y))) return null
      if (this.clipTerritories && this.blendBoundary?.length && !pointInRings([this.blendBoundary], p.x, p.y)) return null
    }
    let best = null, bestDist = Infinity
    for (const cell of this.hits) {
      const dx = Math.abs(x - cell.sx), dy = Math.abs(y - cell.sy)
      if (dx <= halfStep && dy <= halfStep) {
        const d = dx * dx + dy * dy
        if (d < bestDist) { bestDist = d; best = cell }
      }
    }
    return best
  },
  hideTooltip() {
    if (this.tooltip) this.tooltip.remove()
    this.hoverId = null
    this.hoverWasTopo = false
  },
  showTooltip(cell, containerPoint = null) {
    this.hoverId = cell.id
    let content = cell.label
    if (containerPoint && cell.leaderId && this.leaderRelief && !this.focus?.elevation?.levels?.length) {
      const tier = this.dominanceTierAt(containerPoint, cell.leaderId)
      if (tier) content = `${content} · ${tier.label}`
    }
    this.tooltip.setLatLng([cell.lat, cell.lng]).setContent(content).addTo(this._map)
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
        !this.glowing()) return
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
    ctx.save()
    if (this.clipTerritories && this.blendBoundary?.length) {
      const scale = 2 ** this._map.getZoom()
      const origin = this._map.project(this._map.containerPointToLatLng([0, 0]), this._map.getZoom())
      ctx.beginPath()
      this.blendBoundary.forEach((p, i) => ctx[i ? 'lineTo' : 'moveTo'](p.x * scale - origin.x, p.y * scale - origin.y))
      ctx.closePath()
      ctx.clip()
    }
    const reduced = this.motionPreference?.matches
    const sprites = getDominanceSprites()
    let highlighted = this.hideDots ? 0 : this.honeycombGlow ? this.drawHoneycombGlow(ctx, time, reduced, sprites.sparkle) : 0
    for (const cell of (this.hideDots || this.honeycomb || this.honeycombGlow) ? [] : this.hits) {
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
    ctx.restore()
    this.drawAnimatedCampaignSeams(ctx, time)
    this.drawSeamHighlight(ctx, time)
    if (this.stats) Object.assign(this.stats, {
      highlightedPoints: highlighted, shimmerDrawMs: performance.now() - started,
      shimmerAnimating: !document.hidden && !reduced && this.glowing(),
    })
  },
  animateCampaignSeams() {
    if (this.campaignSeamAnimFrame || !this.campaignOverlay?.animateSeams || !this.campaignOverlay?.seams?.length ||
        document.hidden || this.motionPreference?.matches) return
    this.campaignSeamAnimFrame = requestAnimationFrame(time => {
      this.campaignSeamAnimFrame = 0
      if (!this.campaignOverlay?.animateSeams) return
      this.drawRankOne(time)
      this.animateCampaignSeams()
    })
  },
  // Chain adjacent campaign seam segments into continuous polylines and draw smooth contoured curves
  // weighted by rank-gap proximity (rank 4 = bold bright gold 2.8px, rank 5 = sleek warm amber 1.7px).
  buildSmoothSeamChains(seams, scale, origin, filterFn = null) {
    const groups = new Map()
    const keyOf = p => `${Math.round(p.x * 100)},${Math.round(p.y * 100)}`
    for (const seam of seams || []) {
      if (filterFn && !filterFn(seam)) continue
      const bucketKey = `${seam.gapRanks === 1 ? 'r4' : 'r5'}:${seam.playId || ''}`
      if (!groups.has(bucketKey)) groups.set(bucketKey, { gapRanks: seam.gapRanks, playId: seam.playId, segs: [] })
      groups.get(bucketKey).segs.push({
        a: { x: seam.p1.x * scale - origin.x, y: seam.p1.y * scale - origin.y },
        b: { x: seam.p2.x * scale - origin.x, y: seam.p2.y * scale - origin.y },
        ka: keyOf(seam.p1),
        kb: keyOf(seam.p2),
      })
    }
    const chains = []
    for (const grp of groups.values()) {
      const adj = new Map()
      grp.segs.forEach((s, idx) => {
        if (!adj.has(s.ka)) adj.set(s.ka, [])
        if (!adj.has(s.kb)) adj.set(s.kb, [])
        adj.get(s.ka).push({ idx, otherKey: s.kb, pt: s.b })
        adj.get(s.kb).push({ idx, otherKey: s.ka, pt: s.a })
      })
      const used = new Uint8Array(grp.segs.length)
      for (let i = 0; i < grp.segs.length; i++) {
        if (used[i]) continue
        used[i] = 1
        const s = grp.segs[i]
        const pts = [s.a, s.b]
        let headKey = s.ka, tailKey = s.kb
        const extend = (startKey, pushFront) => {
          let cur = startKey
          while (true) {
            const next = (adj.get(cur) || []).find(n => !used[n.idx])
            if (!next) break
            used[next.idx] = 1
            if (pushFront) pts.unshift(next.pt); else pts.push(next.pt)
            cur = next.otherKey
          }
        }
        extend(tailKey, false)
        extend(headKey, true)
        chains.push({ gapRanks: grp.gapRanks, playId: grp.playId, pts })
      }
    }
    return chains
  },
  traceSmoothPolyline(ctx, pts) {
    if (pts.length < 2) return
    ctx.beginPath()
    ctx.moveTo(pts[0].x, pts[0].y)
    if (pts.length === 2) {
      ctx.lineTo(pts[1].x, pts[1].y)
      return
    }
    for (let i = 1; i < pts.length - 1; i++) {
      const mx = (pts[i].x + pts[i + 1].x) / 2
      const my = (pts[i].y + pts[i + 1].y) / 2
      ctx.quadraticCurveTo(pts[i].x, pts[i].y, mx, my)
    }
    const last = pts[pts.length - 1]
    ctx.lineTo(last.x, last.y)
  },
  drawSmoothCampaignSeams(ctx, seams, scale, origin, { ov, pulse = 1 } = {}) {
    if (!seams?.length) return
    const iso = ov?.isolateLayer || null
    const seamBaseAlpha = iso && iso !== 'seams' ? .28 : 1
    const chains = this.buildSmoothSeamChains(seams, scale, origin)
    ctx.save()
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.setLineDash([])
    for (const chain of chains) {
      const dimPlay = (ov?.selectedPlayId && chain.playId !== ov.selectedPlayId) || ov?.selectedAvoidId ? .28 : 1
      const isRank4 = chain.gapRanks === 1
      const width = isRank4 ? 2.8 : 1.7
      const color = isRank4 ? '#ffe082' : '#ffb020'
      const alpha = (isRank4 ? .96 : .82) * seamBaseAlpha * dimPlay * pulse
      this.traceSmoothPolyline(ctx, chain.pts)
      ctx.strokeStyle = 'rgba(0,0,0,0.72)'
      ctx.globalAlpha = alpha * .85
      ctx.lineWidth = width + 2.4
      ctx.stroke()
      ctx.strokeStyle = color
      ctx.globalAlpha = alpha
      ctx.lineWidth = width
      ctx.stroke()
    }
    ctx.restore()
  },
  drawAnimatedCampaignSeams(ctx, time) {
    const ov = this.campaignOverlay
    if (!ov?.animateSeams || !ov.seams?.length || !this._map) return
    const { scale, origin } = this.screenFrame()
    const reduced = this.motionPreference?.matches
    const pulse = reduced ? 1 : .82 + .18 * Math.sin((time || 0) / 380)
    this.drawSmoothCampaignSeams(ctx, ov.seams, scale, origin, { ov, pulse })
  },
  // Draw crimson 45-degree hairline hatch inside a clipped polygon region (zero glow, zero fill).
  drawHatch(ctx, parts, sink, { color = '#e3232d', pitch = 6, alpha = .40, strokeAlpha = .72, viewport } = {}) {
    if (!parts?.length) return
    ctx.save()
    ctx.beginPath()
    for (const part of parts) for (const ring of part.rings) traceTerritoryRing(ring, sink)
    ctx.save()
    ctx.clip('evenodd')
    const w = viewport?.x || 1400, h = viewport?.y || 900
    const span = w + h
    ctx.beginPath()
    for (let d = -h; d < span; d += pitch) {
      ctx.moveTo(d, 0)
      ctx.lineTo(d - h, h)
    }
    ctx.strokeStyle = color
    ctx.globalAlpha = alpha
    ctx.lineWidth = 1
    ctx.setLineDash([])
    ctx.stroke()
    ctx.restore()
    ctx.beginPath()
    for (const part of parts) for (const ring of part.rings) traceTerritoryRing(ring, sink)
    ctx.strokeStyle = color
    ctx.globalAlpha = strokeAlpha
    ctx.lineWidth = 1
    ctx.setLineDash([])
    ctx.stroke()
    ctx.restore()
  },
  getStipplePattern(ctx, color = '#8a8a8a') {
    this._stipplePatterns ||= new Map()
    if (this._stipplePatterns.has(color)) return this._stipplePatterns.get(color)
    const tile = document.createElement('canvas')
    tile.width = tile.height = 8
    const tctx = tile.getContext('2d')
    tctx.fillStyle = color
    tctx.beginPath()
    tctx.arc(2, 2, 1.1, 0, Math.PI * 2)
    tctx.arc(6, 6, 1.1, 0, Math.PI * 2)
    tctx.fill()
    const pat = ctx.createPattern(tile, 'repeat')
    this._stipplePatterns.set(color, pat)
    return pat
  },
  drawStipple(ctx, parts, sink, { color = '#8a8a8a', fillAlpha = .25, strokeAlpha = .7, dash = [4, 4] } = {}) {
    if (!parts?.length) return
    ctx.save()
    ctx.beginPath()
    for (const part of parts) for (const ring of part.rings) traceTerritoryRing(ring, sink)
    const pattern = this.getStipplePattern(ctx, color)
    if (pattern) {
      ctx.fillStyle = pattern
      ctx.globalAlpha = fillAlpha
      ctx.fill('evenodd')
    }
    ctx.strokeStyle = color
    ctx.globalAlpha = strokeAlpha
    ctx.lineWidth = 1
    ctx.setLineDash(dash)
    ctx.stroke()
    ctx.restore()
  },
  drawMapLabelChip(ctx, x, y, text, { stroke = '#333333', color = '#e6e6e6', alpha = 1 } = {}) {
    if (!text) return
    ctx.save()
    ctx.globalAlpha = alpha
    ctx.font = '600 10px "DM Sans", system-ui, sans-serif'
    const padX = 6, h = 18
    const tw = ctx.measureText(text).width
    const w = tw + padX * 2
    const rx = Math.round(x - w / 2), ry = Math.round(y - h / 2)
    ctx.fillStyle = 'rgba(12, 12, 12, 0.92)'
    ctx.strokeStyle = stroke
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.rect(rx, ry, w, h)
    ctx.fill()
    ctx.stroke()
    ctx.fillStyle = color
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(text, rx + w / 2, ry + h / 2 + .5)
    ctx.restore()
  },
  drawCampaignOverlays(ctx, sink, scale, origin, viewport, landPath) {
    const ov = this.campaignOverlay
    if (!ov) return
    const iso = ov.isolateLayer || null
    const overviewMode = !ov.selectedPlayId && !ov.selectedAvoidId && !iso
    const dimFor = (layerKey, itemSelected = null) => {
      let d = 1
      if (iso && iso !== layerKey) d *= .30
      if (itemSelected === false) d *= .30
      return d
    }

    // Clipped to circle and real coastline for geographic layers 2..5
    ctx.save()
    if (landPath) this.clipLand(ctx, landPath, scale, origin)

    // Layer 2: Hold plateau (quiet cyan #00e5dc at 15% fill in overview so gold targets pop; full on hold focus).
    if (ov.holdPlateau?.length) {
      const holdSelected = ov.selectedPlayId ? ov.selectedPlayId.endsWith(':hold_thin') : ov.selectedAvoidId ? false : null
      const alphaMul = dimFor('hold', holdSelected)
      ctx.save()
      ctx.beginPath()
      for (const part of ov.holdPlateau) for (const ring of part.rings) traceTerritoryRing(ring, sink)
      ctx.fillStyle = '#00e5dc'
      ctx.globalAlpha = (overviewMode ? .15 : .22) * alphaMul
      ctx.fill('evenodd')
      ctx.strokeStyle = '#00e5dc'
      ctx.globalAlpha = (overviewMode ? .76 : .90) * alphaMul
      ctx.lineWidth = 1.5
      ctx.setLineDash([])
      ctx.stroke()
      if (ov.thinHoldParts?.length && (!overviewMode || iso === 'hold')) {
        ctx.beginPath()
        for (const part of ov.thinHoldParts) for (const ring of part.rings) traceTerritoryRing(ring, sink)
        ctx.strokeStyle = '#00e5dc'
        ctx.globalAlpha = .92 * alphaMul
        ctx.lineWidth = 1.4
        ctx.setLineDash([5, 4])
        ctx.stroke()
      }
      ctx.restore()
    }

    // Layer 3: Resistance / Fortress crimson 45-degree hairline hatch (receded in overview, full on avoid/fortress focus).
    for (const fr of ov.fortressRegions || []) {
      const selected = ov.selectedAvoidId ? ov.selectedAvoidId === fr.avoidId : ov.selectedPlayId ? false : null
      const alphaMul = dimFor('fortress', selected)
      const isFocusedFortress = ov.selectedAvoidId === fr.avoidId || iso === 'fortress'
      this.drawHatch(ctx, fr.parts, sink, {
        color: '#e3232d',
        pitch: 7,
        alpha: (isFocusedFortress ? .42 : .20) * alphaMul,
        strokeAlpha: (isFocusedFortress ? .82 : .38) * alphaMul,
        viewport,
      })
    }

    // Layer 4: Detached landmass grey stipple + dashed outline (very quiet in overview, crisp on focus).
    for (const det of ov.detachedRegions || []) {
      const selected = ov.selectedAvoidId ? ov.selectedAvoidId === det.avoidId : ov.selectedPlayId ? false : null
      const alphaMul = dimFor('detached', selected)
      const isFocusedDet = ov.selectedAvoidId === det.avoidId || iso === 'detached'
      this.drawStipple(ctx, det.parts, sink, {
        color: '#8a8a8a',
        fillAlpha: (isFocusedDet ? .28 : .13) * alphaMul,
        strokeAlpha: (isFocusedDet ? .76 : .34) * alphaMul,
        dash: [4, 4],
      })
    }

    // Layer 5: Service-gap white dashed contour (progressive disclosure: shown when focusing service_gap play or isolating service_gap).
    const showServiceGap = Boolean(
      ov.serviceGapRegion?.parts?.length &&
      (ov.selectedPlayId === ov.serviceGapRegion.playId || iso === 'service_gap')
    )
    if (showServiceGap) {
      const selected = ov.selectedPlayId ? ov.selectedPlayId === ov.serviceGapRegion.playId : ov.selectedAvoidId ? false : null
      const alphaMul = dimFor('service_gap', selected)
      ctx.save()
      ctx.beginPath()
      for (const part of ov.serviceGapRegion.parts) for (const ring of part.rings) traceTerritoryRing(ring, sink)
      ctx.strokeStyle = '#ffffff'
      ctx.globalAlpha = .92 * alphaMul
      ctx.lineWidth = 1.6
      ctx.setLineDash([6, 4])
      ctx.stroke()
      ctx.restore()
    }
    ctx.restore()

    // Layer 6: Contoured & weighted flip frontiers (progressive disclosure: shown on Play focus, Seams isolate, or Contested toggle).
    const showStaticSeams = Boolean(
      ov.seams?.length && !ov.animateSeams && (ov.selectedPlayId || iso === 'seams')
    )
    if (showStaticSeams) {
      this.drawSmoothCampaignSeams(ctx, ov.seams, scale, origin, { ov, pulse: 1 })
    }

    // Detached landmass & service-gap crisp label chips (only when focused/isolated so overview stays clutter-free).
    for (const det of ov.detachedRegions || []) {
      if (!det.anchor) continue
      const isFocusedDet = ov.selectedAvoidId === det.avoidId || iso === 'detached'
      if (!isFocusedDet) continue
      const lx = det.anchor.x * scale - origin.x, ly = det.anchor.y * scale - origin.y
      if (lx >= -60 && ly >= -20 && lx <= viewport.x + 60 && ly <= viewport.y + 20) {
        this.drawMapLabelChip(ctx, lx, ly, det.label, { stroke: '#525252', color: '#cccccc', alpha: 1 })
      }
    }
    if (showServiceGap && ov.serviceGapRegion?.anchor && ov.serviceGapRegion.label) {
      const lx = ov.serviceGapRegion.anchor.x * scale - origin.x, ly = ov.serviceGapRegion.anchor.y * scale - origin.y
      if (lx >= -100 && ly >= -20 && lx <= viewport.x + 100 && ly <= viewport.y + 20) {
        this.drawMapLabelChip(ctx, lx, ly - 26, ov.serviceGapRegion.label, { stroke: '#ffffff', color: '#ffffff', alpha: 1 })
      }
    }
  },
  // Keyword stuffing overlays: primary top-10 white 1.5px contour + 2px white rings on inherit pins.
  drawKeywordOverlays(ctx, sink, landPath, scale, origin) {
    const kw = this.keywordOverlay
    if (!kw) return
    if (kw.primaryTop10Parts?.length) {
      ctx.save()
      if (landPath) this.clipLand(ctx, landPath, scale, origin)
      ctx.beginPath()
      for (const part of kw.primaryTop10Parts) for (const ring of part.rings) traceTerritoryRing(ring, sink)
      ctx.lineJoin = 'round'
      ctx.strokeStyle = 'rgba(0,0,0,.75)'
      ctx.lineWidth = 3.2
      ctx.stroke()
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 1.5
      ctx.stroke()
      ctx.restore()
    }
    if (kw.inheritIds?.size) {
      ctx.save()
      for (const cell of this.hits) {
        if (!kw.inheritIds.has(cell.id)) continue
        const radius = Math.max(5.5, cell.size / 2 + 2.5)
        ctx.beginPath()
        ctx.arc(cell.sx, cell.sy, radius, 0, Math.PI * 2)
        ctx.strokeStyle = 'rgba(0,0,0,.8)'
        ctx.lineWidth = 3.5
        ctx.stroke()
        ctx.strokeStyle = '#ffffff'
        ctx.lineWidth = 2
        ctx.stroke()
      }
      ctx.restore()
    }
  },
  // Full 30-layer hypsometric topographic elevation for Rankings mode:
  // Every single rank (1..depth) gets its own non-overlapping evenodd elevation band + hairline
  // contour, anchored by bold index contours for the 3 Google Pages (1-10, 11-20, 21-30) + #1 & 3-Pack.
  drawElevation(ctx, sink) {
    const levels = this.elevation?.levels
    if (!levels?.length) return
    const pure = !!this.hideDots
    const dimMul = Number.isFinite(this.elevation?.dimAlpha) ? this.elevation.dimAlpha : 1
    const traceParts = parts => { for (const part of parts) for (const ring of part.rings) traceTerritoryRing(ring, sink) }

    // Generalized scalar relief (e.g., Campaigns Winnability Relief ember ramp or custom bandStyle).
    if (this.elevation?.mode === 'scalar' || typeof this.elevation?.bandStyle === 'function') {
      const emberRamp = ['#3a2400', '#5c3807', '#7f4d0f', '#b8741a', '#db901d', '#ffb020', '#ffc444', '#ffd76a', '#ffe699', '#fff1c4']
      const styleFn = typeof this.elevation.bandStyle === 'function' ? this.elevation.bandStyle : val => {
        const idx = Math.max(0, Math.min(9, Math.floor((val - 1) / 10)))
        const t = idx / 9
        return {
          fill: emberRamp[idx],
          stroke: emberRamp[idx],
          fillAlpha: (.10 + t * .28) * (pure ? 1 : .82),
          lineAlpha: .30,
          lineWidth: .75,
        }
      }
      const boldSpecs = Array.isArray(this.elevation.indexSpecs) ? this.elevation.indexSpecs : [
        { value: 40, stroke: '#ffb020', alpha: .88, width: 1.8, dash: [] },
        { value: 60, stroke: '#ffd76a', alpha: .96, width: 2.2, dash: [] },
      ]
      const boldSet = new Set(boldSpecs.map(s => s.value))
      ctx.save()
      ctx.lineJoin = 'round'
      // Pass 1: Non-overlapping evenodd iso-terraces (outermost to innermost).
      for (let i = levels.length - 1; i >= 0; i--) {
        const outer = levels[i].parts
        if (!outer.length) continue
        const inner = i > 0 ? levels[i - 1].parts : null
        const st = styleFn(levels[i].value ?? levels[i].rank, pure)
        ctx.beginPath()
        traceParts(outer)
        if (inner?.length) traceParts(inner)
        ctx.fillStyle = st.fill
        ctx.globalAlpha = (st.fillAlpha ?? .2) * dimMul
        ctx.fill('evenodd')
      }
      // Pass 2: Hairline contour every level at 30% alpha.
      ctx.setLineDash([])
      for (let i = levels.length - 1; i >= 0; i--) {
        const val = levels[i].value ?? levels[i].rank
        const parts = levels[i].parts
        if (!parts.length || boldSet.has(val)) continue
        const st = styleFn(val, pure)
        ctx.beginPath()
        traceParts(parts)
        ctx.strokeStyle = st.stroke
        ctx.globalAlpha = (st.lineAlpha ?? .30) * dimMul
        ctx.lineWidth = st.lineWidth ?? .75
        ctx.stroke()
      }
      // Pass 3: Bold index contours (40 contest, 60 strike).
      for (const spec of boldSpecs) {
        const entry = levels.find(l => (l.value ?? l.rank) === spec.value)
        if (!entry?.parts.length) continue
        ctx.beginPath()
        traceParts(entry.parts)
        ctx.setLineDash(spec.dash || [])
        ctx.strokeStyle = '#000000'
        ctx.globalAlpha = .58 * spec.alpha * dimMul
        ctx.lineWidth = spec.width + 2
        ctx.stroke()
        ctx.strokeStyle = spec.stroke
        ctx.globalAlpha = spec.alpha * dimMul
        ctx.lineWidth = spec.width
        ctx.stroke()
      }
      ctx.restore()
      return
    }

    const page1Colors = ['#00ffff', '#00f7d4', '#00ee9b', '#1ce668', '#4be038', '#78da18', '#a3d40a', '#c9cc06', '#e6c20a', '#facc15']
    const bandStyle = rank => {
      if (rank <= 10) {
        const t = (rank - 1) / 9
        return {
          fill: page1Colors[rank - 1],
          stroke: page1Colors[rank - 1],
          fillAlpha: pure ? .34 - t * .15 : .21 - t * .10,
          lineAlpha: pure ? .46 - t * .12 : .32 - t * .10,
        }
      }
      if (rank <= 20) {
        const t = (rank - 11) / 9
        // Page 2 (11..20): warm terracotta/crimson slope fading progressively down
        const p2 = ['#f97316', '#f2601d', '#eb4d24', '#e33b2b', '#dc2b2e', '#cc242b', '#bc1f28', '#ac1b25', '#9c1722', '#8c1520']
        return {
          fill: p2[rank - 11],
          stroke: p2[rank - 11],
          fillAlpha: pure ? .18 - t * .08 : .11 - t * .05,
          lineAlpha: pure ? .34 - t * .12 : .22 - t * .08,
        }
      }
      const t = (rank - 21) / 9
      // Page 3 (21..30): deep smoked burgundy fading gently into the 30+ dark void
      const p3 = ['#7f1d28', '#751b2a', '#6b192b', '#61172b', '#57162a', '#4e1529', '#451427', '#3c1324', '#341221', '#2c111e']
      return {
        fill: p3[rank - 21],
        stroke: '#9f2c3c',
        fillAlpha: pure ? .10 - t * .065 : .06 - t * .04,
        lineAlpha: pure ? .22 - t * .11 : .14 - t * .07,
      }
    }

    ctx.save()
    ctx.lineJoin = 'round'
    const tierW = rank => this.tierWeights?.get(masterTierForRank(rank)?.id) || 0
    const anyTier = this.tierWeights?.size ? Math.max(...this.tierWeights.values()) : 0
    const scale = this.lastScale, origin = this.lastOrigin

    // Pass 1: Non-overlapping 1-rank hypsometric bands (outer[k] \ inner[k-1] via evenodd -> zero mud/stacking).
    for (let i = levels.length - 1; i >= 0; i--) {
      const outer = levels[i].parts
      if (!outer.length) continue
      const inner = i > 0 ? levels[i - 1].parts : null
      const st = bandStyle(levels[i].rank)
      const tw = tierW(levels[i].rank)
      ctx.beginPath()
      traceParts(outer)
      if (inner?.length) traceParts(inner)
      ctx.fillStyle = st.fill
      ctx.globalAlpha = st.fillAlpha * (1 - anyTier * .35) + tw * .14
      ctx.fill('evenodd')
    }

    // Pass 1b: Inward-only shapeburst on intermediate contours at gentler weight.
    if (CARTOGRAPHIC.contours === 'all' && scale && origin && typeof Path2D !== 'undefined') {
      for (let i = levels.length - 1; i >= 0; i--) {
        const { rank, parts } = levels[i]
        if (!parts.length || [1, 3, 10, 20, 30].includes(rank)) continue
        const st = bandStyle(rank)
        const path = this.buildScreenPath(parts, scale, origin)
        this.drawInnerShapeburst(ctx, path, st.stroke, { widthPx: CARTOGRAPHIC.innerWidth * .35, maxOpacity: CARTOGRAPHIC.innerOpacity * .35, dim: 1 - anyTier * .3 + tierW(rank) * .6 })
      }
    }

    // Pass 2: Fine 1-rank intermediate topographic contour lines (every single rank step shows true slope/cliffs!).
    const indexRanks = new Set([1, 3, 10, 20, 30])
    ctx.setLineDash([])
    for (let i = levels.length - 1; i >= 0; i--) {
      const { rank, parts } = levels[i]
      if (!parts.length || indexRanks.has(rank)) continue
      const st = bandStyle(rank)
      const tw = tierW(rank)
      ctx.beginPath()
      traceParts(parts)
      ctx.strokeStyle = st.stroke
      ctx.globalAlpha = Math.min(1, st.lineAlpha * (1 - anyTier * .3) + tw * .35)
      ctx.lineWidth = (rank <= 10 ? .75 : rank <= 20 ? .65 : .55) * CARTOGRAPHIC.borderScale + tw * .8
      ctx.stroke()
    }

    // Pass 3: Bold Major Index Contours (the 3 Google Pages + #1 Summit + 3-Pack Money Line).
    const indexSpecs = [
      { rank: 30, stroke: '#991b1b', alpha: .72, width: pure ? 1.3 : 1.1, dash: [2, 5] },
      { rank: 20, stroke: '#ef4444', alpha: .86, width: pure ? 1.7 : 1.4, dash: [5, 5] },
      { rank: 10, stroke: '#facc15', alpha: .95, width: pure ? 2.1 : 1.8, dash: [8, 5] },
      { rank: 3, stroke: '#00ff8e', alpha: .98, width: pure ? 2.3 : 1.9, dash: [] },
      { rank: 1, stroke: '#00ffff', alpha: 1.0, width: pure ? 2.6 : 2.2, dash: [] },
    ]
    for (const spec of indexSpecs) {
      const entry = levels.find(l => l.rank === spec.rank)
      if (!entry?.parts.length) continue
      const tw = tierW(spec.rank)
      const w = spec.width * CARTOGRAPHIC.borderScale + tw * 1.1
      if (scale && origin && typeof Path2D !== 'undefined') {
        const path = this.buildScreenPath(entry.parts, scale, origin)
        ctx.setLineDash([])
        this.drawInnerShapeburst(ctx, path, spec.stroke, { widthPx: CARTOGRAPHIC.innerWidth, maxOpacity: CARTOGRAPHIC.innerOpacity * spec.alpha, dim: 1 - anyTier * .25 + tw * .5 })
      }
      ctx.beginPath()
      traceParts(entry.parts)
      ctx.setLineDash(spec.dash)
      ctx.strokeStyle = '#000000'
      ctx.globalAlpha = .68 * spec.alpha * (1 - anyTier * .2 + tw * .3)
      ctx.lineWidth = w + 2.2 * CARTOGRAPHIC.borderScale
      ctx.stroke()
      ctx.strokeStyle = spec.stroke
      ctx.globalAlpha = Math.min(1, spec.alpha * (1 - anyTier * .25) + tw * .25)
      ctx.lineWidth = w
      ctx.stroke()
    }
    ctx.restore()
  },
  // Focus contours in Local Leaders:
  // If a full 30-layer elevation stack is attached, drape the smooth hypsometric topography
  // straight over the dimmed rival empires (zero dot clutter!); otherwise draw classic 3-pack/top-10 lines.
  drawFocusContours(ctx, sink) {
    if (this.focus.elevation?.levels?.length) {
      const prevElev = this.elevation
      this.elevation = this.focus.elevation
      this.drawElevation(ctx, sink)
      this.elevation = prevElev
      return
    }
    const { color, plateau = [], reach = [] } = this.focus
    const trace = parts => { ctx.beginPath(); for (const part of parts) for (const ring of part.rings) traceTerritoryRing(ring, sink) }
    ctx.save()
    ctx.lineJoin = 'round'
    if (plateau.length) {
      trace(plateau)
      ctx.fillStyle = color; ctx.globalAlpha = .07; ctx.fill('evenodd')
    }
    for (const [parts, width, dash] of [[reach, 1.75, [7, 5]], [plateau, 2.5, []]]) {
      if (!parts.length) continue
      trace(parts)
      ctx.setLineDash(dash)
      ctx.globalAlpha = .7; ctx.strokeStyle = '#000000'; ctx.lineWidth = width + 2.5; ctx.stroke()
      ctx.globalAlpha = 1; ctx.strokeStyle = color; ctx.lineWidth = width; ctx.stroke()
    }
    ctx.restore()
  },
  // Flip targets: solid ring where the focused business ranks #2, dashed ring where it ranks #3.
  // Shown only when grid dots are visible so dotless topographic focus stays razor-clean.
  drawFocusRings(ctx) {
    if (this.hideDots) return
    const { color, rank2, rank3 } = this.focus
    ctx.save()
    for (const cell of this.hits) {
      const second = rank2?.has(cell.id)
      if (!second && !rank3?.has(cell.id)) continue
      const radius = cell.size / 2 + Math.max(2.5, cell.size * .2)
      ctx.beginPath(); ctx.arc(cell.sx, cell.sy, radius, 0, Math.PI * 2)
      ctx.setLineDash(second ? [] : [Math.max(2, radius * .5), Math.max(2, radius * .42)])
      ctx.globalAlpha = .75; ctx.strokeStyle = '#000000'; ctx.lineWidth = second ? 3.4 : 2.8; ctx.stroke()
      ctx.globalAlpha = 1; ctx.strokeStyle = color; ctx.lineWidth = second ? 1.8 : 1.3; ctx.stroke()
    }
    ctx.restore()
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
    this.lastScale = scale
    this.lastOrigin = origin
    const stepPx = this.spacing * scale
    this.stepPx = stepPx
    // Honeycomb: calibrate every real hexagon to public STOP_SIGN_SCALE (0.30) of the finest rung spacing
    // so dots stay crisp, airy, and readable over the map instead of bloating on coarse views.
    const hex = this.honeycombData, hexS = hex ? hex.spacing * scale : 0
    const hexUnit = hex ? this.honeycombUnitScale(hex) : 1
    const size = hex ? hexS * hexUnit * STOP_SIGN_SCALE : stepPx * STOP_SIGN_SCALE
    this.dotSize = size
    const hexRealR = size / 2
    const hexLine = Math.max(.5, Math.min(1.4, hexRealR / 6))
    const diamondSize = stepPx * 2 * DIAMOND_HALF
    const stroke = size * .015
    const mix = this.hoverMix || 0
    const weightOf = id => (id && this.leaderWeights?.get(id)) || 0
    const visible = (x, y, s) => x + s / 2 >= 0 && y + s / 2 >= 0 && x - s / 2 <= viewport.x && y - s / 2 <= viewport.y
    const landPath = this.buildLandPath(scale, origin)
    ctx.save()
    if (this.blendBoundary?.length) {
      ctx.beginPath()
      this.blendBoundary.forEach((p, i) => ctx[i ? 'lineTo' : 'moveTo'](p.x * scale - origin.x, p.y * scale - origin.y))
      ctx.closePath()
      ctx.clip()
    }
    for (const diamond of this.diamonds) {
      const dSize = (diamond.spacing ? diamond.spacing * scale : stepPx) * 2 * DIAMOND_HALF
      const x = diamond.x * scale - origin.x, y = diamond.y * scale - origin.y
      if (!visible(x, y, dSize)) continue
      const wD = weightOf(diamond.leaderId)
      const dimD = mix * (1 - wD)
      const alphaD = 1 - dimD * .56
      ctx.save()
      ctx.beginPath()
      ctx.moveTo(x, y - dSize / 2); ctx.lineTo(x + dSize / 2, y)
      ctx.lineTo(x, y + dSize / 2); ctx.lineTo(x - dSize / 2, y); ctx.closePath()
      ctx.save()
      ctx.clip()
      // Texture already contains each contributor's display alpha.
      ctx.globalAlpha = alphaD
      ctx.drawImage(diamond.texture, x - dSize / 2, y - dSize / 2, dSize, dSize)
      ctx.restore()
      ctx.globalAlpha = alphaD
      ctx.strokeStyle = 'rgba(0,0,0,.5)'; ctx.lineWidth = stroke; ctx.stroke()
      ctx.restore()
    }
    const sharedSink = {
      moveTo: (x, y) => ctx.moveTo(x * scale - origin.x, y * scale - origin.y),
      lineTo: (x, y) => ctx.lineTo(x * scale - origin.x, y * scale - origin.y),
      quadraticCurveTo: (cx, cy, x, y) => ctx.quadraticCurveTo(cx * scale - origin.x, cy * scale - origin.y, x * scale - origin.x, y * scale - origin.y),
      closePath: () => ctx.closePath(),
    }
    // Rankings / Campaigns / Keyword stuffing topographic elevation terraces (clipped to study circle ∩ real coastline, under dots).
    if (this.elevation) {
      if (landPath) { ctx.save(); this.clipLand(ctx, landPath, scale, origin) }
      this.drawElevation(ctx, sharedSink)
      if (landPath) ctx.restore()
    }
    if (this.campaignOverlay) {
      this.drawCampaignOverlays(ctx, sharedSink, scale, origin, viewport, landPath)
    }
    // Crisp between-point estimate triangles (strictly smaller than real hexagons), clipped to study circle ∩ land.
    if (hex && this.honeycomb.estimates) {
      if (landPath) { ctx.save(); this.clipLand(ctx, landPath, scale, origin) }
      this.drawHoneycombEstimates(ctx, hex, scale, origin, hexS, visible, hexRealR, hexLine)
      if (landPath) ctx.restore()
    }
    if (!this.clipTerritories) ctx.restore()
    if (this.territories?.length) {
      const baseRadius = Math.min(stepPx * .26, 13)
      const baseBorderW = Math.max(1.4, Math.min(2.5, stepPx * .09))
      const hoverBorderW = Math.max(2.2, Math.min(3.6, stepPx * .125))
      const traceRing = (ring, inset, adaptive = false, contourSmooth = false) => {
        const pts = ring.map(p => ({
          x: p.x * scale - origin.x + (p.ix || 0) * inset,
          y: p.y * scale - origin.y + (p.iy || 0) * inset,
          convex: !!p.convex,
          r: p.convex ? Math.max(1.5, baseRadius - inset) : baseRadius + inset,
        }))
        for (let i = 0; i < pts.length; i++) {
          const prev = pts[(i - 1 + pts.length) % pts.length]
          const curr = pts[i]
          const next = pts[(i + 1) % pts.length]
          const midPrevX = (prev.x + curr.x) / 2
          const midPrevY = (prev.y + curr.y) / 2
          const midNextX = (curr.x + next.x) / 2
          const midNextY = (curr.y + next.y) / 2
          if (i === 0) ctx.moveTo(midPrevX, midPrevY)
          if (contourSmooth) {
            ctx.quadraticCurveTo(curr.x, curr.y, midNextX, midNextY)
            continue
          }
          let r = curr.r
          if (adaptive) {
            const v1x = prev.x - curr.x, v1y = prev.y - curr.y
            const v2x = next.x - curr.x, v2y = next.y - curr.y
            const d1 = Math.hypot(v1x, v1y), d2 = Math.hypot(v2x, v2y)
            const minEdge = Math.min(d1, d2)
            if (minEdge < 1e-3) {
              ctx.lineTo(curr.x, curr.y)
              continue
            }
            const cosBeta = Math.max(-1, Math.min(1, (v1x * v2x + v1y * v2y) / (d1 * d2)))
            const tanHalf = Math.tan(Math.acos(cosBeta) / 2)
            if (!Number.isFinite(tanHalf) || tanHalf > 1e3) {
              ctx.lineTo(curr.x, curr.y)
              continue
            }
            const localBase = Math.min(minEdge * .45, Math.max(baseRadius * 1.15, 14))
            const desired = curr.convex ? Math.max(1.2, localBase - inset) : localBase + inset
            r = Math.max(0, Math.min(desired, minEdge * .46 * tanHalf))
          }
          if (r > .1) ctx.arcTo(curr.x, curr.y, midNextX, midNextY, r)
          else ctx.lineTo(curr.x, curr.y)
        }
        ctx.closePath()
      }
      // Head-to-head territories: zoom-0 rings traced straight to screen space. Pinned
      // corners (triple junctions, rim) stay exact; regular bends get the shared smoothing.
      const screenSink = {
        moveTo: (x, y) => ctx.moveTo(x * scale - origin.x, y * scale - origin.y),
        lineTo: (x, y) => ctx.lineTo(x * scale - origin.x, y * scale - origin.y),
        quadraticCurveTo: (cx, cy, x, y) => ctx.quadraticCurveTo(cx * scale - origin.x, cy * scale - origin.y, x * scale - origin.x, y * scale - origin.y),
        closePath: () => ctx.closePath(),
      }
      const focusId = this.focus?.leaderId ?? null
      const focusHasTopo = !!(this.focus?.elevation?.levels?.length)
      const baseFillAlpha = this.hideDots ? .17 : .15
      const baseStrokeW = this.hideDots ? 2.8 : 2.4
      const reliefTierAlpha = this.hideDots ? [.095, .105, .115] : [.06, .07, .08]
      const reliefLineAlpha = this.hideDots ? [.42, .68, .88] : [.32, .52, .72]
      const reliefLineW = this.hideDots ? [.85, 1.15, 1.35] : [.7, .95, 1.1]
      if (landPath) {
        ctx.save()
        if (!this.clipTerritories && this.blendBoundary?.length) {
          ctx.beginPath()
          this.blendBoundary.forEach((p, i) => ctx[i ? 'lineTo' : 'moveTo'](p.x * scale - origin.x, p.y * scale - origin.y))
          ctx.closePath()
          ctx.clip()
        }
        this.clipLand(ctx, landPath, scale, origin)
      }
      for (const t of this.territories) {
        if (!t.tectonic) continue
        const focusT = weightOf(t.leaderId)
        const dimT = mix * (1 - focusT)
        // Topographic drape: background empires fade to 0.04 so no ghost double-border peeks through.
        const focusDim = focusId != null ? (focusHasTopo ? CARTOGRAPHIC.focusTopoBackgroundDim : (t.leaderId !== focusId ? .25 : 1)) : 1
        ctx.save()
        ctx.beginPath()
        for (const ring of t.rings) traceTerritoryRing(ring, screenSink)
        ctx.fillStyle = t.color
        ctx.globalAlpha = (baseFillAlpha * (1 - dimT * .5) + .1 * focusT) * focusDim
        ctx.fill('evenodd')
        // Clip to this leader's exact head-to-head polygon so internal Fortress Cores and inner stroke never cross a border or contested seam.
        ctx.clip('evenodd')
        if (typeof Path2D !== 'undefined') {
          const outerPath = this.buildRingsPath(t.rings, scale, origin)
          this.drawInnerShapeburst(ctx, outerPath, t.color, { widthPx: CARTOGRAPHIC.innerWidth, maxOpacity: CARTOGRAPHIC.innerOpacity, dim: (1 - dimT * .45) * focusDim })
        }
        const reliefTiers = !focusHasTopo ? this.leaderRelief?.get(t.leaderId) : null
        if (reliefTiers?.length) {
          ctx.lineJoin = 'round'
          for (const rt of reliefTiers) {
            ctx.beginPath()
            for (const part of rt.parts) for (const ring of part.rings) traceTerritoryRing(ring, screenSink)
            ctx.fillStyle = t.color
            ctx.globalAlpha = (reliefTierAlpha[rt.tier] ?? .09) * (1 - dimT * .45) * focusDim
            ctx.fill('evenodd')
            if (typeof Path2D !== 'undefined') {
              const reliefPath = this.buildScreenPath(rt.parts, scale, origin)
              this.drawInnerShapeburst(ctx, reliefPath, t.color, { widthPx: CARTOGRAPHIC.innerWidth * (.5 + rt.tier * .25), maxOpacity: CARTOGRAPHIC.innerOpacity * .7, dim: (1 - dimT * .45) * focusDim })
            }
            ctx.strokeStyle = t.color
            ctx.globalAlpha = (reliefLineAlpha[rt.tier] ?? .5) * (1 - dimT * .45) * focusDim
            ctx.lineWidth = (reliefLineW[rt.tier] ?? 1) * CARTOGRAPHIC.borderScale + .35
            ctx.stroke()
          }
        }
        ctx.beginPath()
        for (const ring of t.rings) traceTerritoryRing(ring, screenSink)
        ctx.lineJoin = 'round'
        ctx.strokeStyle = t.color
        ctx.globalAlpha = Math.min(1, .88 * (1 - dimT * .45) + .12 * focusT) * focusDim
        ctx.lineWidth = (baseStrokeW + 1.5 * focusT) * CARTOGRAPHIC.borderScale + .4 * focusT
        ctx.stroke()
        ctx.restore()
      }
      if (this.focus) this.drawFocusContours(ctx, screenSink)
      if (landPath) ctx.restore()
      for (const t of this.territories) {
        if (t.tectonic) continue
        const focusT = weightOf(t.leaderId)
        const dimT = mix * (1 - focusT)
        const borderW = baseBorderW + (hoverBorderW - baseBorderW) * focusT
        const inset = borderW / 2
        const rings = t.rings || (t.ring ? [t.ring] : [])
        const adaptive = !!t.adaptiveRadius
        const smooth = !!t.contourSmooth
        ctx.save()
        // Fill interior using evenodd so inner enclaves (holes) are never filled by the surrounding territory
        ctx.beginPath()
        for (const ring of rings) traceRing(ring, 0, adaptive, smooth)
        ctx.fillStyle = t.color
        ctx.globalAlpha = .075 * (1 - dimT * .58) + .105 * focusT
        ctx.fill('evenodd')
        // Stroke each boundary ring inset strictly to its own side of the shared cell line (full-bleed, zero overlap)
        ctx.beginPath()
        for (const ring of rings) traceRing(ring, inset, adaptive, smooth)
        ctx.strokeStyle = t.color
        ctx.globalAlpha = .84 * (1 - dimT * .52) + .15 * focusT
        ctx.lineWidth = borderW
        ctx.stroke()
        ctx.restore()
      }
    }
    if (landPath) this.strokeLandHairline(ctx, landPath, scale, origin)
    this.hits = []
    // Measured dots always sit on top of head-to-head territories at full saturation.
    const fullDots = !!this.territories?.some(t => t.tectonic)
    for (const cell of this.cells) {
      // Every real measured point (ranked, hollow, dashed, dotted, coarse or refined) keeps the exact same calibrated size.
      const cSize = hex ? size : (cell.spacing ? cell.spacing * scale : stepPx) * STOP_SIGN_SCALE
      const x = cell.x * scale - origin.x, y = cell.y * scale - origin.y
      if (!visible(x, y, cSize)) continue
      this.hits.push({ ...cell, sx: x, sy: y, size: cSize })
      // In pure-territory mode, skip drawing bulk grid dots while keeping hover hit-testing and active pin visible.
      if (this.hideDots && !cell.active) continue
      // The business marker replaces the center data hexagon.
      if (hex && this.honeycomb.marker && cell.honeycomb && !cell.honeycomb.a && !cell.honeycomb.b) continue
      const focusC = weightOf(cell.leaderId)
      const dimC = mix * (1 - focusC)
      const hoverFactor = fullDots ? 1 : 1 - dimC * .54
      ctx.save()
      ctx.beginPath()
      if (hex) tracePolygon(ctx, honeycombVertices(x, y, cSize / 2, 1, HONEYCOMB_SHAPES[1].rot))
      else {
        OCTAGON_VERTICES.forEach(([vx, vy], i) => ctx[i ? 'lineTo' : 'moveTo'](x + (vx - .5) * cSize, y + (vy - .5) * cSize))
        ctx.closePath()
      }
      if (!['nr', 'unknown', 'other', 'limited'].includes(cell.kind)) {
        ctx.fillStyle = cell.color
        ctx.globalAlpha = (cell.opacity ?? 1) * (cell.muted ? .15 : 1) * hoverFactor
        ctx.fill()
      }
      ctx.globalAlpha = (cell.muted ? .15 : 1) * hoverFactor
      const coverageOutline = cell.coverage && ['nr', 'unknown', 'other'].includes(cell.kind)
      const skipOutline = !cell.coverage && ['nr', 'unknown', 'other'].includes(cell.kind) && !cell.active
      if (!skipOutline) {
        ctx.strokeStyle = coverageOutline ? (cell.kind === 'unknown' ? 'rgba(225,184,105,.65)' : 'rgba(163,177,195,.55)') : hex ? (this.translucent ? 'rgba(8,8,8,.88)' : '#000') : 'rgba(0,0,0,.5)'
        ctx.lineWidth = coverageOutline ? Math.max(.8, Math.min(1.5, size * .025)) : hex ? Math.max(this.translucent ? 1.1 : .5, hexLine * (cell.active ? 2 : this.translucent ? 1.25 : 1)) : size * (cell.active ? .03 : cell.kind === 'unknown' ? .02 : .015)
        if (cell.kind === 'unknown') ctx.setLineDash([Math.max(1, size * .06), Math.max(1, size * .06)])
        if (cell.kind === 'limited') {
          // Instrument-limited: the business is outside this search's screen. Muted, dotted, never a loss.
          ctx.strokeStyle = 'rgba(150,156,170,.6)'
          ctx.lineWidth = Math.max(.6, hexLine * .8)
          ctx.setLineDash([Math.max(.8, cSize * .05), Math.max(1.2, cSize * .09)])
        }
        ctx.stroke()
      }
      if (focusC > .02) {
        ctx.setLineDash([])
        ctx.globalAlpha = (cell.muted ? .15 : 1) * focusC * .85
        ctx.strokeStyle = '#ffffff'
        ctx.lineWidth = Math.max(1.1, size * .075)
        ctx.stroke()
      }
      if (cell.active) {
        ctx.setLineDash([])
        ctx.globalAlpha = 1
        ctx.strokeStyle = '#ffffff'
        ctx.lineWidth = Math.max(2, size * .12)
        ctx.stroke()
      }
      ctx.restore()
    }
    if (this.focus) this.drawFocusRings(ctx)
    if (this.keywordOverlay) this.drawKeywordOverlays(ctx, sharedSink, landPath, scale, origin)
    if (this.clipTerritories) ctx.restore()
    if (hex && this.honeycomb.marker) this.drawHoneycombMarker(ctx, hex, scale, origin, hexS, viewport, hexRealR)
    this.honeycombGlow = hex && this.honeycomb.glow && !this.hideDots ? this.honeycombGlowCells(hex, scale, origin, hexS, viewport, hexRealR) : null
    this.stats = { renderer: 'canvas', points: this.cells.length, diamonds: this.diamonds.length,
      visiblePoints: this.hits.length, drawMs: performance.now() - started,
      ...(hex ? { honeycomb: { layer2: hex.estimates[2].length, layer3: hex.estimates[3].length,
        glowing: this.honeycombGlow?.length || 0, glints: hex.glow.glints } } : {}) }
    if (this.rankOneCanvas) {
      if (this.rankOneCanvas.width !== width || this.rankOneCanvas.height !== height) {
        this.rankOneCanvas.width = width; this.rankOneCanvas.height = height
      }
      Object.assign(this.rankOneCanvas.style, { width: `${viewport.x}px`, height: `${viewport.y}px` })
      L.DomUtil.setPosition(this.rankOneCanvas, map.containerPointToLayerPoint([0, 0]))
      this.stopRankOneAnimation()
      cancelAnimationFrame(this.campaignSeamAnimFrame)
      this.campaignSeamAnimFrame = 0
      this.drawRankOne(performance.now())
      this.animateRankOne()
      this.animateCampaignSeams()
    }
  },
})
