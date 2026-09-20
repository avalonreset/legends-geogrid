"""Validated, network-free input model for portable GeoGrid strategy reports."""
from __future__ import annotations

from datetime import datetime
import json
import math
from pathlib import Path

STATES = ('found', 'not_returned', 'error', 'empty', 'unmeasured')


def contiguous_depth(ranks):
    require(isinstance(ranks, list) and all(integer(r, 1) for r in ranks), 'invalid observed_ranks')
    require(len(ranks) == len(set(ranks)), 'observed_ranks must be unique')
    reached, present = 0, set(ranks)
    while reached + 1 in present:
        reached += 1
    return reached


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def text(value, label):
    require(isinstance(value, str) and bool(value.strip()), f'{label} must be nonempty text')
    require(all(ord(c) >= 32 or c in '\n\t' for c in value), f'{label} contains control characters')
    return value.strip()


def coordinates(lat, lng):
    require(number(lat) and -85 <= lat <= 85, 'latitude must be finite and within [-85, 85]')
    require(number(lng) and -180 <= lng <= 180, 'longitude must be finite and within [-180, 180]')


def bounds(value):
    require(isinstance(value, list) and len(value) == 4, 'bounds must be [west,south,east,north]')
    west, south, east, north = value
    coordinates(south, west)
    coordinates(north, east)
    require(west < east and south < north and east - west < 180,
            'bounds must have positive extent and cannot cross the antimeridian')
    return value


def local_path(root, value):
    value = text(value, 'local path')
    require('://' not in value, 'only local file paths are supported')
    path = (root / value).resolve()
    require(path.is_file(), f'input file does not exist: {path.name}')
    return path


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def validate_observation(raw, query_id):
    require(isinstance(raw, dict), 'observation must be an object')
    required = {'query_id', 'lat', 'lng', 'rank', 'state', 'returned_count', 'depth', 'sampled_at', 'source'}
    require(required <= raw.keys(), f'observation missing fields: {sorted(required - raw.keys())}')
    require(raw['query_id'] == query_id, 'observation query_id does not match lane')
    coordinates(raw['lat'], raw['lng'])
    state, rank = raw['state'], raw['rank']
    require(state in STATES, f'unknown observation state: {state}')
    require(integer(rank, 1) if state == 'found' else rank is None,
            'found needs a positive integer rank; other states need null rank')
    count, depth = raw['returned_count'], raw['depth']
    require(count is None or integer(count), 'returned_count must be null or a nonnegative integer')
    require(depth is None or integer(depth), 'depth must be null or a nonnegative integer')
    require(state != 'empty' or count in (0, None), 'empty cannot have returned results')
    require(state not in ('found', 'not_returned') or count != 0, 'valid result cannot have zero returned_count')
    sampled = raw['sampled_at']
    if sampled is not None:
        try:
            stamp = datetime.fromisoformat(sampled.replace('Z', '+00:00'))
            require(stamp.tzinfo is not None, 'sampled_at must include timezone')
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError('sampled_at must be an ISO 8601 timestamp with timezone or null') from exc
    source = text(raw['source'], 'observation source')
    result = {key: raw[key] for key in sorted(required)}
    result['source'] = source
    if 'requested_depth' in raw:
        require(raw['requested_depth'] is None or integer(raw['requested_depth'], 1), 'invalid requested_depth')
        result['requested_depth'] = raw['requested_depth']
    if 'observed_ranks' in raw:
        ranks = raw['observed_ranks']
        require(isinstance(ranks, list) and all(integer(r, 1) for r in ranks), 'invalid observed_ranks')
        require(len(ranks) == len(set(ranks)), 'observed_ranks must be unique')
        require(count is None or len(ranks) <= count, 'observed_ranks exceeds returned_count')
        require(state != 'found' or rank in ranks, 'found rank missing from observed_ranks')
        require(state not in ('empty', 'unmeasured') or not ranks,
                'empty or unmeasured origin cannot contain observed_ranks')
        require(depth is None or depth == contiguous_depth(ranks),
                'depth contradicts contiguous observed_ranks; requested depth belongs in requested_depth')
        result['observed_ranks'] = sorted(ranks)
    if 'provenance' in raw:
        # Carry only typed content identifiers, never arbitrary raw metadata,
        # account routes, paths, URLs or credentials. These are supplied hashes,
        # not independent proof of authenticity; private manifests bind artifacts.
        provenance = raw['provenance']
        require(isinstance(provenance, dict), 'provenance must be an object')
        safe = {}
        for key in ('request_fingerprint', 'evidence_sha256', 'response_sha256'):
            if key in provenance:
                value = provenance[key]
                require(value is None or (isinstance(value, str) and len(value) == 64 and
                        all(c in '0123456789abcdefABCDEF' for c in value)), f'invalid provenance {key}')
                safe[key] = value.lower() if isinstance(value, str) else None
        if 'response_retained' in provenance:
            require(type(provenance['response_retained']) is bool, 'provenance response_retained must be boolean')
            safe['response_retained'] = provenance['response_retained']
        if safe:
            result['provenance'] = safe
    return result


def runner_records(payload, lane, business):
    """Explicit legacy parsed-grid adapter; never import raw matched item payloads."""
    if payload.get('keyword') is not None:
        require(payload['keyword'] == lane['query'], 'runner keyword differs from lane query')
    if payload.get('target') is not None:
        require(payload['target'] == business['name'], 'runner target differs from business name')
    settings = payload.get('measurement_settings') or {}
    require(isinstance(settings, dict), 'runner measurement_settings must be an object')
    require(isinstance(payload['results'], list), 'runner results must be a list')
    states = {'found': 'found', 'not_returned': 'not_returned', 'ok': None,
              'error': 'error', 'provider_error': 'error', 'empty': 'empty',
              'no_results': 'empty', 'no_organic_results': 'unmeasured',
              'category_excluded': 'unmeasured', 'missing_result': 'unmeasured',
              'unmeasured': 'unmeasured', 'empty_results': 'empty',
              'not_returned_depth_reached': 'not_returned', 'not_returned_incomplete': 'not_returned'}
    output = []
    for row in payload['results']:
        require(isinstance(row, dict), 'runner result must be an object')
        status = row.get('status')
        require(isinstance(status, str), 'runner status must be text')
        require(status in states, f'unsupported runner status: {status}')
        state = states[status] or ('found' if row.get('rank') is not None else 'not_returned')
        if row.get('error'):
            state = 'error'
        point = row['point']
        require(isinstance(point, dict), 'runner point must be an object')
        result = dict(query_id=lane['query_id'], lat=point['lat'], lng=point['lng'],
                      rank=row.get('rank') if state == 'found' else None, state=state,
                      returned_count=row.get('organic_items_count', row.get('returned_items_count')),
                      depth=None, requested_depth=settings.get('depth'),
                      sampled_at=row.get('sampled_at', payload.get('sampled_at')),
                      source=row.get('source', 'runner parsed-grid'))
        if 'observed_ranks' in row and state in ('found', 'not_returned', 'error'):
            result['observed_ranks'] = row['observed_ranks']
            result['depth'] = contiguous_depth(row['observed_ranks'])
        elif state in ('empty', 'unmeasured'):
            result['depth'] = 0
        output.append(result)
    return output


def metrics(records):
    counts = {state: sum(r['state'] == state for r in records) for state in STATES}
    measured = counts['found'] + counts['not_returned']
    ranks = [r['rank'] for r in records if r['state'] == 'found']
    result = dict(sampled=len(records), measured=measured, excluded=len(records) - measured,
                  states=counts, top3=sum(r <= 3 for r in ranks), top10=sum(r <= 10 for r in ranks),
                  near_miss=sum(4 <= r <= 10 for r in ranks))
    for cutoff in (3, 10):
        result[f'top{cutoff}_observed_share'] = result[f'top{cutoff}'] / measured if measured else None
        result[f'top{cutoff}_unknown_absence'] = sum(
            r['state'] == 'not_returned' and not set(range(1, cutoff + 1)).issubset(r.get('observed_ranks', []))
            for r in records)
    return result


def full_bounds(records, business):
    lats = [r['lat'] for r in records] + [business['lat']]
    lngs = [r['lng'] for r in records] + [business['lng']]
    require(max(lngs) - min(lngs) < 180, 'antimeridian-spanning data is unsupported')
    dx = max((max(lngs) - min(lngs)) * .06, .002)
    dy = max((max(lats) - min(lats)) * .06, .002)
    return bounds([max(-180, min(lngs) - dx), max(-85, min(lats) - dy),
                   min(180, max(lngs) + dx), min(85, max(lats) + dy)])


def inside(record, extent):
    w, s, e, n = extent
    return w <= record['lng'] <= e and s <= record['lat'] <= n


def map_config(raw, root):
    require(isinstance(raw, dict), 'map must be an object')
    # Export only validated map fields, never arbitrary operator metadata.
    result = {}
    result['distance_unit'] = raw.get('distance_unit', 'km')
    require(result['distance_unit'] in ('km', 'mi'), 'map.distance_unit must be km or mi')
    if 'height_pt' in raw:
        require(integer(raw['height_pt']) and 410 <= raw['height_pt'] <= 480,
                'map.height_pt must be an integer within 410..480')
        result['height_pt'] = raw['height_pt']
    if 'bounds' in raw:
        result['bounds'] = bounds(raw['bounds'])
    bands = raw.get('radius_bands_km', [])
    require(isinstance(bands, list) and len(bands) <= 12 and all(number(r) and 0 < r <= 20000 for r in bands),
            'radius_bands_km must contain at most 12 positive distances <= 20000 km')
    result['radius_bands_km'] = sorted(set(bands))
    if 'basemap' in raw:
        base = raw['basemap']
        require(isinstance(base, dict), 'basemap must be an object')
        require(base.get('crs') in ('EPSG:3857', 'EPSG:4326'), 'basemap needs EPSG:3857 or EPSG:4326 CRS')
        result['basemap'] = dict(path=str(local_path(root, base.get('path'))), bounds=bounds(base.get('bounds')),
                                 crs=base['crs'], attribution=text(base.get('attribution'), 'basemap attribution'))
        strip = base.get('credit_strip_px', 0)
        require(integer(strip), 'credit_strip_px must be a nonnegative integer')
        if strip:
            require(base.get('attribution_policy', 'preserve-bottom-strip') == 'preserve-bottom-strip',
                    'credit_strip_px requires preserve-bottom-strip policy')
            result['basemap'].update(credit_strip_px=strip, attribution_policy='preserve-bottom-strip')
        else:
            require(base.get('attribution_policy') == 'separate-caption' and base.get('overlay_safe') is True,
                    'basemap needs credit_strip_px, or attribution_policy=separate-caption with overlay_safe=true')
            result['basemap'].update(attribution_policy='separate-caption', overlay_safe=True)
    return result


def text_list(raw, name, required=False):
    value = raw.get(name, [])
    require(isinstance(value, list) and (bool(value) or not required), f'{name} must be a list of text')
    return [text(item, name) for item in value]


def load_config(path):
    path = Path(path).resolve()
    cfg = read_json(path)
    require(isinstance(cfg, dict), 'config must be an object')
    require(type(cfg.get('schema_version')) is int and cfg['schema_version'] == 1, 'schema_version must be 1')
    business = cfg.get('business')
    require(isinstance(business, dict), 'business must be an object')
    business = dict(name=text(business.get('name'), 'business.name'), location=text(business.get('location'), 'business.location'),
                    lat=business.get('lat'), lng=business.get('lng'))
    coordinates(business['lat'], business['lng'])
    center_kind = cfg.get('center_kind', 'business')
    require(center_kind in ('business', 'market'), 'center_kind must be business or market')
    center_label = text(cfg.get('center_label', business['name'] if center_kind == 'business' else None), 'center_label')
    require(type(cfg.get('synthetic', False)) is bool, 'synthetic must be boolean')
    result = dict(schema_version=1, synthetic=cfg.get('synthetic', False), business=business,
                  center_kind=center_kind, center_label=center_label,
                  thesis=text(cfg.get('thesis'), 'thesis'), objectives=text_list(cfg, 'objectives', True),
                  next_actions=text_list(cfg, 'next_actions'), missing_evidence=text_list(cfg, 'missing_evidence'), lanes=[])
    require(isinstance(cfg.get('map', {}), dict), 'map must be an object')
    if 'fonts' in cfg:
        require(isinstance(cfg['fonts'], dict), 'fonts must be an object')
        result['fonts'] = {k: str(local_path(path.parent, cfg['fonts'].get(k))) for k in ('regular', 'bold')}
        if 'title' in cfg['fonts']:
            result['fonts']['title'] = str(local_path(path.parent, cfg['fonts']['title']))
    lanes = cfg.get('lanes')
    require(isinstance(lanes, list) and lanes, 'lanes must be a nonempty list')
    ids = set()
    for lane in lanes:
        require(isinstance(lane, dict), 'lane must be an object')
        query_id = text(lane.get('query_id'), 'query_id')
        require(query_id not in ids, 'duplicate query_id')
        ids.add(query_id)
        current = dict(query_id=query_id, label=text(lane.get('label'), 'lane label'), query=text(lane.get('query'), 'lane query'))
        require(sum(key in lane for key in ('records', 'records_path', 'records_paths')) == 1,
                'lane needs exactly one of records, records_path, records_paths')
        if 'records' in lane:
            rows = lane['records']
        else:
            paths = lane.get('records_paths', [lane.get('records_path')])
            require(isinstance(paths, list) and paths, 'records_paths must be a nonempty list')
            rows = []
            for name in paths:
                payload = read_json(local_path(path.parent, name))
                if isinstance(payload, dict) and 'results' in payload:
                    selected = runner_records(payload, current, business)
                else:
                    selected = payload.get('observations') if isinstance(payload, dict) else payload
                    require(isinstance(selected, list), 'record file must contain a list, observations, or runner results')
                    require(all(isinstance(r, dict) and 'query_id' in r for r in selected), 'records need query_id')
                    selected = [r for r in selected if r['query_id'] == query_id]
                rows.extend(selected)
        require(isinstance(rows, list) and rows, f'lane {query_id} has no observations')
        records = [validate_observation(r, query_id) for r in rows]
        locations = [(r['lat'], r['lng']) for r in records]
        require(len(locations) == len(set(locations)), f'duplicate coordinates in lane {query_id}')
        current['records'] = records
        current['metrics'] = metrics(records)
        current['full_bounds'] = full_bounds(records, business)
        require(isinstance(lane.get('map', {}), dict), 'lane map must be an object')
        current['map'] = map_config({**cfg.get('map', {}), **lane.get('map', {})}, path.parent)
        current['map'].setdefault('bounds', current['full_bounds'])
        current['outside_view'] = sum(not inside(r, current['map']['bounds']) for r in records)
        current['needs_appendix'] = bool(current['outside_view'] or not inside(business, current['map']['bounds']))
        current['narrative'] = text(lane['narrative'], 'lane narrative') if 'narrative' in lane else None
        current['missing_evidence'] = []
        for key in ('sampled_at', 'depth', 'returned_count'):
            missing = sum(r[key] is None for r in records)
            if missing:
                current['missing_evidence'].append(f'{missing} origins have no {key}.')
        m = current['metrics']
        if m['excluded']:
            current['missing_evidence'].append(f"{m['excluded']} origins are empty, errored, or unmeasured; resolve these before comparing results.")
        for cutoff in (3, 10):
            unknown = m[f'top{cutoff}_unknown_absence']
            if unknown:
                current['missing_evidence'].append(f'{unknown} not-returned origins cannot establish absence in the top {cutoff}; the complete observed rank sequence is missing.')
        result['lanes'].append(current)
    supplied_sources = {r['source'] for lane in result['lanes'] for r in lane['records'] if r['source'].casefold() != 'unmeasured'}
    synthetic_sources = {s for s in supplied_sources if 'synthetic' in s.casefold()}
    require(not synthetic_sources or synthetic_sources == supplied_sources,
            'mixed synthetic and other sources are not supported; use separate reports')
    require(not result['synthetic'] or not supplied_sources or synthetic_sources == supplied_sources,
            'synthetic=true requires explicitly synthetic source labels; separate real or unknown evidence')
    result['synthetic'] = bool(result['synthetic'] or synthetic_sources)
    result['evidence_disclosure'] = (
        'Synthetic observations only; these are not real business findings.' if result['synthetic'] else
        'User-supplied evidence; this renderer does not independently authenticate source labels or origin records. '
        'Acquisition verification requires a separate review of the underlying evidence.')
    return result


def finding(lane):
    m = lane['metrics']
    if not m['measured']:
        return (f"No valid measured origins among {m['sampled']} supplied origins. "
                f"All {m['excluded']} origins are excluded. Top 3: 0 observed; top 10: 0 observed; "
                'near misses (ranks 4-10 inclusive): 0. Shares are undefined, not zero visibility.')
    return (f"Measured: {m['measured']}/{m['sampled']} origins; excluded: {m['excluded']}. "
            f"Found: {m['states']['found']}/{m['measured']}; top 3: {m['top3']}/{m['measured']}; "
            f"top 10: {m['top10']}/{m['measured']}. Near misses (ranks 4-10): {m['near_miss']}. "
            f"Unknown absence: top 3 = {m['top3_unknown_absence']}; top 10 = {m['top10_unknown_absence']}. "
            'Sampled origins only; not area coverage.')
