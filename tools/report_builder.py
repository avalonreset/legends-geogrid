#!/usr/bin/env python3
"""Generic multi-intent GeoGrid report builder.

Config JSON:
  {"business": "Acme Plumbing", "subtitle": "geo visibility report : austin metro",
   "center": [38.6446, -121.2658], "base_png": "assets/base.png",
   "grids": [{"label": "furnace repair", "keyword": "furnace repair sacramento",
               "dir": "data/furnace", "prefix": "repair",
               "points": "grid17_points.tsv", "demand": "390 / low"}],
   "out_html": "report.html", "out_dir": "maps"}

Each grid dir holds one DataForSEO Maps JSON per point named <prefix>_<idx>.json
plus <prefix>_<idx>.noresult markers for no-pack cells. Points file rows:
"<idx> <lat> <lng>". A cell is measured iff at least one result title matches
--category. Pins: rank number where the target ranks, NR where measured but
absent, blank where unmeasured. Run tools/verify_pins.py on the output before
publishing; see docs/keyword-formula.md for how keywords are chosen.

Paths retain their legacy working-directory resolution. Output files must not
exist; choose fresh out_html/out_dir paths for another report. Grid prefixes are
filenames, never paths. Set attribution_bottom_px (globally or on a grid) to the
number of protected bottom image rows, e.g. 44; full pin rings must stay above
them. Optional attribution text is escaped and printed with the map. Pillow
(requirements-report.txt) decodes PNGs, including filters, palettes and alpha;
transparent pixels are composited on white. Animated/16-bit PNGs are rejected.
"""
import argparse, json, math, os, re, struct, sys, zlib
from contextlib import ExitStack
from html import escape
from types import SimpleNamespace
from pathlib import Path
from urllib.parse import quote
from local_heatmap_poc import extract_items, match_score, organic_maps_items, organic_rank, RANK_BASIS

GREEN, YELLOW, RED, WHITE, GOLD = (30, 142, 62), (249, 171, 0), (217, 48, 37), (255, 255, 255), (255, 210, 0)
PIN_RADIUS, RING_WIDTH = 18, 2
MERCATOR_LATITUDE = 85.0511287798066
REQUEST_FIELDS = ('keyword', 'location_coordinate', 'depth', 'device', 'language_code',
                  'se_domain', 'search_places', 'search_this_area')

CSS = """*{box-sizing:border-box}body{font-family:"Segoe UI",Arial,sans-serif;background:#000;color:#fff;font-size:12px;line-height:1.55;margin:0}.wrap{width:850px;margin:0 auto;padding:44px 52px}h1{font-size:36px;font-weight:800;margin:0}.sub{color:#666;font-size:13px}.rule{border:none;border-top:3px solid red;margin:14px 0 18px}.metricbar{display:table;width:100%;margin:16px 0;border-top:1px solid #666;border-bottom:1px solid #666}.metricbar .m{display:table-cell;text-align:center;padding:12px 4px}.metricbar .v{font-size:28px;font-weight:800}.red .v{color:red}.k{font-size:9px;color:#666}h2{font-size:18px;margin:30px 0 8px}h2 .n{color:red}h3{font-size:13px;margin:18px 0 6px}table.data{border-collapse:collapse;width:100%;margin:10px 0 16px;font-size:11px}table.data td,table.data th{border-bottom:1px solid #666;padding:5px 7px;text-align:left}td.r{color:red;font-weight:700}td.g{font-weight:700}img.map{width:100%;display:block;border:1px solid #666}.mapwrap{position:relative}.mapwrap svg{position:absolute;inset:0;width:100%;height:100%}.mapwrap text{fill:#fff;font-weight:700;font-size:14px;text-anchor:middle;dominant-baseline:central;font-family:inherit}.mapwrap text.rk1{font-size:20px}.foot{color:#666;font-size:9px;border-top:1px solid #666;padding-top:8px;margin-top:22px}.how{border:1px solid #666;padding:14px 16px;margin:14px 0}"""


def read_png_rgb(path):
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError('PNG reports require Pillow; install requirements-report.txt') from exc
    with Path(path).open('rb') as stream:
        header = stream.read(29)
    if header[:8] == b'\x89PNG\r\n\x1a\n' and len(header) > 24 and header[24] == 16:
        raise ValueError('Unsupported 16-bit PNG; convert to an 8-bit image explicitly')
    with Image.open(path) as image:
        if image.format != 'PNG' or image.is_animated:
            raise ValueError('Expected a non-animated PNG')
        if image.mode not in ('1', 'L', 'LA', 'P', 'RGB', 'RGBA'):
            raise ValueError('Unsupported PNG mode; use an 8-bit RGB, grayscale or palette image')
        image.verify()  # Validate chunk integrity as well as decoding pixels.
    with Image.open(path) as image:
        rgba = image.convert('RGBA')
        rgb = Image.alpha_composite(Image.new('RGBA', image.size, WHITE + (255,)), rgba).convert('RGB')
        return image.width, image.height, rgb.tobytes()


def png_bytes(w, h, rgb):
    if type(w) is not int or type(h) is not int or min(w, h) < 1 or len(rgb) != w * h * 3:
        raise ValueError('PNG dimensions do not match the RGB buffer')
    def chunk(t, b):
        return struct.pack('>I', len(b)) + t + b + struct.pack('>I', zlib.crc32(t+b))
    raw = b''.join(b'\x00' + rgb[y*w*3:(y+1)*w*3] for y in range(h))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def write_png(path, w, h, rgb):
    payload = png_bytes(w, h, rgb)
    with Path(path).open('xb') as stream:
        stream.write(payload)


def project(lat, lng, clat, clng, z, W, H):
    values = (lat, lng, clat, clng, W, H)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ValueError('Projection requires finite coordinates and dimensions')
    if (abs(lat) > MERCATOR_LATITUDE or abs(clat) > MERCATOR_LATITUDE or
            abs(lng) > 180 or abs(clng) > 180 or min(W, H) <= 0 or
            type(z) is not int or not 0 <= z <= 23):
        raise ValueError('Unsupported Web Mercator coordinates, dimensions or zoom')
    s = 256 * (2 ** z)
    delta_lng = (lng - clng + 180) % 360 - 180
    northing = lambda value: math.asinh(math.tan(math.radians(value)))
    return (W / 2 + s * delta_lng / 360,
            H / 2 - s * (northing(lat) - northing(clat)) / (2 * math.pi))


def attribution_rows(cfg, grid, height):
    value = grid.get('attribution_bottom_px', cfg.get('attribution_bottom_px', 0))
    if type(value) is not int or not 0 <= value < height:
        raise ValueError('attribution_bottom_px must be an integer from zero to image height minus one')
    return value


def marker_fits(x, y, width, height, protected_bottom=0):
    radius = PIN_RADIUS + RING_WIDTH
    return (math.isfinite(x) and math.isfinite(y) and radius <= x <= width - 1 - radius and
            radius <= y <= height - protected_bottom - 1 - radius)


def validate_prefix(value):
    if (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}', value)
            or '..' in value or value.endswith('.') or
            value.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                                          *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}):
        raise ValueError('Grid prefix must be a safe filename, not a path or reserved name')
    return value


def map_output_path(cfg, grid):
    root = Path(cfg.get('out_dir', 'maps')).resolve()
    path = root / (validate_prefix(grid['prefix']) + '.png')
    if path.resolve().parent != root or path.is_symlink():
        raise ValueError('Map output escapes its configured directory')
    return path


def asset_uri(image_path, html_path):
    try:
        relative = os.path.relpath(image_path, Path(html_path).resolve().parent)
    except ValueError as exc:
        raise ValueError('HTML and map output must support relative paths on the same drive') from exc
    return quote(Path(relative).as_posix(), safe='/')


def read_points(path):
    coords = {}
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        if not line.strip():
            continue
        ix, lat, lng = line.split()
        index = int(ix)
        if index < 0 or index in coords:
            raise ValueError('Point IDs must be unique nonnegative integers')
        coords[index] = (float(lat), float(lng))
    if not coords:
        raise ValueError('Points file is empty')
    return coords


def publish_outputs(artifacts):
    """Reserve all new files exclusively; never replace existing user output."""
    created = []
    try:
        with ExitStack() as stack:
            streams = []
            for path, data in artifacts:
                path.parent.mkdir(parents=True, exist_ok=True)
                stream = stack.enter_context(path.open('xb'))
                created.append((path, os.fstat(stream.fileno())))
                streams.append((stream, data))
            for stream, data in streams:
                stream.write(data)
    except Exception:
        # Remove only files this call just created, never a pre-existing target.
        for path, identity in created:
            if path.exists() and os.path.samestat(identity, path.stat()):
                path.unlink()
        raise


def circle(img, w, h, cx, cy, r, color, ring):
    for yy in range(int(cy-r-3), int(cy+r+4)):
        for xx in range(int(cx-r-3), int(cx+r+4)):
            if 0 <= xx < w and 0 <= yy < h:
                dd = math.hypot(xx-cx, yy-cy)
                if dd <= r:
                    img[(yy*w+xx)*3:(yy*w+xx)*3+3] = bytes(color)
                elif ring and dd <= r+2:
                    img[(yy*w+xx)*3:(yy*w+xx)*3+3] = bytes(ring)


def load_measurement(path):
    try:
        d = json.loads(Path(path).read_text(encoding='utf-8-sig'), strict=False)
    except UnicodeDecodeError:
        d = json.loads(Path(path).read_text(encoding='cp1252'), strict=False)
    task = (d.get('tasks') or [{}])[0]
    raw_items, error = extract_items(task)
    items = organic_maps_items(raw_items)
    data = task.get('data') or {}
    # Do not export arbitrary tags, callbacks, auth fields or nested metadata.
    public_data = {key: data[key] for key in REQUEST_FIELDS if key in data and
                   type(data[key]) in (str, int, float, bool) and
                   (not isinstance(data[key], float) or math.isfinite(data[key]))}
    settings = {key: public_data.get(key, 'not recorded') for key in REQUEST_FIELDS}
    settings['provider_request_data'] = public_data
    allowed_paths = (['v3', 'serp', 'google', 'maps', 'live', 'advanced'],
                     ['v3', 'serp', 'google', 'maps', 'task_get', 'advanced'])
    provider_path = task.get('path')
    settings['provider_path'] = provider_path if provider_path in allowed_paths else 'not recorded'
    settings['rank_basis'] = RANK_BASIS
    settings['returned_items_count'] = len(raw_items)
    settings['organic_items_count'] = len(items)
    return items, data.get('keyword'), settings, error


def load_items(path):
    items, keyword, _, _ = load_measurement(path)
    return items, keyword


def target_matches(item, target, target_cid='', target_place_id=''):
    if target_cid or target_place_id:
        return match_score(item, SimpleNamespace(target_name=target, target_domain='',
                           target_cid=target_cid, target_place_id=target_place_id)) == 1
    return bool(target and target.lower() in (item.get('title') or '').lower())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--target", required=True, help="business name fragment, e.g. 'acme plumbing'")
    ap.add_argument("--category", required=True, help="regex for in-category titles")
    ap.add_argument("--target-cid", default='')
    ap.add_argument("--target-place-id", default='')
    ap.add_argument("--zoom", type=int, default=12)
    a = ap.parse_args(argv)
    cfg = json.loads(Path(a.config).read_text(encoding='utf-8-sig'))
    lex = re.compile(a.category, re.I)
    tgt = a.target.lower()
    W, H, base = read_png_rgb(cfg["base_png"])
    clat, clng = cfg["center"]
    html_path = Path(cfg['out_html']).absolute()
    if html_path.is_symlink():
        raise ValueError('HTML output must not be a symlink')
    html_path = html_path.resolve()
    targets = [map_output_path(cfg, grid) for grid in cfg['grids']] + [html_path]
    if len(set(targets)) != len(targets):
        raise ValueError('Duplicate output paths; each grid needs a unique prefix')
    if any(path.exists() or path.is_symlink() for path in targets):
        raise ValueError('Output already exists; choose fresh out_html/out_dir paths (no overwrite)')
    # Validate even unmeasured coordinates and every destination before output.
    for grid, output in zip(cfg['grids'], targets):
        asset_uri(output, html_path)
        attribution_rows(cfg, grid, H)
        for lat, lng in read_points(grid['points']).values():
            project(lat, lng, clat, clng, a.zoom, W, H)
    blocks, rows, artifacts = [], [], []
    for g in cfg["grids"]:
        coords = read_points(g['points'])
        protected_bottom = attribution_rows(cfg, g, H)
        img = bytearray(base); svg = []; measured = 0; held = []
        evidence = []; counts = dict(missing=0, provider_error=0, empty=0, no_organic_results=0, category_excluded=0, not_returned=0, found=0)
        for i, (lat, lng) in sorted(coords.items()):
            p = os.path.join(g["dir"], f"{g['prefix']}_{i}.json")
            if not (os.path.exists(p) and os.path.getsize(p) > 0):
                counts['missing'] += 1
                continue
            items, kw, settings, error = load_measurement(p)
            evidence.append({'point': i, 'measurement_settings': settings, 'returned_items': len(items),
                             'error': 'Provider task failed' if error else None})
            if error:
                counts['provider_error'] += 1
                continue
            if kw != g['keyword']:
                raise ValueError(f"Keyword mismatch at {g['prefix']} point {i}")
            if not items:
                counts['no_organic_results' if settings['returned_items_count'] else 'empty'] += 1
                continue
            if not any(lex.search(t.get('title') or '') for t in items):
                counts['category_excluded'] += 1
                continue
            rk = -1
            for it in items:
                if target_matches(it, tgt, a.target_cid, a.target_place_id):
                    rk = organic_rank(it) or -1
                    break
            counts['found' if rk > 0 else 'not_returned'] += 1
            px, py = project(lat, lng, clat, clng, a.zoom, W, H)
            if not marker_fits(px, py, W, H, protected_bottom):
                raise ValueError(f"Clipped marker or attribution collision at {g['prefix']} point {i}; choose a wider basemap")
            col = RED if not (rk and rk > 0) else (GREEN if rk <= 3 else (YELLOW if rk <= 10 else RED))
            circle(img, W, H, px, py, PIN_RADIUS, col, GOLD if rk == 1 else WHITE)
            svg.append('  <text x="%.1f" y="%.1f" class="%s">%s</text>'
                       % (px, py, 'rk1' if rk == 1 else ('pin' if rk and rk > 0 else 'abs'),
                          str(rk) if rk and rk > 0 else 'NR'))
            measured += 1
            if rk == 1:
                held.append(i)
        outpng = map_output_path(cfg, g)
        artifacts.append((outpng, png_bytes(W, H, bytes(img))))
        svgdoc = '<svg viewBox="0 0 %d %d">\n%s\n</svg>' % (W, H, '\n'.join(svg))
        blocks.append('<h3>%s : %s cells measured, %s held</h3>\n<div class="mapwrap">'
                      '<img class="map" src="%s">\n%s\n</div>' %
                      (escape(str(g['label'])), measured, len(held), escape(asset_uri(outpng, html_path), quote=True), svgdoc))
        if g.get('attribution', cfg.get('attribution')):
            blocks.append('<p class="attribution">%s</p>' % escape(str(g.get('attribution', cfg.get('attribution')))))
        blocks.append('<p>Planned points: %d. States: %s. Category-filtered pins are a subset, not a market denominator.</p>'
                      '<details><summary>Measurement settings and point evidence</summary><pre>%s</pre></details>' %
                      (len(coords), escape(json.dumps(counts, sort_keys=True)), escape(json.dumps(evidence, indent=2))))
        rows.append('<tr><td>%s</td><td>%d</td><td class="g">%d</td><td>%s</td></tr>'
                    % (escape(str(g['label'])), measured, len(held), escape(str(g.get('demand', 'not pulled yet')))))
        print(f'{g["label"]}: measured={measured} held={held}')
    html = ("""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>%s : geo visibility report</title>"""
            """<style>%s</style></head><body><div class="wrap"><h1>%s</h1><div class="sub">%s</div>"""
            """<hr class="rule"><h2><span class="n">01</span> how to read this map</h2><div class="how">"""
            """<p><b>what we did.</b> we stood a customer at grid points over the service area and typed the """
            """category keyword into google maps, exactly as a new customer would, recording the top results.</p>"""
            """<p><b>what the pins mean.</b> a number is an organic Maps group rank; paid placements are excluded. NR means the target had no organic rank returned """
            """in that viewport; it does not establish a rank beyond depth. Blank points were missing, failed, """
            """empty, or excluded by the category filter. None of these states establishes no market.</p></div>"""
            """<h2><span class="n">02</span> the battles</h2><p>%s</p>%s"""
            """<h2><span class="n">03</span> verdict</h2><table class="data">"""
            """<tr><th>battle</th><th>cells</th><th>held</th><th>demand</th></tr>%s</table>"""
            """<div class="foot">keywords chosen per docs/keyword-formula.md. map data copyright google. """
            """base map attribution per provider terms.</div></div></body></html>""")
    intro = ("same center, one grid per buyer intent. NR means not returned under the recorded measurement settings. "
             "a pin appears only where google showed at least one in-category business.")
    intro += ' Matching: ' + escape(json.dumps({'target': a.target, 'target_cid': a.target_cid, 'target_place_id': a.target_place_id,
                                               'policy': 'all_supplied_exact_no_fallback' if a.target_cid or a.target_place_id else 'name_fragment'}))
    document = html % (escape(str(cfg['business'])), CSS, escape(str(cfg['business']).lower()),
                       escape(str(cfg.get('subtitle', 'geo visibility report'))),
                       intro, '\n'.join(blocks), '\n'.join(rows))
    artifacts.append((html_path, document.encode('utf-8')))
    publish_outputs(artifacts)
    print('wrote', cfg["out_html"])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
        print(f'Report refused: {exc}', file=sys.stderr)
        sys.exit(2)
