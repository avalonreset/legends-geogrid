"""Offline hex_radius demo: Dough Valley plan, Voronoi viewer and PNG render.

No network, no geocoding service and no paid calls. The business coordinate
is a hardcoded approximate for 5200 Ross Rd, Del Valle TX 78617 and is
labelled approximate in every artifact.

The demo uses a continuous base spacing s0 = 2.7 miles (not a fixed rung).
The coarse pass collects at 2.7 miles; a synthetic east/west leader split
then refines only the changed cells at 1.35 miles. Cells are drawn as the
Voronoi diagram of the actual collected points, so the mixed resolution
reads naturally: uniform areas form a honeycomb and refined areas show
smaller cells. Leader labels are synthetic demo data, not measurements.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hex_sampling import hex_origins, ladder_spacings, refinement_delta, stamp_scan_dates
from study import _safe_local_path

BUSINESS = {"name": "Dough Valley (demo)", "address": "5200 Ross Rd, Del Valle TX 78617",
            "lat": 30.09, "lng": -97.55, "coordinate_note": "approximate, hardcoded for offline demo"}
RADIUS_MILES = 15.0
BASE_SPACING = 2.7
COARSE_COLOR, FINE_COLOR = "#e4572e", "#2a9d8f"


def build_demo(output_dir: Path) -> dict:
    output_dir = _safe_local_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rungs = ladder_spacings(BASE_SPACING)
    coarse_spacing, fine_spacing = rungs[0], rungs[1]
    coarse = stamp_scan_dates(
        hex_origins(BUSINESS["lat"], BUSINESS["lng"], RADIUS_MILES, coarse_spacing,
                    base_spacing=BASE_SPACING), "2026-11-20")
    observed = {p["origin_id"] for p in coarse}
    # Synthetic leaders for the demo only: west half vs east half.
    leaders = {p["origin_id"]: ("east-leader" if p["east_miles"] >= 0 else "west-leader")
               for p in coarse}
    delta = stamp_scan_dates(
        refinement_delta(BUSINESS["lat"], BUSINESS["lng"], RADIUS_MILES,
                         coarse_spacing, fine_spacing, observed,
                         base_spacing=BASE_SPACING, leaders=leaders),
        "2026-11-20", coarse_sampled_at="2026-11-20")
    collected = coarse + delta
    plan = {
        "business": BUSINESS, "geometry": "hex_radius", "radius_miles": RADIUS_MILES,
        "base_spacing_miles": BASE_SPACING, "ladder_rungs_miles": rungs,
        "coarse_points": len(coarse), "new_points_at_fine_rung": len(delta),
        "collected_points": len(collected),
        "full_fine_rung_points": len(hex_origins(BUSINESS["lat"], BUSINESS["lng"],
                                                 RADIUS_MILES, fine_spacing,
                                                 base_spacing=BASE_SPACING)),
        "leader_note": "Synthetic east/west leaders used only to show changed-cell refinement; not measurements.",
        "points": collected,
    }
    plan_path = _safe_local_path(output_dir / "hex-demo-plan.json")
    html_path = _safe_local_path(output_dir / "hex-viewer.html")
    png_path = _safe_local_path(output_dir / "hex-viewer.png")
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(viewer_html(plan), encoding="utf-8")
    render_png(plan, png_path)
    return plan


def voronoi_cells(points: list[dict], radius_miles: float) -> list[list[tuple[float, float]]]:
    """Voronoi polygons (east/north miles) clipped to a wide square.

    Display only: cells near the border are later drawn under the circular
    border. Uses scipy when available, which the demo environment has.
    """
    from scipy.spatial import Voronoi
    coords = [(p["east_miles"], p["north_miles"]) for p in points]
    # Mirror guards keep border cells finite without affecting the interior.
    guard = radius_miles * 4
    extended = coords + [(-guard, 0.0), (guard, 0.0), (0.0, -guard), (0.0, guard),
                         (-guard, -guard), (-guard, guard), (guard, -guard), (guard, guard)]
    diagram = Voronoi(extended)
    cells = []
    for index in range(len(coords)):
        region = diagram.regions[diagram.point_region[index]]
        if not region or -1 in region:
            cells.append([])
            continue
        cells.append([tuple(diagram.vertices[v]) for v in region])
    return cells


def viewer_html(plan: dict) -> str:
    data = json.dumps({"business": plan["business"], "radius": plan["radius_miles"],
                       "points": [{"east": p["east_miles"], "north": p["north_miles"],
                                   "rung": p["spacing_miles"], "id": p["origin_id"]}
                                  for p in plan["points"]]})
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Dough Valley hex_radius demo (approximate coordinate)</title>
<style>body{{font-family:system-ui,sans-serif;margin:16px}}canvas{{border:1px solid #ccc}}</style>
</head><body>
<h1>Dough Valley: hex_radius R=15 mi, s0=2.7 mi, refined at 1.35 mi where the leader changes</h1>
<p>Business coordinate is approximate (offline demo, no geocoding call). Cells are the Voronoi diagram of the collected points: orange cells were collected at 2.7 mi, teal cells are the 1.35 mi refinement in changed cells only. Leaders in this demo are synthetic. The center cell is the business.</p>
<canvas id="c" width="900" height="900"></canvas>
<script>
const data = {data};
const ctx = document.getElementById('c').getContext('2d');
const pts = data.points, R = data.radius;
const scale = 430 / (R + 1);
const X = e => 450 + e * scale, Y = n => 450 - n * scale;
function clip(poly, a, b, c) {{ // keep a*x + b*y <= c (Sutherland half-plane step)
  const out = [];
  for (let i = 0; i < poly.length; i++) {{
    const p = poly[i], q = poly[(i + 1) % poly.length];
    const dp = a * p[0] + b * p[1] - c, dq = a * q[0] + b * q[1] - c;
    if (dp <= 0) out.push(p);
    if ((dp < 0 && dq > 0) || (dp > 0 && dq < 0)) {{
      const t = dp / (dp - dq);
      out.push([p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])]);
    }}
  }}
  return out;
}}
ctx.save();
ctx.beginPath(); ctx.arc(450, 450, R * scale, 0, 7); ctx.clip();
pts.forEach((p, i) => {{
  let poly = [[-R - 2, -R - 2], [R + 2, -R - 2], [R + 2, R + 2], [-R - 2, R + 2]];
  pts.forEach((q, j) => {{
    if (i === j) return;
    poly = clip(poly, q.east - p.east, q.north - p.north,
                ((q.east ** 2 + q.north ** 2) - (p.east ** 2 + p.north ** 2)) / 2);
  }});
  if (!poly.length) return;
  ctx.beginPath();
  poly.forEach((v, k) => k ? ctx.lineTo(X(v[0]), Y(v[1])) : ctx.moveTo(X(v[0]), Y(v[1])));
  ctx.closePath();
  ctx.fillStyle = p.rung === {plan["ladder_rungs_miles"][0]} ? "#e4572e" : "#2a9d8f";
  ctx.globalAlpha = .75; ctx.fill(); ctx.globalAlpha = 1;
  ctx.strokeStyle = "#333"; ctx.stroke();
  ctx.fillStyle = "#111"; ctx.beginPath(); ctx.arc(X(p.east), Y(p.north), 2.5, 0, 7); ctx.fill();
}});
ctx.restore();
ctx.beginPath(); ctx.arc(450, 450, R * scale, 0, 7); ctx.strokeStyle = "#000"; ctx.lineWidth = 2; ctx.stroke();
ctx.fillStyle = "#000"; ctx.beginPath(); ctx.arc(450, 450, 6, 0, 7); ctx.fill();
</script></body></html>
"""


def render_png(plan: dict, path: Path) -> None:
    path = _safe_local_path(path)
    from PIL import Image, ImageDraw
    size, center = 900, 450
    img = Image.new("RGB", (size, size), "white")
    layer = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(layer)
    radius = plan["radius_miles"]
    scale = (size / 2 - 20) / (radius + 1)
    cells = voronoi_cells(plan["points"], radius)
    for point, cell in zip(plan["points"], cells):
        if not cell:
            continue
        pixels = [(center + e * scale, center - n * scale) for e, n in cell]
        fill = COARSE_COLOR if point["spacing_miles"] == plan["ladder_rungs_miles"][0] else FINE_COLOR
        draw.polygon(pixels, fill=fill, outline="#333333")
        draw.ellipse([center + point["east_miles"] * scale - 2, center - point["north_miles"] * scale - 2,
                      center + point["east_miles"] * scale + 2, center - point["north_miles"] * scale + 2], fill="#111111")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([center - radius * scale, center - radius * scale,
                                  center + radius * scale, center + radius * scale], fill=255)
    img.paste(layer, (0, 0), mask)
    draw = ImageDraw.Draw(img)
    draw.ellipse([center - radius * scale, center - radius * scale,
                  center + radius * scale, center + radius * scale], outline="black", width=2)
    draw.ellipse([center - 6, center - 6, center + 6, center + 6], fill="black")
    draw.text((12, 12), "Dough Valley hex_radius R=15 mi, s0=2.7 mi (approximate coordinate)", fill="black")
    draw.text((12, 30), "Voronoi cells: orange = 2.7 mi pass, teal = 1.35 mi changed-cell refinement", fill="black")
    img.save(path)


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("out/hex-demo")
    result = build_demo(out)
    print(json.dumps({k: result[k] for k in ("coarse_points", "new_points_at_fine_rung",
                                             "collected_points", "full_fine_rung_points",
                                             "ladder_rungs_miles")}, indent=2))
