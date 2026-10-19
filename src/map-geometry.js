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
