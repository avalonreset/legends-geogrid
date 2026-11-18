#!/usr/bin/env python3
"""Offline config-driven strategy report. See examples/reports/README.md."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
from html import escape
import json
import math
from pathlib import Path
import sys
import tempfile

from report_model import finding, inside, load_config, require
from report_design import BRAND_TOP, BRAND_BOTTOM, add_pdf_brand_links, DESIGN_VERSION, THEMES, PAGE_W, PAGE_H, MARGIN, COLUMN, html_styles, legends_font, prepare_html_font

THEME = 'geogrid'
HEADER_COLORS = ('#CC0000', '#8C0000', '#111111', '#777777', '#FFFFFF')
DEFAULT_THEME = 'geogrid'
THEME_FONTS = Path(__file__).parent / 'fonts'


def apply_theme(name):
    global THEME
    THEME = name
    globals().update(THEMES[name])


apply_theme(DEFAULT_THEME)
MAP_W, MAP_H, SCALE = 516, 410, 3
LEGEND = 'Ranks 1–3: green | Ranks 4–10: yellow | Ranks 11+: red | Hollow: not returned | E: error | Ø: empty | U: unmeasured'
RANK_COLORS = ('#00FF00', '#FFFF00', '#FF0000')
LIMITS = ('Measured means found or not returned. Empty, error, and unmeasured origins are excluded. '
          'Top-3 and top-10 shares are observed appearances divided by valid measured origins; '
          'they are not area or market coverage. A requested depth or returned count alone does not '
          'prove absence at a cutoff. Near misses are exactly ranks 4–10 inclusive. '
          'Results describe supplied origins and timestamps only; no sampled boundary proves total absence.')

# Web Companion exact geometry & 30-stop rank palette (matching src/map-geometry.js, src/study-model.js, src/rank-canvas.js)
OCTAGON_CUT = 1.0 / (2.0 + math.sqrt(2.0))
STOP_SIGN_SCALE = 0.30
DIAMOND_HALF = STOP_SIGN_SCALE * OCTAGON_CUT
OCTAGON_VERTICES = (
    (OCTAGON_CUT, 0.0),
    (1.0 - OCTAGON_CUT, 0.0),
    (1.0, OCTAGON_CUT),
    (1.0, 1.0 - OCTAGON_CUT),
    (1.0 - OCTAGON_CUT, 1.0),
    (OCTAGON_CUT, 1.0),
    (0.0, 1.0 - OCTAGON_CUT),
    (0.0, OCTAGON_CUT),
)
WEB_RANK_RGB = (
    (0, 255, 255),    # 1: #00ffff
    (0, 255, 198),    # 2: #00ffc6
    (0, 255, 142),    # 3: #00ff8e
    (0, 255, 85),     # 4: #00ff55
    (0, 255, 28),     # 5: #00ff1c
    (28, 255, 0),     # 6: #1cff00
    (85, 255, 0),     # 7: #55ff00
    (142, 255, 0),    # 8: #8eff00
    (198, 255, 0),    # 9: #c6ff00
    (255, 255, 0),    # 10: #ffff00
) + ((255, 0, 0),) * 20
WEB_RANK_OPACITY = tuple(
    [1.0 - i / 36.0 for i in range(10)]
    + [0.02 + (0.25 - 0.02) * (29 - i) / 19.0 for i in range(10, 30)]
)


def display_text(value):
    """Normalize display punctuation only; raw evidence and matching stay intact."""
    return value.replace('\u2014', ' - ')


def marker_style(state, rank):
    if state == 'not_returned':
        return None, MUTED
    if state != 'found':
        return '#263745', '#FFFFFF' if THEME == 'light' else MUTED
    return RANK_COLORS[0 if rank <= 3 else 1 if rank <= 10 else 2], '#000000' if rank <= 10 else '#FFFFFF'


def marker_label(state, rank):
    return str(rank) if state == 'found' else {'not_returned':'','error':'E','empty':'Ø','unmeasured':'U'}[state]


def marker_outline(state):
    # A one-point neutral ring stays legible over streets without filling a
    # not-returned origin or increasing its geographic footprint.
    return (MUTED, SCALE) if state == 'not_returned' else (INK if state == 'found' else LINE, 2)


def _grid_spacing_px(points_px):
    """Estimate nearest-neighbor spacing in pixels across visible origins."""
    n = len(points_px)
    if n < 4:
        return None
    dists = []
    for i in range(n):
        ax, ay = points_px[i]
        best = None
        for j in range(n):
            if i == j:
                continue
            d = math.hypot(ax - points_px[j][0], ay - points_px[j][1])
            if d > 0.5 and (best is None or d < best):
                best = d
        if best is not None:
            dists.append(best)
    if not dists:
        return None
    dists.sort()
    return dists[len(dists) // 2]


def _is_dense_lattice(n_points, grid_step_px):
    """True for 2D GeoGrid lattices (7x7 through 39x39+) with regular spacing."""
    return bool(n_points >= 36 and grid_step_px is not None and 6.0 <= grid_step_px <= 220.0)


def _web_cell_rgba(state, rank):
    """Exact Web Companion cell fill color + opacity (src/study-model.js)."""
    if state != 'found' or rank is None:
        return (0, 0, 0, 0)
    idx = max(0, min(29, int(rank) - 1))
    r, g, b = WEB_RANK_RGB[idx]
    alpha = round(255.0 * WEB_RANK_OPACITY[idx])
    return (r, g, b, alpha)


def _blend_color_rgba(corners, u, v):
    """Premultiplied bilinear blend matching blendColor() in src/map-geometry.js."""
    w0 = (1.0 - u) * (1.0 - v)
    w1 = u * (1.0 - v)
    w2 = (1.0 - u) * v
    w3 = u * v
    weights = (w0, w1, w2, w3)
    alpha = sum(c[3] * w for c, w in zip(corners, weights))
    if alpha <= 0.5:
        return (0, 0, 0, 0)
    r = round(sum(c[0] * c[3] * w for c, w in zip(corners, weights)) / alpha)
    g = round(sum(c[1] * c[3] * w for c, w in zip(corners, weights)) / alpha)
    b = round(sum(c[2] * c[3] * w for c, w in zip(corners, weights)) / alpha)
    return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)), max(0, min(255, round(alpha))))


def _cluster_axis_coords(values, tolerance):
    """Group 1D coordinates within tolerance into sorted canonical row/col centers."""
    if not values:
        return []
    vals = sorted(values)
    clusters = [[vals[0]]]
    for v in vals[1:]:
        if v - clusters[-1][-1] <= tolerance:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [sum(c) / len(c) for c in clusters]


_DIAMOND_PATCH_CACHE = {}


def _get_diamond_patch(corners_rgba, d_size_px):
    """Render and cache a 45-degree bilinear gradient diamond sprite matching drawBlends()."""
    from PIL import Image
    q_size = max(4.0, round(d_size_px * 2.0) / 2.0)
    key = (corners_rgba, q_size)
    if key in _DIAMOND_PATCH_CACHE:
        return _DIAMOND_PATCH_CACHE[key]
    box_px = int(math.ceil(q_size)) + 4
    if box_px % 2 == 1:
        box_px += 1
    half_box = box_px / 2.0
    half_d = q_size / 2.0
    im = Image.new('RGBA', (box_px, box_px), (0, 0, 0, 0))
    px = im.load()
    for py in range(box_px):
        dy = (py + 0.5) - half_box
        for x_i in range(box_px):
            dx = (x_i + 0.5) - half_box
            manhattan = abs(dx) + abs(dy)
            if manhattan > half_d + 0.75:
                continue
            u = max(0.0, min(1.0, (dx + half_d) / max(1e-6, q_size)))
            v = max(0.0, min(1.0, (dy + half_d) / max(1e-6, q_size)))
            r, g, b, a = _blend_color_rgba(corners_rgba, u, v)
            if manhattan >= half_d - 0.75:
                edge_cov = max(0.0, min(1.0, (half_d + 0.75 - manhattan) / 1.5))
                stroke_a = round(96 * edge_cov * (a / 255.0))
                a = round(a * edge_cov)
                if stroke_a > a:
                    r = round(r * 0.35)
                    g = round(g * 0.35)
                    b = round(b * 0.35)
                    a = stroke_a
            if a > 0:
                px[x_i, py] = (r, g, b, a)
    if len(_DIAMOND_PATCH_CACHE) > 2048:
        _DIAMOND_PATCH_CACHE.clear()
    _DIAMOND_PATCH_CACHE[key] = im
    return im


_DOMINANCE_SPRITES = None


def _get_dominance_sprites():
    """Build the 96x96 cyan halo and 4-pointed white/cyan sparkle sprites (src/rank-canvas.js)."""
    global _DOMINANCE_SPRITES
    if _DOMINANCE_SPRITES is not None:
        return _DOMINANCE_SPRITES
    from PIL import Image, ImageDraw
    halo = Image.new('RGBA', (96, 96), (0, 0, 0, 0))
    hpx = halo.load()
    for y in range(96):
        for x in range(96):
            r = math.hypot(x - 48.0, y - 48.0) / 48.0
            if r <= 0.34 or r >= 1.0:
                continue
            if r <= 0.48:
                t = (r - 0.34) / (0.48 - 0.34)
                hpx[x, y] = (150, 255, 255, round(255 * 0.85 * t))
            elif r <= 0.64:
                t = (r - 0.48) / (0.64 - 0.48)
                red = round(150 * (1.0 - t))
                alpha = round(255 * (0.85 * (1.0 - t) + 0.55 * t))
                hpx[x, y] = (red, 255, 255, alpha)
            else:
                t = (r - 0.64) / (1.0 - 0.64)
                hpx[x, y] = (0, 255, 255, round(255 * 0.55 * (1.0 - t)))

    sparkle = Image.new('RGBA', (96, 96), (0, 0, 0, 0))
    spx = sparkle.load()
    for y in range(96):
        for x in range(96):
            r = math.hypot(x - 48.0, y - 48.0) / 46.0
            if r >= 1.0:
                continue
            if r <= 0.2:
                t = r / 0.2
                red = round(255 * (1.0 - t) + 180 * t)
                alpha = round(255 * (0.95 * (1.0 - t) + 0.65 * t))
                spx[x, y] = (red, 255, 255, alpha)
            else:
                t = (r - 0.2) / 0.8
                red = round(180 * (1.0 - t))
                alpha = round(255 * 0.65 * (1.0 - t))
                spx[x, y] = (red, 255, 255, alpha)
    sdraw = ImageDraw.Draw(sparkle)
    star_pts = [(48, 2), (55, 41), (94, 48), (55, 55), (48, 94), (41, 55), (2, 48), (41, 41)]
    sdraw.polygon(star_pts, fill=(255, 255, 255, 255))
    _DOMINANCE_SPRITES = (halo, sparkle)
    return _DOMINANCE_SPRITES


def _compute_marker_specs(lane, extent, projection, fonts):
    """Compute deterministic marker geometry and lattice parameters shared by map_image and map_qa."""
    from PIL import Image, ImageDraw, ImageFont
    visible = [(index, row, *projection.point(row['lat'], row['lng']))
               for index, row in enumerate(lane['records']) if inside(row, extent)]
    grid_step_px = _grid_spacing_px([(x, y) for _, _, x, y in visible])
    dense_lattice = _is_dense_lattice(len(visible), grid_step_px)

    std_font = ImageFont.truetype(fonts['bold'], 8 * SCALE)
    measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    if dense_lattice:
        stop_sign_r = round(max(2.0 * SCALE, (grid_step_px * STOP_SIGN_SCALE) / 2.0), 4)
        pin_font_px = 8 * SCALE
    else:
        stop_sign_r = None
        pin_font_px = 8 * SCALE

    markers = []
    for index, row, x, y in visible:
        state, rank = row['state'], row['rank']
        label = marker_label(state, rank)
        box = measure.textbbox((0, 0), label, font=std_font)
        std_r = 4.25 * SCALE if state == 'not_returned' else max(6.5 * SCALE, (box[2] - box[0]) / 2 + 2 * SCALE)
        radius = stop_sign_r if dense_lattice else std_r
        markers.append(dict(
            index=index,
            center_px=[x, y],
            radius_px=radius,
            label=label,
            state=state,
            rank=rank,
            footprint_px=[x - radius, y - radius, x + radius, y + radius],
        ))
    return markers, dense_lattice, grid_step_px, pin_font_px


def _paint_lattice_diamonds(canvas, markers, grid_step_px, clip_polygon_px=None):
    """Paint Web Companion 45-degree bilinear corner-blend diamonds across 2x2 intersections (including partial boundary cells)."""
    from PIL import Image, ImageChops, ImageDraw
    if not markers or not grid_step_px:
        return
    tol = max(1.5, grid_step_px * 0.28)
    cols = _cluster_axis_coords([m['center_px'][0] for m in markers], tol)
    rows = _cluster_axis_coords([m['center_px'][1] for m in markers], tol)
    if len(cols) < 2 or len(rows) < 2:
        return
    # Pad axes by 1 step on each side (singleLatticeIntersections partial=True in src/map-geometry.js)
    rows_pad = [2.0 * rows[0] - rows[1]] + rows + [2.0 * rows[-1] - rows[-2]]
    cols_pad = [2.0 * cols[0] - cols[1]] + cols + [2.0 * cols[-1] - cols[-2]]

    cell_map = {}
    for m in markers:
        mx, my = m['center_px']
        c_idx = min(range(len(cols_pad)), key=lambda i: abs(cols_pad[i] - mx))
        r_idx = min(range(len(rows_pad)), key=lambda i: abs(rows_pad[i] - my))
        if abs(cols_pad[c_idx] - mx) <= tol and abs(rows_pad[r_idx] - my) <= tol:
            cell_map[(r_idx, c_idx)] = m

    overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    max_span = grid_step_px * 1.45
    for r in range(len(rows_pad) - 1):
        dy = abs(rows_pad[r + 1] - rows_pad[r])
        if dy > max_span or dy <= 0:
            continue
        cy = 0.5 * (rows_pad[r] + rows_pad[r + 1])
        for c in range(len(cols_pad) - 1):
            dx = abs(cols_pad[c + 1] - cols_pad[c])
            if dx > max_span or dx <= 0:
                continue
            corners = (
                cell_map.get((r, c)),
                cell_map.get((r, c + 1)),
                cell_map.get((r + 1, c)),
                cell_map.get((r + 1, c + 1)),
            )
            if sum(1 for item in corners if item is not None) < 2:
                continue
            corners_rgba = tuple(
                _web_cell_rgba(item['state'], item['rank']) if item is not None else (0, 0, 0, 0)
                for item in corners
            )
            if all(rgba[3] == 0 for rgba in corners_rgba):
                continue
            cx = 0.5 * (cols_pad[c] + cols_pad[c + 1])
            d_space = min(dx, dy)
            d_size = (d_space if d_space > 0 else grid_step_px) * 2.0 * DIAMOND_HALF
            patch = _get_diamond_patch(corners_rgba, d_size)
            px = round(cx - patch.width / 2.0)
            py = round(cy - patch.height / 2.0)
            overlay.alpha_composite(patch, (px, py))

    if clip_polygon_px and len(clip_polygon_px) >= 3:
        clip_mask = Image.new('L', canvas.size, 0)
        ImageDraw.Draw(clip_mask).polygon([tuple(p) for p in clip_polygon_px], fill=255)
        r_ch, g_ch, b_ch, a_ch = overlay.split()
        overlay = Image.merge('RGBA', (r_ch, g_ch, b_ch, ImageChops.multiply(a_ch, clip_mask)))

    canvas.paste(overlay, (0, 0), overlay)


def _paint_rank_one_dominance(canvas, markers, clip_polygon_px=None):
    """Stamp Web Companion Rank-1 cyan halo and 8-corner white/cyan glints (drawRankOne in src/rank-canvas.js)."""
    from PIL import Image, ImageChops, ImageDraw
    rank1_markers = [m for m in markers if m['state'] == 'found' and m['rank'] == 1]
    if not rank1_markers:
        return
    halo_base, sparkle_base = _get_dominance_sprites()
    layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    scale_cache = {}

    def _scaled_sprite(sprite, diameter_px, alpha_factor):
        d = max(4, round(diameter_px))
        key = (id(sprite), d, round(alpha_factor, 3))
        if key not in scale_cache:
            im = sprite.resize((d, d), Image.Resampling.BILINEAR)
            r_c, g_c, b_c, a_c = im.split()
            a_c = a_c.point(lambda v: max(0, min(255, round(v * alpha_factor))))
            scale_cache[key] = Image.merge('RGBA', (r_c, g_c, b_c, a_c))
        return scale_cache[key]

    for m in rank1_markers:
        cx, cy = m['center_px']
        c_size = m['radius_px'] * 2.0
        halo_r = c_size * 0.82 + min(4.0 * (SCALE / 2.0), c_size * 0.30)
        halo_im = _scaled_sprite(halo_base, halo_r * 2.0, 0.825)
        hx = round(cx - halo_im.width / 2.0)
        hy = round(cy - halo_im.height / 2.0)
        if 0 <= hx < canvas.width - halo_im.width and 0 <= hy < canvas.height - halo_im.height:
            layer.alpha_composite(halo_im, (hx, hy))
        twinkle = 0.55
        arm = max(2.8 * (SCALE / 2.0), min(12.0 * (SCALE / 2.0), c_size * 0.24)) * (0.65 + twinkle * 0.55)
        sp_im = _scaled_sprite(sparkle_base, arm * 2.0, 0.06 + twinkle * 0.94)
        for vx, vy in OCTAGON_VERTICES:
            sx = cx + (vx - 0.5) * c_size * 1.08
            sy = cy + (vy - 0.5) * c_size * 1.08
            px = round(sx - sp_im.width / 2.0)
            py = round(sy - sp_im.height / 2.0)
            if 0 <= px < canvas.width - sp_im.width and 0 <= py < canvas.height - sp_im.height:
                layer.alpha_composite(sp_im, (px, py))

    if clip_polygon_px and len(clip_polygon_px) >= 3:
        clip_mask = Image.new('L', canvas.size, 0)
        ImageDraw.Draw(clip_mask).polygon([tuple(p) for p in clip_polygon_px], fill=255)
        r_ch, g_ch, b_ch, a_ch = layer.split()
        layer = Image.merge('RGBA', (r_ch, g_ch, b_ch, ImageChops.multiply(a_ch, clip_mask)))

    canvas.paste(layer, (0, 0), layer)


def _paint_markers_and_lattice(canvas, markers, dense_lattice, grid_step_px, fonts, mask_draw=None, clip_polygon_px=None):
    """Paint Web Companion stop-sign octagons, gradient diamonds, and Rank-1 sheen identically for map_image and map_qa."""
    from PIL import Image, ImageChops, ImageDraw, ImageFont
    if dense_lattice:
        _paint_lattice_diamonds(canvas, markers, grid_step_px, clip_polygon_px=clip_polygon_px)
        ss = 2
        pin_layer_ss = Image.new('RGBA', (canvas.width * ss, canvas.height * ss), (0, 0, 0, 0))
        pdraw = ImageDraw.Draw(pin_layer_ss)
        for marker in markers:
            state, rank = marker['state'], marker['rank']
            cx, cy = marker['center_px']
            c_size = marker['radius_px'] * 2.0
            verts = [
                (round((cx + (vx - 0.5) * c_size) * ss), round((cy + (vy - 0.5) * c_size) * ss))
                for vx, vy in OCTAGON_VERTICES
            ]
            if state == 'found' and rank is not None:
                fill_rgba = _web_cell_rgba('found', rank)
                pdraw.polygon(verts, fill=fill_rgba)
                pdraw.line(verts + [verts[0]], fill=(0, 0, 0, 128), width=max(2, round(c_size * 0.015 * ss)))
            elif state == 'not_returned':
                stroke_w = max(2, round(min(1.5 * (SCALE / 2.0), max(0.8 * (SCALE / 2.0), c_size * 0.025)) * ss))
                pdraw.line(verts + [verts[0]], fill=(163, 177, 195, 140), width=stroke_w)
            else:
                stroke_w = max(2, round(c_size * 0.025 * ss))
                pdraw.line(verts + [verts[0]], fill=(225, 184, 105, 166), width=stroke_w)
            if mask_draw is not None:
                mask_draw.rectangle(marker['footprint_px'], fill=255)
        pin_layer = pin_layer_ss.resize(canvas.size, Image.Resampling.BILINEAR)
        if clip_polygon_px and len(clip_polygon_px) >= 3:
            clip_mask = Image.new('L', canvas.size, 0)
            ImageDraw.Draw(clip_mask).polygon([tuple(p) for p in clip_polygon_px], fill=255)
            r_ch, g_ch, b_ch, a_ch = pin_layer.split()
            pin_layer = Image.merge('RGBA', (r_ch, g_ch, b_ch, ImageChops.multiply(a_ch, clip_mask)))
        canvas.paste(pin_layer, (0, 0), pin_layer)
        _paint_rank_one_dominance(canvas, markers, clip_polygon_px=clip_polygon_px)
    else:
        font = ImageFont.truetype(fonts['bold'], 8 * SCALE)
        paint = ImageDraw.Draw(canvas)
        for marker in markers:
            rank, state = marker['rank'], marker['state']
            color, ink = marker_style(state, rank)
            outline, stroke = marker_outline(state)
            paint.ellipse(marker['footprint_px'], fill=color, outline=outline, width=stroke)
            paint.text(tuple(marker['center_px']), marker['label'], font=font, fill=ink, anchor='mm')
            if mask_draw is not None:
                mask_draw.ellipse(marker['footprint_px'], fill=255)


def shade_bands(overlay, rings, dense_lattice=False):
    """Distance rings: Web Companion thin strokes on dense lattices (zero milky fill); alternating annuli on schematic/sparse maps."""
    from PIL import ImageDraw
    draw = ImageDraw.Draw(overlay)
    if dense_lattice:
        for idx, ring in enumerate(rings):
            pts = [tuple(p) for p in ring['points_px']]
            if idx == len(rings) - 1 and len(rings) > 1:
                # Outer study boundary ring: dashed #969696 at 65% opacity (matching coverageLayer in src/companion.js)
                for seg_start in range(0, len(pts) - 1, 6):
                    seg = pts[seg_start:min(len(pts), seg_start + 4)]
                    if len(seg) >= 2:
                        draw.line(seg, fill=(150, 150, 150, 166), width=2)
                # Ensure all ring points have deterministic paint for QA
                draw.line(pts, fill=(204, 204, 204, 72), width=2)
            else:
                # Inner distance rings: #cccccc at 40% opacity (matching rangeLayer in src/companion.js)
                draw.line(pts, fill=(204, 204, 204, 102), width=2)
        return
    for i in reversed(range(len(rings))):
        draw.polygon([tuple(p) for p in rings[i]['points_px']], fill=(255,255,255,34 if i % 2 == 0 else 12))
    for ring in rings:
        draw.line([tuple(p) for p in ring['points_px']], fill=(169,189,202,140), width=2)


def display_distance(km, unit='km'):
    """Convert display values only; geodesic inputs and evidence stay in km."""
    require(unit in ('km', 'mi'), 'distance unit must be km or mi')
    return f'{km / 1.609344 if unit == "mi" else km:g}'


def _boxes_overlap(a, b, pad=0.0):
    return not (a[2] + pad < b[0] or a[0] - pad > b[2] or a[3] + pad < b[1] or a[1] - pad > b[3])


def paint_band_labels(canvas, rings, fonts, frame, distance_unit='km', dense_lattice=False):
    from PIL import Image, ImageDraw, ImageFont
    draw = ImageDraw.Draw(canvas)
    if dense_lattice:
        font = ImageFont.truetype(fonts['regular'], round(6.2 * SCALE))
        labels = []
        pill_layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        pdraw = ImageDraw.Draw(pill_layer)
        for r_idx, ring in enumerate(rings):
            label = display_distance(ring['km'], distance_unit) + ' ' + distance_unit
            box = draw.textbbox((0, 0), label, font=font)
            width = (box[2] - box[0]) + 4.0 * SCALE
            height = 7.4 * SCALE
            # When 1 mi and 2 mi rings are both present, place the innermost ring at 135 deg (SE)
            # so it never crowds the 2 mi ring or central city label at 45 deg (NE).
            if r_idx == 0 and len(rings) >= 2 and rings[1]['km'] <= ring['km'] * 2.5:
                candidate_indices = (135, 315, 72, 22, 45, 65)
            else:
                candidate_indices = (45, 72, 22, 135, 315, 65)
            chosen_fp = None
            for idx in candidate_indices:
                rx, ry = ring['points_px'][idx % len(ring['points_px'])]
                fp = [rx - width / 2.0, ry - height / 2.0, rx + width / 2.0, ry + height / 2.0]
                if not contains_box(frame, fp):
                    continue
                if any(_boxes_overlap(fp, prev['footprint_px'], pad=8.0 * SCALE) for prev in labels):
                    continue
                chosen_fp = fp
                break
            if chosen_fp is None:
                rx, ry = ring['points_px'][65]
                fp = [rx - width, ry - height, rx, ry]
                if contains_box(frame, fp) and not any(_boxes_overlap(fp, prev['footprint_px'], pad=3.0 * SCALE) for prev in labels):
                    chosen_fp = fp
            if chosen_fp is not None:
                cx = 0.5 * (chosen_fp[0] + chosen_fp[2])
                cy = 0.5 * (chosen_fp[1] + chosen_fp[3])
                pdraw.rounded_rectangle(chosen_fp, radius=1.5 * SCALE, fill=(11, 11, 11, 217), outline=(115, 115, 115, 120), width=1)
                pdraw.text((cx, cy), label, font=font, fill=(207, 207, 207, 255), anchor='mm')
                labels.append(dict(km=ring['km'], label=label, footprint_px=chosen_fp, font_size_pt=8.5))
        canvas.paste(pill_layer, (0, 0), pill_layer)
        return labels

    font = ImageFont.truetype(fonts['regular'],round(8.5*SCALE))
    labels = []
    for ring in rings:
        label = display_distance(ring['km'],distance_unit)+' '+distance_unit
        box = draw.textbbox((0,0),label,font=font)
        width,height = box[2]-box[0]+6*SCALE,12*SCALE
        x,y = ring['points_px'][65]
        footprint = [x-width,y-height,x,y]
        # A small ring can have insufficient label room; its value remains in
        # the adjacent caption. Never paint beyond the geographic frame.
        if contains_box(frame,footprint):
            draw.rounded_rectangle(footprint,radius=2*SCALE,fill=BG)
            draw.text((x-width/2,y-height/2),label,font=font,fill=INK,anchor='mm')
            labels.append(dict(km=ring['km'],label=label,footprint_px=footprint,font_size_pt=8.5))
    return labels


def street_extent(extent, width, height):
    """Expand, never distort/crop, a viewport to fill a street-map frame.

    Reserve 16pt around the requested bounds for complete marker footprints.
    All expanded bounds are disclosed in the asset ledger.
    """
    from report_model import bounds
    w,s,e,n = extent
    x0,x1,y0,y1 = math.radians(w),math.radians(e),mercator(s),mercator(n)
    scale = min((width-32*SCALE)/(x1-x0), (height-32*SCALE)/(y1-y0))
    cx,cy = (x0+x1)/2,(y0+y1)/2
    return bounds([math.degrees(cx-width/scale/2),unmercator(cy-height/scale/2),
                   math.degrees(cx+width/scale/2),unmercator(cy+height/scale/2)])


def mercator(lat):
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def unmercator(y):
    return math.degrees(2 * math.atan(math.exp(y)) - math.pi / 2)


class Projection:
    """North-up Web Mercator with equal x/y scale and padded letterboxing."""
    def __init__(self, bounds, width=MAP_W * SCALE, height=MAP_H * SCALE, pad=26 * SCALE):
        self.bounds = bounds
        w, s, e, n = bounds
        self.x0, self.x1 = math.radians(w), math.radians(e)
        self.y0, self.y1 = mercator(s), mercator(n)
        self.scale = min((width - 2 * pad) / (self.x1 - self.x0), (height - 2 * pad) / (self.y1 - self.y0))
        self.left = (width - self.scale * (self.x1 - self.x0)) / 2
        self.top = (height - self.scale * (self.y1 - self.y0)) / 2
        self.right = width - self.left
        self.bottom = height - self.top

    def point(self, lat, lng):
        return (self.left + (math.radians(lng) - self.x0) * self.scale,
                self.top + (self.y1 - mercator(lat)) * self.scale)


def register_fonts(model):
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    root = Path(reportlab.__file__).parent / 'fonts'
    default = {'regular': str(root / 'Vera.ttf'), 'bold': str(root / 'VeraBd.ttf')}
    paths = model.get('fonts', default)
    if legends_font():
        paths = {key:str(legends_font()) for key in ('regular','bold','title','mono')}
    paths = dict(paths, title=paths.get('title', paths['regular']))
    paths = dict(paths, mono=paths.get('mono', paths['regular']))
    for key, name in (('regular', 'ReportBody'), ('bold', 'ReportBold'), ('title', 'ReportTitle'), ('mono', 'ReportMono')):
        pdfmetrics.registerFont(TTFont(name, paths[key]))
    pdfmetrics.registerFontFamily('ReportBody', normal='ReportBody', bold='ReportBold', italic='ReportBody', boldItalic='ReportBold')
    # Never silently replace unsupported characters in a business identity or copy.
    strings = [model['business']['name'], model['business']['location'], model['thesis'], model['center_label'], LIMITS, LEGEND]
    strings += model['objectives'] + model['next_actions'] + model['missing_evidence'] + model.get('verification_notes', [])
    for lane in model['lanes']:
        strings += [lane['label'], lane['query'], lane.get('narrative') or '']
        strings += [r['source'] for r in lane['records']]
        strings += [lane['map'].get('basemap', {}).get('attribution', '')]
    for name in ('ReportBody', 'ReportBold', 'ReportTitle'):
        chars = pdfmetrics.getFont(name).face.charToGlyph
        missing = sorted({c for s in strings for c in display_text(s) if not c.isspace() and ord(c) not in chars})
        require(not missing, f'font lacks glyphs {missing[:12]}; supply fonts.regular and fonts.bold with these characters')
    return paths


def georeferenced_image(base, extent, width, height):
    """Resample a north-up image by CRS; no guessed stretching to report bounds."""
    from PIL import Image
    with Image.open(base['path']) as source:
        source.load()
        source = source.convert('RGBA')
    require('credit_strip_px' not in base and base.get('attribution_policy') != 'preserve-bottom-strip',
            'detached credit strips are no longer supported; supply complete-image bounds and protected_bottom_px')
    sw, sh = source.size
    bw, bs, be, bn = base['bounds']
    w, s, e, n = extent
    ymax, ymin = mercator(n), mercator(s)
    def source_xy(x, y):
        lng = w + (e - w) * x / width
        my = ymax - (ymax - ymin) * y / height
        if base['crs'] == 'EPSG:4326':
            sy = (bn - unmercator(my)) / (bn - bs) * sh
        else:
            sy = (mercator(bn) - my) / (mercator(bn) - mercator(bs)) * sh
        return ((lng - bw) / (be - bw) * sw, sy)
    mesh = []
    for y in range(0, height, 8):
        y2 = min(y + 8, height)
        quad = (*source_xy(0, y), *source_xy(0, y2), *source_xy(width, y2), *source_xy(width, y))
        mesh.append(((0, y, width, y2), quad))
    return source.transform((width, height), Image.Transform.MESH, mesh, Image.Resampling.BICUBIC)


def basemap_viewport(base, requested, width, height):
    """Embedded credits stay attached to a complete, uncropped basemap."""
    require('credit_strip_px' not in base and base.get('attribution_policy') != 'preserve-bottom-strip',
            'detached credit strips are no longer supported; supply complete-image bounds and protected_bottom_px')
    if base['attribution_policy'] == 'preserve-in-place':
        w,s,e,n = base['bounds']
        rw,rs,re,rn = requested
        require(w <= rw < re <= e and s <= rs < rn <= n,
                'complete basemap must cover the requested view; supply wider imagery with room for markers and credits')
        return list(base['bounds'])
    return street_extent(requested, width, height)


def protected_credit_box(base, source_size, projection, frame):
    """Locate the existing bottom credit area in the same geographic transform."""
    if base['attribution_policy'] != 'preserve-in-place':
        return None
    protected = base.get('protected_bottom_px', 0)
    require(type(protected) is int and 0 < protected < source_size[1],
            'protected_bottom_px must leave positive unprotected image height')
    w,s,e,n = base['bounds']
    fraction = (source_size[1]-protected)/source_size[1]
    latitude = (n-(n-s)*fraction if base['crs'] == 'EPSG:4326' else
                unmercator(mercator(n)-(mercator(n)-mercator(s))*fraction))
    y = math.floor(projection.point(latitude,w)[1])
    return [frame[0], max(frame[1],y-1), frame[2], frame[3]]


def destination(lat, lng, km, bearing):
    distance = km / 6371.0088
    a, b, theta = math.radians(lat), math.radians(lng), math.radians(bearing)
    target_lat = math.asin(math.sin(a) * math.cos(distance) + math.cos(a) * math.sin(distance) * math.cos(theta))
    target_lng = b + math.atan2(math.sin(theta) * math.sin(distance) * math.cos(a), math.cos(distance) - math.sin(a) * math.sin(target_lat))
    return math.degrees(target_lat), (math.degrees(target_lng) + 180) % 360 - 180


def map_image(lane, business, path, fonts, full=False):
    from PIL import Image, ImageDraw, ImageFont
    extent = lane['full_bounds'] if full else lane['map']['bounds']
    base = lane['map'].get('full_basemap', lane['map'].get('basemap')) if full else lane['map'].get('basemap')
    height_pt = MAP_H if full else lane['map'].get('height_pt',452 if base else MAP_H)
    width, height = MAP_W * SCALE, height_pt * SCALE
    requested_extent = list(extent)
    source_pixels = None
    credit_box = None
    credit_hash = None
    geo_height = height
    if base:
        with Image.open(base['path']) as original:
            original = original.convert('RGB')
        source_pixels = list(original.size)
    if base:
        extent = basemap_viewport(base, extent, width, geo_height)
    projection = Projection(extent, width=width, height=geo_height, pad=0 if base else 26*SCALE)
    source_ppi = None
    if base:
        bw,bs,be,bn = base['bounds']
        sx0,sy0 = projection.point(bs,bw)
        sx1,sy1 = projection.point(bn,be)
        source_ppi = dict(x=source_pixels[0]/((sx1-sx0)/SCALE)*72,
                          y_average=source_pixels[1]/((sy0-sy1)/SCALE)*72,
                          note='Native geographic pixels per projected full-image span; vertical value is an average for EPSG:4326')
    canvas = Image.new('RGB', (width, height), BG)
    draw = ImageDraw.Draw(canvas)
    rect = tuple(round(v) for v in (projection.left, projection.top, projection.right, projection.bottom))
    draw.rectangle(rect, fill=PANEL, outline=LINE, width=2)
    if base:
        terrain = georeferenced_image(base, extent, rect[2] - rect[0], rect[3] - rect[1])
        canvas.paste(terrain, rect[:2], terrain)
        credit_box = protected_credit_box(base, source_pixels, projection, rect)
        if credit_box:
            credit_hash = hashlib.sha256(canvas.crop(credit_box).tobytes()).hexdigest()
    overlay_frame = [rect[0],rect[1],rect[2],credit_box[1] if credit_box else rect[3]]
    # Only complete neutral rings are drawn. Cropped bands are disclosed below
    # the map, not presented as seemingly complete service-area boundaries.
    overlay = Image.new('RGBA', canvas.size)
    drawn_bands, omitted_bands, ring_geometry = [], [], []
    for band in lane['map']['radius_bands_km']:
        ring = [destination(business['lat'], business['lng'], band, angle) for angle in range(360)]
        if all(abs(lat) <= 85 and inside({'lat': lat, 'lng': lng}, extent) for lat, lng in ring):
            points = [projection.point(lat, lng) for lat, lng in ring]
            points.append(points[0])
            footprint = [min(p[0] for p in points)-1, min(p[1] for p in points)-1,
                         max(p[0] for p in points)+1, max(p[1] for p in points)+1]
            if not contains_box(overlay_frame, footprint):
                omitted_bands.append(band)
                continue
            drawn_bands.append(band)
            ring_geometry.append(dict(km=band, points_px=points, stroke_px=2, footprint_px=footprint))
        else:
            omitted_bands.append(band)
    marker_geometry, dense_lattice, grid_step_px, _ = _compute_marker_specs(lane, extent, projection, fonts)
    shade_bands(overlay, ring_geometry, dense_lattice=dense_lattice)
    canvas.paste(overlay, (0, 0), overlay)
    distance_unit = lane['map'].get('distance_unit','km')
    pins = []
    for marker in marker_geometry:
        if credit_box:
            require(contains_box(overlay_frame, marker['footprint_px']),
                    'marker overlaps embedded credits or image edge; supply wider imagery with marker clearance')
        pins.append((marker['center_px'][0], marker['center_px'][1], marker['radius_px']))
    clip_poly = ring_geometry[-1]['points_px'] if (dense_lattice and ring_geometry) else None
    _paint_markers_and_lattice(canvas, marker_geometry, dense_lattice, grid_step_px, fonts, clip_polygon_px=clip_poly)
    band_labels = paint_band_labels(canvas, ring_geometry, fonts, overlay_frame, distance_unit, dense_lattice=dense_lattice)
    draw = ImageDraw.Draw(canvas)
    small = ImageFont.truetype(fonts['regular'], round(8.5 * SCALE))
    # Crosshair is an origin marker, not an additional observation.
    if inside(business, extent):
        x, y = projection.point(business['lat'], business['lng'])
        if credit_box:
            require(contains_box(overlay_frame,[x-14*SCALE,y-14*SCALE,x+14*SCALE,y+14*SCALE]),
                    'origin marker overlaps embedded credits or image edge; supply wider imagery')
        for a, b, c, d in ((x-13*SCALE, y, x-9*SCALE, y), (x+9*SCALE, y, x+13*SCALE, y),
                           (x, y-13*SCALE, x, y-9*SCALE), (x, y+9*SCALE, x, y+13*SCALE)):
            draw.line((a, b, c, d), fill=ACCENT, width=3)
    draw.text((8*SCALE, 3*SCALE), 'N', font=small, fill=INK)
    draw.line((19*SCALE, 13*SCALE, 19*SCALE, 3*SCALE), fill=INK, width=2)
    draw.line((16*SCALE, 6*SCALE, 19*SCALE, 3*SCALE, 22*SCALE, 6*SCALE), fill=INK, width=2)
    # Axis labels outside map geometry, all at readable caption size.
    w, s, e, n = extent
    if not base:
        draw.text((8*SCALE, geo_height-14*SCALE), f'W {w:.5f} / S {s:.5f}', font=small, fill=MUTED)
        draw.text((width-8*SCALE, geo_height-14*SCALE), f'E {e:.5f} / N {n:.5f}', font=small, fill=MUTED, anchor='ra')
    if credit_box:
        require(hashlib.sha256(canvas.crop(credit_box).tobytes()).hexdigest() == credit_hash,
                'overlays changed embedded credit pixels; supply imagery with more clearance')
    collisions = sum(math.hypot(a[0]-b[0], a[1]-b[1]) < a[2]+b[2]
                     for i, a in enumerate(pins) for b in pins[i+1:])
    canvas.save(path)
    return dict(file=path.name, full_extent=full, bounds=extent, requested_bounds=requested_extent, plotted=len(pins), outside=len(lane['records'])-len(pins),
                native_pixels=[width,height], effective_ppi=[width/MAP_W*72,height/height_pt*72],
                geographic_height_px=geo_height, geographic_frame_px=list(rect),
                geographic_plot_pt=dict(x=rect[0]/SCALE,y=rect[1]/SCALE,
                                        width=(rect[2]-rect[0])/SCALE,height=(rect[3]-rect[1])/SCALE),
                basemap_native_pixels=source_pixels, protected_credit_box_px=credit_box,
                basemap_effective_ppi=source_ppi,
                credit_pixels_sha256=credit_hash,
                attribution_policy=base['attribution_policy'] if base else 'schematic-caption',
                marker_geometry=marker_geometry, ring_geometry=ring_geometry, band_labels=band_labels, distance_unit=distance_unit,
                drawn_radius_bands_km=drawn_bands, omitted_radius_bands_km=omitted_bands,
                pin_collisions=collisions, projection='EPSG:3857; equal axis scale; no coordinate snapping',
                basemap='supplied georeferenced image' if base else 'schematic',
                attribution=base['attribution'] if base else 'Schematic coordinate map — no street basemap',
                width_pt=MAP_W, height_pt=height_pt, pin_font_pt=8)


def _compute_leader_territories(pts, pts_px, grid_step_px):
    """Port of singleLatticeOutlines() in src/map-geometry.js for contiguous #1 leader clusters."""
    tol = max(1.5, grid_step_px * 0.28)
    cols = _cluster_axis_coords([x for x, _ in pts_px], tol)
    rows = _cluster_axis_coords([y for _, y in pts_px], tol)
    if len(cols) < 2 or len(rows) < 2:
        return [], cols, rows, {}

    col_x = [0.0] * (len(cols) + 1)
    row_y = [0.0] * (len(rows) + 1)
    col_x[0] = cols[0] - (cols[1] - cols[0]) / 2.0
    for c in range(1, len(cols)):
        col_x[c] = 0.5 * (cols[c - 1] + cols[c])
    col_x[len(cols)] = cols[-1] + (cols[-1] - cols[-2]) / 2.0

    row_y[0] = rows[0] - (rows[1] - rows[0]) / 2.0
    for r in range(1, len(rows)):
        row_y[r] = 0.5 * (rows[r - 1] + rows[r])
    row_y[len(rows)] = rows[-1] + (rows[-1] - rows[-2]) / 2.0

    grid = {}
    cell_lookup = {}
    for p, (x, y) in zip(pts, pts_px):
        c_idx = min(range(len(cols)), key=lambda i: abs(cols[i] - x))
        r_idx = min(range(len(rows)), key=lambda i: abs(rows[i] - y))
        if abs(cols[c_idx] - x) > tol or abs(rows[r_idx] - y) > tol:
            continue
        cell_lookup[(r_idx, c_idx)] = (p, x, y)
        if p.get('major') and p.get('winner_id') and p.get('color'):
            grid[(r_idx, c_idx)] = {
                'r': r_idx,
                'c': c_idx,
                'leader_id': p['winner_id'],
                'color': p['color'],
            }

    visited = set()
    outlines = []
    nx = (0, -1, 0, 1)
    ny = (1, 0, -1, 0)
    for start_key, start_node in grid.items():
        if start_key in visited:
            continue
        comp = [start_node]
        visited.add(start_key)
        idx = 0
        while idx < len(comp):
            curr_n = comp[idx]
            idx += 1
            r0, c0, lid = curr_n['r'], curr_n['c'], curr_n['leader_id']
            for nr, nc in ((r0 - 1, c0), (r0 + 1, c0), (r0, c0 - 1), (r0, c0 + 1)):
                nb = grid.get((nr, nc))
                if nb and (nr, nc) not in visited and nb['leader_id'] == lid:
                    visited.add((nr, nc))
                    comp.append(nb)

        in_comp = {(n['r'], n['c']) for n in comp}
        outgoing = {}

        def _add_edge(c1, r1, c2, r2, d):
            outgoing.setdefault((c1, r1), []).append({'c1': c1, 'r1': r1, 'c2': c2, 'r2': r2, 'dir': d, 'used': False})

        for n in comp:
            r0, c0 = n['r'], n['c']
            if (r0 - 1, c0) not in in_comp:
                _add_edge(c0, r0, c0 + 1, r0, 0)
            if (r0, c0 + 1) not in in_comp:
                _add_edge(c0 + 1, r0, c0 + 1, r0 + 1, 1)
            if (r0 + 1, c0) not in in_comp:
                _add_edge(c0 + 1, r0 + 1, c0, r0 + 1, 2)
            if (r0, c0 - 1) not in in_comp:
                _add_edge(c0, r0 + 1, c0, r0, 3)

        rings = []
        for edges in outgoing.values():
            for start_edge in edges:
                if start_edge['used']:
                    continue
                loop = []
                curr = start_edge
                while curr and not curr['used']:
                    curr['used'] = True
                    loop.append(curr)
                    candidates = [e for e in outgoing.get((curr['c2'], curr['r2']), []) if not e['used']]
                    if not candidates:
                        break
                    pref = ((curr['dir'] + 1) % 4, curr['dir'], (curr['dir'] + 3) % 4, (curr['dir'] + 2) % 4)
                    candidates.sort(key=lambda e: pref.index(e['dir']))
                    curr = candidates[0]
                if len(loop) < 4:
                    continue
                corners = []
                for i_e, edge in enumerate(loop):
                    prev = loop[(i_e - 1) % len(loop)]
                    if prev['dir'] != edge['dir']:
                        corners.append({
                            'x': col_x[edge['c1']],
                            'y': row_y[edge['r1']],
                            'ix': nx[prev['dir']] + nx[edge['dir']],
                            'iy': ny[prev['dir']] + ny[edge['dir']],
                            'convex': ((prev['dir'] + 1) % 4) == edge['dir'],
                        })
                if len(corners) >= 4:
                    rings.append(corners)
        if rings:
            outlines.append({
                'leader_id': start_node['leader_id'],
                'color': start_node['color'],
                'size': len(comp),
                'rings': rings,
            })
    return outlines, cols, rows, cell_lookup


def _trace_rounded_ring(ring, base_radius, inset=0.0, scale_mult=1.0, arc_steps=6):
    """Convert orthogonal corner ring into rounded polygon vertices matching traceRing() in src/rank-canvas.js."""
    pts = [
        {
            'x': (p['x'] + p['ix'] * inset) * scale_mult,
            'y': (p['y'] + p['iy'] * inset) * scale_mult,
            'r': (max(1.5, base_radius - inset) if p['convex'] else base_radius + inset) * scale_mult,
        }
        for p in ring
    ]
    n = len(pts)
    poly = []
    for i in range(n):
        prev_p = pts[(i - 1) % n]
        curr_p = pts[i]
        next_p = pts[(i + 1) % n]
        vx_in = curr_p['x'] - prev_p['x']
        vy_in = curr_p['y'] - prev_p['y']
        vx_out = next_p['x'] - curr_p['x']
        vy_out = next_p['y'] - curr_p['y']
        len_in = math.hypot(vx_in, vy_in)
        len_out = math.hypot(vx_out, vy_out)
        if len_in < 1e-3 or len_out < 1e-3:
            poly.append((round(curr_p['x']), round(curr_p['y'])))
            continue
        r = min(curr_p['r'], len_in * 0.48, len_out * 0.48)
        ux_in, uy_in = vx_in / len_in, vy_in / len_in
        ux_out, uy_out = vx_out / len_out, vy_out / len_out
        for k in range(arc_steps + 1):
            theta = (k / arc_steps) * (math.pi / 2.0)
            px = curr_p['x'] - ux_in * r * (1.0 - math.sin(theta)) + ux_out * r * (1.0 - math.cos(theta))
            py = curr_p['y'] - uy_in * r * (1.0 - math.sin(theta)) + uy_out * r * (1.0 - math.cos(theta))
            poly.append((round(px), round(py)))
    return poly


def leaders_map_image(model, base_lane, path, fonts):
    """Render Web Companion Local Leaders territory map (leaders-map.png) matching src/rank-canvas.js."""
    from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFont
    intel = model['companion_intel']
    business = model['business']
    extent = list(base_lane['map']['bounds'])
    base = base_lane['map'].get('basemap')
    height_pt = base_lane['map'].get('height_pt', 452 if base else MAP_H)
    width, height = MAP_W * SCALE, height_pt * SCALE
    source_pixels = None
    credit_box = None
    if base:
        with Image.open(base['path']) as original:
            original = original.convert('RGB')
        source_pixels = list(original.size)
        extent = basemap_viewport(base, extent, width, height)
    projection = Projection(extent, width=width, height=height, pad=0 if base else 26 * SCALE)
    canvas = Image.new('RGB', (width, height), BG)
    draw = ImageDraw.Draw(canvas)
    rect = tuple(round(v) for v in (projection.left, projection.top, projection.right, projection.bottom))
    draw.rectangle(rect, fill=PANEL, outline=LINE, width=2)
    if base:
        terrain = georeferenced_image(base, extent, rect[2] - rect[0], rect[3] - rect[1])
        canvas.paste(terrain, rect[:2], terrain)
        credit_box = protected_credit_box(base, source_pixels, projection, rect)
    overlay_frame = [rect[0], rect[1], rect[2], credit_box[1] if credit_box else rect[3]]

    pts = [p for p in intel.get('leaders_map_points') or [] if inside(p, extent)]
    pts_px = [projection.point(p['lat'], p['lng']) for p in pts]
    grid_step_px = _grid_spacing_px(pts_px) or 25.0
    dense_leaders = _is_dense_lattice(len(pts), grid_step_px)

    overlay = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    ring_geometry = []
    for band in base_lane['map']['radius_bands_km']:
        ring = [destination(business['lat'], business['lng'], band, angle) for angle in range(360)]
        if all(abs(lat) <= 85 and inside({'lat': lat, 'lng': lng}, extent) for lat, lng in ring):
            points = [projection.point(lat, lng) for lat, lng in ring]
            points.append(points[0])
            footprint = [min(p[0] for p in points) - 1, min(p[1] for p in points) - 1,
                         max(p[0] for p in points) + 1, max(p[1] for p in points) + 1]
            if contains_box(overlay_frame, footprint):
                ring_geometry.append(dict(km=band, points_px=points, stroke_px=2, footprint_px=footprint))
    shade_bands(overlay, ring_geometry, dense_lattice=dense_leaders)
    canvas.paste(overlay, (0, 0), overlay)
    distance_unit = base_lane['map'].get('distance_unit', 'km')
    clip_poly = ring_geometry[-1]['points_px'] if ring_geometry else None

    clip_mask = None
    if clip_poly and len(clip_poly) >= 3:
        clip_mask = Image.new('L', canvas.size, 0)
        ImageDraw.Draw(clip_mask).polygon([tuple(p) for p in clip_poly], fill=255)

    outlines, cols, rows, cell_lookup = _compute_leader_territories(pts, pts_px, grid_step_px)

    # 1. Same-leader (4/4) corner gradient diamonds (drawBlends in src/companion.js lines 573-589)
    if len(cols) >= 2 and len(rows) >= 2:
        diamond_layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        max_span = grid_step_px * 1.45
        for r in range(len(rows) - 1):
            dy = abs(rows[r + 1] - rows[r])
            if dy > max_span or dy <= 0:
                continue
            cy = 0.5 * (rows[r] + rows[r + 1])
            for c in range(len(cols) - 1):
                dx = abs(cols[c + 1] - cols[c])
                if dx > max_span or dx <= 0:
                    continue
                quad = (
                    cell_lookup.get((r, c)),
                    cell_lookup.get((r, c + 1)),
                    cell_lookup.get((r + 1, c)),
                    cell_lookup.get((r + 1, c + 1)),
                )
                if any(item is None for item in quad):
                    continue
                lids = {item[0].get('winner_id') for item in quad if item[0].get('major') and item[0].get('winner_id')}
                if len(lids) != 1 or not all(item[0].get('major') and item[0].get('winner_id') in lids for item in quad):
                    continue
                rgb = ImageColor.getrgb(quad[0][0]['color'])
                rgba = (*rgb, round(255 * 0.68))
                corners_rgba = (rgba, rgba, rgba, rgba)
                cx = 0.5 * (cols[c] + cols[c + 1])
                d_size = min(dx, dy) * 2.0 * DIAMOND_HALF
                patch = _get_diamond_patch(corners_rgba, d_size)
                diamond_layer.alpha_composite(patch, (round(cx - patch.width / 2.0), round(cy - patch.height / 2.0)))
        if clip_mask is not None:
            r_c, g_c, b_c, a_c = diamond_layer.split()
            diamond_layer = Image.merge('RGBA', (r_c, g_c, b_c, ImageChops.multiply(a_c, clip_mask)))
        canvas.paste(diamond_layer, (0, 0), diamond_layer)

    # 2. Territory outlines & evenodd fills (src/rank-canvas.js lines 352-393)
    if outlines:
        terr_layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
        base_radius = min(grid_step_px * 0.26, 13.0 * (SCALE / 2.0))
        border_w = max(1.4 * (SCALE / 2.0), min(2.5 * (SCALE / 2.0), grid_step_px * 0.09))
        inset = border_w / 2.0
        ss = 2
        border_layer_ss = Image.new('RGBA', (width * ss, height * ss), (0, 0, 0, 0))
        bdraw_ss = ImageDraw.Draw(border_layer_ss)
        for t in outlines:
            rgb = ImageColor.getrgb(t['color'])
            comp_mask = Image.new('1', canvas.size, 0)
            for ring in t['rings']:
                ring_mask = Image.new('1', canvas.size, 0)
                poly_0 = _trace_rounded_ring(ring, base_radius, inset=0.0, scale_mult=1.0)
                if len(poly_0) >= 3:
                    ImageDraw.Draw(ring_mask).polygon(poly_0, fill=1)
                comp_mask = ImageChops.logical_xor(comp_mask, ring_mask)
                poly_in = _trace_rounded_ring(ring, base_radius, inset=inset, scale_mult=ss)
                if len(poly_in) >= 3:
                    bdraw_ss.line(poly_in + [poly_in[0]], fill=(*rgb, round(255 * 0.84)), width=max(2, round(border_w * ss)))
            fill_alpha = comp_mask.convert('L').point(lambda v: round(255 * 0.075) if v else 0)
            fill_im = Image.new('RGBA', canvas.size, (*rgb, 255))
            fill_im.putalpha(fill_alpha)
            terr_layer.alpha_composite(fill_im)
        border_layer = border_layer_ss.resize(canvas.size, Image.Resampling.BILINEAR)
        terr_layer.alpha_composite(border_layer)
        if clip_mask is not None:
            r_c, g_c, b_c, a_c = terr_layer.split()
            terr_layer = Image.merge('RGBA', (r_c, g_c, b_c, ImageChops.multiply(a_c, clip_mask)))
        canvas.paste(terr_layer, (0, 0), terr_layer)

    # 3. Stop-sign octagon cells (src/rank-canvas.js lines 395-425)
    ss = 2
    pin_layer_ss = Image.new('RGBA', (width * ss, height * ss), (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(pin_layer_ss)
    c_size = max(4.0 * SCALE, grid_step_px * STOP_SIGN_SCALE)
    for p, (cx, cy) in zip(pts, pts_px):
        fp = [cx - c_size / 2.0, cy - c_size / 2.0, cx + c_size / 2.0, cy + c_size / 2.0]
        if not contains_box(overlay_frame, fp):
            continue
        verts = [
            (round((cx + (vx - 0.5) * c_size) * ss), round((cy + (vy - 0.5) * c_size) * ss))
            for vx, vy in OCTAGON_VERTICES
        ]
        if p.get('major') and p.get('color'):
            rgb = ImageColor.getrgb(p['color'])
            pdraw.polygon(verts, fill=(*rgb, 255))
            pdraw.line(verts + [verts[0]], fill=(0, 0, 0, 128), width=max(2, round(c_size * 0.015 * ss)))
        elif p.get('winner_id'):
            stroke_w = max(2, round(min(1.5 * (SCALE / 2.0), max(0.8 * (SCALE / 2.0), c_size * 0.025)) * ss))
            pdraw.line(verts + [verts[0]], fill=(163, 177, 195, 140), width=stroke_w)
        else:
            stroke_w = max(2, round(c_size * 0.025 * ss))
            pdraw.line(verts + [verts[0]], fill=(225, 184, 105, 166), width=stroke_w)
    pin_layer = pin_layer_ss.resize(canvas.size, Image.Resampling.BILINEAR)
    if clip_mask is not None:
        r_c, g_c, b_c, a_c = pin_layer.split()
        pin_layer = Image.merge('RGBA', (r_c, g_c, b_c, ImageChops.multiply(a_c, clip_mask)))
    canvas.paste(pin_layer, (0, 0), pin_layer)

    band_labels = paint_band_labels(canvas, ring_geometry, fonts, overlay_frame, distance_unit, dense_lattice=dense_leaders)

    # 4. Rotated 45-degree .leader-diamond base markers & dashed connectors (src/companion.js lines 533-558)
    badge_layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
    bdraw = ImageDraw.Draw(badge_layer)
    badge_font = ImageFont.truetype(fonts['bold'], round(6.5 * SCALE))
    placed_boxes = [list(lbl['footprint_px']) for lbl in band_labels]
    diamond_r = round(10.5 * SCALE)
    for leader in (intel.get('pooled_leaders') or [])[:14]:
        if not leader.get('recurring') and not leader.get('is_target'):
            continue
        center = leader.get('center')
        has_base = (
            isinstance(leader.get('lat'), (int, float))
            and isinstance(leader.get('lng'), (int, float))
            and inside({'lat': leader['lat'], 'lng': leader['lng']}, extent)
        )
        anchor_pt = {'lat': leader['lat'], 'lng': leader['lng']} if has_base else center
        if not anchor_pt or not inside(anchor_pt, extent):
            continue
        bx, by = projection.point(anchor_pt['lat'], anchor_pt['lng'])
        box = [bx - diamond_r, by - diamond_r, bx + diamond_r, by + diamond_r]
        if not contains_box(overlay_frame, box):
            if center and inside(center, extent):
                bx, by = projection.point(center['lat'], center['lng'])
                box = [bx - diamond_r, by - diamond_r, bx + diamond_r, by + diamond_r]
                if not contains_box(overlay_frame, box):
                    continue
            else:
                continue
        if any(_boxes_overlap(box, prev, pad=2.0 * SCALE) for prev in placed_boxes):
            if center and inside(center, extent):
                bx, by = projection.point(center['lat'], center['lng'])
                box = [bx - diamond_r, by - diamond_r, bx + diamond_r, by + diamond_r]
                if not contains_box(overlay_frame, box) or any(_boxes_overlap(box, prev, pad=2.0 * SCALE) for prev in placed_boxes):
                    continue
            else:
                continue
        placed_boxes.append(box)
        rgb = ImageColor.getrgb(leader.get('color') or '#FFFFFF')
        # If base is distant from territory center, draw dashed connector line to cluster center
        if has_base and center and inside(center, extent):
            tx, ty = projection.point(center['lat'], center['lng'])
            dist_px = math.hypot(tx - bx, ty - by)
            if dist_px > grid_step_px * 2.2:
                steps = max(2, int(dist_px / (6 * SCALE)))
                for s_i in range(0, steps, 2):
                    t0 = s_i / steps
                    t1 = min(1.0, (s_i + 1) / steps)
                    bdraw.line(
                        [(bx + (tx - bx) * t0, by + (ty - by) * t0), (bx + (tx - bx) * t1, by + (ty - by) * t1)],
                        fill=(*rgb, 190),
                        width=2,
                    )
                c_rad = 3.5 * SCALE
                bdraw.ellipse([tx - c_rad, ty - c_rad, tx + c_rad, ty + c_rad], outline=(*rgb, 210), width=2)
        d_pts = [(bx, by - diamond_r), (bx + diamond_r, by), (bx, by + diamond_r), (bx - diamond_r, by)]
        shadow_pts = [(px, py + 2) for px, py in d_pts]
        bdraw.polygon(shadow_pts, fill=(0, 0, 0, 160))
        bdraw.polygon(d_pts, fill=(8, 8, 8, 245))
        bdraw.line(d_pts + [d_pts[0]], fill=(*rgb, 255), width=max(2, round(1.6 * SCALE)))
        bdraw.text((bx, by), leader['badge'], font=badge_font, fill=(255, 255, 255, 255), anchor='mm')

    canvas.paste(badge_layer, (0, 0), badge_layer)
    draw = ImageDraw.Draw(canvas)
    small = ImageFont.truetype(fonts['regular'], round(8.5 * SCALE))
    if inside(business, extent):
        x, y = projection.point(business['lat'], business['lng'])
        for a, b, c, d in ((x - 13 * SCALE, y, x - 9 * SCALE, y), (x + 9 * SCALE, y, x + 13 * SCALE, y),
                           (x, y - 13 * SCALE, x, y - 9 * SCALE), (x, y + 9 * SCALE, x, y + 13 * SCALE)):
            draw.line((a, b, c, d), fill=ACCENT, width=3)
    draw.text((8 * SCALE, 3 * SCALE), 'N', font=small, fill=INK)
    draw.line((19 * SCALE, 13 * SCALE, 19 * SCALE, 3 * SCALE), fill=INK, width=2)
    draw.line((16 * SCALE, 6 * SCALE, 19 * SCALE, 3 * SCALE, 22 * SCALE, 6 * SCALE), fill=INK, width=2)
    canvas.save(path)
    return dict(file=path.name, width_pt=MAP_W, height_pt=height_pt, plotted=len(pts))


def map_caption(lane, asset):
    unit = asset.get('distance_unit','km')
    bands = ', '.join(display_distance(x,unit) for x in asset['drawn_radius_bands_km']) or 'none'
    msg = (f"{asset['attribution']}. Neutral bands: {bands} {unit}; origin: neutral crosshair. "
           f"{asset['plotted']} origins shown; {asset['outside']} outside view.")
    if asset['omitted_radius_bands_km']:
        reason = 'Bands omitted to keep the view and credits clear' if asset['protected_credit_box_px'] else 'Bands omitted outside view'
        msg += ' '+reason+': '+', '.join(display_distance(x,unit) for x in asset['omitted_radius_bands_km'])+' '+unit+'.'
    if asset['pin_collisions']:
        msg += f" {asset['pin_collisions']} pin overlaps; positions are unchanged. See the HTML ledger for every exact coordinate and rank."
    if lane['map'].get('basemap'):
        msg += ' Areas outside the supplied image retain a schematic background.'
        if asset['attribution_policy'] == 'preserve-in-place':
            msg += ' Complete basemap retained; embedded credits remain in their original geographic position, clear of overlays.'
        else:
            msg += ' Overlay-safe image; credit is repeated here separately. Embedded credits are not protected.'
    return msg+' '+center_disclosure(asset) if asset.get('center_kind') == 'market' else msg


def center_disclosure(value):
    if value['center_kind'] == 'market':
        return (f"Market scan center: {value['center_label']}. Crosshair and distance bands use this market reference, "
                'not a verified physical business location.')
    return f"Business origin: {value['center_label']} (user supplied)."


def brief_caption(asset):
    unit = asset.get('distance_unit','km')
    result = asset['attribution']+'. '
    if asset['basemap'] != 'schematic':
        result += 'Outside supplied imagery: schematic background. '
    result += f"{asset['plotted']} origins shown; {asset['outside']} outside view."
    if asset['drawn_radius_bands_km']:
        result += ' Rings: '+', '.join(display_distance(km,unit) for km in asset['drawn_radius_bands_km'])+' '+unit+'.'
    if asset['pin_collisions']:
        result += f" {asset['pin_collisions']} pin overlaps; exact positions retained."
    if asset.get('center_kind') == 'market':
        result += ' '+center_disclosure(asset)
    return result


def legend_items():
    return [('#1 Winner','#00FFFF',False),('Ranks 1–3',RANK_COLORS[0],False),('Ranks 4–10',RANK_COLORS[1],False),
            ('Ranks 11+',RANK_COLORS[2],False),('Not returned',MUTED,True)]


def contains_box(outer, inner, tolerance=.01):
    return all(math.isfinite(v) for v in inner) and outer[0]-tolerance <= inner[0] <= inner[2] <= outer[2]+tolerance and outer[1]-tolerance <= inner[1] <= inner[3] <= outer[3]+tolerance


def map_qa(lane, business, asset, path, fonts):
    """Check recorded drawing geometry against observations and final raster.

    This validates complete footprints and evidence counts, not OCR or geographic
    truth of a supplied basemap. Collisions remain explicitly reported.
    """
    from PIL import Image, ImageChops, ImageDraw, ImageFont
    with Image.open(path) as raster:
        raster = raster.convert('RGB')
    width, height = raster.size
    require([width,height] == asset['native_pixels'] == [MAP_W*SCALE, asset['height_pt']*SCALE], 'map raster dimensions differ from declared native pixels')
    require(asset['effective_ppi'] == [width/asset['width_pt']*72,height/asset['height_pt']*72], 'map effective PPI mismatch')
    geo_height = asset['geographic_height_px']
    credit_box = asset['protected_credit_box_px']
    if credit_box:
        require(contains_box(asset['geographic_frame_px'], credit_box), 'embedded credits are outside geographic frame')
        require(hashlib.sha256(raster.crop(credit_box).tobytes()).hexdigest() == asset['credit_pixels_sha256'], 'protected credit pixels were altered')
    base = lane['map'].get('full_basemap', lane['map'].get('basemap')) if asset.get('full_extent') else lane['map'].get('basemap')
    expected_bounds = basemap_viewport(base,asset['requested_bounds'],width,geo_height) if base else asset['requested_bounds']
    require(asset['bounds'] == expected_bounds, 'expanded viewport bounds mismatch')
    projection = Projection(asset['bounds'], width=width, height=geo_height, pad=0 if base else 26*SCALE)
    frame = [round(v) for v in (projection.left,projection.top,projection.right,projection.bottom)]
    require(frame == asset['geographic_frame_px'], 'geographic frame mismatch')
    base = lane['map'].get('full_basemap', lane['map'].get('basemap')) if asset.get('full_extent') else lane['map'].get('basemap')
    if base:
        with Image.open(base['path']) as original:
            original = original.convert('RGB')
        require(list(original.size)==asset['basemap_native_pixels'], 'source native pixel dimensions mismatch')
        require(credit_box == protected_credit_box(base,original.size,projection,frame), 'embedded credit position mismatch')
        if credit_box:
            expected_terrain = georeferenced_image(base,asset['bounds'],frame[2]-frame[0],frame[3]-frame[1]).convert('RGB')
            source_box = [credit_box[0]-frame[0],credit_box[1]-frame[1],credit_box[2]-frame[0],credit_box[3]-frame[1]]
            require(expected_terrain.crop(source_box).tobytes()==raster.crop(credit_box).tobytes(),
                    'embedded credits do not match the continuous source image')
    # 18pt outer inset reserves the axis caption area. Geographic padding
    # permits boundary-centered pins without clipping their circles.
    safe = [frame[0],frame[1],frame[2],credit_box[1] if credit_box else frame[3]] if base else [0,0,width,geo_height-18*SCALE]
    expected = {i:r for i,r in enumerate(lane['records']) if inside(r,asset['bounds'])}
    markers = asset['marker_geometry']
    require(len(markers) == len(expected) == asset['plotted'], 'marker count does not match visible observations')
    require(asset['outside'] == len(lane['records'])-len(expected), 'outside count mismatch')
    require({m['index'] for m in markers} == set(expected), 'marker IDs missing, duplicated, or fabricated')
    expected_specs, dense_lattice, grid_step_px, _ = _compute_marker_specs(lane, asset['bounds'], projection, fonts)
    spec_by_idx = {s['index']: s for s in expected_specs}
    for marker in markers:
        row = expected[marker['index']]
        spec = spec_by_idx[marker['index']]
        label = marker_label(row['state'],row['rank'])
        require(marker['label']==label and marker['state']==row['state'] and marker['rank']==row['rank'], 'marker rank/state mismatch')
        x,y = projection.point(row['lat'],row['lng'])
        require(max(abs(x-marker['center_px'][0]),abs(y-marker['center_px'][1])) < .001, 'marker coordinate mismatch')
        radius = spec['radius_px']
        require(abs(radius-marker['radius_px']) < .001, 'marker radius mismatch')
        footprint = [x-radius,y-radius,x+radius,y+radius]
        require(all(abs(a-b)<.001 for a,b in zip(footprint,marker['footprint_px'])), 'marker footprint mismatch')
        require(contains_box(safe,footprint), 'marker footprint clips raster, axis captions, or protected credits')
    rings = asset['ring_geometry']
    configured = lane['map']['radius_bands_km']
    require([r['km'] for r in rings] == asset['drawn_radius_bands_km'], 'ring count/list mismatch')
    require(sorted(asset['drawn_radius_bands_km']+asset['omitted_radius_bands_km']) == configured, 'configured ring accounting mismatch')
    for ring in rings:
        points = ring['points_px']
        require(len(points)==361 and points[0]==points[-1], 'ring is not a complete closed 360-degree path')
        require(ring['stroke_px']==2, 'unexpected ring stroke footprint')
        for angle,point in enumerate(points[:-1]):
            lat,lng = destination(business['lat'],business['lng'],ring['km'],angle)
            require(inside({'lat':lat,'lng':lng},asset['bounds']), 'ring extends beyond geographic evidence view')
            actual = projection.point(lat,lng)
            require(max(abs(actual[0]-point[0]),abs(actual[1]-point[1]))<.001, 'ring coordinate mismatch')
        footprint = [min(p[0] for p in points)-1,min(p[1] for p in points)-1,max(p[0] for p in points)+1,max(p[1] for p in points)+1]
        require(contains_box(frame,footprint) and contains_box(safe,footprint), 'ring stroke clips frame or protected area')
        require(all(abs(a-b)<.001 for a,b in zip(footprint,ring['footprint_px'])), 'ring footprint mismatch')
    # Reconstruct paint only where validated marker/ring footprints occur. This
    # detects missing/erased paint even if the drawing ledger is still intact.
    expected_raster = Image.new('RGB',(width,height),BG)
    ImageDraw.Draw(expected_raster).rectangle(frame,fill=PANEL,outline=LINE,width=2)
    if base:
        terrain = georeferenced_image(base,asset['bounds'],frame[2]-frame[0],frame[3]-frame[1])
        expected_raster.paste(terrain,frame[:2],terrain)
    mask = Image.new('L',(width,height))
    mask_draw = ImageDraw.Draw(mask)
    overlay = Image.new('RGBA',(width,height))
    shade_bands(overlay, rings, dense_lattice=dense_lattice)
    for ring in rings:
        points = [tuple(p) for p in ring['points_px']]
        if not dense_lattice:
            mask_draw.polygon(points,fill=255)
        mask_draw.line(points,fill=255,width=2)
    expected_raster.paste(overlay,(0,0),overlay)
    unit = lane['map'].get('distance_unit','km')
    require(asset.get('distance_unit','km') == unit, 'map distance unit mismatch')
    clip_poly = rings[-1]['points_px'] if (dense_lattice and rings) else None
    _paint_markers_and_lattice(expected_raster, markers, dense_lattice, grid_step_px, fonts, mask_draw=mask_draw, clip_polygon_px=clip_poly)
    labels = paint_band_labels(expected_raster,rings,fonts,safe if base else frame,unit,dense_lattice=dense_lattice)
    require(labels == asset['band_labels'], 'band label geometry mismatch')
    for label in labels:
        require(contains_box(safe,label['footprint_px']), 'band label clips geographic area')
        mask_draw.rectangle(label['footprint_px'],fill=255)
    paint = ImageDraw.Draw(expected_raster)
    if inside(business,asset['bounds']):
        x,y = projection.point(business['lat'],business['lng'])
        for a,b,c,d in ((x-13*SCALE,y,x-9*SCALE,y),(x+9*SCALE,y,x+13*SCALE,y),
                         (x,y-13*SCALE,x,y-9*SCALE),(x,y+9*SCALE,x,y+13*SCALE)):
            paint.line((a,b,c,d),fill=ACCENT,width=3)
    channels = ImageChops.difference(expected_raster,raster).split()
    difference = ImageChops.lighter(ImageChops.lighter(channels[0],channels[1]),channels[2])
    require(ImageChops.multiply(difference,mask).getbbox() is None, 'marker/ring painted pixels differ from validated evidence geometry')
    return dict(status='passed', markers_checked=len(markers), rings_checked=len(rings),
                excluded_origins_checked=asset['outside'], protected_credit_pixels_checked=bool(credit_box),
                painted_footprint_pixels_checked=mask.histogram()[255],
                native_pixels=[width,height], effective_ppi=asset['effective_ppi'],
                geographic_plot_pt=asset['geographic_plot_pt'],
                scope='Exact observation counts, projected geometry, full painted footprint pixels and protected source credits; no marker OCR')


def render_pdf(model, assets, output):
    from PIL import ImageFont
    from reportlab.lib.colors import HexColor
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import BaseDocTemplate, Flowable, Frame, Image, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.pdfbase import pdfmetrics
    log = []

    class TrackedParagraph(Paragraph):
        def drawOn(self, canv, x, y, _sW=0):
            log.append(dict(page=canv.getPageNumber(), kind='text', x=x, y=y, width=self.width, height=self.height,
                            font_size_pt=self.style.fontSize))
            return super().drawOn(canv, x, y, _sW)

    class TrackedImage(Image):
        def drawOn(self, canv, x, y, _sW=0):
            log.append(dict(page=canv.getPageNumber(), kind='map', x=x, y=y, width=self.drawWidth, height=self.drawHeight))
            return super().drawOn(canv, x, y, _sW)

    class CompanionMapImage(Image):
        def drawOn(self, canv, x, y, _sW=0):
            log.append(dict(page=canv.getPageNumber(), kind='companion_map', x=x, y=y, width=self.drawWidth, height=self.drawHeight))
            return super().drawOn(canv, x, y, _sW)

    class TrackedTable(Table):
        def drawOn(self, canv, x, y, _sW=0):
            log.append(dict(page=canv.getPageNumber(), kind='table', x=x, y=y, width=self._width, height=self._height, font_size_pt=9.0))
            return super().drawOn(canv, x, y, _sW)

    class MapLegend(Flowable):
        def __init__(self, lane, asset):
            super().__init__()
            self.lane, self.asset = lane, asset
            self.width = COLUMN
            self.excluded = any(lane['metrics']['states'].get(k,0) for k in ('error','empty','unmeasured'))
            self.height = 28 if self.excluded else 16

        def drawOn(self, canv, x, y, _sW=0):
            log.append(dict(page=canv.getPageNumber(),kind='legend',x=x,y=y,width=self.width,height=self.height,font_size_pt=8.5))
            return super().drawOn(canv,x,y,_sW)

        def draw(self):
            c = self.canv
            c.setFont('ReportBody',8.5)
            x,y = 4,self.height-7
            for label,color,hollow in legend_items():
                c.setFillColor(HexColor(color))
                c.setStrokeColor(HexColor(color))
                c.setLineWidth(1)
                c.circle(x,y,3,fill=int(not hollow),stroke=int(hollow))
                c.setFillColor(HexColor(MUTED))
                c.drawString(x+8,y-3,label)
                x += pdfmetrics.stringWidth(label,'ReportBody',8.5)+26
            c.drawRightString(COLUMN,y-3,'Rings: '+self.asset.get('distance_unit','km'))
            if self.excluded:
                c.drawString(0,4,'E: error   Ø: empty   U: unmeasured (excluded from measured denominator)')

    styles = {
        'title': ParagraphStyle('title', fontName='ReportTitle', fontSize=24, leading=30, textColor=HexColor(INK), spaceAfter=12),
        'lane_title': ParagraphStyle('lane_title', fontName='ReportTitle', fontSize=20, leading=24, textColor=HexColor(INK), spaceAfter=4),
        'heading': ParagraphStyle('heading', fontName='ReportBold', fontSize=13, leading=17, textColor=HexColor(INK), spaceBefore=10, spaceAfter=8, keepWithNext=True),
        'lane_heading': ParagraphStyle('lane_heading', fontName='ReportBold', fontSize=11, leading=14, textColor=HexColor(INK), spaceBefore=4, spaceAfter=2, keepWithNext=True),
        'body': ParagraphStyle('body', fontName='ReportBody', fontSize=11, leading=16, textColor=HexColor(INK), spaceAfter=10),
        'lane_body': ParagraphStyle('lane_body', fontName='ReportBody', fontSize=9.5, leading=12.5, textColor=HexColor('#000000' if THEME == 'light' else '#E0E0E0'), spaceAfter=4),
        'finding': ParagraphStyle('finding', fontName='ReportBody', fontSize=9.5, leading=12.5, textColor=HexColor(INK), spaceAfter=4),
        'small': ParagraphStyle('small', fontName='ReportBody', fontSize=8.5, leading=11.5, textColor=HexColor(MUTED), spaceAfter=6),
        'cell': ParagraphStyle('cell', fontName='ReportBody', fontSize=8.5, leading=11, textColor=HexColor('#000000' if THEME == 'light' else '#E0E0E0')),
        'cell_bold': ParagraphStyle('cell_bold', fontName='ReportBold', fontSize=8.5, leading=11, textColor=HexColor(INK)),
        'cell_head': ParagraphStyle('cell_head', fontName='ReportBold', fontSize=8.5, leading=11, textColor=HexColor('#555555' if THEME == 'light' else '#BDBDBD')),
    }
    styles['category'] = ParagraphStyle('category', parent=styles['heading'])
    styles['heading'].fontSize = 16
    styles['heading'].leading = 21
    styles['heading'].spaceBefore = 18
    styles['heading'].spaceAfter = 10
    styles['body'].textColor = HexColor('#000000' if THEME == 'light' else '#E0E0E0')
    styles['small'].textColor = HexColor('#555555' if THEME == 'light' else '#A3A3A3')
    styles['category'].fontSize = 14
    styles['category'].leading = 19
    styles['category'].backColor = HexColor('#FFFFFF' if THEME == 'light' else '#181818')
    styles['category'].borderColor = HexColor(LINE)
    styles['category'].borderWidth = 0.5
    styles['category'].borderPadding = 6
    styles['category'].spaceBefore = 18
    styles['category'].spaceAfter = 14
    ink_fonts, ink_metrics = {}, {}

    def guarded_style(value, style):
        name = style.fontName
        if name not in ink_fonts:
            ink_fonts[name] = ImageFont.truetype(pdfmetrics.getFont(name).face.filename,1000)
        font = ink_fonts[name]
        left, right = 0., 0.
        for char in set(value)-set('\n\r\t '):
            key = (name,char)
            if key not in ink_metrics:
                box = font.getbbox(char)
                ink_metrics[key] = (max(0,-box[0]),max(0,box[2]-font.getlength(char)))
            a,b = ink_metrics[key]
            left,right = max(left,a),max(right,b)
        left = left*style.fontSize/1000 + (.05 if left else 0)
        right = right*style.fontSize/1000 + (.05 if right else 0)
        return ParagraphStyle(style.name+'InkGuard',parent=style,
                              leftIndent=style.leftIndent+left,rightIndent=style.rightIndent+right)

    def p(value, style='body'):
        value = display_text(value)
        paragraph_style = guarded_style(value,styles[style])
        available = COLUMN-paragraph_style.leftIndent-paragraph_style.rightIndent
        if style == 'title':
            words = value.split()
            if pdfmetrics.stringWidth(value, 'ReportTitle', 24) > available:
                candidates = []
                for i in range(1, len(words)):
                    a, b = ' '.join(words[:i]), ' '.join(words[i:])
                    aw, bw = [pdfmetrics.stringWidth(t, 'ReportTitle', 24) for t in (a, b)]
                    if max(aw, bw) <= available:
                        candidates.append((abs(aw-bw), a+'\n'+b))
                if candidates:
                    value = min(candidates)[1]
        return TrackedParagraph(escape(value).replace('\n', '<br/>'), paragraph_style)

    def cell_p(value, style_name='cell'):
        return Paragraph(escape(display_text(str(value))).replace('\n', '<br/>'), styles[style_name])

    def make_table(headers, rows, col_widths, highlight_rows=()):
        data = [[cell_p(h, 'cell_head') for h in headers]]
        for r_idx, row in enumerate(rows):
            st = 'cell_bold' if r_idx in highlight_rows else 'cell'
            data.append([cell_p(c, st) for c in row])
        t_cmds = [
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#F3F3F3' if THEME == 'light' else '#181818')),
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, HexColor(LINE)),
            ('LINEABOVE', (0, 0), (-1, 0), 0.75, HexColor(INK)),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]
        for hr in highlight_rows:
            t_cmds.append(('BACKGROUND', (0, hr + 1), (-1, hr + 1), HexColor('#F7F7F7' if THEME == 'light' else '#231818')))
        tbl = TrackedTable(data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle(t_cmds))
        return tbl

    def keyword(value):
        style = ParagraphStyle('keyword', parent=styles['category'], fontSize=15,
                               leading=17, borderPadding=6, backColor=HexColor('#FFFFFF' if THEME == 'light' else '#211414'),
                               borderColor=HexColor(LINE), spaceBefore=12, spaceAfter=10)
        return TrackedParagraph('<font size="8" color="'+('#555555' if THEME == 'light' else '#BDBDBD')+'">SEARCH KEYWORD</font><br/>'+
                                escape(display_text(value)), guarded_style(value, style))

    def label(canv, x, y, value, right=False):
        (canv.drawRightString if right else canv.drawString)(x, y, value)

    def page(canv, doc):
        canv.setFillColor(HexColor(BG))
        canv.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        canv.setStrokeColor(HexColor(LINE))
        canv.line(MARGIN, 747, PAGE_W-MARGIN, 747)
        canv.line(MARGIN, 43, PAGE_W-MARGIN, 43)
        canv.setFillColor(HexColor(MUTED))
        canv.setFont('ReportBody', 8.5)
        label(canv, MARGIN, 761, 'legends-geogrid / local search observations')
        label(canv, MARGIN, 28, 'SYNTHETIC DEMONSTRATION' if model['synthetic'] else 'SUPPLIED OBSERVATIONAL EVIDENCE')
        label(canv, PAGE_W/2, 28, str(doc.page), right=True)

    doc = BaseDocTemplate(str(output / 'report.pdf'), pagesize=(PAGE_W, PAGE_H),
                          title=display_text(model['business']['name'])+' | legends-geogrid report', author='legends-geogrid',
                          leftMargin=MARGIN, rightMargin=MARGIN, topMargin=65, bottomMargin=58,
                          allowSplitting=1)
    doc.addPageTemplates(PageTemplate(id='dark', frames=[Frame(MARGIN, 58, COLUMN, 669, leftPadding=0,
                          rightPadding=0, topPadding=0, bottomPadding=0)], onPage=page))
    brief = model['decision_brief']
    intel = model.get('companion_intel')
    story = [p(model['business']['name'], 'title'), p(model['business']['location'], 'small')]
    website = model['business'].get('website')
    if website:
        story += [TrackedParagraph('<a href="'+escape(website, quote=True)+'" color="'+ACCENT+'">'+escape(website)+'</a>', styles['body'])]
    if brief.get('headline'):
        story += [p(brief['headline'], 'heading'), p(brief['explanation'])]
        story += [p(str(a['priority'])+'. '+a['title']) for a in brief['actions'][:3]]
    if model['synthetic']:
        story += [p('Synthetic demonstration — no real business findings', 'heading')]
    story += [p('visibility at a glance','heading')]
    v_headers = ['Search Query', 'Top 3 (Share)', 'Top 10 (Share)', 'Ranks 4-10', 'Measured']
    v_rows = []
    for lane in model['lanes']:
        m = lane['metrics']
        if m['measured']:
            t3_pct = 100.0 * m['top3'] / m['measured']
            t10_pct = 100.0 * m['top10'] / m['measured']
            v_rows.append([
                lane['query'],
                f"{m['top3']}/{m['measured']} ({t3_pct:.1f}%)",
                f"{m['top10']}/{m['measured']} ({t10_pct:.1f}%)",
                str(m['near_miss']),
                f"{m['measured']}/{m['sampled']}",
            ])
        else:
            v_rows.append([
                lane['query'],
                'not measured',
                'not measured',
                'not measured',
                f"0/{m['sampled']}" if m['sampled'] else 'not measured',
            ])
    story += [make_table(v_headers, v_rows, [164, 96, 96, 72, 88]), Spacer(1, 8)]
    if intel and intel.get('target_standing'):
        ts = intel['target_standing']
        s_meta = intel['summary']
        story += [p(
            f"Web Companion field standing: #{ts['standing']} of {s_meta['total_observed_profiles']} observed profiles "
            f"({ts['top3_coverage_pct']:.1f}% equal-query top-3 share; {ts['rank1_total']} #1 wins; "
            f"{s_meta['recurring_leaders_count']} recurring local leaders across {s_meta['total_origins']} origins).",
            'small'
        )]
    story += [p('Counts describe sampled locations, not customers or market share. Unmeasured origins are excluded; no measured origins means no rank conclusion.','small')]
    story += ([] if brief.get('headline') else [p('working assessment','heading'),p('Hypothesis, not an established finding: '+model['thesis'])])+[p(model['evidence_disclosure'],'small'),p(center_disclosure(model),'small')]
    brief = model['decision_brief']
    story += [PageBreak(), p('Reading the findings', 'title')]
    story += [p('How to read the evidence', 'heading'), p(brief['reading_guide'])]
    story += [p(x['text']) for x in brief['findings']]
    story += [p(brief['boundary'], 'small')]
    profile = model.get('profile_review')
    if profile:
        from profile_review import readable
        story += [PageBreak(), p('The business behind the listing', 'title'), p(profile['access'],'small'), p(profile['identity_assessment'])]
        for fact in profile['facts']:
            if fact['field'] in ('category','address','phone','rating','local_business_links'):
                story += [p(fact['label'], 'heading'), p(readable(fact))]
        story += [p(profile['limitation'],'small'), PageBreak(), p('Why these searches matter','title')]
        for theme in profile['themes']:
            story += [keyword(theme['query']),p(theme['customer_need']),p(theme['why']),p(theme['limitations'],'small')]
    for i, lane in enumerate(model['lanes']):
        asset = assets[i]['main']
        compact_lane = asset['height_pt'] <= 452 and len(lane.get('narrative') or '') <= 280
        story += [PageBreak(), p(lane['label'], 'lane_title' if compact_lane else 'title'), p('Query: '+lane['query'], 'small')]
        block = [TrackedImage(str(output / asset['file']), width=MAP_W, height=asset['height_pt']), Spacer(1, 5 if compact_lane else 9),
                 MapLegend(lane,asset), p(finding(lane),'finding'), p(brief_caption(asset), 'small')]
        story += [KeepTogether(block)]
        if lane['narrative']:
            if compact_lane:
                story += [p('Working assessment', 'lane_heading'), p('Hypothesis, not an established finding: '+lane['narrative'], 'lane_body')]
            else:
                story += [p('Working assessment', 'heading'), p('Hypothesis, not an established finding: '+lane['narrative'])]

    # Web Companion Competitive Intelligence Sections
    if intel:
        s_meta = intel['summary']
        q_list = intel['queries']
        q_ids = [q['id'] for q in q_list]
        q_short = {q['id']: q['query'] for q in q_list}

        # Section 1: Local Leaders & Territory Control
        story += [PageBreak(), p('Local leaders & territory control', 'lane_title')]
        story += [p(
            f"Across {s_meta['total_origins']} origins and {s_meta['total_queries']} queries, "
            f"{s_meta['all_winners_count']} distinct profiles reached #1 at least once, and "
            f"{s_meta['recurring_leaders_count']} recurring local leaders won 3+ origins in at least one query.",
            'small'
        )]
        leaders_map_path = output / 'leaders-map.png'
        if leaders_map_path.is_file():
            l_height = assets[0]['main']['height_pt']
            story += [CompanionMapImage(str(leaders_map_path), width=MAP_W, height=l_height), Spacer(1, 4)]
            story += [p(
                'Study-wide #1 winner territory map. Recurring leaders (3+ #1 wins in a query) receive neighbor-separated territory colors and L01-L14 cluster badges; crosshair marks primary business origin.',
                'small'
            )]

        story += [PageBreak(), p('Recurring #1 leaders by search', 'lane_title')]
        story += [p(
            'Top recurring #1 territory holders ranked by total #1 wins across all study queries. Badge codes match the territory map.',
            'small'
        )]
        l_headers = ['Badge', 'Business & Address', '#1 Wins', 'Top 3'] + [f"Q{idx+1} #1" for idx in range(len(q_ids[:4]))] + ['Share']
        l_rows = []
        l_hi = []
        for idx, row in enumerate((intel.get('pooled_leaders') or [])[:16]):
            if row.get('is_target'):
                l_hi.append(idx)
            addr = f" ({row['address'].split(',')[0]})" if row.get('address') else ''
            l_rows.append([
                row['badge'],
                f"{row['name']}{addr}",
                str(row['rank1_total']),
                str(row['top3_total']),
                *[str(row['per_query_rank1'].get(qid, 0)) for qid in q_ids[:4]],
                f"{row['share_of_first_place_pct']:.1f}%",
            ])
        if l_rows:
            q_cols = [44] * len(q_ids[:4])
            rem_w = COLUMN - (40 + 48 + 42 + 44 + sum(q_cols))
            story += [make_table(l_headers, l_rows, [40, rem_w, 48, 42, *q_cols, 44], highlight_rows=l_hi), Spacer(1, 6)]
            q_key_legend = ' | '.join(f"Q{idx+1}: {q['query']}" for idx, q in enumerate(q_list[:4]))
            story += [p('Search columns: ' + q_key_legend, 'small')]

        # Section 2: Competitive Field & Strategy Room Reach Matrix
        story += [PageBreak(), p('Competitive field & reach matrix', 'lane_title')]
        ts = intel.get('target_standing')
        if ts:
            story += [p(
                f"Primary business standing: #{ts['standing']} of {s_meta['total_observed_profiles']} observed profiles "
                f"by equal-query Top-3 coverage ({ts['top3_coverage_pct']:.2f}% avg Top-3 share; "
                f"{ts['top3_total']} Top-3 appearances; {ts['top10_total']} Top-10 appearances; "
                f"Top-20 visibility score {ts['visibility_score']:,}).",
                'small'
            )]
        cf_headers = ['Pos', 'Badge', 'Profile', 'Top-3 %', 'Top 3', 'Top 10', '#1 Wins', 'Score', 'Reviews']
        cf_rows = []
        cf_hi = []
        for idx, r in enumerate((intel.get('leaderboard') or [])[:10]):
            if r.get('is_target'):
                cf_hi.append(idx)
            rev = f"{r['rating']:.1f} ({r['votes_count']:,})" if r.get('rating') and r.get('votes_count') else 'n/a'
            cf_rows.append([
                f"#{r['standing']}",
                r['badge'],
                r['name'],
                f"{r['top3_coverage_pct']:.1f}%",
                str(r['top3_total']),
                str(r['top10_total']),
                str(r['rank1_total']),
                f"{r['visibility_score']:,}",
                rev,
            ])
        if cf_rows:
            story += [make_table(cf_headers, cf_rows, [32, 40, 142, 48, 42, 44, 48, 50, 70], highlight_rows=cf_hi), Spacer(1, 6)]

        story += [p('Strategy room distance & sector reach matrix (Top 3 / Ranks 4-10)', 'lane_heading')]
        sr_headers = ['Region', 'Points'] + [f"Q{idx+1}: {q_short[qid]}" for idx, qid in enumerate(q_ids[:4])]
        sr_rows = []
        for reg in (intel.get('strategy_regions') or [])[:6]:
            cells = [reg['label'], str(reg['count'])]
            for qid in q_ids[:4]:
                pq = reg['per_query'].get(qid, {})
                cells.append(f"{pq.get('top3', 0)} ({pq.get('top3_pct', 0):.0f}%) / {pq.get('near', 0)}")
            sr_rows.append(cells)
        if sr_rows:
            q_w = [round((COLUMN - 156) / max(1, len(q_ids[:4])))] * len(q_ids[:4])
            story += [make_table(sr_headers, sr_rows, [112, 44, *q_w], highlight_rows=(0, 1)), Spacer(1, 6)]

        pr_list = (intel.get('pressure_rivals') or [])[:5]
        if pr_list:
            story += [p('Local pressure rivals ahead at near-miss origins (ranks 4-10)', 'lane_heading')]
            pr_headers = ['Badge', 'Competitor', 'Ahead at 4-10', 'Near-Miss Share', 'Study Top 3', '#1 Wins']
            pr_rows = [
                [
                    r['badge'],
                    f"{r['name']} ({r['address'].split(',')[0]})" if r.get('address') else r['name'],
                    f"{r['near_ahead_total']} / {s_meta['near_miss_denominator']}",
                    f"{r['near_ahead_pct']:.1f}%",
                    str(r['top3_total']),
                    str(r['rank1_total']),
                ]
                for r in pr_list
            ]
            story += [make_table(pr_headers, pr_rows, [40, 210, 82, 74, 56, 54])]

        # Section 3: Territory Campaigns & Researched Action Briefs
        story += [PageBreak(), p('Territory campaigns & action briefs', 'lane_title')]
        if intel.get('campaign_summary'):
            story += [p(intel['campaign_summary'], 'small')]
        c_headers = ['Search Query', 'Defend (1-3)', 'Advance (4-10)', 'Service Gap', 'Frontier', 'Build (11-30)', 'Top Advance Blocker']
        c_rows = []
        for qid in q_ids:
            cq = (intel.get('campaigns_by_query') or {}).get(qid)
            if not cq:
                continue
            cnt = cq['counts']
            tb = cq['top_blockers'][0] if cq.get('top_blockers') else None
            tb_str = f"{tb['badge']} {tb['name']} ({tb['count']})" if tb else 'None'
            c_rows.append([
                cq['query'],
                str(cnt['defend']),
                str(cnt['advance']),
                str(cnt['service_gap']),
                str(cnt['frontier']),
                str(cnt['build']),
                tb_str,
            ])
        if c_rows:
            story += [make_table(c_headers, c_rows, [102, 54, 58, 52, 52, 56, 142]), Spacer(1, 6)]

        ab_rows = []
        for qid in q_ids:
            cq = (intel.get('campaigns_by_query') or {}).get(qid) or {}
            ab = cq.get('action_brief')
            if not ab:
                continue
            ab_rows.append([
                f"{cq['query']}\n({ab['area']})",
                ab['title'],
                f"{ab['action']} Check: {ab['success']}",
            ])
        if ab_rows:
            story += [p('Researched website & profile action briefs', 'lane_heading')]
            story += [make_table(['Search & Area', 'Focus', 'Recommended Action & Verification'], ab_rows, [110, 130, 276]), Spacer(1, 6)]

        plans = (intel.get('campaign_plans') or [])[:4]
        if plans:
            story += [PageBreak(), p('Prioritized territory campaign sequence', 'lane_title')]
            if intel.get('campaign_recommendation'):
                story += [p(intel['campaign_recommendation'], 'small')]
            p_headers = ['Stage & Campaign', 'Target Area & Baseline', 'Goal, Evidence & Verification Gate']
            p_rows = [
                [
                    f"{pl['stage']}: {pl['title']}",
                    f"{pl['area']}\n({pl['baseline_query']} - {pl['baseline_lens']})",
                    f"Goal: {pl['goal']}\nEvidence: {pl['evidence']}\nGate: {pl['gate']}",
                ]
                for pl in plans
            ]
            story += [make_table(p_headers, p_rows, [136, 126, 254])]

        # Section 4: Business-Name & Keyword Stuffing Review Dossier
        nr = intel.get('name_review')
        if nr and nr.get('flagged_cases'):
            story += [PageBreak(), p('Business-name & keyword review', 'lane_title')]
            story += [p(
                f"Reviewed {nr['analyst_reviewed']} of {nr['total_in_scope']} priority #1 competitor listings against "
                f"website branding and storefront signage under title-evidence-v1 (0-5 confidence scale): "
                f"{nr['supported_concerns']} supported concerns, {nr['possible_concerns']} possible concerns, "
                f"{nr['names_supported']} branding-consistent names, and {nr['unresolved']} unresolved.",
                'lane_body'
            )]
            nr_headers = ['Badge', 'GBP Listing Title', 'Website Brand', 'Level (0-5)', 'Optical / Signage', '#1 Wins', 'Suspect Terms']
            nr_rows = []
            for fc in nr['flagged_cases'][:14]:
                lvl_str = f"{fc['confidence_level']}/5 {fc['confidence_label']}" if fc.get('confidence_level') is not None else fc['bracket_label']
                site_str = ', '.join(fc.get('website_brands') or []) or 'Unverified'
                terms_str = ', '.join(fc.get('suspect_terms') or []) or 'Title modifier'
                nr_rows.append([
                    fc['badge'],
                    fc['name'],
                    site_str,
                    lvl_str,
                    fc.get('jev_verdict') or 'Web review',
                    str(fc['total_wins']),
                    terms_str,
                ])
            story += [make_table(nr_headers, nr_rows, [40, 126, 86, 68, 72, 38, 86]), Spacer(1, 6)]
            story += [p(
                'Evidence note: Title discrepancy indicators document differences between observed Google Business Profile titles, public websites, and street-level signage. They do not prove ranking causation or legal violation.',
                'small'
            )]

    story += [PageBreak(), p('Recommended next steps', 'title')]
    if brief['actions']:
        for action in brief['actions']:
            story += [p(str(action['priority']).zfill(2)+' / '+action['title'], 'category')]
            story += [p(label+action[key]) for label,key in [('Why: ', 'why'), ('Do next: ', 'next_step'), ('Check success: ', 'success_check'), ('Still uncertain: ', 'uncertainty')]]
            story += [p('Suggested owner: '+action['owner']+'. Evidence: '+', '.join(x['pointer'] for x in action['evidence']), 'small')]
    elif model['next_actions']:
        story += [p(t) for t in model['next_actions']]
    else:
        story += [p('No business recommendations were supplied. Observations alone do not establish causes, demand, or likely returns.')]
    if not model['synthetic']:
        from sampling_review import summary as sampling_summary
        story += [p('Where additional measurement would help','heading')]+[p(t) for t in sampling_summary(model)]
    if model.get('verification_notes'):
        story += [p('How the findings were checked', 'heading')] + [p(t) for t in model['verification_notes']]
    story += [p('What remains unverified', 'heading')]
    if any(lane['missing_evidence'] for lane in model['lanes']):
        for lane in model['lanes']:
            story += [keyword(lane['query'])]
            story += [p(t) for t in lane['missing_evidence']] or [p('No missing timestamp, depth, count, or cutoff sequence detected. Causal evidence and market representativeness remain unestablished.')]
    else:
        q_names = ', '.join(lane['query'] for lane in model['lanes'])
        story += [p(f'Across all evaluated searches ({q_names}), no missing timestamp, depth, count, or cutoff sequence was detected. Causal ranking drivers and market-wide revenue conversion remain unestablished.')]
    if model['missing_evidence']:
        story += [p('Additional open questions', 'heading')] + [p(t) for t in model['missing_evidence']]
    story += [PageBreak(), p('Evidence & denominator appendix', 'title')]
    story += [p(model['evidence_disclosure'],'small'),p('Objectives','heading')]+[p(x) for x in model['objectives']]
    story += [p('Evidence boundaries','heading'),p(LIMITS),p(center_disclosure(model),'small')]
    for lane_index, lane in enumerate(model['lanes']):
        m = lane['metrics']
        lane_block = [keyword(lane['query']), p(finding(lane)),
                      p(map_caption(lane, assets[lane_index]['main']), 'small'),
                      p('States: '+', '.join(f'{k} {v}' for k, v in m['states'].items())+'.', 'small')]
        sources = sorted({r['source'] for r in lane['records']})
        times = sorted({r['sampled_at'] for r in lane['records'] if r['sampled_at']},
                       key=lambda t: datetime.fromisoformat(t.replace('Z', '+00:00')))
        lane_block += [p('Sources: '+'; '.join(sources)+'. Timestamp range: '+(' to '.join((times[0], times[-1])) if times else 'not recorded')+'.', 'small')]
        center_term = 'declared market reference' if model['center_kind']=='market' else 'user-supplied business origin'
        lane_block += [p('Evidence bounds [west, south, east, north]: '+', '.join(f'{v:.7f}' for v in lane['full_bounds'])+
                    '. Includes padding around supplied origins and the '+center_term+
                    '. Exact observations are in report-model.json and the HTML ledger.', 'small')]
        for cutoff in (3, 10):
            share = m[f'top{cutoff}_observed_share']
            lane_block += [p(f'Observed top {cutoff} share: '+(f'{share:.1%}' if share is not None else 'undefined')+
                        f"; not-returned origins with unknown top-{cutoff} absence: {m[f'top{cutoff}_unknown_absence']}.", 'small')]
        story += [KeepTogether(lane_block)]
    for i, lane in enumerate(model['lanes']):
        if 'full' in assets[i]:
            asset = assets[i]['full']
            story += [PageBreak(), p('Full extent: '+lane['label'], 'title'), p('All supplied origins, including those outside the main view.', 'small'),
                      KeepTogether([TrackedImage(str(output / asset['file']), width=MAP_W, height=asset['height_pt']), Spacer(1, 9),
                                    MapLegend(lane,asset), p(map_caption(lane, asset), 'small')])]
    doc.build(story)
    add_pdf_brand_links(output / 'report.pdf')
    for box in log:
        require(box['x'] >= MARGIN-.1 and box['x']+box['width'] <= PAGE_W-MARGIN+.1 and
                box['y'] >= 57.9 and box['y']+box['height'] <= 727.1, f'PDF layout overflow: {box}')
        if box['kind'] == 'text':
            require(box['font_size_pt'] >= 8.5, 'PDF text below readable floor')
    for i, a in enumerate(log):
        for b in log[i+1:]:
            if a['page'] != b['page']:
                continue
            dx = min(a['x']+a['width'], b['x']+b['width']) - max(a['x'], b['x'])
            dy = min(a['y']+a['height'], b['y']+b['height']) - max(a['y'], b['y'])
            require(dx <= .1 or dy <= .1, f"PDF element collision on page {a['page']}")
    return log


def render_html(model, assets, output):
    prepare_html_font(output,THEME)
    def p(s):
        return '<p>'+escape(s).replace('\n', '<br>')+'</p>'
    def h(s, level=2):
        return f'<h{level}>'+escape(s.lower() if level!=1 else s)+f'</h{level}>'
    def pill(badge, color=None):
        valid_hex = bool(color and THEME != 'light' and re.fullmatch(r'#[0-9A-Fa-f]{6}', str(color)))
        style = f' style="border-color:{escape(str(color), quote=True)}"' if valid_hex else ''
        return f'<span class="leader-pill"{style}>{escape(str(badge))}</span>'
    def legend(lane):
        items = ['<span style="display:inline-block;margin-right:20px"><span aria-hidden="true" '
                 'style="display:inline-block;width:8px;height:8px;box-sizing:border-box;border-radius:50%;margin-right:6px;'+
                 ('border:1px solid '+color if hollow else 'background:'+color)+'"></span>'
                 +label+'</span>' for label,color,hollow in legend_items()]
        items += ['<span>Rings: '+lane['map'].get('distance_unit','km')+'</span>']
        if any(lane['metrics']['states'].get(k,0) for k in ('error','empty','unmeasured')):
            items += ['<br>E: error · Ø: empty · U: unmeasured (excluded from measured denominator)']
        return '<p class="report-legend" style="color:'+(INK)+'">'+''.join(items)+'</p>'
    from report_design import prepare_banner
    prepare_banner(output, THEME)
    intel = model.get('companion_intel')
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">',
             '<title>'+escape(model['business']['name'])+' | legends-geogrid</title>',
             '<style>'+html_styles(THEME)+'</style><main data-design="'+DESIGN_VERSION+'" data-stage="findings">'+BRAND_TOP+'<header class="report-cover">',
             ('<img class="banner" src="banner.png" alt="legends-geogrid"><p class="eyebrow">study findings</p>'),
             h(model['business']['name'],1), p(model['business']['location'])]
    if model['business'].get('website'):
        website = escape(model['business']['website'], quote=True)
        parts += ['<p class="business-domain"><a href="'+website+'">'+website+'</a></p>']
    brief = model['decision_brief']
    if brief.get('headline'):
        parts += [h(brief['headline']), p(brief['explanation']), h('Start here',3)]
        parts += [p(str(a['priority'])+'. '+a['title']) for a in brief['actions'][:3]]
    if model['synthetic']:
        parts += [h('Synthetic demonstration — no real business findings')]
    parts += [h('visibility at a glance'), '<table class="visibility-table"><thead><tr><th>search</th><th>top 3</th><th>top 10</th><th>measured</th></tr></thead><tbody>']
    for lane in model['lanes']:
        m=lane['metrics']
        parts += ['<tr><td>'+escape(lane['query'])+'</td><td>'+(str(m['top3'])+'/'+str(m['measured'])+'<span class="metric-rail" aria-hidden="true"><span style="width:'+str(100*m['top3']/m['measured'])+'%"></span></span>' if m['measured'] else 'not measured')+'</td><td>'+(str(m['top10'])+'/'+str(m['measured']) if m['measured'] else 'not measured')+'</td><td>'+str(m['measured'])+'/'+str(m['sampled'])+'</td></tr>']
    parts += ['</tbody></table><p class="summary-note">Counts describe sampled locations, not customers or market share. Unmeasured origins are excluded from rank denominators; no measured origins means no rank conclusion.</p>']
    if not brief.get('headline'):
        parts += [h('working assessment'),p('Hypothesis, not an established finding: '+model['thesis'])]
    parts += [h('important limitations')]+[p(x) for x in model['missing_evidence']]
    parts += ['<details><summary>study objectives and measurement boundaries</summary>']
    parts += [h('Objectives')]+[p(x) for x in model['objectives']]
    parts += [h('Evidence boundaries'), p(LIMITS), p(center_disclosure(model)+f" Coordinates: {model['business']['lat']:.7f}, {model['business']['lng']:.7f}.")]
    parts += [p(model['evidence_disclosure']), '</details>']
    brief = model['decision_brief']
    parts += ['</header><section class="report-section" aria-label="Reading the findings">', h('Reading the findings')]
    parts += [p(brief['reading_guide'])]+[p(x['text']) for x in brief['findings']]+[p(brief['boundary'])]
    profile = model.get('profile_review')
    if profile:
        from profile_review import readable
        parts += [h('The business behind the listing'), p(profile['access']), p(profile['identity_assessment'])]
        parts += ['<p><a href="'+escape(profile['profile_url'],quote=True)+'">Open the named Google Business Profile</a></p>']
        for fact in profile['facts']:
            if fact['field'] in ('category','address','phone','rating','local_business_links'):
                parts += [h(fact['label'],3),p(readable(fact))]
        parts += ['<details><summary>Additional profile fields and observation date</summary>',p(profile['observed_at'])]
        for fact in profile['facts']:
            if fact['field'] not in ('category','address','phone','rating','local_business_links'):
                parts += [h(fact['label'],3),p(readable(fact))]
        parts += ['</details>']
        parts += [p(profile['website_assessment']),p(profile['limitation']),h('Why these searches matter')]
        parts += ['<div class="query-deck">']
        for index, theme in enumerate(profile['themes'],1):
            parts += ['<article class="query-ticket"><span class="query-index">SEARCH '+str(index).zfill(2)+'</span>',h(theme['query'],3),p(theme['customer_need']),p(theme['why']),'<details><summary>Evidence boundaries</summary>'+p(theme['limitations'])+'</details></article>']
        parts += ['</div>']
    parts += ['</section><nav class="report-nav" aria-label="Report sections">']
    parts += [f'<a href="#query-{i+1}">'+escape(lane['label'])+'</a>' for i,lane in enumerate(model['lanes'])]
    if intel:
        parts += [
            '<a href="#local-leaders">Local leaders</a>',
            '<a href="#competitive-field">Competitive field</a>',
            '<a href="#territory-campaigns">Campaigns</a>',
        ]
        if intel.get('name_review'):
            parts += ['<a href="#name-review">Name review</a>']
    parts += ['<a href="#next-steps">Next steps</a></nav>']
    for i, lane in enumerate(model['lanes']):
        parts += [f'<section class="report-lane" id="query-{i+1}">', '<p class="eyebrow">SEARCH '+str(i+1)+'</p>', h(lane['label']), '<p><span class="query-token">'+escape(lane['query'])+'</span></p>']
        for kind in ('main', 'full'):
            if kind not in assets[i]:
                continue
            asset = assets[i][kind]
            if kind == 'full':
                parts += [h('Full extent appendix',3)]
            parts += ['<figure class="report-map">', f'<img src="{asset["file"]}" alt="{escape(lane["label"], quote=True)}: {asset["plotted"]} exact-coordinate observations">',
                      legend(lane), ('<figcaption><details><summary>map extent, attribution and method</summary>'+escape(map_caption(lane, asset))+'</details></figcaption>')+'</figure>']
        parts += [h('Computed finding',3), p(finding(lane))]
        if lane['narrative']:
            parts += [h('Working assessment',3), p('Hypothesis, not an established finding: '+lane['narrative'])]
        parts += [h('What remains unverified',3)] + [p(x) for x in lane['missing_evidence']]
        parts += ['<details><summary>Exact observation ledger</summary><div class="scroll"><table><thead><tr>']
        columns = ('lat','lng','rank','state','returned_count','depth','sampled_at','source')
        parts += ['<th scope="col">'+escape(x)+'</th>' for x in columns]
        parts += ['</tr></thead><tbody>']
        for row in lane['records']:
            parts += ['<tr>'] + ['<td>'+escape(str(row[x]) if row[x] is not None else 'unknown')+'</td>' for x in columns] + ['</tr>']
        parts += ['</tbody></table></div></details></section>']

    if intel:
        s_meta = intel['summary']
        q_list = intel['queries']
        q_ids = [q['id'] for q in q_list]

        # HTML Section 1: Local Leaders & Territory Control
        parts += ['<section class="report-section" id="local-leaders">', '<p class="eyebrow">web companion lens 01</p>', h('Local leaders & territory control')]
        parts += [p(
            f"Across {s_meta['total_origins']} grid origins and {s_meta['total_queries']} searches, "
            f"{s_meta['all_winners_count']} distinct Google Business Profiles reached #1 at least once, and "
            f"{s_meta['recurring_leaders_count']} recurring local leaders won 3+ origins in at least one search."
        )]
        if (output / 'leaders-map.png').is_file():
            parts += [
                '<figure class="report-map">',
                '<img src="leaders-map.png" alt="Study-wide local leaders territory map">',
                '<figcaption>Study-wide #1 winner territory map. Recurring leaders (3+ #1 wins in a search) receive neighbor-separated territory colors and L01-L14 cluster badges.</figcaption>',
                '</figure>',
            ]
        parts += [h('Top recurring #1 leaders across all searches', 3), '<div class="scroll"><table class="visibility-table"><thead><tr><th>badge</th><th>business</th><th>#1 wins</th><th>top 3</th>']
        for q in q_list:
            parts += ['<th>'+escape(q['query'])+' #1</th>']
        parts += ['<th>#1 share</th></tr></thead><tbody>']
        for row in (intel.get('pooled_leaders') or [])[:16]:
            tr_cls = ' class="target-row"' if row.get('is_target') else ''
            addr = f" ({row['address']})" if row.get('address') else ''
            parts += [f'<tr{tr_cls}><td>{pill(row["badge"], row.get("color"))}</td><td>{escape(row["name"] + addr)}</td><td>{int(row["rank1_total"])}</td><td>{int(row["top3_total"])}</td>']
            for qid in q_ids:
                parts += [f'<td>{int(row["per_query_rank1"].get(qid, 0))}</td>']
            parts += [f'<td>{float(row["share_of_first_place_pct"]):.1f}%</td></tr>']
        parts += ['</tbody></table></div></section>']

        # HTML Section 2: Competitive Field & Reach Matrix
        parts += ['<section class="report-section" id="competitive-field">', '<p class="eyebrow">web companion lens 02</p>', h('Competitive field & reach matrix')]
        ts = intel.get('target_standing')
        if ts:
            parts += [p(
                f"Primary business standing: #{int(ts['standing'])} of {int(s_meta['total_observed_profiles'])} observed profiles "
                f"by equal-query Top-3 coverage ({float(ts['top3_coverage_pct']):.2f}% average Top-3 share; "
                f"{int(ts['top3_total'])} Top-3 appearances; {int(ts['top10_total'])} Top-10 appearances; "
                f"Top-20 visibility score {int(ts['visibility_score']):,})."
            )]
        parts += [h('Competitive field leaderboard', 3), '<div class="scroll"><table class="visibility-table"><thead><tr><th>standing</th><th>badge</th><th>profile</th><th>equal-query top-3 %</th><th>top 3</th><th>top 10</th><th>#1 wins</th><th>visibility score</th><th>reviews</th></tr></thead><tbody>']
        for r in (intel.get('leaderboard') or [])[:15]:
            tr_cls = ' class="target-row"' if r.get('is_target') else ''
            rev = f"{float(r['rating']):.1f} ({int(r['votes_count']):,})" if r.get('rating') and r.get('votes_count') else 'n/a'
            parts += [
                f'<tr{tr_cls}><td>#{int(r["standing"])}</td><td>{pill(r["badge"], r.get("color"))}</td>'
                f'<td>{escape(r["name"])}</td><td>{float(r["top3_coverage_pct"]):.2f}%</td><td>{int(r["top3_total"])}</td>'
                f'<td>{int(r["top10_total"])}</td><td>{int(r["rank1_total"])}</td><td>{int(r["visibility_score"]):,}</td><td>{escape(rev)}</td></tr>'
            ]
        parts += ['</tbody></table></div>']

        parts += [h('Strategy room distance & sector reach matrix', 3), '<div class="scroll"><table class="visibility-table"><thead><tr><th>region</th><th>origins</th>']
        for q in q_list:
            parts += ['<th>'+escape(q['query'])+' (top 3 / ranks 4-10)</th>']
        parts += ['</tr></thead><tbody>']
        for reg in (intel.get('strategy_regions') or []):
            parts += [f'<tr><td>{escape(reg["label"])}</td><td>{int(reg["count"])}</td>']
            for qid in q_ids:
                pq = reg['per_query'].get(qid, {})
                parts += [f'<td>{int(pq.get("top3", 0))} ({float(pq.get("top3_pct", 0)):.1f}%) / {int(pq.get("near", 0))} near</td>']
            parts += ['</tr>']
        parts += ['</tbody></table></div>']

        pr_list = intel.get('pressure_rivals') or []
        if pr_list:
            parts += [h('Local pressure rivals ahead at near-miss origins (ranks 4-10)', 3), '<div class="scroll"><table class="visibility-table"><thead><tr><th>badge</th><th>competitor</th><th>ahead at 4-10 origins</th><th>share of near misses</th><th>study top 3</th><th>#1 wins</th></tr></thead><tbody>']
            for r in pr_list:
                addr = f" ({r['address']})" if r.get('address') else ''
                parts += [
                    f'<tr><td>{pill(r["badge"], r.get("color"))}</td><td>{escape(r["name"] + addr)}</td>'
                    f'<td>{int(r["near_ahead_total"])} / {int(s_meta["near_miss_denominator"])}</td><td>{float(r["near_ahead_pct"]):.1f}%</td>'
                    f'<td>{int(r["top3_total"])}</td><td>{int(r["rank1_total"])}</td></tr>'
                ]
            parts += ['</tbody></table></div>']
        parts += ['</section>']

        # HTML Section 3: Territory Campaigns & Action Briefs
        parts += ['<section class="report-section" id="territory-campaigns">', '<p class="eyebrow">web companion lens 03</p>', h('Territory campaigns & action briefs')]
        if intel.get('campaign_summary'):
            parts += [p(intel['campaign_summary'])]
        parts += ['<div class="scroll"><table class="visibility-table"><thead><tr><th>search</th><th>defend (1-3)</th><th>advance (4-10)</th><th>service gap</th><th>expansion frontier</th><th>build (11-30)</th><th>top advance blocker</th></tr></thead><tbody>']
        for qid in q_ids:
            cq = (intel.get('campaigns_by_query') or {}).get(qid)
            if not cq:
                continue
            cnt = cq['counts']
            tb = cq['top_blockers'][0] if cq.get('top_blockers') else None
            tb_html = f"{pill(tb['badge'], tb.get('color'))} {escape(tb['name'])} ({int(tb['count'])})" if tb else 'None'
            parts += [
                f'<tr><td>{escape(cq["query"])}</td><td>{int(cnt["defend"])}</td><td>{int(cnt["advance"])}</td>'
                f'<td>{int(cnt["service_gap"])}</td><td>{int(cnt["frontier"])}</td><td>{int(cnt["build"])}</td><td>{tb_html}</td></tr>'
            ]
        parts += ['</tbody></table></div>']

        parts += ['<div class="intel-grid">']
        for qid in q_ids:
            cq = (intel.get('campaigns_by_query') or {}).get(qid) or {}
            ab = cq.get('action_brief')
            if not ab:
                continue
            parts += [
                '<article class="intel-card">',
                '<span class="query-index">'+escape(cq['query'] + ' / ' + ab['area'])+'</span>',
                h(ab['title'], 3),
                p('Observed: ' + ab['observed']),
                p('Recommended action: ' + ab['action']),
                p('Verification check: ' + ab['success']),
                '</article>',
            ]
        parts += ['</div>']

        plans = intel.get('campaign_plans') or []
        if plans:
            parts += [h('Prioritized territory campaign sequence', 3), '<div class="intel-grid">']
            for pl in plans:
                parts += [
                    '<article class="intel-card">',
                    '<span class="query-index">'+escape(pl['stage'] + ' / ' + pl['area'])+'</span>',
                    h(pl['title'], 3),
                    p('Goal: ' + pl['goal']),
                    p('Evidence: ' + pl['evidence']),
                    p('Verification gate: ' + pl['gate']),
                    '</article>',
                ]
            parts += ['</div>']
        parts += ['</section>']

        # HTML Section 4: Business-Name & Keyword Stuffing Review Dossier
        nr = intel.get('name_review')
        if nr and nr.get('flagged_cases'):
            parts += ['<section class="report-section" id="name-review">', '<p class="eyebrow">web companion lens 04</p>', h('Business-name & keyword review')]
            parts += [p(
                f"Reviewed {int(nr['analyst_reviewed'])} of {int(nr['total_in_scope'])} priority #1 competitor listings against "
                f"public website branding and street-level storefront signage under title-evidence-v1 (0-5 confidence scale): "
                f"{int(nr['supported_concerns'])} supported concerns, {int(nr['possible_concerns'])} possible concerns, "
                f"{int(nr['names_supported'])} branding-supported names, and {int(nr['unresolved'])} unresolved."
            )]
            parts += ['<div class="scroll"><table class="visibility-table"><thead><tr><th>badge</th><th>gbp listing title</th><th>website brand</th><th>confidence (0-5)</th><th>signage / optical</th><th>#1 wins</th><th>suspect terms & finding</th></tr></thead><tbody>']
            for fc in nr['flagged_cases']:
                lvl_str = f"{fc['confidence_level']}/5 {fc['confidence_label']}" if fc.get('confidence_level') is not None else fc['bracket_label']
                site_str = ', '.join(fc.get('website_brands') or []) or 'Unverified'
                terms_str = ', '.join(fc.get('suspect_terms') or [])
                finding_str = (f"[{terms_str}] " if terms_str else '') + (fc.get('finding') or '')
                parts += [
                    f'<tr><td>{pill(fc["badge"], fc.get("color"))}</td><td>{escape(fc["name"])}</td>'
                    f'<td>{escape(site_str)}</td><td>{escape(lvl_str)}</td><td>{escape(fc.get("jev_verdict") or "Web review")}</td>'
                    f'<td>{int(fc["total_wins"])}</td><td>{escape(finding_str)}</td></tr>'
                ]
            parts += ['</tbody></table></div></section>']

    parts += ['<section class="report-section" id="next-steps">', h('Recommended next steps')]
    parts += [h('What to do next',3)]
    if brief['actions']:
        for action in brief['actions']:
            parts += ['<article class="decision-card"><span class="decision-class">'+escape(action.get('category','investigation').replace('_',' '))+'</span>', h(str(action['priority']).zfill(2)+' / '+action['title'],3)]
            parts += ['<p><strong class="decision-label">'+escape(label)+'</strong>'+escape(action[key])+'</p>' for label,key in [('why it matters', 'why'), ('do next', 'next_step'), ('check success', 'success_check'), ('still uncertain', 'uncertainty')]]
            parts += [p('Suggested owner: '+action['owner']), '<details><summary>Supporting evidence</summary>']
            parts += [p(x['pointer']+': '+json.dumps(x['value'],ensure_ascii=False)) for x in action['evidence']]
            parts += ['</details></article>']
    else:
        parts += [p(x) for x in model['next_actions'] or ['No business recommendations supplied.']]
    if not model['synthetic']:
        from sampling_review import summary as sampling_summary
        parts += [h('Where additional measurement would help',3)]+[p(t) for t in sampling_summary(model)]
    if model.get('verification_notes'):
        parts += ['<details><summary>How the findings were checked</summary>']+[p(x) for x in model['verification_notes']]+['</details>']
    parts += [h('What remains unverified')]+[p(x) for x in model['missing_evidence']]
    parts += ['</section><footer class="report-downloads"><p><a href="report.pdf">PDF report</a> · <a href="report-model.json">Normalized evidence and metrics</a> · <a href="report-qa.json">QA receipt</a></p>'+BRAND_BOTTOM+'</footer></main></html>']
    html = display_text('\n'.join(parts))
    require('\u2014' not in html, 'HTML contains forbidden em dash')
    (output/'report.html').write_text(html, encoding='utf-8')


def pdf_qa(path, proof=False, required=False):
    try:
        import pypdfium2 as pdfium
    except ImportError:
        require(not required, 'pypdfium2 required by --require-pdf-qa; install requirements-report.txt')
        return {'status':'skipped', 'reason':'pypdfium2 not installed; layout checks only'}
    issues, pages = [], []
    with pdfium.PdfDocument(str(path)) as doc:
        for i in range(len(doc)):
            page = doc[i]
            textpage = page.get_textpage()
            contents = textpage.get_text_range()
            if '\u2014' in contents:
                issues.append(f'page {i+1}: forbidden em dash')
            if len(contents.strip()) < 40:
                issues.append(f'page {i+1}: insufficient text')
            if tuple(round(v, 2) for v in page.get_size()) != (PAGE_W, PAGE_H):
                issues.append(f'page {i+1}: not Letter')
            bad = []
            for j in range(textpage.count_chars()):
                char = textpage.get_text_range(j, 1)
                if not char.strip():
                    continue
                left, bottom, right, top = textpage.get_charbox(j)
                if left < 47.4 or right > 564.6 or bottom < 23 or top > 774:
                    bad.append(j)
            if bad:
                issues.append(f'page {i+1}: {len(bad)} text glyphs outside bounds')
            bitmap = page.render(scale=1.5 if proof else .25)
            rendered = bitmap.to_pil().convert('RGB')
            corner = rendered.getpixel((1,1))
            expected = tuple(int(BG[k:k+2], 16) for k in (1, 3, 5))
            if max(abs(a-b) for a, b in zip(corner, expected)) > 20:
                issues.append(f'page {i+1}: theme background missing')
            if proof:
                proof_dir = path.parent/'proof'
                proof_dir.mkdir(exist_ok=True)
                rendered.save(proof_dir/f'page-{i+1:02d}.png')
            pages.append({'page':i+1, 'characters':len(contents), 'out_of_bounds_glyphs':len(bad)})
            bitmap.close()
            textpage.close()
            page.close()
    return {'status':'passed' if not issues else 'failed', 'engine':'pypdfium2', 'pages':pages, 'issues':issues}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


def build(config, output_dir, require_pdf_qa=False, proof=False, basemap_provider=None, allow_google_maps=False):
    from local_heatmap_poc import _safe_local_path
    from report_basemaps import BasemapSession, provider_for
    model = load_config(config)
    providers = [provider_for(model,lane,basemap_provider) for lane in model['lanes']]
    apply_theme(model.get('theme', DEFAULT_THEME))
    output = _safe_local_path(output_dir).resolve()
    require(not output.exists() or not any(output.iterdir()), 'output directory must be new or empty; existing files are preserved')
    fonts = register_fonts(model)
    output.mkdir(parents=True, exist_ok=True)
    # Complete and validate in a temporary sibling; invalid input leaves no
    # partial published report. Move only verified, newly generated artifacts.
    with tempfile.TemporaryDirectory(prefix='.geogrid-report-', dir=output.parent) as folder:
        stage = Path(folder)
        basemaps = BasemapSession(stage/'basemaps',model['theme'],allow_google_maps)
        assets = []
        for i, lane in enumerate(model['lanes'], 1):
            provider = providers[i-1]
            lane['map']['provider'] = provider
            if provider == 'schematic':
                lane['map'].pop('basemap',None)
            elif provider in ('openfreemap','google'):
                lane['map']['basemap'] = basemaps.acquire(provider,lane['map']['bounds'],lane['map'].get('height_pt',452))
                if lane['needs_appendix']:
                    lane['map']['full_basemap'] = basemaps.acquire(provider,lane['full_bounds'],MAP_H)
            asset = {'main':map_image(lane, model['business'], stage/f'map-{i:03d}.png', fonts)}
            if lane['needs_appendix']:
                asset['full'] = map_image(lane, model['business'], stage/f'map-{i:03d}-full.png', fonts, full=True)
            for view in asset.values():
                view.update(center_kind=model['center_kind'], center_label=model['center_label'])
            assets.append(asset)
        if model.get('companion_intel') and model['lanes']:
            leaders_map_image(model, model['lanes'][0], stage / 'leaders-map.png', fonts)
        map_validation = [dict(query_id=lane['query_id'], **{
            kind:map_qa(lane,model['business'],asset,stage/asset['file'],fonts)
            for kind,asset in group.items()}) for lane,group in zip(model['lanes'],assets)]
        layout = render_pdf(model, assets, stage)
        render_html(model, assets, stage)
        # Strip operational input paths, retaining attribution and georeferencing.
        public_model = json.loads(json.dumps(model))
        public_model.pop('fonts', None)
        for lane in public_model['lanes']:
            for key in ('basemap','full_basemap'):
                base = lane['map'].get(key,{})
                base.pop('path',None)
        write_json(stage/'report-model.json', public_model)
        from sampling_review import review as review_sampling
        write_json(stage/'sampling-review.json', review_sampling(public_model))
        validation = pdf_qa(stage/'report.pdf', proof, require_pdf_qa)
        require(validation['status'] != 'failed', f"PDF QA failed: {validation.get('issues')}")
        receipt = dict(design_version=DESIGN_VERSION, status='passed' if validation['status']=='passed' else 'layout-passed-pdf-qa-skipped',
                       network_calls=basemaps.network_calls, basemap_providers=providers, pdf=validation, map_validation=map_validation, layout_boxes=layout, maps=assets,
                       metrics={lane['query_id']:lane['metrics'] for lane in model['lanes']},
                       sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.iterdir() if p.is_file()})
        write_json(stage/'report-qa.json', receipt)
        require(not any(output.iterdir()), 'output changed during rendering; refusing to overwrite')
        for file in stage.iterdir():
            file.rename(output/file.name)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--require-pdf-qa', action='store_true')
    parser.add_argument('--basemap', choices=('auto','openfreemap','google','supplied','schematic'), help='Street maps default for real reports; synthetic fixtures remain offline')
    parser.add_argument('--allow-google-maps-charge', action='store_true', help='Explicitly permit Google Static Maps requests; billed separately from ranking data')
    parser.add_argument('--proof', action='store_true', help='render PDF pages to local proof PNGs')
    parser.add_argument('--study-plan',type=Path,help='Research plan to bank with the completed report; auto-detected beside standard report configs')
    parser.add_argument('--vault-dir',type=Path,help='Study library vault root')
    parser.add_argument('--study-run-dir',type=Path,help='Exact original collection folder for banking; otherwise inferred only from plan in evidence/')
    args = parser.parse_args(argv)
    try:
        from report_basemaps import BasemapError, has_configured_google_key
        basemap_choice = args.basemap
        allow_google = args.allow_google_maps_charge
        if basemap_choice in (None, 'auto') and args.config.is_file() and has_configured_google_key(check_dotenv=True) and not load_config(args.config).get('synthetic'):
            try:
                receipt = build(args.config, args.output_dir, args.require_pdf_qa, args.proof, 'google', True)
            except BasemapError:
                receipt = build(args.config, args.output_dir, args.require_pdf_qa, args.proof, 'openfreemap', False)
        else:
            receipt = build(args.config, args.output_dir, args.require_pdf_qa, args.proof, basemap_choice, allow_google)
        plan=args.study_plan or args.config.resolve().parent/'evidence/study-plan.json'
        if plan.is_file():
            from study_library import bank_study
            run_dir=args.study_run_dir or (plan.resolve().parent.parent if plan.resolve().parent.name=='evidence' else None)
            receipt['library']=bank_study(plan,run_dir,args.output_dir,vault=args.vault_dir,stage='report-complete')
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f'Report failed: {exc}', file=sys.stderr)
        return 2
    print(json.dumps({'status':receipt['status'], 'output_dir':str(args.output_dir),'library':receipt.get('library')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
