// Local development adapter. The Google server key never enters client assets.
export function mapPreviewPlugin() {
  return {
    name: 'local-map-preview',
    configureServer(server) {
      let pending = false
      server.middlewares.use(async (req, res, next) => {
        const path = req.url?.split('?')[0]
        if (!['/api/maps/config', '/api/maps/google-preview'].includes(path)) return next()
        const key = process.env.GOOGLE_MAPS_API_KEY
        const reply = (status, value) => {
          res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' })
          res.end(JSON.stringify(value))
        }
        if (!/^(127\.0\.0\.1|localhost)(:\d+)?$/.test(req.headers.host || '') ||
            (req.headers.origin && req.headers.origin !== `http://${req.headers.host}`)) {
          return reply(403, { error: 'Local map preview only.' })
        }
        if (path === '/api/maps/config') return reply(200, { googleStatic: Boolean(key) })
        if (req.method !== 'POST') return reply(405, { error: 'Use POST.' })
        if (!key) return reply(503, { error: 'Google Maps preview is not configured on this server.' })
        if (pending) return reply(429, { error: 'A Google preview is already loading.' })
        let ownsLock = false
        try {
          let body = ''
          for await (const chunk of req) {
            body += chunk
            if (body.length > 1024) return reply(413, { error: 'Request too large.' })
          }
          const { lat, lng, zoom } = JSON.parse(body)
          if (!Number.isFinite(lat) || Math.abs(lat) > 85 || !Number.isFinite(lng) ||
              Math.abs(lng) > 180 || !Number.isInteger(zoom) || zoom < 3 || zoom > 18) {
            return reply(400, { error: 'Invalid map coordinates.' })
          }
          if (pending) return reply(429, { error: 'A Google preview is already loading.' })
          pending = true
          ownsLock = true
          const params = new URLSearchParams({ center: `${lat},${lng}`, zoom: String(zoom),
            size: '640x640', scale: '2', maptype: 'roadmap', key })
          const upstream = await fetch(`https://maps.googleapis.com/maps/api/staticmap?${params}`,
            { signal: AbortSignal.timeout(20000) })
          if (!upstream.ok || !upstream.headers.get('content-type')?.startsWith('image/') ||
              upstream.headers.has('x-staticmap-api-warning')) {
            return reply(502, { error: 'Google could not supply this map. Check Static Maps access and billing.' })
          }
          const data = Buffer.from(await upstream.arrayBuffer())
          res.writeHead(200, { 'Content-Type': upstream.headers.get('content-type'), 'Cache-Control': 'no-store' })
          res.end(data)
        } catch {
          reply(502, { error: 'Map preview failed. No automatic retry was made.' })
        } finally { if (ownsLock) pending = false }
      })
    },
  }
}
