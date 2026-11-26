import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { normalizeStudy } from '../src/study-model.js'
import { campaignEngine, prominenceIndex, CAMPAIGN_WEIGHTS } from '../src/campaign-engine.js'
import { validateCampaignResearch, campaignPanelHTML, visionAgentCampaignBrief } from '../src/campaign-panel.js'
import { suspectTerritory } from '../src/name-review.js'
import { buildViewer, createWindow } from './helpers/viewer-window.js'

const root = resolve(import.meta.dirname, '..')
const readJson = rel => JSON.parse(readFileSync(join(root, rel), 'utf8'))
const phillyRaw = readJson('src/data/cosmis-deli-philly-study.json')
const phillyResearchRaw = readJson('src/data/cosmis-deli-philly-campaign-research.json')
const phillyNameReviewRaw = readJson('src/data/cosmis-deli-philly-name-review.json')
const phillyModel = normalizeStudy(phillyRaw)
const phillyEngine = campaignEngine(phillyModel)

let bundle
before(() => { bundle = buildViewer() })
after(() => bundle?.cleanup())

const click = (w, el) => el.dispatchEvent(new w.MouseEvent('click', { bubbles: true, cancelable: true }))

// ---------- Engine Acceptance Tests (Section 8, items 1 to 9) ----------

test('1. Philadelphia river-clipped landmass components: home 291 PA pins, detached C1 167 NJ pins', () => {
  assert.equal(phillyEngine.available, true)
  assert.equal(phillyEngine.landmass.landClipped, true)
  assert.equal(phillyEngine.landmass.home.pins, 291)
  const sizes = [phillyEngine.landmass.home.pins, ...phillyEngine.landmass.detached.map(d => d.pins)]
  assert.deepEqual(sizes, [291, 167])
  assert.equal(phillyEngine.landmass.detached[0].id, 'C1')
})

test('2. Prominence index Pm matches Cosmi 2.27, POPPA WATTS 1.41, Woodrow 2.71', () => {
  assert.equal(phillyEngine.target.pm, 2.27)
  assert.equal(phillyEngine.target.category, 'Sandwich shop')
  const pmFor = needle => {
    const b = phillyModel.businesses.find(x => x.name.includes(needle))
    assert.ok(b, `missing business ${needle}`)
    return Number(prominenceIndex(b).pm.toFixed(2))
  }
  assert.equal(pmFor('POPPA WATTS HOAGIES'), 1.41)
  assert.equal(pmFor("Woodrow's Sandwich Shop"), 2.71)
})

test('3. Distance-decay reach curve matches hoagie stronghold and cheesesteak 1-mile drop-off', () => {
  assert.deepEqual(phillyEngine.reachByQuery.q1, [0.69, 0.46, 0.42, 0.16, 0.03, 0.02])
  assert.deepEqual(phillyEngine.reachByQuery.q2, [1, 0.85, 0.73, 0.29, 0.13, 0.01])
  assert.deepEqual(phillyEngine.reachByQuery.q3, [0.25, 0, 0, 0, 0, 0])
})

test('4. Campaign weights and max W / strike counts match South Philly baseline', () => {
  assert.deepEqual(CAMPAIGN_WEIGHTS, { gap: 0.40, weak: 0.25, lift: 0.20, reach: 0.15, fortress: 0.5, detached: 0.5 })
  assert.equal(phillyEngine.queries.q1.stats.maxW, 79)
  assert.equal(phillyEngine.queries.q2.stats.maxW, 76)
  assert.equal(phillyEngine.queries.q1.stats.strikeCount, 10)
  assert.equal(phillyEngine.queries.q2.stats.strikeCount, 3)
  assert.equal(phillyEngine.queries.q3.stats.strikeCount, 0)
})

test('5. Sandwich shop service_gap play: Woodrow lead holder, ahead [188, 205]', () => {
  const play = phillyEngine.queries.q1.plays.find(p => p.mechanism === 'service_gap')
  assert.ok(play, 'expected q1 service_gap play')
  assert.equal(play.points, 13)
  assert.equal(play.leadHolder.name, "Woodrow's Sandwich Shop")
  assert.deepEqual(play.leadHolder.aheadWhereBothAppear, [188, 205])
})

test('6. Hoagie weak_pack play: POPPA WATTS HOAGIES ahead 121 of 159', () => {
  const play = phillyEngine.queries.q2.plays.find(p => p.mechanism === 'weak_pack')
  assert.ok(play, 'expected q2 weak_pack play')
  assert.equal(play.points, 25)
  assert.equal(play.leadHolder.name, 'POPPA WATTS HOAGIES')
  assert.deepEqual(play.leadHolder.aheadWhereBothAppear, [121, 159])
})

test('7. No play contains a detached NJ pin and avoid list contains C1 with 167 pins', () => {
  const detachedSet = new Set(phillyEngine.landmass.detached.flatMap(d => d.originIds))
  for (const qd of Object.values(phillyEngine.queries)) {
    for (const play of qd.plays) {
      for (const id of play.originIds) {
        assert.equal(detachedSet.has(id), false, `play ${play.id} must not include detached pin ${id}`)
      }
    }
  }
  for (const qId of ['q1', 'q2']) {
    const c1Avoid = phillyEngine.queries[qId].avoid.find(a => a.kind === 'detached_landmass' && a.componentId === 'C1')
    assert.ok(c1Avoid, `expected detached C1 avoid on ${qId}`)
    assert.equal(c1Avoid.pins, 167)
  }
  const q3Oor = phillyEngine.queries.q3.avoid.find(a => a.kind === 'out_of_reach')
  assert.ok(q3Oor && q3Oor.pins === 275, 'expected q3 out_of_reach avoid covering 275 outer pins')
})

test('8. not_your_blocker contains CHEESSTEAKS on cheesesteak with 63 first places and 0 overlap', () => {
  const njLeader = phillyEngine.queries.q3.avoid.find(a => a.kind === 'not_your_blocker' && a.title.includes('CHEESSTEAKS'))
  assert.ok(njLeader, 'CHEESSTEAKS must appear in q3 not_your_blocker avoid list')
  assert.equal(njLeader.firstPlaces, 63)
  assert.equal(njLeader.targetTop30Overlap, 0)
})

test('9. Engine output and Campaigns rail contain zero compass phrasing ("of the primary business")', () => {
  const serialized = JSON.stringify({
    target: phillyEngine.target,
    landmass: phillyEngine.landmass,
    reachByQuery: phillyEngine.reachByQuery,
    queries: Object.fromEntries(Object.entries(phillyEngine.queries).map(([k, v]) => [k, { plays: v.plays, avoid: v.avoid }])),
  })
  assert.doesNotMatch(serialized, /\b(N|NE|E|SE|S|SW|W|NW)\s+of the primary business/i)
  const research = validateCampaignResearch(phillyResearchRaw, phillyModel, phillyEngine)
  assert.equal(research.campaignPlans.length, 4)
  assert.equal(research.avoidZones.length, 5)
  const panelHtml = campaignPanelHTML(phillyEngine, phillyModel, 'q1', { research })
  assert.doesNotMatch(panelHtml, /of the primary business/i)
  assert.doesNotMatch(panelHtml, /<select\b/i)
  assert.match(panelHtml, /Copy Vision-Agent Campaign Brief/)
  const brief = visionAgentCampaignBrief(phillyEngine, phillyModel, 'q2')
  assert.match(brief, /vision-brief/)
  assert.match(brief, /POPPA WATTS HOAGIES/)
})

// ---------- Viewer & Keyword Stuffing Acceptance Tests (Section 8, items 10 to 14) ----------

test('10, 11, 12. Viewer live 5-button toolbar in Campaigns & Keyword stuffing, zero <select> / "Not scored", consistent .sidebar & visible #map', async () => {
  const { dom, w } = createWindow(bundle.js)
  try {
    const host = w.document.querySelector('#host')
    const viewer = w.GeoGridViewer.mount(host, phillyRaw, {
      capabilities: { perPointListings: true, profiles: true, nameReview: true, campaignResearch: true, strategyRoom: true },
      campaignResearch: phillyResearchRaw,
      nameReview: phillyNameReviewRaw,
    })
    await new Promise(r => setTimeout(r, 40))

    const toolbarButtons = () => [...host.querySelectorAll('.map-options button')]
    const checkSidebarAndMap = label => {
      const sidebar = host.querySelector('.sidebar')
      const mapEl = host.querySelector('#map')
      assert.ok(sidebar && !sidebar.hidden, `.sidebar must stay visible in ${label}`)
      assert.ok(mapEl && !mapEl.hidden, `#map must stay visible in ${label}`)
      assert.equal(host.querySelector('.workspace').classList.contains('keyword-review-active'), false, `keyword-review-active hide class must not exist in ${label}`)
    }

    // Rankings
    checkSidebarAndMap('Rankings')

    // Local leaders
    click(w, host.querySelector('[data-view="factions"]'))
    checkSidebarAndMap('Local leaders')

    // Campaigns: ZERO disabled buttons in the 5-button toolbar, zero <select> in Campaigns rail!
    click(w, host.querySelector('[data-view="campaigns"]'))
    checkSidebarAndMap('Campaigns')
    for (const btn of toolbarButtons()) {
      assert.equal(btn.disabled, false, `Campaigns toolbar button #${btn.id} must not be disabled`)
    }
    assert.equal(host.querySelectorAll('#side-content select').length, 0, 'Campaigns rail must contain zero <select> elements')

    // Keyword stuffing: ZERO disabled buttons, ZERO <select>, ZERO "Not scored", Inspector opens smoothly!
    click(w, host.querySelector('[data-view="keyword-stuffing"]'))
    checkSidebarAndMap('Keyword stuffing')
    for (const btn of toolbarButtons()) {
      assert.equal(btn.disabled, false, `Keyword stuffing toolbar button #${btn.id} must not be disabled`)
    }
    assert.equal(host.querySelectorAll('#side-content select, #nr-inspector select').length, 0, 'Keyword stuffing must contain zero <select> elements')
    assert.ok(!host.textContent.includes('Not scored'), 'Keyword stuffing must contain zero "Not scored" text')

    // Select first flagged row and verify Inspector renders without "Not scored" or "stolen"
    const flaggedRow = host.querySelector('[data-nr-case]')
    assert.ok(flaggedRow, 'Flagged case row must render in Keyword stuffing rail')
    click(w, flaggedRow)
    const insp = host.querySelector('#nr-inspector')
    assert.equal(insp.hidden, false, 'Inspector must open when a case is selected')
    assert.ok(host.querySelector('.workspace').classList.contains('inspector-open'))
    assert.ok(!insp.textContent.includes('Not scored'), 'Inspector must never show "Not scored"')
    assert.doesNotMatch(insp.textContent, /\bstolen\b|\bstealing\b/i, 'Inspector must never use accusatory stolen/stealing wording')
    assert.match(insp.textContent, /First places/)
    assert.match(insp.textContent, /Overlaps you/)
    assert.match(insp.textContent, /You would inherit/)
    assert.equal(insp.querySelectorAll('select').length, 0)

    viewer.destroy()
  } finally {
    dom.window.close()
  }
})

test('13. suspectTerritory for NJ CHEESSTEAKS (cid:7184314602090042923) on q3 returns 63 first places and 0 inherit', () => {
  const terr = suspectTerritory(phillyModel, 'cid:7184314602090042923')
  const q3 = terr.byQuery.q3
  assert.equal(q3.firstPlaces, 63)
  assert.ok(q3.topThree >= 63)
  assert.equal(q3.overlap, 0)
  assert.equal(q3.inherit, 0)
  assert.ok(q3.milesFromPrimary && q3.milesFromPrimary.min > 0)
})

test('14. Zero U+2013 (en-dash) or U+2014 (em-dash) in src/ code and built viewer bundle', () => {
  const walk = dir => {
    const out = []
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name)
      if (entry.isDirectory()) {
        if (entry.name === 'data') continue
        out.push(...walk(full))
      } else if (/\.(js|css)$/.test(entry.name)) {
        out.push(full)
      }
    }
    return out
  }
  const violations = []
  for (const file of walk(join(root, 'src'))) {
    const text = readFileSync(file, 'utf8')
    const lines = text.split(/\r?\n/)
    lines.forEach((line, idx) => {
      if (/[\u2013\u2014]/.test(line)) {
        violations.push(`${file}:${idx + 1}: ${line.trim().slice(0, 100)}`)
      }
    })
  }
  assert.deepEqual(violations, [], `Found forbidden U+2013/U+2014 dashes in src/:\n${violations.join('\n')}`)

  // Check built viewer bundle and companion runtime (excluding MapLibre GL's CJK vertical punctuation lookup table).
  const strippedViewer = bundle.js.replace(/"[\u2013\u2014]":`[\ufe31\ufe32]`/g, '')
  const bundleDashes = strippedViewer.match(/[\u2013\u2014]/g) || []
  assert.deepEqual(bundleDashes, [], `Found forbidden U+2013/U+2014 dashes in built geogrid-viewer.js: ${bundleDashes.length}`)
  const runtimeJs = readFileSync(join(root, 'assets/companion-runtime.js'), 'utf8')
  const runtimeDashes = runtimeJs.replace(/"[\u2013\u2014]":`[\ufe31\ufe32]`/g, '').match(/[\u2013\u2014]/g) || []
  assert.deepEqual(runtimeDashes, [], `Found forbidden U+2013/U+2014 dashes in companion-runtime.js: ${runtimeDashes.length}`)
})
