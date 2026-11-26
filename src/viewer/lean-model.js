// Validation and formatting for the lean hosted model "geogrid-viewer/v1".
// Pure functions with no DOM access so they can be tested in plain Node.
export const LEAN_SCHEMA = 'geogrid-viewer/v1'
export const COMPANION_SCHEMAS = ['geogrid-companion/v1', 'geogrid-battlefield/v1']

const finite = v => typeof v === 'number' && Number.isFinite(v)
const optNumber = v => (finite(v) ? v : null)
const text = (v, fallback = '') => (typeof v === 'string' ? v : v == null ? fallback : String(v))

function fail(path, message) {
  throw new Error(`geogrid-viewer/v1: ${path} ${message}`)
}

function requireObject(value, path) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) fail(path, 'must be an object')
  return value
}

const SCORE_KEYS = ['foundShare', 'solv', 'visibleShare', 'arp', 'atrp', 'centerRank']

function normalizeScores(input) {
  const scores = {}
  for (const key of SCORE_KEYS) scores[key] = optNumber(input?.[key])
  return scores
}

function normalizeZone(zone, index, kind) {
  requireObject(zone, `zones.${kind}[${index}]`)
  return {
    id: text(zone.id, `${kind}-${index + 1}`),
    label: text(zone.label, text(zone.id, `Zone ${index + 1}`)),
    points: finite(zone.points) ? zone.points : 0,
    foundShare: optNumber(zone.foundShare),
    avgRank: optNumber(zone.avgRank),
  }
}

function normalizeCompetitor(row, index) {
  requireObject(row, `competitors[${index}]`)
  return {
    name: text(row.name, 'Unnamed business'),
    top3Share: optNumber(row.top3Share),
    outrankShare: optNumber(row.outrankShare),
    avgRank: optNumber(row.avgRank),
    presenceShare: optNumber(row.presenceShare),
  }
}

function normalizeDelta(input) {
  if (input == null) return null
  requireObject(input, 'delta')
  // Score changes may sit under delta.scores or directly on delta (current minus previous).
  const source = input.scores && typeof input.scores === 'object' ? input.scores : input
  return {
    previousScanId: input.previousScanId == null ? null : text(input.previousScanId),
    previousCreatedAt: input.previousCreatedAt == null ? null : text(input.previousCreatedAt),
    scores: normalizeScores(source),
    improved: optNumber(input.improved),
    declined: optNumber(input.declined),
    unchanged: optNumber(input.unchanged),
  }
}

export function normalizeLeanModel(input) {
  requireObject(input, 'model')
  if (input.schema !== LEAN_SCHEMA) fail('schema', `must be "${LEAN_SCHEMA}"`)
  const business = requireObject(input.business, 'business')
  if (!finite(business.lat) || !finite(business.lng)) fail('business', 'needs numeric lat and lng')
  if (!Array.isArray(input.points) || !input.points.length) fail('points', 'must be a non-empty array')
  const scan = input.scan && typeof input.scan === 'object' ? input.scan : {}
  const points = input.points.map((p, i) => {
    requireObject(p, `points[${i}]`)
    if (!finite(p.lat) || !finite(p.lng)) fail(`points[${i}]`, 'needs numeric lat and lng')
    const rank = Number.isInteger(p.rank) && p.rank >= 1 ? p.rank : null
    const hex = p.hex && typeof p.hex === 'object' ? {
      unitQ: finite(p.hex.unit_q) ? p.hex.unit_q : null,
      unitR: finite(p.hex.unit_r) ? p.hex.unit_r : null,
      firstRungMiles: optNumber(p.hex.first_rung_miles),
      rungMembership: Array.isArray(p.hex.rung_membership) ? p.hex.rung_membership.filter(finite) : [],
    } : null
    return {
      row: finite(p.row) ? p.row : null,
      col: finite(p.col) ? p.col : null,
      lat: p.lat,
      lng: p.lng,
      rank,
      label: text(p.label, rank ? `Rank ${rank}` : 'Not found'),
      heat: optNumber(p.heat),
      hex,
    }
  })
  const zones = input.zones && typeof input.zones === 'object' ? input.zones : {}
  const zoneList = (list, kind) => (Array.isArray(list) ? list.map((z, i) => normalizeZone(z, i, kind)) : [])
  const zoneCompetitors = Array.isArray(input.zoneCompetitors)
    ? input.zoneCompetitors.map((entry, i) => {
      requireObject(entry, `zoneCompetitors[${i}]`)
      return {
        zoneId: text(entry.zoneId),
        top: Array.isArray(entry.top) ? entry.top.map((row, j) => normalizeCompetitor(row, j)) : [],
      }
    })
    : []
  return {
    schema: LEAN_SCHEMA,
    business: { name: text(business.name, 'Business'), lat: business.lat, lng: business.lng },
    scan: {
      id: text(scan.id),
      keyword: text(scan.keyword),
      gridSize: finite(scan.gridSize) ? scan.gridSize : null,
      radiusM: finite(scan.radiusM) && scan.radiusM > 0 ? scan.radiusM : null,
      createdAt: text(scan.createdAt),
      device: text(scan.device),
      geometry: text(scan.geometry),
      spacingMiles: optNumber(scan.spacingMiles),
    },
    points,
    scores: normalizeScores(input.scores),
    zones: { rings: zoneList(zones.rings, 'rings'), quadrants: zoneList(zones.quadrants, 'quadrants') },
    competitors: Array.isArray(input.competitors) ? input.competitors.map(normalizeCompetitor) : [],
    delta: normalizeDelta(input.delta),
    zoneCompetitors,
  }
}

// Shares are fractions from 0 to 1.
export const formatShare = v => (finite(v) ? `${Math.round(v * 1000) / 10}%` : 'n/a')
export const formatRank = v => (finite(v) ? String(Math.round(v * 10) / 10) : 'n/a')
export function formatSigned(v, kind) {
  if (!finite(v)) return 'n/a'
  const rounded = kind === 'share' ? Math.round(v * 1000) / 10 : Math.round(v * 10) / 10
  const sign = rounded > 0 ? '+' : rounded < 0 ? '-' : ''
  return `${sign}${Math.abs(rounded)}${kind === 'share' ? ' pts' : ''}`
}

export function formatDate(value) {
  const date = new Date(value)
  if (!value || Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c])
