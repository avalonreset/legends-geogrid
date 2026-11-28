import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  CARTOGRAPHIC, dominanceScore, dominanceTierForScore, reliefThresholdsAtTau,
  attenuateScoreAtTau, innerShapeburstStrokes, cubicBezierEase, masterTierForRank,
  dominanceTierAtAllowed, rankAtPointAllowed,
} from '../src/cartographic.js'
import { pointInRings } from '../src/map-geometry.js'

test('locked cartographic constants', () => {
  assert.equal(CARTOGRAPHIC.innerWidth, 48)
  assert.equal(CARTOGRAPHIC.innerOpacity, 0.16)
  assert.equal(CARTOGRAPHIC.borderScale, 0.45)
  assert.equal(CARTOGRAPHIC.hoverDurationMs, 200)
  assert.equal(CARTOGRAPHIC.hoverFadeMs, 200)
  assert.equal(CARTOGRAPHIC.contours, 'all')
  assert.equal(CARTOGRAPHIC.focusTopoBackgroundDim, 0.04)
})

test('dominance score and tier lookup', () => {
  assert.equal(dominanceScore(1, 1), 10)
  assert.equal(dominanceScore(0, 0), 1)
  assert.equal(dominanceTierForScore(7.8).name, 'Fortress Core')
  assert.equal(dominanceTierForScore(6.2).name, 'Stronghold')
  assert.equal(dominanceTierForScore(4.2).name, 'Solid Interior')
  assert.equal(dominanceTierForScore(4.19).name, 'Contested Edge')
  assert.match(dominanceTierForScore(9).label, /Fortress Core/)
})

test('tau-coupled relief thresholds rise and edge scores attenuate', () => {
  const base = reliefThresholdsAtTau(0)
  const raised = reliefThresholdsAtTau(1)
  assert.deepEqual(base, [4.2, 6.2, 7.8])
  raised.forEach((v, i) => assert.ok(v > base[i]))
  assert.equal(attenuateScoreAtTau(8, 1, 1), 8)
  assert.ok(attenuateScoreAtTau(8, 0, 1) < 8)
  assert.ok(attenuateScoreAtTau(8, 0, 0.5) > attenuateScoreAtTau(8, 0, 1))
})

test('inner shapeburst strokes are Porter-Duff incremental and widest first', () => {
  const strokes = innerShapeburstStrokes(32, 0.34)
  assert.ok(strokes.length >= 8 && strokes.length <= 18)
  assert.ok(strokes[0].lineWidth > strokes.at(-1).lineWidth)
  let cum = 0
  for (const s of strokes) {
    assert.ok(s.alpha > 0 && s.alpha <= 1)
    cum = cum + s.alpha * (1 - cum)
  }
  assert.ok(cum <= 0.34 + 1e-9)
  assert.ok(cum > 0.1)
})

test('cubic bezier hover easing endpoints and monotonicity', () => {
  assert.equal(cubicBezierEase(0), 0)
  assert.equal(cubicBezierEase(1), 1)
  let prev = -1
  for (let i = 0; i <= 10; i++) {
    const v = cubicBezierEase(i / 10)
    assert.ok(v >= prev && v >= 0 && v <= 1)
    prev = v
  }
})

test('rank master tiers cover 1..30 without flicker boundaries', () => {
  assert.equal(masterTierForRank(1).id, 'summit')
  assert.equal(masterTierForRank(3).id, 'pack')
  assert.equal(masterTierForRank(10).id, 'page1')
  assert.equal(masterTierForRank(20).id, 'page2')
  assert.equal(masterTierForRank(30).id, 'page3')
  assert.equal(masterTierForRank(31), null)
})

test('shapeburst steps clamp rejects Infinity and caps finite counts at 64', () => {
  const fallback = innerShapeburstStrokes(48, 0.16, Infinity)
  assert.ok(fallback.length >= 1 && fallback.length <= 18)
  const nanSteps = innerShapeburstStrokes(48, 0.16, Number.NaN)
  assert.ok(nanSteps.length >= 1 && nanSteps.length <= 18)
  const capped = innerShapeburstStrokes(48, 0.16, 1000)
  assert.ok(capped.length <= 64)
  assert.ok(capped.every(s => Number.isFinite(s.lineWidth) && Number.isFinite(s.alpha)))
  assert.deepEqual(innerShapeburstStrokes(48, 0.16, -5), [])
})

test('dominance tier guard earns a tier only inside territory on land undraped', () => {
  const p = { x: 1, y: 2 }
  assert.equal(dominanceTierAtAllowed({ point: p, insideTerritory: true }), true)
  assert.equal(dominanceTierAtAllowed({ point: p, hasLandMask: false, insideLand: false, insideTerritory: true }), true)
  assert.equal(dominanceTierAtAllowed({ point: null, insideTerritory: true }), false)
  assert.equal(dominanceTierAtAllowed({ point: p, draped: true, insideTerritory: true }), false)
  assert.equal(dominanceTierAtAllowed({ point: p, hasLandMask: true, insideLand: false, insideTerritory: true }), false)
  assert.equal(dominanceTierAtAllowed({ point: p, insideTerritory: false }), false)
  assert.equal(dominanceTierAtAllowed(), false)
})

test('rank guard returns no rank over clipped water or outside the study circle', () => {
  const p = { x: 1, y: 2 }
  assert.equal(rankAtPointAllowed({ point: p }), true)
  assert.equal(rankAtPointAllowed({ point: null }), false)
  assert.equal(rankAtPointAllowed({ point: p, hasLandMask: true, insideLand: false }), false)
  assert.equal(rankAtPointAllowed({ point: p, clipTerritories: true, hasBoundary: true, insideBoundary: false }), false)
  assert.equal(rankAtPointAllowed({ point: p, clipTerritories: true, hasBoundary: true, insideBoundary: true }), true)
  assert.equal(rankAtPointAllowed({ point: p, clipTerritories: false, hasBoundary: true, insideBoundary: false }), true)
  assert.equal(rankAtPointAllowed({ point: p, clipTerritories: true, hasBoundary: false, insideBoundary: false }), true)
})

test('rank canvas wires clip guards before contour and relief lookups', () => {
  const src = readFileSync(new URL('../src/rank-canvas.js', import.meta.url), 'utf8')
  const rankStart = src.indexOf('rankAtPoint(containerPoint')
  const rankSlice = src.slice(rankStart, rankStart + 1600)
  assert.ok(rankStart >= 0)
  assert.ok(rankSlice.indexOf('rankAtPointAllowed(') >= 0)
  assert.ok(rankSlice.indexOf('rankAtPointAllowed(') < rankSlice.indexOf('for (const level of sorted)'))
  assert.match(rankSlice, /landMaskProjected\.some/)
  assert.match(rankSlice, /pointInRings\(\[this\.blendBoundary\]/)
  const tierStart = src.indexOf('dominanceTierAt(containerPoint')
  const tierSlice = src.slice(tierStart, tierStart + 1600)
  assert.ok(tierStart >= 0)
  assert.ok(tierSlice.indexOf('containerToZoom0') < tierSlice.indexOf('leaderRelief.get'))
  assert.match(tierSlice, /dominanceTierAtAllowed\(/)
  assert.match(tierSlice, /t\.flat \|\|= /)
  assert.match(tierSlice, /focus\?\.elevation\?\.levels\?\.length/)
  assert.match(src, /this\.hoverId = '__relief__'/)
  assert.match(src, /this\.hoverWasTopo = true/)
  assert.match(src, /CARTOGRAPHIC\.contours === 'all'/)
  const tipStart = src.indexOf('showTooltip(cell, containerPoint')
  const tipSlice = src.slice(tipStart, tipStart + 500)
  assert.match(tipSlice, /!this\.focus\?\.elevation\?\.levels\?\.length/)
})

test('release 0.3.2 version strings stay in parity', () => {
  const citation = readFileSync(new URL('../CITATION.cff', import.meta.url), 'utf8')
  assert.match(citation, /^version: "0\.3\.2"\r?$/m)
  assert.match(citation, /^date-released: "2026-11-27"\r?$/m)
  const review = readFileSync(new URL('../tools/business_name_review.py', import.meta.url), 'utf8')
  assert.ok(!review.includes('legends-geogrid/0.3.1'))
  assert.ok(review.includes('legends-geogrid/0.3.2'))
  const topo = readFileSync(new URL('../tools/report_hex_topo.py', import.meta.url), 'utf8')
  assert.ok(!topo.includes('v0.3.1'))
  assert.ok(topo.includes('v0.3.2'))
})

test('dominance tier guard returns no tier outside the clipped study circle', () => {
  const p = { x: 1, y: 2 }
  assert.equal(dominanceTierAtAllowed({ point: p, insideTerritory: true, clipTerritories: true, hasBoundary: true, insideBoundary: false }), false)
  assert.equal(dominanceTierAtAllowed({ point: p, insideTerritory: true, clipTerritories: true, hasBoundary: true, insideBoundary: true }), true)
  assert.equal(dominanceTierAtAllowed({ point: p, insideTerritory: true, clipTerritories: false, hasBoundary: true, insideBoundary: false }), true)
  assert.equal(dominanceTierAtAllowed({ point: p, insideTerritory: true, clipTerritories: true, hasBoundary: false, insideBoundary: false }), true)
})

test('rank canvas wires study-circle clips into territory and dominance lookups', () => {
  const src = readFileSync(new URL('../src/rank-canvas.js', import.meta.url), 'utf8')
  const terrStart = src.indexOf('territoryAt({ x, y })')
  const terrSlice = src.slice(terrStart, terrStart + 700)
  assert.ok(terrStart >= 0)
  assert.match(terrSlice, /landMaskProjected\?\.length/)
  assert.match(terrSlice, /this\.clipTerritories && this\.blendBoundary\?\.length && !pointInRings\(\[this\.blendBoundary\], px, py\)/)
  const tierStart = src.indexOf('dominanceTierAt(containerPoint')
  const tierSlice = src.slice(tierStart, tierStart + 1600)
  assert.ok(tierStart >= 0)
  assert.match(tierSlice, /clipTerritories: Boolean\(this\.clipTerritories\), hasBoundary, insideBoundary/)
  assert.match(tierSlice, /pointInRings\(\[this\.blendBoundary\], p\.x, p\.y\)/)
  const tipStart = src.indexOf('showTooltip(cell, containerPoint')
  const tipSlice = src.slice(tipStart, tipStart + 500)
  assert.match(tipSlice, /this\.dominanceTierAt\(containerPoint, cell\.leaderId\)/)
})

test('tectonic hover prefers clip-guarded territory over nearCellAt with no phantom water hover', () => {
  const src = readFileSync(new URL('../src/rank-canvas.js', import.meta.url), 'utf8')
  assert.match(src, /const hasTectonic = Boolean\(this\.territories\?\.some\(t => t\.tectonic\)\)/)
  assert.match(src, /const terrLeader = \(!seam && !cursorRank && !this\.focus\?\.elevation\?\.levels\?\.length\)/)
  assert.match(src, /hit\?\.leaderId \|\| terrLeader \|\| null/)
  assert.match(src, /if \(!hit && terrLeader && this\.leaderRelief\)/)
  assert.match(src, /style\.cursor = hit \|\| nextLeader \? 'pointer' : ''/)
  assert.ok(!src.includes('allowedHit'))
  assert.ok(!src.includes('pointIsAllowed'))
  assert.ok(!src.includes('const nextLeader = seam ? null : near?.leaderId || terrLeader || null'))
  const nearStart = src.indexOf('nearCellAt({ x, y })')
  const nearSlice = src.slice(nearStart, nearStart + 700)
  assert.ok(nearStart >= 0)
  assert.match(nearSlice, /landMaskProjected\?\.length/)
  assert.match(nearSlice, /this\.clipTerritories && this\.blendBoundary\?\.length/)
})

test('pointAllowedAt gates every hitAt call and seamAt carries land and circle guards', () => {
  const src = readFileSync(new URL('../src/rank-canvas.js', import.meta.url), 'utf8')
  assert.match(src, /pointAllowedAt\(containerPoint\) \{/)
  const gated = src.match(/this\.pointAllowedAt\(event\.containerPoint\) \? this\.hitAt\(event\.containerPoint\) : null/g) || []
  assert.equal(gated.length, 3)
  assert.ok(!src.includes('const hit = this.hitAt(event.containerPoint)'))
  const seamStart = src.indexOf('seamAt({ x, y })')
  const seamSlice = src.slice(seamStart, seamStart + 700)
  assert.ok(seamStart >= 0)
  assert.match(seamSlice, /this\.landMaskProjected\?\.length && !this\.landMaskProjected\.some\(rings => pointInRings\(rings, px, py\)\)\) return null/)
  assert.match(seamSlice, /this\.clipTerritories && this\.blendBoundary\?\.length && !pointInRings\(\[this\.blendBoundary\], px, py\)\) return null/)
  assert.ok(seamSlice.indexOf('pointInRings(rings, px, py)') < seamSlice.indexOf('const limit'))
})

// Extract a shipped method body by brace balance so the runtime checks below
// execute the exact source text (Leaflet keeps the module unimportable in Node).
function extractMethod(src, marker) {
  const start = src.indexOf(marker)
  assert.ok(start >= 0, marker)
  const open = src.indexOf('{', src.indexOf(')', start))
  let depth = 0
  for (let i = open; i < src.length; i++) {
    if (src[i] === '{') depth++
    else if (src[i] === '}' && --depth === 0) return src.slice(start, i + 1)
  }
  assert.fail(`unterminated ${marker}`)
}

test('runtime pointAllowedAt and seamAt suppress clipped water and outside-circle points', () => {
  const src = readFileSync(new URL('../src/rank-canvas.js', import.meta.url), 'utf8')
  const allowedObj = new Function('pointInRings', `return { ${extractMethod(src, 'pointAllowedAt(containerPoint)')} }`)(pointInRings)
  const seamObj = new Function('pointInRings', `return { ${extractMethod(src, 'seamAt({ x, y })')} }`)(pointInRings)
  const square = (lo, hi) => [{ x: lo, y: lo }, { x: hi, y: lo }, { x: hi, y: hi }, { x: lo, y: hi }]
  const layer = {
    containerToZoom0: p => p,
    landMaskProjected: [[square(0, 100)]],
    clipTerritories: true,
    blendBoundary: square(10, 50),
  }
  const allowed = p => allowedObj.pointAllowedAt.call(layer, p)
  assert.equal(allowed({ x: 30, y: 30 }), true)
  assert.equal(allowed({ x: 150, y: 30 }), false)
  assert.equal(allowed({ x: 80, y: 30 }), false)
  layer.clipTerritories = false
  assert.equal(allowed({ x: 80, y: 30 }), true)
  assert.equal(allowed({ x: 150, y: 30 }), false)
  layer.landMaskProjected = null
  layer.clipTerritories = true
  assert.equal(allowed({ x: 80, y: 30 }), false)
  assert.equal(allowedObj.pointAllowedAt.call({ ...layer, containerToZoom0: () => null }, { x: 1, y: 1 }), true)

  const seam = { p1: { x: 0, y: 20 }, p2: { x: 200, y: 20 } }
  const seamLayer = {
    _map: {},
    seams: [seam],
    stepPx: 100,
    screenFrame: () => ({ scale: 1, origin: { x: 0, y: 0 } }),
    landMaskProjected: [[square(0, 100)]],
    clipTerritories: true,
    blendBoundary: square(10, 50),
  }
  const seamAtPt = p => seamObj.seamAt.call(seamLayer, p)
  assert.equal(seamAtPt({ x: 30, y: 20 }), seam)
  assert.equal(seamAtPt({ x: 150, y: 20 }), null)
  assert.equal(seamAtPt({ x: 80, y: 20 }), null)
  seamLayer.clipTerritories = false
  assert.equal(seamAtPt({ x: 80, y: 20 }), seam)
  assert.equal(seamAtPt({ x: 150, y: 20 }), null)
})
