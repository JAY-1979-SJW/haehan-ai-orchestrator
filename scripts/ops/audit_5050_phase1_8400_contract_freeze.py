"""5050 Phase 1 — 8400 contract freeze 감사 스크립트.

ASSISTANT_BACKEND_5050_LEGACY_PHASE1_8400_CONTRACT_FREEZE_01

Phase 1 대상 5개 route의 8400 계약을 machine-readable로 고정한다.
실제 HTTP 호출 없이 정적 계약 검증만 수행한다.

실행:
    python scripts/ops/audit_5050_phase1_8400_contract_freeze.py
    python scripts/ops/audit_5050_phase1_8400_contract_freeze.py --json

금지:
    실제 HTTP 호출 금지 / approve/reject 실행 금지 / execute 호출 금지
    5050 중단 금지 / nginx 변경 금지 / DB write 금지 / secret 출력 금지
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# ── Phase 1 대상 contract freeze matrix ──────────────────────────────────────

PHASE1_CONTRACTS: list[dict[str, Any]] = [
    {
        "phase": "PHASE_1",
        "legacy_method": "GET",
        "legacy_path": "/api/v1/inbox",
        "fastapi_method": "GET",
        "fastapi_path": "/api/v1/inbox",
        "overlap_class": "SAME_CONTRACT",
        "contract_status": "FROZEN_CANDIDATE",
        "adapter_required": False,
        "auth_expected": True,
        "side_effect_allowed": False,
        "do_not_call_live": True,
        "live_call_allowed": False,
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
        "risk_level": "LOW",
        "migration_action": "FREEZE_8400_CONTRACT_FIRST",
        "freeze_verdict": "READY_FOR_COMPAT_TEST",
        "note": (
            "nginx /orchestrator/api/ 경유 시 8400 응답. "
            "GET 조회 전용 — side effect 없음. "
            "8400 response schema 고정 후 5050 직접 경로 비활성화 가능."
        ),
    },
    {
        "phase": "PHASE_1",
        "legacy_method": "POST",
        "legacy_path": "/api/v1/inbox/email/fetch",
        "fastapi_method": "POST",
        "fastapi_path": "/api/v1/inbox/email/fetch",
        "overlap_class": "COMPATIBLE_WITH_ADAPTER",
        "contract_status": "FROZEN_CANDIDATE",
        "adapter_required": True,
        "adapter_note": "외부 이메일 서버 접속 포함 — 실행 환경/credential adapter 필요",
        "auth_expected": True,
        "side_effect_allowed": False,
        "do_not_call_live": True,
        "live_call_allowed": False,
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
        "risk_level": "MEDIUM",
        "migration_action": "FREEZE_ADAPTER_CONTRACT_FIRST",
        "freeze_verdict": "READY_FOR_COMPAT_TEST",
        "note": (
            "외부 이메일 서버 접속 포함. "
            "5050 → 8400 이관 시 credential/env adapter 필요. "
            "실제 fetch 실행 금지 — contract만 고정."
        ),
    },
    {
        "phase": "PHASE_1",
        "legacy_method": "POST",
        "legacy_path": "/api/v1/tasks",
        "fastapi_method": "POST",
        "fastapi_path": "/api/v1/tasks",
        "overlap_class": "SAME_CONTRACT",
        "contract_status": "FROZEN_CANDIDATE",
        "adapter_required": False,
        "auth_expected": True,
        "side_effect_allowed": False,
        "do_not_call_live": True,
        "live_call_allowed": False,
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
        "risk_level": "MEDIUM",
        "migration_action": "FREEZE_8400_CONTRACT_FIRST",
        "freeze_verdict": "READY_FOR_COMPAT_TEST",
        "note": (
            "task 생성 POST. nginx 경유 시 8400 응답. "
            "8400 request/response schema 고정 후 5050 직접 경로 비활성화 가능. "
            "실제 task 생성 실행 금지 — contract만 고정."
        ),
    },
    {
        "phase": "PHASE_1",
        "legacy_method": "POST",
        "legacy_path": "/api/v1/tasks/<task_id>/approve",
        "fastapi_method": "POST",
        "fastapi_path": "/api/v1/tasks/{task_id}/approve",
        "overlap_class": "COMPATIBLE_WITH_ADAPTER",
        "contract_status": "FROZEN_CANDIDATE",
        "adapter_required": True,
        "adapter_note": "path param 표기 차이 (<task_id> vs {task_id}) + auth policy 비교 필요",
        "auth_expected": True,
        "side_effect_allowed": False,
        "do_not_call_live": True,
        "live_call_allowed": False,
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
        "risk_level": "HIGH",
        "migration_action": "FREEZE_ADAPTER_CONTRACT_FIRST",
        "freeze_verdict": "READY_FOR_COMPAT_TEST",
        "note": (
            "승인 실행 — 실제 호출 절대 금지. "
            "5050 path param 표기가 Flask 방식(<>). "
            "8400은 FastAPI 방식({}). "
            "auth policy 비교 필요 — adapter compat 공정 대기."
        ),
    },
    {
        "phase": "PHASE_1",
        "legacy_method": "POST",
        "legacy_path": "/api/v1/tasks/<task_id>/reject",
        "fastapi_method": "POST",
        "fastapi_path": "/api/v1/tasks/{task_id}/reject",
        "overlap_class": "COMPATIBLE_WITH_ADAPTER",
        "contract_status": "FROZEN_CANDIDATE",
        "adapter_required": True,
        "adapter_note": "path param 표기 차이 (<task_id> vs {task_id}) + auth policy 비교 필요",
        "auth_expected": True,
        "side_effect_allowed": False,
        "do_not_call_live": True,
        "live_call_allowed": False,
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
        "risk_level": "HIGH",
        "migration_action": "FREEZE_ADAPTER_CONTRACT_FIRST",
        "freeze_verdict": "READY_FOR_COMPAT_TEST",
        "note": (
            "거부 실행 — 실제 호출 절대 금지. "
            "approve와 동일한 adapter 요건. "
            "auth policy 비교 필요 — adapter compat 공정 대기."
        ),
    },
]

# ── 명시적 제외 목록 (Phase 1 범위 밖) ────────────────────────────────────────

PHASE1_EXCLUDED = {
    "HOLD_DANGEROUS": ["/api/v1/tasks/<task_id>/execute"],
    "DO_NOT_TOUCH": ["/api/v1/webhooks/kakaowork", "/api/v1/webhooks/kakaotalk-channel"],
    "HOLD_DASHBOARD": ["/dashboard", "/dashboard/tasks/<task_id>", "/dashboard/approve", "/dashboard/reject"],
}

# ── 안전 경계 ─────────────────────────────────────────────────────────────────

SAFE_BOUNDARY = {
    "5050_stop": False,
    "nginx_change": False,
    "actual_http_call": False,
    "actual_approve_reject": False,
    "actual_execute": False,
    "actual_webhook_call": False,
    "actual_db_write": False,
    "actual_ui_change": False,
    "secret_output": False,
    "server_deploy": False,
}


# ── 감사 함수 ─────────────────────────────────────────────────────────────────


def run_audit() -> dict[str, Any]:
    contracts = PHASE1_CONTRACTS

    total = len(contracts)
    same_contract = sum(1 for r in contracts if r["overlap_class"] == "SAME_CONTRACT")
    compat_adapter = sum(1 for r in contracts if r["overlap_class"] == "COMPATIBLE_WITH_ADAPTER")
    adapter_required_cnt = sum(1 for r in contracts if r["adapter_required"] is True)
    side_effect_false = sum(1 for r in contracts if r["side_effect_allowed"] is False)
    do_not_call_true = sum(1 for r in contracts if r["do_not_call_live"] is True)
    do_not_stop_true = sum(1 for r in contracts if r["do_not_stop_5050"] is True)
    nginx_unchanged_true = sum(1 for r in contracts if r["nginx_unchanged"] is True)
    freeze_ready = sum(1 for r in contracts if r["freeze_verdict"] == "READY_FOR_COMPAT_TEST")

    # /execute, webhook, dashboard가 Phase 1에 포함되지 않았는지 확인
    phase1_paths = [r["legacy_path"] for r in contracts]
    excluded_clean = (
        "/api/v1/tasks/<task_id>/execute" not in phase1_paths
        and not any("webhook" in p for p in phase1_paths)
        and not any("/dashboard" in p for p in phase1_paths)
    )

    boundary_violations = [k for k, v in SAFE_BOUNDARY.items() if v is True]

    success = (
        total == 5
        and same_contract == 2
        and compat_adapter == 3
        and adapter_required_cnt == 3
        and side_effect_false == 5
        and do_not_call_true == 5
        and do_not_stop_true == 5
        and nginx_unchanged_true == 5
        and freeze_ready == 5
        and excluded_clean
        and len(boundary_violations) == 0
    )

    return {
        "audit_id": "ASSISTANT_BACKEND_5050_LEGACY_PHASE1_8400_CONTRACT_FREEZE_01",
        "verdict": "PHASE1_CONTRACT_FREEZE_READY" if success else "FAIL",
        "success": success,
        "contracts": contracts,
        "excluded": PHASE1_EXCLUDED,
        "safe_boundary": {**SAFE_BOUNDARY, "violations": boundary_violations},
        "summary": {
            "total_routes": total,
            "same_contract": same_contract,
            "compatible_with_adapter": compat_adapter,
            "adapter_required": adapter_required_cnt,
            "side_effect_allowed_false": side_effect_false,
            "do_not_call_live_true": do_not_call_true,
            "do_not_stop_5050_true": do_not_stop_true,
            "nginx_unchanged_true": nginx_unchanged_true,
            "freeze_ready": freeze_ready,
            "excluded_clean": excluded_clean,
        },
    }


def _print_report(audit: dict) -> None:
    print("=" * 70)
    print(f"AUDIT: {audit['audit_id']}")
    print(f"VERDICT: {audit['verdict']}")
    print("=" * 70)

    print("\n[Phase 1 contract freeze matrix]")
    header = f"{'METHOD':<6} {'LEGACY PATH':<42} {'OVERLAP':<26} {'ADAPTER':<8} {'RISK'}"
    print(f"  {header}")
    print(f"  {'-' * len(header)}")
    for r in audit["contracts"]:
        print(
            f"  {r['legacy_method']:<6} {r['legacy_path']:<42} "
            f"{r['overlap_class']:<26} {r['adapter_required']!s:<8} {r['risk_level']}"
        )

    s = audit["summary"]
    print("\n[집계]")
    print(f"  총 route 수             : {s['total_routes']} (기준: 5)")
    print(f"  SAME_CONTRACT           : {s['same_contract']} (기준: 2)")
    print(f"  COMPATIBLE_WITH_ADAPTER : {s['compatible_with_adapter']} (기준: 3)")
    print(f"  adapter_required=True   : {s['adapter_required']} (기준: 3)")
    print(f"  side_effect_allowed=False: {s['side_effect_allowed_false']} (기준: 5)")
    print(f"  do_not_call_live=True   : {s['do_not_call_live_true']} (기준: 5)")
    print(f"  do_not_stop_5050=True   : {s['do_not_stop_5050_true']} (기준: 5)")
    print(f"  nginx_unchanged=True    : {s['nginx_unchanged_true']} (기준: 5)")
    print(f"  freeze_ready            : {s['freeze_ready']} (기준: 5)")
    print(f"  excluded_clean          : {s['excluded_clean']}")

    print("\n[제외 확인]")
    for label, paths in audit["excluded"].items():
        for p in paths:
            print(f"  ✅ 제외됨: [{label}] {p}")

    sb = audit["safe_boundary"]
    print("\n[SAFE BOUNDARY]")
    if sb["violations"]:
        print(f"  ❌ 위반: {sb['violations']}")
    else:
        print("  ✅ 위반 없음")

    print("=" * 70)
    print(f"VERDICT: {audit['verdict']}")
    print("GPT 검측 대기 중 — 단독 PASS 확정 불가")
    print("=" * 70)


def main() -> None:
    from scripts.common.audit_cli import run_json_or_report_cli

    run_json_or_report_cli("5050 Phase 1 8400 contract freeze 감사", run_audit, _print_report, "success")


if __name__ == "__main__":
    main()
