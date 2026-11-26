import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { HONEYCOMB_SHAPES, honeycombLayers, honeycombNest } from '../src/map-geometry.js'
import { normalizeStudy, edgeSignalNote, observationFor, businessMetrics, rankPresentation } from '../src/study-model.js'

// Written by the Python exporter from the test_hex_to_companion grid with study_radius 1.6 mi
// and one instrument-limited refine point (hex_-1_0).
const here = path.dirname(fileURLToPath(import.meta.url))
const fixture = () => JSON.parse(fs.readFileSync(path.join(here, 'helpers', 'hex-circle-study.json'), 'utf8'))

test('circle contract keeps the v6 honeycomb sizes', () => {
  assert.deepEqual([HONEYCOMB_SHAPES.marker.r, HONEYCOMB_SHAPES[1].r, HONEYCOMB_SHAPES[2].r, HONEYCOMB_SHAPES[3].r], [.24, .13, .075, .045])
})

test('a nested rung replaces only the estimates within half its own spacing', () => {
  const nodes = []
  for (let q = -2; q <= 2; q++) for (let r = -2; r <= 2; r++) {
    const a = 3 * q, b = 3 * r
    nodes.push({ a, b, x: a + b / 2, y: -Math.sqrt(3) / 2 * b, color: [0, 1, 0, .9], won: true, failed: false })
  }
  const plain = honeycombLayers(nodes)
  const counts = [plain.estimates[2].length, plain.estimates[3].length, plain.glow.glints]
  // A half-spacing refine point halfway between the business and its east neighbor.
  const hex = honeycombNest(honeycombLayers(nodes), [{ a: 1.5, b: 0, scale: .5 }])
  const gone = [...plain.estimates[2], ...plain.estimates[3]].filter(e => Math.hypot(e.e - .5, e.n) < .25)
  assert.ok(gone.length > 0)
  assert.equal(hex.estimates[2].length + hex.estimates[3].length, counts[0] + counts[1] - gone.length)
  for (const e of [...hex.estimates[2], ...hex.estimates[3]]) assert.ok(Math.hypot(e.e - .5, e.n) >= .25)
  assert.ok(hex.glow.glints < counts[2])
  assert.equal(hex.glow.glints, (hex.glow.marker?.tips.length || 0) +
    hex.glow.real.filter(g => g.x.a || g.x.b).reduce((s, g) => s + g.tips.length, 0) +
    hex.glow.estimates.reduce((s, g) => s + g.tips.length, 0))
  // No nested points: the honeycomb is untouched.
  assert.equal(honeycombNest(plain, []), plain)
})

test('points beyond the study radius are not in the study at all', () => {
  const model = normalizeStudy(fixture())
  assert.equal(model.geometry, 'hex_radius')
  assert.equal(model.reachPoints, undefined)
  assert.equal(model.points.length, 10)
  assert.ok(!model.points.some(p => ['hex_-2_-2', 'hex_2_2'].includes(p.id)))
  const m = businessMetrics(model, 'q1', model.targetId)
  // 7 coarse + 1 refine rank one-to-three inside the circle; the exporter dropped the two beyond-R points.
  assert.equal(m.found, 8)
  assert.equal(m.top3, 8)
})

test('edge signal is summary text only: grow the circle when the outer ring still wins', () => {
  const model = normalizeStudy(fixture())
  assert.equal(model.edgeSignal.q1.extends, true)
  assert.equal(model.edgeSignal.q1.top3, 6)
  const note = edgeSignalNote(model, 'q1')
  assert.match(note, /Territory likely extends past the study radius \(top 3 at 6 of 6 edge-ring locations\)/)
  assert.match(note, /Grow the circle: a new, larger full-circle study, run as an explicit paid step/)
  const quiet = { ...model, edgeSignal: { q1: { ...model.edgeSignal.q1, extends: false } } }
  assert.equal(edgeSignalNote(quiet, 'q1'), '')
  assert.equal(edgeSignalNote({ ...model, edgeSignal: null }, 'q1'), '')
})

test('instrument-limited points are a muted mark and never a loss', () => {
  const model = normalizeStudy(fixture())
  const limited = model.points.find(p => p.id === 'hex_-1_0')
  const o = observationFor(model, limited, 'q1', model.targetId)
  assert.equal(o.state, 'limited')
  assert.equal(o.rank, null)
  assert.equal(rankPresentation(model, limited, 'q1', model.targetId).kind, 'limited')
  const m = businessMetrics(model, 'q1', model.targetId)
  assert.equal(m.limited, 1)
  assert.equal(m.scored, 9)
  assert.ok(Math.abs(m.top3Pct - 8 / 9 * 100) < 1e-9)
  // A not-found point inside the box is still a real miss.
  const miss = observationFor(model, model.points.find(p => p.id === 'hex_0_1'), 'q1', model.targetId)
  assert.equal(miss.state, 'absent')
  // Lanes only count their own lattice: q2 measured 4 main points, all rank one.
  const q2 = businessMetrics(model, 'q2', model.targetId)
  assert.equal(q2.scored, 4)
  assert.equal(q2.top3, 4)
})
