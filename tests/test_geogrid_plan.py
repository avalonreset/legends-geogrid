"""Hermetic unit tests for tools/geogrid_plan.py and `tools/study.py plan` (zero live spend)."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import geogrid_plan as gp  # noqa: E402
import study as study_cli  # noqa: E402


def _make_listing(
    idx: int,
    *,
    prefix: str = "biz",
    category: str = "Car detailing service",
    add_cats: list[str] | None = None,
    reviews: int = 30,
    lat: float = 25.77,
    lng: float = -80.20,
    has_street: bool = True,
    cid: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    return {
        "rank": idx,
        "name": name or f"{prefix} listing {idx}",
        "cid": cid or f"{prefix}_cid_{idx}",
        "place_id": f"{prefix}_pid_{idx}",
        "category": category,
        "additional_categories": list(add_cats or []),
        "rating": 4.7,
        "reviews": reviews,
        "latitude": lat,
        "longitude": lng,
        "address": f"{100 + idx} SW 7th St, Miami, FL" if has_street else "Miami, FL",
        "has_street_address": has_street,
    }


def _pack(
    ids: list[str],
    *,
    category: str = "Car detailing service",
    add_cats: list[str] | None = None,
    reviews: int = 30,
    lat: float = 25.77,
    lng: float = -80.20,
    has_street: bool = True,
) -> list[dict[str, Any]]:
    return [
        _make_listing(
            i + 1,
            cid=eid,
            name=f"Biz {eid}",
            category=category,
            add_cats=add_cats,
            reviews=reviews,
            lat=lat,
            lng=lng,
            has_street=has_street,
        )
        for i, eid in enumerate(ids)
    ]


class GeoGridPlanTests(unittest.TestCase):
    def test_stage0_coastal_rim_shift_rotates_45_deg_off_biscayne_bay(self) -> None:
        miami_lat, miami_lng = 25.767049, -80.1980754
        s_lat, s_lng = gp.offset_miles(miami_lat, miami_lng, 4.0, 180.0)
        self.assertTrue(gp.is_point_on_water(s_lat, s_lng))

        pins, adjusted = gp.place_three_probe_pins(miami_lat, miami_lng)
        self.assertEqual(3, len(pins))
        self.assertTrue(adjusted)
        self.assertEqual("c", pins[0].label)
        self.assertEqual(0.0, pins[1].bearing_deg)
        self.assertFalse(pins[1].adjusted)
        self.assertEqual(225.0, pins[2].bearing_deg)
        self.assertTrue(pins[2].adjusted)
        self.assertFalse(gp.is_point_on_water(pins[2].lat, pins[2].lng))

        phx_pins, phx_adj = gp.place_three_probe_pins(33.4484, -112.0740)
        self.assertFalse(phx_adj)
        self.assertEqual([0.0, 180.0], [p.bearing_deg for p in phx_pins[1:]])

    def test_stage0_ssrf_and_input_validation_guards(self) -> None:
        for bad_kwargs in (
            {"seed_keyword": "a", "location": "Miami, FL"},
            {"seed_keyword": "car detailing", "location": ""},
            {"seed_keyword": "car detailing", "location": "Miami, FL", "center_lat": 25.7},
            {"seed_keyword": "car detailing", "location": "Miami, FL", "center_lat": True, "center_lng": -80.2},
            {"seed_keyword": "car detailing", "location": "Miami, FL", "center_lat": float("nan"), "center_lng": -80.2},
            {"seed_keyword": "car detailing", "location": "Miami, FL", "website_url": "http://127.0.0.1/admin"},
            {"seed_keyword": "car detailing", "location": "Miami, FL", "website_url": "http://169.254.169.254/latest"},
            {"seed_keyword": "car detailing", "location": "Miami, FL", "website_url": "file:///etc/passwd"},
            {"seed_keyword": "car detailing", "location": "Miami, FL", "max_candidates": 25},
        ):
            with self.assertRaises(ValueError):
                gp.run_geogrid_plan(**bad_kwargs)  # type: ignore[arg-type]

    def test_stage1_candidate_pool_excludes_noise_and_caps_at_20(self) -> None:
        head_items = [
            _make_listing(i, category="Car detailing service", add_cats=["Car wash", "Ceramic coating"])
            for i in range(1, 15)
        ]
        related = [
            {"keyword": "ceramic coating", "local_pack": True},
            {"keyword": "mobile car detailing", "local_pack": True},
            {"keyword": "car detailing jobs", "local_pack": True},
            {"keyword": "car detailing salary", "local_pack": True},
            {"keyword": "car detailing cost", "local_pack": True},
            {"keyword": "how much car detailing", "local_pack": True},
            {"keyword": "car detailing recipe", "local_pack": True},
            {"keyword": "non local blog query", "local_pack": False},
        ] + [{"keyword": f"detailing variant {i}", "local_pack": True} for i in range(25)]

        pool = gp.assemble_candidate_pool(
            "car detailing",
            location="Miami, FL",
            head_items=head_items,
            related_items=related,
            extra_candidates=["paint protection film"],
        )
        self.assertLessEqual(len(pool), 20)
        self.assertEqual("car detailing", pool[0])
        self.assertIn("paint protection film", pool)
        self.assertIn("ceramic coating", pool)
        for bad in (
            "car detailing jobs",
            "car detailing salary",
            "car detailing cost",
            "how much car detailing",
            "car detailing recipe",
            "non local blog query",
        ):
            self.assertNotIn(bad, pool)

    def test_stage2_boundary_escalation_band(self) -> None:
        base = [f"e_{i}" for i in range(1, 21)]
        dup = base[:18] + ["d1", "d2"]
        bnd = base[:11] + [f"b_{i}" for i in range(1, 10)]
        dis = [f"x_{i}" for i in range(1, 21)]
        escalated = gp.boundary_candidates_from_center(
            ["seed", "dup", "bnd", "dis"],
            {"seed": _pack(base), "dup": _pack(dup), "bnd": _pack(bnd), "dis": _pack(dis)},
        )
        self.assertIn("bnd", escalated)
        self.assertIn("seed", escalated)
        self.assertNotIn("dis", escalated)

    def test_stage4_parse_keyword_overview_ignores_normalized_clickstream(self) -> None:
        envelope = {
            "status_code": 20000,
            "cost": 0.02448,
            "tasks": [
                {
                    "status_code": 20000,
                    "cost": 0.02448,
                    "result": [
                        {
                            "items": [
                                {
                                    "keyword": "personal injury lawyer miami",
                                    "keyword_info": {"search_volume": None, "cpc": None},
                                    "keyword_info_normalized_with_clickstream": {"search_volume": None},
                                    "clickstream_keyword_info": {"search_volume": 206},
                                },
                                {
                                    "keyword": "bail bonds miami",
                                    "keyword_info": {"search_volume": None, "cpc": None},
                                    "keyword_info_normalized_with_clickstream": {"search_volume": 99999},
                                    "clickstream_keyword_info": {"search_volume": 0},
                                },
                            ]
                        }
                    ],
                }
            ],
        }
        parsed = gp.parse_keyword_overview_envelope(envelope)
        by_kw = {r["keyword"]: r for r in parsed["items"]}
        self.assertIsNone(by_kw["personal injury lawyer miami"]["search_volume"])
        self.assertEqual(206, by_kw["personal injury lawyer miami"]["clickstream_search_volume"])
        self.assertEqual(0, by_kw["bail bonds miami"]["clickstream_search_volume"])

    def test_stage4_demand_hygiene_collision_fingerprint_est_clickstream_and_hole(self) -> None:
        cands_p = ["cheesesteak", "philly cheesesteak", "best cheesesteak"]
        clusters_p = [["cheesesteak", "philly cheesesteak"], ["best cheesesteak"]]
        raw_local_p = {
            "cheesesteak": {"search_volume": 301_000, "cpc_usd": 1.20},
            "philly cheesesteak": {"search_volume": 4_400, "cpc_usd": 1.40},
            "best cheesesteak": {"search_volume": 60_500, "cpc_usd": 1.10},
        }
        raw_bare_p = {
            "cheesesteak": {"search_volume": 135_000, "cpc_usd": 1.20},
            "philly cheesesteak": {"search_volume": 550_000, "cpc_usd": 1.40},
            "best cheesesteak": {"search_volume": 2_400, "cpc_usd": 1.10},
        }
        clean_p = gp.apply_demand_hygiene(cands_p, clusters_p, raw_local_p, raw_bare_p)
        self.assertIn("COLLISION", clean_p["cheesesteak"].flags)
        self.assertIn("EST", clean_p["cheesesteak"].flags)
        self.assertEqual("ad_planner_estimated", clean_p["cheesesteak"].volume_source)
        self.assertEqual(round(135_000 * (4_400 / 550_000)), clean_p["cheesesteak"].volume)

        cands_m = ["car detailing", "mobile detailing", "mobile car detailing", "pi lawyer", "bail bonds"]
        clusters_m = [["car detailing"], ["mobile detailing", "mobile car detailing"], ["pi lawyer"], ["bail bonds"]]
        raw_local_m = {
            "car detailing": {"search_volume": 1_600, "cpc_usd": 2.66},
            "mobile detailing": {"search_volume": 1_600, "cpc_usd": 2.66},
            "mobile car detailing": {"search_volume": 320, "cpc_usd": 3.78},
            "pi lawyer": {"search_volume": None, "cpc_usd": None},
            "bail bonds": {"search_volume": None, "cpc_usd": None},
        }
        raw_bare_m = {
            "car detailing": {"search_volume": 135_000, "cpc_usd": 2.66},
            "mobile detailing": {"search_volume": 27_100, "cpc_usd": 2.66},
            "mobile car detailing": {"search_volume": 60_500, "cpc_usd": 3.78},
            "pi lawyer": {"search_volume": None, "cpc_usd": None},
            "bail bonds": {"search_volume": None, "cpc_usd": None},
        }
        raw_cs_m = {
            "pi lawyer": {"clickstream_search_volume": 206},
            "bail bonds": {"clickstream_search_volume": 0},
        }
        clean_m = gp.apply_demand_hygiene(cands_m, clusters_m, raw_local_m, raw_bare_m, raw_cs_m)
        self.assertEqual(1_600, clean_m["car detailing"].volume)
        self.assertIn("FINGERPRINT", clean_m["mobile detailing"].flags)
        self.assertIn("EST", clean_m["mobile detailing"].flags)
        self.assertEqual("clickstream_fallback", clean_m["pi lawyer"].volume_source)
        self.assertEqual(206, clean_m["pi lawyer"].volume)
        self.assertEqual("policy_restricted_maps_proxy", clean_m["bail bonds"].volume_source)
        self.assertIsNone(clean_m["bail bonds"].volume)
        self.assertIn("HOLE", clean_m["bail bonds"].flags)

    def test_stage3_to_7_full_scoring_pruning_tiering_and_coastal_geometry(self) -> None:
        miami_lat, miami_lng = 25.767049, -80.1980754
        pins, adj = gp.place_three_probe_pins(miami_lat, miami_lng)
        self.assertTrue(adj)

        head_ids = [f"cd_{i}" for i in range(1, 21)]
        head_ids[7] = "10367868874034935802"
        auto_ids = head_ids[:18] + ["cd_extra1", "cd_extra2"]
        wash_ids = [f"cw_{i}" for i in range(1, 21)]
        ceramic_ids = [f"cc_{i}" for i in range(1, 21)]
        mobile_ids = [f"mb_{i}" for i in range(1, 21)]
        tint_ids = [f"wt_{i}" for i in range(1, 21)]
        thin_ids = ["th_1", "th_2"]
        lowval_ids = [f"lv_{i}" for i in range(1, 21)]
        overlap_t3_ids = head_ids[:7] + [f"ov_{i}" for i in range(1, 14)]

        comp_lat, comp_lng = gp.offset_miles(miami_lat, miami_lng, 3.18, 270.0)
        r1_lat, r1_lng = gp.offset_miles(pins[1].lat, pins[1].lng, 3.18, 270.0)
        r2_lat, r2_lng = gp.offset_miles(pins[2].lat, pins[2].lng, 3.18, 270.0)

        def _p3(ids: list[str], *, cat: str = "Car detailing service", rev: int = 28) -> dict[str, list[dict[str, Any]]]:
            return {
                "c": _pack(ids, category=cat, reviews=rev, lat=comp_lat, lng=comp_lng),
                "rim1": _pack(ids, category=cat, reviews=rev, lat=r1_lat, lng=r1_lng),
                "rim2": _pack(ids, category=cat, reviews=rev, lat=r2_lat, lng=r2_lng),
            }

        maps_probes = {
            "car detailing": _p3(head_ids, cat="Car detailing service", rev=28),
            "auto detailing": _p3(auto_ids, cat="Car detailing service", rev=28),
            "car wash": _p3(wash_ids, cat="Car wash", rev=385),
            "ceramic coating": _p3(ceramic_ids, cat="Car detailing service", rev=26),
            "mobile detailing": _p3(mobile_ids, cat="Car detailing service", rev=25),
            "window tinting": _p3(tint_ids, cat="Window tinting service", rev=60),
            "headlight restoration": _p3(thin_ids, cat="Car detailing service", rev=20),
            "engine bay cleaning": _p3(lowval_ids, cat="Car detailing service", rev=20),
            "interior detailing": _p3(overlap_t3_ids, cat="Car detailing service", rev=30),
        }
        raw_local = {
            "car detailing": {"search_volume": 1_600, "cpc_usd": 2.66, "yearly_trend_pct": 85.0},
            "auto detailing": {"search_volume": 720, "cpc_usd": 2.50, "yearly_trend_pct": 20.0},
            "car wash": {"search_volume": 2_400, "cpc_usd": 1.80, "yearly_trend_pct": -22.0},
            "ceramic coating": {"search_volume": 170, "cpc_usd": 15.85, "yearly_trend_pct": 436.0},
            "mobile detailing": {"search_volume": 1_600, "cpc_usd": 2.66},
            "window tinting": {"search_volume": 880, "cpc_usd": 5.62},
            "headlight restoration": {"search_volume": 390, "cpc_usd": 8.00},
            "engine bay cleaning": {"search_volume": 10, "cpc_usd": 1.00},
            "interior detailing": {"search_volume": 480, "cpc_usd": 3.00},
        }
        raw_bare = {k: {"search_volume": 100_000, "cpc_usd": v["cpc_usd"]} for k, v in raw_local.items()}

        out = gp.compute_geogrid_plan(
            seed_keyword="car detailing",
            location="Miami, FL",
            center_lat=miami_lat,
            center_lng=miami_lng,
            probe_pins=pins,
            coastal_rim_adjusted=adj,
            candidates=list(maps_probes.keys()),
            maps_probes=maps_probes,
            raw_local_demand=raw_local,
            raw_bare_demand=raw_bare,
            business_name="RESERVE Detailing",
            target_cid="10367868874034935802",
            target_profile={
                "business_name": "RESERVE Detailing",
                "primary_category": "Car wash",
                "additional_categories": ["Car detailing service"],
                "rating": 4.9,
                "reviews": 3078,
            },
            not_offered_terms=["mobile detailing"],
        )

        self.assertEqual("business", out["mode"])
        self.assertEqual("car detailing", out["tier1"]["query"])
        self.assertIn("auto detailing", out["tier1"]["collapsed_synonyms"])
        self.assertEqual(8, out["tier1"]["target_center_rank"])
        self.assertEqual(1.0, out["tier1"]["subscores"]["rank_gap_G"])
        self.assertEqual({"car wash", "ceramic coating"}, {c["query"] for c in out["tier2"]})
        cer = next(c for c in out["tier2"] if c["query"] == "ceramic coating")
        self.assertAlmostEqual(1.0 / 3.0, cer["subscores"]["momentum_M"], places=3)
        self.assertEqual(["interior detailing"], [c["query"] for c in out["tier3"]])

        pruned_by_q = {p["query"]: p["reason"] for p in out["pruned"]}
        self.assertEqual("PRUNED_NOT_OFFERED", pruned_by_q["mobile detailing"])
        self.assertEqual("PRUNED_OUT_OF_CATEGORY", pruned_by_q["window tinting"])
        self.assertEqual("PRUNED_THIN_PACK", pruned_by_q["headlight restoration"])
        self.assertEqual("PRUNED_LOW_VALUE", pruned_by_q["engine bay cleaning"])

        geom = out["recommended_geometry"]
        self.assertEqual("coastal_clipped", geom["geometry_class"])
        self.assertTrue(geom["land_clipping_recommended"])
        self.assertGreaterEqual(geom["water_pin_fraction_unclipped"], 0.15)
        self.assertTrue(6.0 <= geom["starter_radius_km"] <= 10.0)
        self.assertEqual(3, len(out["launch_actions"]))

    def test_stage7_sab_metro_and_adaptive_radius_clamp(self) -> None:
        phx_lat, phx_lng = 33.4484, -112.0740
        pins, adj = gp.place_three_probe_pins(phx_lat, phx_lng)
        self.assertFalse(adj)

        far_lat, far_lng = gp.offset_miles(phx_lat, phx_lng, 15.07, 90.0)
        r1_lat, r1_lng = gp.offset_miles(pins[1].lat, pins[1].lng, 15.07, 90.0)
        r2_lat, r2_lng = gp.offset_miles(pins[2].lat, pins[2].lng, 15.07, 90.0)

        center_pack = [
            _make_listing(i, cid=f"hvac_{i}", category="HVAC contractor", reviews=120, lat=far_lat, lng=far_lng, has_street=(i % 2 == 0))
            for i in range(1, 21)
        ]
        maps_probes = {
            "ac repair": {
                "c": center_pack,
                "rim1": _pack([f"hvac_{i}" for i in range(1, 21)], category="HVAC contractor", lat=r1_lat, lng=r1_lng),
                "rim2": _pack([f"hvac_{i}" for i in range(1, 21)], category="HVAC contractor", lat=r2_lat, lng=r2_lng),
            },
            "furnace repair": {
                "c": _pack([f"fr_{i}" for i in range(1, 21)], category="HVAC contractor", lat=far_lat, lng=far_lng),
                "rim1": _pack([f"fr_{i}" for i in range(1, 21)], category="HVAC contractor", lat=r1_lat, lng=r1_lng),
                "rim2": _pack([f"fr_{i}" for i in range(1, 21)], category="HVAC contractor", lat=r2_lat, lng=r2_lng),
            },
        }
        out = gp.compute_geogrid_plan(
            seed_keyword="ac repair",
            location="Phoenix, AZ",
            center_lat=phx_lat,
            center_lng=phx_lng,
            probe_pins=pins,
            coastal_rim_adjusted=False,
            candidates=["ac repair", "furnace repair"],
            maps_probes=maps_probes,
            raw_local_demand={"ac repair": {"search_volume": 4_400, "cpc_usd": 14.0}, "furnace repair": {"search_volume": 880, "cpc_usd": 12.0}},
            raw_bare_demand={"ac repair": {"search_volume": 200_000, "cpc_usd": 14.0}, "furnace repair": {"search_volume": 60_000, "cpc_usd": 12.0}},
        )
        geom = out["recommended_geometry"]
        self.assertEqual("sab_metro", geom["geometry_class"])
        self.assertAlmostEqual(0.50, geom["sab_hidden_address_share"], places=2)
        self.assertAlmostEqual(round(1.5 * 15.07 * 1.60934, 1), geom["starter_radius_km"], delta=0.2)
        self.assertEqual(5, geom["recommended_rings"])
        self.assertEqual(12, geom["recommended_zoom"])

    def test_end_to_end_mocked_transport_and_selective_clickstream(self) -> None:
        calls: list[tuple[str, dict[str, Any]]] = []

        def _mock_transport(op: str, payload: dict[str, Any]) -> dict[str, Any]:
            calls.append((op, dict(payload)))
            if op == "business_profile":
                return {
                    "found": True,
                    "business_name": "RESERVE Detailing",
                    "cid": "10367868874034935802",
                    "latitude": 25.767049,
                    "longitude": -80.1980754,
                    "primary_category": "Car wash",
                    "additional_categories": ["Car detailing service"],
                    "rating": 4.9,
                    "reviews": 3078,
                    "place_topics": ["ceramic coating"],
                }
            if op == "related_keywords":
                return {
                    "items": [
                        {"keyword": "auto detailing", "local_pack": True},
                        {"keyword": "ceramic coating", "local_pack": True},
                        {"keyword": "mobile detailing", "local_pack": True},
                        {"keyword": "restricted service", "local_pack": True},
                    ]
                }
            if op == "maps_pack":
                q = str(payload.get("keyword") or "").lower()
                lat = float(payload.get("lat") or 25.767)
                lng = float(payload.get("lng") or -80.198)
                if "detailing" in q and "mobile" not in q:
                    ids = [f"cd_{i}" for i in range(1, 21)]
                    ids[4] = "10367868874034935802"
                    return {"items": _pack(ids, category="Car detailing service", lat=lat, lng=lng - 0.04)}
                if "ceramic" in q:
                    return {"items": _pack([f"cc_{i}" for i in range(1, 21)], category="Car detailing service", lat=lat, lng=lng - 0.04)}
                if "restricted" in q:
                    return {"items": _pack([f"rs_{i}" for i in range(1, 21)], category="Car detailing service", lat=lat, lng=lng - 0.04)}
                return {"items": _pack([f"mb_{i}" for i in range(1, 21)], category="Car detailing service", lat=lat, lng=lng - 0.04)}
            if op == "keyword_demand":
                include_cs = bool(payload.get("include_clickstream_data", False))
                items = []
                for kw in payload["keywords"]:
                    if "restricted" in kw:
                        items.append({
                            "keyword": kw,
                            "search_volume": None,
                            "clickstream_search_volume": 240 if include_cs else None,
                            "cpc_usd": None,
                        })
                    elif "ceramic" in kw:
                        items.append({"keyword": kw, "search_volume": 170 if "miami" in kw else 45_000, "cpc_usd": 15.85})
                    else:
                        items.append({"keyword": kw, "search_volume": 1_600 if "miami" in kw else 135_000, "cpc_usd": 2.66})
                return {"items": items}
            raise AssertionError(f"Unexpected op: {op}")

        def _fake_site(_url: str) -> dict[str, Any]:
            return {
                "status_code": 200,
                "headings": ["Ceramic Coating", "Paint Correction"],
                "text": "Studio-only car detailing. We do not offer mobile detailing.",
            }

        with patch.object(gp, "_validate_public_url", side_effect=lambda u: u):
            res = gp.run_geogrid_plan(
                seed_keyword="car detailing",
                location="Miami, FL",
                business_name="RESERVE Detailing",
                website_url="https://example.com/",
                not_offered_terms=["mobile detailing"],
                max_candidates=8,
                execute=True,
                confirm_cost_usd=1.0,
                transport=_mock_transport,
                website_fetcher=_fake_site,
            )

        self.assertEqual("completed", res["status"])
        self.assertEqual("car detailing", res["tier1"]["query"])
        self.assertTrue(res["center_coordinates"]["coastal_rim_adjusted"])
        self.assertIn("evidence_bundle_sha256", res["provenance"])
        # Clickstream fallback was selectively called ONLY for restricted service
        cs_calls = [p for op, p in calls if op == "keyword_demand" and p.get("include_clickstream_data")]
        self.assertEqual(1, len(cs_calls))
        self.assertEqual(["restricted service miami"], cs_calls[0]["keywords"])
        # Never calls keywords_for_site or keyword_ideas
        self.assertTrue(all(op not in ("keywords_for_site", "keyword_ideas") for op, _ in calls))

    def test_cli_dry_run_and_study_plan_subcommand(self) -> None:
        # Direct CLI --dry-run --json
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = gp.main(["--seed-keyword", "car detailing", "--location", "Miami, FL", "--dry-run", "--json"])
        self.assertEqual(0, rc)
        payload = json.loads(buf.getvalue())
        self.assertEqual("dry_run_estimate", payload["status"])
        self.assertTrue(payload["estimate"]["advisory_only"])
        self.assertGreater(payload["estimate"]["estimated_cost_usd"], 0)

        # study.py plan subcommand with --dry-run --json and --output
        with tempfile.TemporaryDirectory() as tmp:
            out_file = Path(tmp) / "plan-estimate.json"
            buf2 = io.StringIO()
            with redirect_stdout(buf2):
                rc2 = study_cli.main([
                    "plan",
                    "--seed-keyword", "car detailing",
                    "--location", "Miami, FL",
                    "--dry-run",
                    "--json",
                    "--output", str(out_file),
                ])
            self.assertEqual(0, rc2)
            self.assertTrue(out_file.is_file())
            saved = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual("dry_run_estimate", saved["status"])

        # Live method without --allow-live is blocked
        with self.assertRaises(ValueError):
            gp.run_geogrid_plan(
                seed_keyword="car detailing",
                location="Miami, FL",
                method="live",
                execute=True,
                confirm_cost_usd=1.0,
            )

    def test_doctor_via_gambit_onboarding_json(self) -> None:
        import geogrid_doctor as doc

        buf = io.StringIO()
        with patch.object(sys, "argv", ["geogrid_doctor.py", "--via-gambit", "--json"]):
            with redirect_stdout(buf):
                rc = doc.main()
        self.assertEqual(0, rc)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["ok"])
        gambit = payload["legends_gambit"]
        self.assertEqual("legends-gambit", gambit["service"])
        self.assertTrue(gambit["byo_local_free"])
        self.assertEqual("https://gambit.cto-legends.com/wallet", gambit["wallet_url"])
        self.assertIn("$10", gambit["starter_pack"])
        raw = buf.getvalue()
        self.assertNotIn("Legends" + " Recon", raw)
        self.assertNotIn("legends" + " gambit", raw.lower())

    def test_budget_ceiling_fails_closed_instead_of_completing_with_fabricated_holes(self) -> None:
        # DfsByoTransport._call_api itself raises BudgetCeilingError when remaining budget is exceeded.
        tx = gp.DfsByoTransport(method="standard", max_cost_usd=0.01)
        tx.spent_usd = 0.009
        with self.assertRaises(gp.BudgetCeilingError):
            tx._call_api("/dataforseo_labs/google/keyword_overview/live", [], estimated_usd=0.01)

        # When BudgetCeilingError trips in Stage 4 (keyword_demand), run_geogrid_plan must fail closed
        # rather than swallowing the error and returning status="completed" with fabricated HOLE flags.
        def _stage4_ceiling_transport(op: str, payload: dict[str, Any]) -> dict[str, Any]:
            if op == "related_keywords":
                return {"items": [{"keyword": "ceramic coating", "local_pack": True}]}
            if op == "maps_pack":
                lat = float(payload.get("lat") or 25.767)
                lng = float(payload.get("lng") or -80.198)
                return {"items": _pack([f"cd_{i}" for i in range(1, 21)], category="Car detailing service", lat=lat, lng=lng - 0.04)}
            if op == "keyword_demand":
                raise gp.BudgetCeilingError("Advisory budget ceiling $0.0600 reached before keyword_overview.")
            raise AssertionError(f"Unexpected op: {op}")

        with self.assertRaises(gp.BudgetCeilingError):
            gp.run_geogrid_plan(
                seed_keyword="car detailing",
                location="Miami, FL",
                max_candidates=4,
                execute=True,
                confirm_cost_usd=1.0,
                transport=_stage4_ceiling_transport,
            )

        # Also verify Stage 2 maps_pack probe and Stage 0a business_profile propagate BudgetCeilingError.
        maps_calls = 0

        def _stage2_ceiling_transport(op: str, payload: dict[str, Any]) -> dict[str, Any]:
            nonlocal maps_calls
            if op == "related_keywords":
                return {"items": [{"keyword": "ceramic coating", "local_pack": True}]}
            if op == "maps_pack":
                maps_calls += 1
                if maps_calls > 1:
                    raise gp.BudgetCeilingError("Budget ceiling reached during Stage 2 probe.")
                return {"items": _pack([f"cd_{i}" for i in range(1, 21)], lat=25.767, lng=-80.23)}
            raise AssertionError(f"Unexpected op: {op}")

        with self.assertRaises(gp.BudgetCeilingError):
            gp.run_geogrid_plan(
                seed_keyword="car detailing",
                location="Miami, FL",
                max_candidates=4,
                execute=True,
                confirm_cost_usd=1.0,
                transport=_stage2_ceiling_transport,
            )

        def _stage0a_ceiling_transport(op: str, payload: dict[str, Any]) -> dict[str, Any]:
            if op == "business_profile":
                raise gp.BudgetCeilingError("Budget ceiling reached during Stage 0a.")
            raise AssertionError(f"Unexpected op: {op}")

        with self.assertRaises(gp.BudgetCeilingError):
            gp.run_geogrid_plan(
                seed_keyword="car detailing",
                location="Miami, FL",
                business_name="RESERVE Detailing",
                max_candidates=4,
                execute=True,
                confirm_cost_usd=1.0,
                transport=_stage0a_ceiling_transport,
            )


if __name__ == "__main__":
    unittest.main()
