"""30-layer vector hypsometric topography, coastline clipping, and local leaders PDF renderer for hex_radius studies."""
from __future__ import annotations

import math
import zlib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

HEX_LEVELS = 30
HEX_MISSING_RANK = 31.0
HEX_SENTINEL = 99.0
HEX_MAX_MESH_RINGS = 28
MILE_KM = 1.609344

PAGE1_HEX = (
    "#00ffff", "#00f7d4", "#00ee9b", "#1ce668", "#4be038",
    "#78da18", "#a3d40a", "#c9cc06", "#e6c20a", "#facc15",
)
PAGE2_HEX = (
    "#f97316", "#f2601d", "#eb4d24", "#e33b2b", "#dc2b2e",
    "#cc242b", "#bc1f28", "#ac1b25", "#9c1722", "#8c1520",
)
PAGE3_HEX = (
    "#7f1d28", "#751b2a", "#6b192b", "#61172b", "#57162a",
    "#4e1529", "#451427", "#3c1324", "#341221", "#2c111e",
)

LEADER_PALETTE = (
    "#00e5ff", "#22c55e", "#f59e0b", "#a855f7", "#ec4899",
    "#38bdf8", "#84cc16", "#fb923c", "#14b8a6", "#f43f5e",
    "#eab308", "#6366f1", "#10b981", "#f97316", "#06b6d4",
)
TARGET_CRIMSON = "#e3232d"

_AXIAL_NB = ((1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1))
_SAFE_FALLBACK = ([1.0, 0.5, 0.0], [0.0, math.sqrt(3.0) / 2.0, 0.0])


def _is_axial(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _finite(*vals: Any) -> bool:
    for v in vals:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            return False
    return True


def hex_rgb(value: str) -> tuple[float, float, float]:
    n = int(value.lstrip("#"), 16)
    return ((n >> 16) & 255) / 255.0, ((n >> 8) & 255) / 255.0, (n & 255) / 255.0


def band_rgb(k: int) -> tuple[float, float, float] | None:
    if 1 <= k <= 10:
        return hex_rgb(PAGE1_HEX[k - 1])
    if 11 <= k <= 20:
        return hex_rgb(PAGE2_HEX[k - 11])
    if 21 <= k <= 30:
        return hex_rgb(PAGE3_HEX[k - 21])
    return None


def band_alpha(k: int) -> float:
    if 1 <= k <= 10:
        t = (k - 1) / 9.0
        return 0.34 - t * 0.15
    if 11 <= k <= 20:
        t = (k - 11) / 9.0
        return 0.18 - t * 0.08
    if 21 <= k <= 30:
        t = (k - 21) / 9.0
        return 0.10 - t * 0.065
    return 0.0


@dataclass(frozen=True)
class MajorContour:
    level: float
    rgb: tuple[float, float, float]
    width: float
    dash: tuple[int, int] | None
    label: str


MAJORS: tuple[MajorContour, ...] = (
    MajorContour(30.5, hex_rgb("#991b1b"), 1.2, (2, 5), "Page 3 (21-30)"),
    MajorContour(20.5, hex_rgb("#ef4444"), 1.5, (5, 5), "Page 2 (11-20)"),
    MajorContour(10.5, hex_rgb("#facc15"), 1.9, (8, 5), "Page 1 (1-10)"),
    MajorContour(3.5, hex_rgb("#00ff8e"), 2.1, None, "3-Pack"),
    MajorContour(1.5, hex_rgb("#00ffff"), 2.4, None, "#1 Crown"),
)
_MAJOR_LEVELS = {m.level for m in MAJORS}


@dataclass
class MeshNode:
    i: int
    q: int
    r: int
    ring: int
    x: float
    y: float
    real: bool
    value: float | None = None
    nb: list[int] = field(default_factory=list)


@dataclass
class HexTopoMesh:
    nodes: list[MeshNode]
    tris: list[tuple[int, int, int]]
    rings: int


def _hex_dist(q: int, r: int) -> int:
    return max(abs(q), abs(r), abs(q + r))


def _nudge(x: float) -> float:
    f = x - math.floor(x)
    return x + 1e-3 if abs(f - 0.5) < 1e-6 else x


def _solve3(a: list[list[float]], b: list[float]) -> list[float] | None:
    def det(m: list[list[float]]) -> float:
        return (
            m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
        )

    d = det(a)
    if not math.isfinite(d) or abs(d) <= 1e-9:
        return None
    out = []
    for c in range(3):
        m = [row[:] for row in a]
        for i in range(3):
            m[i][c] = b[i]
        out.append(det(m) / d)
    return out if all(math.isfinite(v) for v in out) else None


def _fit_affine(samples: list[tuple[int, int, float, float]]) -> tuple[list[float], list[float]] | None:
    valid = [(q, r, x, y) for q, r, x, y in samples if _is_axial(q) and _is_axial(r) and _finite(x, y)]
    if len(valid) < 3:
        return None
    a = [[0.0] * 3 for _ in range(3)]
    bx = [0.0] * 3
    by = [0.0] * 3
    for q, r, x, y in valid:
        v = (float(q), float(r), 1.0)
        for i in range(3):
            for j in range(3):
                a[i][j] += v[i] * v[j]
            bx[i] += v[i] * x
            by[i] += v[i] * y
    cx, cy = _solve3(a, bx), _solve3(a, by)
    return (cx, cy) if cx is not None and cy is not None else None


def axial_from_offset(dx_km: float, dy_km: float, step_km: float) -> tuple[int, int]:
    if not (_finite(dx_km, dy_km, step_km) and step_km > 0):
        return 0, 0
    rf = dy_km / (step_km * math.sqrt(3.0) / 2.0)
    qf = dx_km / step_km - 0.5 * rf
    sf = -qf - rf
    q, r, s = round(qf), round(rf), round(sf)
    dq, dr, ds = abs(q - qf), abs(r - rf), abs(s - sf)
    if dq > dr and dq > ds:
        q = -r - s
    elif dr > ds:
        r = -q - s
    return int(q), int(r)


def build_hex_topo_mesh(
    samples: list[dict[str, Any]],
    fallback: tuple[list[float], list[float]],
    max_rings: int = HEX_MAX_MESH_RINGS,
) -> HexTopoMesh:
    """Build axial hex mesh (1..30 rank field) with water-gap diffusion and sentinel rim."""
    cap = max(1, min(HEX_MAX_MESH_RINGS, max_rings if _is_axial(max_rings) else HEX_MAX_MESH_RINGS))
    real = [
        s for s in samples
        if _is_axial(s.get("q")) and _is_axial(s.get("r")) and _hex_dist(s["q"], s["r"]) <= cap
    ]
    fit = [(s["q"], s["r"], float(s["x"]), float(s["y"])) for s in real if _finite(s.get("x"), s.get("y"))]
    aff = _fit_affine(fit) or fallback or _SAFE_FALLBACK
    rings = max(1, min(cap, max([_hex_dist(s["q"], s["r"]) for s in real] or [1])))

    by_key: dict[tuple[int, int], MeshNode] = {}
    nodes: list[MeshNode] = []
    ax, ay = aff
    for q in range(-(rings + 2), rings + 3):
        for r in range(-(rings + 2), rings + 3):
            d = _hex_dist(q, r)
            if d > rings + 2:
                continue
            nx = ax[0] * q + ax[1] * r + ax[2]
            ny = ay[0] * q + ay[1] * r + ay[2]
            node = MeshNode(len(nodes), q, r, d, nx, ny, d <= rings)
            by_key[(q, r)] = node
            nodes.append(node)

    known: set[int] = set()
    for s in real:
        node = by_key.get((s["q"], s["r"]))
        if node is None:
            continue
        if _finite(s.get("x"), s.get("y")):
            node.x, node.y = float(s["x"]), float(s["y"])
        val = s.get("value")
        if _finite(val):
            node.value = _nudge(float(val))
            known.add(node.i)

    for node in nodes:
        for dq, dr in _AXIAL_NB:
            m = by_key.get((node.q + dq, node.r + dr))
            if m is not None:
                node.nb.append(m.i)

    # Propagate coastal / water-clipped gap nodes smoothly outward so contours reach the true coastline clip cleanly.
    filled = set(known)
    for _ in range(3):
        updates: list[tuple[MeshNode, float]] = []
        for node in nodes:
            if node.ring <= rings and node.i not in filled:
                vals = [nodes[j].value for j in node.nb if j in filled and nodes[j].value is not None]
                if vals:
                    updates.append((node, _nudge(sum(vals) / len(vals))))
        if not updates:
            break
        for node, val in updates:
            node.value = val
            filled.add(node.i)
    for node in nodes:
        if node.ring <= rings and node.value is None:
            node.value = HEX_MISSING_RANK

    for node in nodes:
        if node.ring == rings + 1:
            vals = [nodes[j].value for j in node.nb if nodes[j].ring == rings and nodes[j].value is not None]
            node.value = _nudge(sum(vals) / len(vals)) if vals else HEX_MISSING_RANK
        elif node.ring == rings + 2:
            node.value = HEX_SENTINEL

    tris: list[tuple[int, int, int]] = []
    for node in nodes:
        a = by_key.get((node.q + 1, node.r))
        b = by_key.get((node.q, node.r + 1))
        c = by_key.get((node.q + 1, node.r - 1))
        if a is not None and b is not None:
            tris.append((node.i, a.i, b.i))
        if a is not None and c is not None:
            tris.append((node.i, c.i, a.i))
    return HexTopoMesh(nodes, tris, rings)


def march_hex_contours(mesh: HexTopoMesh, level: float) -> list[list[tuple[float, float]]]:
    nodes = mesh.nodes
    segs: list[tuple[tuple[str, float, float], tuple[str, float, float]]] = []
    adj: dict[str, list[int]] = {}

    def cross(a: int, b: int) -> tuple[str, float, float]:
        if a > b:
            a, b = b, a
        va, vb = nodes[a].value, nodes[b].value
        denom = (vb - va) if (vb is not None and va is not None and vb != va) else 1e-9
        t = (level - (va or 0.0)) / denom
        na, nb_ = nodes[a], nodes[b]
        return f"{a}_{b}", na.x + (nb_.x - na.x) * t, na.y + (nb_.y - na.y) * t

    for a, b, c in mesh.tris:
        ia = (nodes[a].value or HEX_SENTINEL) < level
        ib = (nodes[b].value or HEX_SENTINEL) < level
        ic = (nodes[c].value or HEX_SENTINEL) < level
        if ia == ib == ic:
            continue
        ps = []
        if ia != ib:
            ps.append(cross(a, b))
        if ib != ic:
            ps.append(cross(b, c))
        if ic != ia:
            ps.append(cross(c, a))
        if len(ps) == 2:
            idx = len(segs)
            segs.append((ps[0], ps[1]))
            adj.setdefault(ps[0][0], []).append(idx)
            adj.setdefault(ps[1][0], []).append(idx)

    used = [False] * len(segs)
    loops: list[list[tuple[float, float]]] = []
    for s0 in range(len(segs)):
        if used[s0]:
            continue
        used[s0] = True
        loop = [segs[s0][0], segs[s0][1]]
        start, cur = segs[s0][0][0], segs[s0][1][0]
        guard = 0
        while cur != start and guard < 200000:
            guard += 1
            nxt = next((c for c in adj.get(cur, []) if not used[c]), -1)
            if nxt < 0:
                break
            used[nxt] = True
            sg = segs[nxt]
            other = sg[1] if sg[0][0] == cur else sg[0]
            loop.append(other)
            cur = other[0]
        if len(loop) > 2 and loop[-1][0] == start:
            loop.pop()
        loops.append([(p[1], p[2]) for p in loop])
    return loops


def chaikin_smooth(loop: list[tuple[float, float]], iterations: int = 2) -> list[tuple[float, float]]:
    for _ in range(iterations):
        n = len(loop)
        if n < 3:
            return loop
        out: list[tuple[float, float]] = []
        for i in range(n):
            (px, py), (qx, qy) = loop[i], loop[(i + 1) % n]
            out.append((px * 0.75 + qx * 0.25, py * 0.75 + qy * 0.25))
            out.append((px * 0.25 + qx * 0.75, py * 0.25 + qy * 0.75))
        loop = out
    return loop


def _loops_path(loops: list[list[tuple[float, float]]]) -> str:
    parts = []
    for loop in loops:
        if len(loop) < 3 or not all(_finite(x, y) for x, y in loop):
            continue
        pts = [f"{x:.2f} {y:.2f} {'m' if i == 0 else 'l'}" for i, (x, y) in enumerate(loop)]
        parts.append(" ".join(pts) + " h")
    return " ".join(parts)


def circle_path(cx: float, cy: float, r: float) -> str:
    k = 0.5523 * r
    return (
        f"{cx + r:.2f} {cy:.2f} m "
        f"{cx + r:.2f} {cy + k:.2f} {cx + k:.2f} {cy + r:.2f} {cx:.2f} {cy + r:.2f} c "
        f"{cx - k:.2f} {cy + r:.2f} {cx - r:.2f} {cy + k:.2f} {cx - r:.2f} {cy:.2f} c "
        f"{cx - r:.2f} {cy - k:.2f} {cx - k:.2f} {cy - r:.2f} {cx:.2f} {cy - r:.2f} c "
        f"{cx + k:.2f} {cy - r:.2f} {cx + r:.2f} {cy - k:.2f} {cx + r:.2f} {cy:.2f} c h"
    )


def coastline_clip_path(
    land_mask_polygons: list[dict[str, Any]] | None,
    project_fn: Callable[[float, float], tuple[float, float]],
) -> str:
    """Build a single PDF even-odd subpath string from real coastline landMaskPolygons."""
    if not land_mask_polygons:
        return ""
    parts: list[str] = []
    for poly in land_mask_polygons:
        if not isinstance(poly, dict):
            continue
        rings = []
        outer = poly.get("outer")
        if isinstance(outer, list) and len(outer) >= 3:
            rings.append(outer)
        for hole in poly.get("holes") or []:
            if isinstance(hole, list) and len(hole) >= 3:
                rings.append(hole)
        for ring in rings:
            coords = []
            for pair in ring:
                if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                    continue
                lng, lat = pair[0], pair[1]
                if not _finite(lat, lng):
                    continue
                px, py = project_fn(float(lat), float(lng))
                if _finite(px, py):
                    coords.append((px, py))
            if len(coords) >= 3:
                pts = [f"{x:.2f} {y:.2f} {'m' if i == 0 else 'l'}" for i, (x, y) in enumerate(coords)]
                parts.append(" ".join(pts) + " h")
    return " ".join(parts)


def _pdf_escape(text: str) -> str:
    safe = text.encode("ascii", "replace").decode("ascii")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _extgstate_dict() -> str:
    parts = [f"/GT{k} << /CA {band_alpha(k):.3f} /ca {band_alpha(k):.3f} >>" for k in range(1, HEX_LEVELS + 1)]
    parts.append("/GTh << /CA 0.44 /ca 0.44 >>")
    parts.append("/GTk << /CA 0.68 /ca 0.68 >>")
    parts.append("/GTC << /CA 0.38 /ca 0.38 >>")
    parts.append("/GTL << /CA 0.24 /ca 0.24 >>")
    parts.append("/GTLb << /CA 0.85 /ca 0.85 >>")
    parts.append("/GTR << /CA 0.35 /ca 0.35 >>")
    return "<< " + " ".join(parts) + " >>"


def _mercator_y(lat: float) -> float:
    clamped = max(-85.05112878, min(85.05112878, lat))
    return math.log(math.tan(math.pi / 4.0 + math.radians(clamped) / 2.0))


def _make_circle_projector(
    anchor_lat: float,
    anchor_lng: float,
    radius_km: float,
    cx: float,
    cy: float,
    plot_r: float,
) -> Callable[[float, float], tuple[float, float]]:
    """North-up Web Mercator projector centered dead-on (anchor_lat, anchor_lng) at radius_km -> plot_r."""
    rad = math.pi / 180.0
    cos_lat = math.cos(anchor_lat * rad)
    # Meters per Mercator radian at anchor_lat = 6371.0088 km * cos(lat)
    merc_r = radius_km / (6371.0088 * max(1e-6, cos_lat))
    scale = plot_r / merc_r
    x0 = anchor_lng * rad
    y0 = _mercator_y(anchor_lat)

    def project_pt(lat: float, lng: float) -> tuple[float, float]:
        px = cx + (lng * rad - x0) * scale
        py = cy + (_mercator_y(lat) - y0) * scale
        return px, py

    return project_pt


def _star_path(cx: float, cy: float, outer_r: float, inner_r: float | None = None, points: int = 6) -> str:
    if inner_r is None:
        inner_r = outer_r * 0.36 if points == 6 else outer_r * 0.5
    verts = []
    for i in range(points * 2):
        angle = math.radians(0.0 + i * (180.0 / points))
        r = outer_r if i % 2 == 0 else inner_r
        verts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return " ".join(f"{x:.2f} {y:.2f} {'m' if i == 0 else 'l'}" for i, (x, y) in enumerate(verts)) + " h"


def _hex_cell_path(cx: float, cy: float, r: float) -> str:
    verts = [
        (cx + r * math.cos(math.radians(30 + 60 * i)), cy + r * math.sin(math.radians(30 + 60 * i)))
        for i in range(6)
    ]
    return " ".join(f"{x:.2f} {y:.2f} {'m' if i == 0 else 'l'}" for i, (x, y) in enumerate(verts)) + " h"


def _page_chrome(title: str, subtitle: str, page_num: int, total_pages: int) -> list[str]:
    ops = [
        "0.031 0.031 0.035 rg 0 0 612 792 re f",
        "0.890 0.137 0.176 rg 40 742 532 2.5 re f",
        f"BT 0.945 0.945 0.945 rg /F2 17 Tf 40 755 Td ({_pdf_escape(title)}) Tj ET",
        f"BT 0.620 0.620 0.620 rg /F1 8.5 Tf 40 726 Td ({_pdf_escape(subtitle)}) Tj ET",
        "0.200 0.200 0.220 RG 0.6 w 40 42 m 572 42 l S",
        "BT 0.520 0.520 0.540 rg /F1 7.5 Tf 40 28 Td (legends-geogrid v0.3.1 | vector 30-layer topography & real coastline clipping | observational evidence) Tj ET",
        f"BT 0.680 0.680 0.700 rg /F2 8 Tf 525 28 Td (Page {page_num} / {total_pages}) Tj ET",
    ]
    return ops


def _topo_map_ops(
    mesh: HexTopoMesh,
    cx: float,
    cy: float,
    plot_r: float,
    coast_path: str,
    radius_miles: float,
) -> list[str]:
    paths = {k: _loops_path([chaikin_smooth(loop, 2) for loop in march_hex_contours(mesh, k + 0.5)]) for k in range(0, HEX_LEVELS + 1)}
    ops = [
        # Deep noir ocean / chart disk
        f"0.055 0.063 0.078 rg {circle_path(cx, cy, plot_r)} f",
        f"q {circle_path(cx, cy, plot_r)} W n",
    ]
    if coast_path:
        # Subtle dry-land base fill inside the circle so Biscayne Bay / ocean stays unmistakably distinct
        ops.append(f"0.095 0.098 0.105 rg {coast_path} f*")
        ops.append(f"q {coast_path} W* n")

    # 30 non-overlapping hypsometric elevation bands (even-odd outer \ inner)
    for k in range(HEX_LEVELS, 0, -1):
        if not paths[k]:
            continue
        rgb = band_rgb(k)
        assert rgb is not None
        inner = paths[k - 1]
        ops.append(f"q /GT{k} gs {rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} rg {paths[k]} {inner} f* Q".replace("  ", " "))

    # Fine 1-rank hairlines
    ops.append("q /GTh gs 1 J 1 j")
    for k in range(1, HEX_LEVELS):
        if not paths[k] or (k + 0.5) in _MAJOR_LEVELS:
            continue
        rgb = band_rgb(k)
        assert rgb is not None
        w = 0.70 if k <= 10 else (0.58 if k <= 20 else 0.45)
        ops.append(f"{rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} RG {w:.2f} w {paths[k]} S")
    ops.append("Q")

    # Bold halo-backed major index contours (#1, 3-Pack, Page 1, Page 2, Page 3)
    for m in MAJORS:
        d = paths[int(m.level - 0.5)]
        if not d:
            continue
        dash = f"[{m.dash[0]} {m.dash[1]}] 0 d" if m.dash else "[] 0 d"
        ops.append(f"q /GTk gs 0 0 0 RG {m.width + 2.0:.1f} w 1 j {dash} {d} S Q")
        ops.append(f"q 1 j {m.rgb[0]:.3f} {m.rgb[1]:.3f} {m.rgb[2]:.3f} RG {m.width:.1f} w {dash} {d} S Q")

    if coast_path:
        ops.append("Q")
        # Crisp coastal hairline inside study circle
        ops.append(f"q /GTC gs 0.490 0.827 0.988 RG 0.95 w 1 j {coast_path} S Q")

    ops.append("Q")  # release study circle clip

    # Concentric mile rings & outer study circle border
    ring_steps = [r for r in (1, 2, 5, 10, 15, 20) if r < radius_miles - 0.15]
    ops.append("q /GTR gs 0.78 0.78 0.80 RG 0.65 w")
    for rm in ring_steps:
        rr = plot_r * (rm / max(0.1, radius_miles))
        ops.append(f"{circle_path(cx, cy, rr)} S")
        lx = cx + rr * 0.7071
        ly = cy + rr * 0.7071
        ops.append(f"BT 0.76 0.76 0.78 rg /F1 6.8 Tf {lx + 3:.2f} {ly + 2:.2f} Td ({rm} mi) Tj ET")
    ops.append("Q")
    ops.append(f"q 0.62 0.62 0.64 RG 1.0 w [4 5] 0 d {circle_path(cx, cy, plot_r)} S Q")

    # Dead-center target business star marker (regular pointy-top 6-pointed hexagram)
    ops.append(f"0.02 0.02 0.03 rg 0.00 1.00 1.00 RG 1.1 w {_star_path(cx, cy, 8.5)} B")
    return ops


def _leaders_map_ops(
    points: list[dict[str, Any]],
    lane_id: str,
    target_cid: str,
    project_fn: Callable[[float, float], tuple[float, float]],
    cx: float,
    cy: float,
    plot_r: float,
    coast_path: str,
    step_px: float,
    radius_miles: float,
) -> tuple[list[str], list[tuple[str, str, int, str]]]:
    """Render vector Local Leaders territories + contested borders clipped to circle ∩ coastline."""
    wins: Counter[str] = Counter()
    names: dict[str, str] = {}
    point_winners: dict[tuple[int, int], tuple[str, float, float, dict[str, int]]] = {}

    for pt in points:
        obs = (pt.get("by_lane") or {}).get(lane_id) or {}
        items = obs.get("top_items") or []
        top1 = next((it for it in items if (it.get("rank") or it.get("rank_group")) == 1), None)
        if not top1:
            continue
        cid = str(top1.get("cid") or top1.get("faction_id") or "")
        if not cid:
            continue
        wins[cid] += 1
        names.setdefault(cid, str(top1.get("title") or top1.get("name") or cid))
        px, py = project_fn(float(pt["lat"]), float(pt["lng"]))
        hx = pt.get("hex") or {}
        q = hx.get("unit_q") if _is_axial(hx.get("unit_q")) else hx.get("q")
        r = hx.get("unit_r") if _is_axial(hx.get("unit_r")) else hx.get("r")
        ranks_by_cid = {
            str(it.get("cid") or it.get("faction_id") or ""): int(it.get("rank") or it.get("rank_group"))
            for it in items
            if _is_axial(it.get("rank") or it.get("rank_group"))
        }
        if _is_axial(q) and _is_axial(r):
            point_winners[(q, r)] = (cid, px, py, ranks_by_cid)

    ranked_cids = [cid for cid, _ in wins.most_common()]
    color_map: dict[str, str] = {}
    pal_idx = 0
    for cid in ranked_cids:
        if cid == target_cid:
            color_map[cid] = TARGET_CRIMSON
        else:
            color_map[cid] = LEADER_PALETTE[pal_idx % len(LEADER_PALETTE)]
            pal_idx += 1

    cell_r = max(3.5, step_px * 0.59)
    ops = [
        f"0.055 0.063 0.078 rg {circle_path(cx, cy, plot_r)} f",
        f"q {circle_path(cx, cy, plot_r)} W n",
    ]
    if coast_path:
        ops.append(f"0.095 0.098 0.105 rg {coast_path} f*")
        ops.append(f"q {coast_path} W* n")

    # Fill hex territory cells per #1 leader
    for (q, r), (cid, px, py, _) in point_winners.items():
        rgb = hex_rgb(color_map[cid])
        ops.append(f"q /GTL gs {rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} rg {_hex_cell_path(px, py, cell_r)} f Q")

    # Draw borders between unlike #1 leaders; highlight contested seams (runner-up at rank 2) in crisp white
    contested_count = 0
    for (q, r), (cid_a, ax, ay, ranks_a) in point_winners.items():
        for dq, dr in ((1, 0), (0, 1), (-1, 1)):
            nb = point_winners.get((q + dq, r + dr))
            if not nb or nb[0] == cid_a:
                continue
            cid_b, bx, by, ranks_b = nb
            mx, my = (ax + bx) * 0.5, (ay + by) * 0.5
            dx, dy = bx - ax, by - ay
            seg_len = math.hypot(dx, dy)
            if seg_len < 1e-4:
                continue
            nx, ny = -dy / seg_len, dx / seg_len
            half_e = cell_r * 0.52
            x1, y1 = mx - nx * half_e, my - ny * half_e
            x2, y2 = mx + nx * half_e, my + ny * half_e
            rank_b_at_a = ranks_a.get(cid_b)
            rank_a_at_b = ranks_b.get(cid_a)
            tight = (rank_b_at_a == 2) or (rank_a_at_b == 2)
            if tight:
                contested_count += 1
                ops.append(f"q 1.0 0.96 0.85 RG 1.45 w [2.5 2] 0 d {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S Q")
            else:
                rgb_a = hex_rgb(color_map[cid_a])
                ops.append(f"q /GTLb gs {rgb_a[0]:.3f} {rgb_a[1]:.3f} {rgb_a[2]:.3f} RG 1.1 w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S Q")

    if coast_path:
        ops.append("Q")
        ops.append(f"q /GTC gs 0.490 0.827 0.988 RG 0.95 w 1 j {coast_path} S Q")
    ops.append("Q")

    ops.append(f"q 0.62 0.62 0.64 RG 1.0 w [4 5] 0 d {circle_path(cx, cy, plot_r)} S Q")
    ops.append(f"0.02 0.02 0.03 rg 1 1 1 RG 1.2 w {_star_path(cx, cy, 8.0)} B")
    ops.append(
        f"BT 0.72 0.72 0.75 rg /F1 8 Tf 40 164 Td (Contested borders detected on {contested_count} head-to-head hex seams where #2 sits one rank from flipping.) Tj ET"
    )

    legend_rows = [
        (cid, names[cid], wins[cid], color_map[cid])
        for cid in ranked_cids[:10]
    ]
    return ops, legend_rows


def _assemble_pdf(page_streams: list[str]) -> bytes:
    """Assemble a standards-compliant multi-page PDF 1.4 with Flate-compressed vector streams."""
    objects: list[bytes] = []

    def add_obj(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    f1_id = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    f2_id = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    gs_id = add_obj(_extgstate_dict().encode("ascii"))
    pages_placeholder_id = add_obj(b"")  # filled after page creation

    page_ids: list[int] = []
    for stream_text in page_streams:
        raw = stream_text.encode("latin-1", "replace")
        comp = zlib.compress(raw, 6)
        content_id = add_obj(
            f"<< /Length {len(comp)} /Filter /FlateDecode >>\nstream\n".encode("ascii")
            + comp
            + b"\nendstream"
        )
        page_dict = (
            f"<< /Type /Page /Parent {pages_placeholder_id} 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {f1_id} 0 R /F2 {f2_id} 0 R >> /ExtGState {gs_id} 0 R >> "
            f"/Contents {content_id} 0 R >>"
        ).encode("ascii")
        page_ids.append(add_obj(page_dict))

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[pages_placeholder_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")
    catalog_id = add_obj(f"<< /Type /Catalog /Pages {pages_placeholder_id} 0 R >>".encode("ascii"))

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{idx} 0 obj\n".encode("ascii"))
        out.extend(obj)
        out.extend(b"\nendobj\n")

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    return bytes(out)


def build_hex_pdf(
    study_or_path: dict[str, Any] | str | Path,
    output_pdf: str | Path,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Render a multi-page vector 30-layer topography + coastline + local leaders PDF from a hex_radius study."""
    import json
    from local_heatmap_poc import _safe_local_path

    if isinstance(study_or_path, (str, Path)):
        src_path = _safe_local_path(study_or_path).resolve()
        if not src_path.is_file():
            raise ValueError(f"Study file does not exist: {src_path}")
        study = json.loads(src_path.read_text(encoding="utf-8-sig"))
    elif isinstance(study_or_path, dict):
        study = study_or_path
    else:
        raise ValueError("study_or_path must be a file path or study dict")

    out_path = _safe_local_path(output_pdf).resolve()
    if out_path.exists() and not overwrite:
        raise ValueError("Output PDF already exists; choose a fresh path or pass overwrite=True")

    study_meta = study.get("study") or {}
    sampling = study_meta.get("sampling") or {}
    geometry = study_meta.get("geometry") or sampling.get("geometry")
    if geometry != "hex_radius":
        raise ValueError(f"build_hex_pdf requires geometry='hex_radius', got {geometry!r}")

    points = study.get("points") or []
    lanes = study.get("lanes") or []
    if not points or not lanes:
        raise ValueError("hex_radius study requires non-empty points and lanes")

    target = study.get("target") or {}
    business = study.get("business") or {}
    biz_name = str(business.get("name") or target.get("name") or "Target Business")
    location = str(study.get("location") or "")
    target_cid = str(target.get("cid") or business.get("cid") or "")

    center = sampling.get("center") or target
    anchor_lat = float(center["lat"])
    anchor_lng = float(center["lng"])
    radius_km = float(sampling.get("radius_km") or 0.0)
    spacing_km = float(sampling.get("spacing_km") or 0.0)
    if not (_finite(anchor_lat, anchor_lng, radius_km, spacing_km) and radius_km > 0 and spacing_km > 0):
        raise ValueError("hex_radius study requires finite anchor coordinates, radius_km, and spacing_km")

    radius_miles = radius_km / MILE_KM
    step = int((sampling.get("hex") or {}).get("step") or 1)
    land_polys = study.get("land_mask_polygons") or study.get("landMaskPolygons") or study_meta.get("land_mask_polygons") or []

    total_pages = 1 + len(lanes) + 1
    page_streams: list[str] = []

    # Page 1: Executive Summary
    p1 = _page_chrome(
        biz_name,
        f"{location} | 7-stage honeycomb visibility & 30-layer topographic report",
        1,
        total_pages,
    )
    p1.append(
        f"BT 0.88 0.88 0.90 rg /F2 11 Tf 40 694 Td (Study Footprint & Coastline Geometry) Tj ET"
    )
    p1.append(
        f"BT 0.72 0.72 0.75 rg /F1 9.5 Tf 40 676 Td (Radius: {radius_miles:.2f} mi ({radius_km:.2f} km) | Hex spacing: {spacing_km / MILE_KM:.2f} mi | Dry-land origins: {len(points)} | Land polygons: {len(land_polys)}) Tj ET"
    )
    p1.append(
        "BT 0.88 0.88 0.90 rg /F2 11 Tf 40 640 Td (Visibility Summary by Query (Depth 30)) Tj ET"
    )
    p1.append("0.14 0.14 0.16 rg 40 612 532 20 re f")
    p1.append("BT 0.92 0.92 0.94 rg /F2 8.5 Tf 48 619 Td (Query) Tj 210 0 Td (#1 Wins) Tj 68 0 Td (Top 3) Tj 72 0 Td (Top 10) Tj 72 0 Td (Top 30) Tj ET")

    y_row = 594
    for lane in lanes:
        lid = lane["lane_id"]
        qname = str(lane.get("query") or lid)
        t1 = t3 = t10 = t30 = 0
        for pt in points:
            rk = ((pt.get("by_lane") or {}).get(lid) or {}).get("target_rank")
            if _is_axial(rk) and rk >= 1:
                if rk == 1:
                    t1 += 1
                if rk <= 3:
                    t3 += 1
                if rk <= 10:
                    t10 += 1
                if rk <= 30:
                    t30 += 1
        p1.append(f"0.22 0.22 0.24 RG 0.5 w 40 {y_row - 6} m 572 {y_row - 6} l S")
        p1.append(
            f"BT 0.90 0.90 0.92 rg /F1 9 Tf 48 {y_row} Td ({_pdf_escape(qname[:34])}) Tj "
            f"210 0 Td ({t1}) Tj 68 0 Td ({t3} ({100.0 * t3 / len(points):.1f}%)) Tj "
            f"72 0 Td ({t10} ({100.0 * t10 / len(points):.1f}%)) Tj 72 0 Td ({t30} ({100.0 * t30 / len(points):.1f}%)) Tj ET"
        )
        y_row -= 22

    p1.append("BT 0.88 0.88 0.90 rg /F2 11 Tf 40 480 Td (How to Read the 30-Layer Topographic Contour Maps) Tj ET")
    guide_lines = [
        "1. Every single Google Maps rank (1 through 30) draws its own smooth topographic elevation band.",
        "2. Tightly packed contour lines indicate steep rank cliffs; wide plateaus show stable territory.",
        "3. Bold index contours mark #1 Crown (Cyan), 3-Pack (Emerald), Page 1 (Gold), Page 2 (Red), Page 3 (Burgundy).",
        "4. All contours and leader territories are clipped strictly to the study circle and real OSM coastline.",
    ]
    gy = 460
    for line in guide_lines:
        p1.append(f"BT 0.72 0.72 0.75 rg /F1 9 Tf 40 {gy} Td ({_pdf_escape(line)}) Tj ET")
        gy -= 16
    page_streams.append("\n".join(p1))

    # Map viewport shared across query pages & local leaders page
    map_cx, map_cy, plot_r = 306.0, 440.0, 224.0
    project_fn = _make_circle_projector(anchor_lat, anchor_lng, radius_km, map_cx, map_cy, plot_r)
    coast_path = coastline_clip_path(land_polys, project_fn)
    est_rings = max(1, min(HEX_MAX_MESH_RINGS, round(radius_km / spacing_km)))
    step_px = plot_r / float(est_rings)
    fallback_aff = ([step_px, step_px * 0.5, map_cx], [0.0, step_px * math.sqrt(3.0) / 2.0, map_cy])

    # Pages 2..N: 30-layer topographic elevation maps per query
    for idx, lane in enumerate(lanes, start=2):
        lid = lane["lane_id"]
        qname = str(lane.get("query") or lid)
        samples: list[dict[str, Any]] = []
        t1 = t3 = t10 = t30 = 0
        for pt in points:
            obs = (pt.get("by_lane") or {}).get(lid) or {}
            rk = obs.get("target_rank")
            st = obs.get("status")
            if _is_axial(rk) and 1 <= rk <= HEX_LEVELS:
                val: float | None = float(rk)
                if rk == 1:
                    t1 += 1
                if rk <= 3:
                    t3 += 1
                if rk <= 10:
                    t10 += 1
                t30 += 1
            elif st in ("not_returned_depth_reached", "found", "ok"):
                val = HEX_MISSING_RANK
            else:
                val = None

            hx = pt.get("hex") or {}
            if _is_axial(hx.get("q")) and _is_axial(hx.get("r")):
                q, r = int(hx["q"]), int(hx["r"])
            elif _is_axial(hx.get("unit_q")) and _is_axial(hx.get("unit_r")):
                q, r = int(hx["unit_q"]) // step, int(hx["unit_r"]) // step
            else:
                cos_lat = math.cos(math.radians(anchor_lat))
                dx_km = (float(pt["lng"]) - anchor_lng) * 111.195 * cos_lat
                dy_km = (float(pt["lat"]) - anchor_lat) * 111.195
                q, r = axial_from_offset(dx_km, dy_km, spacing_km)
            px, py = project_fn(float(pt["lat"]), float(pt["lng"]))
            samples.append({"q": q, "r": r, "x": px, "y": py, "value": val})

        mesh = build_hex_topo_mesh(samples, fallback_aff, max_rings=HEX_MAX_MESH_RINGS)
        ops = _page_chrome(
            f"Rank Topography: {qname}",
            f"{biz_name} | #1: {t1} | 3-Pack: {t3} | Page 1 (1-10): {t10} | Top 30: {t30} of {len(points)} dry-land pins",
            idx,
            total_pages,
        )
        ops.extend(_topo_map_ops(mesh, map_cx, map_cy, plot_r, coast_path, radius_miles))

        # Crisp bottom legend
        lx = 44.0
        for m in reversed(MAJORS):
            ops.append(f"{m.rgb[0]:.3f} {m.rgb[1]:.3f} {m.rgb[2]:.3f} rg {lx:.1f} 174 10 6 re f")
            ops.append(f"BT 0.85 0.85 0.87 rg /F1 8 Tf {lx + 14:.1f} 174 Td ({_pdf_escape(m.label)}) Tj ET")
            lx += 106.0
        ops.append(
            f"BT 0.62 0.62 0.65 rg /F1 8 Tf 44 150 Td (Centered on target star ({anchor_lat:.5f}, {anchor_lng:.5f}). Clipped to {radius_miles:.1f} mi circle and {len(land_polys)} coastline polygons.) Tj ET"
        )
        page_streams.append("\n".join(ops))

    # Final Page: Local Leaders & Contested Ground (primary query)
    lead_lane = lanes[0]
    lead_ops, legend_rows = _leaders_map_ops(
        points,
        lead_lane["lane_id"],
        target_cid,
        project_fn,
        map_cx,
        map_cy,
        plot_r,
        coast_path,
        step_px,
        radius_miles,
    )
    p_lead = _page_chrome(
        f"Local Leaders & Contested Ground: {lead_lane.get('query', lead_lane['lane_id'])}",
        f"{biz_name} | First-place territory control & one-rank flip seams",
        total_pages,
        total_pages,
    )
    p_lead.extend(lead_ops)

    # Compact two-column leader legend below map
    ly = 144.0
    for idx_l, (cid, lname, wcnt, col_hex) in enumerate(legend_rows[:8]):
        col_x = 40.0 if idx_l < 4 else 312.0
        row_y = ly - (idx_l % 4) * 18.0
        rgb = hex_rgb(col_hex)
        p_lead.append(f"{rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} rg {col_x:.1f} {row_y:.1f} 8 8 re f")
        label_txt = f"{lname[:34]} ({wcnt} #1)"
        p_lead.append(f"BT 0.86 0.86 0.88 rg /F1 8 Tf {col_x + 12:.1f} {row_y + 1:.1f} Td ({_pdf_escape(label_txt)}) Tj ET")
    page_streams.append("\n".join(p_lead))

    pdf_bytes = _assemble_pdf(page_streams)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb" if overwrite else "xb") as stream:
        stream.write(pdf_bytes)

    return {
        "status": "ok",
        "output_pdf": str(out_path),
        "pages": len(page_streams),
        "bytes": len(pdf_bytes),
        "geometry": geometry,
        "queries": [str(l.get("query") or l.get("lane_id")) for l in lanes],
        "land_mask_polygons": len(land_polys),
        "points": len(points),
    }
