import { defineConfig } from 'vite'
import { mapPreviewPlugin } from './tools/map-preview-plugin.mjs'
import { googleTilesPlugin } from './tools/google-tiles-plugin.mjs'

export default defineConfig({
  plugins: [mapPreviewPlugin(), googleTilesPlugin()],
  build: {
    rollupOptions: {
      input: { companion: 'index.html', legacy: 'legacy.html' },
    },
    license: {
      fileName: 'third-party-licenses.md',
    },
  },
})
