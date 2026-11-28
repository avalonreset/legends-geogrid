import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { classicWorkerSource } from '../src/classic-worker-source.js'

test('classicWorkerSource turns the real MapLibre worker bundle into a classic script', () => {
  const raw = readFileSync(new URL('../node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs', import.meta.url), 'utf8')
  const stripped = classicWorkerSource(raw)
  assert.doesNotThrow(() => new Function(stripped))
  assert.equal(stripped.includes('import.meta'), false)
  assert.equal(stripped.includes('sourceMappingURL'), false)
  assert.doesNotMatch(stripped, /\bexport\s*(?:\{[^}]*\bas\s+default\b|default\b)\s*;?\s*$/)
})

test('an interior export-looking literal does not defeat trailing export removal', () => {
  const interior = "const label = 'export { x as default }'\n"
  const source = `${interior}const x = label\nexport { x as default }\n//# sourceMappingURL=worker.mjs.map\n`
  const stripped = classicWorkerSource(source)
  assert.ok(stripped.includes(interior.trim()), 'interior literal is preserved')
  assert.doesNotMatch(stripped, /export\s*\{\s*x\s+as\s+default\s*\}\s*;?\s*$/)
  assert.equal(stripped.includes('sourceMappingURL'), false)
  assert.doesNotThrow(() => new Function(stripped))
})

test('the inline worker module re-exports classicWorkerSource and probes Worker support', () => {
  const source = readFileSync(new URL('../src/maplibre-worker-inline.js', import.meta.url), 'utf8')
  assert.match(source, /export\s*\{\s*classicWorkerSource\s*\}/)
  assert.match(source, /new Worker\(url\)/)
  assert.match(source, /probe\.terminate\(\)/)
  assert.match(source, /URL\.revokeObjectURL\?\.\(url\)/)
  assert.match(source, /Web Workers are unavailable in this browser\./)
})
