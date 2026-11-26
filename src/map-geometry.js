// Nearest separation in projected map space. Chebyshev distance protects the
// entire square bounding box of each octagon, including diagonal neighbors.
export function cellSpacings(points) {
  function build(entries, depth = 0) {
    if (!entries.length) return null
    const axis = depth % 2
    entries.sort((a, b) => a.xy[axis] - b.xy[axis])
    const mid = entries.length >> 1
    return { ...entries[mid], axis, left: build(entries.slice(0, mid), depth + 1), right: build(entries.slice(mid + 1), depth + 1) }
  }
  const tree = build(points.map((xy, index) => ({ xy, index })))
  return points.map((xy, index) => {
    let best = Infinity
    function visit(node) {
      if (!node) return
      if (node.index !== index) best = Math.min(best, Math.max(Math.abs(xy[0] - node.xy[0]), Math.abs(xy[1] - node.xy[1])))
      const delta = xy[node.axis] - node.xy[node.axis]
      visit(delta < 0 ? node.left : node.right)
      if (Math.abs(delta) < best) visit(delta < 0 ? node.right : node.left)
    }
    visit(tree)
    return best
  })
}

export function cellSize(spacing, zoom) {
  return spacing * 2 ** zoom
}

export const OCTAGON_CUT = 1 / (2 + Math.SQRT2)
// Leave more street detail visible between cells without changing scan spacing.
// Both shapes share this scale, so their edge lengths stay matched.
export const STOP_SIGN_SCALE = .30
// A diamond edge is sqrt(2) * its half-width. Match the octagon's
// diagonal edge (sqrt(2) * cut * full-width), keeping the street gaps open.
export const DIAMOND_HALF = STOP_SIGN_SCALE * OCTAGON_CUT
export const OCTAGON_POINTS = `${OCTAGON_CUT * 100},0 ${100 - OCTAGON_CUT * 100},0 100,${OCTAGON_CUT * 100} 100,${100 - OCTAGON_CUT * 100} ${100 - OCTAGON_CUT * 100},100 ${OCTAGON_CUT * 100},100 0,${100 - OCTAGON_CUT * 100} 0,${OCTAGON_CUT * 100}`

// Partition multi-resolution or hybrid grids into independent uniform lattices
// so inner and outer rings never cross-contaminate row/column intersections.
export function partitionUniformLattices(points) {
  if (points.length <= 4) return [points]
  const byLat = new Map(), byLng = new Map()
  for (const p of points) {
    if (!byLat.has(p.lat)) byLat.set(p.lat, [])
    byLat.get(p.lat).push(p)
    if (!byLng.has(p.lng)) byLng.set(p.lng, [])
    byLng.get(p.lng).push(p)
  }
  const groups = new Map()
  const orphans = []
  for (const p of points) {
    const rowPeers = byLat.get(p.lat).map(q => Math.abs(q.lng - p.lng)).filter(d => d > 1e-6)
    const colPeers = byLng.get(p.lng).map(q => Math.abs(q.lat - p.lat)).filter(d => d > 1e-6)
    const dLng = rowPeers.length ? Math.min(...rowPeers) : 0
    const dLat = colPeers.length ? Math.min(...colPeers) : 0
    const step = dLat || (dLng * Math.cos(p.lat * Math.PI / 180))
    if (!step) {
      orphans.push(p)
      continue
    }
    const key = step.toFixed(3)
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(p)
  }
  if (groups.size <= 1) return [points]
  const sorted = [...groups.values()].sort((a, b) => b.length - a.length)
  if (orphans.length) sorted[0].push(...orphans)
  return sorted.filter(g => g.length >= 2)
}

// Keep the four positions, even when a radial boundary removes some origins.
// Padding the axes also finds intersections beside the outermost measured row.
function singleLatticeIntersections(points, partial = false) {
  const rows = [...new Set(points.map(p => p.lat))].sort((a, b) => b - a)
  const columns = [...new Set(points.map(p => p.lng))].sort((a, b) => a - b)
  if (rows.length < 2 || columns.length < 2) return []
  if (partial) {
    rows.unshift(Number((2 * rows[0] - rows[1]).toFixed(7)))
    rows.push(Number((2 * rows.at(-1) - rows.at(-2)).toFixed(7)))
    columns.unshift(Number((2 * columns[0] - columns[1]).toFixed(7)))
    columns.push(Number((2 * columns.at(-1) - columns.at(-2)).toFixed(7)))
  }
  const lookup = new Map(points.map(p => [`${p.lat},${p.lng}`, p]))
  const intersections = []
  for (let r = 0; r < rows.length - 1; r++) for (let c = 0; c < columns.length - 1; c++) {
    const corners = [[r, c], [r, c + 1], [r + 1, c], [r + 1, c + 1]]
      .map(([y, x]) => lookup.get(`${rows[y]},${columns[x]}`) || null)
    if (corners.filter(Boolean).length < (partial ? 2 : 4)) continue
    intersections.push({ corners, north: rows[r], south: rows[r + 1], west: columns[c], east: columns[c + 1] })
  }
  return intersections
}

export function latticeIntersections(points, partial = false) {
  return partitionUniformLattices(points).flatMap(group => singleLatticeIntersections(group, partial))
}

export function blendColor(corners, x, y) {
  const weights = [(1 - x) * (1 - y), x * (1 - y), (1 - x) * y, x * y]
  const alpha = corners.reduce((sum, color, i) => sum + color[3] * weights[i], 0)
  if (!alpha) return [0, 0, 0, 0]
  // Premultiply before blending so transparent NR corners reveal the map
  // without introducing a dark fringe into neighboring measured colors.
  return [0, 1, 2].map(channel => Math.round(corners.reduce(
    (sum, color, i) => sum + color[channel] * color[3] * weights[i], 0) / alpha)).concat(Math.round(alpha))
}

export function destination(lat, lng, km, bearing) {
  const rad = Math.PI / 180, angle = km / 6371, heading = bearing * rad
  const a = lat * rad, b = lng * rad
  const endLat = Math.asin(Math.sin(a) * Math.cos(angle) + Math.cos(a) * Math.sin(angle) * Math.cos(heading))
  const endLng = b + Math.atan2(Math.sin(heading) * Math.sin(angle) * Math.cos(a), Math.cos(angle) - Math.sin(a) * Math.sin(endLat))
  return [endLat / rad, endLng / rad]
}

// Trace closed orthogonal grid-cell boundary loops for contiguous leader clusters.
function singleLatticeOutlines(points, cellById, project) {
  const rows = [...new Set(points.map(p => p.lat))].sort((a, b) => b - a)
  const columns = [...new Set(points.map(p => p.lng))].sort((a, b) => a - b)
  if (rows.length < 2 || columns.length < 2) return []
  const rowIndex = new Map(rows.map((lat, i) => [lat, i]))
  const colIndex = new Map(columns.map((lng, i) => [lng, i]))
  const colCenter = columns.map(lng => project([rows[0], lng]).x)
  const rowCenter = rows.map(lat => project([lat, columns[0]]).y)
  const colX = new Array(columns.length + 1)
  const rowY = new Array(rows.length + 1)
  colX[0] = colCenter[0] - (colCenter[1] - colCenter[0]) / 2
  for (let c = 1; c < columns.length; c++) colX[c] = (colCenter[c - 1] + colCenter[c]) / 2
  colX[columns.length] = colCenter.at(-1) + (colCenter.at(-1) - colCenter.at(-2)) / 2
  rowY[0] = rowCenter[0] - (rowCenter[1] - rowCenter[0]) / 2
  for (let r = 1; r < rows.length; r++) rowY[r] = (rowCenter[r - 1] + rowCenter[r]) / 2
  rowY[rows.length] = rowCenter.at(-1) + (rowCenter.at(-1) - rowCenter.at(-2)) / 2

  const grid = new Map()
  for (const p of points) {
    const cell = cellById.get(p.id)
    if (!cell || !cell.leaderId || cell.kind !== 'ranked') continue
    const r = rowIndex.get(p.lat), c = colIndex.get(p.lng)
    if (r !== undefined && c !== undefined) grid.set(`${r},${c}`, { r, c, leaderId: cell.leaderId, color: cell.color })
  }

  const visited = new Set()
  const outlines = []
  for (const [startKey, startNode] of grid) {
    if (visited.has(startKey)) continue
    const comp = [startNode]
    visited.add(startKey)
    for (let i = 0; i < comp.length; i++) {
      const { r, c, leaderId } = comp[i]
      for (const [nr, nc] of [[r - 1, c], [r + 1, c], [r, c - 1], [r, c + 1]]) {
        const k = `${nr},${nc}`
        const neighbor = grid.get(k)
        if (neighbor && !visited.has(k) && neighbor.leaderId === leaderId) {
          visited.add(k)
          comp.push(neighbor)
        }
      }
    }
    const inComp = new Set(comp.map(n => `${n.r},${n.c}`))
    // Build directed boundary edges around component cells (clockwise in c,r space)
    const outgoing = new Map()
    const addEdge = (c1, r1, c2, r2, dir) => {
      const k = `${c1},${r1}`
      if (!outgoing.has(k)) outgoing.set(k, [])
      outgoing.get(k).push({ c1, r1, c2, r2, dir, used: false })
    }
    for (const { r, c } of comp) {
      if (!inComp.has(`${r - 1},${c}`)) addEdge(c, r, c + 1, r, 0)         // N edge -> East
      if (!inComp.has(`${r},${c + 1}`)) addEdge(c + 1, r, c + 1, r + 1, 1) // E edge -> South
      if (!inComp.has(`${r + 1},${c}`)) addEdge(c + 1, r + 1, c, r + 1, 2) // S edge -> West
      if (!inComp.has(`${r},${c - 1}`)) addEdge(c, r + 1, c, r, 3)         // W edge -> North
    }
    const nx = [0, -1, 0, 1], ny = [1, 0, -1, 0]
    const rings = []
    for (const edges of outgoing.values()) {
      for (const startEdge of edges) {
        if (startEdge.used) continue
        const loop = []
        let curr = startEdge
        while (curr && !curr.used) {
          curr.used = true
          loop.push(curr)
          const nextKey = `${curr.c2},${curr.r2}`
          const candidates = (outgoing.get(nextKey) || []).filter(e => !e.used)
          if (!candidates.length) break
          // Right-hand turn preference keeps diagonal saddle points separate
          const pref = [(curr.dir + 1) % 4, curr.dir, (curr.dir + 3) % 4, (curr.dir + 2) % 4]
          candidates.sort((a, b) => pref.indexOf(a.dir) - pref.indexOf(b.dir))
          curr = candidates[0]
        }
        if (loop.length < 4) continue
        // Keep only corner vertices where direction changes, with inward normal & turn convexity
        const corners = []
        for (let i = 0; i < loop.length; i++) {
          const prev = loop[(i - 1 + loop.length) % loop.length]
          const edge = loop[i]
          if (prev.dir !== edge.dir) {
            corners.push({
              x: colX[edge.c1],
              y: rowY[edge.r1],
              ix: nx[prev.dir] + nx[edge.dir],
              iy: ny[prev.dir] + ny[edge.dir],
              convex: ((prev.dir + 1) % 4) === edge.dir,
            })
          }
        }
        if (corners.length >= 4) rings.push(corners)
      }
    }
    if (rings.length) {
      outlines.push({
        leaderId: startNode.leaderId,
        color: startNode.color,
        size: comp.length,
        rings,
      })
    }
  }
  return outlines
}

export function territoryOutlines(points, cellById, project) {
  return partitionUniformLattices(points).flatMap(group => singleLatticeOutlines(group, cellById, project))
}

function polygonSignedArea(verts) {
  let area = 0
  for (let i = 0; i < verts.length; i++) {
    const a = verts[i], b = verts[(i + 1) % verts.length]
    area += a.x * b.y - b.x * a.y
  }
  return area * .5
}

// ---------- Head-to-Head Marching Triangles territory engine ----------
// Every border point sits on a mesh edge between two measured locations with unlike
// first-place winners, at a fraction computed only from the two head-to-head ranks at
// those two locations. TAU = 0 draws flush borders at the tie point; TAU > 0 opens a
// rank-computed seam (contested ground) where first place is close to flipping.
export const TERRITORY_LEAD_CAP = 10
export const TERRITORY_MIN_CLAIM = .22
const HOLE = -1
const EDGE_KEY = 1048576
const clampClaim = v => Math.min(1 - TERRITORY_MIN_CLAIM, Math.max(TERRITORY_MIN_CLAIM, v))

// Web Mercator at zoom 0, matching Leaflet map.project(latlng, 0).
export function mercatorZoom0([lat, lng]) {
  const rad = Math.PI / 180, scale = 256 / (2 * Math.PI)
  const sin = Math.sin(Math.max(-85.0511287798, Math.min(85.0511287798, lat)) * rad)
  return { x: scale * (lng * rad + Math.PI), y: scale * (Math.PI - .5 * Math.log((1 + sin) / (1 - sin))) }
}

// Fractions claimed along one unlike-leader edge: [from i toward j, from j toward i].
export function headToHeadReach(mi, mj, loneI, loneJ, tau) {
  const S = mi + mj
  const capI = loneI ? .5 : 1, capJ = loneJ ? .5 : 1
  const rawI = clampClaim(mi / S), rawJ = clampClaim(mj / S)
  let a = Math.min(clampClaim((mi - tau) / S), capI), b = Math.min(clampClaim((mj - tau) / S), capJ)
  // An uncorroborated single dot never claims past the flat midpoint. Its neighbor keeps
  // the border flush at TAU = 0, so the only gaps are the ones TAU opens.
  const void0 = 1 - Math.min(rawI, capI) - Math.min(rawJ, capJ)
  if (void0 > 1e-12) { if (rawI > capI) b += void0; else a += void0 }
  if (tau <= 0 || a + b > 1 - 1e-12) b = 1 - a
  return [a, b]
}

function projectedCircle(project, clipRadiusKm, anchorLatLng) {
  if (!(clipRadiusKm > 0) || !Array.isArray(anchorLatLng) || anchorLatLng.length !== 2) return null
  const c = project(anchorLatLng)
  if (!c || !Number.isFinite(c.x) || !Number.isFinite(c.y)) return null
  let sum = 0, count = 0
  for (const bearing of [0, 90, 180, 270]) {
    const ep = project(destination(anchorLatLng[0], anchorLatLng[1], clipRadiusKm, bearing))
    if (ep && Number.isFinite(ep.x) && Number.isFinite(ep.y)) { sum += Math.hypot(ep.x - c.x, ep.y - c.y); count++ }
  }
  return count ? { x: c.x, y: c.y, r: sum / count } : null
}

const gcd = (a, b) => { while (b) [a, b] = [b, a % b]; return a }

// Uniform honeycomb: triangles straight from (unit_q, unit_r) lattice neighbors.
function latticeTriangles(points, verts, circle, { extrapolateOffshore = false } = {}) {
  const n = verts.length
  if (n < 3) return null
  const Q = [], R = []
  let rung
  for (let v = 0; v < n; v++) {
    const h = points[verts[v].src].hex
    if (!h || !Number.isInteger(h.unit_q) || !Number.isInteger(h.unit_r)) return null
    if (h.rung_miles != null) {
      if (rung === undefined) rung = h.rung_miles
      else if (Math.abs(rung - h.rung_miles) > 1e-9) return null
    }
    Q.push(h.unit_q); R.push(h.unit_r)
  }
  let g = 0, qMin = Infinity, rMin = Infinity, rMax = -Infinity
  for (let v = 0; v < n; v++) {
    g = gcd(g, Math.abs(Q[v] - Q[0])); g = gcd(g, Math.abs(R[v] - R[0]))
    qMin = Math.min(qMin, Q[v]); rMin = Math.min(rMin, R[v]); rMax = Math.max(rMax, R[v])
  }
  if (!g) return null
  const pad = (extrapolateOffshore ? 6 : 4) * g, width = rMax - rMin + 2 * pad + 1
  const key = (q, r) => (q - qMin + pad) * width + (r - rMin + pad)
  const index = new Map()
  for (let v = 0; v < n; v++) {
    const k = key(Q[v], R[v])
    if (index.has(k)) return null
    index.set(k, v)
  }
  const DIRS = [[g, 0], [0, g], [-g, g], [-g, 0], [0, -g], [g, -g]]
  // Mean projected step vectors, used to place hull extensions on the same lattice.
  let ux = 0, uy = 0, un = 0, vx = 0, vy = 0, vn = 0
  for (let v = 0; v < n; v++) {
    let linked = false
    for (const [dq, dr] of DIRS) if (index.has(key(Q[v] + dq, R[v] + dr))) { linked = true; break }
    if (!linked) return null
    const a = index.get(key(Q[v] + g, R[v])), b = index.get(key(Q[v], R[v] + g))
    if (a !== undefined) { ux += verts[a].x - verts[v].x; uy += verts[a].y - verts[v].y; un++ }
    if (b !== undefined) { vx += verts[b].x - verts[v].x; vy += verts[b].y - verts[v].y; vn++ }
  }
  if (!un || !vn) return null
  ux /= un; uy /= un; vx /= vn; vy /= vn
  if (circle || extrapolateOffshore) {
    // Hull & offshore water buffer: mirror coastal/outermost samples outward across missing
    // water nodes (when land-masked) and beyond the study circle so contours & territories run
    // smoothly past every shoreline before the exact coastline and circle clips.
    const rings = extrapolateOffshore ? 3 : 2
    let frontier = verts.map((_, v) => v)
    for (let ring = 0; ring < rings; ring++) {
      const added = new Map()
      for (const v of frontier) {
        for (const [dq, dr] of DIRS) {
          const q = Q[v] + dq, r = R[v] + dr, k = key(q, r)
          if (index.has(k)) continue
          const x = verts[v].x + (dq * ux + dr * vx) / g, y = verts[v].y + (dq * uy + dr * vy) / g
          const rx = circle ? x - circle.x : 0, ry = circle ? y - circle.y : 0
          const rad = circle ? Math.hypot(rx, ry) : Infinity
          // A missing sample inside the circle stays an honest hole unless offshore water extrapolation is enabled.
          if (!extrapolateOffshore && circle && rad <= circle.r) continue
          const score = circle && rad > 1e-12 ? ((x - verts[v].x) * rx + (y - verts[v].y) * ry) / rad : 0
          const prev = added.get(k)
          if (!prev) {
            added.set(k, { q, r, x, y, from: v, score, rad, parents: [v] })
          } else {
            prev.parents.push(v)
            if (score > prev.score + 1e-12) { prev.from = v; prev.score = score }
          }
        }
      }
      frontier = []
      for (const [k, a] of added) {
        const id = verts.length
        verts.push({
          x: a.x, y: a.y, src: verts[a.from].src, real: false, hole: false,
          offshore: extrapolateOffshore && (!circle || a.rad <= circle.r),
          parents: a.parents,
        })
        Q.push(a.q); R.push(a.r)
        index.set(k, id)
        frontier.push(id)
      }
    }
  }
  const tris = []
  for (let v = 0; v < verts.length; v++) {
    const a = index.get(key(Q[v] + g, R[v])), b = index.get(key(Q[v], R[v] + g))
    const c = index.get(key(Q[v] + g, R[v] - g))
    if (a !== undefined && b !== undefined) tris.push(v, a, b)
    if (a !== undefined && c !== undefined) tris.push(v, c, a)
  }
  return tris
}

// Bowyer-Watson sweep (points sorted by x, finished triangles retired early).
function delaunayTriangles(pts) {
  const n = pts.length
  if (n < 3) return []
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const p of pts) {
    minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x)
    minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y)
  }
  const span = Math.max(maxX - minX, maxY - minY) || 1
  const midX = (minX + maxX) / 2, midY = (minY + maxY) / 2
  const all = pts.concat([{ x: midX - 20 * span, y: midY - span }, { x: midX, y: midY + 20 * span }, { x: midX + 20 * span, y: midY - span }])
  const circum = (a, b, c) => {
    const A = all[a], B = all[b], C = all[c]
    const bx = B.x - A.x, by = B.y - A.y, cx = C.x - A.x, cy = C.y - A.y
    const d = 2 * (bx * cy - by * cx)
    if (Math.abs(d) < 1e-300) return null
    const b2 = bx * bx + by * by, c2 = cx * cx + cy * cy
    const ox = (cy * b2 - by * c2) / d, oy = (bx * c2 - cx * b2) / d
    return { a, b, c, x: A.x + ox, y: A.y + oy, r2: ox * ox + oy * oy }
  }
  const order = pts.map((_, i) => i).sort((p, q) => pts[p].x - pts[q].x || pts[p].y - pts[q].y)
  let open = [circum(n, n + 1, n + 2)]
  const closed = []
  for (const i of order) {
    const p = all[i], edges = [], keep = []
    for (const t of open) {
      const dx = p.x - t.x
      if (dx > 0 && dx * dx > t.r2) { closed.push(t); continue }
      const dy = p.y - t.y
      if (dx * dx + dy * dy > t.r2) { keep.push(t); continue }
      edges.push([t.a, t.b], [t.b, t.c], [t.c, t.a])
    }
    const seen = new Map()
    for (const [a, b] of edges) {
      const k = a < b ? a * EDGE_KEY + b : b * EDGE_KEY + a
      seen.set(k, seen.has(k) ? null : [a, b])
    }
    for (const e of seen.values()) {
      if (!e) continue
      const t = circum(e[0], e[1], i)
      if (t) keep.push(t)
    }
    open = keep
  }
  const tris = []
  for (const t of closed.concat(open)) if (t.a < n && t.b < n && t.c < n) tris.push(t.a, t.b, t.c)
  return tris
}

// Nested or mixed rungs: Delaunay over every drawn sample, minus stretched triangles.
function scatteredTriangles(verts, circle, { extrapolateOffshore = false } = {}) {
  const nearest = list => list.map((a, i) => {
    let best = Infinity
    for (let j = 0; j < list.length; j++) {
      if (i === j) continue
      const d2 = (list[j].x - a.x) ** 2 + (list[j].y - a.y) ** 2
      if (d2 > 1e-24 && d2 < best) best = d2
    }
    return Math.sqrt(best)
  })
  const realSpacing = nearest(verts)
  if (circle || extrapolateOffshore) {
    let cos6 = 0, sin6 = 0
    for (let i = 0; i < verts.length; i++) {
      let best = Infinity, ang = 0
      for (let j = 0; j < verts.length; j++) {
        if (i === j) continue
        const dx = verts[j].x - verts[i].x, dy = verts[j].y - verts[i].y, d2 = dx * dx + dy * dy
        if (d2 > 1e-24 && d2 < best) { best = d2; ang = Math.atan2(dy, dx) }
      }
      cos6 += Math.cos(6 * ang); sin6 += Math.sin(6 * ang)
    }
    const base = Math.hypot(cos6, sin6) > 1e-6 ? Math.atan2(sin6, cos6) / 6 : 0
    const rings = extrapolateOffshore ? 2 : 1
    let frontier = verts.map((_, v) => ({ v, d: realSpacing[v] }))
    for (let ring = 0; ring < rings; ring++) {
      const added = new Map()
      for (const { v, d } of frontier) {
        if (!Number.isFinite(d)) continue
        for (let k = 0; k < 6; k++) {
          const x = verts[v].x + d * Math.cos(base + k * Math.PI / 3), y = verts[v].y + d * Math.sin(base + k * Math.PI / 3)
          const rx = circle ? x - circle.x : 0, ry = circle ? y - circle.y : 0
          const rad = circle ? Math.hypot(rx, ry) : Infinity
          if (!extrapolateOffshore && circle && rad <= circle.r) continue
          if (extrapolateOffshore && verts.some(e => Math.hypot(e.x - x, e.y - y) < d * .55)) continue
          const key = `${Math.round(x / (d * .5))},${Math.round(y / (d * .5))}`
          const score = circle && rad > 1e-12 ? ((x - verts[v].x) * rx + (y - verts[v].y) * ry) / rad : 0
          const prev = added.get(key)
          if (!prev) {
            added.set(key, { x, y, src: verts[v].src, score, d, rad, parents: [v] })
          } else {
            prev.parents.push(v)
            if (score > prev.score + 1e-12) { prev.src = verts[v].src; prev.score = score }
          }
        }
      }
      frontier = []
      for (const a of added.values()) {
        const id = verts.length
        verts.push({
          x: a.x, y: a.y, src: a.src, real: false, hole: false,
          offshore: extrapolateOffshore && (!circle || a.rad <= circle.r),
          parents: a.parents,
        })
        frontier.push({ v: id, d: a.d })
      }
    }
  }
  const spacing = verts.length === realSpacing.length ? realSpacing : nearest(verts)
  const floor = Math.min(...spacing.filter(Number.isFinite))
  // A fixed sub-pixel nudge settles cocircular lattice ties the same way every run.
  const nudged = verts.map((v, i) => ({
    x: v.x + ((i * 7919) % 1000 / 1000 - .5) * floor * 1e-6,
    y: v.y + ((i * 104729) % 1000 / 1000 - .5) * floor * 1e-6,
  }))
  const raw = delaunayTriangles(nudged), tris = []
  for (let t = 0; t < raw.length; t += 3) {
    const [a, b, c] = [raw[t], raw[t + 1], raw[t + 2]]
    const local = Math.max(spacing[a], spacing[b], spacing[c])
    const longest = Math.max(Math.hypot(verts[a].x - verts[b].x, verts[a].y - verts[b].y),
      Math.hypot(verts[b].x - verts[c].x, verts[b].y - verts[c].y), Math.hypot(verts[c].x - verts[a].x, verts[c].y - verts[a].y))
    if (longest <= 1.8 * local) tris.push(a, b, c)
  }
  return tris
}

// Shared sample mesh: measured points, copied-rank hull extensions beyond the study circle
// (plus offshore water buffer nodes when land-masked), and a closing skirt of empty apex vertices.
export function buildSampleMesh(points, project, { clipRadiusKm = null, anchorLatLng = null, extrapolateOffshore = false } = {}) {
  const verts = []
  for (let i = 0; i < (points?.length || 0); i++) {
    const pt = project([points[i].lat, points[i].lng])
    if (!pt || !Number.isFinite(pt.x) || !Number.isFinite(pt.y)) continue
    verts.push({ x: pt.x, y: pt.y, src: i, real: true, hole: false })
  }
  const realCount = verts.length
  if (realCount < 3) return null
  const circle = projectedCircle(project, clipRadiusKm, anchorLatLng)
  const tris = latticeTriangles(points, verts, circle, { extrapolateOffshore }) || scatteredTriangles(verts, circle, { extrapolateOffshore })
  // Uniform positive orientation: the owner of a vertex is always on the left of its border.
  const directed = new Map()
  for (let t = 0; t < tris.length; t += 3) {
    const A = verts[tris[t]], B = verts[tris[t + 1]], C = verts[tris[t + 2]]
    if ((B.x - A.x) * (C.y - A.y) - (B.y - A.y) * (C.x - A.x) < 0) [tris[t + 1], tris[t + 2]] = [tris[t + 2], tris[t + 1]]
    for (let k = 0; k < 3; k++) directed.set(tris[t + k] * EDGE_KEY + tris[t + (k + 1) % 3], true)
  }
  const meshVerts = verts.length
  // Skirt: one empty apex per boundary edge plus one wedge per boundary vertex.
  const incoming = new Map(), outgoing = new Map()
  for (const k of [...directed.keys()]) {
    const a = Math.floor(k / EDGE_KEY), b = k % EDGE_KEY
    if (directed.has(b * EDGE_KEY + a)) continue
    const A = verts[a], B = verts[b], dx = B.x - A.x, dy = B.y - A.y
    const apex = verts.length
    verts.push({ x: (A.x + B.x) / 2 + dy * Math.sqrt(3) / 2, y: (A.y + B.y) / 2 - dx * Math.sqrt(3) / 2, src: -1, real: false, hole: true })
    tris.push(b, a, apex)
    if (!incoming.has(b)) incoming.set(b, [])
    incoming.get(b).push({ other: a, apex })
    if (!outgoing.has(a)) outgoing.set(a, [])
    outgoing.get(a).push({ other: b, apex, used: false })
  }
  for (const [v, ins] of incoming) {
    const outs = outgoing.get(v) || []
    for (const edge of ins) {
      let pick = null, best = Infinity
      const ax = verts[edge.other].x - verts[v].x, ay = verts[edge.other].y - verts[v].y
      for (const out of outs) {
        if (out.used) continue
        const bx = verts[out.other].x - verts[v].x, by = verts[out.other].y - verts[v].y
        let turn = Math.atan2(ax * by - ay * bx, ax * bx + ay * by)
        if (turn <= 1e-12) turn += 2 * Math.PI
        if (turn < best) { best = turn; pick = out }
      }
      if (!pick) continue
      pick.used = true
      tris.push(v, edge.apex, pick.apex)
    }
  }
  // Integer edge table: borders are stitched by (edge id, side), never by float welding.
  const edgeIds = new Map(), edgeLo = [], edgeHi = [], triEdges = new Int32Array(tris.length)
  for (let t = 0; t < tris.length; t += 3) {
    for (let k = 0; k < 3; k++) {
      const a = tris[t + k], b = tris[t + (k + 1) % 3]
      const lo = Math.min(a, b), hi = Math.max(a, b), key = lo * EDGE_KEY + hi
      let id = edgeIds.get(key)
      if (id === undefined) { id = edgeLo.length; edgeIds.set(key, id); edgeLo.push(lo); edgeHi.push(hi) }
      triEdges[t + k] = id
    }
  }
  return { points, verts, realCount, meshVerts, tris, triEdges, edgeLo, edgeHi, circle }
}

// Generic label marching over the mesh. label[v] >= 0 names a region, HOLE names nothing.
// cut(e) returns the two fractions along edge e measured from its low vertex:
// [where the low vertex's region ends, where the high vertex's region begins].
// junction(t, k) may return a pinned corner for the region owning vertex k of triangle t.
function marchLabels(mesh, label, cut, junction = null) {
  const { verts, tris, triEdges, edgeLo, edgeHi } = mesh
  const E = edgeLo.length
  const px = new Float64Array(2 * E), py = new Float64Array(2 * E), ready = new Uint8Array(E)
  const edgePoint = (e, v) => {
    if (!ready[e]) {
      const [a, b] = cut(e), L = verts[edgeLo[e]], H = verts[edgeHi[e]]
      px[2 * e] = L.x + (H.x - L.x) * a; py[2 * e] = L.y + (H.y - L.y) * a
      px[2 * e + 1] = L.x + (H.x - L.x) * b; py[2 * e + 1] = L.y + (H.y - L.y) * b
      ready[e] = 1
    }
    return 2 * e + (edgeLo[e] === v ? 0 : 1)
  }
  const segFrom = [], segTo = [], segOwner = [], segMid = []
  const next = new Int32Array(2 * E).fill(-1)
  for (let t = 0; t < tris.length; t += 3) {
    const l0 = label[tris[t]], l1 = label[tris[t + 1]], l2 = label[tris[t + 2]]
    if (l0 === l1 && l1 === l2) continue
    for (let k = 0; k < 3; k++) {
      const a = tris[t + k], kb = (k + 1) % 3, kc = (k + 2) % 3, b = tris[t + kb], c = tris[t + kc]
      const la = label[a], lb = label[b], lc = label[c]
      if (la === HOLE || lc === la) continue
      // Edge ids: triEdges[t + k] joins (k, k + 1); triEdges[t + kc] joins (k + 2, k).
      let from, to, mid = null
      if (lb !== la) {
        from = edgePoint(triEdges[t + k], a)
        to = edgePoint(triEdges[t + kc], a)
        if (lb !== lc && junction) mid = junction(t, k, from, to, px, py)
      } else {
        from = edgePoint(triEdges[t + kb], b)
        to = edgePoint(triEdges[t + kc], a)
      }
      next[from] = segFrom.length
      segFrom.push(from); segTo.push(to); segOwner.push(a); segMid.push(mid)
    }
  }
  const loops = [], used = new Uint8Array(segFrom.length)
  for (let s0 = 0; s0 < segFrom.length; s0++) {
    if (used[s0]) continue
    const ring = []
    let s = s0, closed = false
    while (s >= 0 && !used[s]) {
      used[s] = 1
      ring.push({ x: px[segFrom[s]], y: py[segFrom[s]], pin: false })
      if (segMid[s]) ring.push({ x: segMid[s].x, y: segMid[s].y, pin: true })
      s = next[segTo[s]]
      if (s === s0) closed = true
    }
    if (!closed) continue
    const clean = []
    for (const p of ring) {
      const prev = clean[clean.length - 1]
      if (prev && prev.x === p.x && prev.y === p.y) { prev.pin = prev.pin || p.pin; continue }
      clean.push(p)
    }
    while (clean.length > 1 && clean[0].x === clean.at(-1).x && clean[0].y === clean.at(-1).y) {
      clean[0].pin = clean[0].pin || clean.at(-1).pin
      clean.pop()
    }
    if (clean.length >= 3) loops.push({ owner: segOwner[s0], ring: clean })
  }
  return { loops, px, py, ready }
}

// Clip closed loops (region on the left) to the true study circle. Inside chains are
// reconnected along the rim in 2 degree steps on shared global angles, so neighboring
// territories reuse identical rim vertices and the perimeter stays razor sharp.
function clipLoopsToCircle(rings, circle) {
  if (!circle) return rings
  const r2 = circle.r * circle.r, out = [], chains = []
  const inside = p => (p.x - circle.x) ** 2 + (p.y - circle.y) ** 2 <= r2
  const cross = (P, Q) => {
    const dx = Q.x - P.x, dy = Q.y - P.y, fx = P.x - circle.x, fy = P.y - circle.y
    const a = dx * dx + dy * dy, b = 2 * (fx * dx + fy * dy), c = fx * fx + fy * fy - r2
    const root = Math.sqrt(Math.max(0, b * b - 4 * a * c))
    let t = (-b - root) / (2 * a)
    if (!(t >= 0 && t <= 1)) t = (-b + root) / (2 * a)
    t = Math.min(1, Math.max(0, t))
    const x = P.x + dx * t, y = P.y + dy * t
    return { x, y, pin: true, angle: Math.atan2(y - circle.y, x - circle.x) }
  }
  for (const ring of rings) {
    const flags = ring.map(inside), n = ring.length
    if (flags.every(Boolean)) { out.push(ring); continue }
    if (!flags.some(Boolean)) continue
    let start = 0
    while (flags[start] || !flags[(start + 1) % n]) start++
    let chain = null
    for (let step = 0; step < n; step++) {
      const i = (start + step) % n, j = (i + 1) % n
      if (!flags[i] && flags[j]) chain = [cross(ring[i], ring[j])]
      if (flags[j] && chain) chain.push(ring[j])
      if (flags[i] && !flags[j] && chain) { chain.push(cross(ring[i], ring[j])); chains.push(chain); chain = null }
    }
  }
  const STEP = Math.PI / 90, TURN = 2 * Math.PI
  const pending = new Set(chains)
  while (pending.size) {
    const first = pending.values().next().value
    const ring = []
    let chain = first
    while (chain && pending.has(chain)) {
      pending.delete(chain)
      ring.push(...chain)
      const exit = chain.at(-1).angle
      let nextChain = first, gap = ((first[0].angle - exit) % TURN + TURN) % TURN
      for (const other of pending) {
        const g = ((other[0].angle - exit) % TURN + TURN) % TURN
        if (g < gap) { gap = g; nextChain = other }
      }
      for (let k = Math.floor(exit / STEP) + 1; k * STEP < exit + gap - 1e-9; k++) {
        if (k * STEP <= exit + 1e-9) continue
        ring.push({ x: circle.x + circle.r * Math.cos(k * STEP), y: circle.y + circle.r * Math.sin(k * STEP), pin: true })
      }
      chain = nextChain === first ? null : nextChain
    }
    if (ring.length >= 3) out.push(ring)
  }
  return out
}

function groupRings(mesh, label, loops) {
  const parent = mesh.verts.map((_, i) => i)
  const find = i => { while (parent[i] !== i) { parent[i] = parent[parent[i]]; i = parent[i] } return i }
  for (let e = 0; e < mesh.edgeLo.length; e++) {
    const a = mesh.edgeLo[e], b = mesh.edgeHi[e]
    if (label[a] !== HOLE && label[a] === label[b]) parent[find(a)] = find(b)
  }
  const groups = new Map()
  for (const loop of loops) {
    const root = find(loop.owner)
    if (!groups.has(root)) groups.set(root, { label: label[root], size: 0, rings: [] })
    groups.get(root).rings.push(loop.ring)
  }
  for (let v = 0; v < mesh.realCount; v++) {
    const group = label[v] !== HOLE && groups.get(find(v))
    if (group) group.size++
  }
  const out = []
  for (const group of groups.values()) {
    const rings = clipLoopsToCircle(group.rings, mesh.circle)
      .map(ring => ({ ring, area: polygonSignedArea(ring) }))
      .filter(r => Math.abs(r.area) > 1e-18)
      .sort((p, q) => q.area - p.area)
      .map(r => r.ring)
    if (rings.length && group.size) out.push({ label: group.label, size: group.size, rings })
  }
  return out
}

// Rank-independent preparation: mesh, first-place labels and a head-to-head rank cache.
// cellById values carry { winnerId (true rank 1), leaderId + kind 'ranked' + color when
// the territory is drawn, leaderName }. Points with no usable result become holes.
export function prepareHexTerritory(points, cellById, project, {
  clipRadiusKm = null,
  anchorLatLng = null,
  rankLookup = null,
  nameOf = null,
  extrapolateOffshore = false,
} = {}) {
  const mesh = buildSampleMesh(points, project, { clipRadiusKm, anchorLatLng, extrapolateOffshore })
  if (!mesh) return null
  const leaderIds = [], leaderIndex = new Map(), drawn = new Map(), names = []
  const label = new Int32Array(mesh.verts.length).fill(HOLE)
  for (let v = 0; v < mesh.meshVerts; v++) {
    const cell = cellById.get(points[mesh.verts[v].src].id)
    const id = cell?.winnerId ?? (cell?.kind === 'ranked' ? cell.leaderId : null)
    if (id == null) continue
    if (!leaderIndex.has(id)) {
      leaderIndex.set(id, leaderIds.length)
      leaderIds.push(id)
      names.push((typeof nameOf === 'function' && nameOf(id)) || cell.leaderName || String(id))
    }
    label[v] = leaderIndex.get(id)
    if (cell.kind === 'ranked' && cell.leaderId === id && !drawn.has(label[v])) drawn.set(label[v], cell.color)
  }
  // Uncorroborated single dots: no measured lattice neighbor shares the leader.
  const corroborated = new Uint8Array(mesh.verts.length)
  for (let e = 0; e < mesh.edgeLo.length; e++) {
    const a = mesh.edgeLo[e], b = mesh.edgeHi[e]
    if (a < mesh.realCount && b < mesh.realCount && label[a] !== HOLE && label[a] === label[b]) corroborated[a] = corroborated[b] = 1
  }
  const realOf = new Int32Array(points.length).fill(-1)
  for (let v = 0; v < mesh.realCount; v++) realOf[mesh.verts[v].src] = v
  const rankCache = new Map(), L = Math.max(1, leaderIds.length)
  // Rank of leader l at vertex v, capped at M + 1 (missing counts as M + 1).
  const rankAt = (v, l) => {
    const src = mesh.verts[v].src, key = src * L + l
    let rank = rankCache.get(key)
    if (rank === undefined) {
      const raw = label[realOf[src]] === l ? 1 : typeof rankLookup === 'function' ? rankLookup(points[src], leaderIds[l]) : null
      rank = Number.isFinite(raw) && raw >= 1 ? raw : null
      rankCache.set(key, rank)
    }
    return rank
  }
  const capped = (v, l) => Math.min(rankAt(v, l) ?? TERRITORY_LEAD_CAP + 1, TERRITORY_LEAD_CAP + 1)
  const lead = (v, l) => Math.max(1, capped(v, l) - 1)
  const lone = v => !corroborated[realOf[mesh.verts[v].src]]
  return { mesh, label, leaderIds, names, drawn, rankAt, capped, lead, lone }
}

const sideOf = (ax, ay, bx, by, px, py) => (bx - ax) * (py - ay) - (by - ay) * (px - ax)
function insideTriangle(px, py, ax, ay, bx, by, cx, cy, eps) {
  const d1 = sideOf(ax, ay, bx, by, px, py), d2 = sideOf(bx, by, cx, cy, px, py), d3 = sideOf(cx, cy, ax, ay, px, py)
  return (d1 >= -eps && d2 >= -eps && d3 >= -eps) || (d1 <= eps && d2 <= eps && d3 <= eps)
}

export function hexTerritoryFromPrep(prep, tau = 0) {
  if (!prep) return { outlines: [], seams: [] }
  const { mesh, label, leaderIds, names, drawn, rankAt, capped, lead, lone } = prep
  const { verts, tris, triEdges, edgeLo, edgeHi } = mesh
  tau = Math.min(1, Math.max(0, Number(tau) || 0))
  const reach = (e, t) => {
    const i = edgeLo[e], j = edgeHi[e]
    if (label[i] === HOLE || label[j] === HOLE) return [.5, .5]
    const [a, b] = headToHeadReach(lead(i, label[j]), lead(j, label[i]), lone(i), lone(j), t)
    return [a, 1 - b]
  }
  const cut = e => reach(e, tau)
  // Triple junction: the point where all three head-to-head scores tie, then each
  // leader's own corner retreats along its rank-computed direction as TAU grows.
  const junction = (t, k, from, to, px, py) => {
    const v = [tris[t], tris[t + 1], tris[t + 2]]
    const X = [verts[v[0]].x, verts[v[1]].x, verts[v[2]].x], Y = [verts[v[0]].y, verts[v[1]].y, verts[v[2]].y]
    // TAU = 0 tie points on the three edges, shared by all three leaders.
    const ties = [0, 1, 2].map(m => {
      const e = triEdges[t + m], f = reach(e, 0)[0], lo = verts[edgeLo[e]], hi = verts[edgeHi[e]]
      return [lo.x + (hi.x - lo.x) * f, lo.y + (hi.y - lo.y) * f]
    })
    let jx = (ties[0][0] + ties[1][0] + ties[2][0]) / 3, jy = (ties[0][1] + ties[1][1] + ties[2][1]) / 3
    let vx = 0, vy = 0
    const labels = v.map(i => label[i])
    if (!labels.includes(HOLE)) {
      const score = m => v.map(i => -capped(i, labels[m]))
      const solve = (own, p, q, r1, r2) => {
        const s0 = score(own), s1 = score(p), s2 = score(q)
        const d1 = [0, 1, 2].map(m => s0[m] - s1[m]), d2 = [0, 1, 2].map(m => s0[m] - s2[m])
        const a11 = d1[0] - d1[2], a12 = d1[1] - d1[2], a21 = d2[0] - d2[2], a22 = d2[1] - d2[2]
        const det = a11 * a22 - a12 * a21
        if (Math.abs(det) < 1e-9) return null
        const u1 = r1 === null ? -d1[2] : r1, u2 = r2 === null ? -d2[2] : r2
        const b0 = (u1 * a22 - a12 * u2) / det, b1 = (a11 * u2 - u1 * a21) / det
        return [b0, b1]
      }
      const tie = solve(k, (k + 1) % 3, (k + 2) % 3, null, null)
      if (tie) {
        // The tie point is the same for all three leaders: solve it from vertex 0 for exact reuse.
        const shared = solve(0, 1, 2, null, null)
        if (shared && shared[0] > .02 && shared[1] > .02 && 1 - shared[0] - shared[1] > .02) {
          jx = shared[0] * X[0] + shared[1] * X[1] + (1 - shared[0] - shared[1]) * X[2]
          jy = shared[0] * Y[0] + shared[1] * Y[1] + (1 - shared[0] - shared[1]) * Y[2]
        }
        const vel = solve(k, (k + 1) % 3, (k + 2) % 3, 1, 1)
        if (vel) {
          vx = vel[0] * (X[0] - X[2]) + vel[1] * (X[1] - X[2])
          vy = vel[0] * (Y[0] - Y[2]) + vel[1] * (Y[1] - Y[2])
        }
      }
    }
    if (tau <= 0) return { x: jx, y: jy }
    const ax = X[k], ay = Y[k], eps = 1e-9 * Math.abs(sideOf(X[0], Y[0], X[1], Y[1], X[2], Y[2]))
    const tieNext = ties[k], tiePrev = ties[(k + 2) % 3]
    const cx = jx + tau * vx, cy = jy + tau * vy
    const beyond = (qx, qy) => sideOf(px[from], py[from], px[to], py[to], qx, qy) * sideOf(px[from], py[from], px[to], py[to], ax, ay) < 0
    const inCell = insideTriangle(cx, cy, ax, ay, tieNext[0], tieNext[1], jx, jy, eps) || insideTriangle(cx, cy, ax, ay, jx, jy, tiePrev[0], tiePrev[1], eps)
    const tieBeyond = beyond(jx, jy)
    if (inCell && (beyond(cx, cy) || !tieBeyond)) return { x: cx, y: cy }
    // Otherwise under-claim safely: the straight chord, or the shared tie corner when the chord would overreach.
    return tieBeyond ? null : { x: jx, y: jy }
  }
  const marched = marchLabels(mesh, label, cut, junction)
  const outlines = []
  for (const group of groupRings(mesh, label, marched.loops)) {
    if (!drawn.has(group.label)) continue
    outlines.push({ leaderId: leaderIds[group.label], color: drawn.get(group.label), size: group.size,
      rings: group.rings, contourSmooth: true, tectonic: true })
  }
  // Seam metadata for hover: one record per unlike-leader edge between two measured points.
  const seams = []
  for (let e = 0; e < edgeLo.length; e++) {
    const a = edgeLo[e], b = edgeHi[e]
    if (a >= mesh.realCount || b >= mesh.realCount || label[a] === HOLE || label[b] === HOLE || label[a] === label[b]) continue
    const [fa, fb] = cut(e), A = verts[a], B = verts[b]
    const p1 = { x: A.x + (B.x - A.x) * fa, y: A.y + (B.y - A.y) * fa }, p2 = { x: A.x + (B.x - A.x) * fb, y: A.y + (B.y - A.y) * fb }
    seams.push({ aIdx: A.src, bIdx: B.src, leaderA: leaderIds[label[a]], leaderB: leaderIds[label[b]],
      nameA: names[label[a]], nameB: names[label[b]], rankBatA: rankAt(a, label[b]), rankAatB: rankAt(b, label[a]),
      p1, p2, mid: { x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2 }, reachA: fa, reachB: 1 - fb, gapFrac: Math.max(0, fb - fa),
      a: { x: A.x, y: A.y }, b: { x: B.x, y: B.y } })
  }
  return { outlines, seams }
}

// Territory outlines for hexagonal (uniform or mixed-rung) studies. Returns the outline
// list with the hover seams attached as `.seams`. `tau` runs 0 (flush) to 1 (contested ground).
export function hexTerritoryOutlines(points, cellById, project, options = {}) {
  const { outlines, seams } = hexTerritoryFromPrep(prepareHexTerritory(points, cellById, project, options), options.tau ?? 0)
  outlines.seams = seams
  return outlines
}

// One shared path for canvas and tests: quadratic smoothing through edge midpoints on
// regular bends, with pinned corners (triple junctions, rim vertices) left exact.
export function traceTerritoryRing(ring, sink) {
  const n = ring.length
  if (n < 3) return
  const anchor = (a, b) => b.pin ? b : a.pin ? a : { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
  const first = ring[0].pin ? ring[0] : anchor(ring[0], ring[n - 1])
  sink.moveTo(first.x, first.y)
  for (let i = 0; i < n; i++) {
    const curr = ring[i], next = ring[(i + 1) % n]
    if (curr.pin) { sink.lineTo(curr.x, curr.y); continue }
    const end = anchor(curr, next)
    sink.quadraticCurveTo(curr.x, curr.y, end.x, end.y)
  }
  sink.closePath()
}

// The same rendered outline as a polyline, for hit tests and acceptance tests.
export function flattenTerritoryRing(ring, steps = 6) {
  const out = []
  let last = null
  traceTerritoryRing(ring, {
    moveTo(x, y) { last = { x, y }; out.push(last) },
    lineTo(x, y) { if (last.x !== x || last.y !== y) { last = { x, y }; out.push(last) } },
    quadraticCurveTo(cx, cy, x, y) {
      const from = last
      for (let s = 1; s <= steps; s++) {
        const t = s / steps, u = 1 - t
        out.push({ x: u * u * from.x + 2 * u * t * cx + t * t * x, y: u * u * from.y + 2 * u * t * cy + t * t * y })
      }
      last = { x, y }
    },
    closePath() {},
  })
  return out
}

export function pointInRings(rings, x, y) {
  let inside = false
  for (const ring of rings) {
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const a = ring[i], b = ring[j]
      if ((a.y > y) !== (b.y > y) && x < (b.x - a.x) * (y - a.y) / (b.y - a.y) + a.x) inside = !inside
    }
  }
  return inside
}

function hasLandMask(model) {
  const mask = model?.landMaskPolygons || model?.land_mask_polygons
  return Array.isArray(mask) && mask.length > 0
}

// Extrapolate scalar rank values smoothly into offshore water buffer vertices via
// wavefront neighbor averaging (keeping unranked > depth only when adjacent coastal pins are unranked).
function extrapolateRankValues(mesh, ranks, missing, extrapolateOffshore) {
  const values = new Float64Array(mesh.verts.length)
  values.fill(missing)
  for (let v = 0; v < mesh.realCount; v++) {
    values[v] = ranks[mesh.verts[v].src] ?? missing
  }
  for (let v = mesh.realCount; v < mesh.meshVerts; v++) {
    const parents = mesh.verts[v].parents
    if (extrapolateOffshore && parents?.length) {
      let sum = 0
      for (const p of parents) sum += values[p]
      values[v] = sum / parents.length
    } else {
      values[v] = ranks[mesh.verts[v].src] ?? missing
    }
  }
  return values
}

// Business focus: where one business holds the 3-pack (rank <= 3) and the top 10, traced
// by marching triangles on its own measured rank (missing = depth + 1) at the half-integer
// levels 3.5 and 10.5, plus the flip counts behind the stat bar.
export function computeFocusOverlay(model, lane, businessCid, { project = mercatorZoom0, extrapolateOffshore = hasLandMask(model) } = {}) {
  const hexStudy = model.geometry === 'hex_radius'
  const points = model.points.filter(p => (!hexStudy || p.hex) && p.observations?.[lane]?.status !== 'missing')
  const anchor = model.businesses?.find(b => b.id === model.targetId)
  const center = Number.isFinite(anchor?.lat) && Number.isFinite(anchor?.lng) ? [anchor.lat, anchor.lng]
    : model.sampling?.center ? [model.sampling.center.lat, model.sampling.center.lng] : null
  const mesh = buildSampleMesh(points, project, { clipRadiusKm: model.sampling?.radius_km || null, anchorLatLng: center, extrapolateOffshore })
  const missing = (model.depth || 20) + 1
  const usable = o => o && !['pending', 'missing', 'missing_result', 'error', 'provider_error', 'empty_results'].includes(o.status)
  const ranks = points.map(p => {
    const o = p.observations?.[lane]
    if (!usable(o)) return null
    const rank = businessCid === model.targetId ? o.targetRank : o.items?.find(item => item.id === businessCid)?.rank
    return Number.isFinite(rank) && rank >= 1 ? rank : null
  })
  const stats = { wins: 0, top3Count: 0, top10Count: 0, top20Count: 0, indexedCount: 0, rank2Points: [], rank3Points: [], adjacentRank2Count: 0, topBlocker: null }
  const blockers = new Map()
  points.forEach((p, i) => {
    const r = ranks[i]
    if (r != null) {
      stats.indexedCount++
      if (r <= 20) stats.top20Count++
      if (r <= 10) stats.top10Count++
      if (r <= 3) stats.top3Count++
    }
    if (r === 1) stats.wins++
    else if (r === 3) stats.rank3Points.push(p.id)
    else if (r === 2) {
      stats.rank2Points.push(p.id)
      const top = p.observations[lane].items?.find(item => item.rank === 1)
      if (top) {
        const row = blockers.get(top.id) || { id: top.id, name: top.name, count: 0 }
        row.count++
        blockers.set(top.id, row)
      }
    }
  })
  for (const row of blockers.values()) if (!stats.topBlocker || row.count > stats.topBlocker.count) stats.topBlocker = row
  const result = { businessId: businessCid, crown: [], plateau: [], reach: [], page1: [], horizon: [], stats }
  if (!mesh) return result
  const vertValues = extrapolateRankValues(mesh, ranks, missing, extrapolateOffshore)
  const value = v => vertValues[v]
  const frontier = new Set()
  for (let e = 0; e < mesh.edgeLo.length; e++) {
    const a = mesh.edgeLo[e], b = mesh.edgeHi[e]
    if (a >= mesh.realCount || b >= mesh.realCount) continue
    if (value(a) === 1 && value(b) === 2) frontier.add(b)
    if (value(b) === 1 && value(a) === 2) frontier.add(a)
  }
  stats.adjacentRank2Count = frontier.size
  const contour = level => {
    const label = new Int32Array(mesh.verts.length).fill(HOLE)
    for (let v = 0; v < mesh.meshVerts; v++) if (value(v) < level) label[v] = 0
    const cut = e => {
      const lo = mesh.edgeLo[e], hi = mesh.edgeHi[e]
      if (mesh.verts[lo].hole || mesh.verts[hi].hole) return [.5, .5]
      const f = (level - value(lo)) / (value(hi) - value(lo))
      return [f, f]
    }
    return groupRings(mesh, label, marchLabels(mesh, label, cut).loops).map(g => ({ size: g.size, rings: g.rings }))
  }
  result.crown = contour(1.5)
  result.plateau = contour(3.5)
  result.reach = contour(10.5)
  result.page1 = contour(20.5)
  result.horizon = (model.depth || 20) >= 30 ? contour(30.5) : []
  return result
}

// Full 1..depth hypsometric topographic elevation stack (half-integer contours 1.5 .. depth+0.5)
// for Rankings mode, plus generalized scalar elevation when { valueAt, thresholds } are passed.
// Because adjacent levels are strictly nested, consecutive pairs define exact non-overlapping
// elevation bands with zero alpha stacking via evenodd fill.
const elevationCache = new WeakMap()
export function computeScalarElevation(model, lane, {
  valueAt,
  thresholds,
  compare = 'gte',
  missingValue = 0,
  project = mercatorZoom0,
  extrapolateOffshore = hasLandMask(model),
} = {}) {
  const hexStudy = model.geometry === 'hex_radius'
  const points = model.points.filter(p => (!hexStudy || p.hex) && p.observations?.[lane]?.status !== 'missing')
  const anchor = model.businesses?.find(b => b.id === model.targetId)
  const center = Number.isFinite(anchor?.lat) && Number.isFinite(anchor?.lng) ? [anchor.lat, anchor.lng]
    : model.sampling?.center ? [model.sampling.center.lat, model.sampling.center.lng] : null
  const mesh = buildSampleMesh(points, project, { clipRadiusKm: model.sampling?.radius_km || null, anchorLatLng: center, extrapolateOffshore })
  const levels = []
  if (!mesh || !Array.isArray(thresholds) || !thresholds.length || typeof valueAt !== 'function') {
    return { mode: 'scalar', compare, levels }
  }
  const rawValues = points.map(p => {
    const v = valueAt(p)
    return Number.isFinite(v) ? v : null
  })
  const vertValues = extrapolateRankValues(mesh, rawValues, missingValue, extrapolateOffshore)
  const value = v => vertValues[v]
  // Order levels innermost (most exclusive) to outermost (broadest) for evenodd band subtraction.
  const ordered = compare === 'gte'
    ? [...thresholds].sort((a, b) => b - a)
    : [...thresholds].sort((a, b) => a - b)

  const contour = level => {
    const label = new Int32Array(mesh.verts.length).fill(HOLE)
    let insideCount = 0
    for (let v = 0; v < mesh.meshVerts; v++) {
      const ok = compare === 'gte' ? value(v) >= level : value(v) < level
      if (ok) { label[v] = 0; insideCount++ }
    }
    if (!insideCount) return []
    const cut = e => {
      const lo = mesh.edgeLo[e], hi = mesh.edgeHi[e]
      if (mesh.verts[lo].hole || mesh.verts[hi].hole) return [.5, .5]
      const va = value(lo), vb = value(hi)
      if (vb === va) return [.5, .5]
      const f = Math.max(.02, Math.min(.98, (level - va) / (vb - va)))
      return [f, f]
    }
    return groupRings(mesh, label, marchLabels(mesh, label, cut).loops).map(g => ({ size: g.size, rings: g.rings }))
  }

  for (const threshold of ordered) {
    levels.push({ rank: threshold, value: threshold, parts: contour(threshold) })
  }
  return { mode: 'scalar', compare, levels }
}

// Trace exact circle-clipped polygon region(s) for any subset of pins (fortress, detached landmass, service gap, thin hold).
export function computePinRegion(model, lane, predicate, {
  project = mercatorZoom0,
  extrapolateOffshore = hasLandMask(model),
} = {}) {
  const hexStudy = model.geometry === 'hex_radius'
  const points = model.points.filter(p => (!hexStudy || p.hex) && p.observations?.[lane]?.status !== 'missing')
  const anchor = model.businesses?.find(b => b.id === model.targetId)
  const center = Number.isFinite(anchor?.lat) && Number.isFinite(anchor?.lng) ? [anchor.lat, anchor.lng]
    : model.sampling?.center ? [model.sampling.center.lat, model.sampling.center.lng] : null
  const mesh = buildSampleMesh(points, project, { clipRadiusKm: model.sampling?.radius_km || null, anchorLatLng: center, extrapolateOffshore })
  if (!mesh || typeof predicate !== 'function') return []
  const flags = points.map(p => (predicate(p) ? 1 : 0))
  const label = new Int32Array(mesh.verts.length).fill(HOLE)
  let insideCount = 0
  for (let v = 0; v < mesh.meshVerts; v++) {
    const src = mesh.verts[v].src
    if (src >= 0 && flags[src]) { label[v] = 0; insideCount++ }
  }
  if (!insideCount) return []
  const cut = () => [.5, .5]
  return groupRings(mesh, label, marchLabels(mesh, label, cut).loops).map(g => ({ size: g.size, rings: g.rings }))
}

// Campaign flip seams: hex borders between a hold pin (r <= 3) and a rank 4 or 5 pin,
// and between rank 3 and a stronger rank 4. Returns edges formatted for RankCanvasLayer seam drawing & hover.
export function computeCampaignSeams(model, lane, cellById, {
  project = mercatorZoom0,
  extrapolateOffshore = hasLandMask(model),
  targetName = 'Primary',
} = {}) {
  const hexStudy = model.geometry === 'hex_radius'
  const points = model.points.filter(p => (!hexStudy || p.hex) && p.observations?.[lane]?.status !== 'missing')
  const anchor = model.businesses?.find(b => b.id === model.targetId)
  const center = Number.isFinite(anchor?.lat) && Number.isFinite(anchor?.lng) ? [anchor.lat, anchor.lng]
    : model.sampling?.center ? [model.sampling.center.lat, model.sampling.center.lng] : null
  const mesh = buildSampleMesh(points, project, { clipRadiusKm: model.sampling?.radius_km || null, anchorLatLng: center, extrapolateOffshore })
  if (!mesh || !cellById) return []

  // Map each mesh edge to its adjacent triangle centroids to form clean hex-border seam segments.
  const edgeTris = Array.from({ length: mesh.edgeLo.length }, () => [])
  for (let t = 0; t < mesh.tris.length; t += 3) {
    const A = mesh.verts[mesh.tris[t]], B = mesh.verts[mesh.tris[t + 1]], C = mesh.verts[mesh.tris[t + 2]]
    const cx = (A.x + B.x + C.x) / 3, cy = (A.y + B.y + C.y) / 3
    for (let k = 0; k < 3; k++) edgeTris[mesh.triEdges[t + k]].push({ x: cx, y: cy })
  }

  const seams = []
  for (let e = 0; e < mesh.edgeLo.length; e++) {
    const a = mesh.edgeLo[e], b = mesh.edgeHi[e]
    if (a >= mesh.realCount || b >= mesh.realCount) continue
    const ptA = points[mesh.verts[a].src], ptB = points[mesh.verts[b].src]
    const cA = cellById.get(ptA.id), cB = cellById.get(ptB.id)
    if (!cA || !cB || cA.zone === 'unknown' || cB.zone === 'unknown') continue
    if ((cA.landmass && cA.landmass !== 'home' && cA.landmass !== 'unknown') ||
        (cB.landmass && cB.landmass !== 'home' && cB.landmass !== 'unknown')) continue
    const rA = cA.rank, rB = cB.rank
    if (!Number.isInteger(rA) || !Number.isInteger(rB)) continue
    const aHold = rA <= 3, bHold = rB <= 3
    const aSeam = rA === 4 || rA === 5, bSeam = rB === 4 || rB === 5
    const isFlipSeam = (aHold && bSeam) || (bHold && aSeam)
    if (!isFlipSeam) continue

    const holdCell = aHold ? cA : cB
    const seamCell = aHold ? cB : cA
    const holdPt = aHold ? ptA : ptB
    const seamPt = aHold ? ptB : ptA
    const holdVert = mesh.verts[aHold ? a : b]
    const seamVert = mesh.verts[aHold ? b : a]

    const duals = edgeTris[e]
    let p1, p2
    if (duals.length >= 2) {
      p1 = duals[0]
      p2 = duals[1]
    } else {
      const mx = (holdVert.x + seamVert.x) / 2, my = (holdVert.y + seamVert.y) / 2
      const dx = seamVert.x - holdVert.x, dy = seamVert.y - holdVert.y
      p1 = { x: mx - dy * .28, y: my + dx * .28 }
      p2 = { x: mx + dy * .28, y: my - dx * .28 }
    }
    const mid = { x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2 }
    const rival = seamCell.mustPass?.[0] || null
    const rivalName = rival?.name || 'Pack holder'
    const rivalRankAtSeam = rival?.rank ?? 3
    const holdObs = holdPt.observations?.[lane]?.items || []
    const rivalRankAtHold = rival ? (holdObs.find(i => i.id === rival.id)?.rank ?? null) : null
    seams.push({
      campaignSeam: true,
      aIdx: holdVert.src,
      bIdx: seamVert.src,
      holdPinId: holdPt.id,
      seamPinId: seamPt.id,
      playId: seamCell.play,
      thin: holdCell.rank === 3,
      a: { x: holdVert.x, y: holdVert.y },
      b: { x: seamVert.x, y: seamVert.y },
      p1,
      p2,
      mid,
      nameA: targetName,
      nameB: rivalName,
      rankAatHold: holdCell.rank,
      rankAatSeam: seamCell.rank,
      rankBatA: rivalRankAtHold,
      rankAatB: seamCell.rank,
      rivalRankAtSeam,
      gapRanks: seamCell.rank - 3,
      gapFrac: 0,
    })
  }
  return seams
}

export function computeElevationStack(model, lane, businessCid, {
  project = mercatorZoom0,
  extrapolateOffshore = hasLandMask(model),
  valueAt = null,
  thresholds = null,
  compare = 'gte',
  missingValue = 0,
} = {}) {
  if (typeof valueAt === 'function' && Array.isArray(thresholds)) {
    return computeScalarElevation(model, lane, { valueAt, thresholds, compare, missingValue, project, extrapolateOffshore })
  }
  const depth = Math.min(30, Math.max(10, model.depth || 20))
  const cacheKey = `${lane}:${businessCid}:${depth}:${extrapolateOffshore ? 1 : 0}`
  if (!elevationCache.has(model)) elevationCache.set(model, new Map())
  const byKey = elevationCache.get(model)
  if (byKey.has(cacheKey)) return byKey.get(cacheKey)

  const hexStudy = model.geometry === 'hex_radius'
  const points = model.points.filter(p => (!hexStudy || p.hex) && p.observations?.[lane]?.status !== 'missing')
  const anchor = model.businesses?.find(b => b.id === model.targetId)
  const center = Number.isFinite(anchor?.lat) && Number.isFinite(anchor?.lng) ? [anchor.lat, anchor.lng]
    : model.sampling?.center ? [model.sampling.center.lat, model.sampling.center.lng] : null
  const mesh = buildSampleMesh(points, project, { clipRadiusKm: model.sampling?.radius_km || null, anchorLatLng: center, extrapolateOffshore })
  const missing = depth + 1
  const usable = o => o && !['pending', 'missing', 'missing_result', 'error', 'provider_error', 'empty_results'].includes(o.status)
  const ranks = points.map(p => {
    const o = p.observations?.[lane]
    if (!usable(o)) return null
    const rank = businessCid === model.targetId ? o.targetRank : o.items?.find(item => item.id === businessCid)?.rank
    return Number.isFinite(rank) && rank >= 1 ? rank : null
  })

  const stats = { wins: 0, top3Count: 0, page1Count: 0, page2Count: 0, page3Count: 0, topBlocker: null }
  const blockers = new Map()
  let maxPresentRank = 0
  points.forEach((p, i) => {
    const r = ranks[i]
    if (r != null && r <= depth) {
      if (r > maxPresentRank) maxPresentRank = r
      if (r === 1) stats.wins++
      if (r <= 3) stats.top3Count++
      if (r <= 10) stats.page1Count++
      else if (r <= 20) stats.page2Count++
      else if (r <= 30) stats.page3Count++
    }
    if (r === 2) {
      const top = p.observations[lane].items?.find(item => item.rank === 1)
      if (top) {
        const row = blockers.get(top.id) || { id: top.id, name: top.name, count: 0 }
        row.count++
        blockers.set(top.id, row)
      }
    }
  })
  for (const row of blockers.values()) if (!stats.topBlocker || row.count > stats.topBlocker.count) stats.topBlocker = row

  const levels = []
  if (mesh && maxPresentRank >= 1) {
    const vertValues = extrapolateRankValues(mesh, ranks, missing, extrapolateOffshore)
    const value = v => vertValues[v]
    const contour = level => {
      const label = new Int32Array(mesh.verts.length).fill(HOLE)
      let insideCount = 0
      for (let v = 0; v < mesh.meshVerts; v++) {
        if (value(v) < level) { label[v] = 0; insideCount++ }
      }
      if (!insideCount) return []
      const cut = e => {
        const lo = mesh.edgeLo[e], hi = mesh.edgeHi[e]
        if (mesh.verts[lo].hole || mesh.verts[hi].hole) return [.5, .5]
        const f = (level - value(lo)) / (value(hi) - value(lo))
        return [f, f]
      }
      return groupRings(mesh, label, marchLabels(mesh, label, cut).loops).map(g => ({ size: g.size, rings: g.rings }))
    }
    for (let rank = 1; rank <= depth; rank++) {
      levels.push({ rank, parts: contour(rank + .5) })
    }
  }
  const out = { businessId: businessCid, depth, levels, stats }
  byKey.set(cacheKey, out)
  return out
}

// Internal topographic relief ("Fortress Core vs Thin Ice") inside every leader's territory.
// Measures real neighborhood dominance for each #1 point:
//   - interiorFrac: share of lattice neighbors also won by the same leader (0..1)
//   - runnerGap: how far the point's #2 runner-up falls across its immediate lattice neighbors (0..1)
// Returns Map<leaderId, Array<{ tier: number, parts: Array }>> clipped to the study circle.
const reliefCache = new WeakMap()
export function computeLeaderRelief(model, lane, { project = mercatorZoom0, extrapolateOffshore = hasLandMask(model) } = {}) {
  const cacheKey = `${lane}:${extrapolateOffshore ? 1 : 0}`
  if (!reliefCache.has(model)) reliefCache.set(model, new Map())
  const byLane = reliefCache.get(model)
  if (byLane.has(cacheKey)) return byLane.get(cacheKey)

  const hexStudy = model.geometry === 'hex_radius'
  const points = model.points.filter(p => (!hexStudy || p.hex) && p.observations?.[lane]?.status !== 'missing')
  const anchor = model.businesses?.find(b => b.id === model.targetId)
  const center = Number.isFinite(anchor?.lat) && Number.isFinite(anchor?.lng) ? [anchor.lat, anchor.lng]
    : model.sampling?.center ? [model.sampling.center.lat, model.sampling.center.lng] : null
  const mesh = buildSampleMesh(points, project, { clipRadiusKm: model.sampling?.radius_km || null, anchorLatLng: center, extrapolateOffshore })
  const out = new Map()
  if (!mesh) { byLane.set(cacheKey, out); return out }

  const usable = o => o && !['pending', 'missing', 'missing_result', 'error', 'provider_error', 'empty_results'].includes(o.status)
  const top1 = points.map(p => {
    const o = p.observations?.[lane]
    return usable(o) ? (o.items?.find(item => item.rank === 1)?.id ?? null) : null
  })
  const top2 = points.map(p => {
    const o = p.observations?.[lane]
    return usable(o) ? (o.items?.find(item => item.rank === 2)?.id ?? null) : null
  })

  // Build real-vertex adjacency from mesh edges.
  const nbrs = Array.from({ length: points.length }, () => [])
  for (let e = 0; e < mesh.edgeLo.length; e++) {
    const a = mesh.edgeLo[e], b = mesh.edgeHi[e]
    if (a >= mesh.realCount || b >= mesh.realCount) continue
    nbrs[a].push(b)
    nbrs[b].push(a)
  }

  // Compute real Fortress Security score (1..10) at each ranked point.
  const scores = new Float64Array(points.length)
  const winsByLeader = new Map()
  for (let i = 0; i < points.length; i++) {
    const lid = top1[i]
    if (!lid) continue
    winsByLeader.set(lid, (winsByLeader.get(lid) || 0) + 1)
    const ns = nbrs[i]
    let same = 0, rSum = 0
    const runner = top2[i]
    for (const j of ns) {
      if (top1[j] === lid) same++
      if (runner) {
        const no = points[j].observations?.[lane]
        const rr = usable(no) ? (no.items?.find(item => item.id === runner)?.rank ?? 11) : 11
        rSum += Math.min(11, rr)
      } else {
        rSum += 11
      }
    }
    const interiorFrac = ns.length ? same / ns.length : 0
    const runnerAvg = ns.length ? rSum / ns.length : 11
    const runnerGap = Math.max(0, Math.min(1, (runnerAvg - 2) / 3))
    scores[i] = 1 + 4.5 * interiorFrac + 4.5 * runnerGap
  }

  const thresholds = [4.2, 6.2, 7.8]
  for (const [lid, wins] of winsByLeader) {
    if (wins < 4) continue
    const val = v => {
      const src = mesh.verts[v].src
      return top1[src] === lid ? scores[src] : 0
    }
    const tiers = []
    for (let ti = 0; ti < thresholds.length; ti++) {
      const level = thresholds[ti]
      const label = new Int32Array(mesh.verts.length).fill(HOLE)
      let inside = 0
      for (let v = 0; v < mesh.meshVerts; v++) {
        if (val(v) >= level) { label[v] = 0; inside++ }
      }
      if (!inside) continue
      const cut = e => {
        const lo = mesh.edgeLo[e], hi = mesh.edgeHi[e]
        if (mesh.verts[lo].hole || mesh.verts[hi].hole) return [.5, .5]
        const va = val(lo), vb = val(hi)
        const f = vb === va ? .5 : Math.max(.08, Math.min(.92, (level - va) / (vb - va)))
        return [f, f]
      }
      const parts = groupRings(mesh, label, marchLabels(mesh, label, cut).loops).map(g => ({ size: g.size, rings: g.rings }))
      if (parts.length) tiers.push({ tier: ti, parts })
    }
    if (tiers.length) out.set(lid, tiers)
  }

  byLane.set(cacheKey, out)
  return out
}

// ---------- Honeycomb (hex_radius) studies: the locked 6 -> 6 -> 3 layers ----------
// sqrt(3) even-resolution refinement on a triangular fine lattice with spacing S/3
// and integer coordinates (a, b):
//   real data : a = 0 and b = 0 (mod 3)
//   layer 2   : (a - b) = 0 (mod 3) but not real (triangle centers, S/sqrt3 from real)
//   layer 3   : (a - b) != 0 (mod 3) (1/3 and 2/3 points of every dot-to-dot edge)
// Sizes are corner radii as shares of the view spacing S (v6 ladder: star .24 >
// real .13 > layer 2 .075 > layer 3 .045, small enough to keep the basemap readable). `inner` is the radius share
// of the vertices between corners: .36 pulls the 6 inner valleys close to center for a sharp tactical
// 6-pointed star rotated to 0 deg so all 6 tips aim directly at the 6 surrounding hexagons (0, 60, ..., 300 deg),
// cos 30 turns a 6-point outline into a hexagon, and cos 60 turns a 3-point outline into a triangle.
const HONEYCOMB_DEG = Math.PI / 180
export const HONEYCOMB_SHAPES = {
  marker: { r: .24, n: 6, inner: .36, rot: 0, line: 1 },
  1: { r: .13, n: 6, inner: Math.cos(30 * HONEYCOMB_DEG), rot: 30, line: 1 },
  2: { r: .075, n: 6, inner: Math.cos(30 * HONEYCOMB_DEG), rot: 0, line: .6 },
  3: { r: .045, n: 3, inner: Math.cos(60 * HONEYCOMB_DEG), rot: 0, line: .45 },
}
// An estimate fainter than this is not drawn.
export const HONEYCOMB_ALPHA_MIN = .03
// Fine-lattice neighbors: 0, 60, ... deg at S/3 and 30, 90, ... deg at S/sqrt3.
const STEP60 = [[1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]]
const STEP30 = [[1, 1], [-1, 2], [-2, 1], [-1, -1], [1, -2], [2, -1]]
const mod3 = n => ((n % 3) + 3) % 3
const latticeKey = (a, b) => `${a},${b}`
const CLEAR = [0, 0, 0, 0]

export function honeycombLayer(a, b) {
  if (mod3(a - b) === 0) return mod3(a) === 0 ? 1 : 2
  return 3
}
// Corner orientation in degrees. Layer 3 alternates so its corners point at its parents.
export function honeycombRotation(a, b, layer) {
  if (layer === 3) return mod3(a - b) === 1 ? 60 : 0
  return HONEYCOMB_SHAPES[layer].rot
}
export function honeycombTips(a, b, layer) {
  const shape = HONEYCOMB_SHAPES[layer], rot = honeycombRotation(a, b, layer)
  return Array.from({ length: shape.n }, (_, k) => rot + 360 * k / shape.n)
}
// Fine-lattice offset of the nearest point a corner at `angle` points at.
export function honeycombAim(angle) {
  const d = ((Math.round(angle) % 360) + 360) % 360
  return d % 60 === 0 ? STEP60[d / 60] : STEP30[(d - 30) / 60]
}
// Outline as [angle deg, radius share] pairs: corners alternate with inner vertices.
export function honeycombOutline(layer, rot = HONEYCOMB_SHAPES[layer].rot) {
  const shape = HONEYCOMB_SHAPES[layer]
  return Array.from({ length: shape.n * 2 }, (_, i) => [rot + 180 * i / shape.n, i % 2 ? shape.inner : 1])
}
// Screen vertices (y down, north up) of an outline with corner radius r.
export function honeycombVertices(x, y, r, layer, rot) {
  return honeycombOutline(layer, rot).map(([angle, share]) =>
    [x + r * share * Math.cos(angle * HONEYCOMB_DEG), y - r * share * Math.sin(angle * HONEYCOMB_DEG)])
}

// Premultiplied blend of [r, g, b, a] colors (0..1); weights need not sum to 1.
export function premultipliedMix(weights, colors, scale = 1) {
  let alpha = 0
  for (let i = 0; i < weights.length; i++) alpha += weights[i] * colors[i][3]
  if (alpha <= 1e-6) return CLEAR
  const out = [0, 0, 0, Math.min(1, alpha) * scale]
  for (let ch = 0; ch < 3; ch++) {
    let sum = 0
    for (let i = 0; i < weights.length; i++) sum += weights[i] * colors[i][3] * colors[i][ch]
    out[ch] = sum / alpha
  }
  return out
}

// Least-squares affine map from fine-lattice coordinates to projected map space,
// so every layer shares one geometry fitted to the measured coordinates.
function fitLattice(nodes) {
  const n = nodes.length
  if (n < 3) return null
  const m = [[0, 0, 0], [0, 0, 0], [0, 0, 0]], bx = [0, 0, 0], by = [0, 0, 0]
  for (const p of nodes) {
    const v = [1, p.a, p.b]
    for (let i = 0; i < 3; i++) {
      bx[i] += v[i] * p.x; by[i] += v[i] * p.y
      for (let j = 0; j < 3; j++) m[i][j] += v[i] * v[j]
    }
  }
  const det3 = q => q[0][0] * (q[1][1] * q[2][2] - q[1][2] * q[2][1]) - q[0][1] * (q[1][0] * q[2][2] - q[1][2] * q[2][0]) +
    q[0][2] * (q[1][0] * q[2][1] - q[1][1] * q[2][0])
  const det = det3(m)
  if (!Number.isFinite(det) || Math.abs(det) < 1e-12) return null
  const solve = rhs => [0, 1, 2].map(col => det3(m.map((row, i) => row.map((value, j) => (j === col ? rhs[i] : value)))) / det)
  const [x0, xa, xb] = solve(bx), [y0, ya, yb] = solve(by)
  return { x0, y0, xa, ya, xb, yb }
}

// Every layer point near a measured point. Estimates carry a blended color, a failed
// flag and a captured flag; never a rank. `nodes`: [{ a, b, x, y, color, won, failed }]
// in projected units; `radius` is the study radius as a share of the view spacing.
export function honeycombLayers(nodes, radius = Infinity) {
  const fit = fitLattice(nodes)
  if (!fit) return null
  const position = (a, b) => [fit.x0 + a * fit.xa + b * fit.xb, fit.y0 + a * fit.ya + b * fit.yb]
  // Three fine steps along a span one view spacing S.
  const spacing = 3 * Math.hypot(fit.xa, fit.ya)
  const info = new Map()
  for (const p of nodes) info.set(latticeKey(p.a, p.b), { ...p, layer: 1 })
  const estimates = { 2: [], 3: [] }, seen = new Set()
  for (const p of nodes) for (let da = -3; da <= 3; da++) for (let db = -3; db <= 3; db++) {
    const a = p.a + da, b = p.b + db, layer = honeycombLayer(a, b), k = latticeKey(a, b)
    if (layer === 1 || seen.has(k)) continue
    seen.add(k)
    const e = (a + b / 2) / 3, n = Math.sqrt(3) / 2 * b / 3, dist = Math.hypot(e, n)
    estimates[layer].push({ a, b, layer, e, n, inside: dist <= radius + 1e-9 })
  }
  const blend = (x, parents) => {
    const found = parents.map(([a, b]) => info.get(latticeKey(a, b)) || null)
    x.color = premultipliedMix([1 / 3, 1 / 3, 1 / 3], found.map(q => (q ? q.color : CLEAR)))
    x.failed = found.some(q => q && q.failed)
    x.won = found.every(q => q && q.won)
    info.set(latticeKey(x.a, x.b), x)
  }
  // Layer 2: premultiplied mean of its 3 real corners. Layer 3: of its 3 parents (1 real, 2 layer 2).
  for (const x of estimates[2]) blend(x, STEP30.map(([u, v]) => [x.a + u, x.b + v]).filter(([a, b]) => honeycombLayer(a, b) === 1))
  for (const x of estimates[3]) blend(x, STEP60.map(([u, v]) => [x.a + u, x.b + v]).filter(([a, b]) => honeycombLayer(a, b) !== 3))
  for (const layer of [2, 3]) {
    estimates[layer] = estimates[layer].filter(x => x.failed || x.color[3] >= HONEYCOMB_ALPHA_MIN)
  }
  // Rank-one glow and the directional victory rule: a corner glints only if its shape
  // glows AND the point that corner aims at is captured. No data never counts as won.
  const aimedWon = (x, angle) => {
    const [u, v] = honeycombAim(angle)
    return !!info.get(latticeKey(x.a + u, x.b + v))?.won
  }
  const glow = { marker: null, real: [], estimates: [], glints: 0 }
  const center = info.get(latticeKey(0, 0))
  if (center?.won) {
    const tips = honeycombTips(0, 0, 'marker').filter(angle => aimedWon(center, angle))
    glow.marker = { x: center, tips }; glow.glints += tips.length
  }
  for (const p of nodes) {
    if (!p.won) continue
    const tips = honeycombTips(p.a, p.b, 1).filter(angle => aimedWon(p, angle))
    glow.real.push({ x: info.get(latticeKey(p.a, p.b)), tips })
    if (p.a || p.b) glow.glints += tips.length
  }
  for (const layer of [2, 3]) for (const x of estimates[layer]) {
    if (!x.won || !x.inside) continue
    const tips = honeycombTips(x.a, x.b, layer).filter(angle => aimedWon(x, angle))
    glow.estimates.push({ x, tips }); glow.glints += tips.length
  }
  // The business marker's 6 sharp tips (at 0, 60, ..., 300 deg aiming straight at the 6
  // surrounding hexagons): 25% own color, 75% the neighbor point each tip aims at.
  const markerColor = own => honeycombTips(0, 0, 'marker').map(angle => {
    const [u, v] = honeycombAim(angle)
    return premultipliedMix([.25, .75], [own, info.get(latticeKey(u, v))?.color || CLEAR])
  })
  return { info, estimates, glow, position, spacing, center, markerColor }
}

// Nested rungs inside one honeycomb view. A refined point measured at a finer rung than
// the view replaces every estimate within half its own spacing. `nested`: [{ a, b, scale }]
// on the companion fine lattice (a/3, b/3 not both integers), `scale` = rung / view spacing.
export function honeycombNest(hex, nested) {
  if (!hex || !nested?.length) return hex
  const near = nested.map(p => [(p.a + p.b / 2) / 3, Math.sqrt(3) / 2 * p.b / 3, (p.scale || .5) / 2])
  const keep = x => !near.some(([e, n, r]) => Math.hypot(x.e - e, x.n - n) < r + 1e-9)
  for (const layer of [2, 3]) hex.estimates[layer] = hex.estimates[layer].filter(keep)
  const before = hex.glow.estimates
  hex.glow.estimates = before.filter(g => keep(g.x))
  for (const g of before) if (!keep(g.x)) hex.glow.glints -= g.tips.length
  return hex
}
