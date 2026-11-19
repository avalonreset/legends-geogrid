// Builds the viewer bundle into a temp folder and loads it into a jsdom window (no WebGL, no network).
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import vm from 'node:vm'
import { JSDOM } from 'jsdom'

const root = resolve(import.meta.dirname, '..', '..')

export function buildViewer() {
  const outDir = mkdtempSync(join(tmpdir(), 'ggv-'))
  execFileSync(process.execPath, [join(root, 'node_modules/vite/bin/vite.js'), 'build', '--config', 'vite.viewer.config.js',
    '--outDir', outDir, '--emptyOutDir'], { cwd: root, stdio: 'pipe' })
  return {
    js: readFileSync(join(outDir, 'geogrid-viewer.js'), 'utf8'),
    css: readFileSync(join(outDir, 'geogrid-viewer.css'), 'utf8'),
    worker: readFileSync(join(outDir, 'geogrid-viewer-worker.js'), 'utf8'),
    cleanup: () => rmSync(outDir, { recursive: true, force: true }),
  }
}

export function createWindow(js) {
  const dom = new JSDOM('<!doctype html><html><body><div id="host"></div></body></html>', { pretendToBeVisual: true, runScripts: 'outside-only', url: 'https://app.example.test/report' })
  const w = dom.window
  const fetched = []
  const ctx = new Proxy({}, {
    get(target, key) {
      if (key === 'measureText') return () => ({ width: 0 })
      if (key === 'createImageData') return (width, height) => ({ width, height, data: new Uint8ClampedArray(width * height * 4) })
      if (key === 'getImageData') return (x, y, width, height) => ({ width, height, data: new Uint8ClampedArray(width * height * 4) })
      return key in target ? target[key] : () => ctx
    },
    set(target, key, value) { target[key] = value; return true },
  })
  w.HTMLCanvasElement.prototype.getContext = type => (type === '2d' ? ctx : null)
  w.MessageChannel = MessageChannel
  Object.defineProperty(w.HTMLElement.prototype, 'clientWidth', { get: () => 900 })
  Object.defineProperty(w.HTMLElement.prototype, 'clientHeight', { get: () => 600 })
  w.HTMLElement.prototype.getBoundingClientRect = () => ({ x: 0, y: 0, left: 0, top: 0, right: 900, bottom: 600, width: 900, height: 600 })
  w.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} })
  w.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
  w.Worker = class { postMessage() {} terminate() {} addEventListener() {} removeEventListener() {} }
  w.fetch = async url => { fetched.push(String(url)); throw new Error('offline test window') }
  new vm.Script(js).runInContext(dom.getInternalVMContext())
  return { dom, w, fetched }
}
