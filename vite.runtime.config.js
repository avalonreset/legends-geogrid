import { resolve } from 'node:path'
import { defineConfig } from 'vite'

const root = import.meta.dirname
const stub = resolve(root, 'src/runtime-stub.js')

export default defineConfig({
  publicDir: false,
  resolve: {
    alias: [
      { find: './starter-data.js', replacement: resolve(root, 'src/starter-data-runtime.js') },
      { find: './google-tiles.js', replacement: stub },
      { find: '@maplibre/maplibre-gl-leaflet', replacement: stub },
      { find: 'maplibre-gl/dist/maplibre-gl.css', replacement: stub },
      { find: 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url', replacement: stub },
      { find: 'maplibre-gl', replacement: stub },
    ],
  },
  build: {
    outDir: 'assets',
    emptyOutDir: false,
    cssCodeSplit: false,
    modulePreload: false,
    rollupOptions: {
      input: resolve(root, 'src/companion.js'),
      output: {
        format: 'iife',
        name: 'GeoGridRuntime',
        entryFileNames: 'companion-runtime.js',
        assetFileNames: 'companion-runtime[extname]',
      },
    },
  },
})
