// First-place influence inside the study, independent of base location/shortlist.
import { leaderIdentity, winnerAt } from './leader-colors.js'
const caches = new WeakMap()
export function distanceKm(a, b) {
  const rad = Math.PI / 180, dlat = (b.lat - a.lat) * rad, dlng = (b.lng - a.lng) * rad
  const h = Math.sin(dlat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dlng / 2) ** 2
  return 12742 * Math.asin(Math.sqrt(Math.min(1, h)))
}
export function profileColor(model, id) {
  const identity = leaderIdentity(model).identities.get(id)
  if (identity) return identity.color
  const index = Math.max(0, model.businesses.findIndex(b => b.id === id))
  const palette = ['#00e676', '#2979ff', '#ff9100', '#a855f7', '#ff1744', '#a3e635', '#ffdf00', '#00d4ff', '#ff6d00', '#6366f1']
  return palette[index] || `hsl(${(index * 137.508) % 360} 85% 60%)`
}
export function localLeaders(model, queryId, minimumWins = 3) {
  if (!caches.has(model)) caches.set(model, new Map())
  const cache = caches.get(model)
  const key = `${queryId}:${minimumWins === 1 ? 1 : 3}`
  if (cache.has(key)) return cache.get(key)
  const groups = new Map()
  for (const point of model.points) {
    const observation = point.observations[queryId]
    const winner = winnerAt(observation)
    if (!winner) continue
    if (!groups.has(winner.id)) groups.set(winner.id, [])
    groups.get(winner.id).push(point)
  }
  const threshold = minimumWins === 1 ? 1 : 3
  const primary = model.businesses.find(b => b.id === model.targetId)
  const rows = [...groups].map(([id, points]) => {
    const business = model.businesses.find(b => b.id === id)
    if (!business) return null
    const major = points.length >= threshold
    let cluster = []
    // Largest connected winning patch; a centroid of all wins could land in an
    // unrelated gap between distant clusters. Four-neighbor lattice distance.
    if (major) {
      const remaining = new Set(points)
      const step = model.sampling?.spacing_km
      while (remaining.size) {
        const component = [remaining.values().next().value]
        remaining.delete(component[0])
        for (let i = 0; i < component.length; i++) {
          for (const other of remaining) {
            if (step && distanceKm(component[i], other) <= step * 1.15) {
              component.push(other); remaining.delete(other)
            }
          }
        }
        if (component.length > cluster.length) cluster = component
      }
    }
    const center = cluster.length ? {
      lat: cluster.reduce((sum, p) => sum + p.lat, 0) / cluster.length,
      lng: cluster.reduce((sum, p) => sum + p.lng, 0) / cluster.length,
    } : null
    const hasBase = Number.isFinite(business.lat) && Number.isFinite(business.lng)
    const beyondKm = hasBase && primary && model.sampling?.radius_km
      ? distanceKm(primary, business) - model.sampling.radius_km : null
    const outside = beyondKm !== null && beyondKm > 0
    return { business, wins: points.length, share: points.length / model.points.length,
      major, center, clusterSize: cluster.length, outside, hasBase,
      connector: !!(hasBase && center && beyondKm > 3.218688),
      badge: leaderIdentity(model).identities.get(id)?.badge || '—',
      color: profileColor(model, id) }
  }).filter(Boolean).sort((a, b) => b.wins - a.wins || a.business.id.localeCompare(b.business.id))
  const result = { threshold, rows, byId: new Map(rows.map(r => [r.business.id, r])),
    majorIds: new Set(rows.filter(r => r.major).map(r => r.business.id)),
    coloredPoints: rows.filter(r => r.major).reduce((sum, r) => sum + r.wins, 0) }
  cache.set(key, result)
  return result
}
