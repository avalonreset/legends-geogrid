#!/usr/bin/env python3
"""Executive-ready printable Letter PDF and HTML renderer for geogrid-battlefield/v1.

Renders high-resolution (3x scale = 1548x1140 px for 516x380 pt frames) tactical
cartography figures alongside a 4-page Letter PDF (battlefield-report.pdf) and
matching printable HTML (battlefield-report.html).
"""
from __future__ import annotations

import argparse
from html import escape
import json
import math
from pathlib import Path
import sys
from typing import Any

from report_design import (
    BRAND_BOTTOM,
    BRAND_TOP,
    COLUMN,
    DESIGN_VERSION,
    MARGIN,
    PAGE_H,
    PAGE_W,
    THEMES,
    add_pdf_brand_links,
    html_styles,
    legends_font,
    prepare_banner,
    prepare_html_font,
)

DEFAULT_THEME = 'geogrid'
THEME_FONTS = Path(__file__).resolve().parent / 'fonts'
MAP_W, MAP_H, SCALE = 516, 380, 3

FORBIDDEN_EM_DASH = chr(0x2014)
EN_DASH_CHAR = chr(0x2013)

TACTICAL_CLASSES = (
    ('PRIME_STRIKE_ZONE', 'Prime Strike Zone', '#F59E0B', '#000000'),
    ('FLANKING_MINE', 'Flanking Mine', '#06B6D4', '#000000'),
    ('OWNED_STRONGHOLD', 'Owned Stronghold', '#10B981', '#000000'),
    ('CONTESTED_FRONT', 'Contested Front', '#EAB308', '#000000'),
    ('ENEMY_FORTRESS', 'Enemy Fortress', '#EF4444', '#FFFFFF'),
)

TACTICAL_CLASS_MAP = {k: (label, fill, ink) for k, label, fill, ink in TACTICAL_CLASSES}

DEFAULT_FACTION_PALETTE = {
    'TARGET': '#10B981',
    'YOU': '#10B981',
    'F01': '#3B82F6',
    'R01': '#3B82F6',
    'F02': '#8B5CF6',
    'R02': '#8B5CF6',
    'F03': '#EC4899',
    'R03': '#EC4899',
    'F04': '#F97316',
    'R04': '#F97316',
    'F05': '#06B6D4',
    'R05': '#06B6D4',
    'F06': '#EAB308',
    'R06': '#EAB308',
    'F07': '#14B8A6',
    'R07': '#14B8A6',
    'F08': '#F43F5E',
    'R08': '#F43F5E',
    'F09': '#A855F7',
    'R09': '#A855F7',
    'F10': '#64748B',
    'R10': '#64748B',
}


def clean_text(value: Any, fallback: str = '') -> str:
    """Sanitize any string to guarantee zero em dashes or control characters."""
    if value is None:
        return fallback
    text = str(value)
    text = text.replace(FORBIDDEN_EM_DASH, ' - ').replace(EN_DASH_CHAR, '-')
    return text.strip() or fallback


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        v = float(value)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def hex_to_rgb(hex_str: str, fallback: tuple[int, int, int] = (100, 116, 139)) -> tuple[int, int, int]:
    s = clean_text(hex_str, '').lstrip('#')
    if len(s) == 3:
        s = ''.join(c * 2 for c in s)
    if len(s) >= 6:
        try:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
        except ValueError:
            return fallback
    return fallback


def mercator(lat: float) -> float:
    clamped = max(-85.0, min(85.0, float(lat)))
    return math.log(math.tan(math.pi / 4.0 + math.radians(clamped) / 2.0))


def unmercator(y: float) -> float:
    return math.degrees(2.0 * math.atan(math.exp(y)) - math.pi / 2.0)


def destination(lat: float, lng: float, km: float, bearing_deg: float) -> tuple[float, float]:
    distance = km / 6371.0088
    a, b, theta = math.radians(lat), math.radians(lng), math.radians(bearing_deg)
    sin_lat = math.sin(a) * math.cos(distance) + math.cos(a) * math.sin(distance) * math.cos(theta)
    sin_lat = max(-1.0, min(1.0, sin_lat))
    target_lat = math.asin(sin_lat)
    target_lng = b + math.atan2(
        math.sin(theta) * math.sin(distance) * math.cos(a),
        math.cos(distance) - math.sin(a) * math.sin(target_lat),
    )
    return math.degrees(target_lat), (math.degrees(target_lng) + 180.0) % 360.0 - 180.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2.0 * r * math.asin(min(1.0, math.sqrt(max(0.0, a))))


class ViewportProjection:
    """North-up Web Mercator projection into a pixel sub-rectangle."""

    def __init__(self, bounds: list[float], rect: tuple[int, int, int, int], pad_px: int = 36 * SCALE):
        self.bounds = bounds
        w, s, e, n = bounds
        self.rect = rect
        rx0, ry0, rx1, ry1 = rect
        rw = max(1, rx1 - rx0)
        rh = max(1, ry1 - ry0)
        self.x0, self.x1 = math.radians(w), math.radians(e)
        self.y0, self.y1 = mercator(s), mercator(n)
        dx = max(1e-7, self.x1 - self.x0)
        dy = max(1e-7, self.y1 - self.y0)
        usable_w = max(10, rw - 2 * pad_px)
        usable_h = max(10, rh - 2 * pad_px)
        self.scale = min(usable_w / dx, usable_h / dy)
        self.left = rx0 + (rw - self.scale * dx) / 2.0
        self.top = ry0 + (rh - self.scale * dy) / 2.0
        self.right = rx1 - (rw - self.scale * dx) / 2.0
        self.bottom = ry1 - (rh - self.scale * dy) / 2.0

    def point(self, lat: float, lng: float) -> tuple[float, float]:
        x = self.left + (math.radians(lng) - self.x0) * self.scale
        y = self.top + (self.y1 - mercator(lat)) * self.scale
        return (x, y)

    def inside_bounds(self, lat: float, lng: float, margin_ratio: float = 0.05) -> bool:
        w, s, e, n = self.bounds
        dlng = (e - w) * margin_ratio
        dlat = (n - s) * margin_ratio
        return (w - dlng) <= lng <= (e + dlng) and (s - dlat) <= lat <= (n + dlat)


def register_report_fonts() -> dict[str, str]:
    """Register Inter + JetBrainsMono (or GEOGRID_LEGENDS_FONT override) with ReportLab."""
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    rl_fonts = Path(reportlab.__file__).parent / 'fonts'
    vera_reg = str(rl_fonts / 'Vera.ttf')
    vera_bold = str(rl_fonts / 'VeraBd.ttf')

    inter_reg = THEME_FONTS / 'Inter-Regular.ttf'
    inter_bold = THEME_FONTS / 'Inter-SemiBold.ttf'
    jb_mono = THEME_FONTS / 'JetBrainsMono-Medium.ttf'

    paths = {
        'regular': str(inter_reg if inter_reg.is_file() else vera_reg),
        'bold': str(inter_bold if inter_bold.is_file() else vera_bold),
        'title': str(inter_bold if inter_bold.is_file() else vera_bold),
        'mono': str(jb_mono if jb_mono.is_file() else (inter_reg if inter_reg.is_file() else vera_reg)),
    }
    custom = legends_font()
    if custom:
        paths = {k: str(custom) for k in ('regular', 'bold', 'title', 'mono')}

    for key, font_name in (
        ('regular', 'ReportBody'),
        ('bold', 'ReportBold'),
        ('title', 'ReportTitle'),
        ('mono', 'ReportMono'),
    ):
        pdfmetrics.registerFont(TTFont(font_name, paths[key]))
    pdfmetrics.registerFontFamily(
        'ReportBody',
        normal='ReportBody',
        bold='ReportBold',
        italic='ReportBody',
        boldItalic='ReportBold',
    )
    return paths


def normalize_battlefield_model(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize any geogrid-battlefield/v1 model dict into a canonical structure."""
    if not isinstance(raw, dict):
        raise ValueError('battlefield model must be a JSON object')

    study = raw.get('study') or raw.get('meta') or raw.get('grid') or {}
    if not isinstance(study, dict):
        study = {}

    factions_raw = raw.get('factions') or raw.get('leaderboard') or raw.get('competitors') or []
    factions: list[dict[str, Any]] = []
    target_from_factions = None

    for idx, f in enumerate(factions_raw):
        if not isinstance(f, dict):
            continue
        fid = clean_text(f.get('faction_id') or f.get('id'), f'F{idx:02d}')
        is_target = bool(f.get('is_target')) or fid in ('TARGET', 'YOU', 'F00') or f.get('short_code') == 'YOU'
        short_code = clean_text(
            f.get('short_code') or f.get('code'),
            'YOU' if is_target else (f'R{idx:02d}' if not fid.startswith('R') else fid),
        )
        if not is_target and short_code == 'YOU':
            short_code = f'R{idx:02d}'
        color = clean_text(
            f.get('color'),
            DEFAULT_FACTION_PALETTE.get(fid) or DEFAULT_FACTION_PALETTE.get(short_code) or '#64748B',
        )
        avg_rank_val = f.get('average_rank', f.get('avg_rank'))
        avg_rank = round(float(avg_rank_val), 2) if avg_rank_val is not None and safe_float(avg_rank_val, -1) > 0 else None
        votes_val = f.get('votes_count', f.get('reviews', f.get('review_count')))
        votes_count = safe_int(votes_val, 0) if votes_val is not None else None
        rating_val = f.get('rating')
        rating = round(float(rating_val), 1) if rating_val is not None and safe_float(rating_val, -1) > 0 else None

        lat_val = f.get('lat', f.get('latitude'))
        lng_val = f.get('lng', f.get('longitude'))
        has_coords = lat_val is not None and lng_val is not None

        reach_val = f.get('gravity_radius_km', f.get('reach_km', f.get('max_top3_distance_km', 0.0)))
        norm_f = {
            'faction_id': 'TARGET' if is_target else fid,
            'short_code': 'YOU' if is_target else short_code,
            'is_target': is_target,
            'rank_order': 0 if is_target else safe_int(f.get('rank_order', idx), idx),
            'name': clean_text(f.get('name') or f.get('title') or f.get('business_name'), f'Faction {short_code}'),
            'archetype': clean_text(f.get('archetype'), 'COMMANDER' if is_target else 'LOCAL_OUTPOST'),
            'threat_level': clean_text(f.get('threat_level'), 'SELF' if is_target else 'MODERATE'),
            'solv_pct': round(safe_float(f.get('solv_pct', f.get('solv', 0.0))), 1),
            'visible_pct': round(safe_float(f.get('visible_pct', 0.0)), 1),
            'top1_count': safe_int(f.get('top1_count', 0)),
            'top3_count': safe_int(f.get('top3_count', f.get('top3', 0))),
            'top10_count': safe_int(f.get('top10_count', f.get('top10', 0))),
            'found_count': safe_int(f.get('found_count', 0)),
            'total_slots': safe_int(f.get('total_slots', 0)),
            'average_rank': avg_rank,
            'votes_count': votes_count,
            'rating': rating,
            'category': clean_text(f.get('category') or f.get('primary_category'), 'Local Business'),
            'additional_categories': [clean_text(c) for c in (f.get('additional_categories') or []) if clean_text(c)],
            'domain': clean_text(f.get('domain') or f.get('website'), ''),
            'lat': safe_float(lat_val) if has_coords else None,
            'lng': safe_float(lng_val) if has_coords else None,
            'gravity_radius_km': round(safe_float(reach_val, 0.0), 2),
            'max_top3_distance_km': round(safe_float(f.get('max_top3_distance_km', reach_val), 0.0), 2),
            'primary_vulnerability': clean_text(
                f.get('primary_vulnerability'),
                'Command citadel baseline; expand outer-ring authority' if is_target else 'Standard proximity decay outside core radius',
            ),
            'color': color,
            'lane_stats': f.get('lane_stats') if isinstance(f.get('lane_stats'), dict) else {},
        }
        factions.append(norm_f)
        if is_target and target_from_factions is None:
            target_from_factions = norm_f

    target_raw = raw.get('target') if isinstance(raw.get('target'), dict) else {}
    business_raw = raw.get('business') if isinstance(raw.get('business'), dict) else {}
    study_target = study.get('target') if isinstance(study.get('target'), dict) else {}
    merged_target_meta = {**study_target, **business_raw, **target_raw}

    target_name = clean_text(
        merged_target_meta.get('name')
        or merged_target_meta.get('title')
        or business_raw.get('name')
        or (target_from_factions['name'] if target_from_factions else None)
        or study.get('target_name')
        or raw.get('target_name'),
        'Target Business',
    )
    target_location = clean_text(
        business_raw.get('location')
        or target_raw.get('location')
        or business_raw.get('address')
        or target_raw.get('address')
        or study.get('location')
        or raw.get('location')
        or study.get('center_label'),
        'Local Service Area',
    )

    if target_from_factions is None:
        target_from_factions = {
            'faction_id': 'TARGET',
            'short_code': 'YOU',
            'is_target': True,
            'rank_order': 0,
            'name': target_name,
            'archetype': 'COMMANDER',
            'threat_level': 'SELF',
            'solv_pct': round(safe_float(merged_target_meta.get('solv_pct', 0.0)), 1),
            'visible_pct': round(safe_float(merged_target_meta.get('visible_pct', 0.0)), 1),
            'top1_count': safe_int(merged_target_meta.get('top1_count', 0)),
            'top3_count': safe_int(merged_target_meta.get('top3_count', 0)),
            'top10_count': safe_int(merged_target_meta.get('top10_count', 0)),
            'found_count': safe_int(merged_target_meta.get('found_count', 0)),
            'total_slots': safe_int(merged_target_meta.get('total_slots', 0)),
            'average_rank': safe_float(merged_target_meta.get('average_rank'), 0.0) or None,
            'votes_count': safe_int(merged_target_meta.get('votes_count', 0)) if merged_target_meta.get('votes_count') is not None else None,
            'rating': safe_float(merged_target_meta.get('rating'), 0.0) or None,
            'category': clean_text(merged_target_meta.get('category'), 'Primary Target'),
            'additional_categories': [],
            'domain': clean_text(merged_target_meta.get('domain'), ''),
            'lat': safe_float(merged_target_meta.get('lat')) if merged_target_meta.get('lat') is not None else None,
            'lng': safe_float(merged_target_meta.get('lng')) if merged_target_meta.get('lng') is not None else None,
            'gravity_radius_km': round(safe_float(merged_target_meta.get('gravity_radius_km', 0.0)), 2),
            'max_top3_distance_km': round(safe_float(merged_target_meta.get('max_top3_distance_km', 0.0)), 2),
            'primary_vulnerability': clean_text(merged_target_meta.get('primary_vulnerability'), 'Target command focal point'),
            'color': '#10B981',
            'lane_stats': {},
        }
        factions.insert(0, target_from_factions)

    # Sort factions so TARGET (YOU) is first, followed by R01..R10
    factions.sort(key=lambda x: (0 if x['is_target'] else 1, x['rank_order'], -x['solv_pct']))
    faction_lookup = {}
    for f in factions:
        faction_lookup[f['faction_id']] = f
        faction_lookup[f['short_code']] = f
        faction_lookup[f['name'].lower()] = f

    # Normalize points
    points_raw = raw.get('points') or raw.get('tiles') or raw.get('grid_points') or []
    points: list[dict[str, Any]] = []
    for idx, p in enumerate(points_raw):
        if not isinstance(p, dict):
            continue
        agg = p.get('aggregate') if isinstance(p.get('aggregate'), dict) else (p.get('composite') if isinstance(p.get('composite'), dict) else {})
        lat = safe_float(p.get('lat', p.get('latitude')), 0.0)
        lng = safe_float(p.get('lng', p.get('longitude')), 0.0)
        row = safe_int(p.get('row', p.get('y', idx // 5)), 0)
        col = safe_int(p.get('col', p.get('x', idx % 5)), 0)
        tag = clean_text(p.get('tag'), f'r{row}c{col}')
        sector = clean_text(p.get('sector') or agg.get('sector'), 'CORE')
        dist_km = round(safe_float(p.get('distance_from_target_km', p.get('distance_km', agg.get('distance_from_target_km', 0.0)))), 2)

        tactical_class = clean_text(
            agg.get('tactical_class') or p.get('tactical_class'),
            'CONTESTED_FRONT',
        ).upper()
        if tactical_class not in TACTICAL_CLASS_MAP:
            tactical_class = 'CONTESTED_FRONT'

        opp_score = round(safe_float(agg.get('opportunity_score', p.get('opportunity_score', 50.0))), 1)
        fog_state = clean_text(agg.get('fog_state') or p.get('fog_state'), 'CONTESTED_VISION').upper()
        if fog_state not in ('CLEARED_CITADEL', 'CONTESTED_VISION', 'SUPPRESSED_SECTOR', 'DARK_ZONE'):
            fog_state = 'CONTESTED_VISION'

        ctrl_id = clean_text(agg.get('controlling_faction_id') or p.get('controlling_faction_id') or p.get('owner'), 'CONTESTED')
        matched_f = faction_lookup.get(ctrl_id) or faction_lookup.get(ctrl_id.lower())
        ctrl_name = clean_text(
            agg.get('controlling_faction_name')
            or p.get('controlling_faction_name')
            or (matched_f['name'] if matched_f else None),
            'Contested / Untracked',
        )
        ctrl_code = clean_text(
            agg.get('controlling_short_code')
            or p.get('controlling_short_code')
            or (matched_f['short_code'] if matched_f else None),
            'YOU' if ctrl_id in ('TARGET', 'YOU') else (ctrl_id if ctrl_id.startswith('R') else (f'R{ctrl_id[1:]}' if ctrl_id.startswith('F') and ctrl_id[1:].isdigit() else '--')),
        )
        ctrl_color = clean_text(
            agg.get('controlling_faction_color')
            or p.get('controlling_faction_color')
            or (matched_f['color'] if matched_f else None)
            or DEFAULT_FACTION_PALETTE.get(ctrl_id)
            or DEFAULT_FACTION_PALETTE.get(ctrl_code),
            '#64748B',
        )
        turf_state = clean_text(agg.get('turf_state') or p.get('turf_state'), 'RIVAL_CONTROLLED')
        target_rank_val = agg.get('target_rank', agg.get('best_rank', agg.get('avg_rank', p.get('target_rank', p.get('rank')))))
        target_rank = safe_int(target_rank_val, 0) if target_rank_val is not None and safe_float(target_rank_val, 0) > 0 else None

        grav_raw = agg.get('gravity_anomaly') or p.get('gravity_anomaly') or {}
        if not isinstance(grav_raw, dict):
            grav_raw = {}
        has_anom = bool(grav_raw.get('has_anomaly'))
        grav_anom = {
            'has_anomaly': has_anom,
            'faction_id': clean_text(grav_raw.get('faction_id'), ''),
            'faction_name': clean_text(grav_raw.get('faction_name'), ''),
            'rank': safe_int(grav_raw.get('rank', 0), 0) if grav_raw.get('rank') is not None else None,
            'distance_from_pin_km': round(safe_float(grav_raw.get('distance_from_pin_km', grav_raw.get('distance_km', 0.0))), 2),
            'reason': clean_text(grav_raw.get('reason'), ''),
        }

        points.append({
            'tag': tag,
            'row': row,
            'col': col,
            'lat': lat,
            'lng': lng,
            'sector': sector,
            'distance_from_target_km': dist_km,
            'tactical_class': tactical_class,
            'opportunity_score': opp_score,
            'fog_state': fog_state,
            'controlling_faction_id': ctrl_id,
            'controlling_faction_name': ctrl_name,
            'controlling_short_code': ctrl_code,
            'controlling_faction_color': ctrl_color,
            'turf_state': turf_state,
            'target_rank': target_rank,
            'vulnerability_reasons': [clean_text(r) for r in (agg.get('vulnerability_reasons') or p.get('vulnerability_reasons') or []) if clean_text(r)],
            'counter_move': clean_text(agg.get('counter_move') or p.get('counter_move'), ''),
            'gravity_anomaly': grav_anom,
            'by_lane': p.get('by_lane') if isinstance(p.get('by_lane'), dict) else {},
        })

    # Determine center and bounds
    center_obj = study.get('center') or raw.get('center') or {}
    if not isinstance(center_obj, dict):
        center_obj = {}
    center_lat = safe_float(
        center_obj.get('lat')
        or study.get('center_lat')
        or raw.get('center_lat')
        or merged_target_meta.get('lat')
        or (target_from_factions.get('lat') if target_from_factions else None)
        or (sum(pt['lat'] for pt in points) / len(points) if points else 30.2672),
    )
    center_lng = safe_float(
        center_obj.get('lng')
        or study.get('center_lng')
        or raw.get('center_lng')
        or merged_target_meta.get('lng')
        or (target_from_factions.get('lng') if target_from_factions else None)
        or (sum(pt['lng'] for pt in points) / len(points) if points else -97.7431),
    )
    if target_from_factions['lat'] is None or target_from_factions['lng'] is None:
        target_from_factions['lat'] = center_lat
        target_from_factions['lng'] = center_lng

    lats = [pt['lat'] for pt in points] + [center_lat]
    lngs = [pt['lng'] for pt in points] + [center_lng]
    raw_bounds = raw.get('bounds') or study.get('bounds')
    if isinstance(raw_bounds, list) and len(raw_bounds) == 4:
        bounds = [float(x) for x in raw_bounds]
    else:
        min_lng, max_lng = min(lngs), max(lngs)
        min_lat, max_lat = min(lats), max(lats)
        dlng = max((max_lng - min_lng) * 0.12, 0.008)
        dlat = max((max_lat - min_lat) * 0.12, 0.008)
        bounds = [min_lng - dlng, min_lat - dlat, max_lng + dlng, max_lat + dlat]

    max_dist_km = max(
        [pt['distance_from_target_km'] for pt in points]
        + [haversine_km(center_lat, center_lng, pt['lat'], pt['lng']) for pt in points]
        + [1.5]
    )
    radius_km = round(safe_float(study.get('radius_km') or raw.get('radius_km'), max_dist_km), 2)

    rows_count = safe_int(
        study.get('rows') or study.get('grid_rows') or raw.get('rows'),
        len({pt['row'] for pt in points}) or max(1, int(round(math.sqrt(len(points) or 1)))),
    )
    cols_count = safe_int(
        study.get('cols') or study.get('grid_cols') or raw.get('cols'),
        len({pt['col'] for pt in points}) or max(1, int(round(math.sqrt(len(points) or 1)))),
    )
    raw_gdims = clean_text(study.get('grid_dimensions') or raw.get('grid_dimensions'), '')
    if 'x' in raw_gdims.lower():
        grid_dims = raw_gdims
    else:
        grid_dims = f'{rows_count}x{cols_count} ({len(points)} origins)'

    # Normalize lanes
    lanes_raw = raw.get('lanes') or study.get('lanes') or []
    lanes: list[dict[str, Any]] = []
    for idx, l in enumerate(lanes_raw):
        if not isinstance(l, dict):
            continue
        lid = clean_text(l.get('lane_id') or l.get('query_id') or l.get('id'), f'q{idx + 1}')
        query = clean_text(l.get('query') or l.get('keyword') or l.get('label'), lid)
        label = clean_text(l.get('label') or l.get('title') or query, query)

        # Compute lane metrics from lane dict, target lane_stats, or points.by_lane
        t_lstats = target_from_factions.get('lane_stats', {}).get(lid, {})
        solv_val = l.get('target_solv_pct', l.get('solv_pct', t_lstats.get('solv_pct')))
        avg_rank_val = l.get('target_avg_rank', l.get('target_average_rank', l.get('average_rank', t_lstats.get('average_rank'))))

        lane_pts = [pt['by_lane'].get(lid, {}) for pt in points if isinstance(pt.get('by_lane'), dict) and lid in pt['by_lane']]
        if solv_val is None and lane_pts:
            top3_c = sum(1 for lp in lane_pts if safe_int(lp.get('target_rank', lp.get('rank')), 999) <= 3)
            solv_val = 100.0 * top3_c / len(lane_pts)
        if avg_rank_val is None and lane_pts:
            found_ranks = [safe_float(lp.get('target_rank', lp.get('rank'))) for lp in lane_pts if safe_float(lp.get('target_rank', lp.get('rank')), 0) > 0]
            avg_rank_val = (sum(found_ranks) / len(found_ranks)) if found_ranks else None

        dom_rival = clean_text(
            l.get('dominant_rival_name')
            or l.get('dominant_faction_name')
            or l.get('dominant_rival'),
            '',
        )
        if not dom_rival:
            best_f = None
            best_s = -1.0
            for f in factions:
                if f['is_target']:
                    continue
                fl = f.get('lane_stats', {}).get(lid, {})
                s = safe_float(fl.get('solv_pct'), -1.0)
                if s > best_s:
                    best_s = s
                    best_f = f
            if best_f and best_s >= 0:
                dom_rival = f"{best_f['short_code']} {best_f['name']} ({best_s:.1f}%)"
            elif len(factions) > 1:
                dom_rival = f"{factions[1]['short_code']} {factions[1]['name']}"
            else:
                dom_rival = 'None detected'

        strike_c = l.get('strike_zone_count', l.get('prime_strike_zones'))
        if strike_c is None:
            if lane_pts:
                strike_c = sum(1 for lp in lane_pts if clean_text(lp.get('tactical_class'), '') in ('PRIME_STRIKE_ZONE', 'FLANKING_MINE'))
            else:
                strike_c = sum(1 for pt in points if pt['tactical_class'] in ('PRIME_STRIKE_ZONE', 'FLANKING_MINE'))

        fort_c = l.get('fortress_count', l.get('enemy_fortresses'))
        if fort_c is None:
            if lane_pts:
                fort_c = sum(1 for lp in lane_pts if clean_text(lp.get('tactical_class'), '') == 'ENEMY_FORTRESS')
            else:
                fort_c = sum(1 for pt in points if pt['tactical_class'] == 'ENEMY_FORTRESS')

        lanes.append({
            'lane_id': lid,
            'query': query,
            'label': label,
            'target_solv_pct': round(safe_float(solv_val, target_from_factions['solv_pct']), 1),
            'target_avg_rank': round(safe_float(avg_rank_val), 2) if avg_rank_val is not None and safe_float(avg_rank_val, 0) > 0 else None,
            'dominant_rival': dom_rival,
            'strike_zone_count': safe_int(strike_c, 0),
            'fortress_count': safe_int(fort_c, 0),
        })

    if not lanes:
        lanes.append({
            'lane_id': 'q1',
            'query': clean_text(raw.get('keyword') or study.get('keyword'), 'Primary Search Theme'),
            'label': clean_text(raw.get('keyword') or study.get('keyword'), 'Primary Search Theme'),
            'target_solv_pct': target_from_factions['solv_pct'],
            'target_avg_rank': target_from_factions['average_rank'],
            'dominant_rival': f"{factions[1]['short_code']} {factions[1]['name']}" if len(factions) > 1 else 'None',
            'strike_zone_count': sum(1 for pt in points if pt['tactical_class'] in ('PRIME_STRIKE_ZONE', 'FLANKING_MINE')),
            'fortress_count': sum(1 for pt in points if pt['tactical_class'] == 'ENEMY_FORTRESS'),
        })

    # Tactical class counts & Fog of War summary
    class_counts = {k: 0 for k, _, _, _ in TACTICAL_CLASSES}
    fog_counts = {
        'CLEARED_CITADEL': 0,
        'CONTESTED_VISION': 0,
        'SUPPRESSED_SECTOR': 0,
        'DARK_ZONE': 0,
    }
    anomalies: list[dict[str, Any]] = []
    for pt in points:
        tc = pt['tactical_class']
        class_counts[tc] = class_counts.get(tc, 0) + 1
        fs = pt['fog_state']
        fog_counts[fs] = fog_counts.get(fs, 0) + 1
        if pt['gravity_anomaly']['has_anomaly']:
            anomalies.append({
                'tag': pt['tag'],
                'sector': pt['sector'],
                'lat': pt['lat'],
                'lng': pt['lng'],
                **pt['gravity_anomaly'],
            })

    anomalies.sort(
        key=lambda a: (
            a.get('faction_id') in ('', 'UNALIGNED', None),
            -safe_float(a.get('distance_from_pin_km'), 0.0),
            safe_int(a.get('rank'), 99),
        )
    )

    orders_raw = raw.get('campaign_orders') or {}
    if not isinstance(orders_raw, dict):
        orders_raw = {}

    fow_raw = orders_raw.get('fog_of_war_summary') or raw.get('fog_of_war_summary') or {}
    if not isinstance(fow_raw, dict):
        fow_raw = {}

    cleared_c = safe_int(fow_raw.get('cleared_citadel_tiles', fog_counts['CLEARED_CITADEL']))
    contested_v = safe_int(fow_raw.get('contested_vision_tiles', fog_counts['CONTESTED_VISION']))
    suppressed_c = safe_int(fow_raw.get('suppressed_tiles', fow_raw.get('suppressed_sector_tiles', fog_counts['SUPPRESSED_SECTOR'])))
    dark_c = safe_int(fow_raw.get('dark_zone_tiles', fog_counts['DARK_ZONE']))
    total_pts = max(1, len(points))
    default_vis_pct = round(100.0 * (total_pts - dark_c) / total_pts, 1) if points else 0.0
    vis_pct = round(safe_float(fow_raw.get('visibility_coverage_pct', default_vis_pct), default_vis_pct), 1)

    headline = clean_text(
        orders_raw.get('headline_summary') or raw.get('headline_summary'),
        f"{target_name} holds {target_from_factions['solv_pct']:.1f}% Top-3 Share of Local Voice across {len(points)} coordinates and {len(lanes)} search lane(s), with {class_counts['PRIME_STRIKE_ZONE']} Prime Strike Zones and {class_counts['FLANKING_MINE']} Flanking Mines ready for capture.",
    )

    # Strike corridors
    corridors_raw = orders_raw.get('strike_corridors') or []
    strike_corridors: list[dict[str, Any]] = []
    for idx, c in enumerate(corridors_raw):
        if not isinstance(c, dict):
            continue
        tiles = c.get('tiles') or c.get('point_tags') or []
        if isinstance(tiles, list):
            tiles_str = ', '.join(clean_text(t) for t in tiles[:8]) + (f' (+{len(tiles) - 8} more)' if len(tiles) > 8 else '')
        else:
            tiles_str = clean_text(tiles, 'Sector cluster')
        ranks_val = c.get('target_current_ranks', c.get('target_ranks', '4-10'))
        if isinstance(ranks_val, list):
            ranks_str = ', '.join(str(r) for r in ranks_val[:6])
        else:
            ranks_str = clean_text(ranks_val, '4-10')
        inc_name = clean_text(c.get('weak_incumbent_name') or c.get('vulnerable_incumbent'), 'Overextended Rival')
        inc_vuln = clean_text(c.get('weak_incumbent_vulnerability'), '')
        strike_corridors.append({
            'corridor_id': clean_text(c.get('corridor_id'), f'STRIKE-{idx + 1:02d}'),
            'sector': clean_text(c.get('sector'), 'CORE'),
            'title': clean_text(c.get('title'), f"Sector {clean_text(c.get('sector'), 'CORE')} Strike Corridor"),
            'tiles_str': tiles_str or 'Sector tiles',
            'avg_opportunity_score': round(safe_float(c.get('avg_opportunity_score', c.get('opportunity_score', 70.0))), 1),
            'target_ranks': ranks_str,
            'vulnerable_incumbent': f'{inc_name} ({inc_vuln})' if inc_vuln and inc_vuln not in inc_name else inc_name,
            'recommended_order': clean_text(c.get('recommended_order') or c.get('counter_move'), 'Deploy localized proof and category alignment targeting this corridor.'),
        })

    # Tech-tree unlocks
    unlocks_raw = orders_raw.get('tech_tree_unlocks') or []
    tech_tree_unlocks: list[dict[str, Any]] = []
    for u in unlocks_raw:
        if not isinstance(u, dict):
            continue
        used_by = u.get('used_by_rivals', '')
        if isinstance(used_by, list):
            used_by_str = ', '.join(clean_text(x) for x in used_by) if used_by else 'Top Rivals'
        else:
            used_by_str = clean_text(used_by, 'Top Rivals')
        tech_tree_unlocks.append({
            'unlock_type': clean_text(u.get('unlock_type') or u.get('type'), 'GBP_CATEGORY'),
            'name': clean_text(u.get('name') or u.get('title'), 'Strategic Capability Unlock'),
            'used_by_rivals': used_by_str,
            'rivals_solv_avg': round(safe_float(u.get('rivals_solv_avg', 0.0)), 1),
            'impact_rationale': clean_text(u.get('impact_rationale') or u.get('rationale') or u.get('description'), 'Closes competitive capability gap observed across top-ranking rivals.'),
        })

    # Fortress warnings
    warnings_raw = orders_raw.get('fortress_warnings') or []
    fortress_warnings: list[dict[str, Any]] = []
    for w in warnings_raw:
        if isinstance(w, str):
            fortress_warnings.append({
                'sector': 'FORTRESS',
                'faction_name': 'Entrenched Incumbent',
                'tiles_str': '-',
                'warning': clean_text(w),
            })
        elif isinstance(w, dict):
            wtiles = w.get('tiles') or w.get('fortress_count') or []
            if isinstance(wtiles, list):
                wtiles_str = ', '.join(clean_text(t) for t in wtiles[:6])
            elif isinstance(wtiles, int):
                wtiles_str = f'{wtiles} tiles'
            else:
                wtiles_str = clean_text(wtiles, '-')
            w_reason = clean_text(w.get('reason') or w.get('warning') or w.get('summary'), '')
            w_advice = clean_text(w.get('tactical_advice') or w.get('recommendation'), '')
            if w_advice and w_advice not in w_reason:
                combined_w = f'{w_reason} {w_advice}'.strip()
            else:
                combined_w = w_reason or w_advice or 'Avoid direct early-turn spend against fortified citadel; flank via adjacent strike zones.'
            fortress_warnings.append({
                'sector': clean_text(w.get('sector'), 'CORE'),
                'faction_name': clean_text(w.get('faction_name') or w.get('incumbent_name') or w.get('title'), 'Entrenched Citadel'),
                'tiles_str': wtiles_str or '-',
                'warning': combined_w,
            })

    # Next-turn recon probes
    probes_raw = orders_raw.get('next_turn_recon_probes') or []
    recon_probes: list[dict[str, Any]] = []
    for pr in probes_raw:
        if isinstance(pr, str):
            recon_probes.append({
                'probe_type': 'RIVAL_CITADEL_SCAN',
                'target_name': 'Competitor Frontier',
                'rationale': 'Map rival gravity boundary',
                'cli_command': clean_text(pr),
            })
        elif isinstance(pr, dict):
            recon_probes.append({
                'probe_type': clean_text(pr.get('probe_type') or pr.get('type'), 'RIVAL_CITADEL_SCAN'),
                'target_name': clean_text(pr.get('target_name') or pr.get('faction_name') or pr.get('title'), 'Rival Citadel'),
                'rationale': clean_text(pr.get('rationale') or pr.get('reason') or pr.get('objective'), 'Quantify rival citadel radius and outer flank decay.'),
                'cli_command': clean_text(pr.get('cli_command') or pr.get('command'), 'python tools/battlefield.py --input <run-dir> --output-dir <out>'),
            })

    total_competitors = safe_int(
        study.get('total_competitors_analyzed')
        or raw.get('total_competitors_analyzed')
        or study.get('total_competitors')
        or raw.get('total_competitors'),
        max(0, len(factions) - 1),
    )

    return {
        'schema': clean_text(raw.get('schema'), 'geogrid-battlefield/v1'),
        'generated_at': clean_text(raw.get('generated_at'), '2026-10-15T00:00:00Z'),
        'synthetic': bool(raw.get('synthetic', study.get('synthetic', False))),
        'target': target_from_factions,
        'target_name': target_name,
        'location': target_location,
        'center_lat': center_lat,
        'center_lng': center_lng,
        'bounds': bounds,
        'radius_km': radius_km,
        'rows': rows_count,
        'cols': cols_count,
        'grid_dimensions': grid_dims,
        'total_competitors_analyzed': total_competitors,
        'factions': factions[:11],
        'lanes': lanes,
        'points': points,
        'tactical_counts': class_counts,
        'fog_of_war_summary': {
            'cleared_citadel_tiles': cleared_c,
            'contested_vision_tiles': contested_v,
            'suppressed_tiles': suppressed_c,
            'dark_zone_tiles': dark_c,
            'visibility_coverage_pct': vis_pct,
        },
        'gravity_anomalies': anomalies,
        'campaign_orders': {
            'headline_summary': headline,
            'strike_corridors': strike_corridors,
            'tech_tree_unlocks': tech_tree_unlocks,
            'fortress_warnings': fortress_warnings,
            'next_turn_recon_probes': recon_probes,
        },
        'basemap': raw.get('basemap') if isinstance(raw.get('basemap'), dict) else study.get('basemap'),
    }


def _draw_tactical_radar_base(
    canvas: Any,
    rect: tuple[int, int, int, int],
    proj: ViewportProjection,
    norm: dict[str, Any],
    fonts: dict[str, str],
    theme: str,
) -> None:
    """Render either a supplied georeferenced basemap or the tactical radar grid."""
    from PIL import Image, ImageDraw, ImageFont

    rx0, ry0, rx1, ry1 = rect
    rw, rh = rx1 - rx0, ry1 - ry0
    is_light = theme == 'light'

    panel_bg = (246, 248, 252) if is_light else (8, 12, 20)
    grid_line = (214, 222, 235) if is_light else (22, 33, 52)
    sector_line = (195, 206, 224) if is_light else (30, 45, 70)
    ring_stroke = (148, 163, 184, 175) if is_light else (100, 130, 170, 150)
    border_col = (160, 174, 192) if is_light else (56, 74, 102)
    muted_txt = (90, 102, 120) if is_light else (130, 148, 176)
    ink_txt = (15, 23, 42) if is_light else (235, 242, 252)

    draw = ImageDraw.Draw(canvas)
    draw.rectangle(rect, fill=panel_bg, outline=border_col, width=2 * SCALE // 2)

    # Check if an optional local georeferenced basemap image exists
    base = norm.get('basemap')
    has_street = False
    if isinstance(base, dict) and base.get('path') and base.get('bounds'):
        bpath = Path(str(base['path']))
        if bpath.is_file():
            try:
                from strategy_report import georeferenced_image
                terrain = georeferenced_image(
                    {'path': str(bpath), 'bounds': base['bounds'], 'crs': base.get('crs', 'EPSG:3857')},
                    proj.bounds,
                    rw,
                    rh,
                )
                canvas.paste(terrain, (rx0, ry0), terrain)
                has_street = True
            except Exception:
                has_street = False

    overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    if not has_street:
        # Graticule coordinate grid lines (6 columns x 5 rows)
        for i in range(1, 6):
            gx = round(rx0 + rw * i / 6.0)
            odraw.line((gx, ry0, gx, ry1), fill=(*grid_line, 210), width=2)
        for j in range(1, 5):
            gy = round(ry0 + rh * j / 5.0)
            odraw.line((rx0, gy, rx1, gy), fill=(*grid_line, 210), width=2)

    # Center coordinates
    clat, clng = norm['center_lat'], norm['center_lng']
    cx, cy = proj.point(clat, clng)

    # Subtle 8-sector dividers (22.5, 67.5, ... deg boundaries between N/NE/E/SE/S/SW/W/NW)
    max_r_px = math.hypot(rw, rh)
    for angle_deg in (22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5):
        rad = math.radians(angle_deg)
        # Walk along ray inside rect
        pts_in = []
        for step in range(18, int(max_r_px), 10):
            px = cx + math.sin(rad) * step
            py = cy - math.cos(rad) * step
            if rx0 + 4 <= px <= rx1 - 4 and ry0 + 4 <= py <= ry1 - 4:
                pts_in.append((px, py))
        for k in range(0, len(pts_in) - 1, 2):
            odraw.line((pts_in[k], pts_in[k + 1]), fill=(*sector_line, 130), width=2)

    # Concentric geodesic distance rings around Target / Study Center
    rmax = max(0.6, norm['radius_km'])
    raw_bands = [round(rmax * f, 2) for f in (0.33, 0.66, 1.0)]
    bands_km = sorted({b for b in raw_bands if b > 0.05})
    font_ring = ImageFont.truetype(fonts['mono'], round(7.5 * SCALE))

    for idx_b, b_km in enumerate(bands_km):
        ring_pts = []
        for ang in range(0, 361, 3):
            rlat, rlng = destination(clat, clng, b_km, ang)
            px, py = proj.point(rlat, rlng)
            ring_pts.append((px, py))
        # Clip segment drawing to viewport rect
        for k in range(len(ring_pts) - 1):
            p1, p2 = ring_pts[k], ring_pts[k + 1]
            if (rx0 + 2 <= p1[0] <= rx1 - 2 and ry0 + 2 <= p1[1] <= ry1 - 2 and
                    rx0 + 2 <= p2[0] <= rx1 - 2 and ry0 + 2 <= p2[1] <= ry1 - 2):
                if idx_b % 2 == 1 or k % 2 == 0:
                    odraw.line((p1, p2), fill=ring_stroke, width=2)
        # Ring distance pill label at 45 deg (NE) or 0 deg (N)
        for cand_ang in (55, 0, 125, 305):
            llat, llng = destination(clat, clng, b_km, cand_ang)
            lx, ly = proj.point(llat, llng)
            if rx0 + 45 * SCALE <= lx <= rx1 - 45 * SCALE and ry0 + 18 * SCALE <= ly <= ry1 - 18 * SCALE:
                lbl = f'{b_km:g} km'
                tb = odraw.textbbox((0, 0), lbl, font=font_ring)
                tw, th = tb[2] - tb[0] + 8 * SCALE, tb[3] - tb[1] + 4 * SCALE
                pill = (lx - tw / 2, ly - th / 2, lx + tw / 2, ly + th / 2)
                odraw.rounded_rectangle(
                    pill,
                    radius=3 * SCALE,
                    fill=(255, 255, 255, 220) if is_light else (12, 18, 30, 220),
                    outline=ring_stroke,
                    width=1,
                )
                odraw.text((lx, ly), lbl, font=font_ring, fill=(*ink_txt, 240), anchor='mm')
                break

    canvas.paste(overlay, (0, 0), overlay)
    draw = ImageDraw.Draw(canvas)

    # Compass axes N / S / E / W and sector markers around the inner perimeter
    font_compass = ImageFont.truetype(fonts['bold'], round(8.5 * SCALE))
    font_small = ImageFont.truetype(fonts['mono'], round(7.5 * SCALE))
    mid_x = (rx0 + rx1) / 2.0
    mid_y = (ry0 + ry1) / 2.0
    draw.text((mid_x, ry0 + 10 * SCALE), 'N', font=font_compass, fill=ink_txt, anchor='mm')
    draw.text((mid_x, ry1 - 10 * SCALE), 'S', font=font_compass, fill=ink_txt, anchor='mm')
    draw.text((rx0 + 10 * SCALE, mid_y), 'W', font=font_compass, fill=ink_txt, anchor='mm')
    draw.text((rx1 - 10 * SCALE, mid_y), 'E', font=font_compass, fill=ink_txt, anchor='mm')

    # Diagonal sector tags (NW, NE, SW, SE)
    draw.text((rx0 + 26 * SCALE, ry0 + 14 * SCALE), 'NW', font=font_small, fill=muted_txt, anchor='lm')
    draw.text((rx1 - 14 * SCALE, ry0 + 14 * SCALE), 'NE', font=font_small, fill=muted_txt, anchor='rm')
    draw.text((rx0 + 14 * SCALE, ry1 - 14 * SCALE), 'SW', font=font_small, fill=muted_txt, anchor='lm')
    draw.text((rx1 - 14 * SCALE, ry1 - 14 * SCALE), 'SE', font=font_small, fill=muted_txt, anchor='rm')

    # North arrow icon at top-left
    nx, ny = rx0 + 14 * SCALE, ry0 + 18 * SCALE
    draw.line((nx, ny + 7 * SCALE, nx, ny - 5 * SCALE), fill=(255, 0, 0), width=2 * SCALE // 2)
    draw.polygon([(nx, ny - 7 * SCALE), (nx - 3 * SCALE, ny - 1 * SCALE), (nx + 3 * SCALE, ny - 1 * SCALE)], fill=(255, 0, 0))


def render_opportunity_map(norm: dict[str, Any], out_path: Path, fonts: dict[str, str], theme: str = 'geogrid') -> dict[str, Any]:
    """Render Figure 1: battlefield-opportunity-map.png (1548 x 1140 px)."""
    from PIL import Image, ImageDraw, ImageFont

    width, height = MAP_W * SCALE, MAP_H * SCALE  # 1548 x 1140
    is_light = theme == 'light'
    bg_rgb = (255, 255, 255) if is_light else (0, 0, 0)
    hud_bg = (241, 245, 249) if is_light else (14, 19, 30)
    border_rgb = (180, 190, 205) if is_light else (58, 72, 96)
    ink_rgb = (15, 23, 42) if is_light else (248, 250, 252)
    muted_rgb = (82, 94, 112) if is_light else (148, 163, 184)

    canvas = Image.new('RGB', (width, height), bg_rgb)
    draw = ImageDraw.Draw(canvas)

    # Top HUD bar (y: 0..24*SCALE)
    top_h = 24 * SCALE
    bot_h = 34 * SCALE
    draw.rectangle((0, 0, width - 1, top_h), fill=hud_bg, outline=border_rgb, width=2)
    draw.rectangle((0, 0, 5 * SCALE, top_h), fill=(245, 158, 11))

    font_hud = ImageFont.truetype(fonts['bold'], round(8.5 * SCALE))
    font_hud_mono = ImageFont.truetype(fonts['mono'], round(7.5 * SCALE))
    draw.text(
        (11 * SCALE, top_h / 2),
        'FIG 01 // STRIKE-ZONE OPPORTUNITY MATRIX & TACTICAL RADAR',
        font=font_hud,
        fill=ink_rgb,
        anchor='lm',
    )
    right_meta = f"GRID: {norm['rows']}x{norm['cols']} ({len(norm['points'])} PTS) | LANES: {len(norm['lanes'])} | RADIUS: {norm['radius_km']:g} KM"
    draw.text((width - 8 * SCALE, top_h / 2), right_meta, font=font_hud_mono, fill=muted_rgb, anchor='rm')

    # Geographic viewport rect
    rect = (2 * SCALE, top_h + 2 * SCALE, width - 2 * SCALE, height - bot_h - 2 * SCALE)
    proj = ViewportProjection(norm['bounds'], rect, pad_px=28 * SCALE)
    _draw_tactical_radar_base(canvas, rect, proj, norm, fonts, theme)

    # Soft radial heat halos under PRIME_STRIKE_ZONE and FLANKING_MINE pins
    glow_layer = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow_layer)
    pts = norm['points']
    n_pts = max(1, len(pts))
    base_r = max(5.5 * SCALE, min(11.0 * SCALE, (115.0 / math.sqrt(n_pts)) * SCALE))

    for pt in pts:
        x, y = proj.point(pt['lat'], pt['lng'])
        tc = pt['tactical_class']
        if tc == 'PRIME_STRIKE_ZONE':
            for mult, alpha in ((2.4, 28), (1.8, 52)):
                rr = base_r * mult
                gdraw.ellipse((x - rr, y - rr, x + rr, y + rr), fill=(245, 158, 11, alpha))
        elif tc == 'FLANKING_MINE':
            rr = base_r * 1.9
            gdraw.ellipse((x - rr, y - rr, x + rr, y + rr), fill=(6, 182, 212, 38))

    canvas.paste(glow_layer, (0, 0), glow_layer)
    draw = ImageDraw.Draw(canvas)

    # Target HQ crosshair behind pins
    tx, ty = proj.point(norm['center_lat'], norm['center_lng'])
    ch_r = base_r + 7 * SCALE
    for a, b, c, d in (
        (tx - ch_r - 4 * SCALE, ty, tx - ch_r + 2 * SCALE, ty),
        (tx + ch_r - 2 * SCALE, ty, tx + ch_r + 4 * SCALE, ty),
        (tx, ty - ch_r - 4 * SCALE, tx, ty - ch_r + 2 * SCALE),
        (tx, ty + ch_r - 2 * SCALE, tx, ty + ch_r + 4 * SCALE),
    ):
        draw.line((a, b, c, d), fill=(16, 185, 129), width=3)

    # Draw coordinate markers with Opportunity Score & Tactical Class
    font_pin = ImageFont.truetype(fonts['bold'], max(round(6.5 * SCALE), min(round(8.5 * SCALE), round(base_r * 0.78))))
    for pt in pts:
        x, y = proj.point(pt['lat'], pt['lng'])
        tc = pt['tactical_class']
        _, fill_hex, ink_hex = TACTICAL_CLASS_MAP.get(tc, TACTICAL_CLASS_MAP['CONTESTED_FRONT'])
        fill_rgb = hex_to_rgb(fill_hex)
        pin_ink = hex_to_rgb(ink_hex)
        score_str = str(safe_int(pt['opportunity_score']))

        if tc == 'PRIME_STRIKE_ZONE':
            # Double target ring + reticle ticks + bright Amber/Gold core
            outer_r = base_r + 4.0 * SCALE
            draw.ellipse(
                (x - outer_r, y - outer_r, x + outer_r, y + outer_r),
                outline=(245, 158, 11),
                width=2 * SCALE // 2 + 1,
            )
            for dx_t, dy_t in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                draw.line(
                    (
                        x + dx_t * (outer_r - 1.5 * SCALE),
                        y + dy_t * (outer_r - 1.5 * SCALE),
                        x + dx_t * (outer_r + 2.2 * SCALE),
                        y + dy_t * (outer_r + 2.2 * SCALE),
                    ),
                    fill=(245, 158, 11),
                    width=2,
                )
            draw.ellipse(
                (x - base_r, y - base_r, x + base_r, y + base_r),
                fill=fill_rgb,
                outline=(255, 255, 255) if not is_light else (15, 23, 42),
                width=2,
            )
        elif tc == 'FLANKING_MINE':
            # Cyan fill with gold outer ring
            outer_r = base_r + 2.5 * SCALE
            draw.ellipse(
                (x - outer_r, y - outer_r, x + outer_r, y + outer_r),
                outline=(245, 158, 11),
                width=2,
            )
            draw.ellipse(
                (x - base_r, y - base_r, x + base_r, y + base_r),
                fill=fill_rgb,
                outline=(255, 255, 255) if not is_light else (15, 23, 42),
                width=2,
            )
        elif tc == 'ENEMY_FORTRESS':
            # Heavy crimson double-ring fortress marker
            outer_r = base_r + 2.2 * SCALE
            draw.ellipse(
                (x - outer_r, y - outer_r, x + outer_r, y + outer_r),
                fill=(127, 29, 29),
                outline=(239, 68, 68),
                width=2,
            )
            draw.ellipse(
                (x - base_r, y - base_r, x + base_r, y + base_r),
                fill=fill_rgb,
                outline=(254, 202, 202),
                width=2,
            )
        elif tc == 'OWNED_STRONGHOLD':
            draw.ellipse(
                (x - base_r, y - base_r, x + base_r, y + base_r),
                fill=fill_rgb,
                outline=(209, 250, 229) if not is_light else (6, 95, 70),
                width=2,
            )
        else:
            draw.ellipse(
                (x - base_r, y - base_r, x + base_r, y + base_r),
                fill=fill_rgb,
                outline=(255, 255, 255) if not is_light else (71, 85, 105),
                width=2,
            )

        draw.text((x, y), score_str, font=font_pin, fill=pin_ink, anchor='mm')

    # Bottom Legend & Coordinate Readout Strip
    ly0 = height - bot_h
    draw.rectangle((0, ly0, width - 1, height - 1), fill=hud_bg, outline=border_rgb, width=2)
    font_leg = ImageFont.truetype(fonts['bold'], round(5.9 * SCALE))
    font_leg_sub = ImageFont.truetype(fonts['mono'], round(6.1 * SCALE))

    leg_x_offsets = (12 * SCALE, 118 * SCALE, 212 * SCALE, 326 * SCALE, 424 * SCALE)
    counts = norm['tactical_counts']
    for idx, (tc_key, tc_label, tc_hex, _) in enumerate(TACTICAL_CLASSES):
        cx_i = leg_x_offsets[idx]
        cy_i = ly0 + 11 * SCALE
        sw_rgb = hex_to_rgb(tc_hex)
        if tc_key == 'PRIME_STRIKE_ZONE':
            draw.ellipse((cx_i - 5.2 * SCALE, cy_i - 5.2 * SCALE, cx_i + 5.2 * SCALE, cy_i + 5.2 * SCALE), outline=sw_rgb, width=2)
        draw.ellipse((cx_i - 3.6 * SCALE, cy_i - 3.6 * SCALE, cx_i + 3.6 * SCALE, cy_i + 3.6 * SCALE), fill=sw_rgb)
        c_val = counts.get(tc_key, 0)
        draw.text((cx_i + 7.5 * SCALE, cy_i), f'{tc_label.upper()} ({c_val})', font=font_leg, fill=ink_rgb, anchor='lm')

    w, s, e, n = norm['bounds']
    bounds_txt = (
        f'PIN NUMBER = OPPORTUNITY SCORE (0-100)  |  DOUBLE RING = PRIME STRIKE ZONE (65+)  |  '
        f'BOUNDS: W {w:.4f}  S {s:.4f}  E {e:.4f}  N {n:.4f}'
    )
    draw.text((8 * SCALE, height - 8 * SCALE), bounds_txt, font=font_leg_sub, fill=muted_rgb, anchor='lm')

    canvas.save(out_path, format='PNG')
    return {
        'file': out_path.name,
        'path': str(out_path),
        'width_px': width,
        'height_px': height,
        'width_pt': MAP_W,
        'height_pt': MAP_H,
    }


def render_turf_map(norm: dict[str, Any], out_path: Path, fonts: dict[str, str], theme: str = 'geogrid') -> dict[str, Any]:
    """Render Figure 2: battlefield-turf-map.png (1548 x 1140 px)."""
    from PIL import Image, ImageDraw, ImageFont

    width, height = MAP_W * SCALE, MAP_H * SCALE  # 1548 x 1140
    is_light = theme == 'light'
    bg_rgb = (255, 255, 255) if is_light else (0, 0, 0)
    hud_bg = (241, 245, 249) if is_light else (14, 19, 30)
    border_rgb = (180, 190, 205) if is_light else (58, 72, 96)
    ink_rgb = (15, 23, 42) if is_light else (248, 250, 252)
    muted_rgb = (82, 94, 112) if is_light else (148, 163, 184)

    canvas = Image.new('RGB', (width, height), bg_rgb)
    draw = ImageDraw.Draw(canvas)

    top_h = 24 * SCALE
    bot_h = 56 * SCALE  # Spacious 11-faction legend + Fog of War strip at bottom
    draw.rectangle((0, 0, width - 1, top_h), fill=hud_bg, outline=border_rgb, width=2)
    draw.rectangle((0, 0, 5 * SCALE, top_h), fill=(16, 185, 129))

    font_hud = ImageFont.truetype(fonts['bold'], round(7.8 * SCALE))
    font_hud_mono = ImageFont.truetype(fonts['mono'], round(6.9 * SCALE))
    draw.text(
        (11 * SCALE, top_h / 2),
        'FIG 02 // SOVEREIGN TURF & FOG OF WAR CARTOGRAPHY',
        font=font_hud,
        fill=ink_rgb,
        anchor='lm',
    )
    fow = norm['fog_of_war_summary']
    right_meta = (
        f"FACTIONS: {len(norm['factions'])} | CLEARED: {fow['cleared_citadel_tiles']} | "
        f"DARK FOG: {fow['dark_zone_tiles']} | COVERAGE: {fow['visibility_coverage_pct']:.1f}%"
    )
    draw.text((width - 8 * SCALE, top_h / 2), right_meta, font=font_hud_mono, fill=muted_rgb, anchor='rm')

    rect = (2 * SCALE, top_h + 2 * SCALE, width - 2 * SCALE, height - bot_h - 2 * SCALE)
    proj = ViewportProjection(norm['bounds'], rect, pad_px=28 * SCALE)
    _draw_tactical_radar_base(canvas, rect, proj, norm, fonts, theme)

    pts = norm['points']
    n_pts = max(1, len(pts))
    base_r = max(5.5 * SCALE, min(10.5 * SCALE, (110.0 / math.sqrt(n_pts)) * SCALE))

    # Layer 1: Territorial turf influence patches + Dark Zone fog hatching rings + Gravity Anomaly lines
    turf_layer = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    tdraw = ImageDraw.Draw(turf_layer)

    faction_by_id = {}
    for f in norm['factions']:
        faction_by_id[f['faction_id']] = f
        faction_by_id[f['short_code']] = f

    for pt in pts:
        x, y = proj.point(pt['lat'], pt['lng'])
        f_rgb = hex_to_rgb(pt['controlling_faction_color'])
        patch_r = base_r * 1.95
        tdraw.ellipse((x - patch_r, y - patch_r, x + patch_r, y + patch_r), fill=(*f_rgb, 42))

        if pt['fog_state'] == 'DARK_ZONE':
            # Dark fog shroud ring + diagonal hatching lines
            fog_r = base_r + 5.0 * SCALE
            fog_fill = (30, 41, 59, 155) if not is_light else (148, 163, 184, 130)
            hatch_col = (239, 68, 68, 210) if not is_light else (185, 28, 28, 195)
            tdraw.ellipse((x - fog_r, y - fog_r, x + fog_r, y + fog_r), fill=fog_fill, outline=hatch_col, width=2)
            # Diagonal hatch lines across the dark zone ring
            step_h = round(3.2 * SCALE)
            for offset in range(-int(fog_r), int(fog_r) + 1, step_h):
                half_chord_sq = fog_r * fog_r - (offset * offset) / 2.0
                if half_chord_sq > 0:
                    hc = math.sqrt(half_chord_sq) * 0.68
                    cx_h = x + offset * 0.5
                    cy_h = y + offset * 0.5
                    tdraw.line((cx_h - hc, cy_h + hc, cx_h + hc, cy_h - hc), fill=hatch_col, width=2)
        elif pt['fog_state'] == 'SUPPRESSED_SECTOR':
            sup_r = base_r + 3.2 * SCALE
            tdraw.ellipse(
                (x - sup_r, y - sup_r, x + sup_r, y + sup_r),
                outline=(234, 179, 8, 185),
                width=2,
            )

        # Gravity anomaly vector line from rival Citadel HQ if inside viewport
        anom = pt['gravity_anomaly']
        if anom.get('has_anomaly'):
            anom_r = base_r + 4.5 * SCALE
            tdraw.ellipse((x - anom_r, y - anom_r, x + anom_r, y + anom_r), outline=(244, 63, 94, 235), width=2)
            af = faction_by_id.get(anom.get('faction_id', ''))
            if af and af.get('lat') is not None and af.get('lng') is not None:
                if proj.inside_bounds(af['lat'], af['lng'], margin_ratio=0.05):
                    fx, fy = proj.point(af['lat'], af['lng'])
                    dist_px = math.hypot(x - fx, y - fy)
                    if dist_px > 12 * SCALE:
                        steps = max(4, int(dist_px / (7 * SCALE)))
                        for s_i in range(0, steps, 2):
                            t0 = s_i / steps
                            t1 = min(1.0, (s_i + 1) / steps)
                            tdraw.line(
                                (fx + (x - fx) * t0, fy + (y - fy) * t0, fx + (x - fx) * t1, fy + (y - fy) * t1),
                                fill=(244, 63, 94, 190),
                                width=2,
                            )

    canvas.paste(turf_layer, (0, 0), turf_layer)
    draw = ImageDraw.Draw(canvas)

    # Layer 2: Grid coordinate turf pins colored by controlling_faction_color
    font_pin = ImageFont.truetype(fonts['bold'], max(round(5.8 * SCALE), min(round(7.6 * SCALE), round(base_r * 0.68))))
    placed_hq_boxes: list[tuple[float, float, float, float]] = []
    for pt in pts:
        x, y = proj.point(pt['lat'], pt['lng'])
        f_rgb = hex_to_rgb(pt['controlling_faction_color'])
        code = pt['controlling_short_code'][:3]
        # Perceived luminance for readable label contrast
        lum = 0.299 * f_rgb[0] + 0.587 * f_rgb[1] + 0.114 * f_rgb[2]
        txt_col = (10, 15, 25) if lum > 145 else (255, 255, 255)
        ring_col = (255, 255, 255) if not is_light else (15, 23, 42)
        draw.ellipse((x - base_r, y - base_r, x + base_r, y + base_r), fill=f_rgb, outline=ring_col, width=2)
        draw.text((x, y), code, font=font_pin, fill=txt_col, anchor='mm')
        placed_hq_boxes.append((x - base_r - 2 * SCALE, y - base_r - 2 * SCALE, x + base_r + 2 * SCALE, y + base_r + 2 * SCALE))

    # Layer 3: Physical Citadel HQ Markers for Target (YOU) and Top Competitors within viewport
    font_hq = ImageFont.truetype(fonts['bold'], round(6.8 * SCALE))
    rx0, ry0, rx1, ry1 = rect
    map_cx, map_cy = (rx0 + rx1) / 2.0, (ry0 + ry1) / 2.0

    for f in norm['factions']:
        flat, flng = f.get('lat'), f.get('lng')
        if flat is None or flng is None:
            continue
        if not proj.inside_bounds(flat, flng, margin_ratio=0.02):
            continue
        hx, hy = proj.point(flat, flng)
        if not (rx0 + 10 * SCALE <= hx <= rx1 - 10 * SCALE and ry0 + 10 * SCALE <= hy <= ry1 - 10 * SCALE):
            continue

        f_rgb = hex_to_rgb(f['color'])
        d_r = 7.2 * SCALE if f['is_target'] else 5.8 * SCALE
        placed_hq_boxes.append((hx - d_r, hy - d_r, hx + d_r, hy + d_r))

        # Callout badge with multi-ring obstacle avoidance so it never covers grid pins
        hq_label = f"{f['short_code']} HQ"
        tb = draw.textbbox((0, 0), hq_label, font=font_hq)
        bw = tb[2] - tb[0] + 7 * SCALE
        bh = tb[3] - tb[1] + 4 * SCALE

        # Prefer outward radial angle away from map center
        out_ang = math.atan2(hy - map_cy, hx - map_cx) if (abs(hx - map_cx) > 2 or abs(hy - map_cy) > 2) else -math.pi / 2.0
        candidates = []
        for dist_mult in (1.3, 2.2, 3.2, 4.4, 5.8, 7.2):
            rad_px = d_r + dist_mult * (base_r * 0.85)
            for ang_off in (0.0, 0.45, -0.45, 0.9, -0.9, 1.4, -1.4, math.pi):
                ang = out_ang + ang_off
                candidates.append((hx + math.cos(ang) * (rad_px + bw * 0.35), hy + math.sin(ang) * (rad_px + bh * 0.35)))

        chosen_box = None
        for cx_c, cy_c in candidates:
            cbox = (cx_c - bw / 2, cy_c - bh / 2, cx_c + bw / 2, cy_c + bh / 2)
            if cbox[0] < rx0 + 18 * SCALE or cbox[2] > rx1 - 18 * SCALE or cbox[1] < ry0 + 16 * SCALE or cbox[3] > ry1 - 16 * SCALE:
                continue
            overlaps = any(
                not (cbox[2] < ob[0] - 2 * SCALE or cbox[0] > ob[2] + 2 * SCALE or cbox[3] < ob[1] - 2 * SCALE or cbox[1] > ob[3] + 2 * SCALE)
                for ob in placed_hq_boxes
            )
            if not overlaps:
                chosen_box = cbox
                break
        if chosen_box is None:
            cx_c = max(rx0 + bw / 2 + 6 * SCALE, min(rx1 - bw / 2 - 6 * SCALE, hx))
            cy_c = max(ry0 + bh / 2 + 6 * SCALE, min(ry1 - bh / 2 - 6 * SCALE, hy - d_r - bh / 2 - 3 * SCALE))
            chosen_box = (cx_c - bw / 2, cy_c - bh / 2, cx_c + bw / 2, cy_c + bh / 2)

        placed_hq_boxes.append(chosen_box)
        bcx = (chosen_box[0] + chosen_box[2]) / 2.0
        bcy = (chosen_box[1] + chosen_box[3]) / 2.0
        draw.line((hx, hy, bcx, bcy), fill=f_rgb, width=2)

        # Diamond Citadel HQ marker drawn on top of leader line start
        diamond = [(hx, hy - d_r), (hx + d_r, hy), (hx, hy + d_r), (hx - d_r, hy)]
        draw.polygon(diamond, fill=f_rgb, outline=(255, 255, 255), width=3)
        inner_d = d_r * 0.48
        draw.polygon(
            [(hx, hy - inner_d), (hx + inner_d, hy), (hx, hy + inner_d), (hx - inner_d, hy)],
            fill=(15, 23, 42) if not is_light else (255, 255, 255),
        )

        draw.rounded_rectangle(
            chosen_box,
            radius=3 * SCALE,
            fill=(15, 23, 42) if not is_light else (255, 255, 255),
            outline=f_rgb,
            width=2,
        )
        draw.text((bcx, bcy), hq_label, font=font_hq, fill=(255, 255, 255) if not is_light else (15, 23, 42), anchor='mm')

    # Bottom 11-Faction Legend Strip (mapping YOU and R01..R10 colors to business names and solv_pct%)
    ly0 = height - bot_h
    draw.rectangle((0, ly0, width - 1, height - 1), fill=hud_bg, outline=border_rgb, width=2)

    font_fcode = ImageFont.truetype(fonts['bold'], round(6.6 * SCALE))
    font_fname = ImageFont.truetype(fonts['regular'], round(6.4 * SCALE))
    font_fmeta = ImageFont.truetype(fonts['mono'], round(5.9 * SCALE))

    # 3 rows x 4 columns in the legend panel (11 factions + 1 Fog/Citadel key cell = 12 cells)
    cols = 4
    col_w = (width - 12 * SCALE) / cols
    row_h = (bot_h - 6 * SCALE) / 3.0

    for idx, f in enumerate(norm['factions'][:11]):
        r_i = idx // cols
        c_i = idx % cols
        x0_cell = 6 * SCALE + c_i * col_w
        y_mid = ly0 + 4 * SCALE + r_i * row_h + row_h / 2.0
        f_rgb = hex_to_rgb(f['color'])
        draw.rounded_rectangle(
            (x0_cell, y_mid - 4.5 * SCALE, x0_cell + 18 * SCALE, y_mid + 4.5 * SCALE),
            radius=2 * SCALE,
            fill=f_rgb,
        )
        lum = 0.299 * f_rgb[0] + 0.587 * f_rgb[1] + 0.114 * f_rgb[2]
        code_ink = (10, 15, 25) if lum > 145 else (255, 255, 255)
        draw.text((x0_cell + 9 * SCALE, y_mid), f['short_code'], font=font_fcode, fill=code_ink, anchor='mm')

        short_name = f['name']
        if len(short_name) > 20:
            short_name = short_name[:18].rstrip() + '..'
        label_str = f"{short_name} ({f['solv_pct']:.1f}%)"
        draw.text((x0_cell + 21 * SCALE, y_mid), label_str, font=font_fname, fill=ink_rgb, anchor='lm')

    # 12th cell: Fog of War & Citadel HQ symbol key
    x0_key = 6 * SCALE + 3 * col_w
    y_key = ly0 + 4 * SCALE + 2 * row_h + row_h / 2.0
    draw.ellipse(
        (x0_key, y_key - 4.5 * SCALE, x0_key + 9 * SCALE, y_key + 4.5 * SCALE),
        fill=(30, 41, 59) if not is_light else (203, 213, 225),
        outline=(239, 68, 68),
        width=2,
    )
    draw.line((x0_key + 2 * SCALE, y_key + 3 * SCALE, x0_key + 7 * SCALE, y_key - 3 * SCALE), fill=(239, 68, 68), width=2)
    draw.text(
        (x0_key + 12 * SCALE, y_key),
        'HATCH = DARK FOG | DIAMOND = HQ',
        font=font_fmeta,
        fill=muted_rgb,
        anchor='lm',
    )

    canvas.save(out_path, format='PNG')
    return {
        'file': out_path.name,
        'path': str(out_path),
        'width_px': width,
        'height_px': height,
        'width_pt': MAP_W,
        'height_pt': MAP_H,
    }


def _build_pdf_document(
    norm: dict[str, Any],
    pdf_path: Path,
    banner_path: Path,
    opp_map_path: Path,
    turf_map_path: Path,
    theme: str,
) -> None:
    """Build the 4-page Letter PDF report using ReportLab Platypus."""
    from PIL import Image as PILImage
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        Image,
        PageBreak,
        PageTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    t_colors = THEMES.get(theme, THEMES['geogrid'])
    is_light = theme == 'light'
    bg_hex = t_colors['BG']
    ink_hex = t_colors['INK']
    muted_hex = '#555555' if is_light else '#A3A3A3'
    line_hex = '#CCCCCC' if is_light else '#334155'
    card_bg_hex = '#F8FAFC' if is_light else '#111827'
    card_alt_hex = '#F1F5F9' if is_light else '#0B0F19'
    header_bg_hex = '#E2E8F0' if is_light else '#1E293B'
    accent_hex = t_colors['ACCENT']

    styles = {
        'eyebrow': ParagraphStyle(
            'eyebrow',
            fontName='ReportMono',
            fontSize=8.5,
            leading=11,
            textColor=HexColor(accent_hex),
            spaceAfter=2,
        ),
        'title': ParagraphStyle(
            'title',
            fontName='ReportTitle',
            fontSize=16.5,
            leading=20,
            textColor=HexColor(ink_hex),
            spaceAfter=3,
        ),
        'section': ParagraphStyle(
            'section',
            fontName='ReportTitle',
            fontSize=15,
            leading=19,
            textColor=HexColor(ink_hex),
            spaceAfter=4,
        ),
        'subhead': ParagraphStyle(
            'subhead',
            fontName='ReportBold',
            fontSize=11,
            leading=14,
            textColor=HexColor(ink_hex),
            spaceBefore=6,
            spaceAfter=4,
            keepWithNext=True,
        ),
        'subtitle': ParagraphStyle(
            'subtitle',
            fontName='ReportMono',
            fontSize=8.5,
            leading=11.5,
            textColor=HexColor(muted_hex),
            spaceAfter=4,
        ),
        'body': ParagraphStyle(
            'body',
            fontName='ReportBody',
            fontSize=9.2,
            leading=12.8,
            textColor=HexColor('#111827' if is_light else '#E2E8F0'),
            spaceAfter=4,
        ),
        'caption': ParagraphStyle(
            'caption',
            fontName='ReportBody',
            fontSize=8.2,
            leading=11,
            textColor=HexColor(muted_hex),
            spaceAfter=3,
        ),
        'th': ParagraphStyle(
            'th',
            fontName='ReportBold',
            fontSize=7.6,
            leading=9.5,
            textColor=HexColor('#0F172A' if is_light else '#F8FAFC'),
        ),
        'td': ParagraphStyle(
            'td',
            fontName='ReportBody',
            fontSize=7.6,
            leading=9.8,
            textColor=HexColor('#1E293B' if is_light else '#E2E8F0'),
        ),
        'td_bold': ParagraphStyle(
            'td_bold',
            fontName='ReportBold',
            fontSize=7.6,
            leading=9.8,
            textColor=HexColor(ink_hex),
        ),
        'td_mono': ParagraphStyle(
            'td_mono',
            fontName='ReportMono',
            fontSize=7.0,
            leading=9.2,
            textColor=HexColor('#0F172A' if is_light else '#F1F5F9'),
        ),
    }

    def p(text_val: Any, style_name: str = 'body') -> Paragraph:
        s = escape(clean_text(text_val, '')).replace('\n', '<br/>')
        return Paragraph(s, styles[style_name])

    def p_markup(markup_val: str, style_name: str = 'body') -> Paragraph:
        s = markup_val.replace(FORBIDDEN_EM_DASH, ' - ').replace(EN_DASH_CHAR, '-')
        return Paragraph(s, styles[style_name])

    def on_page(canv: Any, doc: Any) -> None:
        canv.saveState()
        canv.setFillColor(HexColor(bg_hex))
        canv.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        canv.setStrokeColor(HexColor(line_hex))
        canv.setLineWidth(0.75)
        canv.line(MARGIN, 747, PAGE_W - MARGIN, 747)
        canv.line(MARGIN, 43, PAGE_W - MARGIN, 43)
        canv.setFillColor(HexColor(muted_hex))
        canv.setFont('ReportMono', 8.0)
        canv.drawString(MARGIN, 761, 'legends-geogrid // tactical battlefield intelligence')
        footer_left = 'SYNTHETIC BATTLEFIELD FIXTURE' if norm['synthetic'] else 'OBSERVATIONAL BATTLEFIELD INTELLIGENCE'
        canv.drawString(MARGIN, 28, footer_left)
        canv.drawCentredString(PAGE_W / 2.0, 28, f'Page {doc.page}')
        canv.restoreState()

    doc = BaseDocTemplate(
        str(pdf_path),
        pagesize=(PAGE_W, PAGE_H),
        title=f"{norm['target_name']}: Tactical Battlefield & Opportunity Report",
        author='legends-geogrid',
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=50,
        bottomMargin=50,
        allowSplitting=1,
    )
    frame = Frame(
        MARGIN,
        50,
        COLUMN,
        690,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    doc.addPageTemplates(PageTemplate(id='battlefield', frames=[frame], onPage=on_page))

    story: list[Any] = []

    # =========================================================================
    # PAGE 1: Executive Battlefield Briefing & Strike-Zone Opportunity Map
    # =========================================================================
    if banner_path.is_file():
        with PILImage.open(banner_path) as bim:
            bw_px, bh_px = bim.size
        target_bh = 38.0
        target_bw = min(COLUMN, target_bh * (bw_px / max(1, bh_px)))
        banner_img = Image(str(banner_path), width=target_bw, height=target_bh)
        banner_img.hAlign = 'LEFT'
        story.append(banner_img)
        story.append(Spacer(1, 4))

    story.append(p('EXECUTIVE BATTLEFIELD BRIEFING // GEOGRID-BATTLEFIELD/V1', 'eyebrow'))
    story.append(p(f"{norm['target_name']}: Tactical Battlefield & Opportunity Report", 'title'))

    subtitle_line = (
        f"LOCATION: {norm['location']}  |  GRID: {norm['grid_dimensions']}  |  "
        f"LANES: {len(norm['lanes'])}  |  COMPETITOR FACTIONS ANALYZED: {norm['total_competitors_analyzed']}"
    )
    story.append(p(subtitle_line, 'subtitle'))

    # Headline summary box
    headline_tbl = Table(
        [[p_markup(f"<b>COMMAND BRIEFING:</b> {escape(norm['campaign_orders']['headline_summary'])}", 'body')]],
        colWidths=[COLUMN],
    )
    headline_tbl.setStyle(
        TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), HexColor(card_bg_hex)),
            ('BOX', (0, 0), (-1, -1), 0.75, HexColor(line_hex)),
            ('LINEBEFORE', (0, 0), (0, -1), 2.5, HexColor(accent_hex)),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ])
    )
    story.append(headline_tbl)
    story.append(Spacer(1, 5))

    # Figure 1 (516 x 380 pt)
    story.append(Image(str(opp_map_path), width=MAP_W, height=MAP_H))
    story.append(Spacer(1, 5))

    # Tactical Telemetry Strip (5 tactical classes + Visibility Coverage %)
    tc = norm['tactical_counts']
    fow = norm['fog_of_war_summary']
    telemetry_headers = [
        p_markup('<font color="#10B981"><b>OWNED STRONGHOLDS</b></font>', 'th'),
        p_markup('<font color="#F59E0B"><b>PRIME STRIKE ZONES</b></font>', 'th'),
        p_markup('<font color="#06B6D4"><b>FLANKING MINES</b></font>', 'th'),
        p_markup('<font color="#EAB308"><b>CONTESTED FRONTS</b></font>', 'th'),
        p_markup('<font color="#EF4444"><b>ENEMY FORTRESSES</b></font>', 'th'),
        p_markup('<b>VISIBILITY COVERAGE</b>', 'th'),
    ]
    telemetry_vals = [
        p_markup(f"<b>{tc.get('OWNED_STRONGHOLD', 0)}</b> tiles (Rank 1-3)", 'td_mono'),
        p_markup(f"<b>{tc.get('PRIME_STRIKE_ZONE', 0)}</b> tiles (Score 65+)", 'td_mono'),
        p_markup(f"<b>{tc.get('FLANKING_MINE', 0)}</b> tiles (Blind-Spot)", 'td_mono'),
        p_markup(f"<b>{tc.get('CONTESTED_FRONT', 0)}</b> tiles (Score 38-64)", 'td_mono'),
        p_markup(f"<b>{tc.get('ENEMY_FORTRESS', 0)}</b> tiles (Score &lt;38)", 'td_mono'),
        p_markup(f"<b>{fow['visibility_coverage_pct']:.1f}%</b> ({len(norm['points']) - fow['dark_zone_tiles']}/{len(norm['points'])})", 'td_mono'),
    ]
    col_w6 = COLUMN / 6.0
    telemetry_tbl = Table([telemetry_headers, telemetry_vals], colWidths=[col_w6] * 6)
    telemetry_tbl.setStyle(
        TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor(header_bg_hex)),
            ('BACKGROUND', (0, 1), (-1, 1), HexColor(card_bg_hex)),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor(line_hex)),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ])
    )
    story.append(telemetry_tbl)

    # =========================================================================
    # PAGE 2: Sovereign Turf & Fog of War Cartography
    # =========================================================================
    story.append(PageBreak())
    story.append(p('TERRITORIAL CARTOGRAPHY // CITADEL HQs & RECONNAISSANCE VISION', 'eyebrow'))
    story.append(p('Sovereign Territory Control & Fog of War Analysis', 'section'))
    story.append(
        p(
            'Coordinates are shaded by controlling faction (Rank #1 / Top-3 leader). Hatched red/slate rings mark Dark Zone blind spots where the Target is unranked while rival factions capture local demand.',
            'caption',
        )
    )

    # Figure 2 (516 x 380 pt)
    story.append(Image(str(turf_map_path), width=MAP_W, height=MAP_H))
    story.append(Spacer(1, 5))

    # Fog of War Breakdown Strip
    story.append(p('Fog of War Reconnaissance Breakdown', 'subhead'))
    fow_headers = [
        p_markup('<font color="#10B981"><b>CLEARED CITADEL (RANK 1-3)</b></font>', 'th'),
        p_markup('<font color="#F59E0B"><b>CONTESTED VISION (RANK 4-10)</b></font>', 'th'),
        p_markup('<font color="#EAB308"><b>SUPPRESSED SECTOR (RANK 11-20)</b></font>', 'th'),
        p_markup('<font color="#EF4444"><b>DARK ZONE (NOT RETURNED / 20+)</b></font>', 'th'),
    ]
    tot_p = max(1, len(norm['points']))
    fow_vals = [
        p_markup(
            f"<b>{fow['cleared_citadel_tiles']} tiles ({100.0 * fow['cleared_citadel_tiles'] / tot_p:.1f}%)</b><br/>Active Map Pack dominance; high line-of-sight.",
            'td',
        ),
        p_markup(
            f"<b>{fow['contested_vision_tiles']} tiles ({100.0 * fow['contested_vision_tiles'] / tot_p:.1f}%)</b><br/>Near-miss strike range; prime conversion tier.",
            'td',
        ),
        p_markup(
            f"<b>{fow['suppressed_tiles']} tiles ({100.0 * fow['suppressed_tiles'] / tot_p:.1f}%)</b><br/>Deep SERP suppression; requires authority surge.",
            'td',
        ),
        p_markup(
            f"<b>{fow['dark_zone_tiles']} tiles ({100.0 * fow['dark_zone_tiles'] / tot_p:.1f}%)</b><br/>Zero target visibility; unchallenged rival turf.",
            'td',
        ),
    ]
    fow_tbl = Table([fow_headers, fow_vals], colWidths=[COLUMN / 4.0] * 4)
    fow_tbl.setStyle(
        TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor(header_bg_hex)),
            ('BACKGROUND', (0, 1), (-1, 1), HexColor(card_bg_hex)),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor(line_hex)),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ])
    )
    story.append(fow_tbl)
    story.append(Spacer(1, 4))

    # Gravity Anomalies Table
    story.append(p('Proximity-Defiance & Gravity Anomalies (Distant Rivals Ranking Top 3)', 'subhead'))
    anoms = norm['gravity_anomalies']
    if anoms:
        anom_rows = [[
            p('Pin / Sector', 'th'),
            p('Rival Faction', 'th'),
            p('Rank', 'th'),
            p('Dist from Rival HQ', 'th'),
            p('Proximity-Defiance Evidence', 'th'),
        ]]
        for a in anoms[:3]:
            anom_rows.append([
                p(f"{a['tag']} ({a['sector']})", 'td_mono'),
                p(f"{a.get('faction_id', '')} {a.get('faction_name', 'Rival')}".strip(), 'td_bold'),
                p(f"#{a.get('rank') or '-'}", 'td_mono'),
                p(f"{a.get('distance_from_pin_km', 0.0):.2f} km", 'td_mono'),
                p(a.get('reason') or 'Holds Top 3 beyond 2.5 km while outranking closer local competitors.', 'td'),
            ])
        anom_tbl = Table(anom_rows, colWidths=[64, 115, 36, 76, COLUMN - 291])
        anom_tbl.setStyle(
            TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), HexColor(header_bg_hex)),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor(card_bg_hex), HexColor(card_alt_hex)]),
                ('GRID', (0, 0), (-1, -1), 0.5, HexColor(line_hex)),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                ('TOPPADDING', (0, 0), (-1, -1), 2.5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ])
        )
        story.append(anom_tbl)
    else:
        story.append(
            p(
                'No extreme proximity-defiance anomalies (>2.5 km Top-3 override) detected in this snapshot; rank distribution follows standard geodesic decay around faction citadels.',
                'body',
            )
        )

    # =========================================================================
    # PAGE 3: Top 10 Competitor Intelligence Matrix (The 11-Faction Leaderboard)
    # =========================================================================
    story.append(PageBreak())
    story.append(p('ORDER OF BATTLE // MULTI-FACTION INTELLIGENCE MATRIX', 'eyebrow'))
    story.append(p('11-Faction Competitive Matrix (Target + Top 10 Rivals)', 'section'))
    story.append(
        p(
            'Compares the Target (YOU) against the Top 10 territorial rivals sorted by Territory Dominance Score. SoLV % measures Top-3 appearances across all measured coordinate-lane slots; Reach (km) shows 75th-percentile Top-3 radius.',
            'caption',
        )
    )

    matrix_headers = [
        p('Code', 'th'),
        p('Business Name', 'th'),
        p('Archetype', 'th'),
        p('SoLV %', 'th'),
        p('Top 3', 'th'),
        p('Avg Rank', 'th'),
        p('Reviews', 'th'),
        p('Primary Category', 'th'),
        p('Reach (km)', 'th'),
        p('Primary Vulnerability', 'th'),
    ]
    matrix_rows = [matrix_headers]
    for f in norm['factions'][:11]:
        avg_r_str = f"{f['average_rank']:.1f}" if f['average_rank'] is not None else '-'
        if f['votes_count'] is not None and f['rating'] is not None:
            rev_str = f"{f['votes_count']} ({f['rating']:.1f}*)"
        elif f['votes_count'] is not None:
            rev_str = str(f['votes_count'])
        else:
            rev_str = '-'
        reach_str = f"{f['gravity_radius_km']:.2f}" if f['gravity_radius_km'] else '0.00'
        code_cell = p_markup(f"<font color=\"{f['color']}\"><b>{escape(f['short_code'])}</b></font>", 'td_mono')
        matrix_rows.append([
            code_cell,
            p(f['name'], 'td_bold' if f['is_target'] else 'td'),
            p(f['archetype'].replace('_', ' '), 'td_mono'),
            p(f"{f['solv_pct']:.1f}%", 'td_mono'),
            p(str(f['top3_count']), 'td_mono'),
            p(avg_r_str, 'td_mono'),
            p(rev_str, 'td_mono'),
            p(f['category'], 'td'),
            p(reach_str, 'td_mono'),
            p(f['primary_vulnerability'], 'td'),
        ])

    # Column widths summing exactly to 516 pt (COLUMN)
    col_widths_10 = [26, 78, 64, 34, 25, 31, 42, 60, 32, 124]
    matrix_tbl = Table(matrix_rows, colWidths=col_widths_10, repeatRows=1)
    matrix_tbl.setStyle(
        TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor(header_bg_hex)),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor(card_bg_hex), HexColor(card_alt_hex)]),
            ('BACKGROUND', (0, 1), (-1, 1), HexColor('#E6F4EA' if is_light else '#062E22')),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor(line_hex)),
            ('LEFTPADDING', (0, 0), (-1, -1), 3.0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3.0),
            ('TOPPADDING', (0, 0), (-1, -1), 2.2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.2),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ])
    )
    story.append(matrix_tbl)
    story.append(Spacer(1, 5))

    # Per-Lane Dominance Breakdown
    story.append(p('Per-Lane Dominance & Tactical Breakdown', 'subhead'))
    lane_headers = [
        p('Lane ID', 'th'),
        p('Search Theme / Query', 'th'),
        p('Target SoLV %', 'th'),
        p('Target Avg Rank', 'th'),
        p('Dominant Rival Faction', 'th'),
        p('Strike Zones', 'th'),
        p('Fortresses', 'th'),
    ]
    lane_rows = [lane_headers]
    for l in norm['lanes']:
        l_avg = f"{l['target_avg_rank']:.1f}" if l['target_avg_rank'] is not None else '-'
        lane_rows.append([
            p(l['lane_id'], 'td_mono'),
            p(l['query'], 'td_bold'),
            p(f"{l['target_solv_pct']:.1f}%", 'td_mono'),
            p(l_avg, 'td_mono'),
            p(l['dominant_rival'], 'td'),
            p(str(l['strike_zone_count']), 'td_mono'),
            p(str(l['fortress_count']), 'td_mono'),
        ])

    lane_tbl = Table(lane_rows, colWidths=[42, 148, 56, 56, 118, 48, 48], repeatRows=1)
    lane_tbl.setStyle(
        TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor(header_bg_hex)),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor(card_bg_hex), HexColor(card_alt_hex)]),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor(line_hex)),
            ('LEFTPADDING', (0, 0), (-1, -1), 3.5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3.5),
            ('TOPPADDING', (0, 0), (-1, -1), 2.2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.2),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ])
    )
    story.append(lane_tbl)

    # =========================================================================
    # PAGE 4: Campaign Battle Plan, Strike Corridors & Tech-Tree Unlocks
    # =========================================================================
    story.append(PageBreak())
    story.append(p('CAMPAIGN EXECUTION ORDERS // COUNTER-UNIT PLAYBOOK', 'eyebrow'))
    story.append(p('Tactical Campaign Orders & Counter-Unit Playbook', 'section'))

    # 1. Priority Strike Corridors
    story.append(p('1. Priority Strike Corridors (High-ROI Territorial Offensives)', 'subhead'))
    corridors = norm['campaign_orders']['strike_corridors']
    if corridors:
        corr_rows = [[
            p('Sector / Corridor', 'th'),
            p('Avg Opp Score', 'th'),
            p('Target Ranks', 'th'),
            p('Vulnerable Incumbent', 'th'),
            p('Recommended Tactical Order', 'th'),
        ]]
        for c in corridors:
            corr_rows.append([
                p_markup(f"<b>{escape(c['sector'])}</b>: {escape(c['title'])}<br/><font size=\"6.8\">{escape(c['tiles_str'])}</font>", 'td'),
                p_markup(f"<font color=\"#F59E0B\"><b>{c['avg_opportunity_score']:.1f}</b></font>", 'td_mono'),
                p(c['target_ranks'], 'td_mono'),
                p(c['vulnerable_incumbent'], 'td'),
                p(c['recommended_order'], 'td'),
            ])
        corr_tbl = Table(corr_rows, colWidths=[106, 52, 52, 114, COLUMN - 324], repeatRows=1)
        corr_tbl.setStyle(
            TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), HexColor(header_bg_hex)),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor(card_bg_hex), HexColor(card_alt_hex)]),
                ('GRID', (0, 0), (-1, -1), 0.5, HexColor(line_hex)),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 2.5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ])
        )
        story.append(corr_tbl)
    else:
        story.append(p('No high-opportunity strike corridors identified in current grid.', 'body'))

    story.append(Spacer(1, 4))

    # 2. Tech-Tree & Category Unlocks
    story.append(p('2. Tech-Tree & Category Unlocks (Capability & Review Troop Gaps)', 'subhead'))
    unlocks = norm['campaign_orders']['tech_tree_unlocks']
    if unlocks:
        unlock_rows = [[
            p('Unlock Class', 'th'),
            p('Capability / Target Unlock', 'th'),
            p('Rival Adoption & SoLV', 'th'),
            p('Evidence & Impact Rationale', 'th'),
        ]]
        for u in unlocks:
            solv_note = f" (Avg SoLV {u['rivals_solv_avg']:.1f}%)" if u['rivals_solv_avg'] > 0 else ''
            unlock_rows.append([
                p(u['unlock_type'].replace('_', ' '), 'td_mono'),
                p(u['name'], 'td_bold'),
                p(f"{u['used_by_rivals']}{solv_note}", 'td'),
                p(u['impact_rationale'], 'td'),
            ])
        unlock_tbl = Table(unlock_rows, colWidths=[88, 118, 110, COLUMN - 316], repeatRows=1)
        unlock_tbl.setStyle(
            TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), HexColor(header_bg_hex)),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor(card_bg_hex), HexColor(card_alt_hex)]),
                ('GRID', (0, 0), (-1, -1), 0.5, HexColor(line_hex)),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 2.5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ])
        )
        story.append(unlock_tbl)
    else:
        story.append(p('No immediate category or tech-tree gaps detected against Top 10 rivals.', 'body'))

    story.append(Spacer(1, 4))

    # 3. Fortress Warnings & Next-Turn Recon Probes
    story.append(p('3. Fortress Warnings & Next-Turn Reconnaissance Probes', 'subhead'))
    fwarnings = norm['campaign_orders']['fortress_warnings']
    if fwarnings:
        fw_rows = [[
            p('Sector / Tiles', 'th'),
            p('Fortified Incumbent', 'th'),
            p('Budget Preservation & Flanking Directive', 'th'),
        ]]
        for fw in fwarnings:
            sec_lbl = f"{fw['sector']} ({fw['tiles_str']})" if fw['tiles_str'] != '-' else fw['sector']
            fw_rows.append([
                p(sec_lbl, 'td_mono'),
                p(fw['faction_name'], 'td_bold'),
                p(fw['warning'], 'td'),
            ])
        fw_tbl = Table(fw_rows, colWidths=[92, 124, COLUMN - 216], repeatRows=1)
        fw_tbl.setStyle(
            TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), HexColor(header_bg_hex)),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor(card_bg_hex), HexColor(card_alt_hex)]),
                ('GRID', (0, 0), (-1, -1), 0.5, HexColor(line_hex)),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 2.5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ])
        )
        story.append(fw_tbl)
    else:
        story.append(p('No high-attrition enemy fortresses flagged; all contested sectors remain open to flanking operations.', 'body'))

    story.append(Spacer(1, 4))

    probes = norm['campaign_orders']['next_turn_recon_probes']
    if probes:
        pr_rows = [[
            p('Probe Type', 'th'),
            p('Recon Target', 'th'),
            p('Tactical Objective', 'th'),
            p('Recommended CLI Probe Command', 'th'),
        ]]
        for pr in probes[:5]:
            pr_rows.append([
                p(pr['probe_type'].replace('_', ' '), 'td_mono'),
                p(pr['target_name'], 'td_bold'),
                p(pr['rationale'], 'td'),
                p(pr['cli_command'], 'td_mono'),
            ])
        pr_tbl = Table(pr_rows, colWidths=[86, 98, 132, COLUMN - 316], repeatRows=1)
        pr_tbl.setStyle(
            TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), HexColor(header_bg_hex)),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor(card_bg_hex), HexColor(card_alt_hex)]),
                ('GRID', (0, 0), (-1, -1), 0.5, HexColor(line_hex)),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 2.5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ])
        )
        story.append(pr_tbl)

    doc.build(story)
    add_pdf_brand_links(pdf_path)


def _render_battlefield_html(
    norm: dict[str, Any],
    html_path: Path,
    opp_map_name: str,
    turf_map_name: str,
    theme: str,
) -> None:
    """Write printable HTML (battlefield-report.html) matching the 4-page PDF report."""
    output_dir = html_path.parent
    prepare_html_font(output_dir, theme)
    prepare_banner(output_dir, theme)

    tc = norm['tactical_counts']
    fow = norm['fog_of_war_summary']

    extra_css = """
    .telemetry-band{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin:20px 0}
    .telemetry-cell{border:1px solid #404040;padding:12px}
    .telemetry-cell strong{display:block;font-size:22px;line-height:1.2}
    .telemetry-cell span{display:block;font-size:12px;margin-top:4px; opacity:0.85}
    .fow-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:20px 0}
    .faction-badge{display:inline-block;padding:2px 6px;border-radius:3px;font-weight:700;font-size:12px;color:#000}
    @media(max-width:750px){.telemetry-band{grid-template-columns:repeat(2,1fr)}.fow-grid{grid-template-columns:repeat(2,1fr)}}
    """

    parts = [
        '<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>{escape(norm['target_name'])}: Tactical Battlefield &amp; Opportunity Report</title>",
        f'<style>{html_styles(theme)}{extra_css}</style></head>',
        f'<body><main data-design="{DESIGN_VERSION}" data-stage="battlefield">{BRAND_TOP}',
        '<header class="report-cover">',
        '<img class="banner" src="banner.png" alt="legends-geogrid">',
        '<p class="eyebrow">executive battlefield briefing // geogrid-battlefield/v1</p>',
        f"<h1>{escape(norm['target_name'])}: Tactical Battlefield &amp; Opportunity Report</h1>",
        f"<p class=\"mono\">Location: {escape(norm['location'])} | Grid: {escape(norm['grid_dimensions'])} | Lanes: {len(norm['lanes'])} | Competitor Factions Analyzed: {norm['total_competitors_analyzed']}</p>",
        f"<div class=\"notice\"><p><strong>Command Briefing:</strong> {escape(norm['campaign_orders']['headline_summary'])}</p></div>",
        f'<figure class="report-map"><img src="{escape(opp_map_name)}" alt="Strike-Zone Opportunity Map">',
        '<figcaption>Figure 1: Strike-Zone Opportunity Matrix. Coordinate markers display Opportunity Score (0-100); double target rings mark Prime Strike Zones (65+).</figcaption></figure>',
        '<div class="telemetry-band">',
        f"<div class=\"telemetry-cell\"><strong>{tc.get('OWNED_STRONGHOLD', 0)}</strong><span>Owned Strongholds</span></div>",
        f"<div class=\"telemetry-cell\"><strong>{tc.get('PRIME_STRIKE_ZONE', 0)}</strong><span>Prime Strike Zones</span></div>",
        f"<div class=\"telemetry-cell\"><strong>{tc.get('FLANKING_MINE', 0)}</strong><span>Flanking Mines</span></div>",
        f"<div class=\"telemetry-cell\"><strong>{tc.get('CONTESTED_FRONT', 0)}</strong><span>Contested Fronts</span></div>",
        f"<div class=\"telemetry-cell\"><strong>{tc.get('ENEMY_FORTRESS', 0)}</strong><span>Enemy Fortresses</span></div>",
        f"<div class=\"telemetry-cell\"><strong>{fow['visibility_coverage_pct']:.1f}%</strong><span>Visibility Coverage</span></div>",
        '</div></header>',
    ]

    # Section 2: Sovereign Turf & Fog of War
    parts += [
        '<section class="report-section" id="sovereign-turf">',
        '<p class="eyebrow">cartography layer 02 // territorial sovereignty</p>',
        '<h2>Sovereign Territory Control &amp; Fog of War Analysis</h2>',
        f'<figure class="report-map"><img src="{escape(turf_map_name)}" alt="Sovereign Turf and Fog of War Map">',
        '<figcaption>Figure 2: Sovereign Territory Control and Citadel HQs. Hatched rings indicate Dark Zone coordinates where the Target has zero visibility.</figcaption></figure>',
        '<div class="fow-grid">',
        f"<div class=\"telemetry-cell\"><strong>{fow['cleared_citadel_tiles']}</strong><span>Cleared Citadel (Rank 1-3)</span></div>",
        f"<div class=\"telemetry-cell\"><strong>{fow['contested_vision_tiles']}</strong><span>Contested Vision (Rank 4-10)</span></div>",
        f"<div class=\"telemetry-cell\"><strong>{fow['suppressed_tiles']}</strong><span>Suppressed Sector (Rank 11-20)</span></div>",
        f"<div class=\"telemetry-cell\"><strong>{fow['dark_zone_tiles']}</strong><span>Dark Zone (Not Returned)</span></div>",
        '</div>',
        '<h3>Detected Proximity-Defiance &amp; Gravity Anomalies</h3>',
    ]
    if norm['gravity_anomalies']:
        parts.append('<table><thead><tr><th>Pin / Sector</th><th>Rival Faction</th><th>Rank</th><th>Dist from HQ</th><th>Evidence</th></tr></thead><tbody>')
        for a in norm['gravity_anomalies'][:8]:
            parts.append(
                f"<tr><td>{escape(a['tag'])} ({escape(a['sector'])})</td>"
                f"<td>{escape(a.get('faction_id', ''))} {escape(a.get('faction_name', ''))}</td>"
                f"<td>#{a.get('rank') or '-'}</td>"
                f"<td>{a.get('distance_from_pin_km', 0.0):.2f} km</td>"
                f"<td>{escape(a.get('reason') or 'Distant Top-3 rank overriding closer competitors')}</td></tr>"
            )
        parts.append('</tbody></table>')
    else:
        parts.append('<p>No extreme proximity-defiance anomalies (&gt;2.5 km Top-3 override) detected in this snapshot.</p>')
    parts.append('</section>')

    # Section 3: 11-Faction Competitive Matrix
    parts += [
        '<section class="report-section" id="competitive-matrix">',
        '<p class="eyebrow">order of battle // 11-faction leaderboard</p>',
        '<h2>11-Faction Competitive Matrix (Target + Top 10 Rivals)</h2>',
        '<div class="scroll"><table class="visibility-table"><thead><tr>',
        '<th>Code</th><th>Business Name</th><th>Archetype</th><th>SoLV %</th><th>Top 3</th><th>Avg Rank</th><th>Reviews</th><th>Primary Category</th><th>Reach (km)</th><th>Primary Vulnerability</th>',
        '</tr></thead><tbody>',
    ]
    for f in norm['factions'][:11]:
        avg_r_str = f"{f['average_rank']:.1f}" if f['average_rank'] is not None else '-'
        rev_str = f"{f['votes_count']} ({f['rating']:.1f}*)" if (f['votes_count'] is not None and f['rating'] is not None) else (str(f['votes_count']) if f['votes_count'] is not None else '-')
        parts.append(
            f"<tr><td><span class=\"faction-badge\" style=\"background:{escape(f['color'])}\">{escape(f['short_code'])}</span></td>"
            f"<td><strong>{escape(f['name'])}</strong></td>"
            f"<td>{escape(f['archetype'])}</td>"
            f"<td>{f['solv_pct']:.1f}%</td>"
            f"<td>{f['top3_count']}</td>"
            f"<td>{avg_r_str}</td>"
            f"<td>{escape(rev_str)}</td>"
            f"<td>{escape(f['category'])}</td>"
            f"<td>{f['gravity_radius_km']:.2f}</td>"
            f"<td>{escape(f['primary_vulnerability'])}</td></tr>"
        )
    parts.append('</tbody></table></div>')

    parts += [
        '<h3>Per-Lane Dominance Breakdown</h3>',
        '<table><thead><tr><th>Lane ID</th><th>Search Theme / Query</th><th>Target SoLV %</th><th>Target Avg Rank</th><th>Dominant Rival</th><th>Strike Zones</th><th>Fortresses</th></tr></thead><tbody>',
    ]
    for l in norm['lanes']:
        l_avg = f"{l['target_avg_rank']:.1f}" if l['target_avg_rank'] is not None else '-'
        parts.append(
            f"<tr><td>{escape(l['lane_id'])}</td><td>{escape(l['query'])}</td>"
            f"<td>{l['target_solv_pct']:.1f}%</td><td>{l_avg}</td>"
            f"<td>{escape(l['dominant_rival'])}</td><td>{l['strike_zone_count']}</td><td>{l['fortress_count']}</td></tr>"
        )
    parts.append('</tbody></table></section>')

    # Section 4: Campaign Battle Plan
    parts += [
        '<section class="report-section" id="campaign-orders">',
        '<p class="eyebrow">operational directives // counter-unit playbook</p>',
        '<h2>Tactical Campaign Orders &amp; Counter-Unit Playbook</h2>',
        '<h3>1. Priority Strike Corridors</h3>',
    ]
    if norm['campaign_orders']['strike_corridors']:
        parts.append('<table><thead><tr><th>Sector / Corridor</th><th>Avg Opportunity Score</th><th>Target Ranks</th><th>Vulnerable Incumbent</th><th>Recommended Order</th></tr></thead><tbody>')
        for c in norm['campaign_orders']['strike_corridors']:
            parts.append(
                f"<tr><td><strong>{escape(c['sector'])}</strong>: {escape(c['title'])} ({escape(c['tiles_str'])})</td>"
                f"<td>{c['avg_opportunity_score']:.1f}</td><td>{escape(c['target_ranks'])}</td>"
                f"<td>{escape(c['vulnerable_incumbent'])}</td><td>{escape(c['recommended_order'])}</td></tr>"
            )
        parts.append('</tbody></table>')
    else:
        parts.append('<p>No priority strike corridors identified.</p>')

    parts.append('<h3>2. Tech-Tree &amp; Category Unlocks</h3>')
    if norm['campaign_orders']['tech_tree_unlocks']:
        parts.append('<table><thead><tr><th>Unlock Type</th><th>Capability / Name</th><th>Used By Rivals</th><th>Impact Rationale</th></tr></thead><tbody>')
        for u in norm['campaign_orders']['tech_tree_unlocks']:
            parts.append(
                f"<tr><td>{escape(u['unlock_type'])}</td><td><strong>{escape(u['name'])}</strong></td>"
                f"<td>{escape(u['used_by_rivals'])}</td><td>{escape(u['impact_rationale'])}</td></tr>"
            )
        parts.append('</tbody></table>')
    else:
        parts.append('<p>No category or capability gaps detected.</p>')

    parts.append('<h3>3. Fortress Warnings &amp; Next-Turn Recon Probes</h3>')
    for fw in norm['campaign_orders']['fortress_warnings']:
        parts.append(f"<p><strong>Fortress Warning ({escape(fw['sector'])} - {escape(fw['faction_name'])}):</strong> {escape(fw['warning'])}</p>")
    if norm['campaign_orders']['next_turn_recon_probes']:
        parts.append('<table><thead><tr><th>Probe Type</th><th>Target</th><th>Rationale</th><th>CLI Command</th></tr></thead><tbody>')
        for pr in norm['campaign_orders']['next_turn_recon_probes']:
            parts.append(
                f"<tr><td>{escape(pr['probe_type'])}</td><td>{escape(pr['target_name'])}</td>"
                f"<td>{escape(pr['rationale'])}</td><td class=\"mono\">{escape(pr['cli_command'])}</td></tr>"
            )
        parts.append('</tbody></table>')

    parts.append(f'</section><footer><p><a href="{escape(html_path.with_suffix(".pdf").name)}">Download Printable PDF Report</a></p>{BRAND_BOTTOM}</footer></main></body></html>')

    html_text = clean_text('\n'.join(parts))
    if FORBIDDEN_EM_DASH in html_text:
        raise ValueError('Generated HTML contains forbidden em dash')
    html_path.write_text(html_text + '\n', encoding='utf-8')


def verify_battlefield_pdf(pdf_path: Path) -> dict[str, Any]:
    """Verify PDF page count >= 4, zero em dashes, and clean bitmap rendering via pypdf and pypdfium2."""
    from pypdf import PdfReader
    import pypdfium2 as pdfium

    reader = PdfReader(str(pdf_path))
    page_count = len(reader.pages)
    if page_count < 4:
        raise ValueError(f'Expected at least 4 pages in battlefield PDF, got {page_count}')

    for idx, page in enumerate(reader.pages):
        txt = page.extract_text() or ''
        if FORBIDDEN_EM_DASH in txt:
            raise ValueError(f'Forbidden em dash detected via pypdf on page {idx + 1}')

    rendered_pages = []
    with pdfium.PdfDocument(str(pdf_path)) as doc:
        if len(doc) < 4:
            raise ValueError(f'pypdfium2 reported {len(doc)} pages, expected >= 4')
        for i in range(len(doc)):
            page = doc[i]
            w, h = page.get_size()
            if (round(w, 1), round(h, 1)) != (PAGE_W, PAGE_H):
                raise ValueError(f'Page {i + 1} dimensions {(w, h)} do not match Letter {(PAGE_W, PAGE_H)}')
            tp = page.get_textpage()
            contents = tp.get_text_range()
            if FORBIDDEN_EM_DASH in contents:
                raise ValueError(f'Forbidden em dash detected via pypdfium2 on page {i + 1}')
            bitmap = page.render(scale=0.5)
            pil_img = bitmap.to_pil().convert('RGB')
            if pil_img.size[0] <= 0 or pil_img.size[1] <= 0:
                raise ValueError(f'Page {i + 1} failed bitmap rendering')
            rendered_pages.append({'page': i + 1, 'chars': len(contents), 'bitmap_size': list(pil_img.size)})
            bitmap.close()
            tp.close()
            page.close()

    return {'status': 'passed', 'pages': page_count, 'rendered_pages': rendered_pages}


def render_battlefield_pdf(
    model: dict[str, Any] | str | Path,
    pdf_path: str | Path,
    theme: str = DEFAULT_THEME,
) -> dict[str, Any]:
    """Render cartography figures, Letter PDF, and printable HTML, returning a receipt dict."""
    if theme not in THEMES:
        raise ValueError(f'Unsupported theme: {theme}. Expected one of {tuple(THEMES)}')

    if isinstance(model, (str, Path)):
        raw_model = json.loads(Path(model).read_text(encoding='utf-8-sig'))
    else:
        raw_model = model

    norm = normalize_battlefield_model(raw_model)
    pdf_file = Path(pdf_path).resolve()
    out_dir = pdf_file.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    html_file = out_dir / 'battlefield-report.html'
    opp_map_path = out_dir / 'battlefield-opportunity-map.png'
    turf_map_path = out_dir / 'battlefield-turf-map.png'

    fonts = register_report_fonts()
    banner_path = prepare_banner(out_dir, theme)

    render_opportunity_map(norm, opp_map_path, fonts, theme=theme)
    render_turf_map(norm, turf_map_path, fonts, theme=theme)

    _build_pdf_document(norm, pdf_file, banner_path, opp_map_path, turf_map_path, theme=theme)
    _render_battlefield_html(norm, html_file, opp_map_path.name, turf_map_path.name, theme=theme)

    qa = verify_battlefield_pdf(pdf_file)

    return {
        'pdf': str(pdf_file),
        'html': str(html_file),
        'pages': qa['pages'],
        'figures': [str(opp_map_path), str(turf_map_path)],
        'qa': qa,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, type=Path, help='Path to battlefield-model.json (geogrid-battlefield/v1)')
    parser.add_argument('--output-dir', required=True, type=Path, help='Output directory for PDF, HTML, and map PNGs')
    parser.add_argument('--theme', choices=tuple(THEMES), default=DEFAULT_THEME, help='Presentation theme (geogrid dark or light)')
    args = parser.parse_args(argv)

    try:
        raw = json.loads(args.model.resolve().read_text(encoding='utf-8-sig'))
        out_dir = args.output_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = out_dir / 'battlefield-report.pdf'
        receipt = render_battlefield_pdf(raw, pdf_path, theme=args.theme)
    except Exception as exc:
        print(f'Battlefield report failed: {exc}', file=sys.stderr)
        return 2

    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
