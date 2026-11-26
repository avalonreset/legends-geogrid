// A small display adapter. It never changes evidence or estimates unmeasured ranks.
const finite = value => typeof value === 'number' && Number.isFinite(value)
const rankOf = value => Number.isInteger(value) && value > 0 ? value : null
const idOf = item => item.faction_id || (item.cid ? `cid:${item.cid}` : item.place_id ? `place:${item.place_id}` : `name:${item.title}`)
const textOrNull = value => (typeof value === 'string' && value.trim() ? value.trim() : null)
// A string key chosen by the host. It is never parsed and is only used when the item carries no provider identifiers.
const opaqueKeyOf = item => (typeof item.faction_id === 'string' && item.faction_id && !item.cid && !item.place_id ? item.faction_id : null)
const share = value => (finite(value) && value >= 0 && value <= 1 ? value : null)
// Precomputed target scores, in the window the host chose (normally the top 20). Shares are fractions 0..1.
function normalizeTargetScores(input) {
  if (!input || typeof input !== 'object') return null
  const scores = { foundShare: share(input.found_share), top3Share: share(input.top3_share ?? input.visible_share),
    avgRank: finite(input.avg_rank) && input.avg_rank >= 1 ? input.avg_rank : null }
  return Object.values(scores).some(v => v !== null) ? scores : null
}
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
      address: f.address, category: textOrNull(f.category),
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
      // An opaque key (no provider identifiers on the item) stands for itself; the host decides what it means.
      const key = opaqueKeyOf(item)
      if (key) return key
      // Conflicting identity must not retain a stamped faction ID.
      return idOf({ ...item, faction_id: null })
    }
    const queries = input.lanes.map(l => ({ id: l.lane_id, name: l.query || l.keyword, targetScores: normalizeTargetScores(l.scores) }))
    const profileDirectory = input.profiles && typeof input.profiles === 'object' ? input.profiles : {}
    const allPoints = input.points.map(p => ({
      id: p.tag, lat: p.lat, lng: p.lng, distance: p.distance_from_target_km,
      roles: p.roles || [], phase: p.phase, anchors: p.anchor_factions || [],
      ...(p.hex ? { hex: p.hex } : {}),
      observations: Object.fromEntries(queries.map(q => {
        const o = p.by_lane?.[q.id]
        return [q.id, {
          status: o?.status || 'missing', targetRank: rankOf(o?.target_rank), sampledAt: o?.sampled_at,
          collectionMethod: o?.provenance?.method ||
            (['standard', 'live'].includes(input.study?.controls?.method) ? input.study.controls.method : undefined),
          items: (o?.top_items || []).map(rawItem => {
            const opaque = opaqueKeyOf(rawItem)
            const prof = (rawItem.cid && profileDirectory[String(rawItem.cid)]) || (opaque && profileDirectory[opaque]) || {}
            const i = { ...prof, ...rawItem }
            const id = resolveIdentity(i)
            return {
              id, opaque: id === opaque, name: i.title ?? i.name, rank: rankOf(i.rank ?? i.rank_group), category: textOrNull(i.category),
              rating: typeof i.rating === 'object' && i.rating ? i.rating.value : i.rating, reviews: i.votes_count, address: i.address, cid: i.cid, placeId: i.place_id,
              lat: validLocation(i.latitude, i.longitude) ? i.latitude : null,
              lng: validLocation(i.latitude, i.longitude) ? i.longitude : null,
            }
          }).filter(i => i.rank !== null).sort((a, b) => a.rank - b.rank),
        }]
      })),
    }))
    // Circle contract: the exporter keeps only points inside the study radius, so every point is in the read.
    const points = allPoints
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
      if (!(item.cid || item.placeId || item.opaque)) continue
      const business = { id: item.id, name: item.name || 'Unnamed profile', target: false,
        shortlisted: false, cid: item.cid, placeId: item.placeId, address: item.address, category: item.category,
        rating: item.rating, reviews: item.reviews, lat: item.lat, lng: item.lng }
      directory.set(business.id, business)
      businesses.push(business)
    }
    const landMaskPolygons = normalizeLandMaskPolygons(input.land_mask_polygons ?? input.study?.land_mask_polygons)
    return validate({
      name: input.business?.name || input.target?.name, location: input.location || '',
      businessCategory: textOrNull(input.business?.category),
      generatedAt: input.generated_at, depth: input.study?.depth || null, scoreWindow: rankOf(input.study?.score_window),
      kind: input.evidence?.pending_tasks > 0 ? `Collecting · ${input.evidence.pending_tasks} searches queued` : input.evidence?.observed_from ? 'Measured study' : 'Saved study', targetId: businesses.find(b => b.target).id,
      evidence: input.evidence, controls: input.study?.controls,
      geometry: input.study?.geometry, sampling: input.study?.sampling, studyViews: input.study_views,
      businesses, queries, points, edgeSignal: input.study?.edge_signal || null, limited: false,
      ...(landMaskPolygons ? { landMaskPolygons, land_mask_polygons: landMaskPolygons } : {}),
      ...(finite(input.water_clipped_pct) ? { waterClippedPct: input.water_clipped_pct } : {}),
      ...(Number.isInteger(input.raw_circle_pins) ? { rawCirclePins: input.raw_circle_pins } : {}),
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

function normalizeLandMaskPolygons(raw) {
  if (!Array.isArray(raw) || !raw.length) return null
  const cleanRing = ring => {
    if (!Array.isArray(ring) || ring.length < 3) return null
    const pts = []
    for (const pair of ring) {
      if (!Array.isArray(pair) || pair.length < 2) return null
      const lng = Number(pair[0]), lat = Number(pair[1])
      if (!validLocation(lat, lng)) return null
      pts.push([lng, lat])
    }
    return pts.length >= 3 ? pts : null
  }
  const out = []
  for (const poly of raw) {
    if (!poly || typeof poly !== 'object') continue
    const outer = cleanRing(poly.outer)
    if (!outer) continue
    const holes = Array.isArray(poly.holes) ? poly.holes.map(cleanRing).filter(Boolean) : []
    out.push({ outer, holes })
  }
  return out.length ? out : null
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
  // Instrument-limited: the business lies outside the search screen at this point. Not a loss.
  if (o.status === 'instrument_limited' && businessId === model.targetId) {
    return { rank: null, state: 'limited', label: "Can't see from here · outside the search screen" }
  }
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
  // Instrument-limited points are never losses: they leave the denominator. On a honeycomb a
  // location never collected for this query is not part of its lattice either.
  const all = model.points.filter(p => model.geometry !== 'hex_radius' || p.observations[queryId]?.status !== 'missing')
    .map(p => observationFor(model, p, queryId, businessId))
  const observations = all.filter(o => o.state !== 'limited')
  // Scores stay anchored to the score window (normally the top 20) when the study names one, so deeper
  // captured ranks never move them. Without a window the behavior is unchanged.
  const limit = model.scoreWindow || Infinity
  const ranked = observations.filter(o => o.rank && o.rank <= limit)
  const top3 = ranked.filter(o => o.rank <= 3).length
  const metrics = {
    top3, top3Pct: top3 / observations.length * 100,
    visibilityScore: ranked.reduce((sum, o) => sum + Math.max(0, 21 - o.rank), 0),
    found: ranked.length, unknown: observations.filter(o => o.state === 'unknown').length,
    scored: observations.length, limited: all.length - observations.length,
    near: ranked.filter(o => o.rank >= 4 && o.rank <= 10).length,
    average: ranked.length ? ranked.reduce((sum, o) => sum + o.rank, 0) / ranked.length : null,
  }
  // Precomputed target scores (lane.scores in the study) win over anything derived here.
  const given = businessId === model.targetId ? model.queries?.find(q => q.id === queryId)?.targetScores : null
  if (given) {
    if (given.top3Share !== null) { metrics.top3Pct = given.top3Share * 100; metrics.top3 = Math.round(given.top3Share * observations.length) }
    if (given.foundShare !== null) metrics.found = Math.round(given.foundShare * observations.length)
    if (given.avgRank !== null) metrics.average = given.avgRank
  }
  cache.set(key, metrics)
  return metrics
}

// Listings for one location: every captured result in rank order, split at the default window.
export const LISTING_WINDOW = 20
// Circle contract edge signal: when the target still holds the top 3 on half or more of the
// outermost ring inside R, the summary says so and offers growing the circle (text only).
export function edgeSignalNote(model, queryId) {
  const edge = model?.edgeSignal?.[queryId]
  if (!edge?.extends) return ''
  return `Territory likely extends past the study radius (top 3 at ${edge.top3} of ${edge.scored} edge-ring locations). Grow the circle: a new, larger full-circle study, run as an explicit paid step.`
}

export function pointListing(model, pointId, queryId, window = LISTING_WINDOW) {
  const point = model.points.find(p => p.id === pointId)
  const o = point?.observations[queryId]
  if (!o) return null
  const unusable = ['pending', 'missing', 'missing_result', 'error', 'provider_error', 'empty_results'].includes(o.status)
  const items = unusable ? [] : o.items
  const target = observationFor(model, point, queryId, model.targetId)
  const targetListed = items.some(i => i.id === model.targetId)
  const captured = items.length
  return { point, status: o.status, items, captured, top: items.filter(i => i.rank <= window), extra: items.filter(i => i.rank > window),
    target, targetListed, depth: items.reduce((max, i) => Math.max(max, i.rank), 0) || model.depth || 0 }
}

// Competitor presence across the grid for one query. Appearances count every captured result, so a
// rival seen only at rank 40 still counts; score metrics elsewhere stay inside the score window.
export function competitorStats(model, queryId) {
  const measured = model.points.filter(p => {
    const o = p.observations[queryId]
    return o && !['pending', 'missing', 'missing_result', 'error', 'provider_error', 'empty_results'].includes(o.status)
  })
  const rows = new Map()
  const add = (id, rank) => {
    const row = rows.get(id) || { id, appearances: 0, rankSum: 0, best: Infinity, top3: 0 }
    row.appearances++; row.rankSum += rank; row.best = Math.min(row.best, rank); if (rank <= 3) row.top3++
    rows.set(id, row)
  }
  for (const p of measured) {
    const o = p.observations[queryId]
    const seen = new Set()
    for (const item of o.items) {
      if (item.id === model.targetId || seen.has(item.id)) continue
      seen.add(item.id); add(item.id, item.rank)
    }
    if (o.targetRank) add(model.targetId, o.targetRank)
  }
  const directory = new Map(model.businesses.map(b => [b.id, b]))
  const total = measured.length
  const all = [...rows.values()].map(r => ({ business: directory.get(r.id) || { id: r.id, name: 'Unnamed profile' }, appearances: r.appearances,
    share: total ? r.appearances / total : 0, averageRank: r.rankSum / r.appearances, bestRank: r.best, top3: r.top3 }))
    .sort((a, b) => b.appearances - a.appearances || a.averageRank - b.averageRank || a.business.name.localeCompare(b.business.name) || a.business.id.localeCompare(b.business.id))
  return { measured: total, target: all.find(r => r.business.id === model.targetId) || null, rows: all.filter(r => r.business.id !== model.targetId) }
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
  if (observation.state === 'limited') return { label: '·', color: '#87909f', kind: 'limited', description: observation.label }
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
