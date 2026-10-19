"""Evidence collection for individual Business Profile name review.

Standard queue only. A lexical signal is a research prompt, never a violation.
No profile edits or report submission endpoints are implemented.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
from urllib.parse import urlparse, urljoin, quote
import urllib.request

POST = "/business_data/google/my_business_info/task_post"
GET = "/business_data/google/my_business_info/task_get/"
COST = .0015
POLICY = "https://support.google.com/business/answer/3038177?hl=en"


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if exclusive else "w", encoding="utf-8") as out:
        json.dump(value, out, indent=2, ensure_ascii=False, allow_nan=False)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_seed(root):
    seed = load(Path(root) / "seed.json")
    study = Path(seed["study"])
    if not study.is_absolute():
        study = Path(__file__).resolve().parents[1] / study
    if not seed.get("study_sha256") or sha(study) != seed["study_sha256"]:
        raise ValueError("Study evidence changed or is not hash-bound")
    if load(study)["evidence"]["plan_sha256"] != seed["study_plan_sha256"]:
        raise ValueError("Study plan fingerprint changed")
    cids = [c["cid"] for c in seed["cases"]]
    if len(cids) != len(set(cids)) or not all(re.fullmatch(r"\d+", str(c)) for c in cids):
        raise ValueError("Invalid or duplicate profile identity")
    return seed


def fresh(timestamp, days=7):
    try:
        observed = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        delta = dt.datetime.now(dt.timezone.utc) - observed
        return dt.timedelta(0) <= delta <= dt.timedelta(days=days)
    except (ValueError, TypeError, AttributeError):
        return False


def seed_from_study(study, include_cids=(), only_cids=()):
    """Select observed profiles; explicit historical IDs never alter an existing run."""
    raw = load(study)
    identities = {str(b["cid"]): b for b in raw["factions"] if b.get("cid")}
    included, only = set(map(str, include_cids)), set(map(str, only_cids))
    if any(not re.fullmatch(r"\d+", cid) for cid in included | only):
        raise ValueError("Explicit profile IDs must be numeric CIDs")
    cases = {}
    def ensure(cid, item):
        b = identities.get(cid, {})
        return cases.setdefault(cid, {
            "id": b.get("faction_id") or f"cid:{cid}", "cid": cid,
            "name": item.get("title") or b.get("name") or b.get("title") or f"Profile {cid}",
            "address": item.get("address") or b.get("address"),
            "lat": item.get("latitude") if item.get("latitude") is not None else b.get("lat"),
            "lng": item.get("longitude") if item.get("longitude") is not None else b.get("lng"),
            "domain": item.get("domain") or b.get("domain"), "target": bool(b.get("is_target")),
            "wins_by_query": {}, "total_wins": 0, "returned_observations": 0,
        })
    for p in raw["points"]:
        for q, obs in p["by_lane"].items():
            if obs.get("status") in ("missing", "error", "pending", "empty_results", "provider_error"):
                continue
            seen = set()
            winner = next((i for i in obs.get("top_items", []) if (i.get("rank") or i.get("rank_group")) == 1), None)
            for item in obs.get("top_items", []):
                cid = str(item.get("cid", ""))
                if not cid.isdigit() or cid in seen:
                    continue
                seen.add(cid)
                c = ensure(cid, item)
                c["returned_observations"] += 1
            if winner and str(winner.get("cid", "")).isdigit():
                c = ensure(str(winner["cid"]), winner)
                c["wins_by_query"][q] = c["wins_by_query"].get(q, 0) + 1
                c["total_wins"] += 1
    unknown = (included | only) - (set(cases) | set(identities))
    if unknown:
        raise ValueError("Unknown observed profile CID(s): " + ", ".join(sorted(unknown)))
    for cid in included | only:
        ensure(cid, {})
    selected = only if only else {cid for cid, c in cases.items() if c["total_wins"]} | included
    return {"study": str(study), "study_sha256": sha(study),
            "study_plan_sha256": raw["evidence"]["plan_sha256"],
            "generated_at": now(), "cases": sorted((cases[cid] for cid in selected), key=lambda c: (-c["total_wins"], c["id"]))}


def submit(root, api, budget):
    """Exclusive reservations prevent ambiguous POSTs from being bought twice."""
    root = Path(root)
    if not math.isfinite(budget) or budget < 0:
        raise ValueError("Cost ceiling must be finite and nonnegative")
    seed = validate_seed(root)
    cases = seed["cases"]
    lock = root / "submit.lock"
    with lock.open("x") as f:
        f.write(now())
    try:
        spent = sum(float(load(p)["response"].get("cost") or 0) for p in root.glob("batch-*-receipt.json"))
        for start in range(0, len(cases), 100):
            batch = cases[start:start + 100]
            intent, receipt = root / f"batch-{start:04d}-intent.json", root / f"batch-{start:04d}-receipt.json"
            tasks = [{"keyword": f"cid:{c['cid']}", "language_code": "en",
                      "location_code": 2840, "priority": 1, "tag": c["cid"]} for c in batch]
            if receipt.exists():
                if load(intent)["body"] != tasks:
                    raise ValueError("Changed seed after submission")
                continue
            if intent.exists():
                raise ValueError("Unresolved submission reservation; reconcile provider task IDs before resubmitting")
            estimate = round(len(tasks) * COST, 6)
            if spent + estimate > budget + 1e-9:
                raise ValueError("Cumulative cost ceiling exceeded")
            save(intent, {"endpoint": POST, "body": tasks, "estimated_usd": estimate, "reserved_at": now()}, True)
            response = api(POST, tasks, confirm=True, consumer="geogrid-name-review",
                           estimated_cost_usd=estimate, max_cost_usd=estimate, timeout=90)
            save(receipt, {"observed_at": now(), "request_sha256": sha(intent), "response": response}, True)
            validate_receipt(root, receipt)
            spent += float(response.get("cost") or 0)
            print(json.dumps({"submitted": len(tasks), "cumulative_cost_usd": round(spent, 6)}), flush=True)
    finally:
        lock.unlink()


def validate_receipt(root, path):
    receipt = load(path)
    intent = Path(str(path).replace("-receipt.json", "-intent.json"))
    if receipt["request_sha256"] != sha(intent):
        raise ValueError("Submission evidence changed")
    body = load(intent)["body"]
    response = receipt["response"]
    tasks = response.get("tasks") or []
    if response.get("status_code") != 20000 or len(tasks) != len(body):
        raise ValueError("Submission acknowledgement incomplete")
    expected = {t["tag"]: t for t in body}
    if len({t.get("data", {}).get("tag") for t in tasks}) != len(body):
        raise ValueError("Duplicate/missing queue acknowledgement")
    if len({t.get("id") for t in tasks}) != len(body):
        raise ValueError("Duplicate provider task IDs")
    for t in tasks:
        data = t.get("data") or {}
        if (data.get("tag") not in expected or data.get("keyword") != expected[data["tag"]]["keyword"]
                or t.get("status_code") != 20100 or not re.fullmatch(r"[a-zA-Z0-9-]+", str(t.get("id", "")))):
            raise ValueError("Queue identity or acceptance mismatch")
    if abs(sum(float(t.get("cost") or 0) for t in tasks) - float(response.get("cost") or 0)) > 1e-8:
        raise ValueError("Provider cost mismatch")
    return tasks


def retrieve(root, api):
    root = Path(root)
    validate_seed(root)
    tasks = [t for p in root.glob("batch-*-receipt.json") for t in validate_receipt(root, p)]
    if len({t["id"] for t in tasks}) != len(tasks):
        raise ValueError("Duplicate provider task IDs across batches")
    def one(t):
        path = root / "profiles" / f"{t['data']['tag']}.json"
        if path.exists():
            saved = load(path)["response"]["tasks"][0]
            if saved["id"] != t["id"]:
                raise ValueError("Saved result task identity mismatch")
            if saved["status_code"] == 20000:
                return saved["status_code"]
        response = api(GET + t["id"], confirm=True, consumer="geogrid-name-review",
                       estimated_cost_usd=0, max_cost_usd=0, timeout=90)
        received = response.get("tasks") or []
        if len(received) != 1 or received[0].get("id") != t["id"]:
            raise ValueError("Result task identity mismatch")
        save(path, {"checked_at": now(), "endpoint": GET + t["id"], "response": response})
        return received[0]["status_code"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        codes = list(pool.map(one, tasks))
    summary = {"expected": len(load(root / "seed.json")["cases"]), "submitted": len(tasks),
               "complete": codes.count(20000), "statuses": {str(c): codes.count(c) for c in sorted(set(codes))}}
    save(root / "collection-status.json", summary)
    print(json.dumps(summary), flush=True)
    return summary


def profile_item(path, cid):
    if not path.exists():
        return None, "not_collected", None
    data = load(path)
    tasks = data["response"].get("tasks") or []
    if not tasks or tasks[0].get("status_code") != 20000:
        return None, "pending_or_failed", data.get("checked_at")
    items = [i for r in tasks[0].get("result") or [] for i in r.get("items") or []]
    matching = [i for i in items if str(i.get("cid")) == str(cid)]
    if len(matching) != 1:
        return None, "identity_unresolved", data.get("checked_at")
    return matching[0], "complete", data.get("checked_at")


class BrandingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.names, self.text, self.jsonld = [], [], []
        self.title, self.in_title, self.script, self.ignore = "", False, None, 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self.ignore += 1
        if tag == "script" and a.get("type") == "application/ld+json":
            self.script = []
        if tag == "title":
            self.in_title = True
        if tag == "meta" and a.get("property") == "og:site_name" and a.get("content"):
            self.names.append({"name": a["content"], "source": "og:site_name"})
        if tag == "img" and "logo" in " ".join(str(a.get(k, "")) for k in ("class", "id", "src", "alt")).lower() and a.get("alt"):
            self.names.append({"name": a["alt"], "source": "logo alt text"})
    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "script" and self.script is not None:
            self.jsonld.append("".join(self.script))
            self.script = None
        if tag in ("script", "style", "noscript"):
            self.ignore = max(0, self.ignore - 1)
    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.script is not None:
            self.script.append(data)
        if not self.ignore and data.strip():
            self.text.append(data.strip())
    def finish(self):
        def visit(value):
            if isinstance(value, list):
                for v in value:
                    visit(v)
            if isinstance(value, dict):
                types = value.get("@type") or []
                if isinstance(types, str):
                    types = [types]
                if any(t in ("Organization", "LocalBusiness", "HVACBusiness", "HomeAndConstructionBusiness",
                              "Plumber", "Electrician", "Corporation") for t in types):
                    for k in ("name", "legalName", "alternateName"):
                        if isinstance(value.get(k), str):
                            self.names.append({"name": value[k], "source": f"JSON-LD {k}"})
                for v in value.values():
                    if isinstance(v, (list, dict)):
                        visit(v)
        for s in self.jsonld:
            try:
                visit(json.loads(s))
            except (ValueError, TypeError):
                pass
        seen = set()
        self.names = [n for n in self.names if not (tuple(n.values()) in seen or seen.add(tuple(n.values())))]
        return {"title": self.title.strip(), "names": self.names,
                "text": " ".join(self.text)[:120000]}


def public_url(url):
    p = urlparse(url)
    if p.scheme not in ("https", "http") or not p.hostname or p.username or p.password or p.port not in (None, 80, 443):
        raise ValueError("Unsupported public URL")
    addresses = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("Not a public website")
    return url


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, public_url(newurl))


def capture_site(url, root):
    key = hashlib.sha256(url.encode()).hexdigest()
    path = root / "websites" / f"{key}.json"
    if path.exists():
        cached = load(path)
        if fresh(cached.get("checked_at")):
            return cached
        # Preserve stale captures; a new folder is required for a refreshed audit.
        return {**cached, "status": "stale"}
    record = {"url": url, "checked_at": now(), "status": "unavailable", "names": []}
    try:
        request = urllib.request.Request(public_url(url), headers={"User-Agent": "Mozilla/5.0 (compatible; GeoGridEvidence/1.0)"})
        with urllib.request.build_opener(PublicRedirect).open(request, timeout=25) as response:
            if "html" not in response.headers.get("Content-Type", ""):
                raise ValueError("Not HTML")
            raw = response.read(3_000_001)
            if len(raw) > 3_000_000:
                raise ValueError("Page exceeds evidence limit")
            record["url"] = response.url
            text = raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
        html_path = root / "websites" / f"{key}.html"
        html_path.parent.mkdir(exist_ok=True)
        html_path.write_bytes(raw)
        parser = BrandingParser()
        parser.feed(text)
        record.update(parser.finish())
        record.update(status="captured", evidence_path=str(html_path.relative_to(root)), sha256=sha(html_path))
    except Exception as e:
        record["error_type"] = type(e).__name__
    save(path, record)
    return record


def fetch_websites(root):
    root = Path(root)
    validate_seed(root)
    urls = set()
    for c in load(root / "seed.json")["cases"]:
        item, _, _ = profile_item(root / "profiles" / f"{c['cid']}.json", c["cid"])
        url = (item or {}).get("url")
        if url and url.startswith(("https://", "http://")):
            urls.add(url)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda url: capture_site(url, root), sorted(urls)))
    print(json.dumps({"websites": len(results), "captured": sum(r["status"] == "captured" for r in results)}))


def normalize_name(name):
    return " ".join(re.findall(r"[a-z0-9]+", name.lower().replace("&", " and ")))


def screen_name(name, site):
    """Automated comparison; no result is a policy verdict."""
    signals = []
    if re.search(r"\b(best|#1|top rated|24/7|near me|cheap|affordable)\b", name, re.I):
        signals.append({"code": "promotional_terms", "reason": "Promotional wording appears in the profile name; check real-world branding."})
    if len(name) >= 65 or name.count(",") >= 3 or name.count("|") >= 2:
        signals.append({"code": "extended_name", "reason": "Long or multi-part name merits comparison with signs and business materials."})
    names = [n for n in site.get("names", []) if normalize_name(n.get("name", ""))]
    normalized = normalize_name(name)
    exact = [n for n in names if normalize_name(n["name"]) == normalized]
    shorter = [n for n in names if 5 <= len(normalize_name(n["name"])) < len(normalized) - 8
               and normalized.startswith(normalize_name(n["name"]) + " ")]
    if exact:
        return "branding_consistent", signals, "The profile name matches a captured website name. Real-world use and branch identity still need review."
    if shorter:
        signals.append({"code": "shorter_website_brand", "reason": "Website name fields contain a shorter matching brand; appended wording needs individual review."})
    if signals:
        return "needs_review", signals, "Automated screening found a reason to inspect the name. This does not establish a policy violation."
    if site.get("status") != "captured":
        return "unavailable", signals, "Website corroboration is unavailable; no name-compliance conclusion."
    return "no_obvious_signal", signals, "Automated screening found no obvious mismatch. This is not a compliance certification."


def attach_source_reviews(root, cases):
    """Analyst notes never constitute reviewer approval or reporting readiness."""
    by_cid = {c["cid"]: c for c in cases}
    seen = set()
    for path in sorted(root.glob("manual-review-*.json")):
        document = load(path)
        if document.get("schema") != "geogrid-manual-name-review/v1":
            raise ValueError("Unknown analyst-review schema")
        for cid, review in document["cases"].items():
            if cid in seen or cid not in by_cid:
                raise ValueError("Duplicate or unknown analyst-review profile")
            seen.add(cid)
            c = by_cid[cid]
            if review.get("current_profile_name") != c["profile"].get("name"):
                raise ValueError("Analyst review references a superseded profile name")
            if (not fresh(review.get("checked_at")) or c["profile"].get("status") != "complete"
                    or not fresh(c["profile"].get("checked_at"))):
                continue
            bracket = review.get("bracket")
            allowed_brackets = {"name_supported": {"name_supported"},
                                "source_discrepancy": {"supported_concern", "possible_concern"},
                                "research_needed": {"possible_concern", "insufficient_evidence"}}
            if bracket is not None and bracket not in allowed_brackets.get(review.get("status"), set()):
                raise ValueError("Analyst finding bracket contradicts review status")
            suspect_terms = review.get("suspect_terms", [])
            if not isinstance(suspect_terms, list) or any(not isinstance(t, str) for t in suspect_terms):
                raise ValueError("Suspect wording must be a list of exact text terms")
            sources = review.get("sources", [])
            profile_bound = False
            for source in sources:
                if source.get("evidence_path"):
                    evidence = (root / source["evidence_path"]).resolve()
                    if not evidence.is_relative_to(root.resolve()) or sha(evidence) != source.get("sha256"):
                        raise ValueError("Analyst source evidence is missing or changed")
                    if (source.get("sha256") == c["profile"]["sha256"]
                            and evidence == (root / c["profile"]["evidence_path"]).resolve()):
                        profile_bound = True
            if not profile_bound:
                raise ValueError("Analyst review must bind to the current profile response")
            c["source_review"] = {
                "checked_at": review["checked_at"], "status": review["status"],
                "bracket": review.get("bracket"), "suspect_terms": review.get("suspect_terms", []),
                "reviewed_by": review.get("reviewer", "Analyst"),
                "finding": " ".join(review.get("findings", [])),
                "counterevidence": " ".join(review.get("counterevidence", [])),
                "next_action": review["next_action"],
                "sources": [{**s, "label": s.get("label") or s.get("type") or "Evidence source"} for s in sources],
                "report_ready": False, "evidence_path": path.name, "sha256": sha(path),
            }
            c["automated_status"] = c["status"]
            c["automated_assessment"] = c["assessment"]
            c["status"] = {"name_supported": "branding_consistent", "source_discrepancy": "corroborated_discrepancy",
                           "research_needed": "needs_review"}[review["status"]]
            c["assessment"] = c["source_review"]["finding"]


def attach_title_enrichment(root, cases, study_plan_sha256, enrichment_path=None):
    """Preserve bounded evidence annotations, never arbitrary verdict overrides."""
    path = Path(enrichment_path) if enrichment_path is not None else Path(root) / "title-review-enrichment.json"
    if not path.exists():
        return
    apply_title_enrichment(load(path), cases, study_plan_sha256)


def apply_title_enrichment(document, cases, study_plan_sha256):
    """Validate and apply annotation objects after all case identities are resolved."""
    if (not isinstance(document, dict)
            or document.get("schema") != "geogrid-title-review-enrichment/v1"
            or document.get("study_plan_sha256") != study_plan_sha256):
        raise ValueError("Title enrichment schema or study binding mismatch")
    if set(document) - {"schema", "study_plan_sha256", "cases"} or not isinstance(document.get("cases"), dict):
        raise ValueError("Invalid title enrichment fields")
    by_cid = {c["cid"]: c for c in cases}
    validated = {}
    historical_fields = {
        "title", "date", "pages", "historical_name", "disputed_terms", "summary",
        "source_url", "source_sha256", "returned_observations", "distance_miles",
    }
    for cid, annotations in document["cases"].items():
        if cid not in by_cid:
            raise ValueError("Unknown title enrichment profile")
        if not isinstance(annotations, dict) or set(annotations) - {"historical_report", "confidence"}:
            raise ValueError("Invalid title enrichment case fields")
        if "confidence" in annotations:
            confidence = annotations["confidence"]
            fields = {"rubric", "level", "rationale", "factors", "checked_at", "cid", "profile_name"}
            if not isinstance(confidence, dict) or set(confidence) != fields:
                raise ValueError("Invalid confidence fields")
            profile = by_cid[cid].get("profile", {})
            if (confidence["cid"] != cid or not isinstance(confidence["profile_name"], str)
                    or not confidence["profile_name"] or profile.get("status") != "complete"
                    or confidence["profile_name"] != profile.get("name")):
                raise ValueError("Confidence must bind the exact current profile CID and name")
            level = confidence["level"]
            if (confidence["rubric"] != "title-evidence-v1"
                    or (level is not None and (type(level) is not int or not 0 <= level <= 5))
                    or not isinstance(confidence["rationale"], str)
                    or not isinstance(confidence["factors"], list)):
                raise ValueError("Invalid confidence rubric, level or rationale")
            try:
                checked = dt.datetime.fromisoformat(confidence["checked_at"].replace("Z", "+00:00"))
                if checked.utcoffset() is None:
                    raise ValueError("Timezone required")
            except (AttributeError, TypeError, ValueError):
                raise ValueError("Confidence checked_at must be a timezone-aware timestamp") from None
            for factor in confidence["factors"]:
                if (not isinstance(factor, dict) or set(factor) != {"label", "met", "reason"}
                        or not isinstance(factor["label"], str)
                        or type(factor["met"]) is not bool
                        or not isinstance(factor["reason"], str)):
                    raise ValueError("Invalid confidence factor")
        if "historical_report" in annotations:
            historical = annotations["historical_report"]
            if not isinstance(historical, dict) or set(historical) - historical_fields:
                raise ValueError("Invalid historical report fields")
            for key, value in historical.items():
                if key in {"pages", "disputed_terms"}:
                    expected = int if key == "pages" else str
                    if not isinstance(value, list) or any(type(v) is not expected or (key == "pages" and v < 1) for v in value):
                        raise ValueError("Invalid historical report " + key)
                elif key == "returned_observations":
                    if type(value) is not int or value < 0:
                        raise ValueError("Invalid historical returned observations")
                elif key == "distance_miles":
                    if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                        raise ValueError("Invalid historical distance")
                elif not isinstance(value, str):
                    raise ValueError("Invalid historical report " + key)
                elif key == "source_sha256" and not re.fullmatch(r"[a-fA-F0-9]{64}", value):
                    raise ValueError("Invalid historical source hash")
        validated[cid] = annotations
    for cid, annotations in validated.items():
        by_cid[cid].update(annotations)


def export(root):
    root = Path(root)
    seed = validate_seed(root)
    cases = []
    for c in seed["cases"]:
        path = root / "profiles" / f"{c['cid']}.json"
        item, status, checked = profile_item(path, c["cid"])
        item = item or {}
        name = item.get("title") or c["name"]
        url = item.get("url")
        site_path = root / "websites" / (hashlib.sha256(url.encode()).hexdigest() + ".json") if url else None
        site = load(site_path) if site_path and site_path.exists() else {"status": "not_captured", "names": [], "url": url}
        if site.get("status") == "captured" and not fresh(site.get("checked_at")):
            site = {**site, "status": "stale", "names": []}
        if status == "complete" and not fresh(checked):
            status = "stale"
        assessment_status, signals, assessment = screen_name(name, site)
        if status != "complete":
            assessment_status = "unavailable"
            assessment = "A fresh identity-matched profile response is unavailable; saved scan name is shown only as historical context."
        profile_url = f"https://www.google.com/maps?cid={c['cid']}"
        cases.append({
            "id": c["id"], "cid": c["cid"], "name": name, "scan_name": c["name"],
            "address": item.get("address") or c.get("address"), "map_url": profile_url, "website": url,
            "domain": item.get("domain") or c.get("domain"),
            "location": {"lat": item.get("latitude") if item.get("latitude") is not None else c.get("lat"),
                         "lng": item.get("longitude") if item.get("longitude") is not None else c.get("lng")},
            "wins_by_query": c["wins_by_query"], "total_wins": c["total_wins"],
            "returned_observations": c.get("returned_observations"),
            "status": assessment_status, "signals": signals, "assessment": assessment,
            "profile": {"status": status, "name": item.get("title"), "checked_at": checked,
                        "source_url": profile_url, "evidence_path": str(path.relative_to(root)) if path.exists() else None,
                        "sha256": sha(path) if path.exists() else None},
            "website_evidence": {k: site.get(k) for k in ("status", "url", "checked_at", "names", "title", "evidence_path", "sha256")},
            "limitations": ["Profile retrieval and automated website extraction are not an individual assessment; the analyst review specifies which real-world sources were actually inspected.",
                            "A shared domain may describe another branch. A DBA or legal registration alone does not determine Google compliance.",
                            "First-place observation counts prioritize research, not violation likelihood or promised ranking gains."],
        })
    attach_source_reviews(root, cases)
    attach_title_enrichment(root, cases, seed["study_plan_sha256"])
    cost = sum(float(load(p)["response"].get("cost") or 0) for p in root.glob("batch-*-receipt.json"))
    policy_path = root / "policy-review.json"
    policy = load(policy_path) if policy_path.exists() else {
        "url": POLICY, "checked_at": None,
        "summary": "Policy review not recorded. Follow the official naming policy before recommending a correction."}
    output = {"schema": "geogrid-name-review/v1", "generated_at": now(),
              "study_plan_sha256": seed["study_plan_sha256"],
              "policy": policy,
              "collection": {"profile_total": len(cases), "profile_complete": sum(c["profile"]["status"] == "complete" for c in cases),
                             "website_checked": sum(c["website_evidence"]["status"] == "captured" for c in cases),
                             "analyst_reviewed": sum("source_review" in c for c in cases),
                             "cost_usd": round(cost, 6), "method": "standard"},
              "cases": cases}
    save(root / "name-review.json", output)
    print(json.dumps({"collection": output["collection"], "statuses": {s: sum(c["status"] == s for c in cases) for s in sorted({c["status"] for c in cases})}}))
    return output


def attach(root):
    """Publish a portable sidecar; leave hashed ranking evidence untouched."""
    root = Path(root).resolve()
    seed = validate_seed(root)
    study = Path(seed["study"])
    if not study.is_absolute():
        study = Path(__file__).resolve().parents[1] / study
    study = study.resolve()
    evidence_path = root / "name-review.json"
    evidence = load(evidence_path)
    if evidence.get("schema") != "geogrid-name-review/v1" or evidence.get("study_plan_sha256") != seed["study_plan_sha256"]:
        raise ValueError("Review evidence belongs to a different study")
    manifest_path = study.with_name(study.stem + ".attachments.json")
    manifest = load(manifest_path) if manifest_path.exists() else {
        "schema": "geogrid-study-attachments/v1", "study_plan_sha256": seed["study_plan_sha256"]}
    if manifest.get("schema") != "geogrid-study-attachments/v1" or manifest.get("study_plan_sha256") != seed["study_plan_sha256"]:
        raise ValueError("Existing attachment manifest belongs to a different study")
    relative = Path(os.path.relpath(evidence_path, study.parent)).as_posix()
    manifest["name_review"] = quote(relative, safe="/.")
    save(manifest_path, manifest)
    return manifest_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "submit", "retrieve", "websites", "export", "attach"])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--study", type=Path)
    parser.add_argument("--include-cid", action="append", default=[],
                        help="Include an observed profile even without first-place wins; repeatable (plan only).")
    parser.add_argument("--only-cid", action="append", default=[],
                        help="Restrict the plan to these observed profiles; repeatable (plan only).")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-cost-usd", type=float, default=0)
    args = parser.parse_args()
    root = args.output_dir
    root.mkdir(parents=True, exist_ok=True)
    if args.command == "plan":
        if not args.study:
            parser.error("--study required")
        seed = seed_from_study(args.study, include_cids=args.include_cid, only_cids=args.only_cid)
        save(root / "seed.json", seed, True)
        print(json.dumps({"profiles": len(seed["cases"]), "standard_estimate_usd": round(len(seed["cases"]) * COST, 6)}))
    elif args.command in ("submit", "retrieve"):
        if args.command == "submit" and not args.execute:
            print(json.dumps({"profiles": len(load(root / "seed.json")["cases"]), "execute": False}))
            return
        from legends_dataforseo import api_request
        if args.command == "submit":
            submit(root, api_request, args.confirm_cost_usd)
        else:
            retrieve(root, api_request)
    elif args.command == "websites":
        fetch_websites(root)
    elif args.command == "attach":
        print(json.dumps({"attachment": str(attach(root))}))
    else:
        export(root)


if __name__ == "__main__":
    main()
