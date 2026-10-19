import { test } from 'node:test'
import assert from 'node:assert/strict'
import { Readable } from 'node:stream'
import { mapPreviewPlugin } from '../tools/map-preview-plugin.mjs'

test('Google preview rejects cross-origin, invalid and automatic requests without provider calls', async () => {
  let handle, calls = 0
  mapPreviewPlugin().configureServer({ middlewares: { use(fn) { handle = fn } } })
  const key = process.env.GOOGLE_MAPS_API_KEY, originalFetch = globalThis.fetch
  process.env.GOOGLE_MAPS_API_KEY = 'test-only-key'
  globalThis.fetch = async () => { calls++; return new Response(new Uint8Array([1, 2, 3]), { headers: { 'Content-Type': 'image/png' } }) }
  async function request({ method = 'POST', origin = 'http://localhost:5186', body = {}, url = '/api/maps/google-preview' } = {}) {
    const req = Readable.from([JSON.stringify(body)])
    Object.assign(req, { method, url, headers: { host: 'localhost:5186', origin } })
    const result = {}
    const res = { writeHead(status, headers) { Object.assign(result, { status, headers }) }, end(body) { result.body = body } }
    await handle(req, res, () => { result.next = true })
    return result
  }
  try {
    assert.equal((await request({ method: 'GET' })).status, 405)
    assert.equal((await request({ origin: 'https://unrelated.example' })).status, 403)
    assert.equal((await request({ body: { lat: 900, lng: 0, zoom: 10 } })).status, 400)
    const config = await request({ method: 'GET', url: '/api/maps/config' })
    assert.deepEqual(JSON.parse(config.body), { googleStatic: true })
    assert.ok(!config.body.includes('test-only-key'))
    assert.equal(calls, 0)
    const result = await request({ body: { lat: 38.64, lng: -121.27, zoom: 11 } })
    assert.equal(result.status, 200)
    assert.equal(result.headers['Cache-Control'], 'no-store')
    assert.equal(calls, 1)
    globalThis.fetch = async () => { calls++; throw new Error('private upstream key details') }
    const failure = await request({ body: { lat: 38.64, lng: -121.27, zoom: 11 } })
    assert.equal(failure.status, 502)
    assert.ok(!failure.body.includes('private upstream'))
    assert.equal(calls, 2, 'failed requests are not automatically retried')
  } finally {
    globalThis.fetch = originalFetch
    if (key === undefined) delete process.env.GOOGLE_MAPS_API_KEY
    else process.env.GOOGLE_MAPS_API_KEY = key
  }
})
