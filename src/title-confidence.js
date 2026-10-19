// An analyst's ordinal evidence judgement, never a statistical violation probability.
export const TITLE_CONFIDENCE_RUBRIC = 'title-evidence-v1'
export const CONFIDENCE_LEVELS = [
  'Branding supports the title',
  'Weak concern',
  'Limited concern',
  'Moderate concern',
  'Strong concern',
  'Very strong concern',
]
export function titleConfidence(c, now = Date.now()) {
  const x = c?.confidence
  if (!x || x.rubric !== TITLE_CONFIDENCE_RUBRIC || !Number.isInteger(x.level) || x.level < 0 || x.level > 5) return null
  if (!c.source_review || !c.cid_verified || c.profile?.status !== 'complete') return null
  if (x.cid !== c.cid || x.profile_name !== c.profile.name || typeof x.rationale !== 'string' || !x.rationale.trim() || !Array.isArray(x.factors) || !x.factors.length) return null
  for (const timestamp of [x.checked_at,c.profile.checked_at,c.source_review.checked_at]) {
    const age = now - Date.parse(timestamp)
    if (!Number.isFinite(age) || age < -300000 || age > 7*86400000) return null
  }
  if (x.factors.some(f=>typeof f?.label!=='string'||typeof f?.reason!=='string'||!f.reason.trim()||typeof f?.met!=='boolean')) return null
  return { ...x, label: CONFIDENCE_LEVELS[x.level], tone: x.level >= 4 ? 'high' : x.level >= 3 ? 'moderate' : 'low' }
}
