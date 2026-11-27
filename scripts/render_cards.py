#!/usr/bin/env python3
"""Render outlined Legends Font SVG design cards (rev r1) for the legends-geogrid README."""
import argparse
import math
from pathlib import Path
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True


def _find_typeset_root() -> Path:
    candidates = []
    if os.environ.get("AVALON_TYPESET_ROOT"):
        candidates.append(Path(os.environ["AVALON_TYPESET_ROOT"]))
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates.append(parent / "avalonreset")
        candidates.append(parent / "cto-legends-glowup" / "repos" / "avalonreset")
    for cand in candidates:
        if (cand / "typeset.py").is_file():
            return cand
    raise SystemExit("FAIL: typeset.py not found; set AVALON_TYPESET_ROOT to the avalonreset directory.")


AVALON_ROOT = _find_typeset_root()
sys.path.insert(0, str(AVALON_ROOT))
from typeset import FONT, Typesetter, width  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REV = "r1"
CARDS_DIR = ROOT / "assets" / "cards" / REV

TYPE = {"head": 14, "title": 12, "body": 11, "label": 9}
K_WIDE = 829 / 886

BORDER = 'stroke="#ffffff" stroke-opacity="0.09" stroke-width="1"'
HAIR = 'stroke="#ffffff" stroke-opacity="0.07" stroke-width="1"'
CHIP = 'fill="#090a0e" stroke="#ffffff" stroke-opacity="0.15" stroke-width="1"'
RED = 'stroke="#ff0000" stroke-opacity="0.68" stroke-width="1"'
RED_HAIR = 'stroke="#ff0000" stroke-opacity="0.30" stroke-width="1"'


def u(role: str, k: float) -> float:
    return round(TYPE[role] / k, 2)


def svg(vb: str, body: str, t: Typesetter = None) -> str:
    defs = t.defs() if t else ""
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" width="100%">\n{defs}{body}</svg>\n'


def button(t: Typesetter, cx: float, y: float, fill: str, label: str, size: float, weight: str = "600") -> str:
    plain = re.sub(r"<[^>]+>|&\w+;", "", label)
    spacing = size * 0.1 if plain.isupper() else 0.0
    return t.run(cx, y, size, label, fill, weight, "middle", spacing)


def panel_defs(h: float) -> str:
    return (
        "  <defs>\n"
        f'    <linearGradient id="sheen" x1="0" y1="0" x2="0" y2="{h}" gradientUnits="userSpaceOnUse">'
        '<stop offset="0" stop-color="#ffffff" stop-opacity="0.04"/>'
        '<stop offset="0.55" stop-color="#ffffff" stop-opacity="0"/></linearGradient>\n'
        f'    <linearGradient id="edge" x1="0" y1="0" x2="0" y2="{h}" gradientUnits="userSpaceOnUse">'
        '<stop offset="0" stop-color="#ffffff" stop-opacity="0.22"/>'
        '<stop offset="1" stop-color="#ffffff" stop-opacity="0.08"/></linearGradient>\n'
        "  </defs>\n"
    )


def hex_pts(cx: float, cy: float, r: float, flat_top: bool = False) -> str:
    offset = 0.0 if flat_top else 30.0
    pts = []
    for i in range(6):
        ang = math.radians(offset + i * 60.0)
        pts.append(f"{cx + r * math.cos(ang):.2f},{cy + r * math.sin(ang):.2f}")
    return " ".join(pts)


def octagon_pts(cx: float, cy: float, r: float) -> str:
    pts = []
    for i in range(8):
        ang = math.radians(22.5 + i * 45)
        pts.append(f"{cx + r * math.cos(ang):.2f},{cy + r * math.sin(ang):.2f}")
    return " ".join(pts)


def render_slot_1() -> None:
    """Slot 1: Agent handoff header bar above the copy-paste code block."""
    t = Typesetter()
    ti, bd = u("title", K_WIDE), u("body", K_WIDE)
    note = "// paste this into claude code, codex or any coding agent and it does the setup"
    h = 34
    y_base = 22.5
    body = (
        f'  <rect x="0.5" y="0.5" width="885" height="{h - 1}" rx="4" fill="#0c0507" {RED}/>\n'
        f'  <rect x="0.5" y="0.5" width="4" height="{h - 1}" rx="2" fill="#ff0000"/>\n'
        + t.run(16, y_base, ti, "&gt;_", "#ff0000", "700")
        + t.run(16 + width("&gt;_", ti) + 8, y_base, ti, "agent handoff", "#ffffff", "700")
        + t.run(16 + width("&gt;_", ti) + 8 + width("agent handoff", ti) + 12, y_base, bd, note, "#a1a1aa")
    )
    (CARDS_DIR / "slot-1-agent-handoff.svg").write_text(svg(f"0 0 886 {h}", body, t), encoding="utf-8")


def render_slot_2() -> None:
    """Slot 2: Three-pillar overview card for legends-geogrid."""
    t = Typesetter()
    hd, ti, bd, lb = u("head", K_WIDE), u("title", K_WIDE), u("body", K_WIDE), u("label", K_WIDE)
    x0, x1 = 20, 866
    h = 198
    body = (
        panel_defs(h)
        + f'  <rect x="1" y="1" width="884" height="{h - 2}" rx="4" fill="#000000"/>\n'
        + f'  <rect x="1" y="1" width="884" height="{h - 2}" rx="4" fill="url(#sheen)" stroke="url(#edge)" stroke-width="1"/>\n'
        + f'  <rect x="1" y="1" width="4" height="{h - 2}" rx="2" fill="#ff0000"/>\n'
    )
    y_head = 26
    body += t.run(x0, y_head, ti, "&gt;_", "#ff0000", "700")
    x_title = x0 + width("&gt;_", ti) + 8
    body += t.run(x_title, y_head, hd, "You do not have one rank. You have a whole territory.", "#ffffff", "700")
    body += t.run(x1, y_head, lb, "// google maps · radial hex lattice · depth 30", "#a1a1aa", "400", "end")
    body += f'  <line x1="{x0}" y1="40" x2="{x1}" y2="40" {HAIR}/>\n'

    pillars = [
        (
            "01",
            "Radial hexagonal lattice",
            [
                "River-clipped honeycomb to depth 30:",
                "39.5% fewer pins for equal blind-spot",
                "accuracy vs +41.4% square corners.",
            ],
        ),
        (
            "02",
            "Interactive &amp; PDF studio",
            [
                "Explore Local Leaders, Campaigns,",
                "Strategy Room, and vector-hex PDF",
                "reports at wholesale API rates ($0.82).",
            ],
        ),
        (
            "03",
            "Street View signage audit",
            [
                "Pairs live GBP titles with website",
                "branding, storefront &amp; logo photos,",
                "Street View links &amp; optional OCR.",
            ],
        ),
    ]
    gap = 28
    col_w = (x1 - x0 - 2 * gap) / 3
    y_col_head = 67
    for i, (num, title, lines) in enumerate(pillars):
        cx = x0 + i * (col_w + gap)
        body += t.run(cx, y_col_head, lb, num, "#ff0000", "700")
        body += t.run(cx + width(num, lb) + 9, y_col_head, ti, title, "#ffffff", "700")
        for j, ln in enumerate(lines):
            body += t.run(cx, y_col_head + 22 + 18 * j, bd, ln, "#a1a1aa", "400")
        if i > 0:
            vx = cx - gap / 2
            body += f'  <line x1="{vx:.2f}" y1="52" x2="{vx:.2f}" y2="136" {HAIR}/>\n'

    body += f'  <line x1="{x0}" y1="148" x2="{x1}" y2="148" {HAIR}/>\n'
    chip_top = 165
    base = chip_top + 13.5
    lab = "works with:"
    body += t.run(x0, base, lb, lab, "#a1a1aa", "600")
    cx = x0 + width(lab, lb) + 10
    chips = ("google-maps", "dataforseo", "openfreemap", "street-view", "jev-ocr", "claude", "codex")
    for ch in chips:
        cw = width(ch, lb) + 16
        body += f'  <rect x="{cx:.2f}" y="{chip_top}" width="{cw:.2f}" height="20" rx="3" {CHIP}/>\n'
        body += t.run(cx + cw / 2, base, lb, ch, "#e4e4e7", "600", "middle")
        cx += cw + 6
    body += t.run(x1, base, lb, "wholesale api rates", "#ff0000", "600", "end")

    (CARDS_DIR / "slot-2-three-pillars.svg").write_text(svg(f"0 0 886 {h}", body, t), encoding="utf-8")


def render_slot_3() -> None:
    """Slot 3: 4-row visual chain map ('Say the job in plain words')."""
    t = Typesetter()
    hd, ti, bd, lb = u("head", K_WIDE), u("title", K_WIDE), u("body", K_WIDE), u("label", K_WIDE)
    h = 208
    x0, x1 = 20, 866
    body = (
        panel_defs(h)
        + f'  <rect x="1" y="1" width="884" height="{h - 2}" rx="4" fill="#000000"/>\n'
        + f'  <rect x="1" y="1" width="884" height="{h - 2}" rx="4" fill="url(#sheen)" stroke="url(#edge)" stroke-width="1"/>\n'
        + f'  <rect x="1" y="1" width="4" height="{h - 2}" rx="2" fill="#ff0000"/>\n'
    )
    body += t.run(x0, 26, hd, "Say the job in plain words", "#ffffff", "700")
    body += t.run(
        x0 + width("Say the job in plain words", hd) + 12,
        26,
        lb,
        "// your agent designs, budgets and maps the study",
        "#ff0000",
        "600",
    )
    body += f'  <line x1="{x0}" y1="38" x2="{x1}" y2="38" {HAIR}/>\n'

    rows = [
        (
            "01",
            '"Open the example Philly map"',
            'study.py --open <tspan fill="#ff0000">→</tspan> 458 Philly hex points · 3 queries <tspan fill="#ff0000">→</tspan> zero keys or spend',
        ),
        (
            "02",
            '"Study our business on Google Maps"',
            'website &amp; GBP check <tspan fill="#ff0000">→</tspan> 3 to 5 search themes <tspan fill="#ff0000">→</tspan> cost ceiling proposal',
        ),
        (
            "03",
            '"Check top rivals for keyword stuffing"',
            'exact CID refresh <tspan fill="#ff0000">→</tspan> storefront signage &amp; Street View <tspan fill="#ff0000">→</tspan> 0 to 5 signage dossier',
        ),
        (
            "04",
            '"Expand this study out to 10 miles"',
            'reuses inner ring <tspan fill="#ff0000">→</tspan> collects outer lattice <tspan fill="#ff0000">→</tspan> PDF &amp; HTML strategy report',
        ),
    ]

    pill_x = 368
    pill_w = x1 - pill_x
    for i, (num, prompt_txt, chain_markup) in enumerate(rows):
        ry = 64 + i * 42
        if i > 0:
            div_y = ry - 25
            body += f'  <line x1="{x0}" y1="{div_y}" x2="{x1}" y2="{div_y}" {HAIR}/>\n'
        prompt_x = x0 + width(num, lb) + 10
        assert prompt_x + width(prompt_txt, bd) + 14 <= pill_x - 16, f"Row {num} collides with arrow"
        body += t.run(x0, ry, lb, num, "#ff0000", "700")
        body += t.run(prompt_x, ry, bd, prompt_txt, "#ffffff", "700")
        body += t.run(pill_x - 16, ry, ti, "→", "#ff0000", "700", "middle")
        body += f'  <rect x="{pill_x}" y="{ry - 16.5:.1f}" width="{pill_w}" height="24" rx="3" fill="#090a0e" {RED_HAIR}/>\n'
        body += t.run(pill_x + 12, ry - 0.5, lb, chain_markup, "#ffffff", "600")

    (CARDS_DIR / "slot-3-plain-english-chains.svg").write_text(svg(f"0 0 886 {h}", body, t), encoding="utf-8")


def render_slot_4() -> None:
    """Slot 4: Radial Hexagonal Lattice vs. Legacy Square Grid architectural proof card."""
    t = Typesetter()
    hd, ti, bd, lb = u("head", K_WIDE), u("title", K_WIDE), u("body", K_WIDE), u("label", K_WIDE)
    sm = round(lb * 0.92, 2)
    x0, x1 = 20, 866
    h = 424

    body = (
        "  <defs>\n"
        f'    <linearGradient id="sheen" x1="0" y1="0" x2="0" y2="{h}" gradientUnits="userSpaceOnUse">'
        '<stop offset="0" stop-color="#ffffff" stop-opacity="0.04"/>'
        '<stop offset="0.55" stop-color="#ffffff" stop-opacity="0"/></linearGradient>\n'
        f'    <linearGradient id="edge" x1="0" y1="0" x2="0" y2="{h}" gradientUnits="userSpaceOnUse">'
        '<stop offset="0" stop-color="#ffffff" stop-opacity="0.22"/>'
        '<stop offset="1" stop-color="#ffffff" stop-opacity="0.08"/></linearGradient>\n'
        '    <mask id="sq-waste-mask">\n'
        '      <rect x="44" y="122" width="112" height="112" fill="#ffffff"/>\n'
        '      <circle cx="100" cy="178" r="56" fill="#000000"/>\n'
        '    </mask>\n'
        '    <clipPath id="hex-circle-clip">\n'
        '      <circle cx="532" cy="178" r="57"/>\n'
        '    </clipPath>\n'
        "  </defs>\n"
        + f'  <rect x="1" y="1" width="884" height="{h - 2}" rx="4" fill="#000000"/>\n'
        + f'  <rect x="1" y="1" width="884" height="{h - 2}" rx="4" fill="url(#sheen)" stroke="url(#edge)" stroke-width="1"/>\n'
        + f'  <rect x="1" y="1" width="4" height="{h - 2}" rx="2" fill="#ff0000"/>\n'
    )

    # Header
    body += t.run(x0, 27, hd, "Why square rank grids waste budget and distort local rank", "#ffffff", "700")
    body += t.run(x1, 27, lb, "// radial hexagonal lattice vs square grid", "#ff0000", "600", "end")
    body += f'  <line x1="{x0}" y1="41" x2="{x1}" y2="41" {HAIR}/>\n'

    box_w = 414
    box_y = 54
    box_h = 272

    # ================= LEFT CHAMBER: LEGACY SQUARE GRID =================
    body += f'  <rect x="{x0}" y="{box_y}" width="{box_w}" height="{box_h}" rx="3" fill="#090a0e" {BORDER}/>\n'
    body += t.run(x0 + 16, box_y + 23, ti, "LEGACY SQUARE GRID", "#d4d4d8", "700")
    body += t.run(x0 + box_w - 14, box_y + 23, lb, "// +41.4% corner stretch", "#ff0000", "600", "end")
    body += f'  <line x1="{x0 + 14}" y1="{box_y + 34}" x2="{x0 + box_w - 14}" y2="{box_y + 34}" {HAIR}/>\n'

    # Vector 5x5 square grid diagram (center 100, 178, half-width 56 -> 112x112)
    lcx, lcy, lr = 100.0, 178.0, 56.0
    # Highlight the 21.5% wasted corner area outside the inscribed circle
    body += f'  <rect x="{lcx - lr:.1f}" y="{lcy - lr:.1f}" width="{lr * 2:.1f}" height="{lr * 2:.1f}" fill="#ff0000" fill-opacity="0.18" mask="url(#sq-waste-mask)"/>\n'
    # Square grid lines (4x4 cells = 5x5 vertices, step = 28)
    step = lr / 2.0
    for k in range(-2, 3):
        gx = lcx + k * step
        gy = lcy + k * step
        body += f'  <line x1="{gx:.1f}" y1="{lcy - lr:.1f}" x2="{gx:.1f}" y2="{lcy + lr:.1f}" stroke="#ffffff" stroke-opacity="0.14" stroke-width="1"/>\n'
        body += f'  <line x1="{lcx - lr:.1f}" y1="{gy:.1f}" x2="{lcx + lr:.1f}" y2="{gy:.1f}" stroke="#ffffff" stroke-opacity="0.14" stroke-width="1"/>\n'
    # Outer square frame
    body += f'  <rect x="{lcx - lr:.1f}" y="{lcy - lr:.1f}" width="{lr * 2:.1f}" height="{lr * 2:.1f}" fill="none" stroke="#8b8b94" stroke-opacity="0.65" stroke-width="1.2"/>\n'
    # Dashed inscribed trade-area circle
    body += f'  <circle cx="{lcx:.1f}" cy="{lcy:.1f}" r="{lr:.1f}" fill="none" stroke="#ffffff" stroke-opacity="0.45" stroke-dasharray="3 3" stroke-width="1"/>\n'
    # Diagonal stretch ray to top-right corner
    body += f'  <line x1="{lcx:.1f}" y1="{lcy:.1f}" x2="{lcx + lr:.1f}" y2="{lcy - lr:.1f}" stroke="#ff0000" stroke-opacity="0.85" stroke-width="1.3" stroke-dasharray="3 2"/>\n'
    # Diagonal blind-spot highlight in bottom-left interior square cell
    body += f'  <line x1="{lcx - step:.1f}" y1="{lcy:.1f}" x2="{lcx:.1f}" y2="{lcy + step:.1f}" stroke="#ff0000" stroke-opacity="0.72" stroke-width="1.2" stroke-dasharray="2 2"/>\n'
    # Plot all 25 square grid pins: red if outside radius R, muted grey inside
    for ix in range(-2, 3):
        for iy in range(-2, 3):
            px, py = lcx + ix * step, lcy + iy * step
            dist = math.hypot(ix * step, iy * step)
            if ix == 0 and iy == 0:
                body += f'  <circle cx="{px:.1f}" cy="{py:.1f}" r="3.8" fill="#ffffff"/>\n'
            elif dist > lr + 0.5:
                # Out-of-radius wasted corner pin
                body += f'  <circle cx="{px:.1f}" cy="{py:.1f}" r="3.2" fill="#ff0000"/>\n'
            else:
                body += f'  <circle cx="{px:.1f}" cy="{py:.1f}" r="2.2" fill="#8b8b94"/>\n'
    # Diagram micro-captions beneath square
    body += t.run(lcx, lcy + lr + 18, sm, "red pins = outside radius", "#ff0000", "600", "middle")
    body += t.run(lcx, lcy + lr + 33, sm, "21.5% dead corner area", "#a1a1aa", "400", "middle")

    # Right text column inside Left Chamber
    ltx = x0 + 174
    left_bullets = [
        ("21.5% dead corner waste", "Corners sit 41.4% farther out", "than edges; 1 in 5 pins is junk."),
        ("+41.4% diagonal gaps", "Only 4 close neighbors; diagonal", "blind spots stretch 1.41x wider."),
        ("Scans open water", "Unclipped boxes burn credits", "on rivers, bays, and lakes."),
        ("Depth 20 + SaaS tax", "Hides ranks 21-30 behind", "$50-$250/mo credit markups."),
    ]
    for i, (head_txt, ln1, ln2) in enumerate(left_bullets):
        by = box_y + 56 + i * 54
        for check_txt, sz in ((head_txt, lb), (ln1, sm), (ln2, sm)):
            assert ltx + width(check_txt, sz) <= x0 + box_w - 10, f"Left bullet overflow: {check_txt}"
        body += t.run(ltx, by, lb, head_txt, "#ff0000", "700")
        body += t.run(ltx, by + 15, sm, ln1, "#d4d4d8", "400")
        body += t.run(ltx, by + 29, sm, ln2, "#a1a1aa", "400")

    # ================= RIGHT CHAMBER: RADIAL HEXAGONAL LATTICE =================
    rx0 = x1 - box_w
    body += f'  <rect x="{rx0}" y="{box_y}" width="{box_w}" height="{box_h}" rx="3" fill="#0c0507" {RED_HAIR}/>\n'
    body += t.run(rx0 + 16, box_y + 23, ti, "RADIAL HEXAGONAL LATTICE", "#ffffff", "700")
    body += t.run(rx0 + box_w - 14, box_y + 23, lb, "// legends-geogrid", "#ff0000", "600", "end")
    body += f'  <line x1="{rx0 + 14}" y1="{box_y + 34}" x2="{rx0 + box_w - 14}" y2="{box_y + 34}" {RED_HAIR}/>\n'

    # Real circle-clipped hexagonal honeycomb vector diagram (center 532, 178, r = 56)
    rcx, rcy, rr = 532.0, 178.0, 56.0
    hex_step = 19.5
    hex_r = hex_step / math.sqrt(3.0)  # exact Voronoi cell circumradius!
    # Clean river band notched out inside circle on east-southeast side
    river_path = (
        f"M {rcx + 28:.1f},{rcy - 60:.1f} "
        f"C {rcx + 22:.1f},{rcy - 18:.1f} {rcx + 36:.1f},{rcy + 12:.1f} {rcx + 14:.1f},{rcy + 60:.1f} "
        f"L {rcx + 26:.1f},{rcy + 60:.1f} "
        f"C {rcx + 48:.1f},{rcy + 12:.1f} {rcx + 34:.1f},{rcy - 18:.1f} {rcx + 40:.1f},{rcy - 60:.1f} Z"
    )
    body += '  <g clip-path="url(#hex-circle-clip)">\n'
    body += f'    <circle cx="{rcx:.1f}" cy="{rcy:.1f}" r="{rr:.1f}" fill="#090a0e"/>\n'
    body += f'    <path d="{river_path}" fill="#000000" stroke="#52525b" stroke-opacity="0.7" stroke-dasharray="2 2" stroke-width="0.9"/>\n'

    # Generate true axial hex lattice inside circle, excluding the river ribbon!
    sqrt3 = math.sqrt(3.0)
    hex_centers = []
    for qr in range(-4, 5):
        for qq in range(-4, 5):
            ex = hex_step * (qq + qr / 2.0)
            ey = hex_step * (sqrt3 / 2.0 * qr)
            dist = math.hypot(ex, ey)
            if dist <= rr - 2.0:
                river_x = 29.0 + 5.0 * math.sin((ey / rr) * 2.2) - (8.0 if ey > 24 else 0.0)
                if abs(ex - river_x) < 7.8:
                    continue
                hex_centers.append((qq, qr, rcx + ex, rcy + ey, dist))

    # Draw interlocking hexagonal Voronoi cells
    for qq, qr, hx, hy, dist in hex_centers:
        is_center = (qq == 0 and qr == 0)
        is_ring1 = (max(abs(qq), abs(qr), abs(qq + qr)) == 1)
        fill = "#ff0000" if is_center else ("#ff0000" if is_ring1 else "#ffffff")
        fop = "0.28" if is_center else ("0.11" if is_ring1 else "0.03")
        stroke = "#ff0000" if (is_center or is_ring1) else "#ffffff"
        sop = "0.85" if is_center else ("0.52" if is_ring1 else "0.20")
        body += (
            f'    <polygon points="{hex_pts(hx, hy, hex_r - 0.5, flat_top=False)}" '
            f'fill="{fill}" fill-opacity="{fop}" stroke="{stroke}" stroke-opacity="{sop}" stroke-width="0.9"/>\n'
        )

    # 6 equidistant 60-degree neighbor spokes from storefront center
    for qq, qr, hx, hy, dist in hex_centers:
        if max(abs(qq), abs(qr), abs(qq + qr)) == 1:
            body += f'    <line x1="{rcx:.1f}" y1="{rcy:.1f}" x2="{hx:.1f}" y2="{hy:.1f}" stroke="#ffffff" stroke-opacity="0.58" stroke-width="1"/>\n'

    # Plot dry-land hex pin nodes
    for qq, qr, hx, hy, dist in hex_centers:
        if qq == 0 and qr == 0:
            body += f'    <circle cx="{hx:.1f}" cy="{hy:.1f}" r="4.0" fill="#ff0000" stroke="#ffffff" stroke-width="1.2"/>\n'
        elif max(abs(qq), abs(qr), abs(qq + qr)) == 1:
            body += f'    <circle cx="{hx:.1f}" cy="{hy:.1f}" r="2.4" fill="#ffffff"/>\n'
        else:
            body += f'    <circle cx="{hx:.1f}" cy="{hy:.1f}" r="1.8" fill="#e4e4e7" fill-opacity="0.72"/>\n'
    body += "  </g>\n"
    # Crisp circular radius boundary
    body += f'  <circle cx="{rcx:.1f}" cy="{rcy:.1f}" r="{rr:.1f}" fill="none" stroke="#ff0000" stroke-opacity="0.88" stroke-width="1.4"/>\n'
    body += t.run(rcx, rcy + rr + 18, sm, "6 equal 60-deg neighbors", "#ffffff", "600", "middle")
    body += t.run(rcx, rcy + rr + 33, sm, "exact circle + river clip", "#a1a1aa", "400", "middle")

    # Right text column inside Right Chamber
    rtx = rx0 + 174
    right_bullets = [
        ("0% corner distortion", "Exact haversine circle clip keeps", "100% of pins in your true radius."),
        ("6 equidistant neighbors", "Isotropic honeycomb cuts max", "blind spot 18.4% at same spacing."),
        ("39.5% fewer pins needed", "Optimal 2D hex covering + river", "clip eliminates wasted water scans."),
        ("Depth 30 + nested ladder", "Refine 4->2->1->0.5 mi reusing", "every pin; $0.82 wholesale cost."),
    ]
    for i, (head_txt, ln1, ln2) in enumerate(right_bullets):
        by = box_y + 56 + i * 54
        for check_txt, sz in ((head_txt, lb), (ln1, sm), (ln2, sm)):
            assert rtx + width(check_txt, sz) <= rx0 + box_w - 10, f"Right bullet overflow: {check_txt}"
        body += t.run(rtx, by, lb, head_txt, "#ffffff", "700")
        body += t.run(rtx, by + 15, sm, ln1, "#e4e4e7", "400")
        body += t.run(rtx, by + 29, sm, ln2, "#a1a1aa", "400")

    # ================= BOTTOM PROOF BAR =================
    bar_y = 338
    bar_h = 72
    body += f'  <rect x="{x0}" y="{bar_y}" width="{x1 - x0}" height="{bar_h}" rx="3" fill="#090a0e" {RED_HAIR}/>\n'
    body += f'  <rect x="{x0}" y="{bar_y}" width="3" height="{bar_h}" rx="1.5" fill="#ff0000"/>\n'
    body += t.run(x0 + 14, bar_y + 18, sm, "MEASURED 6-MILE SOUTH PHILLY PROOF", "#ff0000", "700")
    body += t.run(
        x0 + 14 + width("MEASURED 6-MILE SOUTH PHILLY PROOF", sm) + 10,
        bar_y + 18,
        sm,
        "// equal 0.289 mi worst-case blind spot (Cosmi's Deli)",
        "#a1a1aa",
        "400",
    )
    body += f'  <line x1="{x0 + 14}" y1="{bar_y + 26}" x2="{x1 - 14}" y2="{bar_y + 26}" {HAIR}/>\n'

    stats = [
        ("961 -> 458 pins", "52.3% fewer pins vs equal-accuracy square"),
        ("55 water pins cut", "10.7% open-river waste clipped via OSM"),
        ("$0.82 wholesale", "1,374 depth-30 searches; $0/mo SaaS fee"),
    ]
    col_w = (x1 - x0 - 28) / 3.0
    for idx, (val, desc) in enumerate(stats):
        sx = x0 + 14 + idx * col_w
        if idx > 0:
            body += f'  <line x1="{sx - 8:.1f}" y1="{bar_y + 32}" x2="{sx - 8:.1f}" y2="{bar_y + bar_h - 8}" {HAIR}/>\n'
        assert width(desc, sm) <= col_w - 12, f"Bottom stat overflow: {desc}"
        body += t.run(sx, bar_y + 45, ti, val, "#ffffff", "700")
        body += t.run(sx, bar_y + 61, sm, desc, "#a1a1aa", "400")

    (CARDS_DIR / "slot-4-circular-vs-square.svg").write_text(svg(f"0 0 886 {h}", body, t), encoding="utf-8")


def render_slot_5() -> None:
    """Slot 5: Comparison table ('Monthly local rank SaaS' vs 'Your own territory engine // legends-geogrid')."""
    t = Typesetter()
    ti, lb = u("title", K_WIDE), u("label", K_WIDE)
    rows = [
        ("Grid geometry &amp; depth", "Square (+41.4% corners, 21.5% waste), rank 20", "Radial hex lattice + river clip, depth 30 (39.5% fewer pins)"),
        ("Search window accuracy", "Restricted viewport clips real competitors", "Open search by default + straight-edge diagnostic"),
        ("Competitor name checks", "Manual eyeballing or blind keyword flags", "Website brand + storefront photos + Street View + OCR"),
        ("Data cost &amp; ownership", "Recurring $50-$250/mo SaaS &amp; locked exports", "Wholesale DataForSEO (~$0.82 to $3.00) on local disk"),
    ]
    h = 198
    col0_x, col1_x, col2_x = 20, 206, 500
    body = (
        panel_defs(h)
        + f'  <rect x="1" y="1" width="884" height="{h - 2}" rx="4" fill="#000000"/>\n'
        + f'  <rect x="1" y="1" width="884" height="{h - 2}" rx="4" fill="url(#sheen)" stroke="url(#edge)" stroke-width="1"/>\n'
        + f'  <rect x="{col2_x - 12}" y="7" width="{880 - (col2_x - 12)}" height="{h - 14}" rx="3" fill="#0c0507" {RED_HAIR}/>\n'
    )
    y_hdr = 27
    body += t.run(col0_x, y_hdr, lb, "comparison", "#8b8b94", "600")
    body += t.run(col1_x, y_hdr, ti, "Monthly local rank SaaS", "#a1a1aa", "700")
    body += t.run(col2_x, y_hdr, ti, "Your own territory engine", "#ffffff", "700")
    body += t.run(col2_x + width("Your own territory engine", ti) + 10, y_hdr, lb, "// legends-geogrid", "#ff0000", "600")
    body += f'  <line x1="16" y1="39" x2="870" y2="39" {HAIR}/>\n'
    body += f'  <line x1="{col1_x - 12}" y1="12" x2="{col1_x - 12}" y2="{h - 12}" {HAIR}/>\n'

    for i, (label_txt, raw_txt, emp_txt) in enumerate(rows):
        ry = 64 + i * 38
        if i > 0:
            div_y = ry - 21
            body += f'  <line x1="16" y1="{div_y}" x2="870" y2="{div_y}" {HAIR}/>\n'
        body += t.run(col0_x, ry, lb, label_txt, "#e4e4e7", "600")
        body += t.run(col1_x, ry, lb, raw_txt, "#a1a1aa", "400")
        body += t.run(col2_x, ry, lb, emp_txt, "#ffffff", "600")

    (CARDS_DIR / "slot-5-saas-vs-geogrid.svg").write_text(svg(f"0 0 886 {h}", body, t), encoding="utf-8")


def render_slot_shrine() -> None:
    """Graphic shrine for the cto-legends GitHub Star List."""
    t = Typesetter()
    hd, bd, lb = u("head", K_WIDE), u("body", K_WIDE), u("label", K_WIDE)
    h = 96
    cx, cy = 58.0, 48.0
    r_out, r_in = 23.5, 9.8
    verts = []
    for i in range(10):
        ang = math.radians(-90 + i * 36)
        r = r_out if i % 2 == 0 else r_in
        verts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))

    facets = ""
    for i in range(10):
        x1, y1 = verts[i]
        x2, y2 = verts[(i + 1) % 10]
        tri = f"{cx:.2f},{cy:.2f} {x1:.2f},{y1:.2f} {x2:.2f},{y2:.2f}"
        facets += f'  <polygon points="{tri}" fill="#ff0000"/>\n'
        if i % 2 == 1:
            facets += f'  <polygon points="{tri}" fill="#000000" opacity="0.34"/>\n'
    star_outline = " ".join(f"{x:.2f},{y:.2f}" for x, y in verts)

    def mini_star(mx: float, my: float, ro: float = 4.2, ri: float = 1.6) -> str:
        pts = []
        for k in range(8):
            a = math.radians(-90 + k * 45)
            rk = ro if k % 2 == 0 else ri
            pts.append(f"{mx + rk * math.cos(a):.2f},{my + rk * math.sin(a):.2f}")
        return " ".join(pts)

    body = (
        "  <defs>\n"
        f'    <linearGradient id="sheen" x1="0" y1="0" x2="0" y2="{h}" gradientUnits="userSpaceOnUse">'
        '<stop offset="0" stop-color="#ffffff" stop-opacity="0.05"/>'
        '<stop offset="0.65" stop-color="#ffffff" stop-opacity="0"/></linearGradient>\n'
        f'    <radialGradient id="star-aura" cx="{cx:.1f}" cy="{cy:.1f}" r="34" gradientUnits="userSpaceOnUse">'
        '<stop offset="0" stop-color="#ff0000" stop-opacity="0.32"/>'
        '<stop offset="0.65" stop-color="#ff0000" stop-opacity="0.08"/>'
        '<stop offset="1" stop-color="#ff0000" stop-opacity="0"/></radialGradient>\n'
        "  </defs>\n"
        + f'  <rect x="1" y="1" width="884" height="{h - 2}" rx="4" fill="#0c0507" {RED}/>\n'
        + f'  <rect x="1" y="1" width="884" height="{h - 2}" rx="4" fill="url(#sheen)"/>\n'
        + f'  <rect x="1" y="1" width="4" height="{h - 2}" rx="2" fill="#ff0000"/>\n'
        + '  <rect x="18" y="12" width="80" height="72" rx="4" fill="#000000" stroke="#ff0000" stroke-opacity="0.55" stroke-width="1"/>\n'
        + '  <rect x="22" y="16" width="72" height="64" rx="2" fill="none" stroke="#ffffff" stroke-opacity="0.08" stroke-width="1"/>\n'
        + f'  <circle cx="{cx:.1f}" cy="{cy:.1f}" r="34" fill="url(#star-aura)"/>\n'
        + facets
        + f'  <polygon points="{star_outline}" fill="none" stroke="#ff0000" stroke-opacity="0.9" stroke-width="0.6"/>\n'
        + f'  <polygon points="{mini_star(29.5, 48.0)}" fill="#ff0000" opacity="0.75"/>\n'
        + f'  <polygon points="{mini_star(86.5, 48.0)}" fill="#ff0000" opacity="0.75"/>\n'
    )
    tx = 116
    sub = "Bookmark or star the router and every module from a single GitHub list."
    body += t.run(tx, 27, lb, "GITHUB STAR LIST", "#ff0000", "700")
    x_meta = tx + width("GITHUB STAR LIST", lb) + 10
    body += t.run(x_meta, 27, lb, "// github.com/stars/avalonreset/lists/cto-legends", "#a1a1aa", "400")
    body += t.run(tx, 52, hd, "The complete cto-legends collection on one page", "#ffffff", "700")
    body += t.run(tx, 74, bd, sub, "#d4d4d8", "400")

    btn_w = 216
    btn_x = 868 - btn_w
    assert tx + width(sub, bd) + 20 <= btn_x, "Shrine subline collides with button"
    body += f'  <rect x="{btn_x}" y="29" width="{btn_w}" height="38" rx="3" fill="#000000" {RED}/>\n'
    body += button(t, btn_x + btn_w / 2, 52.5, "#ffffff", 'OPEN GITHUB LIST <tspan fill="#ff0000">↗</tspan>', lb, "700")

    (CARDS_DIR / "slot-collection-star-shrine.svg").write_text(svg(f"0 0 886 {h}", body, t), encoding="utf-8")


def render_slot_7() -> None:
    """Slot 7: Closing message desk CTA card ('Message Avalon Reset')."""
    t = Typesetter()
    ti, bd, lb = u("title", K_WIDE), u("body", K_WIDE), u("label", K_WIDE)
    h = 68
    body = (
        f'  <rect x="1" y="1" width="884" height="{h - 2}" rx="4" fill="#0c0507" {RED}/>\n'
        f'  <rect x="1" y="1" width="4" height="{h - 2}" rx="2" fill="#ff0000"/>\n'
    )
    body += t.run(22, 28, ti, "Want this way of working applied to your own stack?", "#ffffff", "700")
    body += t.run(22, 48, bd, "Message Avalon Reset", "#ff0000", "700")
    x_note = 22 + width("Message Avalon Reset", bd) + 10
    body += t.run(x_note, 48, lb, "// async message desk at cto-legends.com/dm", "#a1a1aa", "400")

    btn_w = 228
    btn_x = 868 - btn_w
    body += f'  <rect x="{btn_x}" y="18" width="{btn_w}" height="32" rx="3" fill="#000000" {RED}/>\n'
    body += button(t, btn_x + btn_w / 2, 38.5, "#ffffff", 'MESSAGE AVALON RESET <tspan fill="#ff0000">↗</tspan>', lb, "700")

    (CARDS_DIR / "slot-7-message-avalon-reset.svg").write_text(svg(f"0 0 886 {h}", body, t), encoding="utf-8")


def validate() -> None:
    expected = [
        "slot-1-agent-handoff.svg",
        "slot-2-three-pillars.svg",
        "slot-3-plain-english-chains.svg",
        "slot-4-circular-vs-square.svg",
        "slot-5-saas-vs-geogrid.svg",
        "slot-7-message-avalon-reset.svg",
        "slot-collection-star-shrine.svg",
    ]
    svgs = sorted(CARDS_DIR.glob("*.svg"))
    names = [p.name for p in svgs]
    assert names == expected, f"Expected {len(expected)} SVGs {expected}, found {names}"
    allowed_hex = {
        "#000000", "#ffffff", "#ff0000",
        "#e4e4e7", "#d4d4d8", "#a1a1aa", "#8b8b94", "#52525b",
        "#090a0e", "#0c0507",
    }
    for p in svgs:
        raw = p.read_bytes().replace(b"\r\n", b"\n")
        p.write_bytes(raw)
        s = raw.decode("utf-8")
        assert "\u2014" not in s and "\u2013" not in s, f"Dash found in {p.name}"
        assert "<text" not in s, f"Live <text> element found in {p.name}; all text must be outlined"
        ET.fromstring(s)
        colors = {c.lower() for c in re.findall(r"#[0-9a-fA-F]{6}", s)}
        unexpected = colors - allowed_hex
        assert not unexpected, f"Unexpected color in {p.name}: {unexpected}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Render outlined Legends Font SVG cards (rev r1) for legends-geogrid.")
    ap.parse_args()
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    render_slot_1()
    render_slot_2()
    render_slot_3()
    render_slot_4()
    render_slot_5()
    render_slot_shrine()
    render_slot_7()
    validate()
    print(f"Rendered and validated 7 SVG cards in {CARDS_DIR.relative_to(ROOT)} (font={FONT}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
