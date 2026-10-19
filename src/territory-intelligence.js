// Descriptive hypotheses from complete observations, not estimates of demand or ease.
const MILE_KM = 1.609344
const STEPS = [[1, 0], [-1, 0], [0, 1], [0, -1]]
const cache = new WeakMap()
export const TERRITORY_BANDS = {
  defend: { label: 'Defend', description: 'Existing top-three foothold' },
  advance: { label: 'Advance', description: 'Ranks 4–10 to investigate' },
  build: { label: 'Build', description: 'Ranks 11–30; visibility to develop' },
  outside30: { label: 'Outside top 30', description: 'Not empty territory' },
  unknown: { label: 'Unknown', description: 'Incomplete or contradictory evidence' },
}
const LIMITATIONS = 'One snapshot of Maps rankings. Sampled locations are not customers or demand. These areas do not establish ranking cause, ease, market gaps, or commercial value.'
const keyOf = (x, y) => `${x},${y}`
const finite = value => typeof value === 'number' && Number.isFinite(value)
function distanceKm(a, b) {
  const rad = Math.PI / 180, dLat = (b.lat - a.lat) * rad, dLng = (b.lng - a.lng) * rad
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) ** 2
  // Match tools/competitive_sampling.py exactly at circular boundary origins.
  return 6371.0088 * 2 * Math.asin(Math.sqrt(Math.min(1, h)))
}
function median(values) {
  if (!values.length) return null
  const sorted = [...values].sort((a, b) => a - b), middle = sorted.length >> 1
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2
}
function classify(model, point, queryId, businesses) {
  const o = point?.observations?.[queryId], unknown = { band: 'unknown', rank: null, items: [] }
  if (model.depth < 30 || !Number.isInteger(model.depth) ||
      !o || !['found', 'not_returned_depth_reached'].includes(o.status)) return unknown
  const items = (o.items || []).filter(i => Number.isInteger(i.rank) && i.rank >= 1 && i.rank <= 30)
  const ranks = new Set(items.map(i => i.rank)), identities = new Set()
  for (const item of items) {
    const b = businesses.get(item.id)
    const identity = item.cid || b?.cid ? `cid:${item.cid || b.cid}` :
      item.placeId || b?.placeId ? `place:${item.placeId || b.placeId}` : null
    if (!identity || identities.has(identity)) return unknown
    identities.add(identity)
  }
  if (items.length !== 30 || ranks.size !== 30 || new Set(items.map(i => i.id)).size !== 30) return unknown
  const rank = items.find(i => i.id === model.targetId)?.rank ?? null
  if (o.targetRank !== rank || (rank === null) !== (o.status === 'not_returned_depth_reached')) return unknown
  return { band: rank === null ? 'outside30' : rank <= 3 ? 'defend' : rank <= 10 ? 'advance' : 'build', rank, items }
}
function direction(x, y) {
  if (Math.hypot(x, y) < .25) return 'Around the primary business'
  const angle = (Math.atan2(x, y) * 180 / Math.PI + 360) % 360
  return `${['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][Math.round(angle / 45) % 8]} of the primary business`
}
function lattice(model) {
  const s = model.sampling, center = s?.center
  if (s?.geometry !== 'radius_grid' || !center || !finite(center.lat) || !finite(center.lng) ||
      Math.abs(center.lat) >= 85 || Math.abs(center.lng) > 180 ||
      !finite(s.spacing_km) || !finite(s.radius_km) || s.spacing_km <= 0 ||
      s.radius_km < s.spacing_km || s.radius_km > 100 * MILE_KM) return null
  const n = Math.ceil(s.radius_km / s.spacing_km), step = s.spacing_km / 111.195
  if ((2 * n + 1) ** 2 > 100000) return null
  const cells = new Map(), pointKeys = new Set()
  for (let y = -n; y <= n; y++) for (let x = -n; x <= n; x++) {
    const cell = { x, y, lat: Number((center.lat + y * step).toFixed(7)),
      lng: Number((center.lng + x * step / Math.cos(center.lat * Math.PI / 180)).toFixed(7)) }
    cell.distanceMiles = distanceKm(center, cell) / MILE_KM
    if (cell.distanceMiles * MILE_KM <= s.radius_km) cells.set(keyOf(x, y), cell)
  }
  for (const p of model.points) {
    const x = Math.round((p.lng - center.lng) * Math.cos(center.lat * Math.PI / 180) / step)
    const y = Math.round((p.lat - center.lat) / step), key = keyOf(x, y), cell = cells.get(key)
    if (!cell || pointKeys.has(key) || Math.abs(cell.lat - p.lat) > .000001 || Math.abs(cell.lng - p.lng) > .000001) return null
    pointKeys.add(key)
    cell.point = p
    cell.id = p.id
  }
  for (const cell of cells.values()) cell.id ??= `missing:${cell.x},${cell.y}`
  return { cells, center }
}
function connected(cells) {
  const remaining = new Map(cells.map(c => [keyOf(c.x, c.y), c])), groups = []
  for (const seed of cells) {
    if (!remaining.delete(keyOf(seed.x, seed.y))) continue
    const group = [], stack = [seed]
    while (stack.length) {
      const cell = stack.pop()
      group.push(cell)
      for (const [dx, dy] of STEPS) {
        const key = keyOf(cell.x + dx, cell.y + dy), neighbor = remaining.get(key)
        if (neighbor) { remaining.delete(key); stack.push(neighbor) }
      }
    }
    group.sort((a, b) => a.y - b.y || a.x - b.x)
    groups.push(group)
  }
  return groups.sort((a, b) => b.length - a.length || a[0].y - b[0].y || a[0].x - b[0].x)
}

export function territoryIntelligence(model, queryId) {
  if (!cache.has(model)) cache.set(model, new Map())
  if (cache.get(model).has(queryId)) return cache.get(model).get(queryId)
  const result = { schema: 'geogrid-territory-intelligence/v1', available: false, reason: '', queryId,
    source: { generatedAt: model.generatedAt, controls: model.controls, evidence: model.evidence },
    counts: { defend: 0, advance: 0, build: 0, outside30: 0, unknown: 0, serviceGap: 0, frontier: 0 },
    cells: [], areas: [], frontierAreas: [], serviceGapAreas: [], featuredAreas: [], limitations: LIMITATIONS }
  const grid = lattice(model)
  if (!grid || !model.queries.some(q => q.id === queryId)) {
    result.reason = 'Area analysis requires a valid regular circular lattice and a known query.'
    cache.get(model).set(queryId, result)
    return result
  }
  const businesses = new Map(model.businesses.map(b => [b.id, b]))
  const classifications = new Map()
  for (const c of grid.cells.values()) {
    const observations = new Map(model.queries.map(q => [q.id, classify(model, c.point, q.id, businesses)]))
    classifications.set(c.id, observations)
    const o = observations.get(queryId)
    const supportingQueries = model.queries.filter(q => q.id !== queryId && observations.get(q.id).band === 'defend').map(q => q.id)
    const serviceGap = o.band === 'advance' && supportingQueries.length > 0
    const cell = { id: c.id, lat: c.lat, lng: c.lng, x: c.x, y: c.y,
      distanceMiles: c.distanceMiles, missing: !c.point, band: o.band, rank: o.rank, serviceGap, supportingQueries }
    result.cells.push(cell)
    result.counts[o.band]++
    if (serviceGap) result.counts.serviceGap++
  }
  const lookup = new Map(result.cells.map(c => [keyOf(c.x, c.y), c]))
  for (const cell of result.cells) {
    cell.frontier = cell.band === 'build' && STEPS.some(([dx, dy]) =>
      ['defend', 'advance'].includes(lookup.get(keyOf(cell.x + dx, cell.y + dy))?.band))
    if (cell.frontier) result.counts.frontier++
  }
  const core = result.cells.filter(c => c.band === 'defend')
  const lenses = Object.keys(TERRITORY_BANDS).map(band => ({ lens: band, band, cells: result.cells.filter(c => c.band === band), output: result.areas }))
  lenses.push({ lens: 'frontier', band: 'build', cells: result.cells.filter(c => c.frontier), output: result.frontierAreas },
    { lens: 'serviceGap', band: 'advance', cells: result.cells.filter(c => c.serviceGap), output: result.serviceGapAreas })
  for (const { lens, band, cells, output } of lenses) {
    for (const group of connected(cells)) {
      const avgX = group.reduce((n, c) => n + c.x, 0) / group.length
      const avgY = group.reduce((n, c) => n + c.y, 0) / group.length
      const representative = [...group].sort((a, b) =>
        Math.hypot(a.x - avgX, a.y - avgY) - Math.hypot(b.x - avgX, b.y - avgY) || a.id.localeCompare(b.id))[0]
      const rivals = new Map(), members = new Set(group.map(c => c.id)), adjacentCore = new Set(), adjacentTopTen = new Set()
      let nearestCoreMiles = band === 'defend' ? 0 : null
      for (const cell of group) {
        for (const item of classifications.get(cell.id).get(queryId).items) {
          if (item.rank > 3 || item.id === model.targetId) continue
          const b = businesses.get(item.id)
          if (!rivals.has(item.id)) rivals.set(item.id, { id: item.id, name: b?.name || item.name,
            cid: item.cid || b?.cid, placeId: item.placeId || b?.placeId, address: item.address || b?.address, count: 0 })
          rivals.get(item.id).count++
        }
        for (const [dx, dy] of STEPS) {
          const neighbor = lookup.get(keyOf(cell.x + dx, cell.y + dy))
          if (!neighbor || members.has(neighbor.id)) continue
          if (neighbor.band === 'defend') adjacentCore.add(neighbor.id)
          if (['defend', 'advance'].includes(neighbor.band)) adjacentTopTen.add(neighbor.id)
        }
        for (const c of ['advance', 'build'].includes(band) ? core : []) {
          const d = distanceKm(cell, c) / MILE_KM
          nearestCoreMiles = nearestCoreMiles === null ? d : Math.min(nearestCoreMiles, d)
        }
      }
      const allRivals = [...rivals.values()].sort((a, b) => b.count - a.count || a.id.localeCompare(b.id))
        .map(r => ({ ...r, share: r.count / group.length, denominator: group.length }))
      const serviceGapCount = group.filter(c => c.serviceGap).length
      const featured = group.length >= 2 && (band === 'advance' || band === 'defend' || (band === 'build' && adjacentTopTen.size > 0))
      const reason = band === 'defend' ? 'The primary already holds top-three ranks at these connected measured locations.' :
        band === 'advance' ? `${group.length} connected locations rank 4–10.${serviceGapCount ? ` ${serviceGapCount} also rank top three for another measured query.` : ''}` :
        band === 'build' ? `${group.length} connected locations rank 11–30; ${adjacentTopTen.size} neighboring locations already rank in the top ten.` :
        band === 'outside30' ? 'The primary is absent from complete top-30 results. Other profiles are present; this is not an empty market.' :
        'Missing, incomplete, or contradictory results cannot support a territory recommendation.'
      output.push({
        id: `${queryId}:${lens}:${group[0].id}`, band, lens,
        label: lens === 'frontier' ? 'Expansion frontier' : lens === 'serviceGap' ? 'Service gap' : TERRITORY_BANDS[band].label,
        direction: direction(avgX, avgY), originIds: group.map(c => c.id), count: group.length,
        medianRank: median(group.map(c => c.rank).filter(Number.isInteger)),
        distanceMiles: { min: Math.min(...group.map(c => c.distanceMiles)), max: Math.max(...group.map(c => c.distanceMiles)) },
        representative: { id: representative.id, lat: representative.lat, lng: representative.lng,
          queries: model.queries.map(q => ({ id: q.id, name: q.name,
            rank: classifications.get(representative.id).get(q.id).rank,
            band: classifications.get(representative.id).get(q.id).band })) },
        rivals: allRivals.slice(0, 3), allRivals, serviceGapCount,
        adjacentCoreCount: adjacentCore.size, adjacentTopTenCount: adjacentTopTen.size, nearestCoreMiles,
        featured, isolated: group.length === 1, reason,
        competition: { metric: 'Top-three appearances per measured location', distinctProfiles: allRivals.length,
          leadingRivalShare: allRivals[0]?.share ?? null,
          interpretation: 'Recurring profiles describe local competition, not difficulty or unused demand.' },
        limitations: LIMITATIONS,
      })
    }
  }
  const priority = a => a.band === 'advance' ? a.serviceGapCount > 0 ? 0 : 1 : a.band === 'build' ? 2 : 3
  result.featuredAreas = [...result.areas.filter(a => a.band !== 'build'), ...result.frontierAreas].filter(a => a.featured).sort((a, b) =>
    priority(a) - priority(b) || b.serviceGapCount - a.serviceGapCount || b.count - a.count || a.id.localeCompare(b.id)).slice(0, 3)
  result.available = true
  result.expectedOrigins = grid.cells.size
  result.missingOrigins = result.cells.filter(c => c.missing).length
  result.method = 'Orthogonal same-band connected observations. No interpolation. Featured: at least two origins, advance first, then build adjoining the top ten, then defend. Ordering is descriptive, not commercial priority.'
  cache.get(model).set(queryId, result)
  return result
}
