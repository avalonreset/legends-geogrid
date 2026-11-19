import { viewerRuntime } from './viewer-runtime.js'

export async function maplibreWorkerUrl() {
  return viewerRuntime.workerUrl()
}
