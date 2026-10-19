// A small display adapter. It never changes evidence or estimates unmeasured ranks.
const finite = value => typeof value === 'number' && Number.isFinite(value)
const rankOf = value => Number.isInteger(value) && value > 0 ? value : null
const idOf = item => item.faction_id || (item.cid ? `cid:${item.cid}` : item.place_id ? `place:${item.place_id}` : `name:${item.title}`)
const validLocation = (lat, lng) => finite(lat) && finite(lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180
// Models are immutable evidence snapshots. Keep derived lookups out of exports.
const observationIndexes = new WeakMap()
const metricCaches = new WeakMap()
const leaderboardCaches = new WeakMap()

function observationIndex(o) {
  if (!observationIndexes.has(o)) {
    const ranks = new Map(), positions = new Set()
    for (const item of o.items) {
      if (!ranks.has(item.id)) ranks.set(item.id, item.rank)
      positions.add(item.rank)
    }
    let completeDepth = 0
    while (positions.has(completeDepth + 1)) completeDepth++
    observationIndexes.set(o, { ranks, completeDepth })
  }
  return observationIndexes.get(o)
}

export function normalizeStudy(input) {
  if (!input || typeof input !== 'object') throw new Error('Choose a saved study JSON file.')
  if (['geogrid-battlefield/v1', 'geogrid-companion/v1'].includes(input.schema)) {
    if (!Array.isArray(input.points) || !input.points.length || !Array.isArray(input.lanes) || !input.lanes.length || !Array.isArray(input.factions)) {
      throw new Error('This study is missing its locations, queries, or businesses.')
    }
    const businesses = input.factions.map(f => ({
      id: f.faction_id, name: f.name, target: !!f.is_target, discovered: !!f.discovered, shortlisted: true,
      lat: !f.location_estimated && validLocation(f.lat, f.lng) ? f.lat : null,
      lng: !f.location_estimated && validLocation(f.lat, f.lng) ? f.lng : null,
      rating: typeof f.rating === 'object' && f.rating ? f.rating.value : f.rating,
      reviews: f.votes_count ?? f.rating?.votes_count, domain: f.domain, cid: f.cid, placeId: f.place_id,
      selection: f.selection,
      address: f.address,
    }))
    if (!businesses.some(b => b.target)) throw new Error('This study has no identified primary business.')
    const resolveIdentity = item => {
      const matching = businesses.filter(b => {
        if (item.cid && b.cid && String(item.cid) !== String(b.cid)) return false
        if (item.place_id && b.placeId && item.place_id !== b.placeId) return false
        return (item.cid && b.cid && String(item.cid) === String(b.cid)) ||
          (item.place_id && b.placeId && item.place_id === b.placeId) ||
          (item.faction_id && b.id === item.faction_id)
      })
      if (matching.length === 1) return matching[0].id
      // Conflicting identity must not retain a stamped faction ID.
      return idOf({ ...item, faction_id: null })
    }
    const queries = input.lanes.map(l => ({ id: l.lane_id, name: l.query || l.keyword }))
    const points = input.points.map(p => ({
      id: p.tag, lat: p.lat, lng: p.lng, distance: p.distance_from_target_km,
      roles: p.roles || [], phase: p.phase, anchors: p.anchor_factions || [],
      observations: Object.fromEntries(queries.map(q => {
        const o = p.by_lane?.[q.id]
        return [q.id, {
          status: o?.status || 'missing', targetRank: rankOf(o?.target_rank), sampledAt: o?.sampled_at,
          collectionMethod: o?.provenance?.method ||
            (['standard', 'live'].includes(input.study?.controls?.method) ? input.study.controls.method : undefined),
          items: (o?.top_items || []).map(i => ({
            id: resolveIdentity(i), name: i.title, rank: rankOf(i.rank ?? i.rank_group),
            rating: i.rating, reviews: i.votes_count, address: i.address, cid: i.cid, placeId: i.place_id,
            lat: validLocation(i.latitude, i.longitude) ? i.latitude : null,
            lng: validLocation(i.latitude, i.longitude) ? i.longitude : null,
          })).filter(i => i.rank !== null).sort((a, b) => a.rank - b.rank),
        }]
      })),
    }))
    // The shortlist is a display preference, never an evidence exclusion.
    const directory = new Map(businesses.map(b => [b.id, b]))
    for (const point of points) for (const o of Object.values(point.observations)) for (const item of o.items) {
      if (directory.has(item.id)) {
        const existing = directory.get(item.id)
        if (!validLocation(existing.lat, existing.lng) && validLocation(item.lat, item.lng)) {
          existing.lat = item.lat; existing.lng = item.lng
        }
        continue
      }
      if (!(item.cid || item.placeId)) continue
      const business = { id: item.id, name: item.name || 'Unnamed profile', target: false,
        shortlisted: false, cid: item.cid, placeId: item.placeId, address: item.address,
        rating: item.rating, reviews: item.reviews, lat: item.lat, lng: item.lng }
      directory.set(business.id, business)
      businesses.push(business)
    }
    return validate({
      name: input.business?.name || input.target?.name, location: input.location || '',
      generatedAt: input.generated_at, depth: input.study?.depth || null,
      kind: input.evidence?.pending_tasks > 0 ? `Collecting · ${input.evidence.pending_tasks} searches queued` : input.evidence?.observed_from ? 'Measured study' : 'Saved study', targetId: businesses.find(b => b.target).id,
      evidence: input.evidence, controls: input.study?.controls,
      geometry: input.study?.geometry, sampling: input.study?.sampling, studyViews: input.study_views,
      businesses, queries, points, limited: false,
    })
  }
  if (Array.isArray(input.results) && typeof input.target === 'string') {
    const counts = new Map()
    for (const p of input.results) for (const i of p.top_items || []) {
      if (i.title !== input.target) counts.set(i.title, (counts.get(i.title) || 0) + 1)
    }
    const businesses = [{ id: 'TARGET', name: input.target, target: true, shortlisted: true },
      ...[...counts].sort((a, b) => b[1] - a[1]).slice(0, 9).map(([name]) => ({ id: `name:${name}`, name, target: false, shortlisted: true }))]
    return validate({
      name: input.target, location: input.location || '', generatedAt: null, depth: null,
      kind: 'Bundled sample', targetId: 'TARGET', limited: true, businesses,
      queries: [{ id: 'q1', name: input.keyword }],
      points: input.results.map(p => ({
        id: p.point.tag, lat: p.point.lat, lng: p.point.lng,
        observations: { q1: {
          status: p.error ? 'error' : rankOf(p.rank) ? 'found' : 'sample_not_returned',
          targetRank: rankOf(p.rank),
          items: (p.top_items || []).map((i, n) => ({ id: i.title === input.target ? 'TARGET' : `name:${i.title}`, name: i.title, rank: n + 1 })),
        } },
      })),
    })
  }
  throw new Error('Unsupported file. Open a companion-study.json, battlefield-model.json, or a GeoGrid proof dataset.')
}

function validate(model) {
  if (!model.points.length) throw new Error('This study has no search locations.')
  if (model.businesses.some(b => typeof b.id !== 'string' || typeof b.name !== 'string') ||
      new Set(model.businesses.map(b => b.id)).size !== model.businesses.length) {
    throw new Error('Business identities must be named and unique.')
  }
  if (model.queries.some(q => typeof q.id !== 'string' || typeof q.name !== 'string') ||
      new Set(model.queries.map(q => q.id)).size !== model.queries.length) {
    throw new Error('Search queries must be named and unique.')
  }
  if (model.points.length > 15000) throw new Error('This viewer supports up to 15,000 locations.')
  if (new Set(model.points.map(p => p.id)).size !== model.points.length) throw new Error('Location identifiers must be unique.')
  if (model.points.some(p => !finite(p.lat) || !finite(p.lng) || Math.abs(p.lat) > 90 || Math.abs(p.lng) > 180)) {
    throw new Error('The study contains invalid map coordinates.')
  }
  return model
}

export function observationFor(model, point, queryId, businessId) {
  const o = point.observations[queryId]
  if (o?.status === 'pending') return { rank: null, state: 'unknown', label: 'Search queued · no result yet' }
  if (!o || ['missing', 'missing_result', 'error', 'provider_error', 'empty_results'].includes(o.status)) return { rank: null, state: 'unknown', label: 'No usable result' }
  const index = observationIndex(o)
  const rank = businessId === model.targetId ? o.targetRank : index.ranks.get(businessId)
  if (rank) return { rank, state: 'ranked', label: `Rank ${rank}` }
  // Only the target's status certifies depth in the legacy model. For rivals,
  // require explicit organic ranks to reach the requested depth as well.
  const depthReached = model.depth && ((businessId === model.targetId && o.status === 'not_returned_depth_reached') ||
    index.completeDepth >= model.depth)
  if (depthReached) return { rank: null, state: 'absent', label: `Not in returned top ${model.depth}` }
  return { rank: null, state: 'unknown', label: model.limited ? 'Not in saved sample' : 'Incomplete results' }
}

export function businessMetrics(model, queryId, businessId) {
  if (!metricCaches.has(model)) metricCaches.set(model, new Map())
  const cache = metricCaches.get(model), key = JSON.stringify([queryId, businessId])
  if (cache.has(key)) return cache.get(key)
  const observations = model.points.map(p => observationFor(model, p, queryId, businessId))
  const ranked = observations.filter(o => o.rank)
  const top3 = ranked.filter(o => o.rank <= 3).length
  const metrics = {
    top3, top3Pct: top3 / observations.length * 100,
    visibilityScore: ranked.reduce((sum, o) => sum + Math.max(0, 21 - o.rank), 0),
    found: ranked.length, unknown: observations.filter(o => o.state === 'unknown').length,
    near: ranked.filter(o => o.rank >= 4 && o.rank <= 10).length,
    average: ranked.length ? ranked.reduce((sum, o) => sum + o.rank, 0) / ranked.length : null,
  }
  cache.set(key, metrics)
  return metrics
}

export function businessLeaderboard(model, queryId) {
  if (!leaderboardCaches.has(model)) leaderboardCaches.set(model, new Map())
  const cache = leaderboardCaches.get(model)
  if (cache.has(queryId)) return cache.get(queryId)
  const rows = model.businesses.map(business => ({
    business, metrics: businessMetrics(model, queryId, business.id),
  })).sort((a, b) => b.metrics.top3 - a.metrics.top3 ||
    b.metrics.visibilityScore - a.metrics.visibilityScore ||
    a.business.id.localeCompare(b.business.id))
  let position = 0
  const ranked = rows.map((row, index) => {
    const previous = rows[index - 1]
    if (!previous || row.metrics.top3 !== previous.metrics.top3 ||
        row.metrics.visibilityScore !== previous.metrics.visibilityScore) position = index + 1
    return { ...row, position }
  })
  cache.set(queryId, ranked)
  return ranked
}

export function businessPage(model, queryId, { scope = 'shortlist', search = '', page = 0, pageSize = 25 } = {}) {
  const needle = search.trim().toLocaleLowerCase()
  const rows = businessLeaderboard(model, queryId).filter(({ business: b }) =>
    (scope === 'all' || b.shortlisted !== false) &&
    (!needle || [b.name, b.address, b.cid, b.placeId].some(value => String(value || '').toLocaleLowerCase().includes(needle))))
  const size = Math.max(1, Math.min(50, Math.trunc(pageSize) || 25))
  const pages = Math.max(1, Math.ceil(rows.length / size))
  const currentPage = Math.max(0, Math.min(pages - 1, Math.trunc(page) || 0))
  return { rows: rows.slice(currentPage * size, (currentPage + 1) * size), total: rows.length,
    page: currentPage, pages, pageSize: size }
}

// Top ten: pure cyan through green to yellow. Rank 11 is the hard red threshold.
// Lower ranks keep pure red and reveal more map through decreasing alpha.
// Evidence remains unchanged by this display scale.
export const RANK_COLORS = ['#00ffff', '#00ffc6', '#00ff8e', '#00ff55', '#00ff1c',
  '#1cff00', '#55ff00', '#8eff00', '#c6ff00', '#ffff00', ...Array(20).fill('#ff0000')]
export const RANK_OPACITIES = Array.from({ length: 30 }, (_, i) => i < 10 ? 1 - i / 36 : .02 + (.25 - .02) * (29 - i) / 19)

export function rankFillOpacity(rank, translucent = false) {
  if (!Number.isInteger(rank) || rank < 1 || rank > 30) return 0
  // The explicit 25%→2% red policy stays the same in both appearance modes.
  return RANK_OPACITIES[rank - 1] * (rank <= 10 && translucent ? .45 : 1)
}

export function rankPresentation(model, point, queryId, businessId) {
  const observation = observationFor(model, point, queryId, businessId)
  if (point.observations[queryId]?.status === 'pending') return { label: '?', color: '#87909f', kind: 'unknown', description: observation.label }
  if (observation.rank && observation.rank <= 30) {
    return { label: String(observation.rank), rank: observation.rank,
      color: RANK_COLORS[observation.rank - 1], opacity: rankFillOpacity(observation.rank),
      kind: 'ranked', description: observation.label }
  }
  const ranks = new Set(point.observations[queryId]?.items.map(i => i.rank) || [])
  const topThirtyComplete = Array.from({ length: 30 }, (_, i) => i + 1).every(rank => ranks.has(rank))
  if (observation.rank > 30 || (observation.state === 'absent' && model.depth >= 30) ||
      (topThirtyComplete && !['missing', 'missing_result', 'error', 'provider_error', 'empty_results'].includes(point.observations[queryId]?.status))) {
    return { label: 'NR', color: '#10080b', kind: 'nr', description: observation.rank ? `Outside top 30 · observed rank ${observation.rank}` : 'Not returned in the top 30' }
  }
  return { label: '?', color: '#87909f', kind: 'unknown',
    description: ranks.size ? `${ranks.size} organic results returned · top-30 absence unconfirmed` : 'No usable result for the top 30' }
}
