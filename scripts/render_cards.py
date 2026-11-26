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
    body += t.run(x1, y_head, lb, "// google maps · circular lattice · depth 30", "#a1a1aa", "400", "end")
    body += f'  <line x1="{x0}" y1="40" x2="{x1}" y2="40" {HAIR}/>\n'

    pillars = [
        (
            "01",
            "Circular territory lattice",
            [
                "True circular distance rings up to 30",
                "results deep, without the 41% corner",
                "distortion of square rank grids.",
            ],
        ),
        (
            "02",
            "Interactive &amp; PDF studio",
            [
                "Explore Local Leaders, Campaigns,",
                "Strategy Room, and vector PDF",
                "reports at wholesale API rates.",
            ],
        ),
        (
            "03",
            "Street View signage audit",
            [
                "Pairs live GBP titles with website",
                "branding, multi-angle Street View,",
                "and optical storefront sign reads.",
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
    """Slot 4: Circular Territory Lattice vs. Square Grid Trap architectural diagram card."""
    t = Typesetter()
    hd, ti, bd, lb = u("head", K_WIDE), u("title", K_WIDE), u("body", K_WIDE), u("label", K_WIDE)
    x0, x1 = 20, 866
    h = 204
    body = (
        panel_defs(h)
        + f'  <rect x="1" y="1" width="884" height="{h - 2}" rx="4" fill="#000000"/>\n'
        + f'  <rect x="1" y="1" width="884" height="{h - 2}" rx="4" fill="url(#sheen)" stroke="url(#edge)" stroke-width="1"/>\n'
        + f'  <rect x="1" y="1" width="4" height="{h - 2}" rx="2" fill="#ff0000"/>\n'
    )
    body += t.run(x0, 26, hd, "Why circular territory geometry beats square rank grids", "#ffffff", "700")
    body += t.run(x1, 26, lb, "// true circular lattice vs +41% square corners", "#a1a1aa", "400", "end")
    body += f'  <line x1="{x0}" y1="40" x2="{x1}" y2="40" {HAIR}/>\n'

    box_w = 412
    box_h = 92
    # Left chamber: The Square Grid Trap
    body += f'  <rect x="{x0}" y="52" width="{box_w}" height="{box_h}" rx="3" fill="#090a0e" {BORDER}/>\n'
    # Mini vector illustration of square grid + inscribed circle (center at x0+44, y=98, r=24)
    lcx, lcy, lr = x0 + 44, 98, 24
    body += f'  <rect x="{lcx - lr}" y="{lcy - lr}" width="{lr * 2}" height="{lr * 2}" fill="none" stroke="#8b8b94" stroke-opacity="0.55" stroke-width="1"/>\n'
    body += f'  <circle cx="{lcx}" cy="{lcy}" r="{lr}" fill="none" stroke="#ffffff" stroke-opacity="0.25" stroke-dasharray="2 2" stroke-width="1"/>\n'
    # Corner distortion diagonals and corner dots outside circle
    for dx in (-1, 1):
        for dy in (-1, 1):
            px, py = lcx + dx * lr, lcy + dy * lr
            body += f'  <line x1="{lcx}" y1="{lcy}" x2="{px}" y2="{py}" stroke="#ff0000" stroke-opacity="0.35" stroke-width="1"/>\n'
            body += f'  <circle cx="{px}" cy="{py}" r="2.6" fill="#ff0000"/>\n'
    body += f'  <circle cx="{lcx}" cy="{lcy}" r="3" fill="#a1a1aa"/>\n'

    ltx = x0 + 84
    body += t.run(ltx, 73, ti, "The Square Grid Trap", "#ffffff", "700")
    body += t.run(ltx + width("The Square Grid Trap", ti) + 8, 73, lb, "// +41% corner stretch", "#ff0000", "600")
    body += t.run(ltx, 94, bd, "Corners sit 41% farther out than the sides,", "#d4d4d8", "400")
    body += t.run(ltx, 112, bd, "skewing visibility toward distant corners and", "#a1a1aa", "400")
    body += t.run(ltx, 130, bd, "cutting off every competitor ranked 21 to 30.", "#a1a1aa", "400")

    # Right chamber: True Circular Lattice
    rx0 = x1 - box_w
    body += f'  <rect x="{rx0}" y="52" width="{box_w}" height="{box_h}" rx="3" fill="#0c0507" {RED_HAIR}/>\n'
    rcx, rcy = rx0 + 44, 98
    for rr, op in ((26, "0.65"), (17, "0.45"), (8.5, "0.35")):
        body += f'  <circle cx="{rcx}" cy="{rcy}" r="{rr}" fill="none" stroke="#ff0000" stroke-opacity="{op}" stroke-width="1"/>\n'
    # Cardinal and diagonal pins strictly inside the circle
    for ang_deg in range(0, 360, 45):
        ang = math.radians(ang_deg)
        px, py = rcx + 17 * math.cos(ang), rcy + 17 * math.sin(ang)
        body += f'  <polygon points="{octagon_pts(px, py, 2.5)}" fill="#ffffff" opacity="0.85"/>\n'
    body += f'  <polygon points="{octagon_pts(rcx, rcy, 4.2)}" fill="#ff0000"/>\n'

    rtx = rx0 + 84
    body += t.run(rtx, 73, ti, "True Circular Lattice", "#ffffff", "700")
    body += t.run(rtx + width("True Circular Lattice", ti) + 8, 73, lb, "// legends-geogrid", "#ff0000", "600")
    rlines = (
        ("Uniform distance rings clipped to a circle", "#d4d4d8"),
        ("at depth 30, with open search by default", "#a1a1aa"),
        ("and straight-edge diagnostics built in.", "#a1a1aa"),
    )
    for j, (rln, rcol) in enumerate(rlines):
        assert rtx + width(rln, bd) <= rx0 + box_w - 12, f"Right chamber line overflows: {rln}"
        body += t.run(rtx, 94 + 18 * j, bd, rln, rcol, "400")

    # Bottom bar with all 7 interactive & print views
    body += f'  <line x1="{x0}" y1="156" x2="{x1}" y2="156" {HAIR}/>\n'
    chip_top = 170
    base = chip_top + 13.5
    views = (
        ("01", "Local Leaders"),
        ("02", "Rankings"),
        ("03", "Campaigns"),
        ("04", "Signage Audit"),
        ("05", "Strategy Room"),
        ("06", "Lightbox"),
        ("07", "PDF Report"),
    )
    total_slots = len(views)
    slot_gap = 8
    slot_w = (x1 - x0 - (total_slots - 1) * slot_gap) / total_slots
    for idx, (num, vname) in enumerate(views):
        px = x0 + idx * (slot_w + slot_gap)
        body += f'  <rect x="{px:.2f}" y="{chip_top}" width="{slot_w:.2f}" height="21" rx="3" {CHIP}/>\n'
        label_markup = f'<tspan fill="#ff0000">{num}</tspan> {vname}'
        body += t.run(px + slot_w / 2, base, lb, label_markup, "#ffffff", "600", "middle")

    (CARDS_DIR / "slot-4-circular-vs-square.svg").write_text(svg(f"0 0 886 {h}", body, t), encoding="utf-8")


def render_slot_5() -> None:
    """Slot 5: Comparison table ('Monthly local rank SaaS' vs 'Your own territory engine // legends-geogrid')."""
    t = Typesetter()
    ti, lb = u("title", K_WIDE), u("label", K_WIDE)
    rows = [
        ("Grid geometry &amp; depth", "Square grid (+41% corners), stops at rank 20", "True circular lattice captured 30 results deep"),
        ("Search window accuracy", "Restricted viewport clips real competitors", "Open search by default + straight-edge diagnostic"),
        ("Competitor name checks", "Manual eyeballing or blind keyword flags", "Website brand + 3 Street View angles + sign OCR"),
        ("Data cost &amp; ownership", "Recurring SaaS subscription &amp; locked exports", "Wholesale DataForSEO rates (~$0.74 to $3.00) on disk"),
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
