// Cartographic identity coloring for Local Leaders:
// 1. Target business owns an exclusive signature crimson never shared by rivals.
// 2. Top 15 distinct competitor brands each get a globally unique high-contrast OKLab hue.
// 3. Next 12 distinct brands get unique secondary hues (28 unique brand slots before any reuse).
// 4. Multi-location franchises share one hue family with distinct branch tints (OKLab delta >= 0.16).
// 5. Any long-tail reuse past 28 brands avoids 1-hop/2-hop neighbors and maximizes map distance.
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
  return [
    .2104542553 * l + .793617785 * m - .0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + .4505937099 * s,
    .0259040371 * l + .7827717662 * m - .808675766 * s,
  ]
}

function oklabToHex(L, a, b) {
  const l_ = L + .3963377774 * a + .2158037573 * b
  const m_ = L - .1055613458 * a - .0638541728 * b
  const s_ = L - .0894841775 * a - 1.2914855480 * b
  const l = l_ * l_ * l_, m = m_ * m_ * m_, s = s_ * s_ * s_
  const lin = [
    +4.0767416621 * l - 3.3077115913 * m + .2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - .3413193965 * s,
    -.0041960863 * l - .7034186147 * m + 1.7076147010 * s,
  ]
  const toByte = c => {
    const clamped = Math.max(0, Math.min(1, c))
    const enc = clamped <= .0031308 ? 12.92 * clamped : 1.055 * (clamped ** (1 / 2.4)) - .055
    return Math.round(Math.max(0, Math.min(1, enc)) * 255).toString(16).padStart(2, '0')
  }
  return `#${toByte(lin[0])}${toByte(lin[1])}${toByte(lin[2])}`
}

function deriveSiblingHex(baseHex, branchIndex) {
  const [L, a, b] = perceptualColor(baseHex)
  // Shift lightness + subtle chroma while preserving hue angle so multi-location
  // branches visibly share one brand family yet stay > 0.16 OKLab apart.
  const presets = [
    [L > .78 ? -.20 : +.17, .74],
    [L > .78 ? -.34 : -.18, .86],
    [L > .78 ? -.12 : +.24, .56],
    [L > .78 ? -.28 : -.26, .68],
  ]
  const [dL, cScale] = presets[(branchIndex - 1) % presets.length]
  const nextL = Math.max(.34, Math.min(.94, L + dL))
  return oklabToHex(nextL, a * cScale, b * cScale)
}

const separation = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])

// Slot 0: Exclusive Target Signature Crimson (never assigned to unrelated rivals).
// Slots 1..15: 15 maximally separated dark-basemap hues for top competitor brands
// (deliberately excludes crimson/rose shades reserved for Target + its sibling branches).
// Slots 16..27: 12 distinct secondary hues so 28 distinct brands never repeat a color.
export const TARGET_SIGNATURE_COLOR = '#ff2e55'
const PRIMARY_RIVAL_PALETTE = [
  '#00e5ff', '#2be67b', '#9d7bff', '#ffd829', '#ff8a24',
  '#e040fb', '#3b8cff', '#e8eef7', '#a8e62e', '#14c9b2',
  '#d97742', '#6d7dff', '#57c7ff', '#c9a227', '#c084fc',
]
const SECONDARY_PALETTE = [
  '#7ee0a8', '#f7c96b', '#92b4ff', '#e3966d', '#64d6d4', '#cfe06c',
  '#b794f6', '#38d9a9', '#9ec5e0', '#b8a05c', '#6bc45e', '#88a8ff',
]
const PALETTE = [TARGET_SIGNATURE_COLOR, ...PRIMARY_RIVAL_PALETTE, ...SECONDARY_PALETTE]
const LABS = PALETTE.map(perceptualColor)

const GENERIC_TOKENS = new Set([
  'pizza', 'pizzeria', 'pizzaria', 'pies', 'pie', 'co', 'company',
  'new', 'york', 'ny', 'style', 'italian', 'greek', 'cuisine',
  'pastaria', 'pasta', 'salads', 'salad', 'and', 'the', 'of', 'at', 'on',
])

export function coreBrandKey(name) {
  if (!name || typeof name !== 'string') return ''
  let s = name.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
  // Strip branch/location suffixes after @, :, |, or spaced hyphen/dash
  s = s.replace(/\s*[@:|]\s*.+$/, '').replace(/\s+[-\u2013\u2014]\s+.+$/, '')
  // Normalize apostrophes, ampersands, punctuation
  s = s.replace(/['\u2018\u2019`]/g, '').replace(/&/g, ' and ').replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim()
  if (!s) return ''
  // Normalize "new york" before pizza/pizzeria ("Yaghi's New York Pizzeria" -> "yaghis pizzeria")
  s = s.replace(/\bnew york\b/g, ' ').replace(/\s+/g, ' ').trim()
  const tokens = s.split(' ').filter(Boolean)
  // Strip trailing generic category/menu words only when a distinctive brand stem remains
  let end = tokens.length
  while (end > 1 && GENERIC_TOKENS.has(tokens[end - 1])) end--
  const stem = tokens.slice(0, end)
  // Guard against over-collapsing single short/generic words like "dough" or "home"
  if (stem.length === 1 && (stem[0].length < 5 || stem[0] === 'dough' || stem[0] === 'home' || stem[0] === 'main')) {
    return tokens.slice(0, Math.min(2, tokens.length)).join(' ')
  }
  return stem.join(' ')
}

function resolveBrandKeys(ids, businessById) {
  const raw = new Map()
  for (const id of ids) {
    const name = businessById.get(id)?.name || id
    raw.set(id, coreBrandKey(name) || id)
  }
  // Secondary pass: if a shorter multi-word brand stem (e.g. "via 313") is a strict
  // word-boundary prefix of another winner's stem (e.g. "via 313 st elmos springdale"),
  // group them into the same brand family.
  const stems = [...new Set(raw.values())].sort((a, b) => a.length - b.length || a.localeCompare(b))
  const canonical = new Map()
  for (const stem of stems) {
    let parent = stem
    for (const candidate of stems) {
      if (candidate.length >= stem.length) break
      if (candidate.includes(' ') && candidate.length >= 6 && stem.startsWith(`${candidate} `)) {
        parent = candidate
        break
      }
    }
    canonical.set(stem, parent)
  }
  const byId = new Map()
  for (const id of ids) byId.set(id, canonical.get(raw.get(id)))
  return byId
}

export function leaderIdentity(model) {
  if (cache.has(model)) return cache.get(model)
  const queries = model.queries?.map(q => q.id) || Object.keys(model.points[0]?.observations || {})
  const businessById = new Map((model.businesses || []).map(b => [b.id, b]))
  const counts = new Map(), graph = new Map(), winners = new Map(), coordsById = new Map()

  // Sort points deterministically so spatial hashing is 100% input-order invariant.
  const sortedPoints = [...(model.points || [])].sort((a, b) => String(a.id).localeCompare(String(b.id)))
  for (const point of sortedPoints) {
    const ids = queries.map(q => winnerAt(point.observations?.[q])?.id)
    winners.set(point, ids)
    for (const id of ids) if (id) {
      counts.set(id, (counts.get(id) || 0) + 1)
      if (!graph.has(id)) graph.set(id, new Map())
      if (!coordsById.has(id)) coordsById.set(id, [])
      coordsById.get(id).push([point.lat, point.lng])
    }
  }

  // Spatial hashing in local kilometers (1-hop adjacency across grid cells).
  const step = model.sampling?.spacing_km
  if (step > 0 && sortedPoints.length) {
    const origin = sortedPoints[0], cos = Math.cos(origin.lat * Math.PI / 180), buckets = new Map()
    for (const point of sortedPoints) {
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
  const brandById = resolveBrandKeys(ids, businessById)

  // Group business IDs into brand families (e.g. multi-location franchises).
  const brandMembers = new Map(), brandWins = new Map(), brandPoints = new Map()
  for (const id of ids) {
    const b = brandById.get(id)
    if (!brandMembers.has(b)) {
      brandMembers.set(b, [])
      brandWins.set(b, 0)
      brandPoints.set(b, [])
    }
    brandMembers.get(b).push(id)
    brandWins.set(b, brandWins.get(b) + counts.get(id))
    for (const pt of coordsById.get(id) || []) brandPoints.get(b).push(pt)
  }

  // Brand-level 1-hop and 2-hop adjacency graphs.
  const brandGraph = new Map([...brandMembers.keys()].map(b => [b, new Map()]))
  for (const [id, nbrs] of graph) {
    const ba = brandById.get(id)
    for (const [nid, w] of nbrs) {
      const bb = brandById.get(nid)
      if (ba === bb) continue
      brandGraph.get(ba).set(bb, (brandGraph.get(ba).get(bb) || 0) + w)
    }
  }
  const brandTwoHop = new Map()
  for (const [ba, nbrs] of brandGraph) {
    const hop2 = new Set()
    for (const mid of nbrs.keys()) {
      for (const far of brandGraph.get(mid).keys()) {
        if (far !== ba && !nbrs.has(far)) hop2.add(far)
      }
    }
    brandTwoHop.set(ba, hop2)
  }

  // Approximate centroid per brand (for physical distance repulsion on long-tail reuse).
  const brandCentroid = new Map()
  for (const [b, pts] of brandPoints) {
    if (!pts.length) continue
    const lat = pts.reduce((s, p) => s + p[0], 0) / pts.length
    const lng = pts.reduce((s, p) => s + p[1], 0) / pts.length
    brandCentroid.set(b, [lat, lng])
  }
  const cosLat = sortedPoints.length ? Math.cos(sortedPoints[0].lat * Math.PI / 180) : 1
  const approxDistKm = (ba, bb) => {
    const ca = brandCentroid.get(ba), cb = brandCentroid.get(bb)
    if (!ca || !cb) return 10
    return Math.hypot((ca[1] - cb[1]) * 111.195 * cosLat, (ca[0] - cb[0]) * 111.195)
  }

  const targetBrand = model.targetId && brandById.has(model.targetId) ? brandById.get(model.targetId) : null
  const orderedBrands = [...brandMembers.keys()].sort((a, b) =>
    brandWins.get(b) - brandWins.get(a) || a.localeCompare(b))
  const nonTargetBrands = orderedBrands.filter(b => b !== targetBrand)

  const brandSlot = new Map()
  const slotBrands = Array.from({ length: PALETTE.length }, () => [])

  const commitSlot = (brand, slot) => {
    brandSlot.set(brand, slot)
    slotBrands[slot].push(brand)
  }

  // Tier 0: Target brand exclusively owns Slot 0 (Signature Crimson).
  if (targetBrand) commitSlot(targetBrand, 0)

  const scoreSlot = (brand, slot, allowReuse) => {
    const lab = LABS[slot]
    const n1 = [...brandGraph.get(brand)].filter(([n]) => brandSlot.has(n))
    const n2 = [...brandTwoHop.get(brand)].filter(n => brandSlot.has(n))

    let min1 = .55, avg1 = .55, exact1 = 0
    if (n1.length) {
      let sumW = 0, sumD = 0
      min1 = Infinity
      for (const [n, w] of n1) {
        const ns = brandSlot.get(n)
        if (ns === slot) exact1++
        const d = separation(lab, LABS[ns])
        if (d < min1) min1 = d
        sumD += d * w
        sumW += w
      }
      avg1 = sumD / (sumW || 1)
    }

    let min2 = .50, exact2 = 0
    if (n2.length) {
      min2 = Infinity
      for (const n of n2) {
        const ns = brandSlot.get(n)
        if (ns === slot) exact2++
        const d = separation(lab, LABS[ns])
        if (d < min2) min2 = d
      }
    }

    let score = min1 * 22 + min2 * 6 + avg1 * 2.5
    if (exact1 > 0) score -= 1000 * exact1
    if (exact2 > 0) score -= 120 * exact2
    // Keep multi-branch franchises on saturated chromatic hues so sibling tints stay vivid (never grey).
    if ((brandMembers.get(brand)?.length || 1) > 1 && Math.hypot(lab[1], lab[2]) < .05) {
      score -= 8
    }

    if (allowReuse && slotBrands[slot].length > 0) {
      let minPhysKm = Infinity
      for (const other of slotBrands[slot]) {
        const km = approxDistKm(brand, other)
        if (km < minPhysKm) minPhysKm = km
      }
      score += Math.min(15, minPhysKm) * .45 - slotBrands[slot].length * 1.4
    }
    return score
  }

  const assignTier = (tierBrands, candidateSlots, allowReuse) => {
    const pending = new Set(tierBrands)
    while (pending.size) {
      const next = [...pending].sort((a, b) => {
        const sat = key => new Set([...brandGraph.get(key).keys()].map(n => brandSlot.get(n)).filter(s => s !== undefined)).size
        return sat(b) - sat(a) || brandGraph.get(b).size - brandGraph.get(a).size ||
          brandWins.get(b) - brandWins.get(a) || a.localeCompare(b)
      })[0]
      let chosen = candidateSlots[0], best = -Infinity
      for (const slot of candidateSlots) {
        if (!allowReuse && slotBrands[slot].length > 0) continue
        const s = scoreSlot(next, slot, allowReuse)
        if (s > best) { best = s; chosen = slot }
      }
      commitSlot(next, chosen)
      pending.delete(next)
    }
  }

  // Tier 1: Top 15 non-target brands each get a globally UNIQUE primary slot (1..15).
  const primarySlots = Array.from({ length: PRIMARY_RIVAL_PALETTE.length }, (_, i) => i + 1)
  const secondarySlots = Array.from({ length: SECONDARY_PALETTE.length }, (_, i) => i + 1 + PRIMARY_RIVAL_PALETTE.length)
  const allRivalSlots = [...primarySlots, ...secondarySlots]

  const tier1 = nonTargetBrands.slice(0, primarySlots.length)
  const tier2 = nonTargetBrands.slice(primarySlots.length, primarySlots.length + secondarySlots.length)
  const tier3 = nonTargetBrands.slice(primarySlots.length + secondarySlots.length)

  assignTier(tier1, primarySlots, false)
  assignTier(tier2, secondarySlots, false)
  if (tier3.length) assignTier(tier3, allRivalSlots, true)

  // Resolve per-location color: primary branch gets exact base color; sibling branches
  // of the same brand get hue-family shifts (OKLab delta >= 0.16 from primary).
  const colorById = new Map()
  const branchInfoById = new Map()
  for (const [brand, members] of brandMembers) {
    const baseHex = PALETTE[brandSlot.get(brand)]
    const orderedMembers = [...members].sort((a, b) => {
      if (a === model.targetId) return -1
      if (b === model.targetId) return 1
      return counts.get(b) - counts.get(a) || a.localeCompare(b)
    })
    orderedMembers.forEach((id, idx) => {
      colorById.set(id, idx === 0 ? baseHex : deriveSiblingHex(baseHex, idx))
      branchInfoById.set(id, { brandKey: brand, branchCount: orderedMembers.length, branchIndex: idx })
    })
  }

  const identities = new Map(ids.map((id, index) => [id, {
    color: colorById.get(id),
    badge: `L${String(index + 1).padStart(2, '0')}`,
    ...branchInfoById.get(id),
  }]))
  const result = { identities, graph }
  cache.set(model, result)
  return result
}
