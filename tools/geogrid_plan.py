#!/usr/bin/env python3
"""Deterministic 7-stage Universal GeoGrid Keyword & Territory Planner (BYO open-core).

Implements the full deterministic empirical pipeline with zero LLM guesswork and
zero external server dependency (uses your own DataForSEO account via legends-dataforseo):
- Stage 0: Subject intake, mode resolution, SSRF-pinned website service extraction, coastal 45-deg rim shift
- Stage 1: Deterministic candidate pool generation (K <= 20; excludes keywords_for_site / unfiltered keyword_ideas)
- Stage 2: 3-pin Google Maps competitive fingerprinting (adaptive [0.30, 0.60] fast-path vs full 3-pin deep)
- Stage 3: Pairwise 3-pin Top-20 Jaccard (J3) & average-linkage agglomerative clustering at tau = 0.45
- Stage 4: Demand hygiene (COLLISION, FINGERPRINT, median EST backfill) + 3-tier restricted-keyword cascade
- Stage 5: Cluster representative selection, hard pruning gates (bypassed for is_head), 5-factor score
- Stage 6: Greedy diminishing-returns tiering (T1=1, T2<=4 gated by ratio>=0.10 & U>=0.40, T3, PRUNED_LOW_VALUE)
- Stage 7: Data-driven starter radius R0 = clamp(1.5 * median(dmax), 1, 25), SAB detection, water-pin clipping
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import statistics
import sys
import time
from typing import Any, Callable
import unicodedata

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from study import _safe_local_path, _validate_public_url, safe_public_fetch

SCHEMA_ID = "legends-geogrid/geogrid-plan/v1"

CLUSTERING_TAU = 0.45
ADAPTIVE_LOW = 0.30
ADAPTIVE_HIGH = 0.60
RIM_DISTANCE_MILES = 4.0
MAX_CANDIDATES = 20
DEFAULT_TARGET_CANDIDATES = 15
CATEGORY_PURITY_GATE = 0.50
THIN_PACK_MIN_RESULTS = 10
T2_MAX_COUNT = 4
T2_MIN_RATIO = 0.10
T2_MIN_UNIQUENESS = 0.40
T3_MIN_RATIO = 0.02
COLLISION_RATIO_MAX = 0.50
SAB_HIDDEN_ADDRESS_THRESHOLD = 0.25
SAB_P80_MILES_THRESHOLD = 8.0
WATER_CLIPPING_THRESHOLD = 0.15

GEOGRID_VALID_RINGS = (2, 3, 4, 5, 6, 7)

# Advisory wholesale DataForSEO task rates (USD) for pre-run cost estimates.
# Estimates are advisory only and are never a provider-enforced billing limit.
RATE_MAPS_STANDARD_USD = 0.0006
RATE_MAPS_LIVE_USD = 0.0020
RATE_GBP_LIVE_USD = 0.0054
RATE_RELATED_KEYWORDS_USD = 0.0160
RATE_KEYWORD_OVERVIEW_BASE_USD = 0.0100
RATE_KEYWORD_OVERVIEW_PER_KW_USD = 0.0001
RATE_CLICKSTREAM_PER_KW_USD = 0.0005

_MILES_TO_KM = 1.60934
_EARTH_RADIUS_MILES = 3958.7613
_TARGET_CID_RE = re.compile(r"^[A-Za-z0-9_:-]{1,40}$")
_VALID_COMPETITION_LEVELS = frozenset({"LOW", "MEDIUM", "HIGH"})
_VALID_SEARCH_INTENTS = frozenset({"informational", "navigational", "commercial", "transactional"})

_NOISE_TOKENS = frozenset({
    "jobs", "job", "salary", "salaries", "career", "careers", "hiring",
    "recipe", "recipes", "cost", "how much", "meaning", "definition",
    "reddit", "wikipedia", "youtube", "course", "courses", "training",
    "certification", "school", "schools", "diy", "meme", "memes",
    "movie", "netflix", "book", "lyrics",
})

_NON_OFFERING_NEGATION_RE = re.compile(
    r"(?:we\s+do\s+not\s+(?:offer|provide|do)|not\s+offered|no\s+(?:mobile|walk-?in)\s+service|"
    r"studio[\s-]+only|in[\s-]+shop\s+only)",
    re.IGNORECASE,
)

# Fallback coordinate table for major US metros when center_lat/lng and GBP coords are absent.
_CITY_FALLBACK_COORDS: dict[str, tuple[float, float]] = {
    "miami": (25.7617, -80.1918),
    "scottsdale": (33.4942, -111.9261),
    "phoenix": (33.4484, -112.0740),
    "philadelphia": (39.9526, -75.1652),
    "philly": (39.9526, -75.1652),
    "dallas": (32.7767, -96.7970),
    "austin": (30.2672, -97.7431),
    "houston": (29.7604, -95.3698),
    "new york": (40.7128, -74.0060),
    "chicago": (41.8781, -87.6298),
    "los angeles": (34.0522, -118.2437),
    "san diego": (32.7157, -117.1611),
    "san francisco": (37.7749, -122.4194),
    "seattle": (47.6062, -122.3321),
    "tampa": (27.9506, -82.4572),
    "boston": (42.3601, -71.0589),
    "atlanta": (33.7490, -84.3880),
    "denver": (39.7392, -104.9903),
    "las vegas": (36.1699, -115.1398),
}

# Lightweight pure-Python coastal water polygons (lat, lng) for major US bays & ocean shelves.
# Safe fallback: inland/unknown coordinates always return False (dry land).
_WATER_POLYGONS: tuple[tuple[tuple[float, float], ...], ...] = (
    # Biscayne Bay & South Florida Atlantic
    (
        (26.15, -80.10),
        (25.95, -80.12),
        (25.86, -80.175),
        (25.79, -80.185),
        (25.765, -80.188),
        (25.740, -80.215),
        (25.720, -80.242),
        (25.690, -80.260),
        (25.630, -80.290),
        (25.520, -80.330),
        (25.400, -80.330),
        (25.400, -79.500),
        (26.150, -79.500),
    ),
    # Lake Michigan east of Chicago shoreline
    (
        (42.20, -87.80),
        (42.00, -87.66),
        (41.88, -87.61),
        (41.78, -87.56),
        (41.70, -87.52),
        (41.70, -86.60),
        (42.20, -86.60),
    ),
    # San Francisco Bay / Pacific west of SF
    (
        (37.90, -122.52),
        (37.80, -122.52),
        (37.65, -122.50),
        (37.65, -123.20),
        (37.90, -123.20),
    ),
    # Tampa Bay water body
    (
        (27.93, -82.55),
        (27.85, -82.56),
        (27.72, -82.61),
        (27.65, -82.55),
        (27.76, -82.43),
        (27.91, -82.45),
    ),
    # San Diego / SoCal Pacific Ocean
    (
        (33.10, -117.32),
        (32.85, -117.28),
        (32.72, -117.26),
        (32.55, -117.13),
        (32.55, -118.00),
        (33.10, -118.00),
    ),
    # New York Bight / Lower Bay Atlantic
    (
        (40.58, -74.06),
        (40.58, -73.75),
        (40.20, -73.75),
        (40.20, -74.00),
    ),
    # Boston Harbor / Massachusetts Bay
    (
        (42.45, -70.95),
        (42.36, -71.03),
        (42.25, -70.95),
        (42.25, -70.40),
        (42.45, -70.40),
    ),
    # Puget Sound west of Seattle waterfront
    (
        (47.75, -122.39),
        (47.62, -122.36),
        (47.52, -122.40),
        (47.52, -122.51),
        (47.75, -122.50),
    ),
)

WaterChecker = Callable[[float, float], bool]
PlanTransport = Callable[[str, dict[str, Any]], dict[str, Any]]
WebsiteFetcher = Callable[[str], dict[str, Any]]


@dataclass(frozen=True)
class GridPoint:
    index: int
    q: int
    r: int
    ring: int
    dx_km: float
    dy_km: float
    lat: float
    lng: float


def geogrid_hex_points(rings: int) -> int:
    r = int(rings)
    if r not in GEOGRID_VALID_RINGS:
        raise ValueError("rings must be one of 2, 3, 4, 5, 6, 7")
    return 1 + 3 * r * (r + 1)


def auto_zoom_for_radius(radius_km: float) -> int:
    """Map zoom by scan radius: <=3 km -> 14, 3-15 km -> 13, >15 km -> 12."""
    rad = float(radius_km)
    if rad <= 3.0:
        return 14
    if rad <= 15.0:
        return 13
    return 12


def generate_hex_lattice(
    center_lat: float,
    center_lng: float,
    rings: int = 3,
    radius_km: float = 5.0,
) -> list[GridPoint]:
    """Generate a circular-fanning axial hexagonal lattice centered on (center_lat, center_lng)."""
    r_max = int(rings)
    if r_max not in GEOGRID_VALID_RINGS:
        raise ValueError("rings must be one of 2, 3, 4, 5, 6, 7")
    rad = float(radius_km)
    if not math.isfinite(rad) or rad < 0.5 or rad > 50.0:
        raise ValueError("radius_km must be between 0.5 and 50.0")

    step_km = rad / float(r_max)
    sqrt3_half = math.sqrt(3.0) / 2.0
    lat_deg_per_km = 1.0 / 111.32
    cos_lat = max(0.1, math.cos(math.radians(center_lat)))
    lng_deg_per_km = 1.0 / (111.32 * cos_lat)

    raw_nodes: list[tuple[int, float, int, int, float, float]] = []
    for q in range(-r_max, r_max + 1):
        for r in range(-r_max, r_max + 1):
            ring = max(abs(q), abs(r), abs(-q - r))
            if ring > r_max:
                continue
            dx_km = step_km * (q + 0.5 * r)
            dy_km = step_km * (r * sqrt3_half)
            angle = 0.0 if ring == 0 else (math.atan2(dx_km, dy_km) % (2.0 * math.pi))
            raw_nodes.append((ring, round(angle, 9), q, r, dx_km, dy_km))

    raw_nodes.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    return [
        GridPoint(
            index=idx,
            q=q,
            r=r,
            ring=ring,
            dx_km=round(dx_km, 6),
            dy_km=round(dy_km, 6),
            lat=round(center_lat + dy_km * lat_deg_per_km, 6),
            lng=round(center_lng + dx_km * lng_deg_per_km, 6),
        )
        for idx, (ring, _ang, q, r, dx_km, dy_km) in enumerate(raw_nodes)
    ]


def _finite_float(val: Any) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    try:
        out = float(val)
    except (TypeError, ValueError, OverflowError):
        return None
    return out if math.isfinite(out) else None


def _finite_int(val: Any) -> int | None:
    f = _finite_float(val)
    if f is None:
        return None
    return int(round(f))


def _opt_int(value: Any, *, lo: int | None = None, hi: int | None = None) -> int | None:
    out = _finite_int(value)
    if out is None:
        return None
    if lo is not None and out < lo:
        return None
    if hi is not None and out > hi:
        return None
    return out


def _opt_money(value: Any) -> float | None:
    out = _finite_float(value)
    if out is None or out < 0 or out > 10_000:
        return None
    return round(out, 2)


def _norm_phrase(raw: Any) -> str:
    text = unicodedata.normalize("NFKC", str(raw or ""))
    return re.sub(r"\s+", " ", text).strip().lower()


def _norm_entity_name(raw: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _norm_phrase(raw)).strip()


def _extract_city_token(location: str) -> str:
    parts = [p.strip() for p in str(location or "").split(",") if p.strip()]
    return _norm_phrase(parts[0]) if parts else ""


def strip_city_modifier(phrase: str, city_token: str) -> str:
    """Strip leading or trailing city modifier token on word boundaries while keeping a valid bare phrase."""
    p = _norm_phrase(phrase)
    city = _norm_phrase(city_token)
    if not p or not city or p == city:
        return p
    changed = True
    while changed:
        changed = False
        if p.startswith(f"{city} "):
            rem = p[len(city) + 1 :].strip()
            if len(rem) >= 2:
                p = rem
                changed = True
        if p.endswith(f" {city}"):
            rem = p[: -(len(city) + 1)].strip()
            if len(rem) >= 2:
                p = rem
                changed = True
    return p


def has_city_modifier(phrase: str, city_token: str) -> bool:
    """Return True when phrase already contains city_token on normalized word boundaries."""
    p = _norm_phrase(phrase)
    city = _norm_phrase(city_token)
    if not p or not city:
        return False
    return bool(re.search(rf"(?:^|\s){re.escape(city)}(?:\s|$)", p))


def _review_count_band(count: int | None) -> str:
    n = max(0, int(count or 0))
    if n == 0:
        return "0"
    if n < 25:
        return "1-24"
    if n < 100:
        return "25-99"
    if n < 500:
        return "100-499"
    if n < 1000:
        return "500-999"
    return "1000+"


def _point_in_polygon(lat: float, lng: float, poly: tuple[tuple[float, float], ...]) -> bool:
    """Ray-casting point-in-polygon test in (lat, lng) space."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        yi, xi = poly[i]
        yj, xj = poly[j]
        intersects = ((yi > lat) != (yj > lat)) and (
            lng < (xj - xi) * (lat - yi) / ((yj - yi) if (yj - yi) != 0 else 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def is_point_on_water(lat: float, lng: float) -> bool:
    """Pure-Python coastal water-polygon check with safe inland fallback (False)."""
    lat_f = _finite_float(lat)
    lng_f = _finite_float(lng)
    if lat_f is None or lng_f is None:
        return False
    for poly in _WATER_POLYGONS:
        if _point_in_polygon(lat_f, lng_f, poly):
            return True
    return False


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(max(0.0, a)), math.sqrt(max(0.0, 1.0 - a)))
    return _EARTH_RADIUS_MILES * c


def offset_miles(lat: float, lng: float, miles: float, bearing_deg: float) -> tuple[float, float]:
    """Destination (lat, lng) at given miles and compass bearing (0=N, 90=E, 180=S, 270=W)."""
    ang = miles / _EARTH_RADIUS_MILES
    brg = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lng1 = math.radians(lng)
    sin_lat2 = math.sin(lat1) * math.cos(ang) + math.cos(lat1) * math.sin(ang) * math.cos(brg)
    lat2 = math.asin(max(-1.0, min(1.0, sin_lat2)))
    y = math.sin(brg) * math.sin(ang) * math.cos(lat1)
    x = math.cos(ang) - math.sin(lat1) * math.sin(lat2)
    lng2 = lng1 + math.atan2(y, x)
    out_lng = ((math.degrees(lng2) + 540.0) % 360.0) - 180.0
    return round(math.degrees(lat2), 6), round(out_lng, 6)


@dataclass(frozen=True)
class ProbePin:
    label: str
    lat: float
    lng: float
    bearing_deg: float | None = None
    adjusted: bool = False


def place_three_probe_pins(
    center_lat: float,
    center_lng: float,
    *,
    rim_miles: float = RIM_DISTANCE_MILES,
    water_checker: WaterChecker | None = None,
) -> tuple[list[ProbePin], bool]:
    """Place center pin plus 2 opposing rim pins (0 deg N, 180 deg S), rotating in 45 deg increments off water."""
    is_water = water_checker or is_point_on_water
    pins: list[ProbePin] = [ProbePin(label="c", lat=round(center_lat, 6), lng=round(center_lng, 6))]
    used_bearings: set[int] = set()
    any_adjusted = False

    for default_bearing, base_label in ((0, "rim1"), (180, "rim2")):
        chosen: ProbePin | None = None
        for delta in (0, 45, -45, 90, -90, 135, -135, 180):
            brg = (default_bearing + delta) % 360
            if brg in used_bearings:
                continue
            plat, plng = offset_miles(center_lat, center_lng, rim_miles, float(brg))
            if not is_water(plat, plng):
                adjusted = delta != 0
                if adjusted:
                    any_adjusted = True
                used_bearings.add(brg)
                chosen = ProbePin(label=base_label, lat=plat, lng=plng, bearing_deg=float(brg), adjusted=adjusted)
                break
        if chosen is None:
            plat, plng = offset_miles(center_lat, center_lng, rim_miles, float(default_bearing))
            chosen = ProbePin(label=base_label, lat=plat, lng=plng, bearing_deg=float(default_bearing), adjusted=False)
        pins.append(chosen)
    return pins, any_adjusted


def canonical_entity_id(item: dict[str, Any]) -> str:
    """Canonical entity identity per Maps item: str(cid or place_id or title/name)."""
    for key in ("cid", "place_id", "name", "title"):
        val = str(item.get(key) or "").strip()
        if val:
            return val
    return ""


def extract_head_categories(
    head_items: list[dict[str, Any]],
    *,
    target_categories: list[str] | None = None,
) -> tuple[list[str], set[str]]:
    """Extract primary GBP categories accounting for >= 25% of top-20 head items (fallback: modal category)."""
    counts: dict[str, int] = {}
    display_by_low: dict[str, str] = {}
    top20 = [it for it in (head_items or [])[:20] if isinstance(it, dict)]
    for it in top20:
        cat = str(it.get("category") or "").strip()
        if not cat:
            continue
        low = cat.lower()
        counts[low] = counts.get(low, 0) + 1
        display_by_low.setdefault(low, cat)

    total = max(1, len(top20))
    head_lows = [
        low for low, cnt in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        if (cnt / total) >= 0.25
    ]
    if not head_lows and counts:
        head_lows = [max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]]

    head_cats = [display_by_low[low] for low in head_lows]
    catset = set(head_lows)
    for tc in target_categories or []:
        t_clean = str(tc or "").strip()
        if t_clean:
            catset.add(t_clean.lower())
    return head_cats, catset


def _clean_category_to_phrase(cat: str) -> str:
    phrase = _norm_phrase(cat)
    phrase = re.sub(r"\b(service|services|shop|store|company|contractor|clinic|center|restaurant)\b$", "", phrase).strip()
    return phrase


def _is_noise_candidate(phrase: str, *, city_token: str = "") -> bool:
    low = _norm_phrase(phrase)
    if not low or len(low) < 2 or len(low) > 80:
        return True
    if any(tok in low.split() for tok in _NOISE_TOKENS):
        return True
    if "how much" in low or "http://" in low or "https://" in low or "www." in low:
        return True
    if city_token and low.endswith(f" {city_token}"):
        return False
    return False


def assemble_candidate_pool(
    seed_keyword: str,
    *,
    location: str = "",
    head_items: list[dict[str, Any]] | None = None,
    related_items: list[dict[str, Any]] | None = None,
    target_topics: list[str] | None = None,
    website_services: list[str] | None = None,
    extra_candidates: list[str] | None = None,
    max_candidates: int = MAX_CANDIDATES,
) -> list[str]:
    """Deterministic Stage 1 candidate pool (K <= 20), explicitly excluding keywords_for_site & keyword_ideas."""
    seed = _norm_phrase(seed_keyword)
    city = _extract_city_token(location)
    cap = max(1, min(MAX_CANDIDATES, int(max_candidates)))
    pool: list[str] = []
    seen: set[str] = set()

    def _add(raw: str, *, is_seed: bool = False) -> None:
        if len(pool) >= cap:
            return
        p = _norm_phrase(raw)
        if city and not is_seed:
            p = strip_city_modifier(p, city)
        if not p or p in seen or _is_noise_candidate(p, city_token=city):
            return
        seen.add(p)
        pool.append(p)

    # 1. Seed + explicit user extras prioritized first
    _add(seed, is_seed=True)
    for ex in extra_candidates or []:
        _add(ex)

    # 2. Normalized morphology & modifier variants derived from city-stripped seed
    bare_seed = strip_city_modifier(seed, city) if city else seed
    if bare_seed != seed:
        _add(bare_seed)
    if "near me" not in bare_seed:
        _add(f"{bare_seed} near me")
    if not bare_seed.endswith("service") and not bare_seed.endswith("services") and len(bare_seed.split()) <= 3:
        _add(f"{bare_seed} service")
    if bare_seed.endswith("s") and not bare_seed.endswith("ss") and len(bare_seed) > 4:
        _add(bare_seed[:-1])
    elif not bare_seed.endswith("s") and len(bare_seed.split()) <= 2:
        _add(f"{bare_seed}s")

    # 3. Head Maps pack primary & frequent additional categories (count >= 2)
    top20 = [it for it in (head_items or [])[:20] if isinstance(it, dict)]
    primary_counts: dict[str, int] = {}
    add_cat_counts: dict[str, int] = {}
    for it in top20:
        cat = str(it.get("category") or "").strip()
        if cat:
            low = cat.lower()
            primary_counts[low] = primary_counts.get(low, 0) + 1
        for ac in it.get("additional_categories") or []:
            ac_clean = str(ac or "").strip().lower()
            if ac_clean:
                add_cat_counts[ac_clean] = add_cat_counts.get(ac_clean, 0) + 1
    if primary_counts:
        modal_cat = max(primary_counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
        _add(modal_cat)
        cleaned_modal = _clean_category_to_phrase(modal_cat)
        if cleaned_modal:
            _add(cleaned_modal)
    for ac_low, cnt in sorted(add_cat_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if cnt >= 2:
            _add(_clean_category_to_phrase(ac_low) or ac_low)

    # 4. Related keywords strictly gated on local_pack == True
    for rel in related_items or []:
        if not isinstance(rel, dict):
            continue
        if not bool(rel.get("local_pack")):
            continue
        kw = str(rel.get("keyword") or "").strip()
        if kw:
            _add(kw)

    # 5. Business-mode target GBP topics & verified website services
    for src_list in (target_topics or [], website_services or []):
        for svc in src_list:
            _add(svc)

    return pool[:cap]


def extract_services_from_text(
    plain_text: str,
    headings: list[str] | None = None,
    *,
    candidates: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Deterministic prompt-firewalled plain-text offering extraction (offered, explicitly_not_offered)."""
    combined = " ".join([*(headings or []), plain_text or ""])
    low = _norm_phrase(combined)
    offered: list[str] = []
    not_offered: list[str] = []
    seen_off: set[str] = set()
    seen_no: set[str] = set()

    for cand in candidates or []:
        c = _norm_phrase(cand)
        if not c or len(c) < 3:
            continue
        idx = low.find(c)
        if idx >= 0:
            window = low[max(0, idx - 60) : min(len(low), idx + len(c) + 60)]
            if _NON_OFFERING_NEGATION_RE.search(window) or f"no {c}" in window or f"not {c}" in window:
                if c not in seen_no:
                    seen_no.add(c)
                    not_offered.append(c)
            else:
                if c not in seen_off:
                    seen_off.add(c)
                    offered.append(c)

    for h in headings or []:
        clean_h = re.sub(r"[^a-z0-9\s&-]", " ", _norm_phrase(h))
        clean_h = re.sub(r"\s+", " ", clean_h).strip()
        words = clean_h.split()
        if 2 <= len(words) <= 4 and clean_h not in seen_off and not _is_noise_candidate(clean_h):
            if not any(b in clean_h for b in ("about us", "contact us", "book now", "call us", "our team", "reviews", "faq")):
                seen_off.add(clean_h)
                offered.append(clean_h)
    return offered[:15], not_offered[:15]


def fetch_website_services(url: str) -> dict[str, Any]:
    """SSRF-pinned public HTTP(S) page capture returning plain text and headings only."""
    _validate_public_url(url)

    class _ServiceHTMLParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.parts: list[str] = []
            self.headings: list[str] = []
            self._heading_buf: list[str] = []
            self._in_heading = False
            self._skip = 0

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            low = tag.lower()
            if low in ("script", "style", "noscript", "svg"):
                self._skip += 1
            elif low in ("h1", "h2", "h3"):
                self._in_heading = True
                self._heading_buf = []

        def handle_endtag(self, tag: str) -> None:
            low = tag.lower()
            if low in ("script", "style", "noscript", "svg"):
                self._skip = max(0, self._skip - 1)
            elif low in ("h1", "h2", "h3") and self._in_heading:
                text = " ".join(self._heading_buf).strip()
                if text:
                    self.headings.append(text[:120])
                self._in_heading = False
                self._heading_buf = []

        def handle_data(self, data: str) -> None:
            if self._skip:
                return
            chunk = data.strip()
            if not chunk:
                return
            self.parts.append(chunk)
            if self._in_heading:
                self._heading_buf.append(chunk)

    raw, final_url, headers = safe_public_fetch(url, max_bytes=2_000_000, timeout=12, user_agent="legends-geogrid plan/1.0")
    encoding = headers.get_content_charset() or "utf-8"
    parser = _ServiceHTMLParser()
    parser.feed(raw.decode(encoding, errors="replace"))
    return {
        "status_code": 200,
        "final_url": final_url,
        "headings": parser.headings[:25],
        "text": "\n".join(parser.parts)[:20_000],
    }


def pairwise_jaccard_matrix(
    candidates: list[str],
    maps_probes: dict[str, dict[str, list[dict[str, Any]]]],
) -> tuple[dict[tuple[str, str], float], float, float]:
    """Compute pairwise 3-pin average Top-20 Jaccard J3, mean SE3, and % pairs within 1 SE of tau=0.45."""
    sets_by_kw: dict[str, dict[str, set[str]]] = {}
    for kw in candidates:
        pin_map = maps_probes.get(kw) or {}
        sets_by_kw[kw] = {}
        for pin_lbl, items in pin_map.items():
            ids = {canonical_entity_id(it) for it in (items or [])[:20] if isinstance(it, dict)}
            ids.discard("")
            if ids:
                sets_by_kw[kw][pin_lbl] = ids

    j3: dict[tuple[str, str], float] = {}
    se_list: list[float] = []
    pair_vals: list[float] = []

    n = len(candidates)
    for i in range(n):
        a = candidates[i]
        j3[(a, a)] = 1.0
        pins_a = sets_by_kw.get(a) or {}
        for j in range(i + 1, n):
            b = candidates[j]
            pins_b = sets_by_kw.get(b) or {}
            shared_pins = sorted(set(pins_a.keys()) & set(pins_b.keys()))
            pin_js: list[float] = []
            for p in shared_pins:
                sa = pins_a[p]
                sb = pins_b[p]
                union = sa | sb
                pin_js.append((len(sa & sb) / len(union)) if union else 0.0)
            avg_j = (sum(pin_js) / len(pin_js)) if pin_js else 0.0
            j3[(a, b)] = avg_j
            j3[(b, a)] = avg_j
            pair_vals.append(avg_j)
            if len(pin_js) >= 2:
                se_list.append(statistics.stdev(pin_js) / math.sqrt(len(pin_js)))

    mean_se3 = round(sum(se_list) / len(se_list), 4) if se_list else 0.0
    if pair_vals and mean_se3 > 0.0:
        within = sum(1 for v in pair_vals if abs(v - CLUSTERING_TAU) <= mean_se3)
        within_pct = round((within / len(pair_vals)) * 100.0, 1)
    else:
        within_pct = 0.0
    return j3, mean_se3, within_pct


def boundary_candidates_from_center(
    candidates: list[str],
    center_probes: dict[str, list[dict[str, Any]]],
    *,
    low: float = ADAPTIVE_LOW,
    high: float = ADAPTIVE_HIGH,
) -> list[str]:
    """Identify candidates participating in any center-pin pair with J1 in [0.30, 0.60] for adaptive 3-pin escalation."""
    sets: dict[str, set[str]] = {}
    for kw in candidates:
        ids = {canonical_entity_id(it) for it in (center_probes.get(kw) or [])[:20] if isinstance(it, dict)}
        ids.discard("")
        sets[kw] = ids

    escalate: set[str] = set()
    n = len(candidates)
    for i in range(n):
        a = candidates[i]
        sa = sets[a]
        for j in range(i + 1, n):
            b = candidates[j]
            sb = sets[b]
            union = sa | sb
            j1 = (len(sa & sb) / len(union)) if union else 0.0
            if low <= j1 <= high:
                escalate.add(a)
                escalate.add(b)
    return [kw for kw in candidates if kw in escalate]


def agglomerative_average_linkage(
    candidates: list[str],
    j3: dict[tuple[str, str], float],
    *,
    tau: float = CLUSTERING_TAU,
) -> list[list[str]]:
    """Average-linkage agglomerative clustering merging pairs while max cross-cluster avg J3 >= tau."""
    clusters: list[list[str]] = [[kw] for kw in candidates]
    while len(clusters) > 1:
        best_sim = -1.0
        best_pair: tuple[int, int] | None = None
        m = len(clusters)
        for i in range(m):
            ci = clusters[i]
            for j in range(i + 1, m):
                cj = clusters[j]
                total = 0.0
                for a in ci:
                    for b in cj:
                        total += j3.get((a, b), 0.0)
                avg_sim = total / (len(ci) * len(cj))
                if avg_sim > best_sim + 1e-12:
                    best_sim = avg_sim
                    best_pair = (i, j)
        if best_pair is None or best_sim < tau:
            break
        i, j = best_pair
        clusters[i] = clusters[i] + clusters[j]
        clusters.pop(j)
    return clusters


@dataclass
class CleanDemandRow:
    keyword: str
    volume: int | None
    cpc_usd: float | None
    trend_pct: float | None
    volume_source: str
    flags: list[str] = field(default_factory=list)
    v_bare: int | None = None


def _stage4a_hygiene_state(
    candidates: list[str],
    clusters: list[list[str]],
    raw_local: dict[str, dict[str, Any]],
    raw_bare: dict[str, dict[str, Any]],
    *,
    local_bare_same: set[str] | None = None,
) -> dict[str, Any]:
    """Run Stage 4a guards (COLLISION, FINGERPRINT, niche median ratio) before Tier 2 Clickstream selection."""
    cl_of: dict[str, int] = {}
    for cid, members in enumerate(clusters):
        for kw in members:
            cl_of[kw] = cid

    same_set: set[str] = set(local_bare_same or set())
    v_loc: dict[str, int | None] = {}
    cpc_loc: dict[str, float | None] = {}
    trend_loc: dict[str, float | None] = {}
    v_bare_map: dict[str, int | None] = {}
    cpc_bare_map: dict[str, float | None] = {}
    trend_bare_map: dict[str, float | None] = {}
    flags: dict[str, list[str]] = {kw: [] for kw in candidates}

    for kw in candidates:
        loc_d = raw_local.get(kw) or {}
        bare_d = raw_bare.get(kw) or {}
        loc_q_str = _norm_phrase(loc_d.get("keyword") or "")
        bare_q_str = _norm_phrase(bare_d.get("keyword") or "")
        if loc_q_str and bare_q_str and loc_q_str == bare_q_str:
            same_set.add(kw)
        vl = _finite_int(loc_d.get("search_volume"))
        vb = _finite_int(bare_d.get("search_volume"))
        v_loc[kw] = vl if (vl is not None and vl > 0) else None
        v_bare_map[kw] = vb if (vb is not None and vb > 0) else None
        cl_c = _finite_float(loc_d.get("cpc_usd"))
        cb_c = _finite_float(bare_d.get("cpc_usd"))
        cpc_loc[kw] = round(cl_c, 2) if (cl_c is not None and cl_c >= 0) else None
        cpc_bare_map[kw] = round(cb_c, 2) if (cb_c is not None and cb_c >= 0) else None
        trend_loc[kw] = _finite_float(loc_d.get("yearly_trend_pct"))
        trend_bare_map[kw] = _finite_float(bare_d.get("yearly_trend_pct"))

    # Guard 1: City-modifier COLLISION (V_local > 0.50 * V_bare)
    for kw in candidates:
        if kw in same_set:
            continue
        vl = v_loc[kw]
        vb = v_bare_map[kw]
        if vl is not None and vb is not None and vb > 0 and vl > COLLISION_RATIO_MAX * vb:
            v_loc[kw] = None
            flags[kw].append("COLLISION")

    # Guard 2: Cross-cluster close-variant FINGERPRINT duplicate (V_local, cpc)
    tuples_map: dict[tuple[int, float], list[str]] = {}
    for kw in candidates:
        vl = v_loc[kw]
        cl_c = cpc_loc[kw]
        if vl is not None and vl > 0 and cl_c is not None:
            tuples_map.setdefault((vl, round(cl_c, 2)), []).append(kw)
    for _key, kws in tuples_map.items():
        if len(kws) < 2:
            continue
        distinct_clusters = {cl_of.get(k, -1) for k in kws}
        if len(distinct_clusters) < 2:
            continue
        keeper = max(kws, key=lambda k: (v_bare_map.get(k) or 0, -len(k), k))
        keeper_cl = cl_of.get(keeper, -1)
        for k in kws:
            if cl_of.get(k, -1) != keeper_cl:
                v_loc[k] = None
                if "FINGERPRINT" not in flags[k]:
                    flags[k].append("FINGERPRINT")

    ratios = [
        v_loc[kw] / v_bare_map[kw]  # type: ignore[operator]
        for kw in candidates
        if (
            kw not in same_set
            and v_loc[kw] is not None
            and v_loc[kw] > 0
            and v_bare_map[kw] is not None
            and v_bare_map[kw] > 0
        )
    ]
    med_ratio = statistics.median(ratios) if ratios else None
    return {
        "same_set": same_set,
        "v_loc": v_loc,
        "cpc_loc": cpc_loc,
        "trend_loc": trend_loc,
        "v_bare_map": v_bare_map,
        "cpc_bare_map": cpc_bare_map,
        "trend_bare_map": trend_bare_map,
        "flags": flags,
        "med_ratio": med_ratio,
    }


def find_clickstream_fallback_candidates(
    candidates: list[str],
    clusters: list[list[str]],
    raw_local: dict[str, dict[str, Any]],
    raw_bare: dict[str, dict[str, Any]],
    *,
    local_bare_same: set[str] | None = None,
) -> list[str]:
    """Return every candidate whose post-guard Tier 1 (v_loc) and Tier 1b (vb * med_ratio) volume is still None."""
    st = _stage4a_hygiene_state(
        candidates,
        clusters,
        raw_local,
        raw_bare,
        local_bare_same=local_bare_same,
    )
    same_set: set[str] = st["same_set"]
    v_loc: dict[str, int | None] = st["v_loc"]
    v_bare_map: dict[str, int | None] = st["v_bare_map"]
    med_ratio: float | None = st["med_ratio"]

    unresolved: list[str] = []
    for kw in candidates:
        vl = v_loc[kw]
        if vl is not None and vl > 0:
            continue
        vb = v_bare_map[kw]
        if kw not in same_set and vb is not None and vb > 0 and med_ratio is not None and med_ratio > 0:
            continue
        unresolved.append(kw)
    return unresolved


def apply_demand_hygiene(
    candidates: list[str],
    clusters: list[list[str]],
    raw_local: dict[str, dict[str, Any]],
    raw_bare: dict[str, dict[str, Any]],
    raw_clickstream: dict[str, dict[str, Any]] | None = None,
    *,
    local_bare_same: set[str] | None = None,
) -> dict[str, CleanDemandRow]:
    """Stage 4 deterministic demand hygiene: COLLISION, FINGERPRINT, EST backfill, Clickstream & Maps Proxy."""
    st = _stage4a_hygiene_state(
        candidates,
        clusters,
        raw_local,
        raw_bare,
        local_bare_same=local_bare_same,
    )
    same_set: set[str] = st["same_set"]
    v_loc: dict[str, int | None] = st["v_loc"]
    cpc_loc: dict[str, float | None] = st["cpc_loc"]
    trend_loc: dict[str, float | None] = st["trend_loc"]
    v_bare_map: dict[str, int | None] = st["v_bare_map"]
    cpc_bare_map: dict[str, float | None] = st["cpc_bare_map"]
    trend_bare_map: dict[str, float | None] = st["trend_bare_map"]
    flags: dict[str, list[str]] = st["flags"]
    med_ratio: float | None = st["med_ratio"]

    cs_map = raw_clickstream or {}
    cs_calib_ratios: list[float] = []
    for kw in candidates:
        vl = v_loc[kw]
        cs_entry = cs_map.get(kw) or {}
        cs_v = _finite_int(cs_entry.get("clickstream_search_volume"))
        if cs_v is None and str(cs_entry.get("volume_source") or "") == "clickstream_fallback":
            cs_v = _finite_int(cs_entry.get("search_volume"))
        if vl is not None and vl > 0 and cs_v is not None and cs_v > 0:
            cs_calib_ratios.append(vl / cs_v)
    cs_scale = statistics.median(cs_calib_ratios) if cs_calib_ratios else None

    out: dict[str, CleanDemandRow] = {}
    for kw in candidates:
        vl = v_loc[kw]
        vb = v_bare_map[kw]
        cpc = cpc_loc[kw] if cpc_loc[kw] is not None else cpc_bare_map[kw]
        tr = trend_loc[kw] if trend_loc[kw] is not None else trend_bare_map[kw]

        if vl is not None and vl > 0:
            out[kw] = CleanDemandRow(
                keyword=kw,
                volume=vl,
                cpc_usd=cpc,
                trend_pct=tr,
                volume_source="ad_planner",
                flags=list(flags[kw]),
                v_bare=vb,
            )
            continue

        # Tier 1b: EST backfill from bare volume * niche median local/bare ratio
        if kw not in same_set and vb is not None and vb > 0 and med_ratio is not None and med_ratio > 0:
            est_v = max(1, int(round(vb * med_ratio)))
            f_list = list(flags[kw])
            if "EST" not in f_list:
                f_list.append("EST")
            out[kw] = CleanDemandRow(
                keyword=kw,
                volume=est_v,
                cpc_usd=cpc,
                trend_pct=tr,
                volume_source="ad_planner_estimated",
                flags=f_list,
                v_bare=vb,
            )
            continue

        # Tier 2: selective Clickstream fallback (reads clickstream_keyword_info.search_volume directly)
        cs_entry = cs_map.get(kw) or raw_local.get(kw) or {}
        cs_v = _finite_int(cs_entry.get("clickstream_search_volume"))
        if cs_v is None and str(cs_entry.get("volume_source") or "") == "clickstream_fallback":
            cs_v = _finite_int(cs_entry.get("search_volume"))
        if cs_v is not None and cs_v > 0:
            calibrated = max(1, int(round(cs_v * cs_scale))) if cs_scale is not None else cs_v
            cs_cpc = cpc if cpc is not None else _finite_float(cs_entry.get("cpc_usd"))
            out[kw] = CleanDemandRow(
                keyword=kw,
                volume=calibrated,
                cpc_usd=round(cs_cpc, 2) if (cs_cpc is not None and cs_cpc >= 0) else None,
                trend_pct=tr,
                volume_source="clickstream_fallback",
                flags=list(flags[kw]),
                v_bare=vb,
            )
            continue

        # Tier 3: policy_restricted_maps_proxy fail-safe floor
        f_list = list(flags[kw])
        if "HOLE" not in f_list:
            f_list.append("HOLE")
        out[kw] = CleanDemandRow(
            keyword=kw,
            volume=None,
            cpc_usd=cpc,
            trend_pct=tr,
            volume_source="policy_restricted_maps_proxy",
            flags=f_list,
            v_bare=vb,
        )
    return out


def _matches_target(
    item: dict[str, Any],
    *,
    target_cid: str | None,
    business_name_norm: str,
) -> bool:
    if target_cid and str(item.get("cid") or "").strip() == target_cid:
        return True
    if business_name_norm:
        item_name = _norm_entity_name(item.get("name") or item.get("title") or "")
        if item_name and (item_name == business_name_norm or business_name_norm in item_name):
            return True
    return False


def _is_not_offered(phrase: str, not_offered_set: set[str]) -> bool:
    """Match excluded terms against candidate phrase strictly on normalized word boundaries."""
    p = _norm_phrase(phrase)
    if not p or not not_offered_set:
        return False
    if p in not_offered_set:
        return True
    for term in not_offered_set:
        if term and re.search(rf"(?:^|\s){re.escape(term)}(?:\s|$)", p):
            return True
    return False


def _has_street_address(item: dict[str, Any]) -> bool:
    if isinstance(item.get("has_street_address"), bool):
        return bool(item["has_street_address"])
    addr = str(item.get("address") or "").strip()
    if not addr:
        return False
    return bool(re.match(r"^\d+\s+\S+", addr))


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = (len(s) - 1) * max(0.0, min(1.0, pct))
    lo = int(math.floor(idx))
    hi = min(len(s) - 1, lo + 1)
    frac = idx - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def _recommended_rings_for_radius(radius_km: float) -> int:
    if radius_km <= 12.0:
        return 3
    if radius_km <= 25.0:
        return 4
    return 5


def compute_geogrid_plan(
    *,
    seed_keyword: str,
    location: str,
    center_lat: float,
    center_lng: float,
    probe_pins: list[ProbePin],
    coastal_rim_adjusted: bool,
    candidates: list[str],
    maps_probes: dict[str, dict[str, list[dict[str, Any]]]],
    raw_local_demand: dict[str, dict[str, Any]],
    raw_bare_demand: dict[str, dict[str, Any]],
    raw_clickstream_demand: dict[str, dict[str, Any]] | None = None,
    business_name: str | None = None,
    target_cid: str | None = None,
    target_profile: dict[str, Any] | None = None,
    not_offered_terms: list[str] | None = None,
    water_checker: WaterChecker | None = None,
    local_bare_same: set[str] | None = None,
    failed_center_candidates: set[str] | None = None,
) -> dict[str, Any]:
    """Pure-Python deterministic Stage 3..7 core."""
    seed = _norm_phrase(seed_keyword)
    mode = "business" if (business_name or target_cid) else "market"
    failed_set = {_norm_phrase(c) for c in (failed_center_candidates or set()) if _norm_phrase(c)}
    clean_cands: list[str] = []
    seen_c: set[str] = set()
    for c in [seed, *(candidates or [])]:
        cn = _norm_phrase(c)
        if not cn or cn in seen_c:
            continue
        if cn != seed and cn in failed_set:
            continue
        seen_c.add(cn)
        clean_cands.append(cn)
    clean_cands = clean_cands[:MAX_CANDIDATES]

    head_pin_map = maps_probes.get(seed) or {}
    head_center_items = list(head_pin_map.get("c") or [])
    effective_thin_min = (
        min(THIN_PACK_MIN_RESULTS, max(3, int(0.6 * len(head_center_items))))
        if 0 < len(head_center_items) < THIN_PACK_MIN_RESULTS
        else THIN_PACK_MIN_RESULTS
    )
    target_cats: list[str] = []
    if target_profile:
        if target_profile.get("primary_category"):
            target_cats.append(str(target_profile["primary_category"]))
        for ac in target_profile.get("additional_categories") or []:
            target_cats.append(str(ac))
    head_cats, catset = extract_head_categories(
        head_center_items,
        target_categories=target_cats if mode == "business" else None,
    )

    # Stage 3: Pairwise J3 matrix & average-linkage clustering at tau = 0.45
    j3, jaccard_se3, pairs_within_1se_pct = pairwise_jaccard_matrix(clean_cands, maps_probes)
    clusters = agglomerative_average_linkage(clean_cands, j3, tau=CLUSTERING_TAU)

    # Stage 4: Demand hygiene & 3-tier restricted-keyword cascade
    demand_by_kw = apply_demand_hygiene(
        clean_cands,
        clusters,
        raw_local_demand,
        raw_bare_demand,
        raw_clickstream_demand,
        local_bare_same=local_bare_same,
    )

    # Stage 5: Cluster representative selection, hard gates & exact 5-factor scoring
    not_offered_set = {_norm_phrase(t) for t in (not_offered_terms or []) if _norm_phrase(t)}
    biz_norm = _norm_entity_name(business_name or (target_profile or {}).get("business_name") or "")

    pos_cpcs = [
        d.cpc_usd for d in demand_by_kw.values()
        if d.cpc_usd is not None and d.cpc_usd > 0
    ]
    median_cpc = statistics.median(pos_cpcs) if pos_cpcs else 1.0

    cluster_records: list[dict[str, Any]] = []
    for cl in clusters:
        is_head = seed in cl

        def _member_weight(kw: str) -> float:
            d = demand_by_kw[kw]
            if d.volume is None or d.volume <= 0:
                return 0.0
            eff_cpc = d.cpc_usd if (d.cpc_usd is not None and d.cpc_usd > 0) else median_cpc
            return float(d.volume) * float(eff_cpc)

        non_est_real = [
            k for k in cl
            if demand_by_kw[k].volume is not None
            and demand_by_kw[k].volume > 0
            and "EST" not in demand_by_kw[k].flags
            and demand_by_kw[k].volume_source == "ad_planner"
        ]
        any_pos = [
            k for k in cl
            if demand_by_kw[k].volume is not None and demand_by_kw[k].volume > 0
        ]
        if non_est_real:
            rep = max(non_est_real, key=lambda k: (_member_weight(k), demand_by_kw[k].volume or 0, -len(k)))
        elif any_pos:
            rep = max(any_pos, key=lambda k: (_member_weight(k), demand_by_kw[k].volume or 0, -len(k)))
        else:
            rep = min(cl, key=lambda k: (len(k), k))

        if is_head:
            query = seed
        elif demand_by_kw[rep].volume is not None and demand_by_kw[rep].volume > 0:
            query = rep
        else:
            query = min(cl, key=lambda k: (len(k), k))

        collapsed = [k for k in cl if k != query]
        rep_d = demand_by_kw[rep]
        cl_vol = rep_d.volume
        cl_cpc = rep_d.cpc_usd
        if cl_cpc is None:
            cpcs_in_cl = [demand_by_kw[k].cpc_usd for k in cl if demand_by_kw[k].cpc_usd is not None]
            cl_cpc = max(cpcs_in_cl) if cpcs_in_cl else None
        cl_trend = rep_d.trend_pct
        cl_vol_source = rep_d.volume_source
        is_hole = cl_vol is None or cl_vol <= 0
        raw_w = (
            float(cl_vol) * float(cl_cpc)
            if (cl_vol and cl_cpc is not None and cl_cpc > 0)
            else (float(cl_vol) * float(median_cpc) if (cl_vol and cl_vol > 0) else 0.0)
        )

        cl_flags: list[str] = []
        for k in cl:
            for fl in demand_by_kw[k].flags:
                if fl == "HOLE" and not is_hole:
                    continue
                if fl not in cl_flags:
                    cl_flags.append(fl)

        q_pins = maps_probes.get(query) or {}
        top10_union: set[str] = set()
        purity_vals: list[float] = []
        for pin_items in q_pins.values():
            top20 = [it for it in (pin_items or [])[:20] if isinstance(it, dict)]
            for it in top20[:10]:
                eid = canonical_entity_id(it)
                if eid:
                    top10_union.add(eid)
            if top20:
                if catset:
                    hits = 0
                    for it in top20:
                        cats = {str(it.get("category") or "").strip().lower()}
                        cats.update(str(c).strip().lower() for c in (it.get("additional_categories") or []) if c)
                        cats.discard("")
                        if cats & catset:
                            hits += 1
                    purity_vals.append(hits / len(top20))
                else:
                    purity_vals.append(1.0)
        incat = round(sum(purity_vals) / len(purity_vals), 4) if purity_vals else 0.0

        center_items = [it for it in (q_pins.get("c") or [])[:20] if isinstance(it, dict)]
        n_center = len(center_items)
        top10_center = center_items[:10]
        votes = [max(0, _finite_int(it.get("reviews")) or 0) for it in top10_center]
        med_votes = round(float(statistics.median(votes)), 1) if votes else 0.0
        weak_cnt = sum(1 for v in votes if v < 50)

        target_rank: int | None = None
        if mode == "business":
            for pos, it in enumerate(center_items[:20], start=1):
                if _matches_target(it, target_cid=target_cid, business_name_norm=biz_norm):
                    target_rank = pos
                    break

        pruned_reason: str | None = None
        pruned_note = ""
        if not is_head:
            if mode == "business" and not_offered_set and all(_is_not_offered(k, not_offered_set) for k in cl):
                pruned_reason = "PRUNED_NOT_OFFERED"
                pruned_note = "Excluded because this service is marked not offered by the target business."
            elif incat < CATEGORY_PURITY_GATE:
                pruned_reason = "PRUNED_OUT_OF_CATEGORY"
                pruned_note = f"Category purity {incat:.2f} is below the {CATEGORY_PURITY_GATE:.2f} gate."
            elif n_center < effective_thin_min:
                pruned_reason = "PRUNED_THIN_PACK"
                pruned_note = f"Center Maps pack returned only {n_center} listings (minimum {effective_thin_min})."

        cluster_records.append(
            {
                "members": cl,
                "is_head": is_head,
                "query": query,
                "collapsed_synonyms": collapsed,
                "monthly_volume": cl_vol,
                "cpc_usd": round(cl_cpc, 2) if cl_cpc is not None else None,
                "raw_w": raw_w,
                "trend_pct": cl_trend,
                "volume_source": cl_vol_source,
                "is_hole": is_hole,
                "data_hygiene_flags": cl_flags,
                "top10_union": top10_union,
                "category_purity": incat,
                "median_top10_reviews": med_votes,
                "weak_listings": weak_cnt,
                "n_center": n_center,
                "target_center_rank": target_rank,
                "pruned_reason": pruned_reason,
                "pruned_note": pruned_note,
            }
        )

    pos_ws = [r["raw_w"] for r in cluster_records if r["raw_w"] > 0]
    median_w_pos = statistics.median(pos_ws) if pos_ws else 1.0
    for r in cluster_records:
        r["w_use"] = r["raw_w"] if r["raw_w"] > 0 else median_w_pos

    eligible = [r for r in cluster_records if r["pruned_reason"] is None]
    w_max = max((r["w_use"] for r in eligible), default=max((r["w_use"] for r in cluster_records), default=1.0))
    w_max = max(1.0, float(w_max))

    log_denom_w = math.log1p(w_max)
    log_2001 = math.log(2001.0)
    for r in cluster_records:
        c_score = min(1.0, math.log1p(max(0.0, r["w_use"])) / log_denom_w) if log_denom_w > 0 else 0.0
        l_score = max(0.0, min(1.0, float(r["category_purity"])))
        v = r["monthly_volume"]
        tr = r["trend_pct"]
        if tr is None or v is None or v < 300:
            m_score = 1.0 / 3.0
        else:
            m_score = (max(-50.0, min(100.0, float(tr))) + 50.0) / 150.0
        o_score = 1.0 - min(1.0, math.log1p(max(0.0, float(r["median_top10_reviews"]))) / log_2001)
        rk = r["target_center_rank"]
        if mode == "market" or rk is None:
            g_score = 0.6
        elif 4 <= rk <= 20:
            g_score = 1.0
        else:
            g_score = 0.3

        total_score = round(
            100.0 * (0.40 * c_score + 0.20 * l_score + 0.10 * m_score + 0.15 * o_score + 0.15 * g_score),
            1,
        )
        r["score_0_100"] = max(0.0, min(100.0, total_score))
        r["subscores"] = {
            "commercial_C": round(c_score, 4),
            "purity_L": round(l_score, 4),
            "momentum_M": round(m_score, 4),
            "opportunity_O": round(o_score, 4),
            "rank_gap_G": round(g_score, 4),
        }

    # Stage 6: Greedy diminishing-returns tiering
    head_candidates = [r for r in eligible if r["is_head"]]
    if not head_candidates:
        head_candidates = sorted(cluster_records, key=lambda r: (-r["score_0_100"], r["query"]))
    t1_rec = max(head_candidates, key=lambda r: (r["score_0_100"], r["w_use"]))
    t1_rec["tier"] = "T1"
    t1_rec["marginal_uniqueness"] = 1.0
    t1_rec["demand_ratio_vs_t1"] = 1.0
    seen_top10: set[str] = set(t1_rec["top10_union"])
    w_t1 = max(1e-9, float(t1_rec["w_use"]))

    tier2_recs: list[dict[str, Any]] = []
    tier3_recs: list[dict[str, Any]] = []
    pruned_recs: list[dict[str, Any]] = [r for r in cluster_records if r["pruned_reason"] is not None]

    rest_eligible = [r for r in eligible if r is not t1_rec]
    rest_eligible.sort(key=lambda r: (-r["score_0_100"], -r["w_use"], r["query"]))

    for r in rest_eligible:
        tc = r["top10_union"]
        u_val = round(len(tc - seen_top10) / max(1, len(tc)), 4) if tc else 0.0
        ratio_val = round(float(r["w_use"]) / w_t1, 4)
        r["marginal_uniqueness"] = u_val
        r["demand_ratio_vs_t1"] = ratio_val
        if len(tier2_recs) < T2_MAX_COUNT and ratio_val >= T2_MIN_RATIO and u_val >= T2_MIN_UNIQUENESS:
            r["tier"] = "T2"
            tier2_recs.append(r)
            seen_top10 |= tc
        elif ratio_val >= T3_MIN_RATIO or r["is_hole"]:
            r["tier"] = "T3"
            tier3_recs.append(r)
        else:
            r["pruned_reason"] = "PRUNED_LOW_VALUE"
            r["pruned_note"] = f"Commercial ratio {ratio_val:.3f} is below the {T3_MIN_RATIO:.2f} watchlist floor."
            pruned_recs.append(r)

    # Stage 7: Starter radius R0 = clamp(1.5 * median(dmax), 1, 25), SAB detection, water-pin clipping
    pin_by_label = {p.label: p for p in probe_pins}
    dmax_by_pin: list[float] = []
    center_dists: list[float] = []
    for plbl, pitems in head_pin_map.items():
        pin = pin_by_label.get(plbl)
        if pin is None:
            continue
        dists: list[float] = []
        for it in (pitems or [])[:20]:
            if not isinstance(it, dict):
                continue
            ilat = _finite_float(it.get("latitude"))
            ilng = _finite_float(it.get("longitude"))
            if ilat is None or ilng is None:
                continue
            d_mi = haversine_miles(pin.lat, pin.lng, ilat, ilng)
            if math.isfinite(d_mi) and d_mi <= 50.0:
                dists.append(d_mi)
        if dists:
            dmax_by_pin.append(max(dists))
            if plbl == "c":
                center_dists = dists

    reach_miles = float(statistics.median(dmax_by_pin)) if dmax_by_pin else 3.0
    r0_miles = max(1.0, min(25.0, 1.5 * reach_miles))
    starter_radius_km = round(max(0.5, min(50.0, r0_miles * _MILES_TO_KM)), 1)
    median_reach_km = round(reach_miles * _MILES_TO_KM, 2)

    p80_center_miles = _percentile(center_dists, 0.80) if center_dists else 0.0
    head_top20_center = [it for it in head_center_items[:20] if isinstance(it, dict)]
    if head_top20_center:
        no_street_cnt = sum(1 for it in head_top20_center if not _has_street_address(it))
        sab_share = round(no_street_cnt / len(head_top20_center), 4)
    else:
        sab_share = 0.0

    rec_rings = _recommended_rings_for_radius(starter_radius_km)
    hex_points = geogrid_hex_points(rec_rings)
    rec_zoom = auto_zoom_for_radius(starter_radius_km)

    is_water = water_checker or is_point_on_water
    lattice = generate_hex_lattice(center_lat, center_lng, rings=rec_rings, radius_km=starter_radius_km)
    water_pts = sum(1 for gp in lattice if is_water(gp.lat, gp.lng))
    water_frac = round(water_pts / max(1, len(lattice)), 4)
    land_clipping = water_frac >= WATER_CLIPPING_THRESHOLD

    if sab_share >= SAB_HIDDEN_ADDRESS_THRESHOLD or p80_center_miles >= SAB_P80_MILES_THRESHOLD:
        geom_class = "sab_metro"
    elif land_clipping:
        geom_class = "coastal_clipped"
    elif starter_radius_km <= 8.5:
        geom_class = "dense_urban"
    else:
        geom_class = "suburban_metro"

    def _to_cluster_dict(r: dict[str, Any]) -> dict[str, Any]:
        return {
            "query": r["query"],
            "tier": r["tier"],
            "score_0_100": r["score_0_100"],
            "subscores": r["subscores"],
            "collapsed_synonyms": r["collapsed_synonyms"],
            "monthly_volume": r["monthly_volume"],
            "cpc_usd": r["cpc_usd"],
            "commercial_weight": round(float(r["w_use"]), 2),
            "volume_source": r["volume_source"],
            "data_hygiene_flags": r["data_hygiene_flags"],
            "category_purity": r["category_purity"],
            "marginal_uniqueness": r["marginal_uniqueness"],
            "demand_ratio_vs_t1": r["demand_ratio_vs_t1"],
            "median_top10_reviews": r["median_top10_reviews"],
            "weak_listings_under_50_reviews": r["weak_listings"],
            "target_center_rank": r["target_center_rank"],
        }

    def _to_pruned_dict(r: dict[str, Any]) -> dict[str, Any]:
        return {
            "query": r["query"],
            "reason": r["pruned_reason"],
            "score_0_100": r["score_0_100"],
            "collapsed_synonyms": r["collapsed_synonyms"],
            "category_purity": r["category_purity"],
            "note": r["pruned_note"],
        }

    launch_biz = (
        (business_name or "").strip()
        or str((target_profile or {}).get("business_name") or "").strip()
        or (str(head_top20_center[0].get("name") or "").strip() if head_top20_center else "")
        or f"Market Benchmark ({location})"
    )[:160]
    byo_standard_usd = round(hex_points * RATE_MAPS_STANDARD_USD, 4)

    safe_target_cid = (
        str(target_cid).strip()
        if (target_cid and _TARGET_CID_RE.fullmatch(str(target_cid).strip()))
        else None
    )
    launch_actions: list[dict[str, Any]] = []
    for rec in [t1_rec, *tier2_recs]:
        tier_lbl = "Tier 1" if rec["tier"] == "T1" else "Tier 2"
        act_params: dict[str, Any] = {
            "business_name": launch_biz,
            "keyword": rec["query"],
            "center_lat": round(center_lat, 6),
            "center_lng": round(center_lng, 6),
            "rings": rec_rings,
            "radius_km": starter_radius_km,
            "zoom": rec_zoom,
            "method": "standard",
        }
        if safe_target_cid:
            act_params["target_cid"] = safe_target_cid
        launch_actions.append(
            {
                "label": f"Run {tier_lbl} GeoGrid: {rec['query']}",
                "tier": rec["tier"],
                "estimated_byo_standard_usd": byo_standard_usd,
                "params": act_params,
            }
        )

    dups_collapsed = max(0, len(clean_cands) - len(clusters))
    recommended_count = 1 + len(tier2_recs)

    target_profile_out: dict[str, Any] | None = None
    if mode == "business" and (target_profile or business_name):
        tp = target_profile or {}
        target_profile_out = {
            "business_name": str(tp.get("business_name") or business_name or "")[:160],
            "primary_category": str(tp.get("primary_category") or (head_cats[0] if head_cats else "Local business"))[:80],
            "additional_categories": [str(c)[:80] for c in (tp.get("additional_categories") or [])][:12],
            "rating": _finite_float(tp.get("rating")),
            "review_count_band": str(tp.get("review_count_band") or _review_count_band(_finite_int(tp.get("reviews")))),
            "offered_services_verified": [str(s)[:80] for s in (tp.get("offered_services_verified") or [])][:15],
        }

    return {
        "schema_id": SCHEMA_ID,
        "mode": mode,
        "seed_keyword": seed,
        "location_canonical": str(location).strip(),
        "target_profile": target_profile_out,
        "center_coordinates": {
            "lat": round(center_lat, 6),
            "lng": round(center_lng, 6),
            "probe_pins_count": len(probe_pins),
            "coastal_rim_adjusted": bool(coastal_rim_adjusted),
        },
        "head_categories": head_cats,
        "summary_metrics": {
            "candidates_evaluated": len(clean_cands),
            "clusters_formed": len(clusters),
            "duplicates_collapsed": dups_collapsed,
            "recommended_scan_count": recommended_count,
            "clustering_threshold_tau": CLUSTERING_TAU,
            "jaccard_se3": jaccard_se3,
            "pairs_within_1se_pct": pairs_within_1se_pct,
        },
        "recommended_geometry": {
            "geometry_class": geom_class,
            "starter_radius_km": starter_radius_km,
            "recommended_rings": rec_rings,
            "hex_points": hex_points,
            "recommended_zoom": rec_zoom,
            "water_pin_fraction_unclipped": water_frac,
            "land_clipping_recommended": land_clipping,
            "median_competitor_reach_km": median_reach_km,
            "sab_hidden_address_share": sab_share,
        },
        "tier1": _to_cluster_dict(t1_rec),
        "tier2": [_to_cluster_dict(r) for r in tier2_recs],
        "tier3": [_to_cluster_dict(r) for r in tier3_recs],
        "pruned": [_to_pruned_dict(r) for r in pruned_recs],
        "launch_actions": launch_actions,
    }


def resolve_fallback_coordinates(
    location: str,
    head_items: list[dict[str, Any]] | None = None,
) -> tuple[float, float]:
    """Resolve fallback center coordinates from head Maps pack median or city lookup."""
    lats = [
        _finite_float(it.get("latitude"))
        for it in (head_items or [])[:20]
        if isinstance(it, dict)
    ]
    lngs = [
        _finite_float(it.get("longitude"))
        for it in (head_items or [])[:20]
        if isinstance(it, dict)
    ]
    valid_lats = [x for x in lats if x is not None and -90.0 <= x <= 90.0]
    valid_lngs = [x for x in lngs if x is not None and -180.0 <= x <= 180.0]
    if valid_lats and valid_lngs:
        return round(float(statistics.median(valid_lats)), 6), round(float(statistics.median(valid_lngs)), 6)
    city = _extract_city_token(location)
    if city in _CITY_FALLBACK_COORDS:
        return _CITY_FALLBACK_COORDS[city]
    return (39.8283, -98.5795)


# ------------------------------------------------------------------ DataForSEO envelope parsers


def _first_task_result(envelope: dict[str, Any]) -> dict[str, Any]:
    tasks = envelope.get("tasks") or []
    if not tasks or not isinstance(tasks[0], dict):
        return {}
    results = tasks[0].get("result") or []
    if not results or not isinstance(results[0], dict):
        return {}
    return results[0]


def _task_cost_usd(envelope: dict[str, Any]) -> float | None:
    tasks = envelope.get("tasks") or []
    raw = tasks[0].get("cost") if (tasks and isinstance(tasks[0], dict)) else None
    if raw is None:
        raw = envelope.get("cost")
    val = _finite_float(raw)
    if val is None or val < 0 or val > 100.0:
        return None
    return round(val, 6)


def parse_keyword_overview_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Normalize DataForSEO Labs keyword_overview envelope.

    Reads ``clickstream_keyword_info.search_volume`` directly when present (NEVER
    ``keyword_info_normalized_with_clickstream``, which stays null on policy-suppressed rows).
    """
    res = _first_task_result(envelope)
    rows: list[dict[str, Any]] = []
    for item in res.get("items") or []:
        if not isinstance(item, dict):
            continue
        kw = str(item.get("keyword") or "").strip().lower()
        if not kw:
            continue
        info = item.get("keyword_info") if isinstance(item.get("keyword_info"), dict) else {}
        cs_info = item.get("clickstream_keyword_info") if isinstance(item.get("clickstream_keyword_info"), dict) else {}
        props = item.get("keyword_properties") if isinstance(item.get("keyword_properties"), dict) else {}
        intent_info = item.get("search_intent_info") if isinstance(item.get("search_intent_info"), dict) else {}
        sv_trend = info.get("search_volume_trend") if isinstance(info.get("search_volume_trend"), dict) else {}
        comp_level = str(info.get("competition_level") or "").strip().upper()
        intent = str(intent_info.get("main_intent") or "").strip().lower()
        rows.append(
            {
                "keyword": kw,
                "search_volume": _opt_int(info.get("search_volume"), lo=0),
                "clickstream_search_volume": _opt_int(cs_info.get("search_volume"), lo=0),
                "yearly_trend_pct": _finite_float(sv_trend.get("yearly")),
                "cpc_usd": _opt_money(info.get("cpc")),
                "competition_level": comp_level if comp_level in _VALID_COMPETITION_LEVELS else "UNKNOWN",
                "keyword_difficulty": _opt_int(props.get("keyword_difficulty"), lo=0, hi=100),
                "search_intent": intent if intent in _VALID_SEARCH_INTENTS else "unknown",
            }
        )
    return {"items": rows, "cost_usd": _task_cost_usd(envelope)}


def parse_related_keywords_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Normalize DataForSEO Labs related_keywords envelope into local-pack gated candidates."""
    res = _first_task_result(envelope)
    rows: list[dict[str, Any]] = []
    for entry in res.get("items") or []:
        if not isinstance(entry, dict):
            continue
        kd = entry.get("keyword_data") if isinstance(entry.get("keyword_data"), dict) else entry
        kw = str(kd.get("keyword") or "").strip().lower()
        if not kw:
            continue
        info = kd.get("keyword_info") if isinstance(kd.get("keyword_info"), dict) else {}
        serp_info = kd.get("serp_info") if isinstance(kd.get("serp_info"), dict) else {}
        serp_types = [str(t).strip().lower() for t in (serp_info.get("serp_item_types") or []) if t]
        local_pack = bool(entry.get("local_pack")) or ("local_pack" in serp_types) or ("maps" in serp_types)
        rows.append(
            {
                "keyword": kw,
                "local_pack": local_pack,
                "search_volume": _opt_int(info.get("search_volume"), lo=0),
                "cpc_usd": _opt_money(info.get("cpc")),
            }
        )
    return {"items": rows, "cost_usd": _task_cost_usd(envelope)}


def parse_business_profile_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Normalize DataForSEO Business Data my_business_info envelope."""
    res = _first_task_result(envelope)
    items = res.get("items") or []
    entry = items[0] if items and isinstance(items[0], dict) else {}
    if not entry:
        return {"found": False, "cost_usd": _task_cost_usd(envelope)}
    rating_obj = entry.get("rating")
    rating_val = rating_obj.get("value") if isinstance(rating_obj, dict) else rating_obj
    reviews_val = rating_obj.get("votes_count") if isinstance(rating_obj, dict) else entry.get("reviews")
    add_cats = [
        str(c).strip()[:80]
        for c in (entry.get("additional_categories") or [])
        if isinstance(c, str) and c.strip()
    ][:12]
    topics_raw = entry.get("place_topics")
    place_topics: list[str] = []
    if isinstance(topics_raw, dict):
        place_topics = [str(k).strip()[:60] for k in topics_raw.keys() if str(k).strip()][:15]
    elif isinstance(topics_raw, list):
        place_topics = [str(k).strip()[:60] for k in topics_raw if isinstance(k, str) and k.strip()][:15]
    return {
        "found": True,
        "business_name": str(entry.get("title") or entry.get("name") or "").strip()[:160],
        "cid": str(entry.get("cid") or "").strip() or None,
        "place_id": str(entry.get("place_id") or "").strip() or None,
        "latitude": _finite_float(entry.get("latitude")),
        "longitude": _finite_float(entry.get("longitude")),
        "primary_category": str(entry.get("category") or "").strip()[:80],
        "additional_categories": add_cats,
        "rating": _finite_float(rating_val),
        "reviews": _opt_int(reviews_val, lo=0),
        "place_topics": place_topics,
        "cost_usd": _task_cost_usd(envelope),
    }


def parse_maps_pack_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Normalize DataForSEO Google Maps SERP envelope into Top-20 listing rows."""
    res = _first_task_result(envelope)
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(res.get("items") or [], start=1):
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "maps_search").lower()
        if item_type not in ("maps_search", "local_pack", ""):
            continue
        name = str(item.get("title") or item.get("name") or "").strip()
        if not name:
            continue
        rating_obj = item.get("rating")
        rating_val = rating_obj.get("value") if isinstance(rating_obj, dict) else rating_obj
        reviews_val = rating_obj.get("votes_count") if isinstance(rating_obj, dict) else item.get("reviews")
        out.append(
            {
                "rank": _opt_int(item.get("rank_group") or item.get("rank_absolute"), lo=1) or idx,
                "name": name[:160],
                "cid": str(item.get("cid") or "").strip() or None,
                "place_id": str(item.get("place_id") or "").strip() or None,
                "category": str(item.get("category") or "").strip()[:80],
                "additional_categories": [
                    str(c).strip()[:80]
                    for c in (item.get("additional_categories") or [])
                    if isinstance(c, str) and c.strip()
                ][:12],
                "rating": _finite_float(rating_val),
                "reviews": _opt_int(reviews_val, lo=0) or 0,
                "latitude": _finite_float(item.get("latitude")),
                "longitude": _finite_float(item.get("longitude")),
                "address": str(item.get("address") or "").strip()[:200],
            }
        )
        if len(out) >= 20:
            break
    return {"items": out, "cost_usd": _task_cost_usd(envelope)}


# ------------------------------------------------------------------ BYO DataForSEO transport


class BudgetCeilingError(RuntimeError):
    """Raised when the advisory --confirm-cost-usd ceiling is reached mid-run."""


class DfsByoTransport:
    """Thin BYO DataForSEO transport delegating exclusively to legends_dataforseo.api_request."""

    def __init__(
        self,
        *,
        method: str = "standard",
        allow_live: bool = False,
        max_cost_usd: float = 0.0,
        poll_interval_seconds: float = 2.0,
        max_wait_seconds: float = 180.0,
    ) -> None:
        if method not in ("standard", "live"):
            raise ValueError("method must be 'standard' or 'live'")
        if method == "live" and not allow_live:
            raise ValueError("Live Maps probes require explicit --allow-live; Standard queue is the default.")
        self.method = method
        self.allow_live = allow_live
        self.max_cost_usd = float(max_cost_usd)
        self.spent_usd = 0.0
        self.poll_interval_seconds = max(0.5, float(poll_interval_seconds))
        self.max_wait_seconds = max(10.0, float(max_wait_seconds))

    def _call_api(self, endpoint: str, body: list[dict[str, Any]] | None, *, estimated_usd: float) -> dict[str, Any]:
        remaining = max(0.0, self.max_cost_usd - self.spent_usd)
        if estimated_usd > remaining + 1e-9:
            raise BudgetCeilingError(
                f"Advisory budget ceiling ${self.max_cost_usd:.4f} reached before {endpoint} "
                f"(spent ${self.spent_usd:.4f}, next est ${estimated_usd:.4f})."
            )
        from legends_dataforseo import api_request

        resp = api_request(
            endpoint,
            body,
            confirm=True,
            estimated_cost_usd=estimated_usd,
            max_cost_usd=remaining,
            consumer="geogrid-plan",
        )
        actual = _task_cost_usd(resp)
        self.spent_usd += actual if actual is not None else estimated_usd
        return resp

    def _maps_standard(self, task: dict[str, Any]) -> dict[str, Any]:
        post_resp = self._call_api(
            "/serp/google/maps/task_post",
            [{**task, "priority": 1}],
            estimated_usd=RATE_MAPS_STANDARD_USD,
        )
        tasks = post_resp.get("tasks") or []
        task_id = tasks[0].get("id") if (tasks and isinstance(tasks[0], dict)) else None
        if not task_id:
            return {"items": [], "cost_usd": _task_cost_usd(post_resp)}
        deadline = time.monotonic() + self.max_wait_seconds
        while time.monotonic() < deadline:
            time.sleep(self.poll_interval_seconds)
            get_resp = self._call_api(
                f"/serp/google/maps/task_get/advanced/{task_id}",
                None,
                estimated_usd=0.0,
            )
            g_tasks = get_resp.get("tasks") or []
            status = g_tasks[0].get("status_code") if (g_tasks and isinstance(g_tasks[0], dict)) else None
            if status == 20000:
                return parse_maps_pack_envelope(get_resp)
            if status not in (40601, 40602, 20100, None):
                break
        return {"items": [], "cost_usd": _task_cost_usd(post_resp)}

    def __call__(self, op: str, payload: dict[str, Any]) -> dict[str, Any]:
        if op == "business_profile":
            body = [{
                "keyword": payload.get("target_cid") or payload["keyword"],
                "location_name": payload.get("location_name") or "United States",
                "language_code": "en",
            }]
            resp = self._call_api("/business_data/google/my_business_info/live", body, estimated_usd=RATE_GBP_LIVE_USD)
            return parse_business_profile_envelope(resp)

        if op == "related_keywords":
            body = [{
                "keyword": payload["keyword"],
                "location_name": payload.get("location_name") or "United States",
                "language_code": "en",
                "limit": int(payload.get("limit") or 30),
                "include_serp_info": True,
            }]
            resp = self._call_api("/dataforseo_labs/google/related_keywords/live", body, estimated_usd=RATE_RELATED_KEYWORDS_USD)
            return parse_related_keywords_envelope(resp)

        if op == "maps_pack":
            task: dict[str, Any] = {
                "keyword": payload["keyword"],
                "depth": 20,
                "device": "desktop",
                "language_code": "en",
                "se_domain": "google.com",
                "search_this_area": False,
                "search_places": False,
            }
            if payload.get("lat") is not None and payload.get("lng") is not None:
                zoom = int(payload.get("zoom") or 13)
                task["location_coordinate"] = f"{float(payload['lat']):.7f},{float(payload['lng']):.7f},{zoom}z"
            else:
                task["location_name"] = payload.get("location_name") or "United States"
            if self.method == "live":
                resp = self._call_api("/serp/google/maps/live/advanced", [task], estimated_usd=RATE_MAPS_LIVE_USD)
                return parse_maps_pack_envelope(resp)
            return self._maps_standard(task)

        if op == "keyword_demand":
            kws = list(payload.get("keywords") or [])
            include_cs = bool(payload.get("include_clickstream_data", False))
            per_kw = RATE_CLICKSTREAM_PER_KW_USD if include_cs else RATE_KEYWORD_OVERVIEW_PER_KW_USD
            est = RATE_KEYWORD_OVERVIEW_BASE_USD + per_kw * len(kws)
            body_item: dict[str, Any] = {
                "keywords": kws,
                "location_name": payload.get("location_name") or "United States",
                "language_code": "en",
            }
            if include_cs:
                body_item["include_clickstream_data"] = True
            resp = self._call_api("/dataforseo_labs/google/keyword_overview/live", [body_item], estimated_usd=est)
            return parse_keyword_overview_envelope(resp)

        raise ValueError(f"Unsupported operation: {op}")


# ------------------------------------------------------------------ Cost estimate & 7-stage runner


def estimate_plan_cost(
    *,
    max_candidates: int = DEFAULT_TARGET_CANDIDATES,
    deep: bool = False,
    has_business: bool = False,
    method: str = "standard",
) -> dict[str, Any]:
    """Compute an itemized advisory pre-run wholesale DataForSEO cost estimate (USD)."""
    k = max(1, min(MAX_CANDIDATES, int(max_candidates)))
    maps_rate = RATE_MAPS_LIVE_USD if method == "live" else RATE_MAPS_STANDARD_USD
    # Worst-case Maps probe count: 3 pins * k in deep mode; center (k) + seed rims (2) + ~half escalated in standard mode
    est_maps_probes = (3 * k) if deep else min(3 * k, k + 2 + 2 * max(2, k // 2))
    max_maps_probes = 3 * k

    gbp_usd = RATE_GBP_LIVE_USD if has_business else 0.0
    related_usd = RATE_RELATED_KEYWORDS_USD
    maps_est_usd = round(est_maps_probes * maps_rate, 4)
    maps_max_usd = round(max_maps_probes * maps_rate, 4)
    demand_base_usd = round(2 * (RATE_KEYWORD_OVERVIEW_BASE_USD + RATE_KEYWORD_OVERVIEW_PER_KW_USD * k), 4)
    clickstream_max_usd = round(RATE_KEYWORD_OVERVIEW_BASE_USD + RATE_CLICKSTREAM_PER_KW_USD * k, 4)

    est_total = round(gbp_usd + related_usd + maps_est_usd + demand_base_usd, 4)
    ceiling_total = round(gbp_usd + related_usd + maps_max_usd + demand_base_usd + clickstream_max_usd, 4)
    return {
        "advisory_only": True,
        "notice": "Advisory wholesale DataForSEO estimate only; never a provider-enforced billing limit.",
        "method": method,
        "depth": "deep" if deep else "standard",
        "max_candidates": k,
        "estimated_maps_probes": est_maps_probes,
        "max_maps_probes": max_maps_probes,
        "breakdown_usd": {
            "business_profile": round(gbp_usd, 4),
            "related_keywords": round(related_usd, 4),
            "maps_probes_estimated": maps_est_usd,
            "maps_probes_max": maps_max_usd,
            "keyword_demand_local_and_bare": demand_base_usd,
            "clickstream_fallback_worst_case": clickstream_max_usd,
        },
        "estimated_cost_usd": est_total,
        "worst_case_ceiling_usd": ceiling_total,
    }


def _validate_plan_inputs(
    *,
    seed_keyword: str,
    location: str,
    center_lat: float | None,
    center_lng: float | None,
    website_url: str | None,
    max_candidates: int,
    depth: str,
    method: str,
) -> tuple[str, str, float | None, float | None]:
    seed = _norm_phrase(seed_keyword)
    if not seed or len(seed) < 2:
        raise ValueError("seed_keyword must be at least 2 characters.")
    loc = str(location or "").strip()
    if not loc or len(loc) < 2:
        raise ValueError("location must be provided (for example 'Miami, FL').")
    if (center_lat is None) != (center_lng is None):
        raise ValueError("Provide both center_lat and center_lng together, or omit both.")
    lat_v: float | None = None
    lng_v: float | None = None
    if center_lat is not None and center_lng is not None:
        lat_v = _finite_float(center_lat)
        lng_v = _finite_float(center_lng)
        if lat_v is None or lng_v is None or not (-90.0 <= lat_v <= 90.0) or not (-180.0 <= lng_v <= 180.0):
            raise ValueError("center_lat and center_lng must be finite valid WGS84 coordinates.")
    if website_url:
        _validate_public_url(str(website_url).strip())
    if depth not in ("standard", "deep"):
        raise ValueError("depth must be 'standard' or 'deep'.")
    if method not in ("standard", "live"):
        raise ValueError("method must be 'standard' or 'live'.")
    if not (1 <= int(max_candidates) <= MAX_CANDIDATES):
        raise ValueError(f"max_candidates must be between 1 and {MAX_CANDIDATES}.")
    return seed, loc, lat_v, lng_v


def run_geogrid_plan(
    *,
    seed_keyword: str,
    location: str,
    business_name: str | None = None,
    target_cid: str | None = None,
    website_url: str | None = None,
    center_lat: float | None = None,
    center_lng: float | None = None,
    extra_candidates: list[str] | None = None,
    not_offered_terms: list[str] | None = None,
    depth: str = "standard",
    max_candidates: int = DEFAULT_TARGET_CANDIDATES,
    method: str = "standard",
    allow_live: bool = False,
    execute: bool = False,
    confirm_cost_usd: float = 0.0,
    transport: PlanTransport | None = None,
    website_fetcher: WebsiteFetcher | None = None,
    water_checker: WaterChecker | None = None,
) -> dict[str, Any]:
    """Execute the full 7-stage deterministic planner (or return a zero-spend dry-run estimate)."""
    seed, loc, c_lat, c_lng = _validate_plan_inputs(
        seed_keyword=seed_keyword,
        location=location,
        center_lat=center_lat,
        center_lng=center_lng,
        website_url=website_url,
        max_candidates=max_candidates,
        depth=depth,
        method=method,
    )
    deep = depth == "deep"
    biz_name = str(business_name).strip() if business_name else None
    cid_clean = str(target_cid).strip() if target_cid else None
    extra_clean = [_norm_phrase(c) for c in (extra_candidates or []) if _norm_phrase(c)]
    not_off_clean = [_norm_phrase(c) for c in (not_offered_terms or []) if _norm_phrase(c)]

    estimate = estimate_plan_cost(
        max_candidates=max_candidates,
        deep=deep,
        has_business=bool(biz_name or cid_clean),
        method=method,
    )

    if not execute:
        return {
            "status": "dry_run_estimate",
            "schema_id": SCHEMA_ID,
            "seed_keyword": seed,
            "location": loc,
            "mode": "business" if (biz_name or cid_clean) else "market",
            "business_name": biz_name,
            "target_cid": cid_clean,
            "website_url": str(website_url).strip() if website_url else None,
            "estimate": estimate,
            "next_step": (
                f"Re-run with --execute --confirm-cost-usd {estimate['worst_case_ceiling_usd']:.4f} "
                "using your BYO DataForSEO credentials (DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD)."
            ),
        }

    if method == "live" and not allow_live:
        raise ValueError("Live Maps probes require explicit --allow-live; Standard queue is the default.")
    ceiling = _finite_float(confirm_cost_usd)
    if ceiling is None or ceiling <= 0:
        raise ValueError("--execute requires a positive --confirm-cost-usd ceiling.")
    if estimate["estimated_cost_usd"] > ceiling + 1e-9:
        raise ValueError(
            f"Advisory estimate ${estimate['estimated_cost_usd']:.4f} exceeds "
            f"--confirm-cost-usd ceiling ${ceiling:.4f}."
        )

    tx: PlanTransport = transport or DfsByoTransport(
        method=method,
        allow_live=allow_live,
        max_cost_usd=ceiling,
    )

    # Stage 0a: Business profile grounding (Business Mode)
    target_profile: dict[str, Any] | None = None
    target_topics: list[str] = []
    if biz_name or cid_clean:
        try:
            bp = tx("business_profile", {
                "keyword": biz_name or seed,
                "location_name": loc,
                "target_cid": cid_clean,
            })
            if isinstance(bp, dict) and bp.get("found"):
                target_profile = dict(bp)
                cand_cid = str(bp.get("cid") or "").strip()
                if not cid_clean and cand_cid and _TARGET_CID_RE.fullmatch(cand_cid):
                    cid_clean = cand_cid
                if not biz_name and bp.get("business_name"):
                    biz_name = str(bp["business_name"]).strip()
                target_topics = [str(t) for t in (bp.get("place_topics") or []) if str(t).strip()]
        except BudgetCeilingError:
            raise
        except Exception:
            target_profile = None

    # Stage 0b: SSRF-pinned plain-text website service extraction
    website_services: list[str] = []
    website_not_offered: list[str] = []
    if website_url:
        try:
            fetcher = website_fetcher or fetch_website_services
            page = fetcher(str(website_url).strip())
            if int(page.get("status_code", 200)) == 200:
                website_services, website_not_offered = extract_services_from_text(
                    str(page.get("text") or page.get("markdown") or ""),
                    list(page.get("headings") or []),
                    candidates=[seed, *extra_clean, *not_off_clean],
                )
                if target_profile is None:
                    target_profile = {
                        "business_name": biz_name or "",
                        "primary_category": "",
                        "additional_categories": [],
                        "rating": None,
                        "reviews": 0,
                    }
                target_profile["offered_services_verified"] = list(website_services)
        except ValueError:
            raise
        except Exception:
            pass

    if (c_lat is None or c_lng is None) and target_profile:
        bp_lat = _finite_float(target_profile.get("latitude"))
        bp_lng = _finite_float(target_profile.get("longitude"))
        if bp_lat is not None and bp_lng is not None and -90.0 <= bp_lat <= 90.0 and -180.0 <= bp_lng <= 180.0:
            c_lat, c_lng = bp_lat, bp_lng

    # Stage 1a: Head Maps probe at center (13z, depth 20)
    head_res = tx("maps_pack", {
        "keyword": seed,
        "location_name": loc,
        "lat": c_lat,
        "lng": c_lng,
        "zoom": 13,
    })
    head_items = [it for it in (head_res.get("items") or [])[:20] if isinstance(it, dict)]

    if c_lat is None or c_lng is None:
        c_lat, c_lng = resolve_fallback_coordinates(loc, head_items)

    probe_pins, coastal_rim_adjusted = place_three_probe_pins(
        c_lat,
        c_lng,
        water_checker=water_checker,
    )

    # Stage 1b: Related keywords (local_pack filtered; NEVER keywords_for_site or keyword_ideas)
    related_items: list[dict[str, Any]] = []
    try:
        rel_res = tx("related_keywords", {"keyword": seed, "location_name": loc, "limit": 30})
        related_items = [it for it in (rel_res.get("items") or []) if isinstance(it, dict)]
    except BudgetCeilingError:
        raise
    except Exception:
        related_items = []

    candidates = assemble_candidate_pool(
        seed,
        location=loc,
        head_items=head_items,
        related_items=related_items,
        target_topics=target_topics,
        website_services=website_services,
        extra_candidates=extra_clean,
        max_candidates=max_candidates,
    )

    # Stage 2: 3-pin Google Maps competitive fingerprinting
    maps_probes: dict[str, dict[str, list[dict[str, Any]]]] = {seed: {"c": head_items}}
    failed_center_candidates: set[str] = set()
    pin_c, pin_rim1, pin_rim2 = probe_pins[0], probe_pins[1], probe_pins[2]

    def _probe(kw: str, pin: ProbePin) -> tuple[list[dict[str, Any]], bool]:
        try:
            res = tx("maps_pack", {
                "keyword": kw,
                "location_name": f"{pin.lat:.6f},{pin.lng:.6f}",
                "lat": pin.lat,
                "lng": pin.lng,
                "zoom": 13,
            })
            return [it for it in (res.get("items") or [])[:20] if isinstance(it, dict)], True
        except BudgetCeilingError:
            raise
        except Exception:
            return [], False

    for rim_pin in (pin_rim1, pin_rim2):
        items_r, ok_r = _probe(seed, rim_pin)
        if ok_r:
            maps_probes[seed][rim_pin.label] = items_r

    center_probes: dict[str, list[dict[str, Any]]] = {seed: head_items}
    for kw in candidates:
        if kw == seed:
            continue
        items_c, ok_c = _probe(kw, pin_c)
        if ok_c:
            maps_probes.setdefault(kw, {})["c"] = items_c
            center_probes[kw] = items_c
        else:
            failed_center_candidates.add(kw)

    active_candidates = [kw for kw in candidates if kw == seed or kw not in failed_center_candidates]
    if deep:
        rim_targets = [kw for kw in active_candidates if kw != seed]
    else:
        rim_targets = [
            kw for kw in boundary_candidates_from_center(active_candidates, center_probes)
            if kw != seed
        ]
    for kw in rim_targets:
        for rim_pin in (pin_rim1, pin_rim2):
            items_r, ok_r = _probe(kw, rim_pin)
            if ok_r:
                maps_probes.setdefault(kw, {})[rim_pin.label] = items_r

    # Stage 3 clustering prior to Stage 4 Clickstream fallback selection
    j3_pre, _, _ = pairwise_jaccard_matrix(active_candidates, maps_probes)
    clusters_pre = agglomerative_average_linkage(active_candidates, j3_pre, tau=CLUSTERING_TAU)

    # Stage 4: Demand lookup (local + bare + selective Clickstream fallback)
    city_tok = _extract_city_token(loc)
    raw_local_demand: dict[str, dict[str, Any]] = {}
    raw_bare_demand: dict[str, dict[str, Any]] = {}
    raw_clickstream_demand: dict[str, dict[str, Any]] = {}

    local_query_map: dict[str, str] = {}
    bare_query_map: dict[str, str] = {}
    local_bare_same: set[str] = set()
    for kw in active_candidates:
        bare_q = strip_city_modifier(kw, city_tok) if city_tok else kw
        if city_tok and has_city_modifier(kw, city_tok):
            local_q = kw
        elif city_tok:
            local_q = f"{bare_q} {city_tok}"
        else:
            local_q = kw
        local_query_map[kw] = local_q
        bare_query_map[kw] = bare_q
        if local_q == bare_q:
            local_bare_same.add(kw)

    local_queries = list(dict.fromkeys(local_query_map.values()))
    bare_queries = list(dict.fromkeys(bare_query_map.values()))

    if local_queries:
        try:
            loc_raw = tx("keyword_demand", {"keywords": local_queries, "location_name": "United States"})
            loc_by_q = {
                str(it.get("keyword") or "").strip().lower(): it
                for it in (loc_raw.get("items") or [])
                if isinstance(it, dict) and str(it.get("keyword") or "").strip()
            }
            for kw, lq in local_query_map.items():
                if lq in loc_by_q:
                    raw_local_demand[kw] = loc_by_q[lq]
        except BudgetCeilingError:
            raise
        except Exception:
            pass

    if bare_queries:
        try:
            bare_raw = tx("keyword_demand", {"keywords": bare_queries, "location_name": "United States"})
            bare_by_q = {
                str(it.get("keyword") or "").strip().lower(): it
                for it in (bare_raw.get("items") or [])
                if isinstance(it, dict) and str(it.get("keyword") or "").strip()
            }
            for kw, bq in bare_query_map.items():
                if bq in bare_by_q:
                    raw_bare_demand[kw] = bare_by_q[bq]
        except BudgetCeilingError:
            raise
        except Exception:
            pass

    unresolved_for_cs = find_clickstream_fallback_candidates(
        active_candidates,
        clusters_pre,
        raw_local_demand,
        raw_bare_demand,
        local_bare_same=local_bare_same,
    )
    suppressed_for_cs: list[str] = []
    suppressed_query_to_kws: dict[str, list[str]] = {}
    for kw in unresolved_for_cs:
        lq = local_query_map[kw]
        if lq not in suppressed_query_to_kws:
            suppressed_for_cs.append(lq)
            suppressed_query_to_kws[lq] = []
        suppressed_query_to_kws[lq].append(kw)

    if suppressed_for_cs:
        try:
            cs_raw = tx("keyword_demand", {
                "keywords": suppressed_for_cs,
                "location_name": "United States",
                "include_clickstream_data": True,
            })
            for it in cs_raw.get("items") or []:
                if not isinstance(it, dict):
                    continue
                q_key = str(it.get("keyword") or "").strip().lower()
                matched_kws = suppressed_query_to_kws.get(q_key)
                if matched_kws:
                    for okw in matched_kws:
                        raw_clickstream_demand[okw] = it
                elif q_key in active_candidates:
                    raw_clickstream_demand[q_key] = it
        except BudgetCeilingError:
            raise
        except Exception:
            pass

    merged_not_offered = list(dict.fromkeys([*not_off_clean, *website_not_offered]))
    computed = compute_geogrid_plan(
        seed_keyword=seed,
        location=loc,
        center_lat=c_lat,
        center_lng=c_lng,
        probe_pins=probe_pins,
        coastal_rim_adjusted=coastal_rim_adjusted,
        candidates=candidates,
        maps_probes=maps_probes,
        raw_local_demand=raw_local_demand,
        raw_bare_demand=raw_bare_demand,
        raw_clickstream_demand=raw_clickstream_demand,
        business_name=biz_name,
        target_cid=cid_clean,
        target_profile=target_profile,
        not_offered_terms=merged_not_offered,
        water_checker=water_checker,
        local_bare_same=local_bare_same,
        failed_center_candidates=failed_center_candidates,
    )
    computed["status"] = "completed"
    computed["estimate"] = estimate
    computed["provenance"] = {
        "computed_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": method,
        "depth": depth,
        "evidence_bundle_sha256": hashlib.sha256(
            json.dumps(computed, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest(),
    }
    return computed


def format_plan_summary(result: dict[str, Any]) -> str:
    """Render a concise human-readable terminal summary for dry-run estimates or completed plans."""
    if result.get("status") == "dry_run_estimate":
        est = result["estimate"]
        lines = [
            f"legends-geogrid plan (dry-run estimate): {result['seed_keyword']} @ {result['location']}",
            f"  Mode: {result['mode']} | Depth: {est['depth']} | Method: {est['method']}",
            f"  Max candidates: {est['max_candidates']} | Maps probes: ~{est['estimated_maps_probes']} (max {est['max_maps_probes']})",
            f"  Advisory wholesale estimate: ${est['estimated_cost_usd']:.4f} (worst-case ceiling: ${est['worst_case_ceiling_usd']:.4f})",
            f"  Note: {est['notice']}",
            f"  Next: {result['next_step']}",
        ]
        return "\n".join(lines)

    sm = result["summary_metrics"]
    geom = result["recommended_geometry"]
    t1 = result["tier1"]
    lines = [
        f"legends-geogrid plan: {result['seed_keyword']} @ {result['location_canonical']} ({result['mode']} mode)",
        f"  Candidates: {sm['candidates_evaluated']} -> {sm['clusters_formed']} clusters ({sm['duplicates_collapsed']} duplicates collapsed, tau={sm['clustering_threshold_tau']})",
        f"  Starter geometry: {geom['geometry_class']} | R0={geom['starter_radius_km']} km | {geom['recommended_rings']} rings ({geom['hex_points']} hex pts) | zoom {geom['recommended_zoom']}",
        f"  Tier 1: {t1['query']} (score {t1['score_0_100']}, vol={t1['monthly_volume']}, source={t1['volume_source']})",
    ]
    for idx, t2 in enumerate(result.get("tier2") or [], start=1):
        lines.append(
            f"  Tier 2.{idx}: {t2['query']} (score {t2['score_0_100']}, vol={t2['monthly_volume']}, U={t2['marginal_uniqueness']})"
        )
    if result.get("tier3"):
        lines.append(f"  Tier 3 watchlist: {', '.join(c['query'] for c in result['tier3'])}")
    if result.get("pruned"):
        lines.append(f"  Pruned: {', '.join(f'{p['query']} ({p['reason']})' for p in result['pruned'])}")
    return "\n".join(lines)


def build_arg_parser(parser: argparse.ArgumentParser | None = None) -> argparse.ArgumentParser:
    p = parser or argparse.ArgumentParser(description="Deterministic 7-stage GeoGrid keyword & territory planner")
    p.add_argument("--seed-keyword", required=True, help="Core service keyword (for example 'car detailing')")
    p.add_argument("--location", required=True, help="Target city/market (for example 'Miami, FL')")
    p.add_argument("--business-name", help="Optional target business name (enables business mode)")
    p.add_argument("--target-cid", help="Optional Google Business Profile CID")
    p.add_argument("--website-url", help="Optional public website URL for SSRF-pinned service extraction")
    p.add_argument("--center-lat", type=float, help="Optional center latitude")
    p.add_argument("--center-lng", type=float, help="Optional center longitude")
    p.add_argument("--extra-candidate", action="append", default=[], help="Additional candidate phrase (repeatable)")
    p.add_argument("--not-offered", action="append", default=[], help="Service explicitly not offered (repeatable)")
    p.add_argument("--depth", choices=("standard", "deep"), default="standard", help="3-pin escalation mode (default: standard adaptive)")
    p.add_argument("--max-candidates", type=int, default=DEFAULT_TARGET_CANDIDATES, help="Candidate pool cap (1..20, default 15)")
    p.add_argument("--method", choices=("standard", "live"), default="standard", help="DataForSEO Maps queue mode (default: standard)")
    p.add_argument("--allow-live", action="store_true", help="Explicit opt-in for Live Maps probes")
    p.add_argument("--dry-run", action="store_true", help="Print pre-run advisory cost estimate without network calls")
    p.add_argument("--execute", action="store_true", help="Execute live BYO DataForSEO discovery within --confirm-cost-usd")
    p.add_argument("--confirm-cost-usd", type=float, default=0.0, help="Required dollar ceiling when --execute is set")
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    p.add_argument("--output", help="Optional symlink-safe path to save JSON output")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.dry_run and args.execute:
        parser.error("Cannot combine --dry-run and --execute.")
    try:
        result = run_geogrid_plan(
            seed_keyword=args.seed_keyword,
            location=args.location,
            business_name=args.business_name,
            target_cid=args.target_cid,
            website_url=args.website_url,
            center_lat=args.center_lat,
            center_lng=args.center_lng,
            extra_candidates=args.extra_candidate,
            not_offered_terms=args.not_offered,
            depth=args.depth,
            max_candidates=args.max_candidates,
            method=args.method,
            allow_live=args.allow_live,
            execute=bool(args.execute and not args.dry_run),
            confirm_cost_usd=args.confirm_cost_usd,
        )
        if args.output:
            out_path = _safe_local_path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(format_plan_summary(result))
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Plan stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
