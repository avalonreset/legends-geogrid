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

test('basemap switcher load deadlines use the visibility-aware timer', () => {
  const source = readFileSync(new URL('../src/basemap-switcher.js', import.meta.url), 'utf8')
  assert.match(source, /visibleTimeout\(25000/)
  assert.match(source, /visibleTimeout\(20000/)
  assert.doesNotMatch(source, /setTimeout\(\(\) => reject\(new Error\('Map loading timed out/)
})
