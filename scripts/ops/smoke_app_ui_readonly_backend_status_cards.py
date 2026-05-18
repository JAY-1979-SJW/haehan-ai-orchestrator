"""APP_UI_READONLY_BACKEND_STATUS_CARDS_01 smoke 스크립트."""
from __future__ import annotations

import json
from pathlib import Path

import scripts.ops.audit_app_ui_readonly_backend_status_cards as audit_mod

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_ID = "APP_UI_READONLY_BACKEND_STATUS_CARDS_SMOKE"

VERDICT_PASS = "READONLY_STATUS_CARDS_SMOKE_PASS"
VERDICT_WARN = "READONLY_STATUS_CARDS_SMOKE_WARN"
VERDICT_FAIL = "READONLY_STATUS_CARDS_SMOKE_FAIL"


def run_smoke() -> audit_mod.AuditReport:
    report = audit_mod.run_audit()
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

    out_path = REPO_ROOT / "data" / "app_ui_readonly_backend_status_cards_smoke_latest.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 70)
    print(f"[{SMOKE_ID}] Read-Only Backend Status Cards Smoke")
    print("=" * 70)
    for c in report.checks:
        mark = "✓" if c.status == "PASS" else ("△" if c.status == "WARN" else "✗")
        print(f"  [{c.status:<4}] {mark} {c.name}: {c.message}")
    print("=" * 70)
    s = report.summary()
    print(f"PASS={s['passed']} WARN={s['warned']} FAIL={s['failed']}")
    print(f"VERDICT: {report.verdict}")
    print("=" * 70)

    if s["failed"] > 0:
        raise SystemExit(1)
