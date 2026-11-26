import L from 'leaflet'

// Leaflet 1.9's non-animated setView fires viewprereset, which destroys every
// tile, and calls _setView/_abortLoading/_update on every fractional zoom frame.
// PersistentTileLayer keeps lower-zoom parent pyramid tiles painted underneath
// while smooth wheel/camera zoom transforms run on the GPU, then loads the
// settled target zoom cleanly on top with zero blank or strobe frames.
export const PersistentTileLayer = L.TileLayer.extend({
  options: {
    keepBuffer: 6,
    updateWhenZooming: false,
    keepParentLevels: 3,
    maxRetainedTiles: 180,
  },

  getEvents() {
    const events = L.TileLayer.prototype.getEvents.call(this)
    delete events.viewprereset
    events.smoothzoomend = this._onSmoothZoomEnd
    return events
  },

  _resetView(e) {
    if (this._map && this._map._smoothZooming && this._tileZoom !== undefined && !this.options.updateWhenZooming) {
      this._setZoomTransforms(this._map.getCenter(), this._map.getZoom())
      return
    }
    L.TileLayer.prototype._resetView.call(this, e)
  },

  _onMoveEnd() {
    if (!this._map || this._map._animatingZoom) return
    if (this._map._smoothZooming && this._tileZoom !== undefined && !this.options.updateWhenZooming) return
    this._update()
  },

  _onSmoothZoomEnd() {
    if (!this._map) return
    this._setView(this._map.getCenter(), this._map.getZoom(), false, false)
  },

  _ensureNullProtoMap(obj) {
    if (obj && Object.getPrototypeOf(obj) === null) return obj
    const clean = Object.create(null)
    if (obj) {
      for (const key of Object.keys(obj)) clean[key] = obj[key]
    }
    return clean
  },

  _updateLevels() {
    if (this._levels) this._levels = this._ensureNullProtoMap(this._levels)
    const level = L.TileLayer.prototype._updateLevels.call(this)
    const zoom = this._tileZoom
    const maxZoom = this.options.maxZoom ?? 22
    if (zoom !== undefined && this._levels) {
      for (const key of Object.keys(this._levels)) {
        const z = Number(key)
        const entry = this._levels[key]
        if (!entry?.el) continue
        if (z === zoom) {
          entry.el.style.zIndex = String(maxZoom * 2 + 2)
        } else if (z < zoom) {
          entry.el.style.zIndex = String(Math.max(1, maxZoom * 2 - 2 * (zoom - z)))
        } else {
          entry.el.style.zIndex = String(Math.max(0, maxZoom * 2 - 2 * (z - zoom) - 1))
        }
      }
    }
    return level
  },

  _retainAncestorPyramid(x, y, z, minZoom) {
    let cx = x, cy = y, cz = z
    while (cz > minZoom) {
      cx = Math.floor(cx / 2)
      cy = Math.floor(cy / 2)
      cz -= 1
      const key = `${cx}:${cy}:${cz}`
      const tile = Object.hasOwn(this._tiles, key) ? this._tiles[key] : undefined
      if (tile && (tile.active || tile.loaded)) {
        tile.retain = true
      }
    }
  },

  _pruneTiles() {
    if (!this._map) return
    const tiles = Object.values(this._tiles)
    // Never prune while any current viewport tile is still loading or fading in.
    if (tiles.some(tile => tile.current && !tile.active)) return

    const zoom = this._map.getZoom()
    if (zoom > this.options.maxZoom || zoom < this.options.minZoom) {
      this._removeAllTiles()
      return
    }

    for (const key of Object.keys(this._tiles)) {
      this._tiles[key].retain = this._tiles[key].current
    }

    // Keep loaded lower-zoom parent pyramid tiles covering the active viewport
    // so subsequent zoom-in or zoom-out gestures always have an opaque floor.
    const parentDepth = Math.max(0, Number(this.options.keepParentLevels) || 0)
    const minZoom = this.options.minZoom || 0
    if (parentDepth > 0) {
      for (const key of Object.keys(this._tiles)) {
        const tile = this._tiles[key]
        if (tile.current) {
          const c = tile.coords
          this._retainAncestorPyramid(c.x, c.y, c.z, Math.max(minZoom, c.z - parentDepth))
        }
      }
    }

    // Enforce an upper bound on retained off-level tiles while never dropping current tiles.
    const maxRetained = Math.max(32, Number(this.options.maxRetainedTiles) || 180)
    let retainedCount = 0
    const nonCurrentRetained = []
    for (const key of Object.keys(this._tiles)) {
      const tile = this._tiles[key]
      if (tile.retain) {
        retainedCount++
        if (!tile.current) nonCurrentRetained.push([key, tile])
      }
    }
    if (retainedCount > maxRetained && nonCurrentRetained.length) {
      const activeZ = this._tileZoom ?? Math.round(zoom)
      nonCurrentRetained.sort((a, b) => Math.abs(b[1].coords.z - activeZ) - Math.abs(a[1].coords.z - activeZ))
      for (const [key, tile] of nonCurrentRetained) {
        if (retainedCount <= maxRetained) break
        tile.retain = false
        retainedCount--
      }
    }

    for (const key of Object.keys(this._tiles)) {
      if (!this._tiles[key].retain) {
        this._removeTile(key)
      }
    }
  },
})
