// A study-wide adjacency graph keeps identity colors stable when queries change.
// It optimizes local separation; color alone cannot uniquely label a large field.
const cache = new WeakMap()
const unusable = new Set(['pending', 'missing', 'missing_result', 'error', 'provider_error', 'empty_results'])
export const winnerAt = observation => observation && !unusable.has(observation.status)
  ? observation.items.find(item => item.rank === 1) : null

export function perceptualColor(hex) {
  const [r, g, b] = [1, 3, 5].map(i => {
    const n = parseInt(hex.slice(i, i + 2), 16) / 255
    return n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4
  })
  const l = Math.cbrt(.4122214708 * r + .5363325363 * g + .0514459929 * b)
  const m = Math.cbrt(.2119034982 * r + .6806995451 * g + .1073969566 * b)
  const s = Math.cbrt(.0883024619 * r + .2817188376 * g + .6299787005 * b)
  return [.2104542553 * l + .793617785 * m - .0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + .4505937099 * s,
    .0259040371 * l + .7827717662 * m - .808675766 * s]
}
const separation = (a, b) => Math.hypot(...a.map((v, i) => v - b[i]))
const palette = ['#00ffff', '#ff3158', '#ffe629', '#9271ff', '#32e475', '#ff922b',
  '#ff68d4', '#379aff', '#ffffff', '#c5ed58', '#bd8a58', '#45c7ab',
  '#ecabd1', '#a8c8ff', '#f9c487', '#c69fff', '#8ed6df', '#d2dc9c',
  '#7caf50', '#db5b2e', '#8994d9', '#d2bbff', '#f8a397', '#58bede']
const labs = palette.map(perceptualColor)

export function leaderIdentity(model) {
  if (cache.has(model)) return cache.get(model)
  const queries = model.queries?.map(q => q.id) || Object.keys(model.points[0]?.observations || {})
  const counts = new Map(), graph = new Map(), winners = new Map()
  for (const point of model.points) {
    const ids = queries.map(q => winnerAt(point.observations[q])?.id)
    winners.set(point, ids)
    for (const id of ids) if (id) {
      counts.set(id, (counts.get(id) || 0) + 1)
      if (!graph.has(id)) graph.set(id, new Map())
    }
  }
  // Spatial hashing in local kilometers: include diagonal neighbors, without
  // joining points two grid cells apart. No business-base distance restriction.
  const step = model.sampling?.spacing_km
  if (step > 0 && model.points.length) {
    const origin = model.points[0], cos = Math.cos(origin.lat * Math.PI / 180), buckets = new Map()
    for (const point of model.points) {
      const x = (point.lng - origin.lng) * 111.195 * cos / step
      const y = (point.lat - origin.lat) * 111.195 / step
      const bx = Math.floor(x), by = Math.floor(y)
      for (let dx = -2; dx <= 2; dx++) for (let dy = -2; dy <= 2; dy++) {
        for (const other of buckets.get(`${bx + dx},${by + dy}`) || []) {
          if (Math.hypot(x - other.x, y - other.y) > 1.65) continue
          winners.get(point).forEach((id, q) => {
            const neighbor = winners.get(other.point)[q]
            if (!id || !neighbor || id === neighbor) return
            graph.get(id).set(neighbor, (graph.get(id).get(neighbor) || 0) + 1)
            graph.get(neighbor).set(id, (graph.get(neighbor).get(id) || 0) + 1)
          })
        }
      }
      const key = `${bx},${by}`
      if (!buckets.has(key)) buckets.set(key, [])
      buckets.get(key).push({ point, x, y })
    }
  }
  const ids = [...counts.keys()].sort((a, b) => counts.get(b) - counts.get(a) || a.localeCompare(b))
  const assigned = new Map(), usage = palette.map(() => 0), pending = new Set(ids)
  while (pending.size) {
    const id = [...pending].sort((a, b) => {
      const saturation = key => new Set([...graph.get(key).keys()].map(n => assigned.get(n)).filter(n => n !== undefined)).size
      return saturation(b) - saturation(a) || graph.get(b).size - graph.get(a).size ||
        counts.get(b) - counts.get(a) || a.localeCompare(b)
    })[0]
    const neighbors = [...graph.get(id)].filter(([n]) => assigned.has(n))
    let chosen = 0, best = -Infinity
    palette.forEach((_, index) => {
      // Maximize worst neighboring perceptual contrast, then weighted average.
      const distances = neighbors.map(([n, weight]) => ({ d: separation(labs[index], labs[assigned.get(n)]), weight }))
      const min = distances.length ? Math.min(...distances.map(d => d.d)) : .5
      const avg = distances.reduce((s, d) => s + d.d * d.weight, 0) / (distances.reduce((s, d) => s + d.weight, 0) || 1)
      const score = min * 10 + avg - usage[index] * .015
      if (score > best) { best = score; chosen = index }
    })
    assigned.set(id, chosen); usage[chosen]++; pending.delete(id)
  }
  const identities = new Map(ids.map((id, index) => [id, {
    color: palette[assigned.get(id)], badge: `L${String(index + 1).padStart(2, '0')}`,
  }]))
  const result = { identities, graph }
  cache.set(model, result)
  return result
}
