import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig } from 'vite'

const root = import.meta.dirname
const pkg = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8'))
const SCOPE = '.ggv-root'

// Every style rule is confined to the viewer root so the host page is never restyled, and the
// remote webfont import is dropped so the viewer needs no style or font origin beyond the host's own.
const scopeToViewer = {
  postcssPlugin: 'geogrid-viewer-scope',
  Once(css) {
    css.walkAtRules('import', rule => { rule.remove() })
    css.walkRules(rule => {
      let parent = rule.parent
      while (parent && parent.type !== 'root') {
        if (parent.type === 'atrule' && /keyframes$/i.test(parent.name)) return
        parent = parent.parent
      }
      rule.selectors = rule.selectors.map(selector => {
        const s = selector.trim()
        if (s.startsWith(SCOPE)) return s
        if (/^(:root|html|body|#app)$/.test(s)) return SCOPE
        const rest = s.replace(/^(?:html|body)\s+/, '')
        return `${SCOPE} ${rest}`
      })
    })
  },
}

// The MapLibre worker is served as a plain same-origin file next to the script (no eval, no inline script).
function copyWorker() {
  return {
    name: 'geogrid-viewer-worker',
    generateBundle() {
      this.emitFile({
        type: 'asset',
        fileName: 'geogrid-viewer-worker.js',
        source: readFileSync(resolve(root, 'node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs')),
      })
    },
  }
}

const stub = resolve(root, 'src/runtime-stub.js')
const viewer = file => resolve(root, 'src/viewer', file)

export default defineConfig({
  publicDir: false,
  plugins: [copyWorker()],
  define: { __VIEWER_VERSION__: JSON.stringify(pkg.version), 'process.env.NODE_ENV': JSON.stringify('production') },
  css: { postcss: { plugins: [scopeToViewer] } },
  resolve: {
    alias: [
      { find: './starter-data.js', replacement: viewer('viewer-starter-stub.js') },
      { find: './osm-tiles.js', replacement: viewer('viewer-osm-stub.js') },
      { find: './maplibre-worker.js', replacement: viewer('viewer-maplibre-worker.js') },
      { find: 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url', replacement: stub },
    ],
  },
  build: {
    outDir: 'dist-viewer',
    emptyOutDir: true,
    cssCodeSplit: false,
    modulePreload: false,
    sourcemap: false,
    minify: true,
    rollupOptions: {
      input: resolve(root, 'src/viewer-entry.js'),
      // Keep the entry exports: the page reaches the viewer only through the GeoGridViewer global.
      preserveEntrySignatures: 'strict',
      output: {
        format: 'iife',
        name: 'GeoGridViewer',
        codeSplitting: false,
        entryFileNames: 'geogrid-viewer.js',
        assetFileNames: 'geogrid-viewer[extname]',
      },
    },
  },
})
