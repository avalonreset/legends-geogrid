#!/usr/bin/env python3
"""Generic multi-intent GeoGrid report builder.

Config JSON:
  {"business": "Acme Plumbing", "subtitle": "geo visibility report : austin metro",
   "center": [38.6446, -121.2658], "base_png": "assets/base.png",
   "grids": [{"label": "furnace repair", "keyword": "furnace repair sacramento",
               "dir": "data/furnace", "prefix": "alpha_FUR",
               "points": "grid17_points.tsv", "demand": "390 / low"}],
   "out_html": "report.html", "out_dir": "maps"}

Each grid dir holds one DataForSEO Maps JSON per point named <prefix>_<idx>.json
plus <prefix>_<idx>.noresult markers for no-pack cells. Points file rows:
"<idx> <lat> <lng>". A cell is measured iff at least one result title matches
--category. Pins: rank number where the target ranks, 20+ where measured but
absent, blank where unmeasured. Run tools/verify_pins.py on the output before
publishing; see docs/keyword-formula.md for how keywords are chosen.
"""
import argparse, json, math, os, re, struct, sys, zlib

GREEN, YELLOW, RED, WHITE, GOLD = (30, 142, 62), (249, 171, 0), (217, 48, 37), (255, 255, 255), (255, 210, 0)

CSS = """*{box-sizing:border-box}body{font-family:"Segoe UI",Arial,sans-serif;background:#000;color:#fff;font-size:12px;line-height:1.55;margin:0}.wrap{width:850px;margin:0 auto;padding:44px 52px}h1{font-size:36px;font-weight:800;margin:0}.sub{color:#666;font-size:13px}.rule{border:none;border-top:3px solid red;margin:14px 0 18px}.metricbar{display:table;width:100%;margin:16px 0;border-top:1px solid #666;border-bottom:1px solid #666}.metricbar .m{display:table-cell;text-align:center;padding:12px 4px}.metricbar .v{font-size:28px;font-weight:800}.red .v{color:red}.k{font-size:9px;color:#666}h2{font-size:18px;margin:30px 0 8px}h2 .n{color:red}h3{font-size:13px;margin:18px 0 6px}table.data{border-collapse:collapse;width:100%;margin:10px 0 16px;font-size:11px}table.data td,table.data th{border-bottom:1px solid #666;padding:5px 7px;text-align:left}td.r{color:red;font-weight:700}td.g{font-weight:700}img.map{width:100%;display:block;border:1px solid #666}.mapwrap{position:relative}.mapwrap svg{position:absolute;inset:0;width:100%;height:100%}.mapwrap text{fill:#fff;font-weight:700;font-size:14px;text-anchor:middle;dominant-baseline:central;font-family:inherit}.mapwrap text.rk1{font-size:20px}.foot{color:#666;font-size:9px;border-top:1px solid #666;padding-top:8px;margin-top:22px}.how{border:1px solid #666;padding:14px 16px;margin:14px 0}"""


def read_png_rgb(path):
    d = open(path, 'rb').read()
    pos, idat, plte = 8, b'', None
    while pos < len(d):
        ln = struct.unpack('>I', d[pos:pos+4])[0]
        typ = d[pos+4:pos+8]; body = d[pos+8:pos+8+ln]
        if typ == b'IHDR':
            w, h, bd, ct, _, _, _ = struct.unpack('>IIBBBBB', body)
        elif typ == b'PLTE':
            plte = body
        elif typ == b'IDAT':
            idat += body
        elif typ == b'IEND':
            break
        pos += 12 + ln
    raw = zlib.decompress(idat)
    ch = {0: 1, 2: 3, 3: 1}[ct]; stride = w * ch
    px = bytearray(w * h * ch); prev = bytearray(stride); p = 0
    for y in range(h):
        f = raw[p]; p += 1
        row = bytearray(raw[p:p+stride]); p += stride
        if f == 1:
            for i in range(ch, len(row)):
                row[i] = (row[i] + row[i-ch]) & 255
        elif f == 2:
            for i in range(len(row)):
                row[i] = (row[i] + prev[i]) & 255
        px[y*stride:(y+1)*stride] = row; prev = row
    if ct == 3:
        rgb = bytearray(w*h*3)
        for i in range(w*h):
            v = px[i]*3; rgb[i*3:i*3+3] = plte[v:v+3]
        return w, h, bytes(rgb)
    return w, h, bytes(px)


def write_png(path, w, h, rgb):
    def chunk(t, b):
        return struct.pack('>I', len(b)) + t + b + struct.pack('>I', zlib.crc32(t+b))
    raw = b''.join(b'\x00' + rgb[y*w*3:(y+1)*w*3] for y in range(h))
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
                            + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def project(lat, lng, clat, clng, z, W, H):
    s = 256 * (2 ** z)
    return (s*(lng+180)/360 - s*(clng+180)/360 + W/2,
            s*(0.5 - math.log((1+math.sin(math.radians(lat)))/(1-math.sin(math.radians(lat))))/(4*math.pi))
            - s*(0.5 - math.log((1+math.sin(math.radians(clat)))/(1-math.sin(math.radians(clat))))/(4*math.pi)) + H/2)


def circle(img, w, h, cx, cy, r, color, ring):
    for yy in range(int(cy-r-3), int(cy+r+4)):
        for xx in range(int(cx-r-3), int(cx+r+4)):
            if 0 <= xx < w and 0 <= yy < h:
                dd = math.hypot(xx-cx, yy-cy)
                if dd <= r:
                    img[(yy*w+xx)*3:(yy*w+xx)*3+3] = bytes(color)
                elif ring and dd <= r+2:
                    img[(yy*w+xx)*3:(yy*w+xx)*3+3] = bytes(ring)


def load_items(path):
    try:
        d = json.loads(open(path, 'rb').read().decode('cp1252'), strict=False)
    except Exception:
        d = json.loads(open(path, encoding='utf-8', errors='replace').read(), strict=False)
    return ((d.get('tasks') or [{}])[0].get('result') or [{}])[0].get('items') or [], \
           ((d.get('tasks') or [{}])[0].get('data') or {}).get('keyword')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--target", required=True, help="business name fragment, e.g. 'acme plumbing'")
    ap.add_argument("--category", required=True, help="regex for in-category titles")
    ap.add_argument("--zoom", type=int, default=12)
    a = ap.parse_args()
    cfg = json.load(open(a.config))
    lex = re.compile(a.category, re.I)
    tgt = a.target.lower()
    W, H, base = read_png_rgb(cfg["base_png"])
    clat, clng = cfg["center"]
    os.makedirs(cfg.get("out_dir", "maps"), exist_ok=True)
    blocks, rows = [], []
    for g in cfg["grids"]:
        coords = {}
        for ln in open(g["points"]):
            ix, la, ln2 = ln.split()
            coords[int(ix)] = (float(la), float(ln2))
        img = bytearray(base); svg = []; measured = 0; held = []
        for i, (lat, lng) in sorted(coords.items()):
            p = os.path.join(g["dir"], f"{g['prefix']}_{i}.json")
            if not (os.path.exists(p) and os.path.getsize(p) > 0):
                continue
            items, kw = load_items(p)
            assert kw == g["keyword"], (p, kw)
            if not items or not any(lex.search(t.get('title') or '') for t in items):
                continue
            rk = -1
            for it in items:
                if tgt in (it.get('title') or '').lower():
                    rk = it.get('rank_absolute') or -1
                    break
            px, py = project(lat, lng, clat, clng, a.zoom, W, H)
            col = RED if not (rk and rk > 0) else (GREEN if rk <= 3 else (YELLOW if rk <= 10 else RED))
            circle(img, W, H, px, py, 18, col, GOLD if rk == 1 else WHITE)
            svg.append('  <text x="%.1f" y="%.1f" class="%s">%s</text>'
                       % (px, py, 'rk1' if rk == 1 else ('pin' if rk and rk > 0 else 'abs'),
                          str(rk) if rk and rk > 0 else '20+'))
            measured += 1
            if rk == 1:
                held.append(i)
        outpng = os.path.join(cfg.get("out_dir", "maps"), g["prefix"] + ".png")
        write_png(outpng, W, H, bytes(img))
        svgdoc = '<svg viewBox="0 0 %d %d">\n%s\n</svg>' % (W, H, '\n'.join(svg))
        blocks.append('<h3>%s : %s cells measured, %s held</h3>\n<div class="mapwrap">'
                      '<img class="map" src="%s">\n%s\n</div>' % (g["label"], measured, len(held), outpng, svgdoc))
        rows.append('<tr><td>%s</td><td>%d</td><td class="g">%d</td><td>%s</td></tr>'
                    % (g["label"], measured, len(held), g.get("demand", "not pulled yet")))
        print(f'{g["label"]}: measured={measured} held={held}')
    html = ("""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>%s : geo visibility report</title>"""
            """<style>%s</style></head><body><div class="wrap"><h1>%s</h1><div class="sub">%s</div>"""
            """<hr class="rule"><h2><span class="n">01</span> how to read this map</h2><div class="how">"""
            """<p><b>what we did.</b> we stood a customer at grid points over the service area and typed the """
            """category keyword into google maps, exactly as a new customer would, recording the top results.</p>"""
            """<p><b>what the pins mean.</b> green with a number: the business ranks here. red 20 plus: outside """
            """the top 20 here. blank: google showed no in-category pack, no market to measure.</p></div>"""
            """<h2><span class="n">02</span> the battles</h2><p>%s</p>"""
            """<h2><span class="n">03</span> verdict</h2><table class="data">"""
            """<tr><th>battle</th><th>cells</th><th>held</th><th>demand</th></tr>%s</table>"""
            """<div class="foot">keywords chosen per docs/keyword-formula.md. map data copyright google. """
            """base map attribution per provider terms.</div></div></body></html>""")
    intro = ("same center, one grid per buyer intent. red 20 plus means outside the top 20. "
             "a pin appears only where google showed at least one in-category business.")
    open(cfg["out_html"], 'w').write(html % (cfg["business"], CSS, cfg["business"].lower(),
                                             cfg.get("subtitle", "geo visibility report"),
                                             intro, '\n'.join(blocks), '\n'.join(rows)))
    print('wrote', cfg["out_html"])


if __name__ == "__main__":
    sys.exit(main())
