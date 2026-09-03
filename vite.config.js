import { defineConfig } from 'vite'

export default defineConfig({
  build: {
    license: {
      fileName: 'third-party-licenses.md',
    },
  },
})
