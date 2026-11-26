import test from 'node:test'
import assert from 'node:assert/strict'
import { HONEYCOMB_SHAPES, honeycombLayer, honeycombRotation, honeycombTips, honeycombAim, honeycombVertices, honeycombLayers } from '../src/map-geometry.js'

test('honeycomb sizes follow the locked sharp 6-star -> hex -> triangle ladder', () => {
  assert.equal(HONEYCOMB_SHAPES.marker.r, .24)
  assert.equal(HONEYCOMB_SHAPES[1].r, .13)
  assert.equal(HONEYCOMB_SHAPES[2].r, .075)
  assert.equal(HONEYCOMB_SHAPES[3].r, .045)
  assert.deepEqual([HONEYCOMB_SHAPES.marker.n, HONEYCOMB_SHAPES[1].n, HONEYCOMB_SHAPES[2].n, HONEYCOMB_SHAPES[3].n], [6, 6, 6, 3])
  // Sharp tactical 6-point star: deep inner valleys (.36) and rot 0 so all 6 tips point at the 6 surrounding hexagons.
  assert.equal(HONEYCOMB_SHAPES.marker.inner, .36)
  assert.equal(HONEYCOMB_SHAPES.marker.rot, 0)
})

test('every corner points at the right neighbor layer', () => {
  for (let a = -6; a <= 6; a++) for (let b = -6; b <= 6; b++) {
    const layer = honeycombLayer(a, b)
    for (const angle of honeycombTips(a, b, layer)) {
      const [u, v] = honeycombAim(angle)
      const target = honeycombLayer(a + u, b + v)
      // Real hexagon corners (30, 90, ...) face layer 2; layer 2 corners face layer 3;
      // layer 3 corners face their parents (real or layer 2).
      if (layer === 1) assert.equal(target, 2)
      else if (layer === 2) assert.equal(target, 3)
      else assert.notEqual(target, 3)
      const x = u + v / 2, y = v * Math.sqrt(3) / 2
      const got = Math.atan2(y, x) * 180 / Math.PI
      assert.ok(Math.abs((((got - angle) % 360) + 540) % 360 - 180) < 1e-6)
    }
  }
  assert.equal(honeycombRotation(1, 0, 3), 60)
  assert.equal(honeycombRotation(0, 1, 3), 0)
})

test('real data is a pointy-top hexagon with its corners at 30 degrees', () => {
  const v = honeycombVertices(0, 0, 1, 1, HONEYCOMB_SHAPES[1].rot)
  assert.equal(v.length, 12)
  const radii = v.map(([x, y]) => Math.hypot(x, y))
  assert.ok(Math.abs(radii[0] - 1) < 1e-9 && Math.abs(radii[1] - Math.cos(Math.PI / 6)) < 1e-9)
  assert.ok(Math.abs(v[0][0] - Math.cos(Math.PI / 6)) < 1e-9)
})

test('business marker is a sharp 6-pointed star aiming straight at the 6 surrounding hexagons', () => {
  const v = honeycombVertices(0, 0, 1, 'marker', HONEYCOMB_SHAPES.marker.rot)
  assert.equal(v.length, 12)
  // First outer tip (index 0 -> 0 deg) points straight east (1, 0) toward the east hexagon neighbor.
  assert.ok(Math.abs(v[0][0] - 1) < 1e-9 && Math.abs(v[0][1]) < 1e-9)
  // All 6 outer tips sit at 0, 60, 120, 180, 240, 300 deg (matching the 6 neighbor hexagon axes)
  // and all 6 inner valleys sit tightly at radius 0.36.
  for (let k = 0; k < 6; k++) {
    const outer = v[2 * k], inner = v[2 * k + 1]
    assert.ok(Math.abs(Math.hypot(outer[0], outer[1]) - 1) < 1e-9)
    assert.ok(Math.abs(Math.hypot(inner[0], inner[1]) - .36) < 1e-9)
  }
})

test('estimates blend measured colors, keep the first ring around the marker and never invent data', () => {
  const nodes = []
  for (let q = -2; q <= 2; q++) for (let r = -2; r <= 2; r++) {
    const a = 3 * q, b = 3 * r
    nodes.push({ a, b, x: a + b / 2, y: -Math.sqrt(3) / 2 * b, color: [0, 1, 0, .9], won: true, failed: false })
  }
  const hex = honeycombLayers(nodes)
  assert.ok(Math.abs(hex.spacing - 3) < 1e-9)
  assert.ok(hex.estimates[2].length > 0 && hex.estimates[3].length > 0)
  for (const e of [...hex.estimates[2], ...hex.estimates[3]]) {
    assert.ok(e.color[3] <= .9 + 1e-9)
    assert.equal(e.rank, undefined)
  }
  assert.equal(hex.glow.marker.tips.length, 6)
  // v6: the first layer-3 ring (S/3 from the business) is drawn, clear of the star.
  const ring = hex.estimates[3].filter(e => Math.abs(Math.hypot(e.e, e.n) - 1 / 3) < 1e-9)
  assert.equal(ring.length, 6)
  assert.ok(HONEYCOMB_SHAPES.marker.r + HONEYCOMB_SHAPES[3].r < 1 / 3)
  for (const layer of [1, 2, 3]) assert.ok(HONEYCOMB_SHAPES.marker.r > HONEYCOMB_SHAPES[layer].r)
})
