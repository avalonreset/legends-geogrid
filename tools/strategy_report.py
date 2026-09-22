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

BG = '#08131E'
PANEL = '#102434'
INK = '#F3F6F8'
MUTED = '#A9BDCA'
ACCENT = '#A9BDCA'
LINE = '#375061'
THEME = 'geogrid'
# Page palettes. Rank marker colors are part of the evidence contract and never change.
THEMES = {
    'geogrid': dict(BG='#08131E', PANEL='#102434', INK='#F3F6F8', MUTED='#A9BDCA', ACCENT='#A9BDCA', LINE='#375061'),
    'light': dict(BG='#FFFFFF', PANEL='#FFFFFF', INK='#0F0F10', MUTED='#6D6D6A', ACCENT='#C80000', LINE='#D8D8D4'),
}
HEADER_COLORS = ('#CC0000', '#8C0000', '#111111', '#777777', '#FFFFFF')
DEFAULT_THEME = 'geogrid'
THEME_FONTS = Path(__file__).parent / 'fonts'


def apply_theme(name):
    global THEME
    THEME = name
    globals().update(THEMES[name])


apply_theme(DEFAULT_THEME)
PAGE_W, PAGE_H, MARGIN, COLUMN = 612, 792, 48, 516
MAP_W, MAP_H, SCALE = 516, 410, 3
LEGEND = 'Ranks 1–3: green | Ranks 4–10: yellow | Ranks 11+: red | Hollow: not returned | E: error | Ø: empty | U: unmeasured'
RANK_COLORS = ('#00FF00', '#FFFF00', '#FF0000')
LIMITS = ('Measured means found or not returned. Empty, error, and unmeasured origins are excluded. '
          'Top-3 and top-10 shares are observed appearances divided by valid measured origins; '
          'they are not area or market coverage. A requested depth or returned count alone does not '
          'prove absence at a cutoff. Near misses are exactly ranks 4–10 inclusive. '
          'Results describe supplied origins and timestamps only; no sampled boundary proves total absence.')


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


def shade_bands(overlay, rings):
    """Alternating neutral annuli, painted largest first without alpha stacking."""
    from PIL import ImageDraw
    draw = ImageDraw.Draw(overlay)
    for i in reversed(range(len(rings))):
        draw.polygon([tuple(p) for p in rings[i]['points_px']], fill=(255,255,255,34 if i % 2 == 0 else 12))
    for ring in rings:
        draw.line([tuple(p) for p in ring['points_px']], fill=(169,189,202,140), width=2)


def display_distance(km, unit='km'):
    """Convert display values only; geodesic inputs and evidence stay in km."""
    require(unit in ('km', 'mi'), 'distance unit must be km or mi')
    return f'{km / 1.609344 if unit == "mi" else km:g}'


def paint_band_labels(canvas, rings, fonts, frame, distance_unit='km'):
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(canvas)
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
    if model.get('theme', DEFAULT_THEME) == 'light' and (THEME_FONTS / 'Inter-Regular.ttf').is_file():
        # Bundled OFL fonts for the light theme (see tools/fonts/*-OFL.txt).
        default = {'regular': str(THEME_FONTS / 'Inter-Regular.ttf'), 'bold': str(THEME_FONTS / 'Inter-SemiBold.ttf'),
                   'title': str(THEME_FONTS / 'Inter-SemiBold.ttf'), 'mono': str(THEME_FONTS / 'JetBrainsMono-Medium.ttf')}
    else:
        default = {'regular': str(root / 'Vera.ttf'), 'bold': str(root / 'VeraBd.ttf')}
    paths = model.get('fonts', default)
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
    base = lane['map'].get('basemap')
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
    shade_bands(overlay, ring_geometry)
    canvas.paste(overlay, (0, 0), overlay)
    distance_unit = lane['map'].get('distance_unit','km')
    band_labels = paint_band_labels(canvas,ring_geometry,fonts,overlay_frame,distance_unit)
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(fonts['bold'], 8 * SCALE)
    small = ImageFont.truetype(fonts['regular'], round(8.5 * SCALE))
    pins, marker_geometry = [], []
    for index, row in enumerate(lane['records']):
        if not inside(row, extent):
            continue
        x, y = projection.point(row['lat'], row['lng'])
        state, rank = row['state'], row['rank']
        label = marker_label(state, rank)
        color, ink = marker_style(state, rank)
        box = draw.textbbox((0, 0), label, font=font)
        radius = 4.25*SCALE if state == 'not_returned' else max(6.5 * SCALE, (box[2] - box[0]) / 2 + 2 * SCALE)
        if credit_box:
            require(contains_box(overlay_frame,[x-radius,y-radius,x+radius,y+radius]),
                    'marker overlaps embedded credits or image edge; supply wider imagery with marker clearance')
        pins.append((x, y, radius))
        marker_geometry.append(dict(index=index, center_px=[x, y], radius_px=radius, label=label,
                                    state=state, rank=rank, footprint_px=[x-radius,y-radius,x+radius,y+radius]))
        outline, stroke = marker_outline(state)
        draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color, outline=outline, width=stroke)
        draw.text((x, y), label, font=font, fill=ink, anchor='mm')
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
    return dict(file=path.name, bounds=extent, requested_bounds=requested_extent, plotted=len(pins), outside=len(lane['records'])-len(pins),
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
    return [('Ranks 1–3',RANK_COLORS[0],False),('Ranks 4–10',RANK_COLORS[1],False),
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
    base = lane['map'].get('basemap')
    expected_bounds = basemap_viewport(base,asset['requested_bounds'],width,geo_height) if base else asset['requested_bounds']
    require(asset['bounds'] == expected_bounds, 'expanded viewport bounds mismatch')
    projection = Projection(asset['bounds'], width=width, height=geo_height, pad=0 if base else 26*SCALE)
    frame = [round(v) for v in (projection.left,projection.top,projection.right,projection.bottom)]
    require(frame == asset['geographic_frame_px'], 'geographic frame mismatch')
    base = lane['map'].get('basemap')
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
    font = ImageFont.truetype(fonts['bold'],8*SCALE)
    measure = ImageDraw.Draw(Image.new('RGB',(1,1)))
    for marker in markers:
        row = expected[marker['index']]
        label = marker_label(row['state'],row['rank'])
        require(marker['label']==label and marker['state']==row['state'] and marker['rank']==row['rank'], 'marker rank/state mismatch')
        x,y = projection.point(row['lat'],row['lng'])
        require(max(abs(x-marker['center_px'][0]),abs(y-marker['center_px'][1])) < .001, 'marker coordinate mismatch')
        box = measure.textbbox((0,0),label,font=font)
        radius = 4.25*SCALE if row['state']=='not_returned' else max(6.5*SCALE,(box[2]-box[0])/2+2*SCALE)
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
    shade_bands(overlay, rings)
    for ring in rings:
        points = [tuple(p) for p in ring['points_px']]
        mask_draw.polygon(points,fill=255)
        mask_draw.line(points,fill=255,width=2)
    expected_raster.paste(overlay,(0,0),overlay)
    unit = lane['map'].get('distance_unit','km')
    require(asset.get('distance_unit','km') == unit, 'map distance unit mismatch')
    labels = paint_band_labels(expected_raster,rings,fonts,safe if base else frame,unit)
    require(labels == asset['band_labels'], 'band label geometry mismatch')
    for label in labels:
        require(contains_box(safe,label['footprint_px']), 'band label clips geographic area')
        mask_draw.rectangle(label['footprint_px'],fill=255)
    paint = ImageDraw.Draw(expected_raster)
    for marker in markers:
        rank,state = marker['rank'],marker['state']
        color, ink = marker_style(state, rank)
        outline, stroke = marker_outline(state)
        paint.ellipse(marker['footprint_px'],fill=color,outline=outline,width=stroke)
        paint.text(tuple(marker['center_px']),marker['label'],font=font,fill=ink,anchor='mm')
        mask_draw.ellipse(marker['footprint_px'],fill=255)
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
    from reportlab.platypus import BaseDocTemplate, Flowable, Frame, Image, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer
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

    class MapLegend(Flowable):
        def __init__(self, lane, asset):
            super().__init__()
            self.lane, self.asset = lane, asset
            self.width = COLUMN
            self.excluded = any(lane['metrics']['states'].get(k,0) for k in ('error','empty','unmeasured'))
            self.height = 30 if self.excluded else 18

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
        'heading': ParagraphStyle('heading', fontName='ReportBold', fontSize=13, leading=17, textColor=HexColor(INK), spaceBefore=10, spaceAfter=8, keepWithNext=True),
        'body': ParagraphStyle('body', fontName='ReportBody', fontSize=11, leading=16, textColor=HexColor(INK), spaceAfter=10),
        'finding': ParagraphStyle('finding', fontName='ReportBody', fontSize=10.5, leading=14, textColor=HexColor(INK), spaceAfter=8),
        'small': ParagraphStyle('small', fontName='ReportBody', fontSize=8.5, leading=12, textColor=HexColor(MUTED), spaceAfter=10),
    }
    ink_fonts, ink_metrics = {}, {}

    def guarded_style(value, style):
        # Paragraph wraps by advance widths, which can omit negative left
        # bearings (for example a line beginning with j) and right ink overhang.
        # Measure the actual selected TTF at high precision; keep glyph ink
        # within the existing 48pt column, without reducing type or QA bounds.
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
            # Balance a two-line title only when both lines fit; never reduce type.
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

    def label(canv, x, y, value, right=False):
        # Uppercase tracked mono labels (light theme); plain labels otherwise.
        if THEME != 'light':
            (canv.drawRightString if right else canv.drawString)(x, y, value)
            return
        spacing = .8
        width = pdfmetrics.stringWidth(value, 'ReportMono', 8.5) + spacing*(len(value)-1)
        canv.saveState()  # character spacing is PDF text state; keep it out of body copy
        text = canv.beginText(x-width if right else x, y)
        text.setFont('ReportMono', 8.5)
        text.setCharSpace(spacing)
        text.textOut(value)
        text.setCharSpace(0)
        canv.drawText(text)
        canv.restoreState()

    def header_bar(canv, y, height):
        steps = 120
        width = (PAGE_W-2*MARGIN)/steps
        stops = [HexColor(c) for c in HEADER_COLORS]
        for i in range(steps):
            t = i/(steps-1)*(len(stops)-1)
            a, b = stops[int(t)], stops[min(int(t)+1, len(stops)-1)]
            f = t-int(t)
            canv.setFillColorRGB(a.red+(b.red-a.red)*f, a.green+(b.green-a.green)*f, a.blue+(b.blue-a.blue)*f)
            canv.rect(MARGIN+i*width, y, width+.3, height, fill=1, stroke=0)

    def page(canv, doc):
        canv.setFillColor(HexColor(BG))
        canv.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        if THEME == 'light':
            header_bar(canv, 739, 3)
        canv.setStrokeColor(HexColor(LINE))
        canv.line(MARGIN, 747 if THEME != 'light' else 735, PAGE_W-MARGIN, 747 if THEME != 'light' else 735)
        canv.line(MARGIN, 43, PAGE_W-MARGIN, 43)
        canv.setFillColor(HexColor(MUTED))
        canv.setFont('ReportBody', 8.5)
        label(canv, MARGIN, 752 if THEME == 'light' else 761, 'legends-geogrid / local search observations')
        label(canv, MARGIN, 28, 'SYNTHETIC DEMONSTRATION' if model['synthetic'] else 'SUPPLIED OBSERVATIONAL EVIDENCE')
        label(canv, PAGE_W-MARGIN, 28, str(doc.page), right=True)

    doc = BaseDocTemplate(str(output / 'report.pdf'), pagesize=(PAGE_W, PAGE_H),
                          title=display_text(model['business']['name'])+' | legends-geogrid report', author='legends-geogrid',
                          leftMargin=MARGIN, rightMargin=MARGIN, topMargin=65, bottomMargin=58,
                          allowSplitting=1)
    doc.addPageTemplates(PageTemplate(id='dark', frames=[Frame(MARGIN, 58, COLUMN, 669, leftPadding=0,
                          rightPadding=0, topPadding=0, bottomPadding=0)], onPage=page))
    story = [p(model['business']['name'], 'title'), p(model['business']['location'], 'small')]
    if model['synthetic']:
        story += [p('Synthetic demonstration — no real business findings', 'heading')]
    story += [p(model['evidence_disclosure'], 'small'), p('Working assessment', 'heading'),
              p('Hypothesis, not an established finding: '+model['thesis']), p('Objectives', 'heading')]
    story += [p(item) for item in model['objectives']]
    story += [p('Evidence boundaries', 'heading'), p(LIMITS)]
    story += [p(center_disclosure(model)+f" Coordinates: {model['business']['lat']:.7f}, {model['business']['lng']:.7f}. "
                f"{len(model['lanes'])} independent query lanes; denominators remain separate.", 'small')]
    for i, lane in enumerate(model['lanes']):
        asset = assets[i]['main']
        story += [PageBreak(), p(lane['label'], 'title'), p('Query: '+lane['query'], 'small')]
        block = [TrackedImage(str(output / asset['file']), width=MAP_W, height=asset['height_pt']), Spacer(1, 9),
                 MapLegend(lane,asset), p(finding(lane),'finding'), p(brief_caption(asset), 'small')]
        # Keep the map/summary together when it fits. Oversized supplied credits
        # continue through Platypus at the same font floor rather than clipping.
        story += [KeepTogether(block)]
        if lane['narrative']:
            story += [p('Working assessment', 'heading'), p('Hypothesis, not an established finding: '+lane['narrative'])]
    story += [PageBreak(), p('Recommended next steps', 'title')]
    if model['next_actions']:
        story += [p(t) for t in model['next_actions']]
    else:
        story += [p('No business recommendations were supplied. Observations alone do not establish causes, demand, or likely returns.')]
    if model.get('verification_notes'):
        story += [p('How the findings were checked', 'heading')] + [p(t) for t in model['verification_notes']]
    story += [p('What remains unverified', 'heading')]
    for lane in model['lanes']:
        story += [p(lane['label'], 'heading')]
        story += [p(t) for t in lane['missing_evidence']] or [p('No missing timestamp, depth, count, or cutoff sequence detected. Causal evidence and market representativeness remain unestablished.')]
    if model['missing_evidence']:
        story += [p('Additional open questions', 'heading')] + [p(t) for t in model['missing_evidence']]
    story += [PageBreak(), p('Evidence & denominator appendix', 'title')]
    for lane_index, lane in enumerate(model['lanes']):
        m = lane['metrics']
        lane_block = [p(lane['label'], 'heading'), p(finding(lane)),
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
        # Move a complete lane to the next page when needed. An exceptionally
        # long block may still split at full readable type through Platypus.
        story += [KeepTogether(lane_block)]
    for i, lane in enumerate(model['lanes']):
        if 'full' in assets[i]:
            asset = assets[i]['full']
            story += [PageBreak(), p('Full extent: '+lane['label'], 'title'), p('All supplied origins, including those outside the main view.', 'small'),
                      KeepTogether([TrackedImage(str(output / asset['file']), width=MAP_W, height=asset['height_pt']), Spacer(1, 9),
                                    MapLegend(lane,asset), p(map_caption(lane, asset), 'small')])]
    doc.build(story)
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
    def p(s):
        return '<p>'+escape(s).replace('\n', '<br>')+'</p>'
    def h(s, level=2):
        return f'<h{level}>'+escape(s)+f'</h{level}>'
    def legend(lane):
        items = ['<span style="display:inline-block;margin-right:20px"><span aria-hidden="true" '
                 'style="display:inline-block;width:8px;height:8px;box-sizing:border-box;border-radius:50%;margin-right:6px;'+
                 ('border:1px solid '+color if hollow else 'background:'+color)+'"></span>'
                 +label+'</span>' for label,color,hollow in legend_items()]
        items += ['<span>Rings: '+lane['map'].get('distance_unit','km')+'</span>']
        if any(lane['metrics']['states'].get(k,0) for k in ('error','empty','unmeasured')):
            items += ['<br>E: error · Ø: empty · U: unmeasured (excluded from measured denominator)']
        return '<p style="font-size:13px;color:'+MUTED+'">'+''.join(items)+'</p>'
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">',
             '<title>'+escape(model['business']['name'])+' | legends-geogrid</title>',
             '<style>'+('.brand-strip{height:6px;background:linear-gradient(115deg,'+','.join(HEADER_COLORS)+')}.mono{font-family:"JetBrains Mono",ui-monospace,monospace;letter-spacing:.09em;font-size:12px;color:'+MUTED+'}h1,h2,h3{font-weight:600;letter-spacing:-.02em}' if THEME == 'light' else '')+'body{margin:0;background:'+BG+';color:'+INK+';font:16px/1.6 '+('Inter,' if THEME == 'light' else '')+'system-ui,sans-serif}main{max-width:860px;margin:auto;padding:40px 24px}h1{font-size:36px;line-height:1.2}h2{color:'+ACCENT+'}p,h1,h2,td{overflow-wrap:anywhere}section{border-top:1px solid '+LINE+';padding:24px 0}img{width:100%;height:auto}table{border-collapse:collapse;font-size:13px;width:100%}th,td{padding:7px;text-align:left;border-bottom:1px solid '+LINE+'}.scroll{overflow:auto}small{color:'+MUTED+'}a{color:'+ACCENT+'}</style><main>',
             *(['<div class="brand-strip"></div>'] if THEME == 'light' else []),
             '<p class="mono">legends-geogrid / local search observations</p>',
             h(model['business']['name'],1), p(model['business']['location'])]
    if model['synthetic']:
        parts += [h('Synthetic demonstration — no real business findings')]
    parts += [p(model['evidence_disclosure']), h('Working assessment'),
              p('Hypothesis, not an established finding: '+model['thesis']), h('Objectives')]
    parts += [p(x) for x in model['objectives']]
    parts += [h('Evidence boundaries'), p(LIMITS), p(center_disclosure(model)+
              f" Coordinates: {model['business']['lat']:.7f}, {model['business']['lng']:.7f}.")]
    for i, lane in enumerate(model['lanes']):
        parts += ['<section>', h(lane['label']), p('Query: '+lane['query'])]
        for kind in ('main', 'full'):
            if kind not in assets[i]:
                continue
            asset = assets[i][kind]
            if kind == 'full':
                parts += [h('Full extent appendix',3)]
            parts += [f'<img src="{asset["file"]}" alt="{escape(lane["label"], quote=True)}: {asset["plotted"]} exact-coordinate observations">',
                      legend(lane), p(map_caption(lane, asset))]
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
    parts += [h('Recommended next steps')]+[p(x) for x in model['next_actions'] or ['No business recommendations supplied.']]
    if model.get('verification_notes'):
        parts += [h('How the findings were checked')]+[p(x) for x in model['verification_notes']]
    parts += [h('What remains unverified')]+[p(x) for x in model['missing_evidence']]
    parts += ['<p><a href="report.pdf">PDF report</a> · <a href="report-model.json">Normalized evidence and metrics</a> · <a href="report-qa.json">QA receipt</a></p></main></html>']
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


def build(config, output_dir, require_pdf_qa=False, proof=False):
    model = load_config(config)
    apply_theme(model.get('theme', DEFAULT_THEME))
    output = Path(output_dir).resolve()
    require(not output.exists() or not any(output.iterdir()), 'output directory must be new or empty; existing files are preserved')
    fonts = register_fonts(model)
    output.mkdir(parents=True, exist_ok=True)
    # Complete and validate in a temporary sibling; invalid input leaves no
    # partial published report. Move only verified, newly generated artifacts.
    with tempfile.TemporaryDirectory(prefix='.geogrid-report-', dir=output.parent) as folder:
        stage = Path(folder)
        assets = []
        for i, lane in enumerate(model['lanes'], 1):
            asset = {'main':map_image(lane, model['business'], stage/f'map-{i:03d}.png', fonts)}
            if lane['needs_appendix']:
                asset['full'] = map_image(lane, model['business'], stage/f'map-{i:03d}-full.png', fonts, full=True)
            for view in asset.values():
                view.update(center_kind=model['center_kind'], center_label=model['center_label'])
            assets.append(asset)
        map_validation = [dict(query_id=lane['query_id'], **{
            kind:map_qa(lane,model['business'],asset,stage/asset['file'],fonts)
            for kind,asset in group.items()}) for lane,group in zip(model['lanes'],assets)]
        layout = render_pdf(model, assets, stage)
        render_html(model, assets, stage)
        # Strip operational input paths, retaining attribution and georeferencing.
        public_model = json.loads(json.dumps(model))
        public_model.pop('fonts', None)
        for lane in public_model['lanes']:
            lane['map'].get('basemap', {}).pop('path', None)
        write_json(stage/'report-model.json', public_model)
        validation = pdf_qa(stage/'report.pdf', proof, require_pdf_qa)
        require(validation['status'] != 'failed', f"PDF QA failed: {validation.get('issues')}")
        receipt = dict(status='passed' if validation['status']=='passed' else 'layout-passed-pdf-qa-skipped',
                       network_calls=0, pdf=validation, map_validation=map_validation, layout_boxes=layout, maps=assets,
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
    parser.add_argument('--proof', action='store_true', help='render PDF pages to local proof PNGs')
    args = parser.parse_args(argv)
    try:
        receipt = build(args.config, args.output_dir, args.require_pdf_qa, args.proof)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f'Report failed: {exc}', file=sys.stderr)
        return 2
    print(json.dumps({'status':receipt['status'], 'output_dir':str(args.output_dir)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
