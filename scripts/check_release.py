"""Static public-release and EDR gate for legends-geogrid."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    ".legends-module",
    ".legends-router-pin",
    "AGENTS.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "assets/banner.png",
    "assets/banner.webp",
    "assets/manifest.json",
    "assets/preview.png",
    "assets/social-preview.png",
    "docs/AGENT-RECIPE.md",
    "docs/STUDY-RECIPE.md",
    "package.json",
    "skills/cto-legends/SKILL.md",
]

FORBIDDEN_PATHS = [
    "CLAUDE.md",
    "GEMINI.md",
    "CODEX.md",
    "GROK.md",
    "SKILL.md",
    "github/SKILL.md",
    "gemini-extension.json",
    "skill-package.json",
    ".claude-plugin",
    "install.ps1",
    "install.sh",
    "install-codex.ps1",
    "install-codex.sh",
    "bin/setup-multi-agent.ps1",
    "bin/setup-multi-agent.sh",
    "bin/setup-multi-agent",
    "bin/install-spine.ps1",
    "bin/install-spine.sh",
]

FORBIDDEN_EXTENSIONS = {".ps1", ".bat", ".cmd", ".exe", ".dll", ".pyc"}

FORBIDDEN_CODE_PATTERNS = [
    r"CREATE_NO_WINDOW",
    r"0x08000000",
    r"-WindowStyle\s+Hidden",
    r"-ExecutionPolicy\s+Bypass",
    r"CryptUnprotectData",
    r"ctypes\.windll",
    r"SetWindowsHookEx",
    r"GetAsyncKeyState",
    r"IndexedDB",
    r"LevelDB",
    r"Local\s+State",
    r"Login\s+Data",
    r"Web\s+Data",
    r"Cookies",
    r"gh[pousr]_[A-Za-z0-9]{20,}",
    r"sk-[A-Za-z0-9]{20,}",
    r"-----BEGIN[A-Z ]*PRIVATE KEY-----",
    r"https?://[a-z0-9.-]+\.ts\.net",
]

HOUSE_PATH_PATTERNS = [
    r"C:\\" + r"Users\\",
    r"/home/[a-z0-9_-]+/",
    r"E:\\" + r"empire",
    r"E:\\" + r"ai-marketing-hub",
    r"rc" + r"col",
    r"glit" + r"chyglitch",
    r"omni" + r"gent",
]

CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\ufffd]")
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def tracked_files() -> list[Path]:
    out = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    return [ROOT / line.strip() for line in out.splitlines() if line.strip()]


def _check_manifest(issues: list[str]) -> None:
    manifest_path = ROOT / "assets/manifest.json"
    if not manifest_path.is_file():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        issues.append(f"Invalid JSON in assets/manifest.json: {exc}")
        return
    assets = manifest.get("assets", {})
    for key, meta in assets.items():
        rel_path = meta.get("path")
        if not rel_path:
            issues.append(f"assets/manifest.json entry '{key}' missing path")
            continue
        asset_file = ROOT / rel_path
        if not asset_file.is_file():
            issues.append(f"assets/manifest.json target missing: {rel_path}")
            continue
        raw = asset_file.read_bytes()
        actual_sha = hashlib.sha256(raw).hexdigest()
        if meta.get("sha256") and meta.get("sha256") != actual_sha:
            issues.append(
                f"SHA-256 mismatch for {rel_path}: manifest={meta.get('sha256')} actual={actual_sha}"
            )
        if meta.get("bytes") is not None and meta.get("bytes") != len(raw):
            issues.append(
                f"Byte size mismatch for {rel_path}: manifest={meta.get('bytes')} actual={len(raw)}"
            )


def _check_markdown_links(md_path: Path, text: str, issues: list[str]) -> None:
    rel_src = md_path.relative_to(ROOT).as_posix()
    stripped = re.sub(r"```.*?```", "", text, flags=re.S)
    stripped = re.sub(r"`[^`\n]+`", "", stripped)
    for match in MARKDOWN_LINK_RE.finditer(stripped):
        raw_target = match.group(1).strip()
        if not raw_target or raw_target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        target_clean = raw_target.split("#", 1)[0].split("?", 1)[0].strip()
        if not target_clean:
            continue
        resolved = (md_path.parent / target_clean).resolve()
        try:
            resolved.relative_to(ROOT.resolve())
        except ValueError:
            issues.append(f"Markdown link escapes repository root in {rel_src}: {raw_target}")
            continue
        if not resolved.exists():
            issues.append(f"Broken relative link in {rel_src}: {raw_target}")


def check_release() -> list[str]:
    issues: list[str] = []

    for rel in REQUIRED_FILES:
        if not (ROOT / rel).is_file():
            issues.append(f"Missing required file: {rel}")

    for rel in FORBIDDEN_PATHS:
        if (ROOT / rel).exists():
            issues.append(f"Forbidden path exists: {rel}")

    mod_file = ROOT / ".legends-module"
    if mod_file.is_file() and mod_file.read_text(encoding="utf-8").strip() != "legends-geogrid":
        issues.append(".legends-module must equal 'legends-geogrid'")

    pin_file = ROOT / ".legends-router-pin"
    if pin_file.is_file():
        pin = pin_file.read_text(encoding="utf-8").strip()
        if not re.fullmatch(r"[0-9a-f]{40}", pin):
            issues.append(".legends-router-pin must be a 40-char lowercase hex SHA")

    pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    pkg_ver = pkg.get("version")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    m_chg = re.search(r"^##\s+\[?v?(\d+\.\d+\.\d+)\]?", changelog, re.M)
    chg_ver = m_chg.group(1) if m_chg else None
    cff_text = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    m_cff = re.search(r'^version:\s*["\']?(\d+\.\d+\.\d+)["\']?\s*$', cff_text, re.M)
    cff_ver = m_cff.group(1) if m_cff else None
    if not pkg_ver or pkg_ver != chg_ver or pkg_ver != cff_ver:
        issues.append(f"Version mismatch: package.json={pkg_ver}, CHANGELOG.md={chg_ver}, CITATION.cff={cff_ver}")

    _check_manifest(issues)

    skill_files = [p.relative_to(ROOT).as_posix() for p in tracked_files() if p.name == "SKILL.md"]
    if skill_files != ["skills/cto-legends/SKILL.md"]:
        issues.append(f"Expected only skills/cto-legends/SKILL.md, found: {skill_files}")

    for p in tracked_files():
        if not p.exists():
            continue
        rel = p.relative_to(ROOT).as_posix()
        suffix = p.suffix.lower()
        if suffix in FORBIDDEN_EXTENSIONS:
            issues.append(f"Forbidden tracked file extension ({suffix}): {rel}")
        if rel in ("scripts/check_release.py", "tests/test_release_hygiene.py"):
            continue
        if suffix in (".png", ".webp"):
            raw = p.read_bytes()
            for chunk in (b"tEXt", b"iTXt", b"zTXt", b"eXIf", b"EXIF", b"XMP "):
                if chunk in raw:
                    issues.append(f"Image metadata chunk {chunk!r} found in {rel}")
        if suffix in (".py", ".md", ".toml", ".yml", ".yaml", ".json", ".ps1", ".sh", ".cmd", ".bat", ".js", ".mjs", ".cff", ".txt"):
            text = p.read_text(encoding="utf-8", errors="replace")
            if CONTROL_CHAR_RE.search(text):
                issues.append(f"Forbidden control or replacement character found in {rel}")
            for pat in FORBIDDEN_CODE_PATTERNS:
                if re.search(pat, text, re.IGNORECASE):
                    issues.append(f"Forbidden pattern '{pat}' in {rel}")
            for pat in HOUSE_PATH_PATTERNS:
                if re.search(pat, text, re.IGNORECASE):
                    issues.append(f"House/private pattern '{pat}' in {rel}")
            if suffix == ".md":
                if rel != "skills/cto-legends/SKILL.md":
                    if "\u2014" in text or "\u2013" in text:
                        issues.append(f"Typography dash (em/en dash) found in {rel}")
                _check_markdown_links(p, text, issues)

    return issues


def main() -> int:
    issues = check_release()
    if issues:
        for issue in issues:
            print(f"FAIL: {issue}")
        return 1
    print("Release checks: PASS (0 issues)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
