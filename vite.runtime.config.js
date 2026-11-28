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
      // OpenFreeMap vector styles work from file://: MapLibre is bundled and its worker starts from a Blob URL.
      { find: './maplibre-worker.js', replacement: resolve(root, 'src/maplibre-worker-inline.js') },
      { find: 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url', replacement: stub },
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
        codeSplitting: false,
        entryFileNames: 'companion-runtime.js',
        assetFileNames: 'companion-runtime[extname]',
      },
    },
  },
})
