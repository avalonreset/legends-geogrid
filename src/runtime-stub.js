export function createGoogleTiles() {
  throw new Error('Google Map Tiles require the local HTTP server (pnpm dev). OpenStreetMap backgrounds remain active in static file mode.')
}
export class MaplibreGL {
  constructor() {
    throw new Error('OpenFreeMap vector styles require the local HTTP server (pnpm dev). OpenStreetMap backgrounds remain active in static file mode.')
  }
}
export const setWorkerUrl = () => {}
export default ''
