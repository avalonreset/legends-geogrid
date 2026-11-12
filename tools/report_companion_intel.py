#!/usr/bin/env python3
"""Compute Web Companion competitive intelligence for strategy reports.

Translates the Web Companion's five analytical lenses into structured report
data for PDF and HTML strategy reports:
1. Rankings & Distance-Ring Breakdown (Core 0-2 mi, 2-5 mi, 5-10 mi)
2. Local Leaders & Neighbor-Colored Territories (L-number badges, #1 clusters)
3. Competitive Field Leaderboard (all observed profiles sorted by Top-3 & Top-20 score)
4. Strategy Room Sector Matrix & Local Pressure Rivals (ahead at ranks 4-10)
5. Territory Campaigns, Researched Action Briefs & GBP Name-Review Dossier
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
import math
from pathlib import Path
from typing import Any

MILE_KM = 1.609344
FORBIDDEN_EM_DASH = '\u2014'
EN_DASH_CHAR = '\u2013'

# Deterministic neighbor-separated palette matching src/leader-colors.js & src/local-leaders.js
LEADER_PALETTE = [
    '#00E676', '#2979FF', '#FF9100', '#A855F7', '#FF1744',
    '#A3E635', '#FFDF00', '#00D4FF', '#FF6D00', '#EC4899',
    '#14B8A6', '#8B5CF6', '#F43F5E', '#84CC16', '#38BDF8',
    '#FB923C', '#C084FC', '#2DD4BF', '#FACC15', '#60A5FA',
]

CONFIDENCE_LABELS = [
    'Branding supports the title',
    'Weak concern',
    'Limited concern',
    'Moderate concern',
    'Strong concern',
    'Very strong concern',
]


def _clean(value: Any) -> str:
    if value is None:
        return ''
    return str(value).replace(FORBIDDEN_EM_DASH, ' - ').replace(EN_DASH_CHAR, '-')


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    rad = math.pi / 180.0
    dlat = (lat2 - lat1) * rad
    dlng = (lng2 - lng1) * rad
    h = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1 * rad) * math.cos(lat2 * rad) * math.sin(dlng / 2.0) ** 2
    )
    return 6371.0088 * 2.0 * math.asin(math.sqrt(min(1.0, max(0.0, h))))


def _safe_path(path: Path | str, allowed_roots: tuple[Path, ...] | None = None) -> Path:
    from local_heatmap_poc import _safe_local_path
    resolved = _safe_local_path(path).resolve()
    if allowed_roots:
        if not any(resolved.is_relative_to(_safe_local_path(root).resolve()) for root in allowed_roots):
            raise ValueError(f'Companion artifact path escapes allowed directories: {path}')
    return resolved


def _sanitize_companion_node(node: Any) -> Any:
    if isinstance(node, str):
        return _clean(node)
    if isinstance(node, bool):
        return node
    if isinstance(node, (int, float)):
        if math.isnan(node) or math.isinf(node):
            return 0
        return node
    if isinstance(node, list):
        return [_sanitize_companion_node(item) for item in node]
    if isinstance(node, dict):
        return {str(k): _sanitize_companion_node(v) for k, v in node.items()}
    return None


def _profile_id(item: dict[str, Any]) -> str | None:
    cid = str(item.get('cid') or '').strip()
    if cid:
        return f'cid:{cid}'
    pid = str(item.get('place_id') or item.get('placeId') or '').strip()
    if pid:
        return f'place:{pid}'
    fid = str(item.get('faction_id') or '').strip()
    if fid:
        return fid
    return None


def _compass_direction(dx: float, dy: float) -> str:
    if math.hypot(dx, dy) < 0.25:
        return 'Around the primary business'
    angle = (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0
    sectors = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    return f"{sectors[round(angle / 45.0) % 8]} of the primary business"


def _quadrant(dx: float, dy: float) -> str:
    return f"{'n' if dy >= 0 else 's'}{'e' if dx >= 0 else 'w'}"


def _median(values: list[int | float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    return float(s[mid]) if len(s) % 2 == 1 else (s[mid - 1] + s[mid]) / 2.0


def build_companion_intel(
    study_data: dict[str, Any],
    campaign_research: dict[str, Any] | None = None,
    name_review: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build the complete Web Companion intelligence bundle from geogrid-companion/v1 JSON."""
    if not isinstance(study_data, dict) or study_data.get('schema') != 'geogrid-companion/v1':
        return None

    target_raw = study_data.get('target') or {}
    target_cid = str(target_raw.get('cid') or study_data.get('business', {}).get('cid') or '').strip()
    target_id = f'cid:{target_cid}' if target_cid else 'TARGET'
    center_lat = float(target_raw.get('lat') or study_data.get('business', {}).get('lat') or 0.0)
    center_lng = float(target_raw.get('lng') or study_data.get('business', {}).get('lng') or 0.0)

    sampling = study_data.get('study', {}).get('sampling') or {}
    radius_km = float(sampling.get('radius_km') or 16.09344)
    spacing_km = float(sampling.get('spacing_km') or 0.804672)
    radius_miles = round(radius_km / MILE_KM, 2)
    spacing_miles = round(spacing_km / MILE_KM, 2)

    lanes = study_data.get('lanes') or []
    query_ids = [str(l['lane_id']) for l in lanes if isinstance(l, dict) and l.get('lane_id')]
    query_names = {str(l['lane_id']): _clean(l.get('query') or l.get('lane_id')) for l in lanes if isinstance(l, dict) and l.get('lane_id')}
    if not query_ids:
        return None

    # 1. Build unified businesses table from factions + profiles + point items
    businesses: dict[str, dict[str, Any]] = {}
    profiles_table = study_data.get('profiles') or {}

    def register_business(
        bid: str,
        name: str,
        cid: str | None = None,
        address: str | None = None,
        lat: float | None = None,
        lng: float | None = None,
        rating: float | None = None,
        votes_count: int | None = None,
        domain: str | None = None,
        is_target: bool = False,
    ) -> dict[str, Any]:
        entry = businesses.get(bid)
        if not entry:
            entry = {
                'id': bid,
                'cid': str(cid or '').strip() or None,
                'name': _clean(name or bid),
                'address': _clean(address or ''),
                'lat': float(lat) if isinstance(lat, (int, float)) and math.isfinite(lat) else None,
                'lng': float(lng) if isinstance(lng, (int, float)) and math.isfinite(lng) else None,
                'rating': float(rating) if isinstance(rating, (int, float)) and math.isfinite(rating) else None,
                'votes_count': int(votes_count) if isinstance(votes_count, (int, float)) and math.isfinite(votes_count) else None,
                'domain': _clean(domain or ''),
                'is_target': bool(is_target or (target_cid and str(cid or '').strip() == target_cid)),
            }
            businesses[bid] = entry
        else:
            if name and (not entry['name'] or entry['name'] == bid):
                entry['name'] = _clean(name)
            if address and not entry['address']:
                entry['address'] = _clean(address)
            if isinstance(lat, (int, float)) and math.isfinite(lat) and entry['lat'] is None:
                entry['lat'] = float(lat)
            if isinstance(lng, (int, float)) and math.isfinite(lng) and entry['lng'] is None:
                entry['lng'] = float(lng)
            if isinstance(rating, (int, float)) and math.isfinite(rating) and entry['rating'] is None:
                entry['rating'] = float(rating)
            if isinstance(votes_count, (int, float)) and math.isfinite(votes_count) and entry['votes_count'] is None:
                entry['votes_count'] = int(votes_count)
            if domain and not entry['domain']:
                entry['domain'] = _clean(domain)
            if is_target:
                entry['is_target'] = True
        return entry

    if target_cid:
        register_business(
            target_id,
            target_raw.get('name') or study_data.get('business', {}).get('name') or 'Target Business',
            cid=target_cid,
            address=target_raw.get('address') or study_data.get('business', {}).get('location'),
            lat=center_lat,
            lng=center_lng,
            rating=target_raw.get('rating'),
            votes_count=target_raw.get('votes_count'),
            domain=target_raw.get('domain') or study_data.get('business', {}).get('website'),
            is_target=True,
        )

    for f in study_data.get('factions') or []:
        fcid = str(f.get('cid') or '').strip()
        bid = target_id if f.get('is_target') else (f'cid:{fcid}' if fcid else str(f.get('faction_id') or ''))
        if not bid:
            continue
        register_business(
            bid,
            f.get('name') or bid,
            cid=fcid or None,
            address=f.get('address'),
            lat=f.get('lat'),
            lng=f.get('lng'),
            rating=f.get('rating'),
            votes_count=f.get('votes_count'),
            domain=f.get('domain'),
            is_target=bool(f.get('is_target')),
        )

    for cid_key, prof in profiles_table.items():
        if not isinstance(prof, dict):
            continue
        cid_str = str(prof.get('cid') or cid_key).strip()
        bid = target_id if (target_cid and cid_str == target_cid) else f'cid:{cid_str}'
        register_business(
            bid,
            prof.get('title') or prof.get('name') or bid,
            cid=cid_str,
            address=prof.get('address'),
            lat=prof.get('latitude') if prof.get('latitude') is not None else prof.get('lat'),
            lng=prof.get('longitude') if prof.get('longitude') is not None else prof.get('lng'),
            rating=prof.get('rating'),
            votes_count=prof.get('votes_count'),
            domain=prof.get('domain'),
            is_target=(target_cid != '' and cid_str == target_cid),
        )

    # 2. Parse points & observations across all queries
    raw_points = study_data.get('points') or []
    points: list[dict[str, Any]] = []
    step_deg_lat = spacing_km / 111.195 if spacing_km > 0 else 0.007236
    cos_lat = math.cos(math.radians(center_lat)) if abs(center_lat) < 85 else 1.0
    step_deg_lng = step_deg_lat / max(0.05, cos_lat)

    # Track per-business metrics across queries
    biz_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            'top3_total': 0,
            'top10_total': 0,
            'top20_total': 0,
            'found_total': 0,
            'rank1_total': 0,
            'visibility_score': 0,
            'rank_sum': 0,
            'rank_count': 0,
            'per_query': {
                qid: {'top3': 0, 'top10': 0, 'found': 0, 'rank1': 0, 'score': 0, 'near_ahead': 0}
                for qid in query_ids
            },
        }
    )

    complete_by_query = Counter()

    for idx, pt in enumerate(raw_points):
        lat = float(pt['lat'])
        lng = float(pt['lng'])
        tag = str(pt.get('tag') or f'p_{idx:04d}')
        dist_km = float(pt.get('distance_from_target_km') or haversine_km(center_lat, center_lng, lat, lng))
        dist_miles = dist_km / MILE_KM
        gx = round((lng - center_lng) / step_deg_lng) if step_deg_lng > 0 else 0
        gy = round((lat - center_lat) / step_deg_lat) if step_deg_lat > 0 else 0
        by_lane = pt.get('by_lane') or {}

        obs_by_q: dict[str, dict[str, Any]] = {}
        for qid in query_ids:
            lane_obs = by_lane.get(qid) or {}
            status = str(lane_obs.get('status') or '')
            raw_items = lane_obs.get('top_items') or []
            parsed_items: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            for item in raw_items:
                rank = item.get('rank') or item.get('rank_group')
                if not isinstance(rank, int) or rank < 1 or rank > 30:
                    continue
                cid_str = str(item.get('cid') or '').strip()
                prof = profiles_table.get(cid_str) if cid_str else None
                bid = (
                    target_id
                    if (target_cid and cid_str == target_cid) or item.get('faction_id') == 'TARGET'
                    else (f'cid:{cid_str}' if cid_str else _profile_id(item))
                )
                if not bid or bid in seen_ids:
                    continue
                seen_ids.add(bid)
                if bid not in businesses:
                    register_business(
                        bid,
                        (prof or item).get('title') or (prof or item).get('name') or bid,
                        cid=cid_str or None,
                        address=(prof or item).get('address'),
                        lat=(prof or item).get('latitude'),
                        lng=(prof or item).get('longitude'),
                        rating=(prof or item).get('rating'),
                        votes_count=(prof or item).get('votes_count'),
                        domain=(prof or item).get('domain'),
                    )
                parsed_items.append({'id': bid, 'rank': rank})

            parsed_items.sort(key=lambda x: x['rank'])
            complete = (
                status in ('found', 'not_returned_depth_reached')
                and len(parsed_items) == 30
            )
            target_rank = lane_obs.get('target_rank')
            if not isinstance(target_rank, int) or target_rank < 1 or target_rank > 30:
                target_rank = None

            if not complete:
                band = 'unknown'
            elif target_rank is None:
                band = 'outside30'
            elif target_rank <= 3:
                band = 'defend'
            elif target_rank <= 10:
                band = 'advance'
            else:
                band = 'build'

            winner_id = parsed_items[0]['id'] if parsed_items and parsed_items[0]['rank'] == 1 else None
            obs_by_q[qid] = {
                'status': status,
                'complete': complete,
                'target_rank': target_rank,
                'band': band,
                'winner_id': winner_id,
                'items': parsed_items,
            }

            if complete:
                complete_by_query[qid] += 1
                for it in parsed_items:
                    bid = it['id']
                    rk = it['rank']
                    st = biz_stats[bid]
                    qst = st['per_query'][qid]
                    st['found_total'] += 1
                    qst['found'] += 1
                    st['rank_sum'] += rk
                    st['rank_count'] += 1
                    if rk == 1:
                        st['rank1_total'] += 1
                        qst['rank1'] += 1
                    if rk <= 3:
                        st['top3_total'] += 1
                        qst['top3'] += 1
                    if rk <= 10:
                        st['top10_total'] += 1
                        qst['top10'] += 1
                    if rk <= 20:
                        st['top20_total'] += 1
                        pts_score = 21 - rk
                        st['visibility_score'] += pts_score
                        qst['score'] += pts_score
                    if target_rank is not None and 4 <= target_rank <= 10 and rk < target_rank and bid != target_id:
                        qst['near_ahead'] += 1

        # Determine service_gap per query (ranks 4-10 on qid while ranking 1-3 on another query)
        defend_queries = [q for q in query_ids if obs_by_q[q]['band'] == 'defend']
        for qid in query_ids:
            obs_by_q[qid]['service_gap'] = (
                obs_by_q[qid]['band'] == 'advance'
                and any(other != qid for other in defend_queries)
            )
            obs_by_q[qid]['supporting_queries'] = [q for q in defend_queries if q != qid]

        points.append({
            'id': tag,
            'lat': lat,
            'lng': lng,
            'x': gx,
            'y': gy,
            'distance_km': round(dist_km, 4),
            'distance_miles': round(dist_miles, 4),
            'observations': obs_by_q,
        })

    # Determine frontier per query (ranks 11-30 orthogonally adjacent to a top-10 cell)
    grid_lookup = {(p['x'], p['y']): p for p in points}
    for p in points:
        for qid in query_ids:
            o = p['observations'][qid]
            if o['band'] == 'build':
                o['frontier'] = any(
                    grid_lookup.get((p['x'] + dx, p['y'] + dy), {}).get('observations', {}).get(qid, {}).get('band') in ('defend', 'advance')
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                )
            else:
                o['frontier'] = False

    # 3. Assign study-wide L-number badges & neighbor-separated colors (matching src/leader-colors.js)
    winners_sorted = sorted(
        [bid for bid, st in biz_stats.items() if st['rank1_total'] > 0],
        key=lambda bid: (-biz_stats[bid]['rank1_total'], -biz_stats[bid]['top3_total'], bid),
    )
    identities: dict[str, dict[str, Any]] = {}
    for idx, bid in enumerate(winners_sorted, 1):
        identities[bid] = {
            'badge': f'L{idx:02d}',
            'color': '#00FFFF' if bid == target_id else LEADER_PALETTE[(idx - 1) % len(LEADER_PALETTE)],
            'rank1_total': biz_stats[bid]['rank1_total'],
        }
    if target_id not in identities:
        identities[target_id] = {'badge': 'YOU', 'color': '#00FFFF', 'rank1_total': 0}

    # 4. Build Local Leaders per query and pooled study-wide
    local_leaders_by_query: dict[str, Any] = {}
    for qid in query_ids:
        win_points_by_biz: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for p in points:
            wid = p['observations'][qid]['winner_id']
            if wid:
                win_points_by_biz[wid].append(p)

        rows = []
        for bid, wpts in win_points_by_biz.items():
            biz = businesses.get(bid)
            if not biz:
                continue
            wins = len(wpts)
            major = wins >= 3
            # Connected cluster centroid for badge placement
            center_pt = wpts[0]
            if len(wpts) > 1:
                mean_lat = sum(x['lat'] for x in wpts) / len(wpts)
                mean_lng = sum(x['lng'] for x in wpts) / len(wpts)
                center_pt = min(wpts, key=lambda x: haversine_km(mean_lat, mean_lng, x['lat'], x['lng']))
            has_base = biz['lat'] is not None and biz['lng'] is not None
            beyond_km = (
                haversine_km(center_lat, center_lng, biz['lat'], biz['lng']) - radius_km
                if has_base
                else None
            )
            ident = identities.get(bid, {'badge': '--', 'color': '#94A3B8'})
            rows.append({
                'id': bid,
                'cid': biz.get('cid'),
                'name': biz['name'],
                'address': biz['address'],
                'is_target': biz['is_target'],
                'badge': ident['badge'],
                'color': ident['color'],
                'wins': wins,
                'share_pct': round(100.0 * wins / max(1, len(points)), 1),
                'major': major,
                'center': {'lat': center_pt['lat'], 'lng': center_pt['lng']},
                'base': {'lat': biz['lat'], 'lng': biz['lng']} if has_base else None,
                'outside_radius': bool(beyond_km is not None and beyond_km > 0),
                'connector': bool(beyond_km is not None and beyond_km > 3.218688 and major),
            })
        rows.sort(key=lambda r: (-r['wins'], r['id']))
        major_ids = {r['id'] for r in rows if r['major']}
        local_leaders_by_query[qid] = {
            'query_id': qid,
            'query': query_names[qid],
            'recurring_count': len(major_ids),
            'all_winners_count': len(rows),
            'colored_points': sum(r['wins'] for r in rows if r['major']),
            'leaders': rows[:12],
        }

    # Study-wide pooled #1 winner per point (for the Sovereign Local Leaders Map)
    pooled_win_points: dict[str, list[dict[str, Any]]] = defaultdict(list)
    point_dominant_leaders: list[dict[str, Any]] = []
    for p in points:
        counts: Counter[str] = Counter()
        best_rank_by_w: dict[str, int] = {}
        for qid in query_ids:
            wid = p['observations'][qid]['winner_id']
            if wid:
                counts[wid] += 1
                best_rank_by_w[wid] = 1
        if counts:
            # Winner with most #1 wins at this coordinate across queries (tie-break: study-wide rank1_total)
            dom_id = max(
                counts.keys(),
                key=lambda wid: (counts[wid], biz_stats[wid]['rank1_total'], wid == target_id),
            )
            pooled_win_points[dom_id].append(p)
            ident = identities.get(dom_id, {'badge': '--', 'color': '#64748B'})
            major = any(
                 biz_stats[dom_id]['per_query'][q]['rank1'] >= 3 for q in query_ids
            )
            point_dominant_leaders.append({
                'lat': p['lat'],
                'lng': p['lng'],
                'winner_id': dom_id,
                'badge': ident['badge'],
                'color': ident['color'],
                'major': major,
                'queries_won': counts[dom_id],
            })
        else:
            point_dominant_leaders.append({
                'lat': p['lat'],
                'lng': p['lng'],
                'winner_id': None,
                'badge': '',
                'color': '#475569',
                'major': False,
                'queries_won': 0,
            })

    pooled_leader_rows = []
    for bid, st in biz_stats.items():
        if st['rank1_total'] <= 0:
            continue
        biz = businesses.get(bid)
        if not biz:
            continue
        recurring_any = any(st['per_query'][q]['rank1'] >= 3 for q in query_ids)
        ident = identities.get(bid, {'badge': '--', 'color': '#94A3B8'})
        wpts = pooled_win_points.get(bid) or []
        center_pt = None
        if wpts:
            mean_lat = sum(x['lat'] for x in wpts) / len(wpts)
            mean_lng = sum(x['lng'] for x in wpts) / len(wpts)
            c_pt = min(wpts, key=lambda x: haversine_km(mean_lat, mean_lng, x['lat'], x['lng']))
            center_pt = {'lat': c_pt['lat'], 'lng': c_pt['lng']}
        pooled_leader_rows.append({
            'id': bid,
            'cid': biz.get('cid'),
            'name': biz['name'],
            'address': biz['address'],
            'is_target': biz['is_target'],
            'badge': ident['badge'],
            'color': ident['color'],
            'rank1_total': st['rank1_total'],
            'top3_total': st['top3_total'],
            'dominant_origins': len(wpts),
            'share_of_first_place_pct': round(100.0 * st['rank1_total'] / max(1, sum(complete_by_query.values())), 1),
            'recurring': recurring_any,
            'per_query_rank1': {q: st['per_query'][q]['rank1'] for q in query_ids},
            'lat': biz.get('lat'),
            'lng': biz.get('lng'),
            'center': center_pt,
        })
    pooled_leader_rows.sort(key=lambda r: (-r['rank1_total'], -r['top3_total'], r['id']))

    # 5. Competitive Field Leaderboard (all observed profiles sorted by equal-query top-3 coverage, then top-20 visibility score)
    all_leaderboard = []
    valid_queries = [q for q in query_ids if complete_by_query[q] > 0]
    for bid, st in biz_stats.items():
        biz = businesses.get(bid)
        if not biz:
            continue
        q_top3_pcts = [
            100.0 * st['per_query'][q]['top3'] / complete_by_query[q]
            for q in valid_queries
        ]
        top3_cov_pct = sum(q_top3_pcts) / len(q_top3_pcts) if q_top3_pcts else 0.0
        ident = identities.get(bid, {'badge': 'YOU' if biz['is_target'] else '--', 'color': '#00FFFF' if biz['is_target'] else '#64748B'})
        all_leaderboard.append({
            'id': bid,
            'cid': biz.get('cid'),
            'name': biz['name'],
            'address': biz['address'],
            'is_target': biz['is_target'],
            'badge': ident['badge'],
            'color': ident['color'],
            'rating': biz['rating'],
            'votes_count': biz['votes_count'],
            'top3_coverage_pct': round(top3_cov_pct, 2),
            'top3_total': st['top3_total'],
            'top10_total': st['top10_total'],
            'rank1_total': st['rank1_total'],
            'found_total': st['found_total'],
            'visibility_score': st['visibility_score'],
            'avg_rank': round(st['rank_sum'] / st['rank_count'], 1) if st['rank_count'] else None,
            'per_query_top3': {q: st['per_query'][q]['top3'] for q in query_ids},
            'per_query_top10': {q: st['per_query'][q]['top10'] for q in query_ids},
            'near_ahead_total': sum(st['per_query'][q]['near_ahead'] for q in query_ids),
        })

    all_leaderboard.sort(
        key=lambda r: (-r['top3_coverage_pct'], -r['visibility_score'], -r['top3_total'], r['id'])
    )
    for pos, row in enumerate(all_leaderboard, 1):
        row['standing'] = pos

    target_standing = next((r for r in all_leaderboard if r['is_target']), None)
    top_leaderboard = all_leaderboard[:15]
    if target_standing and not any(r['is_target'] for r in top_leaderboard):
        top_leaderboard = all_leaderboard[:14] + [target_standing]

    # 6. Strategy Room Reach Matrix (Core 0-2 mi, 2-5 mi, 5-10 mi + NE/SE/SW/NW sectors)
    region_defs = [
        ('all', 'Whole Study (0-10 mi)', lambda p: True),
        ('core', 'Core (0-2 mi)', lambda p: p['distance_miles'] <= 2.0),
        ('inner', 'Inner Ring (2-5 mi)', lambda p: 2.0 < p['distance_miles'] <= 5.0),
        ('outer', f'Outer Ring (5-{radius_miles:g} mi)', lambda p: p['distance_miles'] > 5.0),
    ]
    for band_name, low_m, high_m in (('inner', 2.0, 5.0), ('outer', 5.0, radius_miles)):
        if radius_miles <= low_m:
            continue
        for comp in ('ne', 'se', 'sw', 'nw'):
            region_defs.append((
                f'{band_name}-{comp}',
                f'{comp.upper()} ({low_m:g}-{min(high_m, radius_miles):g} mi)',
                lambda p, b=band_name, c=comp, lo=low_m, hi=high_m: (
                    lo < p['distance_miles'] <= hi and _quadrant(p['x'], p['y']) == c
                ),
            ))

    strategy_regions = []
    for reg_id, reg_label, pred in region_defs:
        reg_pts = [p for p in points if pred(p)]
        per_q = {}
        for qid in query_ids:
            comp = sum(1 for p in reg_pts if p['observations'][qid]['complete'])
            t3 = sum(1 for p in reg_pts if p['observations'][qid]['band'] == 'defend')
            near = sum(1 for p in reg_pts if p['observations'][qid]['band'] == 'advance')
            t10 = t3 + near
            bld = sum(1 for p in reg_pts if p['observations'][qid]['band'] == 'build')
            out30 = sum(1 for p in reg_pts if p['observations'][qid]['band'] == 'outside30')
            sgap = sum(1 for p in reg_pts if p['observations'][qid]['service_gap'])
            front = sum(1 for p in reg_pts if p['observations'][qid]['frontier'])
            per_q[qid] = {
                'complete': comp,
                'top3': t3,
                'top3_pct': round(100.0 * t3 / comp, 1) if comp else 0.0,
                'near': near,
                'top10': t10,
                'top10_pct': round(100.0 * t10 / comp, 1) if comp else 0.0,
                'build': bld,
                'outside30': out30,
                'service_gap': sgap,
                'frontier': front,
            }
        strategy_regions.append({
            'id': reg_id,
            'label': reg_label,
            'count': len(reg_pts),
            'per_query': per_q,
        })

    # Local pressure rivals (who ranks ahead of the primary at its ranks 4-10 near-miss locations)
    total_near_denominator = sum(
        sum(1 for p in points if p['observations'][q]['band'] == 'advance')
        for q in query_ids
    )
    pressure_rivals = sorted(
        [r for r in all_leaderboard if not r['is_target'] and r['near_ahead_total'] > 0],
        key=lambda r: (-r['near_ahead_total'], -r['top3_total'], r['id']),
    )[:8]
    for r in pressure_rivals:
        r['near_ahead_pct'] = round(100.0 * r['near_ahead_total'] / max(1, total_near_denominator), 1)

    # Core top-3 concentration
    all_reg = next(r for r in strategy_regions if r['id'] == 'all')
    core_reg = next(r for r in strategy_regions if r['id'] == 'core')
    total_top3_obs = sum(all_reg['per_query'][q]['top3'] for q in query_ids)
    core_top3_obs = sum(core_reg['per_query'][q]['top3'] for q in query_ids)
    core_concentration_pct = round(100.0 * core_top3_obs / total_top3_obs, 1) if total_top3_obs else 0.0

    # 7. Territory Campaigns & Researched Action Briefs
    campaigns_by_query: dict[str, Any] = {}
    for qid in query_ids:
        # Connected advance (ranks 4-10) and defend (ranks 1-3) and frontier clusters
        band_counts = Counter(p['observations'][qid]['band'] for p in points)
        sgap_count = sum(1 for p in points if p['observations'][qid]['service_gap'])
        front_count = sum(1 for p in points if p['observations'][qid]['frontier'])

        # Top rivals ahead in the advance (ranks 4-10) zone for this query
        advance_pts = [p for p in points if p['observations'][qid]['band'] == 'advance']
        ahead_counter: Counter[str] = Counter()
        for p in advance_pts:
            trk = p['observations'][qid]['target_rank'] or 99
            for it in p['observations'][qid]['items']:
                if it['id'] != target_id and it['rank'] < trk and it['rank'] <= 3:
                    ahead_counter[it['id']] += 1
        top_blockers = []
        for bid, cnt in ahead_counter.most_common(4):
            biz = businesses.get(bid)
            ident = identities.get(bid, {'badge': '--', 'color': '#94A3B8'})
            if biz:
                top_blockers.append({
                    'id': bid,
                    'badge': ident['badge'],
                    'color': ident['color'],
                    'name': biz['name'],
                    'address': biz['address'],
                    'count': cnt,
                    'denominator': len(advance_pts),
                })

        q_research = (campaign_research or {}).get('queries', {}).get(qid) if isinstance(campaign_research, dict) else None
        action_brief = None
        if isinstance(q_research, dict) and isinstance(q_research.get('actionBrief'), dict):
            ab = q_research['actionBrief']
            action_brief = {
                'area': _clean(q_research.get('area') or ''),
                'hypothesis': _clean(q_research.get('hypothesis') or ''),
                'checked_facts': [_clean(f) for f in (q_research.get('checkedWebsiteFacts') or [])[:3]],
                'title': _clean(ab.get('title') or ''),
                'observed': _clean(ab.get('observed') or ''),
                'action': _clean(ab.get('action') or ''),
                'reason': _clean(ab.get('reason') or ''),
                'next_checks': [_clean(c) for c in (ab.get('nextChecks') or q_research.get('nextChecks') or [])[:3]],
                'success': _clean(ab.get('success') or q_research.get('success') or ''),
                'readiness': _clean(ab.get('readiness') or ''),
                'existing_url': _clean(ab.get('existingUrl') or ''),
            }

        campaigns_by_query[qid] = {
            'query_id': qid,
            'query': query_names[qid],
            'counts': {
                'defend': band_counts.get('defend', 0),
                'advance': band_counts.get('advance', 0),
                'build': band_counts.get('build', 0),
                'outside30': band_counts.get('outside30', 0),
                'unknown': band_counts.get('unknown', 0),
                'service_gap': sgap_count,
                'frontier': front_count,
            },
            'top_blockers': top_blockers,
            'action_brief': action_brief,
        }

    campaign_plans = []
    if isinstance(campaign_research, dict) and isinstance(campaign_research.get('campaignPlans'), list):
        for plan in campaign_research['campaignPlans']:
            if not isinstance(plan, dict) or not plan.get('title'):
                continue
            campaign_plans.append({
                'id': _clean(plan.get('id') or ''),
                'title': _clean(plan.get('title') or ''),
                'area': _clean(plan.get('area') or ''),
                'stage': _clean(plan.get('stage') or ''),
                'baseline_query': _clean(plan.get('baselineQuery') or ''),
                'baseline_lens': _clean(plan.get('baselineLens') or ''),
                'goal': _clean(plan.get('goal') or ''),
                'evidence': _clean(plan.get('evidence') or ''),
                'steps': [_clean(s) for s in (plan.get('steps') or [])[:4]],
                'gate': _clean(plan.get('gate') or ''),
                'measure': _clean(plan.get('measure') or ''),
                'boundary': _clean(plan.get('boundary') or ''),
            })

    # 8. Keyword Stuffing / Business-Name Review Dossier
    name_review_bundle = None
    if isinstance(name_review, dict) and name_review.get('schema') == 'geogrid-name-review/v1':
        cases = name_review.get('cases') or []
        priority_cases = [
            c for c in cases
            if isinstance(c, dict) and (
                bool(c.get('historical_report'))
                or any(int(v or 0) >= 3 for v in (c.get('wins_by_query') or {}).values())
            )
        ]

        def _bracket(c: dict[str, Any]) -> str:
            conf = c.get('confidence')
            if isinstance(conf, dict):
                cb = str(conf.get('bracket') or '')
                if cb in ('supported_concern', 'possible_concern', 'name_supported', 'insufficient_evidence', 'not_investigated'):
                    return cb
                lvl = conf.get('level')
                if isinstance(lvl, int):
                    if lvl >= 4:
                        return 'supported_concern'
                    if lvl >= 2:
                        return 'possible_concern'
                    if lvl == 0:
                        return 'name_supported'
                    return 'insufficient_evidence'
            sr = c.get('source_review')
            if not isinstance(sr, dict):
                return 'not_investigated'
            b = str(sr.get('bracket') or '')
            if b in ('supported_concern', 'possible_concern', 'name_supported', 'insufficient_evidence', 'not_investigated'):
                return b
            if c.get('status') == 'corroborated_discrepancy':
                return 'supported_concern'
            if c.get('status') == 'branding_consistent':
                return 'name_supported'
            return 'insufficient_evidence'

        bracket_counts = Counter(_bracket(c) for c in priority_cases)
        flagged_rows = []
        for c in priority_cases:
            brk = _bracket(c)
            if brk not in ('supported_concern', 'possible_concern'):
                continue
            cid_str = str(c.get('cid') or '').strip()
            bid = f'cid:{cid_str}' if cid_str else str(c.get('id') or '')
            ident = identities.get(bid, {'badge': '--', 'color': '#94A3B8'})
            conf = c.get('confidence') if isinstance(c.get('confidence'), dict) else {}
            lvl = conf.get('level') if isinstance(conf.get('level'), int) and 0 <= conf.get('level') <= 5 else None
            sr = c.get('source_review') if isinstance(c.get('source_review'), dict) else {}
            site = c.get('website_evidence') if isinstance(c.get('website_evidence'), dict) else {}
            site_names = [
                _clean(n.get('name'))
                for n in (site.get('names') or [])
                if isinstance(n, dict) and n.get('name')
                and _clean(n.get('name')).lower() not in ('mysite', 'home', 'welcome', 'menu', 'order online')
                and '_' not in _clean(n.get('name'))
                and 'logo' not in _clean(n.get('name')).lower()
                and not ('-' in _clean(n.get('name')) and ' ' not in _clean(n.get('name')))
            ]
            if not site_names and site.get('title'):
                raw_title = _clean(str(site.get('title') or ''))
                for sep in ('|', '::', '–', ' - ', ' — '):
                    if sep in raw_title:
                        segs = [s.strip() for s in raw_title.split(sep) if s.strip() and s.strip().lower() not in ('home', 'welcome', 'mysite', 'menu', 'order online')]
                        if segs:
                            raw_title = segs[0]
                            break
                if raw_title and raw_title.lower() not in ('mysite', 'home', 'welcome', 'menu', 'order online'):
                    site_names.append(raw_title)
            # Deduplicate site names while preserving order
            dedup_site_names: list[str] = []
            for sn in site_names:
                if sn and sn not in dedup_site_names:
                    dedup_site_names.append(sn)
            prof = c.get('profile') if isinstance(c.get('profile'), dict) else {}
            jev = prof.get('jev_optical') if isinstance(prof.get('jev_optical'), dict) else None
            jev_verdict = ''
            if jev and jev.get('verdict'):
                vmap = {
                    'supports_full_title': 'Supports full title',
                    'omits_suspect_terms': 'Signage omits suspect terms',
                    'obstructed_or_no_sign': 'Sign obstructed or not visible',
                }
                jev_verdict = vmap.get(str(jev['verdict']), _clean(jev['verdict']))

            flagged_rows.append({
                'id': bid,
                'cid': cid_str,
                'badge': ident['badge'],
                'color': ident['color'],
                'name': _clean((prof.get('name') or c.get('name') or '')),
                'address': _clean(c.get('address') or ''),
                'bracket': brk,
                'bracket_label': 'Supported concern' if brk == 'supported_concern' else 'Possible concern',
                'confidence_level': lvl,
                'confidence_label': CONFIDENCE_LABELS[lvl] if lvl is not None else 'Reviewed',
                'confidence_rationale': _clean(conf.get('rationale') or ''),
                'suspect_terms': [_clean(t) for t in (sr.get('suspect_terms') or [])[:6]],
                'website_brands': dedup_site_names[:2],
                'total_wins': int(c.get('total_wins') or 0),
                'wins_by_query': {k: int(v or 0) for k, v in (c.get('wins_by_query') or {}).items()},
                'jev_verdict': jev_verdict,
                'finding': _clean(sr.get('finding') or c.get('assessment') or ''),
                'counterevidence': _clean(sr.get('counterevidence') or ''),
            })

        flagged_rows.sort(
            key=lambda r: (
                0 if r['bracket'] == 'supported_concern' else 1,
                -(r['confidence_level'] if r['confidence_level'] is not None else -1),
                -r['total_wins'],
                r['id'],
            )
        )
        reviewed_in_scope = sum(1 for c in priority_cases if isinstance(c.get('source_review'), dict))
        name_review_bundle = {
            'policy_url': _clean((name_review.get('policy') or {}).get('url') or 'https://support.google.com/business/answer/3038177'),
            'policy_summary': _clean((name_review.get('policy') or {}).get('summary') or ''),
            'total_in_scope': len(priority_cases),
            'analyst_reviewed': reviewed_in_scope,
            'supported_concerns': bracket_counts.get('supported_concern', 0),
            'possible_concerns': bracket_counts.get('possible_concern', 0),
            'names_supported': bracket_counts.get('name_supported', 0),
            'unresolved': bracket_counts.get('insufficient_evidence', 0),
            'pending': bracket_counts.get('not_investigated', 0),
            'flagged_cases': flagged_rows,
        }

    return {
        'schema': 'geogrid-report-companion-intel/v1',
        'summary': {
            'total_origins': len(points),
            'total_queries': len(query_ids),
            'total_observed_profiles': len(businesses),
            'recurring_leaders_count': sum(1 for r in pooled_leader_rows if r['recurring']),
            'all_winners_count': len(pooled_leader_rows),
            'radius_miles': radius_miles,
            'spacing_miles': spacing_miles,
            'core_top3_concentration_pct': core_concentration_pct,
            'near_miss_denominator': total_near_denominator,
        },
        'queries': [{'id': q, 'query': query_names[q]} for q in query_ids],
        'target_standing': target_standing,
        'leaderboard': top_leaderboard,
        'pressure_rivals': pressure_rivals,
        'pooled_leaders': pooled_leader_rows[:18],
        'local_leaders_by_query': local_leaders_by_query,
        'leaders_map_points': point_dominant_leaders,
        'strategy_regions': strategy_regions,
        'campaigns_by_query': campaigns_by_query,
        'campaign_plans': campaign_plans,
        'campaign_summary': _clean((campaign_research or {}).get('summary') or '') if isinstance(campaign_research, dict) else '',
        'campaign_recommendation': _clean((campaign_research or {}).get('recommendation') or '') if isinstance(campaign_research, dict) else '',
        'name_review': name_review_bundle,
    }


def load_companion_intel_for_config(cfg: dict[str, Any], config_dir: Path) -> dict[str, Any] | None:
    """Resolve optional or auto-discovered Web Companion artifacts for a report config."""
    if isinstance(cfg.get('companion_intel'), dict) and cfg['companion_intel'].get('schema') == 'geogrid-report-companion-intel/v1':
        sanitized = _sanitize_companion_node(cfg['companion_intel'])
        return sanitized if isinstance(sanitized, dict) and isinstance(sanitized.get('summary'), dict) else None

    repo_root = Path(__file__).resolve().parents[1]
    allowed_roots = (config_dir, repo_root)
    study_path: Path | None = None
    research_path: Path | None = None
    name_review_path: Path | None = None

    if cfg.get('companion_study_path'):
        study_path = _safe_path(config_dir / str(cfg['companion_study_path']), allowed_roots)
    elif (config_dir / 'companion-study.json').exists():
        study_path = _safe_path(config_dir / 'companion-study.json', allowed_roots)
    elif (
        not cfg.get('synthetic', True)
        and str(cfg.get('business', {}).get('name') or '') == 'Home Slice Pizza'
        and len(cfg.get('lanes') or []) == 4
        and len(cfg['lanes'][0].get('records') or []) == 1249
    ):
        starter_study = repo_root / 'src' / 'data' / 'home-slice-study.json'
        if starter_study.exists():
            study_path = _safe_path(starter_study, allowed_roots)
            starter_research = repo_root / 'src' / 'data' / 'home-slice-campaign-research.json'
            starter_nr = repo_root / 'src' / 'data' / 'home-slice-name-review.json'
            if starter_research.exists():
                research_path = _safe_path(starter_research, allowed_roots)
            if starter_nr.exists():
                name_review_path = _safe_path(starter_nr, allowed_roots)

    if not study_path or not study_path.is_file():
        return None

    if cfg.get('campaign_research_path'):
        research_path = _safe_path(config_dir / str(cfg['campaign_research_path']), allowed_roots)
    elif not research_path and (config_dir / 'campaign-research.json').exists():
        research_path = _safe_path(config_dir / 'campaign-research.json', allowed_roots)

    if cfg.get('name_review_path'):
        name_review_path = _safe_path(config_dir / str(cfg['name_review_path']), allowed_roots)
    elif not name_review_path and (config_dir / 'name-review.json').exists():
        name_review_path = _safe_path(config_dir / 'name-review.json', allowed_roots)

    study_data = json.loads(study_path.read_text(encoding='utf-8-sig'))
    research_data = json.loads(research_path.read_text(encoding='utf-8-sig')) if research_path and research_path.is_file() else None
    nr_data = json.loads(name_review_path.read_text(encoding='utf-8-sig')) if name_review_path and name_review_path.is_file() else None
    return build_companion_intel(study_data, research_data, nr_data)
