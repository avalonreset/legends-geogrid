const escape = text => String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
export const MATCHUP_STYLES = {
  primaryAhead: { color: '#00e5dc', label: 'Primary ahead', kind: 'ranked' },
  rivalAhead: { color: '#ff4545', label: 'Rival ahead', kind: 'ranked' },
  tied: { color: '#eeeeee', label: 'Same rank', kind: 'ranked' },
  primaryOnly: { color: '#8af05a', label: 'Only primary in top 30', kind: 'ranked' },
  rivalOnly: { color: '#ffbc52', label: 'Only rival in top 30', kind: 'ranked' },
  neither: { color: 'transparent', label: 'Neither in top 30', kind: 'nr' },
  unknown: { color: 'transparent', label: 'Incomplete evidence', kind: 'unknown' },
}

export function matchupLabel(cell, primaryName, rivalName) {
  if (cell.state === 'unknown') return 'Incomplete evidence'
  const rank = value => value == null ? 'outside top 30' : `#${value}`
  return `${primaryName}: ${rank(cell.primaryRank)} · ${rivalName}: ${rank(cell.rivalRank)}`
}

export function regionPanelHTML(model, region, queryId) {
  if (!region) return '<div class="side-intro"><h2>Choose an area</h2><button class="text-button" data-open-strategy>Open Strategy room →</button></div>'
  return `<div class="side-intro"><div class="eyebrow">SELECTED GEOGRAPHY</div><h2>${escape(region.label)}</h2>
    <p>${region.count} sampled locations · ${escape(model.name)}</p>
    <button class="text-button" data-open-strategy>Compare all areas →</button></div>
    <div class="strategy-area-queries">${model.queries.map(q => {
      const m = region.perQuery[q.id]
      return `<button data-region-query="${escape(q.id)}" aria-pressed="${q.id === queryId}"><strong>${escape(q.name)}</strong>
        <span>${m.top3}/${m.complete} top 3 · ${m.top10}/${m.complete} top 10</span>
        <i style="--coverage:${m.top10Pct ?? 0}%"><b style="width:${m.top3Pct ?? 0}%"></b></i>
        ${m.unknown ? `<small>${m.unknown} incomplete</small>` : ''}</button>`
    }).join('')}</div>
    <div class="side-intro"><h3>Opponents in this area</h3><p>Top-three appearances for this query. Select a profile to compare it with ${escape(model.name)}.</p></div>
    <div class="strategy-area-rivals">${(region.perQuery[queryId]?.rivals || []).slice(0, 8).filter(r => r.id !== model.targetId).map(r => `<button data-map-rival="${escape(r.id)}"><span>${escape(r.name)}<small>${escape(r.address || 'Location not verified')}</small></span><strong>${r.count}/${r.denominator}</strong></button>`).join('')}</div>
    <p class="list-caption">Geographic sectors are measured study areas, not city boundaries. Coverage is sampled reach, not search demand.</p>`
}

export function matchupPanelHTML(matchup, model, queryId) {
  if (!matchup?.available) return '<div class="side-intro"><h2>Comparison unavailable</h2><p>Choose a profile with compatible complete evidence.</p></div>'
  const counts = matchup.counts
  const primary = model.businesses.find(b => b.id === model.targetId)
  const rival = matchup.rival
  return `<div class="side-intro"><div class="eyebrow">HEAD-TO-HEAD · SAME SEARCHES</div><h2>${escape(primary.name)}</h2><p>versus</p><h2>${escape(rival.name)}</h2>
    <p>${escape(rival.address || 'Profile location not verified')}</p><p>${escape(matchup.region.label)} · ${escape(model.queries.find(q => q.id === queryId)?.name)}</p>
    <button class="text-button" data-open-strategy>Choose another opponent →</button></div>
    <div class="matchup-totals">${Object.entries(MATCHUP_STYLES).map(([key, value]) => `<div><i style="background:${value.color}"></i><span>${value.label}</span><strong>${counts[key] || 0}</strong></div>`).join('')}</div>
    <div class="side-intro"><h3>What this comparison reveals</h3><p>Where you already outrank this profile, where it leads, and where only one appears in the first 30 results.</p><p>Hover for both ranks. Click a location to inspect the actual returned results.</p></div>
    <div class="campaign-actions matchup-actions"><button data-return-region>View primary rankings</button><button data-open-strategy>Strategy room</button></div>
    <p class="list-caption">“Ahead” compares exact observed ranks when both profiles appear. Absence stays outside top 30; it is never assigned an invented rank. This snapshot does not establish movement or future difficulty.</p>`
}
