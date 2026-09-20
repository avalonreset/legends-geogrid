#!/usr/bin/env python3
"""Pin verifier: prove every report pin traces to raw grid JSON.

Usage: python3 tools/verify_pins.py --config report.json --target "acme plumbing" \
           --category "hvac|heating|..." [--html report.html]

Checks per grid: full point coverage (json or .noresult marker each), keyword
uniformity, measured-cell counts, target rank map, and (with --html) that every
map block's baked PNG circles match its embedded SVG pins in count and position.
Exit 0 only when everything passes.
"""
import argparse, json, math, re, sys
from collections import deque
from html.parser import HTMLParser
from pathlib import Path, PureWindowsPath
from urllib.parse import unquote, urlsplit
from report_builder import (project, read_png_rgb, read_points, map_output_path,
                            attribution_rows, marker_fits, asset_uri)
from local_heatmap_poc import extract_items, organic_maps_items, organic_rank

RED, GREEN, YELLOW = (217, 48, 37), (30, 142, 62), (249, 171, 0)
fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


def load_items(path):
    try:
        d = json.loads(Path(path).read_text(encoding='utf-8-sig'), strict=False)
    except UnicodeDecodeError:
        d = json.loads(Path(path).read_text(encoding='cp1252'), strict=False)
    t = (d.get('tasks') or [{}])[0]
    items, error = extract_items(t)
    check(f'{Path(path).name} provider status', error is None, error or '')
    return organic_maps_items(items), (t.get('data') or {}).get('keyword')


def read_rgb(path):
    return read_png_rgb(path)


class MapBlocks(HTMLParser):
    """Parse entity-escaped paths/labels without letting missing blocks bypass QA."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.current = None
        self.div_depth = 0
        self.text_pin = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'div':
            if self.current is not None:
                self.div_depth += 1
            elif 'mapwrap' in attrs.get('class', '').split():
                self.current = {'images': [], 'views': [], 'pins': []}
                self.div_depth = 1
        if self.current is None:
            return
        if tag == 'img':
            self.current['images'].append(attrs.get('src', ''))
        elif tag == 'svg':
            self.current['views'].append(attrs.get('viewbox', ''))
        elif tag == 'text':
            self.text_pin = {'x': attrs.get('x', ''), 'y': attrs.get('y', ''),
                             'class': attrs.get('class', ''), 'label': ''}

    def handle_data(self, data):
        if self.text_pin is not None:
            self.text_pin['label'] += data

    def handle_endtag(self, tag):
        if tag == 'text' and self.text_pin is not None:
            self.current['pins'].append(self.text_pin)
            self.text_pin = None
        if tag == 'div' and self.current is not None:
            self.div_depth -= 1
            if not self.div_depth:
                self.blocks.append(self.current)
                self.current = None


def referenced_image(html_path, value):
    url = urlsplit(value)
    decoded = unquote(url.path)
    if (url.scheme or url.netloc or url.query or url.fragment or '\\' in decoded or
            Path(decoded).is_absolute() or PureWindowsPath(decoded).drive):
        raise ValueError('Report image references must be portable relative URLs')
    return (html_path.parent / decoded).resolve()


def expected_pixels(base, width, height, pins):
    """Independent raster oracle: reconstruct colored disks/rings from raw ranks."""
    image = bytearray(base)
    for x, y, rank in pins:
        color = RED if rank is None or rank > 10 else GREEN if rank <= 3 else YELLOW
        ring = (255, 210, 0) if rank == 1 else (255, 255, 255)
        for py in range(max(0, math.floor(y-20)), min(height, math.ceil(y+20)+1)):
            for px in range(max(0, math.floor(x-20)), min(width, math.ceil(x+20)+1)):
                distance_squared = (px-x)**2 + (py-y)**2
                if distance_squared <= 400:
                    offset = (py * width + px) * 3
                    image[offset:offset+3] = bytes(color if distance_squared <= 324 else ring)
    return bytes(image)


def centers(w, h, px):
    mask = bytearray(w * h)
    for i in range(w * h):
        if (px[i*3], px[i*3+1], px[i*3+2]) in (RED, GREEN, YELLOW):
            mask[i] = 1
    seen = bytearray(w * h); out = []
    for s in range(w * h):
        if not mask[s] or seen[s]:
            continue
        q = deque([s]); seen[s] = 1; xs = []; ys = []
        while q:
            c = q.popleft(); cx, cy = c % w, c // w
            xs.append(cx); ys.append(cy)
            for nx, ny in ((cx-1, cy), (cx+1, cy), (cx, cy-1), (cx, cy+1)):
                if 0 <= nx < w and 0 <= ny < h:
                    n = ny * w + nx
                    if mask[n] and not seen[n]:
                        seen[n] = 1; q.append(n)
        if len(xs) > 200:
            out.append((sum(xs)/len(xs), sum(ys)/len(ys)))
    return out


def main(argv=None):
    fails.clear()
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--category", required=True)
    ap.add_argument("--target-cid", default='')
    ap.add_argument("--target-place-id", default='')
    ap.add_argument("--zoom", type=int, default=12, help="Base-map projection zoom, matching report_builder")
    ap.add_argument("--html", default=None)
    a = ap.parse_args(argv)
    cfg = json.loads(Path(a.config).read_text(encoding='utf-8-sig'))
    lex = re.compile(a.category, re.I); tgt = a.target.lower()
    W, H, base = read_rgb(cfg['base_png'])
    expected_paths = [map_output_path(cfg, grid) for grid in cfg['grids']]
    check('unique map outputs', len(set(expected_paths)) == len(expected_paths))
    blocks = {}
    if a.html:
        html_path = Path(a.html).resolve()
        parser = MapBlocks()
        parser.feed(html_path.read_text(encoding='utf-8'))
        parser.close()
        check('map blocks', len(parser.blocks) == len(cfg['grids']) and parser.current is None,
              str(len(parser.blocks)))
        for block in parser.blocks:
            if len(block['images']) != 1 or len(block['views']) != 1:
                check('map image and SVG', False, 'exactly one of each required')
                continue
            path = referenced_image(html_path, block['images'][0])
            check('unique HTML image', path not in blocks)
            blocks[path] = block
            check('portable image path', block['images'][0] == asset_uri(path, html_path))
        check('configured map blocks', set(blocks) == set(expected_paths))
    else:
        print('INFO No --html supplied: checking raw evidence and geometry only, not rendered output.')
    for g in cfg["grids"]:
        outpng = map_output_path(cfg, g)
        coords = read_points(g['points'])
        protected = attribution_rows(cfg, g, H)
        file_ids = []
        files = {}
        for path in Path(g['dir']).glob(f"{g['prefix']}_*"):
            match = re.fullmatch(re.escape(g['prefix']) + r'_(\d+)\.(json|noresult)', path.name)
            if match:
                index = int(match[1])
                file_ids.append(index)
                if match[2] == 'json':
                    files[index] = path
        check(f'{g["label"]} coverage', set(file_ids) == set(coords) and len(file_ids) == len(coords),
              'exactly one JSON or noresult marker per planned point')
        badkw = 0; ranks = {}; measured_points = []; projected = {}
        for index, (lat, lng) in coords.items():
            projected[index] = project(lat, lng, *cfg['center'], a.zoom, W, H)
        for i, f in sorted(files.items()):
            items, kw = load_items(f)
            if kw != g["keyword"]:
                badkw += 1
            if i not in coords:
                continue
            for it in items:
                exact = [(str(it.get(key) or '') == value) for key, value in
                         (('cid', a.target_cid), ('place_id', a.target_place_id)) if value]
                if (all(exact) if exact else bool(tgt and tgt in (it.get('title') or '').lower())):
                    rank = organic_rank(it)
                    check(f'{g["label"]} point {i} target rank', rank is not None,
                          'Matched target requires a positive organic rank, never an NR label')
                    ranks[i] = rank
                    break
            if not items or not any(lex.search(x.get('title') or '') for x in items):
                continue
            measured_points.append(i)
        check(f'{g["label"]} keywords', badkw == 0, f'{badkw} mismatches')
        print(f'INFO {g["label"]}: measured={len(measured_points)} target_cells={sorted(ranks.items())}')
        expected_pins = [(*projected[i], ranks.get(i)) for i in measured_points]
        check(f'{g["label"]} full marker bounds',
              all(marker_fits(x, y, W, H, protected) for x, y, rank in expected_pins),
              f'{W}x{H}, protected bottom {protected}px')
        if a.html and outpng in blocks:
            block = blocks[outpng]
            pins = block['pins']
            check(f'{g["label"]} pin count', len(pins) == len(measured_points))
            w, h, px = read_rgb(outpng)
            check(f'{g["label"]} image dimensions', (w, h) == (W, H))
            check(f'{g["label"]} SVG geometry', [float(v) for v in block['views'][0].split()] == [0, 0, W, H])
            check(f'{g["label"]} pins in frame',
                  all(marker_fits(float(p['x']), float(p['y']), w, h, protected) for p in pins))
            expected = sorted((round(x, 1), round(y, 1), str(rank) if rank else 'NR') for x, y, rank in expected_pins)
            actual = sorted((float(p['x']), float(p['y']), p['label']) for p in pins)
            check(f'{g["label"]} pin ranks and coordinates', actual == expected,
                  'SVG labels and positions traced to raw items')
            check(f'{g["label"]} baked circles', (w, h) == (W, H) and
                  px == expected_pixels(base, W, H, expected_pins), 'pixels traced to raw ranks and original basemap')
            if protected:
                check(f'{g["label"]} attribution preserved', (w, h) == (W, H) and
                      px[(H-protected)*W*3:] == base[(H-protected)*W*3:])
    print('ALL_OK' if not fails else f'{len(fails)} FAILURES')
    return 1 if fails else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
        print(f'FAIL verifier: {exc}', file=sys.stderr)
        sys.exit(1)
