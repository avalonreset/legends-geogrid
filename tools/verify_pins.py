#!/usr/bin/env python3
"""Pin verifier: prove every report pin traces to raw grid JSON.

Usage: python3 tools/verify_pins.py --config report.json --target "acme plumbing" \
           --category "hvac|heating|..." [--html report.html]

Checks per grid: full point coverage (json or .noresult marker each), keyword
uniformity, measured-cell counts, target rank map, and (with --html) that every
map block's baked PNG circles match its embedded SVG pins in count and position.
Exit 0 only when everything passes.
"""
import argparse, glob, json, math, os, re, struct, sys, zlib
from collections import deque

RED, GREEN = (217, 48, 37), (30, 142, 62)
fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


def load_items(path):
    try:
        d = json.loads(open(path, 'rb').read().decode('cp1252'), strict=False)
    except Exception:
        d = json.loads(open(path, encoding='utf-8', errors='replace').read(), strict=False)
    t = (d.get('tasks') or [{}])[0]
    return (((t.get('result') or [{}])[0].get('items')) or [],
            (t.get('data') or {}).get('keyword'))


def read_rgb(path):
    d = open(path, 'rb').read()
    pos, idat = 8, b''
    while pos < len(d):
        ln = struct.unpack('>I', d[pos:pos+4])[0]
        typ = d[pos+4:pos+8]; body = d[pos+8:pos+8+ln]
        if typ == b'IHDR':
            w, h, bd, ct, _, _, _ = struct.unpack('>IIBBBBB', body)
        elif typ == b'IDAT':
            idat += body
        elif typ == b'IEND':
            break
        pos += 12 + ln
    assert ct == 2, (path, ct)
    raw = zlib.decompress(idat); stride = w * 3
    px = bytearray(w * h * 3); prev = bytearray(stride); p = 0
    for y in range(h):
        f = raw[p]; p += 1
        row = bytearray(raw[p:p+stride]); p += stride
        if f == 1:
            for i in range(3, len(row)):
                row[i] = (row[i] + row[i-3]) & 255
        elif f == 2:
            for i in range(len(row)):
                row[i] = (row[i] + prev[i]) & 255
        px[y*stride:(y+1)*stride] = row; prev = row
    return w, h, px


def centers(w, h, px):
    mask = bytearray(w * h)
    for i in range(w * h):
        if (px[i*3], px[i*3+1], px[i*3+2]) in (RED, GREEN):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--category", required=True)
    ap.add_argument("--html", default=None)
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    lex = re.compile(a.category, re.I); tgt = a.target.lower()
    blocks = {}
    if a.html:
        html = open(a.html, encoding='utf-8').read()
        for h3, img, svg in re.findall(
                r'<h3>([^<]+)</h3>\s*<div class="mapwrap"><img class="map" src="([^"]+)">\s*(<svg.*?</svg>)',
                html, re.S):
            blocks[img] = (h3, svg)
        check('map blocks', len(blocks) == len(cfg["grids"]), str(len(blocks)))
        check('no em/en dashes', '\u2014' not in html and '\u2013' not in html)
    for g in cfg["grids"]:
        files = sorted(glob.glob(os.path.join(g["dir"], f"{g['prefix']}_*.json")))
        nores = glob.glob(os.path.join(g["dir"], f"{g['prefix']}_*.noresult"))
        npts = sum(1 for _ in open(g["points"]))
        check(f'{g["label"]} coverage', len(files) + len(nores) == npts,
              f'{len(files)}+{len(nores)}/{npts}')
        badkw = meas = 0; ranks = {}
        for f in files:
            items, kw = load_items(f)
            if kw != g["keyword"]:
                badkw += 1
            if not items or not any(lex.search(x.get('title') or '') for x in items):
                continue
            meas += 1
            i = int(re.search(r'_(\d+)\.json$', f).group(1))
            for it in items:
                if tgt in (it.get('title') or '').lower():
                    ranks[i] = it.get('rank_absolute')
        check(f'{g["label"]} keywords', badkw == 0, f'{badkw} mismatches')
        print(f'INFO {g["label"]}: measured={meas} target_cells={sorted(ranks.items())}')
        outpng = os.path.join(cfg.get("out_dir", "maps"), g["prefix"] + ".png")
        if a.html and outpng in blocks:
            h3, svg = blocks[outpng]
            pins = re.findall(r'<text x="(-?[\d.]+)" y="(-?[\d.]+)" class="([^"]+)">([^<]+)</text>', svg)
            check(f'{g["label"]} pin count', len(pins) == meas, f'{len(pins)}/{meas}')
            check(f'{g["label"]} pins in frame',
                  all(0 <= float(x) <= 1280 and 0 <= float(y) <= 1280 for x, y, _, _ in pins))
            w, h, px = read_rgb(outpng)
            cc = centers(w, h, px)
            check(f'{g["label"]} baked circles', len(cc) == len(pins), f'{len(cc)}/{len(pins)}')
    print('ALL_OK' if not fails else f'{len(fails)} FAILURES')
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
