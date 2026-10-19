import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer, request as httpRequest } from 'node:http'
import { createGoogleTilesMiddleware } from '../tools/google-tiles-plugin.mjs'

const KEY = 'private-test-key'
const TOKEN = 'private-provider-session'
const START = 1800000000000
const sessionJSON = (expiry = (START + 3600000) / 1000) => ({
  session: TOKEN, expiry: String(expiry), tileWidth: 256, tileHeight: 256,
})
const json = (value, status = 200) => new Response(JSON.stringify(value), {
  status, headers: { 'Content-Type': 'application/json' },
})
async function harness(t, handler, options = {}) {
  const calls = []
  const middleware = createGoogleTilesMiddleware({
    getKey: () => KEY, now: () => START,
    fetcher: async (url, init) => { calls.push({ url: new URL(url), init }); return handler(new URL(url), init) },
    ...options,
  })
  const server = createServer((req, res) => {
    Promise.resolve(middleware(req, res, () => { res.writeHead(404); res.end('next') }))
      .catch(() => { res.writeHead(500); res.end('unhandled middleware error') })
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections() }))
  const base = `http://127.0.0.1:${server.address().port}`
  // Use node:http so deliberate Host overrides reach the server; fetch rewrites
  // this forbidden header and would accidentally exercise a valid local request.
  const request = (path, init = {}) => new Promise((resolve, reject) => {
    const req = httpRequest(base + path, { method: init.method || 'GET', headers: init.headers }, res => {
      const chunks = []
      res.on('data', chunk => chunks.push(chunk))
      res.on('end', () => resolve(new Response(Buffer.concat(chunks), { status: res.statusCode, headers: res.headers })))
      res.on('error', reject)
    })
    req.on('error', reject)
    req.end(init.body)
  })
  const session = (style = 'roadmap', init = {}) => request('/api/maps/google/session', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ style }), ...init,
  })
  return { calls, request, session, base }
}

test('Google tiles reuses per-style sessions and coalesces concurrent paid session creation', async t => {
  let release
  const gate = new Promise(resolve => { release = resolve })
  const h = await harness(t, async () => { await gate; return json(sessionJSON()) })
  const pending = Array.from({ length: 8 }, () => h.session())
  await new Promise(resolve => setTimeout(resolve, 40))
  release()
  const results = await Promise.all(pending.map(async p => (await p).json()))
  assert.equal(h.calls.length, 1)
  assert.ok(results.every(r => r.id === results[0].id))
  assert.match(results[0].id, /^[a-f0-9-]{36}$/)
  assert.equal(results[0].expiry, START + 3600000)
  assert.deepEqual(Object.keys(results[0]).sort(), ['expiry', 'id'])
  assert.equal(JSON.stringify(results).includes(TOKEN), false)
  assert.equal(JSON.stringify(results).includes(KEY), false)
  await h.session()
  assert.equal(h.calls.length, 1)
  await h.session('dark')
  assert.equal(h.calls.length, 2)
  const body = JSON.parse(h.calls[1].init.body)
  assert.equal(body.mapType, 'roadmap')
  assert.ok(body.styles.length)
  assert.equal(body.language, 'en-US')
  assert.equal(h.calls[0].url.searchParams.get('key'), KEY)
})

test('Google adapter rejects cross-origin, malformed and unsupported requests before provider spending', async t => {
  const h = await harness(t, () => { throw new Error('Provider must not be called') })
  const attempts = [
    ['/api/maps/google/session', {}, 405],
    ['/api/maps/google/session', { method: 'POST', headers: { Origin: 'https://attacker.example' }, body: '{"style":"roadmap"}' }, 403],
    ['/api/maps/google/session', { method: 'POST', headers: { 'Sec-Fetch-Site': 'cross-site' }, body: '{"style":"roadmap"}' }, 403],
    ['/api/maps/google/session', { method: 'POST', headers: { Host: 'attacker.example' }, body: '{"style":"roadmap"}' }, 403],
    ['/api/maps/google/session', { method: 'POST', body: '{bad' }, 400],
    ['/api/maps/google/session', { method: 'POST', body: 'null' }, 400],
    ['/api/maps/google/session', { method: 'POST', body: '[]' }, 400],
    ['/api/maps/google/session', { method: 'POST', body: '{"style":["roadmap"]}' }, 400],
    ['/api/maps/google/session', { method: 'POST', body: '{"style":"toString"}' }, 400],
    ['/api/maps/google/session', { method: 'POST', body: '{"style":"unknown"}' }, 400],
    ['/api/maps/google/session', { method: 'POST', body: 'x'.repeat(1025) }, 413],
    ['/api/maps/google/unknown', {}, 404],
  ]
  for (const [path, init, status] of attempts) {
    const response = await h.request(path, init)
    assert.equal(response.status, status, `${init.method || 'GET'} ${path} ${JSON.stringify(init.headers || {})} ${init.body || ''}`)
  }
  assert.equal(h.calls.length, 0)
  const unmatched = await h.request('/not-google')
  assert.equal(await unmatched.text(), 'next')
})

test('Google adapter fails without credentials without calling provider', async t => {
  const h = await harness(t, () => { throw new Error('No provider') }, { getKey: () => undefined })
  assert.equal((await h.session()).status, 503)
  assert.equal(h.calls.length, 0)
})

test('Google tiles stream exact image bytes with private tokens only in upstream requests', async t => {
  const image = Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10, 0, 255])
  const h = await harness(t, url => url.pathname.endsWith('createSession')
    ? json(sessionJSON())
    : new Response(image, { headers: { 'Content-Type': 'image/png' } }))
  const { id } = await (await h.session()).json()
  const response = await h.request(`/api/maps/google/${id}/tiles/8/30/44`)
  assert.equal(response.status, 200)
  assert.equal(response.headers.get('cache-control'), 'no-store')
  assert.equal(response.headers.get('content-type'), 'image/png')
  assert.deepEqual(new Uint8Array(await response.arrayBuffer()), image)
  assert.equal(h.calls[1].url.pathname, '/v1/2dtiles/8/30/44')
  assert.equal(h.calls[1].url.searchParams.get('session'), TOKEN)
  assert.equal(h.calls[1].url.searchParams.get('key'), KEY)
  for (const coordinate of ['23/0/0', '2/4/0', '2/0/4', '2/9999999999999999999999999/0']) {
    assert.equal((await h.request(`/api/maps/google/${id}/tiles/${coordinate}`)).status, 400)
  }
  assert.equal(h.calls.length, 2)
})

test('Google viewport validates bounds and exposes only public attribution fields', async t => {
  const rectangles = [{ maxZoom: 18, west: -122, east: -121, north: 39, south: 38 }]
  const h = await harness(t, url => url.pathname.endsWith('createSession') ? json(sessionJSON())
    : json({ copyright: 'Map data ©2026 Google', maxZoomRects: rectangles, session: TOKEN, key: KEY, debug: 'private' }))
  const { id } = await (await h.session()).json()
  const path = `/api/maps/google/${id}/viewport`
  for (const query of ['', '?zoom=&north=39&south=38&east=-121&west=-122', '?zoom=12&north=39&south=38&east=-121&west=', '?zoom=12&north=39&south=38&east=-121', '?zoom=12.5&north=39&south=38&east=-121&west=-122', '?zoom=12&north=38&south=39&east=-121&west=-122', '?zoom=12&north=91&south=38&east=-121&west=-122', '?zoom=12&north=39&south=38&east=181&west=-122', '?zoom=12&north=NaN&south=38&east=-121&west=-122']) {
    assert.equal((await h.request(path + query)).status, 400)
  }
  assert.equal(h.calls.length, 1)
  const response = await h.request(path + '?zoom=12&north=39&south=38&east=-121&west=-122')
  assert.deepEqual(await response.json(), { copyright: 'Map data ©2026 Google', maxZoomRects: rectangles })
  assert.equal(h.calls[1].url.pathname, '/tile/v1/viewport')
  assert.equal(h.calls[1].url.searchParams.get('session'), TOKEN)
})

test('Google upstream errors do not expose key, token, raw response or thrown URL', async t => {
  for (const [upstreamStatus, expectedStatus] of [[403, 502], [429, 429]]) {
    const h = await harness(t, () => json({ error: `${KEY} ${TOKEN}` }, upstreamStatus))
    const response = await h.session()
    assert.equal(response.status, expectedStatus)
    const text = await response.text()
    assert.ok(!text.includes(KEY) && !text.includes(TOKEN))
  }
  const h = await harness(t, () => { throw new Error(`https://tile.googleapis.com?key=${KEY}&session=${TOKEN}`) })
  const response = await h.session()
  assert.equal(response.status, 502)
  assert.doesNotMatch(await response.text(), /private-test-key|private-provider-session|tile\.googleapis/)
})

test('Google adapter rejects non-image tiles and missing attribution without leaking responses', async t => {
  const h = await harness(t, url => url.pathname.endsWith('createSession') ? json(sessionJSON()) : json({ key: KEY, session: TOKEN }))
  const { id } = await (await h.session()).json()
  for (const suffix of ['tiles/1/0/0', 'viewport?zoom=12&north=39&south=38&east=-121&west=-122']) {
    const response = await h.request(`/api/maps/google/${id}/${suffix}`)
    assert.equal(response.status, 502)
    assert.doesNotMatch(await response.text(), /private-test-key|private-provider-session/)
  }
})

test('Google adapter can retry a failed session and handles interrupted tile bodies without exposing secrets', async t => {
  let attempts = 0
  const h = await harness(t, url => {
    if (url.pathname.endsWith('createSession')) {
      if (++attempts === 1) throw new Error(`Session failed: ${KEY}`)
      return json(sessionJSON())
    }
    return {
      ok: true, headers: new Headers({ 'Content-Type': 'image/png' }),
      arrayBuffer: async () => { throw new Error(`Stream failed: ${TOKEN}`) },
    }
  })
  assert.equal((await h.session()).status, 502)
  const response = await h.session()
  assert.equal(response.status, 200)
  const { id } = await response.json()
  const tile = await h.request(`/api/maps/google/${id}/tiles/1/0/0`)
  assert.equal(tile.status, 502)
  assert.equal(tile.headers.get('content-type'), 'application/json')
  assert.doesNotMatch(await tile.text(), /private-test-key|private-provider-session/)
  assert.equal(attempts, 2)
})

test('Google session expiry refreshes near-expired sessions and stops expired tile calls', async t => {
  let clock = START
  let count = 0
  const h = await harness(t, () => { count++; return json(sessionJSON((clock + 120000) / 1000)) }, { now: () => clock })
  const original = await (await h.session()).json()
  clock += 30000
  assert.equal((await (await h.session()).json()).id, original.id)
  assert.equal(count, 1)
  clock += 31000
  const fresh = await (await h.session()).json()
  assert.notEqual(fresh.id, original.id)
  assert.equal(count, 2)
  clock = START + 121000
  assert.equal((await h.request(`/api/maps/google/${original.id}/tiles/1/0/0`)).status, 410)
  assert.equal(count, 2)
})

test('Google adapter rejects invalid or expired provider session payloads', async t => {
  for (const bad of [
    { ...sessionJSON(), session: '' },
    { ...sessionJSON(), session: { secret: TOKEN } },
    { ...sessionJSON(), tileWidth: 512 },
    { ...sessionJSON(), expiry: 'not-a-time' },
    sessionJSON((START - 1000) / 1000),
  ]) {
    const h = await harness(t, () => json(bad))
    assert.equal((await h.session()).status, 502)
  }
})
