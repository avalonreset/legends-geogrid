// Study-bound, portable attachment discovery. Never attach another client's audit.
export async function resolveStudyAttachment({ attachment, explicit, studyURL, model, baseURL, fetcher = fetch }) {
  if (!['name_review', 'campaign_research'].includes(attachment)) throw new Error('Unknown study attachment')
  const localURL = (value, relativeTo = baseURL) => {
    const url = new URL(value, relativeTo)
    if (!['http:', 'https:'].includes(url.protocol) || url.origin !== new URL(baseURL).origin || url.username || url.password) throw new Error('Study evidence must use the same origin')
    return url
  }
  if (explicit) return localURL(explicit).href
  if (!studyURL) return null
  const study = localURL(studyURL)
  const manifestURL = new URL(study.href)
  manifestURL.search = ''; manifestURL.hash = ''
  manifestURL.pathname = manifestURL.pathname.replace(/\.json$/i, '') + '.attachments.json'
  const response = await fetcher(manifestURL.href, { cache: 'no-store' })
  if (response.status === 404) return null
  if (!response.ok) throw new Error(`Attachment manifest failed (HTTP ${response.status})`)
  // Static dev servers may return their HTML fallback for absent JSON files.
  if (!response.headers.get('content-type')?.includes('application/json')) return null
  const manifest = await response.json()
  if (manifest.schema !== 'geogrid-study-attachments/v1' || !model.evidence?.plan_sha256 || manifest.study_plan_sha256 !== model.evidence.plan_sha256) throw new Error('Attachment manifest belongs to a different study')
  if (typeof manifest[attachment] !== 'string') return null
  return localURL(manifest[attachment], manifestURL.href).href
}

export const resolveReviewAttachment = args => resolveStudyAttachment({ ...args, attachment: 'name_review' })
