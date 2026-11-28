import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { visibleTimeout } from '../src/visible-timeout.js'

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

function fakeDocument(hidden) {
  const listeners = new Set()
  return {
    hidden,
    addEventListener: (type, fn) => { if (type === 'visibilitychange') listeners.add(fn) },
    removeEventListener: (type, fn) => { if (type === 'visibilitychange') listeners.delete(fn) },
    setHidden(value) { this.hidden = value; for (const fn of [...listeners]) fn() },
    get listenerCount() { return listeners.size },
  }
}

test('visible timeout fires after the deadline on a visible page', async () => {
  const doc = fakeDocument(false)
  let fired = 0
  visibleTimeout(30, () => { fired += 1 }, doc)
  await sleep(80)
  assert.equal(fired, 1)
  assert.equal(doc.listenerCount, 0)
})

test('a background tab does not burn the basemap load deadline', async () => {
  const doc = fakeDocument(true)
  let fired = 0
  visibleTimeout(40, () => { fired += 1 }, doc)
  await sleep(120)
  assert.equal(fired, 0, 'hidden time must not count toward the deadline')
  doc.setHidden(false)
  await sleep(10)
  assert.equal(fired, 0)
  await sleep(90)
  assert.equal(fired, 1)
})

test('hiding the tab pauses the remaining time and stop cancels cleanly', async () => {
  const doc = fakeDocument(false)
  let fired = 0
  const stop = visibleTimeout(60, () => { fired += 1 }, doc)
  await sleep(20)
  doc.setHidden(true)
  await sleep(120)
  assert.equal(fired, 0)
  stop()
  doc.setHidden(false)
  await sleep(120)
  assert.equal(fired, 0)
  assert.equal(doc.listenerCount, 0)
})

test('zero, negative and NaN deadlines fire promptly without leaking listeners', async () => {
  for (const ms of [0, -50, NaN]) {
    const doc = fakeDocument(false)
    let fired = 0
    visibleTimeout(ms, () => { fired += 1 }, doc)
    await sleep(30)
    assert.equal(fired, 1, `ms=${String(ms)}`)
    assert.equal(doc.listenerCount, 0)
  }
})

test('Infinity and over-range deadlines are clamped, not passed raw to setTimeout', async () => {
  for (const ms of [Infinity, 0x7fffffff + 5000]) {
    const doc = fakeDocument(false)
    let fired = 0
    const stop = visibleTimeout(ms, () => { fired += 1 }, doc)
    await sleep(40)
    assert.equal(fired, 0, `ms=${String(ms)} must not fire immediately`)
    stop()
    assert.equal(doc.listenerCount, 0)
    await sleep(20)
    assert.equal(fired, 0)
  }
})

test('repeated hidden and visible events do not burn or double-count the deadline', t => {
  // Mocked clock: real 5 ms sleeps round up to about 15.6 ms on Windows runners,
  // which made the visible-time budget depend on OS timer granularity.
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'] })
  const realPerformance = Object.getOwnPropertyDescriptor(globalThis, 'performance')
  Object.defineProperty(globalThis, 'performance', { configurable: true, writable: true, value: { now: () => Date.now() } })
  t.after(() => {
    if (realPerformance) Object.defineProperty(globalThis, 'performance', realPerformance)
    else delete globalThis.performance
  })
  const doc = fakeDocument(false)
  let fired = 0
  visibleTimeout(50, () => { fired += 1 }, doc)
  for (let i = 0; i < 5; i += 1) {
    doc.setHidden(true)
    doc.setHidden(true)
    t.mock.timers.tick(15)
    doc.setHidden(false)
    doc.setHidden(false)
    t.mock.timers.tick(5)
  }
  assert.equal(fired, 0, 'only 25ms of visible time has elapsed')
  t.mock.timers.tick(24)
  assert.equal(fired, 0, '49ms of visible time is still inside the 50ms deadline')
  t.mock.timers.tick(1)
  assert.equal(fired, 1)
  t.mock.timers.tick(200)
  assert.equal(fired, 1, 'fires exactly once')
  assert.equal(doc.listenerCount, 0)
})

test('stop while hidden on start prevents firing when the page becomes visible', async () => {
  const doc = fakeDocument(true)
  let fired = 0
  const stop = visibleTimeout(20, () => { fired += 1 }, doc)
  stop()
  assert.equal(doc.listenerCount, 0)
  doc.setHidden(false)
  await sleep(60)
  assert.equal(fired, 0)
})

test('basemap switcher load deadlines use the visibility-aware timer', () => {
  const source = readFileSync(new URL('../src/basemap-switcher.js', import.meta.url), 'utf8')
  assert.match(source, /visibleTimeout\(25000/)
  assert.match(source, /visibleTimeout\(20000/)
  assert.doesNotMatch(source, /setTimeout\(\(\) => reject\(new Error\('Map loading timed out/)
})
