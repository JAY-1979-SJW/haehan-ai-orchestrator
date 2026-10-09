"""Audit direct CDP tab creation outside approved lifecycle helpers.

Default mode reports findings without failing so existing legacy code can be
classified. Use --strict in CI or pre-commit once the legacy call sites are
migrated to scripts.browser.page.web_connector.get_task_page/browser_task_session.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
SCAN_DIRS = ("scripts", "local_agent", "ai_orchestrator")
SKIP_PARTS = {
    ".git",
    "__pycache__",
    "data",
    "archive",
    "tests",
}
APPROVED_FILES = {
    Path("scripts/browser/page/web_connector.py"),
    Path("scripts/browser/session/browser_cdp_selection_gate.py"),
    Path("scripts/browser/session/browser_task_session.py"),
    Path("scripts/local_agent/open_user_browser_session.py"),
}
PATTERNS = (
    re.compile(r"\.new_page\s*\("),
    re.compile(r"\bnew_page\s*\("),
    re.compile(r"Target\.createTarget"),
)


def should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if rel in APPROVED_FILES:
        return True
    return any(part in SKIP_PARTS for part in rel.parts)


def scan() -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for dirname in SCAN_DIRS:
        base = ROOT / dirname
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if should_skip(path):
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for lineno, line in enumerate(lines, start=1):
                if any(pattern.search(line) for pattern in PATTERNS):
                    findings.append(
                        {
                            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                            "line": lineno,
                            "text": line.strip(),
                        }
                    )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit direct CDP tab creation.")
    parser.add_argument("--strict", action="store_true", help="fail when findings exist")
    args = parser.parse_args(argv)

    findings = scan()
    print(json.dumps({"ok": not findings, "findings": findings}, ensure_ascii=False, indent=2))
    return 1 if args.strict and findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
