// Strip the MapLibre worker bundle's module syntax so it can run as a classic worker.
// The bundle's only module syntax is its trailing default export. The sourceMappingURL
// comment is removed first so it cannot keep the export from being the trailing token,
// and the export removal is anchored to the end so an interior string literal that
// merely looks like an export is left untouched.
export const classicWorkerSource = source => source
  .replace(/\/\/#\s*sourceMappingURL=\S+\s*$/, '')
  .replace(/\bexport\s*(?:\{\s*[\w$]+\s+as\s+default\s*\}|default\s+[\w$]+)\s*;?\s*$/, '')
