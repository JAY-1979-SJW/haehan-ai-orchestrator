"""APP_UI_SHELL_READONLY_API_WIRING_01 정적 smoke 스크립트.

API client + 화면 연결 상태를 정적 분석으로 검증한다.
"""

from __future__ import annotations

import json
from pathlib import Path

import scripts.ops.audit_app_ui_shell_readonly_api_wiring as audit_mod

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_ID = "APP_UI_SHELL_READONLY_API_WIRING_SMOKE"

VERDICT_PASS = "READONLY_API_SMOKE_PASS"
VERDICT_WARN = "READONLY_API_SMOKE_WARN"
VERDICT_FAIL = "READONLY_API_SMOKE_FAIL"


def run_smoke() -> audit_mod.AuditReport:
    report = audit_mod.run_audit()
    # verdict를 smoke 전용으로 변환
    if report.verdict == audit_mod.VERDICT_READY:
        report.verdict = VERDICT_PASS
    elif report.verdict == audit_mod.VERDICT_WARN:
        report.verdict = VERDICT_WARN
    else:
        report.verdict = VERDICT_FAIL
    return report


if __name__ == "__main__":
    report = run_smoke()
    summary = report.summary()

    out_path = REPO_ROOT / "data" / "app_ui_shell_readonly_api_wiring_smoke_latest.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 70)
    print(f"[{SMOKE_ID}] Read-Only API Wiring Smoke")
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
