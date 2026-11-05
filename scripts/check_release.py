"""Static public-release and EDR gate for legends-geogrid."""
from __future__ import annotations

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

FORBIDDEN_CODE_PATTERNS = [
    r"CREATE_NO_WINDOW",
    r"0x08000000",
    r"-WindowStyle\s+Hidden",
    r"-ExecutionPolicy\s+Bypass",
    r"CryptUnprotectData",
    r"IndexedDB",
    r"LevelDB",
    r"Login Data",
    r"Web Data",
]

HOUSE_PATH_PATTERNS = [
    r"C:\\" + r"Users\\",
    r"/home/[a-z0-9_-]+/",
    r"E:\\" + r"empire",
    r"E:\\" + r"ai-marketing-hub",
    r"ben" + r"jamin",
    r"rc" + r"col",
    r"glit" + r"chyglitch",
    r"omni" + r"gent",
]


def tracked_files() -> list[Path]:
    out = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    return [ROOT / line.strip() for line in out.splitlines() if line.strip()]


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
    if not pkg_ver or pkg_ver != chg_ver:
        issues.append(f"Version mismatch: package.json={pkg_ver}, CHANGELOG.md={chg_ver}")

    skill_files = [p.relative_to(ROOT).as_posix() for p in tracked_files() if p.name == "SKILL.md"]
    if skill_files != ["skills/cto-legends/SKILL.md"]:
        issues.append(f"Expected only skills/cto-legends/SKILL.md, found: {skill_files}")

    for p in tracked_files():
        rel = p.relative_to(ROOT).as_posix()
        if rel in ("scripts/check_release.py", "tests/test_release_hygiene.py"):
            continue
        suffix = p.suffix.lower()
        if suffix in (".png", ".webp"):
            raw = p.read_bytes()
            for chunk in (b"tEXt", b"iTXt", b"zTXt", b"eXIf", b"EXIF", b"XMP "):
                if chunk in raw:
                    issues.append(f"Image metadata chunk {chunk!r} found in {rel}")
        if suffix in (".py", ".md", ".toml", ".yml", ".yaml", ".json", ".ps1", ".sh", ".cmd", ".bat", ".js", ".mjs"):
            text = p.read_text(encoding="utf-8", errors="replace")
            for pat in FORBIDDEN_CODE_PATTERNS:
                if re.search(pat, text, re.IGNORECASE):
                    issues.append(f"Forbidden pattern '{pat}' in {rel}")
            for pat in HOUSE_PATH_PATTERNS:
                if re.search(pat, text, re.IGNORECASE):
                    issues.append(f"House/private pattern '{pat}' in {rel}")
            if suffix == ".md" and rel != "skills/cto-legends/SKILL.md":
                if "\u2014" in text or "\u2013" in text:
                    issues.append(f"Typography dash (em/en dash) found in {rel}")

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
