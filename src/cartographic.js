// Locked v0.3.1 cartographic constants and pure helpers (owner approved).
export const CARTOGRAPHIC = Object.freeze({
  innerWidth: 48,
  innerOpacity: 0.16,
  borderScale: 0.45,
  hoverDurationMs: 200,
  hoverFadeMs: 200,
  contours: 'all',
  hoverBezier: Object.freeze([0.22, 1, 0.36, 1]),
  focusTopoBackgroundDim: 0.04,
  reliefThresholds: Object.freeze([4.2, 6.2, 7.8]),
})

export const DOMINANCE_TIERS = Object.freeze([
  Object.freeze({ tier: 0, name: 'Solid Interior', label: 'Solid Interior · #1' }),
  Object.freeze({ tier: 1, name: 'Stronghold', label: 'Stronghold · solid #1' }),
  Object.freeze({ tier: 2, name: 'Fortress Core', label: 'Fortress Core · unbreakable #1' }),
])
export const CONTESTED_EDGE = Object.freeze({ tier: -1, name: 'Contested Edge', label: 'Contested Edge · #1 border' })

// Dominance score: 1 + 4.5 * neighborWinShare + 4.5 * runnerUpDropoff (range 1..10).
export function dominanceScore(neighborWinShare, runnerUpDropoff) {
  const a = Math.max(0, Math.min(1, Number(neighborWinShare) || 0))
  const b = Math.max(0, Math.min(1, Number(runnerUpDropoff) || 0))
  return 1 + 4.5 * a + 4.5 * b
}

export function dominanceTierForScore(score) {
  const s = Number(score)
  if (!Number.isFinite(s)) return CONTESTED_EDGE
  if (s >= CARTOGRAPHIC.reliefThresholds[2]) return DOMINANCE_TIERS[2]
  if (s >= CARTOGRAPHIC.reliefThresholds[1]) return DOMINANCE_TIERS[1]
  if (s >= CARTOGRAPHIC.reliefThresholds[0]) return DOMINANCE_TIERS[0]
  return CONTESTED_EDGE
}

// Tau-coupled relief: contested pullback raises effective thresholds and
// attenuates scores at exposed edges so inner rings recede inside the
// shrunken territory instead of being chopped at the contested border.
export function reliefThresholdsAtTau(tau = 0) {
  const t = Math.max(0, Math.min(1, Number(tau) || 0))
  return CARTOGRAPHIC.reliefThresholds.map(base => base + t * (10 - base) * 0.35)
}

export function attenuateScoreAtTau(score, neighborWinShare, tau = 0) {
  const t = Math.max(0, Math.min(1, Number(tau) || 0))
  const share = Math.max(0, Math.min(1, Number(neighborWinShare) || 0))
  return (Number(score) || 0) - t * (1 - share) * 2.5
}

// Clip guards for hover lookups. A cursor point earns a dominance tier only
// when it is known, not under draped focus topography, on land when a land
// mask exists, and strictly inside the leader territory. Anything else is
// null (no phantom tier), never Contested Edge.
export function dominanceTierAtAllowed({ point = null, draped = false, hasLandMask = false, insideLand = true, insideTerritory = false } = {}) {
  if (!point) return false
  if (draped) return false
  if (hasLandMask && !insideLand) return false
  if (!insideTerritory) return false
  return true
}

// A cursor point earns an interpolated rank only when it is known, on land
// when a land mask exists, and inside the study boundary when territory
// clipping is active. Clipped water and offshore points return no rank.
export function rankAtPointAllowed({ point = null, hasLandMask = false, insideLand = true, clipTerritories = false, hasBoundary = false, insideBoundary = true } = {}) {
  if (!point) return false
  if (hasLandMask && !insideLand) return false
  if (clipTerritories && hasBoundary && !insideBoundary) return false
  return true
}

// Inward-only shapeburst strokes: exact Porter-Duff incremental alphas.
// Returns widest-first strokes; caller clips to the shape (0% exterior bleed).
export function innerShapeburstStrokes(widthPx = CARTOGRAPHIC.innerWidth, maxOpacity = CARTOGRAPHIC.innerOpacity, steps = null) {
  const w = Math.max(0, Number(widthPx) || 0)
  const max = Math.max(0, Math.min(1, Number(maxOpacity) || 0))
  const stepCount = Number(steps)
  const n = steps == null || !Number.isFinite(stepCount)
    ? Math.max(8, Math.min(18, Math.round(w / 2) || 8))
    : Math.max(1, Math.min(64, Math.round(stepCount)))
  const out = []
  let prevCum = 0
  for (let k = n; k >= 1; k--) {
    const u = k / n
    const targetCum = max * Math.pow(1 - u, 2.15)
    const stepAlpha = (targetCum - prevCum) / Math.max(0.001, 1 - prevCum)
    prevCum = targetCum
    if (stepAlpha > 0.0005) out.push({ lineWidth: 2 * w * k / n, alpha: stepAlpha, cumulative: targetCum })
  }
  return out
}

// cubic-bezier(0.22, 1, 0.36, 1) easing solver (Newton + bisection fallback).
export function cubicBezierEase(x, points = CARTOGRAPHIC.hoverBezier) {
  const t = Math.max(0, Math.min(1, Number(x) || 0))
  if (t === 0 || t === 1) return t
  const [x1, y1, x2, y2] = points
  const cx = s => 3 * (1 - s) ** 2 * s * x1 + 3 * (1 - s) * s ** 2 * x2 + s ** 3
  const cy = s => 3 * (1 - s) ** 2 * s * y1 + 3 * (1 - s) * s ** 2 * y2 + s ** 3
  let s = t
  for (let i = 0; i < 8; i++) {
    const err = cx(s) - t
    if (Math.abs(err) < 1e-6) return cy(s)
    const d = 3 * (1 - s) ** 2 * x1 + 6 * (1 - s) * s * (x2 - x1) + 3 * s ** 2 * (1 - x2)
    if (Math.abs(d) < 1e-6) break
    s -= err / d
    s = Math.max(0, Math.min(1, s))
  }
  let lo = 0, hi = 1
  s = t
  for (let i = 0; i < 24; i++) {
    if (cx(s) < t) lo = s; else hi = s
    s = (lo + hi) / 2
  }
  return cy(s)
}

export const RANK_MASTER_TIERS = Object.freeze([
  Object.freeze({ id: 'summit', label: '#1 Summit', min: 1, max: 1 }),
  Object.freeze({ id: 'pack', label: '#2-#3 3-Pack', min: 2, max: 3 }),
  Object.freeze({ id: 'page1', label: '#4-#10 Page 1', min: 4, max: 10 }),
  Object.freeze({ id: 'page2', label: '#11-#20 Page 2', min: 11, max: 20 }),
  Object.freeze({ id: 'page3', label: '#21-#30 Page 3', min: 21, max: 30 }),
])

export function masterTierForRank(rank) {
  const r = Number(rank)
  if (!Number.isFinite(r)) return null
  return RANK_MASTER_TIERS.find(t => r >= t.min && r <= t.max) || null
}
