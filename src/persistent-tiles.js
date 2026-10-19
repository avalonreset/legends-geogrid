import L from 'leaflet'

// Leaflet 1.9's non-animated setView fires viewprereset, which normally destroys
// every tile. Fractional wheel zoom uses setView each frame: keep the old levels
// and let GridLayer transform them and fade loaded replacements over them.
export const PersistentTileLayer = L.TileLayer.extend({
  getEvents() {
    const events = L.TileLayer.prototype.getEvents.call(this)
    delete events.viewprereset
    return events
  },

  _pruneTiles() {
    // Preserve coverage even across a rapid jump of more than two zoom levels.
    // Normal pruning resumes after the replacement tiles finish their fade.
    if (this._map && Object.values(this._tiles).some(tile => tile.current && !tile.active)) return
    L.TileLayer.prototype._pruneTiles.call(this)
  },
})
