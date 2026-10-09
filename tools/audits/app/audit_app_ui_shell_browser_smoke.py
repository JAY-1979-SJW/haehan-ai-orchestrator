"""APP_UI_SHELL_BROWSER_SMOKE_01 감사 스크립트.

smoke_app_ui_shell_browser.run_smoke() 결과를 받아 최종 verdict 판정.
- BROWSER_SMOKE_PASS: 전부 PASS
- BROWSER_SMOKE_WARN: WARN 있음, FAIL 없음
- BROWSER_SMOKE_FAIL: FAIL 1개 이상
"""

from __future__ import annotations

import json
from pathlib import Path

import tools.audits.app.smoke_app_ui_shell_browser as smoke_mod

REPO_ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
AUDIT_ID = "APP_UI_SHELL_BROWSER_SMOKE"

VERDICT_PASS = smoke_mod.VERDICT_PASS
VERDICT_WARN = smoke_mod.VERDICT_WARN
VERDICT_FAIL = smoke_mod.VERDICT_FAIL


def run_audit() -> smoke_mod.SmokeReport:
    report = smoke_mod.run_smoke()
    return report


if __name__ == "__main__":
    report = run_audit()
    summary = report.summary()

    out_path = REPO_ROOT / "data" / "app_ui_shell_browser_smoke_audit_latest.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 70)
    print(f"[{AUDIT_ID}] Browser Smoke Audit")
    print("=" * 70)
    for c in report.checks:
        mark = "✓" if c.status == "PASS" else ("△" if c.status == "WARN" else "✗")
        print(f"  [{c.status:<4}] {mark} {c.name}: {c.message}")
    print("=" * 70)
    print(f"PASS={summary['passed']} WARN={summary['warned']} FAIL={summary['failed']}")
    print(f"VERDICT: {report.verdict}")
    print("=" * 70)

    if summary["failed"] > 0:
        raise SystemExit(1)
