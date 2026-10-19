"""Compose preserved name-review exports and identity-bound evidence annotations.

No provider calls or report submissions. Existing output files are never overwritten.
"""
import argparse
import copy
import datetime as dt
import math
import os
from pathlib import Path
import re

import business_name_review as review


def timestamp(value):
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            raise ValueError()
        return parsed
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Profile checked_at must be a timezone-aware timestamp") from None


def document(path):
    data = review.load(path)
    if (data.get("schema") != "geogrid-name-review/v1"
            or not re.fullmatch(r"[a-fA-F0-9]{64}", str(data.get("study_plan_sha256", "")))
            or not isinstance(data.get("cases"), list)):
        raise ValueError("Invalid name-review export schema or fingerprint")
    seen = set()
    for case in data["cases"]:
        cid = case.get("cid")
        if not isinstance(cid, str) or not re.fullmatch(r"\d+", cid) or cid in seen:
            raise ValueError("Invalid or duplicate profile CID")
        seen.add(cid)
    return data


def rebase(value, origin, output_dir):
    """Retain references to immutable originals instead of copying source evidence."""
    if isinstance(value, list):
        return [rebase(v, origin, output_dir) for v in value]
    if not isinstance(value, dict):
        return value
    result = {k: rebase(v, origin, output_dir) for k, v in value.items()}
    if value.get("evidence_path"):
        source = (origin / value["evidence_path"]).resolve()
        if not source.is_file():
            raise ValueError("Referenced evidence file is missing: " + str(source))
        if value.get("sha256") and review.sha(source) != value["sha256"]:
            raise ValueError("Referenced evidence file hash changed: " + str(source))
        result["evidence_path"] = Path(os.path.relpath(source, output_dir)).as_posix()
    return result


def validate_supplement(case, origin, prior=None):
    profile = case.get("profile", {})
    if (profile.get("status") != "complete" or not profile.get("name")
            or profile["name"] != case.get("name") or not profile.get("evidence_path")
            or not profile.get("sha256") or not review.fresh(profile.get("checked_at"))):
        raise ValueError("Supplement requires a fresh complete exact-profile response")
    path = (origin / profile["evidence_path"]).resolve()
    if not path.is_file() or review.sha(path) != profile["sha256"]:
        raise ValueError("Supplement profile evidence missing or changed")
    item, status, checked = review.profile_item(path, case["cid"])
    if (status != "complete" or item.get("title") != profile["name"]
            or checked != profile["checked_at"]):
        raise ValueError("Supplement profile CID, name or timestamp does not match raw evidence")
    if prior and prior.get("profile", {}).get("checked_at"):
        if timestamp(profile["checked_at"]) < timestamp(prior["profile"]["checked_at"]):
            raise ValueError("Supplement profile is older than the base profile")


def costs(data, path, role):
    existing = data.get("collection", {}).get("provenance")
    if existing is not None:
        if not isinstance(existing, list):
            raise ValueError("Invalid collection provenance")
        return copy.deepcopy(existing)
    return [{"role": role, "source": str(path.resolve()), "sha256": review.sha(path),
             "cost_usd": data.get("collection", {}).get("cost_usd", 0)}]


def compose(base, supplement, enrichment, output):
    base, supplement, enrichment, output = map(lambda p: Path(p).resolve(), (base, supplement, enrichment, output))
    if output in {base, supplement, enrichment} or output.exists():
        raise ValueError("Output must be a new file, distinct from all input/source files")
    original, extra = document(base), document(supplement)
    fingerprint = original["study_plan_sha256"]
    if extra["study_plan_sha256"] != fingerprint:
        raise ValueError("Cannot combine reviews from different study fingerprints")
    merged = {c["cid"]: rebase(c, base.parent, output.parent) for c in original["cases"]}
    original_cases = {c["cid"]: c for c in original["cases"]}
    for case in extra["cases"]:
        prior = original_cases.get(case["cid"])
        validate_supplement(case, supplement.parent, prior)
        replacement = rebase(case, supplement.parent, output.parent)
        # Keep historical context, but never carry an old score or source verdict
        # across a refreshed response unless the new export explicitly supplies it.
        if prior and "historical_report" in prior and "historical_report" not in replacement:
            replacement["historical_report"] = copy.deepcopy(prior["historical_report"])
        merged[case["cid"]] = replacement
    cases = sorted(merged.values(), key=lambda c: (-c.get("total_wins", 0), c.get("id", c["cid"])))
    inherited = {c["cid"]: {k: c[k] for k in ("confidence", "historical_report") if k in c}
                 for c in cases if "confidence" in c or "historical_report" in c}
    review.apply_title_enrichment({"schema": "geogrid-title-review-enrichment/v1",
                                  "study_plan_sha256": fingerprint, "cases": inherited}, cases, fingerprint)
    # Explicit annotations are validated only against the final merged identities.
    review.apply_title_enrichment(review.load(enrichment), cases, fingerprint)
    provenance = {}
    for source in costs(original, base, "base") + costs(extra, supplement, "supplement"):
        amount = source.get("cost_usd")
        if (type(amount) not in (int, float) or not math.isfinite(amount) or amount < 0
                or not isinstance(source.get("source"), str)
                or not re.fullmatch(r"[a-fA-F0-9]{64}", str(source.get("sha256", "")))):
            raise ValueError("Invalid collection cost provenance")
        identity = source["sha256"]
        if identity in provenance and provenance[identity]["cost_usd"] != amount:
            raise ValueError("Contradictory collection cost provenance")
        provenance[identity] = source
    result = copy.deepcopy(original)
    result.update(generated_at=review.now(), cases=cases)
    result["collection"] = {
        "profile_total": len(cases),
        "profile_complete": sum(c.get("profile", {}).get("status") == "complete" for c in cases),
        "website_checked": sum(c.get("website_evidence", {}).get("status") == "captured" for c in cases),
        "analyst_reviewed": sum("source_review" in c for c in cases),
        "cost_usd": round(sum(s["cost_usd"] for s in provenance.values()), 6),
        "supplement_cost_usd": extra.get("collection", {}).get("cost_usd", 0),
        "method": "standard",
        "provenance": list(provenance.values()),
        "composition": {"base_sha256": review.sha(base), "supplement_sha256": review.sha(supplement),
                        "enrichment_sha256": review.sha(enrichment)},
    }
    review.save(output, result, exclusive=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "supplement", "enrichment", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = compose(args.base, args.supplement, args.enrichment, args.output)
    print(f"Composed {len(result['cases'])} exact-CID cases; retained source evidence and cost provenance.")


if __name__ == "__main__":
    main()
