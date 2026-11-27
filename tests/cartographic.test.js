import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  CARTOGRAPHIC, dominanceScore, dominanceTierForScore, reliefThresholdsAtTau,
  attenuateScoreAtTau, innerShapeburstStrokes, cubicBezierEase, masterTierForRank,
} from '../src/cartographic.js'

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
