// Deterministic Strike-Zone and Leverage Engine (Layer A).
// Pure module: no DOM, no network, no randomness.
// Output schema: geogrid-campaign-engine/v1.
import { territoryIntelligence } from './territory-intelligence.js'

const MILE_KM = 1.609344
const SQUARE_STEPS = [[1, 0], [-1, 0], [0, 1], [0, -1]]
const HEX_STEPS = [[1, 0], [-1, 0], [0, 1], [0, -1], [1, -1], [-1, 1]]
const engineCache = new WeakMap()

export const CAMPAIGN_ENGINE_SCHEMA = 'geogrid-campaign-engine/v1'

export const CAMPAIGN_WEIGHTS = Object.freeze({
  gap: 0.40,
  weak: 0.25,
  lift: 0.20,
  reach: 0.15,
  fortress: 0.5,
  detached: 0.5,
})

const LIMITATIONS = 'One snapshot. W ranks observed structure. It is not a ranking probability, a demand estimate or a revenue forecast.'

const finite = v => typeof v === 'number' && Number.isFinite(v)
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v))
const round2 = v => Math.round(v * 100) / 100
const keyOf = (x, y) => `${x},${y}`

export function distanceKm(a, b) {
  const rad = Math.PI / 180
  const dLat = (b.lat - a.lat) * rad
  const dLng = (b.lng - a.lng) * rad
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) ** 2
  return 6371.0088 * 2 * Math.asin(Math.sqrt(Math.min(1, h)))
}

export function prominenceIndex(business) {
  const rating = business?.rating
  const reviews = business?.reviews
  if (!finite(rating) || !finite(reviews) || rating <= 0 || reviews < 0) {
    return { pm: 0, unrated: true }
  }
  const pm = Math.log10(1 + reviews) * ((rating / 5) ** 2)
  return { pm, unrated: false }
}

function hexAxialOf(point, step) {
  const h = point?.hex
  if (!h) return null
  if (Number.isInteger(h.q) && Number.isInteger(h.r)) return [h.q, h.r]
  if (Number.isInteger(h.unit_q) && Number.isInteger(h.unit_r) &&
      h.unit_q % step === 0 && h.unit_r % step === 0) {
    return [h.unit_q / step, h.unit_r / step]
  }
  return null
}

function buildPinAdjacency(model) {
  const s = model.sampling
  const points = model.points || []
  const adj = new Map(points.map(p => [p.id, []]))
  if (!points.length || !s) return adj

  if (s.geometry === 'hex_radius') {
    const step = Number.isInteger(s.hex?.step) && s.hex.step > 0 ? s.hex.step : 1
    const allAxial = points.every(p => hexAxialOf(p, step) !== null)
    if (allAxial) {
      const byAxial = new Map()
      const coords = new Map()
      for (const p of points) {
        const [q, r] = hexAxialOf(p, step)
        byAxial.set(keyOf(q, r), p.id)
        coords.set(p.id, [q, r])
      }
      for (const p of points) {
        const [q, r] = coords.get(p.id)
        const nbs = adj.get(p.id)
        for (const [dq, dr] of HEX_STEPS) {
          const nbId = byAxial.get(keyOf(q + dq, r + dr))
          if (nbId) nbs.push(nbId)
        }
      }
      return adj
    }
    const thresholdKm = 1.25 * (s.spacing_km || 0.8)
    for (let i = 0; i < points.length; i++) {
      const a = points[i]
      for (let j = i + 1; j < points.length; j++) {
        const b = points[j]
        if (Math.abs(a.lat - b.lat) * 111.32 > thresholdKm * 1.1) continue
        if (distanceKm(a, b) <= thresholdKm) {
          adj.get(a.id).push(b.id)
          adj.get(b.id).push(a.id)
        }
      }
    }
    return adj
  }

  if (s.geometry === 'radius_grid' && s.center && finite(s.spacing_km) && s.spacing_km > 0) {
    const step = s.spacing_km / 111.195
    const cosLat = Math.cos(s.center.lat * Math.PI / 180)
    const byGrid = new Map()
    const coords = new Map()
    for (const p of points) {
      const gx = Math.round((p.lng - s.center.lng) * cosLat / step)
      const gy = Math.round((p.lat - s.center.lat) / step)
      byGrid.set(keyOf(gx, gy), p.id)
      coords.set(p.id, [gx, gy])
    }
    for (const p of points) {
      const [gx, gy] = coords.get(p.id)
      const nbs = adj.get(p.id)
      for (const [dx, dy] of SQUARE_STEPS) {
        const nbId = byGrid.get(keyOf(gx + dx, gy + dy))
        if (nbId) nbs.push(nbId)
      }
    }
  }
  return adj
}

export function detectLandmassComponents(model) {
  const landClipped = model.sampling?.land_clipped === true
  const points = model.points || []
  const byPin = new Map()
  if (!landClipped || !points.length) {
    for (const p of points) byPin.set(p.id, 'unknown')
    return { landClipped: false, byPin, home: { pins: points.length, originIds: points.map(p => p.id) }, detached: [], components: [] }
  }

  const target = model.businesses?.find(b => b.id === model.targetId)
  const center = (finite(target?.lat) && finite(target?.lng))
    ? { lat: target.lat, lng: target.lng }
    : model.sampling?.center || { lat: points[0].lat, lng: points[0].lng }
  const cosLat = Math.cos(center.lat * Math.PI / 180)
  const adj = buildPinAdjacency(model)
  const pointMap = new Map(points.map(p => [p.id, p]))

  // Find pin nearest base to identify the home landmass.
  let homePinId = points[0].id
  let homeDist = Infinity
  for (const p of points) {
    const d = distanceKm(center, p)
    if (d < homeDist) { homeDist = d; homePinId = p.id }
  }

  const visited = new Set()
  const rawComponents = []
  for (const p of points) {
    if (visited.has(p.id)) continue
    const comp = []
    const stack = [p.id]
    visited.add(p.id)
    while (stack.length) {
      const id = stack.pop()
      comp.push(id)
      for (const nb of adj.get(id) || []) {
        if (!visited.has(nb)) {
          visited.add(nb)
          stack.push(nb)
        }
      }
    }
    comp.sort()
    rawComponents.push(comp)
  }

  const homeIdx = rawComponents.findIndex(c => c.includes(homePinId))
  const homeIds = homeIdx >= 0 ? rawComponents[homeIdx] : rawComponents[0]
  const otherComps = rawComponents
    .filter((_, idx) => idx !== (homeIdx >= 0 ? homeIdx : 0))
    .sort((a, b) => b.length - a.length || a[0].localeCompare(b[0]))

  for (const id of homeIds) byPin.set(id, 'home')
  const detached = otherComps.map((originIds, idx) => {
    const cid = `C${idx + 1}`
    let sumLat = 0, sumLng = 0
    for (const id of originIds) {
      byPin.set(id, cid)
      const pt = pointMap.get(id)
      sumLat += pt.lat
      sumLng += pt.lng
    }
    const meanLat = sumLat / originIds.length
    const meanLng = sumLng / originIds.length
    const eastMiles = ((meanLng - center.lng) * cosLat * 111.195) / MILE_KM
    const northMiles = ((meanLat - center.lat) * 111.195) / MILE_KM
    return {
      id: cid,
      pins: originIds.length,
      originIds,
      offsetMiles: {
        east: Math.round(eastMiles * 10) / 10,
        north: Math.round(northMiles * 10) / 10,
      },
    }
  })

  return {
    landClipped: true,
    byPin,
    home: { pins: homeIds.length, originIds: homeIds },
    detached,
    components: [{ id: 'home', pins: homeIds.length, originIds: homeIds }, ...detached],
  }
}

function gapScore(rank) {
  if (rank <= 3) return null
  if (rank <= 10) return 1 - (rank - 4) / 8
  if (rank <= 30) return 0.2 * (1 - (rank - 11) / 20)
  return 0
}

function formatPlayTitle(mechanism, queryName, strongQueryName, leadHolder, points) {
  if (mechanism === 'service_gap') {
    const holder = leadHolder?.name || 'Local specialists'
    return `${queryName}: your ${strongQueryName || 'other service'} strength does not carry over. ${holder} holds the pack.`
  }
  if (mechanism === 'weak_pack') {
    const holder = leadHolder?.name || 'Weaker profiles'
    const rating = finite(leadHolder?.rating) ? leadHolder.rating.toFixed(1) : 'unrated'
    const reviews = finite(leadHolder?.reviews) ? leadHolder.reviews.toLocaleString('en-US') : '0'
    return `${queryName}: outranked by ${holder}, ${rating} stars, ${reviews} reviews`
  }
  if (mechanism === 'seam') {
    return `${queryName}: ${points} points one or two ranks from the pack`
  }
  if (mechanism === 'hold_thin') {
    return `${queryName}: holding the pack without a single first place`
  }
  return `${queryName}: ${points} longer climbs`
}

export function campaignEngine(model) {
  if (engineCache.has(model)) return engineCache.get(model)

  const targetBiz = model.businesses?.find(b => b.id === model.targetId) || null
  const targetPmInfo = prominenceIndex(targetBiz)
  const targetPm = targetPmInfo.pm
  const center = (finite(targetBiz?.lat) && finite(targetBiz?.lng))
    ? { lat: targetBiz.lat, lng: targetBiz.lng }
    : model.sampling?.center || null

  const businessById = new Map((model.businesses || []).map(b => [b.id, b]))
  const pmById = new Map()
  for (const b of model.businesses || []) pmById.set(b.id, prominenceIndex(b))

  const profileCategory = targetBiz?.category || null
  const businessCategory = model.businessCategory || null
  const categoryConflict = (businessCategory && profileCategory && businessCategory !== profileCategory)
    ? { business: businessCategory, profile: profileCategory }
    : null

  const intelByQuery = new Map()
  let anyAvailable = false
  for (const q of model.queries || []) {
    const ti = territoryIntelligence(model, q.id)
    intelByQuery.set(q.id, ti)
    if (ti.available) anyAvailable = true
  }

  if (!anyAvailable || !center || !targetBiz) {
    const unavailable = {
      schema: CAMPAIGN_ENGINE_SCHEMA,
      available: false,
      reason: 'Campaign analysis requires a valid regular circular lattice with complete depth-30 evidence.',
      weights: { ...CAMPAIGN_WEIGHTS },
      target: targetBiz ? {
        id: targetBiz.id,
        cid: targetBiz.cid || null,
        name: targetBiz.name,
        pm: round2(targetPm),
        unrated: targetPmInfo.unrated,
        rating: targetBiz.rating ?? null,
        reviews: targetBiz.reviews ?? null,
        category: profileCategory,
        categoryConflict,
      } : null,
      landmass: { landClipped: false, home: { pins: 0 }, detached: [] },
      reachByQuery: {},
      queries: {},
      limitations: LIMITATIONS,
    }
    engineCache.set(model, unavailable)
    return unavailable
  }

  const landmass = detectLandmassComponents(model)
  const pointById = new Map(model.points.map(p => [p.id, p]))
  const spacingKm = model.sampling?.spacing_km || 0.804672
  const fortressRadiusKm = 1.5 * spacingKm
  const radiusMiles = Math.max(1, Math.ceil((model.sampling?.radius_km || 0) / MILE_KM))

  // Pre-compute cell lookup & distance ring per pin
  const distMilesByPin = new Map()
  const ringByPin = new Map()
  for (const p of model.points) {
    const dm = finite(p.distance) ? p.distance / MILE_KM : distanceKm(center, p) / MILE_KM
    distMilesByPin.set(p.id, dm)
    ringByPin.set(p.id, Math.min(radiusMiles - 1, Math.max(0, Math.floor(dm))))
  }

  // Pre-compute complete observations per query & pin
  const completeCellMap = new Map() // queryId -> Map<pinId, { rank, items, tiCell }>
  const reachByQuery = {}
  for (const q of model.queries) {
    const ti = intelByQuery.get(q.id)
    const qMap = new Map()
    const ringComplete = new Array(radiusMiles).fill(0)
    const ringTop10 = new Array(radiusMiles).fill(0)

    for (const c of ti.cells) {
      if (c.missing || !pointById.has(c.id)) continue
      const pt = pointById.get(c.id)
      const items = c.band === 'unknown' ? [] : (pt.observations?.[q.id]?.items || [])
      const rank = c.band === 'unknown' ? null : (c.rank ?? 31)
      qMap.set(c.id, { band: c.band, rank, items, cell: c, point: pt })
      if (c.band !== 'unknown') {
        const ring = ringByPin.get(c.id)
        ringComplete[ring]++
        if (rank <= 10) ringTop10[ring]++
      }
    }
    completeCellMap.set(q.id, qMap)
    reachByQuery[q.id] = ringComplete.map((den, idx) => den > 0 ? round2(ringTop10[idx] / den) : 0)
  }

  // Exact (unrounded) ring reach per query for W calculation
  const rawReachByQuery = {}
  for (const q of model.queries) {
    const qMap = completeCellMap.get(q.id)
    const ringComplete = new Array(radiusMiles).fill(0)
    const ringTop10 = new Array(radiusMiles).fill(0)
    for (const [pinId, entry] of qMap) {
      if (entry.band === 'unknown') continue
      const ring = ringByPin.get(pinId)
      ringComplete[ring]++
      if (entry.rank <= 10) ringTop10[ring]++
    }
    rawReachByQuery[q.id] = ringComplete.map((den, idx) => den > 0 ? ringTop10[idx] / den : 0)
  }

  const queriesOut = {}
  const queryNameById = new Map(model.queries.map(q => [q.id, q.name]))

  for (const q of model.queries) {
    const qMap = completeCellMap.get(q.id)
    const ti = intelByQuery.get(q.id)

    // Compute top-3 category share across all complete pins for this query
    const catCounts = new Map()
    let catTotal = 0
    // Also track head-to-head aheadWhereBothAppear[bizId] = [ahead, both] and firstPlacePins[bizId]
    const aheadStats = new Map() // bizId -> { ahead, both }
    const firstPlacePins = new Map() // bizId -> [pinId, ...]
    const firstPlaceTargetTop30 = new Map() // bizId -> count where target is top 30

    for (const [pinId, entry] of qMap) {
      if (entry.band === 'unknown') continue
      const targetRank = entry.rank // 1..30 or 31
      const targetPresent = targetRank <= 30

      for (const item of entry.items) {
        if (item.rank > 30) continue
        if (item.rank <= 3) {
          const cat = item.category || businessById.get(item.id)?.category || null
          if (cat) {
            catCounts.set(cat, (catCounts.get(cat) || 0) + 1)
            catTotal++
          }
        }
        if (item.id === model.targetId) continue
        if (item.rank === 1) {
          if (!firstPlacePins.has(item.id)) firstPlacePins.set(item.id, [])
          firstPlacePins.get(item.id).push(pinId)
          if (targetPresent) {
            firstPlaceTargetTop30.set(item.id, (firstPlaceTargetTop30.get(item.id) || 0) + 1)
          }
        }
        if (targetPresent) {
          let st = aheadStats.get(item.id)
          if (!st) { st = { ahead: 0, both: 0 }; aheadStats.set(item.id, st) }
          st.both++
          if (item.rank < targetRank) st.ahead++
        }
      }
    }

    const categoryShareTop3 = {}
    let dominantCategory = null
    let dominantShare = 0
    for (const [cat, count] of [...catCounts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))) {
      const share = catTotal > 0 ? count / catTotal : 0
      categoryShareTop3[cat] = round2(share)
      if (share > dominantShare) {
        dominantShare = share
        dominantCategory = cat
      }
    }

    const categoryMismatch = (dominantCategory && dominantShare >= 0.60 && profileCategory && dominantCategory !== profileCategory)
      ? {
        dominantCategory,
        share: round2(dominantShare),
        targetCategory: profileCategory,
      }
      : null

    // Per-pin scoring
    const cells = []
    const cellById = new Map()
    const fortressPinsByHolder = new Map() // holderId -> [pinId, ...]

    for (const c of ti.cells) {
      if (c.missing || !pointById.has(c.id)) continue
      const entry = qMap.get(c.id)
      const pt = entry.point
      const lm = landmass.byPin.get(c.id) || 'unknown'
      const isDetached = landmass.landClipped && lm !== 'home'
      const ring = ringByPin.get(c.id)
      const distMiles = distMilesByPin.get(c.id)

      if (entry.band === 'unknown') {
        const cellObj = {
          id: c.id,
          lat: pt.lat,
          lng: pt.lng,
          distanceMiles: round2(distMiles),
          ring,
          rank: null,
          w: null,
          wRaw: null,
          zone: 'unknown',
          thin: false,
          gap: null,
          weak: null,
          lift: null,
          reach: null,
          gateId: null,
          gateCid: null,
          mustPass: [],
          fortressId: null,
          fortressCid: null,
          landmass: lm,
          play: null,
          supportingQueryIds: [],
        }
        cells.push(cellObj)
        cellById.set(c.id, cellObj)
        continue
      }

      const r = entry.rank // 1..30 or 31
      // Check Fortress: any top-3 non-target profile with reviews >= 150 within 1.5 * spacing
      let fortressHolder = null
      for (const item of entry.items) {
        if (item.rank > 3 || item.id === model.targetId) continue
        const biz = businessById.get(item.id)
        const reviews = biz?.reviews ?? item.reviews
        const lat = finite(biz?.lat) ? biz.lat : item.lat
        const lng = finite(biz?.lng) ? biz.lng : item.lng
        if (finite(reviews) && reviews >= 150 && finite(lat) && finite(lng)) {
          if (distanceKm(pt, { lat, lng }) <= fortressRadiusKm) {
            fortressHolder = {
              id: item.id,
              cid: biz?.cid || item.cid || null,
              name: biz?.name || item.name || item.id,
              reviews,
              rating: biz?.rating ?? item.rating ?? null,
            }
            break
          }
        }
      }
      const fort = Boolean(fortressHolder)
      if (fortressHolder) {
        if (!fortressPinsByHolder.has(fortressHolder.id)) fortressPinsByHolder.set(fortressHolder.id, [])
        fortressPinsByHolder.get(fortressHolder.id).push(c.id)
      }

      // Cross-query Lift & supporting queries
      let lift = 0
      const supportingQueryIds = []
      for (const otherQ of model.queries) {
        if (otherQ.id === q.id) continue
        const otherEntry = completeCellMap.get(otherQ.id).get(c.id)
        if (!otherEntry || otherEntry.band === 'unknown') continue
        const or = otherEntry.rank
        if (or <= 3) {
          lift = 1.0
          supportingQueryIds.push(otherQ.id)
        } else if (or <= 10 && or <= r - 3 && lift < 0.5) {
          lift = 0.5
        }
      }

      // Reach(c) = max over queries of rawReachByQuery[q][ring]
      let reach = 0
      for (const otherQ of model.queries) {
        const rr = rawReachByQuery[otherQ.id][ring] || 0
        if (rr > reach) reach = rr
      }
      const queryRingReach = rawReachByQuery[q.id][ring] || 0

      // MustPass(c, q): profiles at ranks 3 .. min(r - 1, 10), excluding target
      let gap = null, weak = null, wRaw = null, w = null
      let gateId = null, gateCid = null
      const mustPass = []

      if (r >= 4) {
        gap = gapScore(r)
        const maxMpRank = Math.min(r - 1, 10)
        let gatePm = -Infinity
        for (const item of entry.items) {
          if (item.rank < 3 || item.rank > maxMpRank || item.id === model.targetId) continue
          const biz = businessById.get(item.id)
          const pInfo = pmById.get(item.id) || prominenceIndex({ rating: item.rating, reviews: item.reviews })
          mustPass.push({
            id: item.id,
            cid: biz?.cid || item.cid || null,
            name: biz?.name || item.name || item.id,
            rank: item.rank,
            rating: biz?.rating ?? item.rating ?? null,
            reviews: biz?.reviews ?? item.reviews ?? null,
            pm: round2(pInfo.pm),
          })
          if (pInfo.pm > gatePm) {
            gatePm = pInfo.pm
            gateId = item.id
            gateCid = biz?.cid || item.cid || null
          }
        }
        weak = mustPass.length > 0 ? clamp(0.5 + (targetPm - gatePm) / 2, 0, 1) : 0
        wRaw = 100 * (
          CAMPAIGN_WEIGHTS.gap * gap +
          CAMPAIGN_WEIGHTS.weak * weak +
          CAMPAIGN_WEIGHTS.lift * lift +
          CAMPAIGN_WEIGHTS.reach * reach
        ) * (fort ? CAMPAIGN_WEIGHTS.fortress : 1) * (isDetached ? CAMPAIGN_WEIGHTS.detached : 1)
        w = Math.round(wRaw)
      }

      // Zone class (first match wins, Section 2.6)
      let zone
      if (r <= 3) zone = 'hold'
      else if (isDetached) zone = 'detached'
      else if (fort) zone = 'fortress'
      else if (wRaw >= 60) zone = 'strike'
      else if (wRaw >= 40) zone = 'contest'
      else if (queryRingReach < 0.10) zone = 'out_of_reach'
      else if (r <= 30) zone = 'long'
      else zone = 'absent'

      // Check weak_pack membership: 4 <= r <= 10 and any top-3 non-target holder has Pm <= Pm_target - 0.5
      let hasWeakPackHolder = false
      if (r >= 4 && r <= 10) {
        for (const item of entry.items) {
          if (item.rank > 3 || item.id === model.targetId) continue
          const pInfo = pmById.get(item.id) || prominenceIndex({ rating: item.rating, reviews: item.reviews })
          if (pInfo.pm <= targetPm - 0.5) {
            hasWeakPackHolder = true
            break
          }
        }
      }

      const cellObj = {
        id: c.id,
        lat: pt.lat,
        lng: pt.lng,
        distanceMiles: round2(distMiles),
        ring,
        rank: r <= 30 ? r : null,
        effectiveRank: r,
        w,
        wRaw: wRaw !== null ? round2(wRaw) : null,
        zone,
        thin: r === 3,
        gap: gap !== null ? round2(gap) : null,
        weak: weak !== null ? round2(weak) : null,
        lift,
        reach: round2(reach),
        gateId,
        gateCid,
        mustPass,
        fortressId: fortressHolder?.id || null,
        fortressCid: fortressHolder?.cid || null,
        landmass: lm,
        play: null,
        supportingQueryIds,
        _hasWeakPackHolder: hasWeakPackHolder,
      }
      cells.push(cellObj)
      cellById.set(c.id, cellObj)
    }

    // Plays: home-landmass pins only (Section 2.7), precedence dedupe:
    // service_gap > weak_pack > seam > long_climb, plus hold_thin for r <= 3.
    const homeComplete = cells.filter(c => c.zone !== 'unknown' && (!landmass.landClipped || c.landmass === 'home'))
    const hasRank1 = homeComplete.some(c => c.effectiveRank === 1)

    const buckets = {
      service_gap: [],
      weak_pack: [],
      seam: [],
      long_climb: [],
      hold_thin: [],
    }
    const assigned = new Set()

    for (const c of homeComplete) {
      if (c.effectiveRank <= 3) {
        if (c.effectiveRank === 3 || !hasRank1) {
          buckets.hold_thin.push(c)
          c.play = `${q.id}:hold_thin`
        }
        continue
      }
      if (c.lift === 1) {
        buckets.service_gap.push(c)
        assigned.add(c.id)
        c.play = `${q.id}:service_gap`
      }
    }
    for (const c of homeComplete) {
      if (c.effectiveRank <= 3 || assigned.has(c.id)) continue
      if (c._hasWeakPackHolder) {
        buckets.weak_pack.push(c)
        assigned.add(c.id)
        c.play = `${q.id}:weak_pack`
      }
    }
    for (const c of homeComplete) {
      if (c.effectiveRank <= 3 || assigned.has(c.id)) continue
      if (c.effectiveRank === 4 || c.effectiveRank === 5) {
        buckets.seam.push(c)
        assigned.add(c.id)
        c.play = `${q.id}:seam`
      }
    }
    for (const c of homeComplete) {
      if (c.effectiveRank <= 3 || assigned.has(c.id)) continue
      if (c.zone === 'strike' || c.zone === 'contest') {
        buckets.long_climb.push(c)
        assigned.add(c.id)
        c.play = `${q.id}:long_climb`
      }
    }

    const buildPlay = (mechanism, playCells) => {
      if (!playCells.length) return null
      // Count top-3 appearances of non-target profiles across playCells
      const holderCounts = new Map()
      const supportingCounts = new Map()
      for (const c of playCells) {
        const entry = qMap.get(c.id)
        for (const item of entry.items) {
          if (item.rank > 3 || item.id === model.targetId) continue
          holderCounts.set(item.id, (holderCounts.get(item.id) || 0) + 1)
        }
        for (const sq of c.supportingQueryIds) {
          supportingCounts.set(sq, (supportingCounts.get(sq) || 0) + 1)
        }
      }
      const topHolders = [...holderCounts.entries()]
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
        .slice(0, 5)
        .map(([id, packCount]) => {
          const biz = businessById.get(id)
          const pInfo = pmById.get(id) || { pm: 0, unrated: true }
          const ahead = aheadStats.get(id) || { ahead: 0, both: 0 }
          const milesFromBase = (finite(biz?.lat) && finite(biz?.lng))
            ? round2(distanceKm(center, { lat: biz.lat, lng: biz.lng }) / MILE_KM)
            : null
          return {
            id,
            cid: biz?.cid || null,
            name: biz?.name || id,
            rating: biz?.rating ?? null,
            reviews: biz?.reviews ?? null,
            pm: round2(pInfo.pm),
            unrated: pInfo.unrated,
            lat: finite(biz?.lat) ? biz.lat : null,
            lng: finite(biz?.lng) ? biz.lng : null,
            domain: biz?.domain || null,
            category: biz?.category || null,
            packCount,
            milesFromBase,
            aheadWhereBothAppear: [ahead.ahead, ahead.both],
          }
        })

      const leadHolder = topHolders[0] || null
      const supportingQueryIds = [...supportingCounts.entries()]
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
        .map(([sq]) => sq)
      const strongQueryName = supportingQueryIds.length ? queryNameById.get(supportingQueryIds[0]) : null

      const scoredW = playCells.filter(c => finite(c.w))
      const leverage = scoredW.reduce((s, c) => s + c.w, 0)
      const meanW = scoredW.length ? Math.round(leverage / scoredW.length) : null

      let diagnosis = null
      if (leadHolder && leadHolder.pm <= round2(targetPm - 0.5) &&
          leadHolder.aheadWhereBothAppear[1] > 0 &&
          leadHolder.aheadWhereBothAppear[0] / leadHolder.aheadWhereBothAppear[1] >= 0.90) {
        diagnosis = 'relevance_not_reputation'
      }

      // Compute ring reach summary for play's pins
      const minRing = Math.min(...playCells.map(c => c.ring))
      const maxRing = Math.max(...playCells.map(c => c.ring))
      const ringReach = reachByQuery[q.id][minRing] ?? 0
      const rank1Count = playCells.filter(c => c.effectiveRank === 1).length

      return {
        id: `${q.id}:${mechanism}`,
        queryId: q.id,
        queryName: q.name,
        mechanism,
        title: formatPlayTitle(mechanism, q.name, strongQueryName, leadHolder, playCells.length),
        originIds: playCells.map(c => c.id),
        points: playCells.length,
        meanW,
        leverage,
        leadHolder,
        topHolders: topHolders.slice(0, 3),
        diagnosis,
        categoryMismatch: ['service_gap', 'weak_pack', 'hold_thin'].includes(mechanism) ? categoryMismatch : null,
        supportingQueryIds,
        strongQueryName,
        minRing,
        maxRing,
        ringReach,
        rank1Count,
      }
    }

    const plays = ['service_gap', 'weak_pack', 'seam', 'long_climb', 'hold_thin']
      .map(mech => buildPlay(mech, buckets[mech]))
      .filter(Boolean)
      .sort((a, b) => b.leverage - a.leverage || b.points - a.points || a.id.localeCompare(b.id))

    // Avoid list (Section 2.7):
    // 1. detached_landmass: each non-home component holding any pin at r <= 10
    const avoid = []
    if (landmass.landClipped) {
      for (const comp of landmass.detached) {
        const compCells = comp.originIds.map(id => cellById.get(id)).filter(Boolean)
        const top10Count = compCells.filter(c => c.rank !== null && c.rank <= 10).length
        const nearCount = compCells.filter(c => c.rank !== null && c.rank >= 4 && c.rank <= 10).length
        if (top10Count > 0) {
          // Find top pack holders on this detached landmass
          const holders = new Map()
          for (const c of compCells) {
            const entry = qMap.get(c.id)
            if (!entry || entry.band === 'unknown') continue
            for (const item of entry.items) {
              if (item.rank > 3 || item.id === model.targetId) continue
              holders.set(item.id, (holders.get(item.id) || 0) + 1)
            }
          }
          const topRivals = [...holders.entries()]
            .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
            .slice(0, 2)
            .map(([id]) => businessById.get(id)?.name || id)
          avoid.push({
            id: `${q.id}:detached:${comp.id}`,
            kind: 'detached_landmass',
            componentId: comp.id,
            title: `Detached landmass ${comp.id}`,
            pins: comp.pins,
            top10Count,
            nearCount,
            attractiveCount: top10Count,
            originIds: comp.originIds,
            offsetMiles: comp.offsetMiles,
            topRivals,
            reason: `${comp.pins} pins, no dry-land lattice path to your base (${top10Count} rank 1 to 10 here).`,
          })
        }
      }
    }

    // 2. fortress: each fortress holder, with the pins it guards
    for (const [holderId, originIds] of fortressPinsByHolder.entries()) {
      const biz = businessById.get(holderId)
      const reviews = biz?.reviews ?? 0
      const rating = biz?.rating ?? null
      const pm = round2((pmById.get(holderId) || { pm: 0 }).pm)
      avoid.push({
        id: `${q.id}:fortress:${holderId}`,
        kind: 'fortress',
        holderId,
        holderCid: biz?.cid || null,
        title: `Fortress: ${biz?.name || holderId}`,
        holderName: biz?.name || holderId,
        rating,
        reviews,
        pm,
        lat: finite(biz?.lat) ? biz.lat : null,
        lng: finite(biz?.lng) ? biz.lng : null,
        pins: originIds.length,
        attractiveCount: originIds.length,
        originIds,
        reason: `${originIds.length} ${originIds.length === 1 ? 'pin' : 'pins'} guarded by ${biz?.name || holderId} (${finite(rating) ? rating.toFixed(1) : 'unrated'} stars, ${reviews.toLocaleString('en-US')} reviews) on its own block.`,
      })
    }

    // 3. out_of_reach: first ring where reachByQuery[q] < 0.10 and everything beyond it
    const firstOutRing = rawReachByQuery[q.id].findIndex(v => v < 0.10)
    if (firstOutRing >= 0) {
      const outOriginIds = homeComplete.filter(c => c.ring >= firstOutRing).map(c => c.id)
      const ringPct = Math.round((rawReachByQuery[q.id][firstOutRing] || 0) * 100)
      if (outOriginIds.length > 0) {
        avoid.push({
          id: `${q.id}:out_of_reach`,
          kind: 'out_of_reach',
          fromMiles: firstOutRing,
          reachPct: ringPct,
          title: `${q.name} past ${firstOutRing} mi`,
          pins: outOriginIds.length,
          attractiveCount: outOriginIds.length,
          originIds: outOriginIds,
          reason: `Top-ten reach drops to ${ringPct}% at ${firstOutRing} to ${firstOutRing + 1} mi (${outOriginIds.length} home pins beyond ${firstOutRing} mi).`,
        })
      }
    }

    // 4. not_your_blocker: profile with >= 20 first-place pins on this query where target is in top 30 at < 10% of them
    for (const [bizId, fpIds] of firstPlacePins.entries()) {
      if (fpIds.length < 20) continue
      const overlap30 = firstPlaceTargetTop30.get(bizId) || 0
      if (overlap30 / fpIds.length < 0.10) {
        const biz = businessById.get(bizId)
        avoid.push({
          id: `${q.id}:not_your_blocker:${bizId}`,
          kind: 'not_your_blocker',
          holderId: bizId,
          holderCid: biz?.cid || null,
          holderName: biz?.name || bizId,
          title: biz?.name || bizId,
          firstPlaces: fpIds.length,
          targetTop30Overlap: overlap30,
          pins: fpIds.length,
          attractiveCount: fpIds.length,
          originIds: fpIds,
          reason: `${fpIds.length} first places, you appear in the top 30 at ${overlap30} of them. Not your blocker.`,
        })
      }
    }

    const kindOrder = { detached_landmass: 0, fortress: 1, out_of_reach: 2, not_your_blocker: 3 }
    avoid.sort((a, b) => (kindOrder[a.kind] ?? 9) - (kindOrder[b.kind] ?? 9) || b.attractiveCount - a.attractiveCount || a.id.localeCompare(b.id))

    // Clean internal scratch fields on cells
    const cleanCells = cells.map(({ _hasWeakPackHolder, effectiveRank, ...rest }) => rest)

    const wValues = cleanCells.filter(c => finite(c.wRaw))
    const stats = {
      maxW: wValues.length ? Math.max(...wValues.map(c => c.w)) : 0,
      strikeCount: wValues.filter(c => c.wRaw >= 60).length,
      contestCount: wValues.filter(c => c.wRaw >= 40 && c.wRaw < 60).length,
      holdCount: cleanCells.filter(c => c.zone === 'hold').length,
      thinHoldCount: cleanCells.filter(c => c.zone === 'hold' && c.thin).length,
      fortressCount: cleanCells.filter(c => c.zone === 'fortress').length,
      detachedCount: cleanCells.filter(c => c.zone === 'detached').length,
      unknownCount: cleanCells.filter(c => c.zone === 'unknown').length,
      outOfReachFromMiles: firstOutRing >= 0 ? firstOutRing : null,
    }

    queriesOut[q.id] = {
      queryId: q.id,
      queryName: q.name,
      cells: cleanCells,
      cellById: new Map(cleanCells.map(c => [c.id, c])),
      plays,
      avoid,
      categoryShareTop3,
      categoryMismatch,
      stats,
    }
  }

  const result = {
    schema: CAMPAIGN_ENGINE_SCHEMA,
    available: true,
    weights: { ...CAMPAIGN_WEIGHTS },
    target: {
      id: targetBiz.id,
      cid: targetBiz.cid || null,
      name: targetBiz.name,
      pm: round2(targetPm),
      unrated: targetPmInfo.unrated,
      rating: targetBiz.rating ?? null,
      reviews: targetBiz.reviews ?? null,
      category: profileCategory,
      categoryConflict,
    },
    landmass: {
      landClipped: landmass.landClipped,
      home: { pins: landmass.home.pins, originIds: landmass.home.originIds },
      detached: landmass.detached,
    },
    reachByQuery,
    queries: queriesOut,
    limitations: LIMITATIONS,
  }

  engineCache.set(model, result)
  return result
}
