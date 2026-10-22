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

// Keep the four positions, even when a radial boundary removes some origins.
// Padding the axes also finds intersections beside the outermost measured row.
export function latticeIntersections(points, partial = false) {
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
export function territoryOutlines(points, cellById, project) {
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
