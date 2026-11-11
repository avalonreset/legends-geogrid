"""Zero-daemon static Companion builder and browser launcher.

Builds a self-contained HTML file from the pre-compiled Companion runtime
(`assets/companion-runtime.js` and `assets/companion-runtime.css`) plus any
study JSON and optional campaign-research / name-review attachments, then
opens it via the system browser without spawning a background server, Node.js
daemon, or hidden PowerShell process.
"""
from __future__ import annotations

import json
import webbrowser
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_JS = REPO_ROOT / "assets" / "companion-runtime.js"
RUNTIME_CSS = REPO_ROOT / "assets" / "companion-runtime.css"
STARTER_STUDY = REPO_ROOT / "src" / "data" / "home-slice-study.json"
STARTER_RESEARCH = REPO_ROOT / "src" / "data" / "home-slice-campaign-research.json"
STARTER_NAME_REVIEW = REPO_ROOT / "src" / "data" / "home-slice-name-review.json"
STARTER_REPORT_PDF = REPO_ROOT / "examples" / "starter-home-slice" / "report" / "report.pdf"
STARTER_REPORT_HTML = REPO_ROOT / "examples" / "starter-home-slice" / "report" / "report.html"


def _safe_local_path(value: str | Path) -> Path:
    import sys
    p = Path(value).expanduser().absolute()
    for idx, part in enumerate((p, *p.parents)):
        if idx > 0 and sys.platform == "darwin" and part in {Path("/var"), Path("/tmp"), Path("/etc")}:
            continue
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            raise ValueError("Refusing to access symlink or junction path.")
        try:
            st = part.lstat()
            if getattr(st, "st_reparse_tag", 0) == 0xA0000003 or (
                getattr(st, "st_file_attributes", 0) & 0x400
            ):
                raise ValueError("Refusing to access Windows reparse point.")
        except OSError:
            continue
    return p


def _safe_script_json(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return (
        raw.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _safe_inline_script(code: str) -> str:
    return code.replace("</script", "<\\/script")


def _load_json(path: Path) -> Any:
    return json.loads(_safe_local_path(path).read_text(encoding="utf-8-sig"))


def _resolve_study_inputs(
    study: str | Path | None = None,
    research: str | Path | None = None,
    name_review: str | Path | None = None,
    output: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None, Path, Path | None, Path | None]:
    if study is None:
        study_data = _load_json(STARTER_STUDY)
        research_data = _load_json(STARTER_RESEARCH) if research is None else _load_json(Path(research))
        review_data = _load_json(STARTER_NAME_REVIEW) if name_review is None else _load_json(Path(name_review))
        out_path = Path(output) if output is not None else (REPO_ROOT / "runs" / "starter-home-slice" / "companion.html")
        return study_data, research_data, review_data, out_path, STARTER_REPORT_PDF, STARTER_REPORT_HTML

    candidate = Path(study)
    if candidate.is_dir():
        for name in ("companion-study.json", "battlefield-model.json", "study.json", "parsed-grid.json"):
            if (candidate / name).is_file():
                candidate = candidate / name
                break
        else:
            raise ValueError(f"No companion-study.json, battlefield-model.json, or parsed-grid.json found in directory: {candidate}")
    if not candidate.is_file():
        raise ValueError(f"Study file not found: {candidate}")

    study_data = _load_json(candidate)
    plan_sha = (study_data.get("evidence") or {}).get("plan_sha256")
    base_dir = candidate.parent
    stem = candidate.name[:-5] if candidate.name.lower().endswith(".json") else candidate.name
    manifest_path = base_dir / f"{stem}.attachments.json"
    manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        loaded = _load_json(manifest_path)
        if isinstance(loaded, dict) and loaded.get("schema") == "geogrid-study-attachments/v1":
            if not plan_sha or loaded.get("study_plan_sha256") == plan_sha:
                manifest = loaded

    research_data = None
    if research is not None:
        research_data = _load_json(Path(research))
    elif isinstance(manifest.get("campaign_research"), str):
        rp = (base_dir / manifest["campaign_research"]).resolve()
        if rp.is_relative_to(base_dir.resolve()) and rp.is_file():
            research_data = _load_json(rp)
    elif (base_dir / "campaign-research.json").is_file():
        cand_r = _load_json(base_dir / "campaign-research.json")
        if not plan_sha or cand_r.get("studyPlanSha256") == plan_sha:
            research_data = cand_r

    review_data = None
    if name_review is not None:
        review_data = _load_json(Path(name_review))
    elif isinstance(manifest.get("name_review"), str):
        np = (base_dir / manifest["name_review"]).resolve()
        if np.is_relative_to(base_dir.resolve()) and np.is_file():
            review_data = _load_json(np)
    elif (base_dir / "name-review.json").is_file():
        cand_n = _load_json(base_dir / "name-review.json")
        if not plan_sha or cand_n.get("study_plan_sha256") == plan_sha:
            review_data = cand_n

    out_path = Path(output) if output is not None else (base_dir / f"{stem}.companion.html")
    report_pdf = base_dir / "report" / "report.pdf"
    report_html = base_dir / "report" / "report.html"
    return (
        study_data,
        research_data,
        review_data,
        out_path,
        report_pdf if report_pdf.is_file() else None,
        report_html if report_html.is_file() else None,
    )


def open_companion(
    study: str | Path | None = None,
    research: str | Path | None = None,
    name_review: str | Path | None = None,
    output: str | Path | None = None,
    open_browser: bool = True,
    open_pdf: bool = False,
) -> dict[str, Any]:
    if not RUNTIME_JS.is_file() or not RUNTIME_CSS.is_file():
        raise ValueError("Companion runtime assets are missing (assets/companion-runtime.js / .css).")

    study_data, research_data, review_data, out_path, report_pdf, report_html = _resolve_study_inputs(
        study=study, research=research, name_review=name_review, output=output
    )
    is_valid_study = isinstance(study_data, dict) and (
        study_data.get("schema") in ("geogrid-companion/v1", "geogrid-battlefield/v1")
        or (isinstance(study_data.get("results"), list) and isinstance(study_data.get("target"), str))
    )
    if not is_valid_study:
        raise ValueError(
            "Study JSON must use schema 'geogrid-companion/v1', 'geogrid-battlefield/v1', or a GeoGrid parsed-grid dataset."
        )

    css_text = RUNTIME_CSS.read_text(encoding="utf-8")
    js_text = _safe_inline_script(RUNTIME_JS.read_text(encoding="utf-8"))
    bootstrap_json = _safe_script_json(
        {
            "study": study_data,
            "campaignResearch": research_data,
            "nameReview": review_data,
        }
    )

    html = (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "  <head>\n"
        '    <meta charset="UTF-8" />\n'
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        '    <meta name="description" content="Open-source google maps rank checker with geographic ranking grids, PDF reports, and DataForSEO cost controls." />\n'
        "    <title>legends-geogrid · open-source google maps rank checker</title>\n"
        f"    <style>{css_text}</style>\n"
        "  </head>\n"
        "  <body>\n"
        '    <div id="app"></div>\n'
        f"    <script>window.__GEOGRID_BOOTSTRAP__ = {bootstrap_json};</script>\n"
        f"    <script>{js_text}</script>\n"
        "  </body>\n"
        "</html>\n"
    )

    out_path = _safe_local_path(out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    browser_opened = False
    pdf_opened = False
    if open_browser:
        browser_opened = bool(webbrowser.open(out_path.as_uri()))
        if open_pdf and report_pdf and report_pdf.is_file():
            pdf_opened = bool(webbrowser.open(report_pdf.resolve().as_uri()))

    return {
        "status": "companion_ready",
        "mode": "static_file_zero_daemon",
        "companion_html": str(out_path),
        "companion_uri": out_path.as_uri(),
        "report_pdf": str(report_pdf.resolve()) if report_pdf and report_pdf.is_file() else None,
        "report_html": str(report_html.resolve()) if report_html and report_html.is_file() else None,
        "browser_opened": browser_opened,
        "pdf_opened": pdf_opened,
        "background_processes_spawned": 0,
    }
