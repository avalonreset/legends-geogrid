import { randomUUID } from 'node:crypto'

const darkStyle = [
  { elementType: 'geometry', stylers: [{ color: '#171717' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#bcbcbc' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#171717' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#343434' }] },
  { featureType: 'road.highway', elementType: 'geometry', stylers: [{ color: '#595044' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#122c35' }] },
  { featureType: 'poi.park', elementType: 'geometry', stylers: [{ color: '#203025' }] },
]
const styles = {
  roadmap: { mapType: 'roadmap' },
  dark: { mapType: 'roadmap', styles: darkStyle },
  satellite: { mapType: 'satellite', layerTypes: ['layerRoadmap'] },
}

// Reusable same-origin server adapter. Keys and provider session tokens never
// enter browser URLs/assets. Google imagery is streamed, never stored on disk.
export function createGoogleTilesMiddleware({ getKey = () => process.env.GOOGLE_MAP_TILES_API_KEY || process.env.GOOGLE_MAPS_API_KEY,
  fetcher = (...args) => fetch(...args), now = Date.now } = {}) {
  const sessions = new Map(), byStyle = new Map(), pending = new Map()
  const upstream = async (path, params, options = {}) => {
    const response = await fetcher(`https://tile.googleapis.com${path}?${new URLSearchParams({ ...params, key: getKey() })}`,
      { ...options, signal: AbortSignal.timeout(25000) })
    if (!response.ok) {
      const error = new Error('Google Maps could not load. Check Map Tiles API access, key restrictions, billing and quota.')
      error.status = response.status === 429 ? 429 : 502
      throw error
    }
    return response
  }
  const getSession = async style => {
    const saved = sessions.get(byStyle.get(style))
    if (saved && saved.expiry > now() + 60000) return saved
    if (pending.has(style)) return pending.get(style)
    const task = (async () => {
      const response = await upstream('/v1/createSession', {}, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...styles[style], language: 'en-US', region: 'US' }),
      })
      const data = await response.json()
      if (typeof data.session !== 'string' || !data.session || !Number.isFinite(Number(data.expiry)) ||
          Number(data.expiry) * 1000 <= now() + 60000 || data.tileWidth !== 256 || data.tileHeight !== 256) {
        throw new Error('Google returned an invalid map session.')
      }
      const session = { id: randomUUID(), token: data.session, expiry: Number(data.expiry) * 1000 }
      for (const [id, previous] of sessions) if (previous.expiry <= now()) sessions.delete(id)
      sessions.set(session.id, session)
      byStyle.set(style, session.id)
      return session
    })()
    pending.set(style, task)
    try { return await task } finally { pending.delete(style) }
  }
  return async (req, res, next) => {
    const url = new URL(req.url, 'http://localhost')
    if (!url.pathname.startsWith('/api/maps/google/')) return next()
    const reply = (status, value) => {
      res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' })
      res.end(JSON.stringify(value))
    }
    // The shipped adapter is local-only. A hosted deployment must install its
    // own authenticated same-origin boundary, not expose a public billing proxy.
    const host = req.headers.host || ''
    if (!/^(127\.0\.0\.1|localhost)(:\d+)?$/.test(host) ||
        (req.headers.origin && req.headers.origin !== `http://${host}`) ||
        req.headers['sec-fetch-site'] === 'cross-site') return reply(403, { error: 'Same-origin local maps only.' })
    if (!getKey()) return reply(503, { error: 'Set GOOGLE_MAP_TILES_API_KEY on the server and enable Map Tiles API.' })
    try {
      if (url.pathname === '/api/maps/google/session') {
        if (req.method !== 'POST') return reply(405, { error: 'Use POST.' })
        let body = ''
        for await (const chunk of req) {
          body += chunk
          if (body.length > 1024) return reply(413, { error: 'Request too large.' })
        }
        let input
        try { input = JSON.parse(body) } catch { return reply(400, { error: 'Invalid request.' }) }
        if (!input || typeof input !== 'object' || Array.isArray(input) || typeof input.style !== 'string' ||
            !Object.hasOwn(styles, input.style)) return reply(400, { error: 'Unknown Google map style.' })
        const session = await getSession(input.style)
        return reply(200, { id: session.id, expiry: session.expiry })
      }
      if (req.method !== 'GET') return reply(405, { error: 'Use GET.' })
      const match = url.pathname.match(/^\/api\/maps\/google\/([a-f0-9-]{36})\/(viewport|tiles\/(\d+)\/(\d+)\/(\d+))$/)
      if (!match) return reply(404, { error: 'Unknown map resource.' })
      const session = sessions.get(match[1])
      if (!session || session.expiry <= now()) return reply(410, { error: 'Map session expired. Reselect Google Maps.' })
      if (match[2] === 'viewport') {
        const bounds = Object.fromEntries(['zoom', 'north', 'south', 'east', 'west'].map(k => [k, Number(url.searchParams.get(k))]))
        if (['zoom', 'north', 'south', 'east', 'west'].some(k => !url.searchParams.get(k)?.trim()) ||
            !Object.values(bounds).every(Number.isFinite) || !Number.isInteger(bounds.zoom) ||
            bounds.zoom < 0 || bounds.zoom > 22 || Math.abs(bounds.north) > 90 || Math.abs(bounds.south) > 90 ||
            bounds.north <= bounds.south || Math.abs(bounds.east) > 180 || Math.abs(bounds.west) > 180) {
          return reply(400, { error: 'Invalid viewport.' })
        }
        const response = await upstream('/tile/v1/viewport', { session: session.token, ...bounds })
        const data = await response.json()
        if (!data.copyright) throw new Error('Google attribution unavailable.')
        return reply(200, { copyright: data.copyright, maxZoomRects: data.maxZoomRects })
      }
      const [z, x, y] = match.slice(3).map(Number)
      if (z > 22 || x >= 2 ** z || y >= 2 ** z) return reply(400, { error: 'Invalid tile coordinates.' })
      const response = await upstream(`/v1/2dtiles/${z}/${x}/${y}`, { session: session.token })
      const type = response.headers.get('content-type')
      if (!type?.startsWith('image/')) throw new Error('Google returned no tile image.')
      const bytes = Buffer.from(await response.arrayBuffer())
      res.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-store' })
      res.end(bytes)
    } catch (error) {
      // Do not leak upstream URLs, credentials, provider tokens or raw errors.
      reply(error.status || 502, { error: 'Google Maps could not load. Check Map Tiles API access, key restrictions, billing and quota.' })
    }
  }
}

export function googleTilesPlugin() {
  const attach = server => { server.middlewares.use(createGoogleTilesMiddleware()) }
  return { name: 'google-interactive-tiles', configureServer: attach, configurePreviewServer: attach }
}
