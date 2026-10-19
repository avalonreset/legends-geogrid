import { territoryIntelligence } from './territory-intelligence.js'

const cache = new WeakMap()
const matchupCache = new WeakMap()
const LIMITATIONS = 'Maps observations, not demand or market share. No absence, concentration, or ranking difference proves easy competition, a cause, or a content opportunity.'
const compareId = (a, b) => a.id.localeCompare(b.id)
const percent = (n, d) => d ? n / d * 100 : null
const mean = values => values.length ? values.reduce((a, b) => a + b, 0) / values.length : null
const quadrant = cell => `${cell.y >= 0 ? 'n' : 's'}${cell.x >= 0 ? 'e' : 'w'}`
function regionId(cell) {
  return cell.distanceMiles <= 2 ? 'core' : `${cell.distanceMiles <= 5 ? 'inner' : 'outer'}-${quadrant(cell)}`
}
function meta(model, id) {
  const b = model.businesses.find(b => b.id === id)
  return { id, name: b?.name || id, address: b?.address || '', cid: b?.cid, placeId: b?.placeId }
}
function indexes(model) {
  const byQuery = new Map(model.queries.map(q => [q.id, territoryIntelligence(model, q.id)]))
  if ([...byQuery.values()].some(r => !r.available)) return null
  const points = new Map(model.points.map(p => [p.id, p]))
  return { byQuery, points, cells: byQuery.values().next().value.cells,
    cellsByQuery: new Map([...byQuery].map(([q, r]) => [q, new Map(r.cells.map(c => [c.id, c]))])) }
}
function regionMetrics(model, region, index, metadata) {
  const perQuery = {}, rivalMap = new Map()
  let completeDenominator = 0, nearDenominator = 0, primaryReturnedDenominator = 0
  const getRival = item => {
    if (!rivalMap.has(item.id)) rivalMap.set(item.id, {
      ...(metadata.get(item.id) || { id: item.id, name: item.name, address: item.address || '', cid: item.cid, placeId: item.placeId }),
      top3Appearances: 0, top10Appearances: 0, appearances: 0, nearAhead: 0, primaryReturnedAhead: 0,
      perQuery: Object.fromEntries(model.queries.map(q => [q.id, { top3: 0, top10: 0, found: 0, nearAhead: 0, primaryReturnedAhead: 0 }])),
    })
    return rivalMap.get(item.id)
  }
  for (const q of model.queries) {
    const counts = { complete: 0, unknown: 0, top3: 0, top10: 0, near: 0, found: 0, serviceGap: 0, frontier: 0 }
    const rivalCounts = new Map()
    for (const id of region.originIds) {
      const cell = index.cellsByQuery.get(q.id).get(id)
      if (!cell || cell.band === 'unknown') { counts.unknown++; continue }
      counts.complete++
      if (cell.rank !== null) counts.found++
      if (cell.band === 'defend') counts.top3++
      if (['defend', 'advance'].includes(cell.band)) counts.top10++
      if (cell.band === 'advance') counts.near++
      if (cell.serviceGap) counts.serviceGap++
      if (cell.frontier) counts.frontier++
      for (const item of index.points.get(id).observations[q.id].items) {
        if (item.id === model.targetId || item.rank > 30) continue
        const rival = getRival(item), rq = rival.perQuery[q.id]
        rival.appearances++; rq.found++
        if (item.rank <= 3) {
          rival.top3Appearances++; rq.top3++
          rivalCounts.set(item.id, (rivalCounts.get(item.id) || 0) + 1)
        }
        if (item.rank <= 10) { rival.top10Appearances++; rq.top10++ }
        if (cell.rank !== null && item.rank < cell.rank) {
          rival.primaryReturnedAhead++; rq.primaryReturnedAhead++
          if (cell.band === 'advance') { rival.nearAhead++; rq.nearAhead++ }
        }
      }
    }
    completeDenominator += counts.complete
    nearDenominator += counts.near
    primaryReturnedDenominator += counts.found
    perQuery[q.id] = { ...counts, top3Pct: percent(counts.top3, counts.complete), top10Pct: percent(counts.top10, counts.complete),
      rivals: [...rivalCounts].map(([id, count]) => ({ ...rivalMap.get(id), count, denominator: counts.complete }))
        .sort((a, b) => b.count - a.count || compareId(a, b)).slice(0, 3)
        .map(({ id, name, address, cid, placeId, count, denominator }) => ({ id, name, address, cid, placeId, count, denominator })) }
  }
  const rivals = [...rivalMap.values()].map(r => ({
    ...r, completeDenominator, nearDenominator, primaryReturnedDenominator,
    top3CoveragePct: mean(model.queries.filter(q => perQuery[q.id].complete > 0)
      .map(q => percent(r.perQuery[q.id].top3, perQuery[q.id].complete))),
    nearAheadPct: percent(r.nearAhead, nearDenominator),
    primaryReturnedAheadPct: percent(r.primaryReturnedAhead, primaryReturnedDenominator),
    top3Queries: model.queries.filter(q => r.perQuery[q.id].top3 > 0).length,
  })).sort((a, b) => (b.top3CoveragePct ?? -1) - (a.top3CoveragePct ?? -1) ||
    b.top10Appearances - a.top10Appearances || compareId(a, b))
  const nearRivals = [...rivals].sort((a, b) => b.nearAhead - a.nearAhead ||
    b.primaryReturnedAhead - a.primaryReturnedAhead || compareId(a, b))
  return { ...region, perQuery, rivals, nearRivals, completeDenominator, nearDenominator, primaryReturnedDenominator }
}
function evidenceInsights(model, regions, index) {
  const all = regions.find(r => r.id === 'all'), core = regions.find(r => r.id === 'core'), insights = []
  const gaps = model.queries.map(q => ({ q, cells: index.byQuery.get(q.id).cells.filter(c => c.serviceGap && c.distanceMiles <= 2) }))
    .sort((a, b) => b.cells.length - a.cells.length || a.q.id.localeCompare(b.q.id))
  if (gaps[0]?.cells.length >= 2) {
    const { q, cells } = gaps[0]
    insights.push({
      id: `service-gap:${q.id}:core`, title: `${q.name}: investigate the service gap`,
      reason: `${cells.length} core locations rank 4–10 for this query but already rank top three for another measured query.`,
      nextAction: 'Compare the existing service page and business profile with the local profiles ahead. Verify query intent and indexing before deciding what to change.',
      queryId: q.id, regionId: 'core', originIds: cells.map(c => c.id),
      evidence: { count: cells.length, regionCount: core.count, selectedQuery: q.name,
        supportingQueryIds: [...new Set(cells.flatMap(c => c.supportingQueries))] },
      limitations: 'Cross-query differences locate a diagnostic question; they do not identify the cause or prove that new content will fix it.',
    })
  }
  const frontiers = model.queries.flatMap(q => index.byQuery.get(q.id).frontierAreas
    .filter(a => !a.isolated).map(a => ({ q, a })))
    .sort((a, b) => b.a.count - a.a.count || a.q.id.localeCompare(b.q.id) || a.a.id.localeCompare(b.a.id))
  if (frontiers.length) {
    const { q, a } = frontiers[0]
    const representative = index.cellsByQuery.get(q.id).get(a.representative.id)
    insights.push({
      id: `frontier:${a.id}`, title: `${q.name}: inspect the adjoining frontier`,
      reason: `${a.count} connected locations rank 11–30, each directly beside an existing top-ten observation.`,
      nextAction: 'Check service coverage, local demand, and the nearby ranking competitors before committing an expansion campaign.',
      queryId: q.id, regionId: regionId(representative), originIds: a.originIds,
      evidence: { count: a.count, medianRank: a.medianRank, direction: a.direction, adjacentTopTenCount: a.adjacentTopTenCount,
        distanceMiles: a.distanceMiles, rivals: a.rivals },
      limitations: 'Adjacent visibility does not establish that expansion is easy, profitable, or achievable through a location page.',
    })
  }
  const regionalLeader = all.rivals[0], nearLeader = all.nearRivals.find(r => r.nearAhead > 0)
  if (regionalLeader && nearLeader && regionalLeader.id !== nearLeader.id) {
    const q = [...model.queries].sort((a, b) => nearLeader.perQuery[b.id].nearAhead - nearLeader.perQuery[a.id].nearAhead || a.id.localeCompare(b.id))[0]
    const origins = index.byQuery.get(q.id).cells.filter(c => c.band === 'advance' &&
      index.points.get(c.id).observations[q.id].items.some(i => i.id === nearLeader.id && i.rank < c.rank))
    insights.push({
      id: 'local-vs-regional', title: 'Investigate the local blocker, not only the regional leader',
      reason: `${nearLeader.name} is ahead at ${nearLeader.nearAhead} of ${all.nearDenominator} near-top-three observations across all ${model.queries.length} studied queries; ${regionalLeader.name} leads regional top-three coverage.`,
      nextAction: 'Use the head-to-head view and inspect the profiles that repeatedly outrank the primary in its near-top-three areas.',
      queryId: q.id, regionId: 'all', originIds: origins.map(c => c.id),
      evidence: { regionalLeader, nearLeader, nearDenominator: all.nearDenominator },
      limitations: 'The near-top-three denominator is a subset of searches. These profiles are observed competitors, not automatically verified service competitors.',
    })
  }
  return insights.slice(0, 3)
}

export function strategyIntelligence(model) {
  if (cache.has(model)) return cache.get(model)
  const index = indexes(model)
  if (!index) {
    const unavailable = { available: false, reason: 'Strategy analysis requires a declared valid regular circular lattice.', regions: [], queryMatrix: [], insights: [], limitations: LIMITATIONS }
    cache.set(model, unavailable)
    return unavailable
  }
  const radius = model.sampling.radius_km / 1.609344
  const regions = [{ id: 'all', label: 'Whole study', originIds: index.cells.map(c => c.id) },
    { id: 'core', label: `Core · 0–${Math.min(2, radius).toLocaleString('en-US', { maximumFractionDigits: 1 })} mi`, originIds: [] }]
  for (const [band, low, high] of [['inner', 2, 5], ['outer', 5, radius]]) {
    if (radius <= low) continue
    for (const compass of ['ne', 'se', 'sw', 'nw']) regions.push({
      id: `${band}-${compass}`, label: `${compass.toUpperCase()} · >${low}–${Math.min(high, radius).toLocaleString('en-US', { maximumFractionDigits: 1 })} mi`, originIds: [],
    })
  }
  const lookup = new Map(regions.map(r => [r.id, r]))
  for (const cell of index.cells) lookup.get(regionId(cell)).originIds.push(cell.id)
  const metadata = new Map(model.businesses.map(b => [b.id, { id: b.id, name: b.name, address: b.address || '', cid: b.cid, placeId: b.placeId }]))
  const metrics = regions.map(r => regionMetrics(model, { ...r, count: r.originIds.length }, index, metadata))
  const result = { schema: 'geogrid-strategy-intelligence/v1', available: true, regions: metrics,
    queryMatrix: model.queries.map(q => ({ queryId: q.id, query: q.name, regions: metrics.filter(r => r.id !== 'all')
      .map(r => ({ regionId: r.id, count: r.count, ...r.perQuery[q.id] })) })),
    insights: evidenceInsights(model, metrics, index),
    source: { generatedAt: model.generatedAt, controls: model.controls, evidence: model.evidence },
    method: {
      geography: 'Core <=2 miles; nonoverlapping NE/SE/SW/NW sectors >2–5 and >5 miles, capped at study radius. Axes belong north/east; no invented neighborhood names.',
      regionalRivals: 'Mean query-specific top-three coverage across queries with complete observations; queries have equal weight, not demand or revenue weights.',
      localRivals: 'Count of appearances ahead where the primary ranks 4–10, pooled across query/origin pairs. Ties use ahead-when-primary-returned count, then profile ID.',
      unknown: 'Only complete, consistent, identity-bearing top30 observations support comparisons. Missing evidence is excluded from percentage denominators and reported separately.',
    }, limitations: LIMITATIONS }
  cache.set(model, result)
  return result
}

export function strategyMatchup(model, queryId, rivalId, selectedRegion = 'all') {
  if (!matchupCache.has(model)) matchupCache.set(model, new Map())
  const key = JSON.stringify([queryId, rivalId, selectedRegion]), stored = matchupCache.get(model)
  if (stored.has(key)) return stored.get(key)
  const strategy = strategyIntelligence(model), region = strategy.regions.find(r => r.id === selectedRegion)
  const counts = { primaryAhead: 0, rivalAhead: 0, tied: 0, primaryOnly: 0, rivalOnly: 0, neither: 0, unknown: 0 }
  if (!strategy.available || !region || !model.queries.some(q => q.id === queryId) ||
      !model.businesses.some(b => b.id === rivalId) || rivalId === model.targetId) {
    return { available: false, reason: 'Choose a known rival profile, query, and region.', cells: [], counts }
  }
  const territorial = territoryIntelligence(model, queryId), byId = new Map(territorial.cells.map(c => [c.id, c]))
  const points = new Map(model.points.map(p => [p.id, p]))
  const cells = region.originIds.map(id => {
    const c = byId.get(id), primaryRank = c?.rank ?? null
    const rivalRank = c?.band !== 'unknown' ? points.get(id)?.observations[queryId].items.find(i => i.id === rivalId && i.rank <= 30)?.rank ?? null : null
    const state = !c || c.band === 'unknown' ? 'unknown' :
      primaryRank === null ? rivalRank === null ? 'neither' : 'rivalOnly' :
      rivalRank === null ? 'primaryOnly' : primaryRank < rivalRank ? 'primaryAhead' : primaryRank > rivalRank ? 'rivalAhead' : 'tied'
    counts[state]++
    return { id, lat: c?.lat, lng: c?.lng, primaryRank, rivalRank, state }
  })
  const primaryWins = counts.primaryAhead + counts.primaryOnly, rivalWins = counts.rivalAhead + counts.rivalOnly
  const result = { available: true, queryId, regionId: selectedRegion, region, primary: meta(model, model.targetId), rival: meta(model, rivalId),
    cells, counts, primaryWins, rivalWins, comparedOrigins: region.count - counts.unknown,
    leader: primaryWins === rivalWins ? null : meta(model, primaryWins > rivalWins ? model.targetId : rivalId),
    leaderMetric: 'More complete origins with a better observed position or exclusive presence in the returned top30.',
    limitations: 'Neither means both absent from complete top30, not a tie in exact rank. Unknown observations cannot be compared. This is visibility, not sales or ranking difficulty.' }
  stored.set(key, result)
  return result
}

export function rivalPressure(model, regionId = 'all') {
  const region = strategyIntelligence(model).regions.find(r => r.id === regionId)
  return region ? { available: true, regionId, regional: region.rivals, local: region.nearRivals,
    completeDenominator: region.completeDenominator, nearDenominator: region.nearDenominator,
    primaryReturnedDenominator: region.primaryReturnedDenominator } : { available: false, regional: [], local: [] }
}
