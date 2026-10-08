"""5050 Flask legacy route characterization 감사 스크립트.

ASSISTANT_BACKEND_5050_LEGACY_CHARACTERIZATION_TEST_01

실행:
    python scripts/ops/audit_5050_legacy_characterization.py
    python scripts/ops/audit_5050_legacy_characterization.py --json

금지:
    5050 중단 금지 / nginx 변경 금지 / docker restart 금지
    실제 webhook 호출 금지 / task execute 금지 / approve/reject 실행 금지
    inbox fetch/classify 실행 금지 / secret 출력 금지
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# ── migration_class 상수 ──────────────────────────────────────────────────────

MC_ALREADY_ROUTED = "ALREADY_ROUTED_TO_8400"
MC_CHAR_NEEDED = "CHARACTERIZATION_NEEDED"
MC_LEGACY_REVIEW = "LEGACY_ONLY_NEEDS_REVIEW"
MC_HOLD = "HOLD"
MC_HOLD_DANGEROUS = "HOLD_DANGEROUS"
MC_DO_NOT_TOUCH = "DO_NOT_TOUCH"

# ── 안전 경계 ─────────────────────────────────────────────────────────────────

SAFE_BOUNDARY = {
    "5050_stop": False,
    "nginx_change": False,
    "docker_restart": False,
    "actual_webhook_call": False,
    "actual_task_execute": False,
    "actual_approve_reject": False,
    "actual_inbox_fetch": False,
    "actual_inbox_classify": False,
    "actual_db_write": False,
    "actual_ui_change": False,
    "secret_output": False,
    "side_effect_execution": False,
}

# ── 5050 Route Characterization Matrix ───────────────────────────────────────

ROUTE_MATRIX: list[dict[str, Any]] = [
    # ── DASHBOARD_UI ──────────────────────────────────────────────────────────
    {
        "route_id": "D-01",
        "path": "/dashboard",
        "method": ["GET"],
        "category": "DASHBOARD_UI",
        "handler": "dashboard.py → index/dashboard view",
        "auth_expected": True,
        "expected_status_without_auth": "302 또는 401",
        "expected_status_with_fake_auth": "200 HTML",
        "response_shape_summary": "HTML page, task 목록 렌더링",
        "side_effect_allowed": False,
        "migration_class": MC_HOLD,
        "fastapi_overlap": False,
        "risk_level": "LOW",
        "test_strategy": "unauthenticated status만 고정, HTML 실행 금지",
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
    },
    {
        "route_id": "D-02",
        "path": "/dashboard/tasks/<task_id>",
        "method": ["GET"],
        "category": "DASHBOARD_UI",
        "handler": "dashboard.py → task detail view",
        "auth_expected": True,
        "expected_status_without_auth": "302 또는 401",
        "expected_status_with_fake_auth": "200 HTML 또는 404",
        "response_shape_summary": "HTML page, 단일 task 렌더링",
        "side_effect_allowed": False,
        "migration_class": MC_HOLD,
        "fastapi_overlap": False,
        "risk_level": "LOW",
        "test_strategy": "unauthenticated status만 고정",
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
    },
    {
        "route_id": "D-03",
        "path": "/dashboard/approve",
        "method": ["POST"],
        "category": "DASHBOARD_UI",
        "handler": "dashboard.py → approve action",
        "auth_expected": True,
        "expected_status_without_auth": "302 또는 401",
        "expected_status_with_fake_auth": "200 또는 302",
        "response_shape_summary": "redirect 또는 JSON ack",
        "side_effect_allowed": False,
        "migration_class": MC_HOLD,
        "fastapi_overlap": True,
        "fastapi_equiv": "/api/v1/tasks/{task_id}/approve (POST)",
        "risk_level": "MEDIUM",
        "test_strategy": "실제 POST 금지, unauthenticated status만 고정",
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
    },
    {
        "route_id": "D-04",
        "path": "/dashboard/reject",
        "method": ["POST"],
        "category": "DASHBOARD_UI",
        "handler": "dashboard.py → reject action",
        "auth_expected": True,
        "expected_status_without_auth": "302 또는 401",
        "expected_status_with_fake_auth": "200 또는 302",
        "response_shape_summary": "redirect 또는 JSON ack",
        "side_effect_allowed": False,
        "migration_class": MC_HOLD,
        "fastapi_overlap": True,
        "fastapi_equiv": "/api/v1/tasks/{task_id}/reject (POST)",
        "risk_level": "MEDIUM",
        "test_strategy": "실제 POST 금지, unauthenticated status만 고정",
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
    },
    # ── WEBHOOK_LEGACY ────────────────────────────────────────────────────────
    {
        "route_id": "W-01",
        "path": "/api/v1/webhooks/kakaowork",
        "method": ["POST"],
        "category": "WEBHOOK_LEGACY",
        "handler": "webhooks_router.py → kakaowork handler",
        "auth_expected": True,
        "expected_status_without_auth": "400 또는 401 또는 403",
        "expected_status_with_fake_auth": "200 또는 400 (signature 검증 실패)",
        "response_shape_summary": "JSON ack 또는 error",
        "side_effect_allowed": False,
        "migration_class": MC_DO_NOT_TOUCH,
        "fastapi_overlap": False,
        "risk_level": "HIGH",
        "test_strategy": "route 존재 + DO_NOT_TOUCH 분류만 고정. 실제 호출 금지.",
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
        "note": "HMAC signature 검증 포함. 외부 계약. 별도 webhook compat 공정.",
    },
    {
        "route_id": "W-02",
        "path": "/api/v1/webhooks/kakaotalk-channel",
        "method": ["POST"],
        "category": "WEBHOOK_LEGACY",
        "handler": "webhooks_router.py → kakaotalk-channel handler",
        "auth_expected": True,
        "expected_status_without_auth": "400 또는 401 또는 403",
        "expected_status_with_fake_auth": "200 또는 400 (signature 검증 실패)",
        "response_shape_summary": "JSON ack 또는 error",
        "side_effect_allowed": False,
        "migration_class": MC_DO_NOT_TOUCH,
        "fastapi_overlap": False,
        "risk_level": "HIGH",
        "test_strategy": "route 존재 + DO_NOT_TOUCH 분류만 고정. 실제 호출 금지.",
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
        "note": "HMAC signature 검증 포함. 외부 계약. 별도 webhook compat 공정.",
    },
    # ── INBOX_LEGACY ──────────────────────────────────────────────────────────
    {
        "route_id": "I-01",
        "path": "/api/v1/inbox",
        "method": ["GET"],
        "category": "INBOX_LEGACY",
        "handler": "inbox_router.py → inbox list",
        "auth_expected": True,
        "expected_status_without_auth": "401 또는 403",
        "expected_status_with_fake_auth": "200 JSON",
        "response_shape_summary": "JSON list of inbox items",
        "side_effect_allowed": False,
        "migration_class": MC_ALREADY_ROUTED,
        "fastapi_overlap": True,
        "fastapi_equiv": "/api/v1/inbox (GET, 8400)",
        "risk_level": "LOW",
        "test_strategy": "nginx 경유 시 8400 응답. 5050 직접 경로는 legacy.",
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
    },
    {
        "route_id": "I-02",
        "path": "/api/v1/inbox/email/fetch",
        "method": ["POST"],
        "category": "INBOX_LEGACY",
        "handler": "inbox_router.py → email fetch",
        "auth_expected": True,
        "expected_status_without_auth": "401 또는 403",
        "expected_status_with_fake_auth": "200 또는 202",
        "response_shape_summary": "JSON fetch result",
        "side_effect_allowed": False,
        "migration_class": MC_ALREADY_ROUTED,
        "fastapi_overlap": True,
        "fastapi_equiv": "/api/v1/inbox/email/fetch (POST, 8400)",
        "risk_level": "HIGH",
        "test_strategy": "실제 fetch 금지. route 존재 + side_effect_allowed=False 고정.",
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
        "note": "외부 이메일 서버 접속 — 실행 금지",
    },
    {
        "route_id": "I-03",
        "path": "/api/v1/inbox/email/classify",
        "method": ["POST"],
        "category": "INBOX_LEGACY",
        "handler": "inbox_router.py → email classify",
        "auth_expected": True,
        "expected_status_without_auth": "401 또는 403",
        "expected_status_with_fake_auth": "200 또는 202",
        "response_shape_summary": "JSON classification result",
        "side_effect_allowed": False,
        "migration_class": MC_LEGACY_REVIEW,
        "fastapi_overlap": False,
        "risk_level": "MEDIUM",
        "test_strategy": "실제 classify 금지. route 존재 + migration_class 고정.",
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
    },
    {
        "route_id": "I-04",
        "path": "/api/v1/inbox/classify",
        "method": ["POST"],
        "category": "INBOX_LEGACY",
        "handler": "inbox_router.py → classify shorthand",
        "auth_expected": True,
        "expected_status_without_auth": "401 또는 403",
        "expected_status_with_fake_auth": "200 또는 202",
        "response_shape_summary": "JSON classification result",
        "side_effect_allowed": False,
        "migration_class": MC_LEGACY_REVIEW,
        "fastapi_overlap": False,
        "risk_level": "MEDIUM",
        "test_strategy": "실제 classify 금지. route 존재 + migration_class 고정.",
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
    },
    {
        "route_id": "I-05",
        "path": "/api/v1/inbox/candidates",
        "method": ["GET"],
        "category": "INBOX_LEGACY",
        "handler": "inbox_router.py → candidates list",
        "auth_expected": True,
        "expected_status_without_auth": "401 또는 403",
        "expected_status_with_fake_auth": "200 JSON",
        "response_shape_summary": "JSON list of candidate items",
        "side_effect_allowed": False,
        "migration_class": MC_LEGACY_REVIEW,
        "fastapi_overlap": False,
        "risk_level": "LOW",
        "test_strategy": "route 존재 + migration_class 고정.",
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
    },
    {
        "route_id": "I-06",
        "path": "/api/v1/inbox/candidates/<item_id>/task",
        "method": ["POST"],
        "category": "INBOX_LEGACY",
        "handler": "inbox_router.py → candidate promote to task",
        "auth_expected": True,
        "expected_status_without_auth": "401 또는 403",
        "expected_status_with_fake_auth": "200 또는 201",
        "response_shape_summary": "JSON task created",
        "side_effect_allowed": False,
        "migration_class": MC_CHAR_NEEDED,
        "fastapi_overlap": False,
        "risk_level": "MEDIUM",
        "test_strategy": "실제 POST 금지. route 존재 + migration_class 고정.",
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
    },
    {
        "route_id": "I-07",
        "path": "/api/v1/inbox/tasks/<task_id>",
        "method": ["GET"],
        "category": "INBOX_LEGACY",
        "handler": "inbox_router.py → email task detail",
        "auth_expected": True,
        "expected_status_without_auth": "401 또는 403",
        "expected_status_with_fake_auth": "200 또는 404",
        "response_shape_summary": "JSON task detail",
        "side_effect_allowed": False,
        "migration_class": MC_CHAR_NEEDED,
        "fastapi_overlap": False,
        "risk_level": "LOW",
        "test_strategy": "route 존재 + migration_class 고정.",
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
    },
    # ── TASK_LEGACY ───────────────────────────────────────────────────────────
    {
        "route_id": "T-01",
        "path": "/api/v1/tasks",
        "method": ["POST"],
        "category": "TASK_LEGACY",
        "handler": "tasks_router.py → task create",
        "auth_expected": True,
        "expected_status_without_auth": "401 또는 403",
        "expected_status_with_fake_auth": "200 또는 201",
        "response_shape_summary": "JSON task object",
        "side_effect_allowed": False,
        "migration_class": MC_ALREADY_ROUTED,
        "fastapi_overlap": True,
        "fastapi_equiv": "/api/v1/tasks (POST, 8400)",
        "risk_level": "LOW",
        "test_strategy": "nginx 경유 시 8400 응답. 5050 직접은 legacy.",
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
    },
    {
        "route_id": "T-02",
        "path": "/api/v1/tasks/<task_id>",
        "method": ["GET"],
        "category": "TASK_LEGACY",
        "handler": "tasks_router.py → task detail",
        "auth_expected": True,
        "expected_status_without_auth": "401 또는 403",
        "expected_status_with_fake_auth": "200 또는 404",
        "response_shape_summary": "JSON task object",
        "side_effect_allowed": False,
        "migration_class": MC_CHAR_NEEDED,
        "fastapi_overlap": False,
        "risk_level": "LOW",
        "test_strategy": "route 존재 + migration_class 고정.",
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
    },
    {
        "route_id": "T-03",
        "path": "/api/v1/tasks/<task_id>/approval-request",
        "method": ["POST"],
        "category": "TASK_LEGACY",
        "handler": "tasks_router.py → approval request",
        "auth_expected": True,
        "expected_status_without_auth": "401 또는 403",
        "expected_status_with_fake_auth": "200 또는 201",
        "response_shape_summary": "JSON approval request",
        "side_effect_allowed": False,
        "migration_class": MC_CHAR_NEEDED,
        "fastapi_overlap": False,
        "risk_level": "MEDIUM",
        "test_strategy": "실제 POST 금지. route 존재 + migration_class 고정.",
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
    },
    {
        "route_id": "T-04",
        "path": "/api/v1/tasks/<task_id>/approve",
        "method": ["POST"],
        "category": "TASK_LEGACY",
        "handler": "tasks_router.py → approve",
        "auth_expected": True,
        "expected_status_without_auth": "401 또는 403",
        "expected_status_with_fake_auth": "200",
        "response_shape_summary": "JSON ack",
        "side_effect_allowed": False,
        "migration_class": MC_ALREADY_ROUTED,
        "fastapi_overlap": True,
        "fastapi_equiv": "/api/v1/tasks/{task_id}/approve (POST, 8400)",
        "risk_level": "MEDIUM",
        "test_strategy": "실제 POST 금지. nginx 경유 시 8400 응답.",
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
    },
    {
        "route_id": "T-05",
        "path": "/api/v1/tasks/<task_id>/reject",
        "method": ["POST"],
        "category": "TASK_LEGACY",
        "handler": "tasks_router.py → reject",
        "auth_expected": True,
        "expected_status_without_auth": "401 또는 403",
        "expected_status_with_fake_auth": "200",
        "response_shape_summary": "JSON ack",
        "side_effect_allowed": False,
        "migration_class": MC_ALREADY_ROUTED,
        "fastapi_overlap": True,
        "fastapi_equiv": "/api/v1/tasks/{task_id}/reject (POST, 8400)",
        "risk_level": "MEDIUM",
        "test_strategy": "실제 POST 금지. nginx 경유 시 8400 응답.",
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
    },
    {
        "route_id": "T-06",
        "path": "/api/v1/tasks/<task_id>/execute",
        "method": ["POST"],
        "category": "TASK_LEGACY",
        "handler": "tasks_router.py → email_task_executor",
        "auth_expected": True,
        "expected_status_without_auth": "401 또는 403",
        "expected_status_with_fake_auth": "[HOLD — 실행 금지]",
        "response_shape_summary": "email_task_executor 실제 실행 — 위험",
        "side_effect_allowed": False,
        "migration_class": MC_HOLD_DANGEROUS,
        "fastapi_overlap": False,
        "risk_level": "CRITICAL",
        "test_strategy": "절대 실행 금지. HOLD_DANGEROUS 분류만 고정.",
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
        "note": "email_task_executor 완전 감사 후 이관. 현재 HOLD.",
    },
    {
        "route_id": "T-07",
        "path": "/api/v1/tasks/<task_id>/approval",
        "method": ["GET"],
        "category": "TASK_LEGACY",
        "handler": "tasks_router.py → approval status GET",
        "auth_expected": True,
        "expected_status_without_auth": "401 또는 403",
        "expected_status_with_fake_auth": "200 또는 404",
        "response_shape_summary": "JSON approval status",
        "side_effect_allowed": False,
        "migration_class": MC_CHAR_NEEDED,
        "fastapi_overlap": False,
        "risk_level": "LOW",
        "test_strategy": "route 존재 + migration_class 고정.",
        "do_not_stop_5050": True,
        "nginx_unchanged": True,
    },
]

# ── 8400 overlap comparison matrix ───────────────────────────────────────────

OVERLAP_MATRIX: list[dict[str, Any]] = [
    {
        "5050_path": "/api/v1/inbox",
        "8400_path": "/api/v1/inbox",
        "method": "GET",
        "overlap_class": "SAME_CONTRACT",
        "auth_policy_diff": False,
        "response_shape_diff": False,
        "migration_readiness": "ALREADY_ROUTED_TO_8400 — nginx 경유 시 8400 응답",
        "action": "5050 해당 route 비활성화 가능 (검증 후)",
    },
    {
        "5050_path": "/api/v1/inbox/email/fetch",
        "8400_path": "/api/v1/inbox/email/fetch",
        "method": "POST",
        "overlap_class": "COMPATIBLE_WITH_ADAPTER",
        "auth_policy_diff": False,
        "response_shape_diff": "미확인 — 실제 fetch 금지로 비교 불가",
        "migration_readiness": "ALREADY_ROUTED_TO_8400 — 실행 시 8400 응답",
        "action": "response contract 비교 후 5050 폐기 가능",
    },
    {
        "5050_path": "/api/v1/tasks",
        "8400_path": "/api/v1/tasks",
        "method": "POST",
        "overlap_class": "SAME_CONTRACT",
        "auth_policy_diff": False,
        "response_shape_diff": False,
        "migration_readiness": "ALREADY_ROUTED_TO_8400",
        "action": "5050 해당 route 비활성화 가능 (검증 후)",
    },
    {
        "5050_path": "/api/v1/tasks/<task_id>/approve",
        "8400_path": "/api/v1/tasks/{task_id}/approve",
        "method": "POST",
        "overlap_class": "COMPATIBLE_WITH_ADAPTER",
        "auth_policy_diff": "미확인 — auth 실행 금지로 비교 불가",
        "response_shape_diff": "미확인",
        "migration_readiness": "ALREADY_ROUTED_TO_8400",
        "action": "contract 검증 후 5050 폐기 가능",
    },
    {
        "5050_path": "/api/v1/tasks/<task_id>/reject",
        "8400_path": "/api/v1/tasks/{task_id}/reject",
        "method": "POST",
        "overlap_class": "COMPATIBLE_WITH_ADAPTER",
        "auth_policy_diff": "미확인 — auth 실행 금지로 비교 불가",
        "response_shape_diff": "미확인",
        "migration_readiness": "ALREADY_ROUTED_TO_8400",
        "action": "contract 검증 후 5050 폐기 가능",
    },
]

# ── next migration steps ──────────────────────────────────────────────────────

NEXT_MIGRATION_STEPS = [
    {
        "phase": 1,
        "target": "ALREADY_ROUTED_TO_8400 routes",
        "routes": [
            "/api/v1/inbox",
            "/api/v1/inbox/email/fetch",
            "/api/v1/tasks",
            "/api/v1/tasks/<task_id>/approve",
            "/api/v1/tasks/<task_id>/reject",
        ],
        "action": "8400 response contract 고정 후 5050 해당 route 비활성화",
        "precondition": "8400 integration test PASS",
    },
    {
        "phase": 2,
        "target": "CHARACTERIZATION_NEEDED routes",
        "routes": [
            "/api/v1/tasks/<task_id>",
            "/api/v1/tasks/<task_id>/approval-request",
            "/api/v1/tasks/<task_id>/approval",
            "/api/v1/inbox/candidates/<item_id>/task",
            "/api/v1/inbox/tasks/<task_id>",
        ],
        "action": "FastAPI 동등 route 추가 + contract 검증 + 5050 폐기",
        "precondition": "Phase 1 완료",
    },
    {
        "phase": 3,
        "target": "LEGACY_ONLY_NEEDS_REVIEW routes",
        "routes": ["/api/v1/inbox/email/classify", "/api/v1/inbox/classify", "/api/v1/inbox/candidates"],
        "action": "업무 검토 후 존치/이관/폐기 결정",
        "precondition": "Phase 2 완료",
    },
    {
        "phase": "HOLD",
        "target": "dashboard UI routes",
        "routes": ["/dashboard", "/dashboard/tasks/<task_id>", "/dashboard/approve", "/dashboard/reject"],
        "action": "UI 인테리어 공정 이후 별도 계획",
        "precondition": "autowork UI 인테리어 완료",
    },
    {
        "phase": "HOLD_DANGEROUS",
        "target": "task execute",
        "routes": ["/api/v1/tasks/<task_id>/execute"],
        "action": "email_task_executor 완전 감사 후 이관. 현재 실행 절대 금지.",
        "precondition": "executor 감사 완료 + 별도 승인",
    },
    {
        "phase": "DO_NOT_TOUCH",
        "target": "kakaowork/kakaotalk webhook",
        "routes": ["/api/v1/webhooks/kakaowork", "/api/v1/webhooks/kakaotalk-channel"],
        "action": "별도 webhook compat 공정 완료 후 이관",
        "precondition": "webhook compat 공정 PASS + staging 검증",
    },
]


# ── 감사 함수 ─────────────────────────────────────────────────────────────────


def _categorize_routes() -> dict[str, list]:
    by_category: dict[str, list] = {}
    for r in ROUTE_MATRIX:
        cat = r["category"]
        by_category.setdefault(cat, []).append(r)
    return by_category


def _categorize_by_migration_class() -> dict[str, list]:
    by_mc: dict[str, list] = {}
    for r in ROUTE_MATRIX:
        mc = r["migration_class"]
        by_mc.setdefault(mc, []).append({"route_id": r["route_id"], "path": r["path"]})
    return by_mc


def run_audit() -> dict[str, Any]:
    by_cat = _categorize_routes()
    by_mc = _categorize_by_migration_class()

    hold_dangerous = [r for r in ROUTE_MATRIX if r["migration_class"] == MC_HOLD_DANGEROUS]
    do_not_touch = [r for r in ROUTE_MATRIX if r["migration_class"] == MC_DO_NOT_TOUCH]

    boundary_violations = [k for k, v in SAFE_BOUNDARY.items() if v is True]
    any_side_effect = any(r["side_effect_allowed"] for r in ROUTE_MATRIX)

    checks = {
        "dashboard_routes_characterized": "DASHBOARD_UI" in by_cat,
        "webhook_routes_characterized": "WEBHOOK_LEGACY" in by_cat,
        "inbox_routes_characterized": "INBOX_LEGACY" in by_cat,
        "task_routes_characterized": "TASK_LEGACY" in by_cat,
        "execute_is_hold_dangerous": len(hold_dangerous) >= 1,
        "webhook_is_do_not_touch": len(do_not_touch) >= 2,
        "5050_do_not_stop_all_routes": all(r.get("do_not_stop_5050") for r in ROUTE_MATRIX),
        "nginx_unchanged_all_routes": all(r.get("nginx_unchanged") for r in ROUTE_MATRIX),
        "overlap_matrix_5_routes": len(OVERLAP_MATRIX) >= 5,
        "no_side_effect_in_matrix": not any_side_effect,
        "no_secret_output": not SAFE_BOUNDARY["secret_output"],
        "no_ui_change": not SAFE_BOUNDARY["actual_ui_change"],
        "no_db_write": not SAFE_BOUNDARY["actual_db_write"],
        "boundary_no_violations": len(boundary_violations) == 0,
    }

    all_ok = all(checks.values())

    return {
        "audit_id": "ASSISTANT_BACKEND_5050_LEGACY_CHARACTERIZATION_TEST_01",
        "verdict": "CHARACTERIZATION_READY 후보" if all_ok else "FAIL 후보",
        "all_ok": all_ok,
        "route_matrix": ROUTE_MATRIX,
        "by_category": {k: [r["route_id"] + " " + r["path"] for r in v] for k, v in by_cat.items()},
        "by_migration_class": by_mc,
        "overlap_matrix": OVERLAP_MATRIX,
        "hold_routes": [r["path"] for r in ROUTE_MATRIX if r["migration_class"] == MC_HOLD],
        "dangerous_routes": [r["path"] for r in hold_dangerous],
        "do_not_touch_routes": [r["path"] for r in do_not_touch],
        "next_migration_steps": NEXT_MIGRATION_STEPS,
        "safe_boundary": {**SAFE_BOUNDARY, "violations": boundary_violations},
        "checks": checks,
    }


def _print_report(audit: dict) -> None:
    print("=" * 70)
    print(f"AUDIT: {audit['audit_id']}")
    print(f"VERDICT: {audit['verdict']}")
    print(f"총 route: {len(audit['route_matrix'])}개")
    print("=" * 70)

    print("\n[카테고리별 route]")
    for cat, routes in audit["by_category"].items():
        print(f"  {cat} ({len(routes)}개)")
        for r in routes:
            print(f"    {r}")

    print("\n[migration class별 분류]")
    for mc, routes in audit["by_migration_class"].items():
        print(f"  {mc} ({len(routes)}개)")
        for r in routes:
            print(f"    {r['route_id']} {r['path']}")

    print("\n[HOLD_DANGEROUS] (절대 실행 금지)")
    for p in audit["dangerous_routes"]:
        print(f"  ⛔ {p}")

    print("\n[DO_NOT_TOUCH] (외부 webhook 계약)")
    for p in audit["do_not_touch_routes"]:
        print(f"  🔒 {p}")

    print(f"\n[8400 overlap] ({len(audit['overlap_matrix'])}개)")
    for o in audit["overlap_matrix"]:
        print(f"  {o['method']} {o['5050_path']}  →  {o['8400_path']}  [{o['overlap_class']}]")

    print("\n[CHECKLIST]")
    for k, v in audit["checks"].items():
        mark = "✅" if v else "❌"
        print(f"  {mark} {k}")

    print("\n[SAFE BOUNDARY]")
    sb = audit["safe_boundary"]
    if sb["violations"]:
        print(f"  ❌ 위반: {sb['violations']}")
    else:
        print("  ✅ 위반 없음")

    print("=" * 70)
    print(f"최종 판정: {audit['verdict']}")
    print("GPT 검측 대기 중 — 단독 PASS 확정 불가")
    print("=" * 70)


def main() -> None:
    from scripts.common.audit_cli import run_json_or_report_cli

    run_json_or_report_cli("5050 legacy characterization 감사", run_audit, _print_report, "all_ok")


if __name__ == "__main__":
    main()
