"""
5050 Flask legacy → FastAPI 8400 이관 준비 감사 스크립트.

ASSISTANT_BACKEND_5050_LEGACY_FASTAPI_MIGRATION_PLAN_01

역할:
- 5050 route 목록 정리
- 8400 route 목록 정리
- 중복/유일/충돌 route 분류
- nginx 라우팅 영향 분석
- migration matrix 출력
- read-only / 외부 호출 없음 / 서버 변경 없음

실행:
    python scripts/archive/ops/audit_5050_legacy_fastapi_migration_readiness.py
    python scripts/archive/ops/audit_5050_legacy_fastapi_migration_readiness.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

READ_ONLY = True
SHUTDOWN_5050_FORBIDDEN = True
NGINX_CHANGE_FORBIDDEN = True
FULL_ROUTE_SWITCH_FORBIDDEN = True

# ── 5050 Flask legacy route 목록 ──────────────────────────────────────────────
# 서버 /home/ubuntu/apps/haehan-ai-orchestrator 기준 전수 조사 결과

ROUTES_5050: list[dict] = [
    # Dashboard UI (app.py → dashboard.py)
    {
        "path": "/dashboard",
        "methods": ["GET"],
        "category": "DASHBOARD_UI",
        "auth": "basic_auth",
        "external_webhook": False,
        "db_write": False,
        "description": "운영 대시보드 메인 페이지",
        "nginx_location": "/orchestrator/",
        "8400_equiv": None,
        "duplicate_risk": "LOW",
        "migration_tier": "HOLD",
    },
    {
        "path": "/dashboard/tasks/<task_id>",
        "methods": ["GET"],
        "category": "DASHBOARD_UI",
        "auth": "basic_auth",
        "external_webhook": False,
        "db_write": False,
        "description": "태스크 상세 대시보드",
        "nginx_location": "/orchestrator/",
        "8400_equiv": None,
        "duplicate_risk": "LOW",
        "migration_tier": "HOLD",
    },
    {
        "path": "/dashboard/approve",
        "methods": ["POST"],
        "category": "APPROVAL_LEGACY",
        "auth": "basic_auth",
        "external_webhook": False,
        "db_write": True,
        "description": "대시보드에서 태스크 승인",
        "nginx_location": "/orchestrator/",
        "8400_equiv": "/api/v1/tasks/{task_id}/approve",
        "duplicate_risk": "MEDIUM",
        "migration_tier": "CHARACTERIZATION_NEEDED",
    },
    {
        "path": "/dashboard/reject",
        "methods": ["POST"],
        "category": "APPROVAL_LEGACY",
        "auth": "basic_auth",
        "external_webhook": False,
        "db_write": True,
        "description": "대시보드에서 태스크 거부",
        "nginx_location": "/orchestrator/",
        "8400_equiv": "/api/v1/tasks/{task_id}/reject",
        "duplicate_risk": "MEDIUM",
        "migration_tier": "CHARACTERIZATION_NEEDED",
    },
    # Inbox (inbox_router.py, url_prefix=/api/v1/inbox)
    {
        "path": "/api/v1/inbox",
        "methods": ["GET"],
        "category": "INBOX_LEGACY",
        "auth": "basic_auth",
        "external_webhook": False,
        "db_write": False,
        "description": "inbox 목록 조회 (legacy)",
        "nginx_location": "/orchestrator/api/",
        "8400_equiv": "/api/v1/inbox",
        "duplicate_risk": "HIGH",
        "migration_tier": "ALREADY_ROUTED_TO_8400",
    },
    {
        "path": "/api/v1/inbox/email/fetch",
        "methods": ["POST"],
        "category": "INBOX_LEGACY",
        "auth": "basic_auth",
        "external_webhook": False,
        "db_write": True,
        "description": "이메일 fetch (hiworks)",
        "nginx_location": "/orchestrator/api/",
        "8400_equiv": "/api/v1/inbox/email/fetch",
        "duplicate_risk": "HIGH",
        "migration_tier": "ALREADY_ROUTED_TO_8400",
    },
    {
        "path": "/api/v1/inbox/email/classify",
        "methods": ["POST"],
        "category": "INBOX_LEGACY",
        "auth": "basic_auth",
        "external_webhook": False,
        "db_write": True,
        "description": "이메일 분류 (legacy)",
        "nginx_location": "/orchestrator/api/",
        "8400_equiv": None,
        "duplicate_risk": "LOW",
        "migration_tier": "LEGACY_ONLY_NEEDS_REVIEW",
    },
    {
        "path": "/api/v1/inbox/classify",
        "methods": ["POST"],
        "category": "INBOX_LEGACY",
        "auth": "basic_auth",
        "external_webhook": False,
        "db_write": True,
        "description": "메시지 분류",
        "nginx_location": "/orchestrator/api/",
        "8400_equiv": None,
        "duplicate_risk": "LOW",
        "migration_tier": "LEGACY_ONLY_NEEDS_REVIEW",
    },
    {
        "path": "/api/v1/inbox/candidates",
        "methods": ["GET"],
        "category": "INBOX_LEGACY",
        "auth": "basic_auth",
        "external_webhook": False,
        "db_write": False,
        "description": "후보 목록 조회",
        "nginx_location": "/orchestrator/api/",
        "8400_equiv": None,
        "duplicate_risk": "LOW",
        "migration_tier": "LEGACY_ONLY_NEEDS_REVIEW",
    },
    {
        "path": "/api/v1/inbox/candidates/<item_id>/task",
        "methods": ["POST"],
        "category": "INBOX_LEGACY",
        "auth": "basic_auth",
        "external_webhook": False,
        "db_write": True,
        "description": "후보 → task 승격",
        "nginx_location": "/orchestrator/api/",
        "8400_equiv": None,
        "duplicate_risk": "LOW",
        "migration_tier": "LEGACY_ONLY_NEEDS_REVIEW",
    },
    {
        "path": "/api/v1/inbox/tasks/<task_id>",
        "methods": ["GET"],
        "category": "INBOX_LEGACY",
        "auth": "basic_auth",
        "external_webhook": False,
        "db_write": False,
        "description": "email task 조회",
        "nginx_location": "/orchestrator/api/",
        "8400_equiv": None,
        "duplicate_risk": "LOW",
        "migration_tier": "LEGACY_ONLY_NEEDS_REVIEW",
    },
    # Tasks (tasks_router.py, url_prefix=/api/v1/tasks)
    {
        "path": "/api/v1/tasks",
        "methods": ["POST"],
        "category": "TASK_LEGACY",
        "auth": "basic_auth",
        "external_webhook": False,
        "db_write": True,
        "description": "task 생성",
        "nginx_location": "/orchestrator/api/",
        "8400_equiv": "/api/v1/tasks",
        "duplicate_risk": "HIGH",
        "migration_tier": "ALREADY_ROUTED_TO_8400",
    },
    {
        "path": "/api/v1/tasks/<task_id>",
        "methods": ["GET"],
        "category": "TASK_LEGACY",
        "auth": "basic_auth",
        "external_webhook": False,
        "db_write": False,
        "description": "task 조회",
        "nginx_location": "/orchestrator/api/",
        "8400_equiv": None,
        "duplicate_risk": "MEDIUM",
        "migration_tier": "LEGACY_ONLY_NEEDS_REVIEW",
    },
    {
        "path": "/api/v1/tasks/<task_id>/approval-request",
        "methods": ["POST"],
        "category": "APPROVAL_LEGACY",
        "auth": "basic_auth",
        "external_webhook": False,
        "db_write": True,
        "description": "승인 요청 생성",
        "nginx_location": "/orchestrator/api/",
        "8400_equiv": None,
        "duplicate_risk": "LOW",
        "migration_tier": "CHARACTERIZATION_NEEDED",
    },
    {
        "path": "/api/v1/tasks/<task_id>/approve",
        "methods": ["POST"],
        "category": "APPROVAL_LEGACY",
        "auth": "basic_auth",
        "external_webhook": False,
        "db_write": True,
        "description": "task 승인 (legacy)",
        "nginx_location": "/orchestrator/api/",
        "8400_equiv": "/api/v1/tasks/{task_id}/approve",
        "duplicate_risk": "HIGH",
        "migration_tier": "ALREADY_ROUTED_TO_8400",
    },
    {
        "path": "/api/v1/tasks/<task_id>/reject",
        "methods": ["POST"],
        "category": "APPROVAL_LEGACY",
        "auth": "basic_auth",
        "external_webhook": False,
        "db_write": True,
        "description": "task 거부 (legacy)",
        "nginx_location": "/orchestrator/api/",
        "8400_equiv": "/api/v1/tasks/{task_id}/reject",
        "duplicate_risk": "HIGH",
        "migration_tier": "ALREADY_ROUTED_TO_8400",
    },
    {
        "path": "/api/v1/tasks/<task_id>/execute",
        "methods": ["POST"],
        "category": "TASK_LEGACY",
        "auth": "basic_auth",
        "external_webhook": False,
        "db_write": True,
        "description": "task 실행 (email_task_executor) — 위험",
        "nginx_location": "/orchestrator/api/",
        "8400_equiv": None,
        "duplicate_risk": "HIGH",
        "migration_tier": "HOLD_DANGEROUS",
    },
    {
        "path": "/api/v1/tasks/<task_id>/approval",
        "methods": ["GET"],
        "category": "APPROVAL_LEGACY",
        "auth": "basic_auth",
        "external_webhook": False,
        "db_write": False,
        "description": "승인 상태 조회",
        "nginx_location": "/orchestrator/api/",
        "8400_equiv": None,
        "duplicate_risk": "LOW",
        "migration_tier": "CHARACTERIZATION_NEEDED",
    },
    # Webhooks (webhooks_router.py, url_prefix=/api/v1/webhooks)
    {
        "path": "/api/v1/webhooks/kakaowork",
        "methods": ["POST"],
        "category": "WEBHOOK_LEGACY",
        "auth": "hmac_signature",
        "external_webhook": True,
        "db_write": True,
        "description": "카카오워크 메시지 수신 — 외부 callback 계약",
        "nginx_location": "/orchestrator/api/",
        "8400_equiv": None,
        "duplicate_risk": "CRITICAL",
        "migration_tier": "DO_NOT_TOUCH",
    },
    {
        "path": "/api/v1/webhooks/kakaotalk-channel",
        "methods": ["POST"],
        "category": "WEBHOOK_LEGACY",
        "auth": "none_or_implicit",
        "external_webhook": True,
        "db_write": True,
        "description": "카카오톡 채널 메시지 수신 — 외부 callback 계약",
        "nginx_location": "/orchestrator/api/",
        "8400_equiv": None,
        "duplicate_risk": "CRITICAL",
        "migration_tier": "DO_NOT_TOUCH",
    },
]

# ── 8400 FastAPI route 목록 (openapi 기준, 이관 관련 항목만) ──────────────────

ROUTES_8400_RELEVANT: list[dict] = [
    {"path": "/api/v1/inbox",                         "methods": ["GET"],          "note": "inbox 목록"},
    {"path": "/api/v1/inbox/email/fetch",             "methods": ["POST"],         "note": "이메일 fetch"},
    {"path": "/api/v1/inbox/{item_id}",               "methods": ["GET"],          "note": "inbox 항목 조회"},
    {"path": "/api/v1/tasks",                         "methods": ["POST"],         "note": "task 생성"},
    {"path": "/api/v1/tasks/{task_id}/approve",       "methods": ["POST"],         "note": "task 승인"},
    {"path": "/api/v1/tasks/{task_id}/reject",        "methods": ["POST"],         "note": "task 거부"},
    {"path": "/api/v1/webhooks/telegram",             "methods": ["POST"],         "note": "Telegram webhook (8400 전용)"},
    {"path": "/api/v1/ops/approvals",                 "methods": ["GET"],          "note": "승인 현황 (ops)"},
]

# ── nginx 라우팅 영향 분석 ─────────────────────────────────────────────────────

NGINX_ANALYSIS = {
    "note": "nginx location 매칭은 더 구체적인 prefix 우선",
    "locations": [
        {
            "location": "/orchestrator/api/v1/local-agents/ws",
            "backend": "8400",
            "priority": 1,
        },
        {
            "location": "/orchestrator/api/",
            "backend": "8400",
            "priority": 2,
            "impact": "5050 /api/v1/* route는 모두 8400으로 먼저 라우팅됨",
        },
        {
            "location": "/orchestrator/admin-web/",
            "backend": "admin-web:3000",
            "priority": 3,
        },
        {
            "location": "/orchestrator/",
            "backend": "5050",
            "priority": 4,
            "impact": "/dashboard, /dashboard/* 만 5050 도달",
        },
    ],
    "critical_finding": (
        "5050의 /api/v1/* route는 nginx /orchestrator/api/ location에 의해 "
        "이미 8400으로 라우팅되고 있음. "
        "5050이 실제 /api/v1/* 요청을 받으려면 nginx를 우회한 직접 호출(127.0.0.1:5050)만 가능. "
        "따라서 nginx 경유 사용자 트래픽은 /api/v1/* 에 대해 이미 8400을 사용 중."
    ),
    "5050_actually_receives": [
        "/dashboard",
        "/dashboard/tasks/<task_id>",
        "/dashboard/approve",
        "/dashboard/reject",
    ],
}

# ── migration matrix ──────────────────────────────────────────────────────────

MIGRATION_TIERS = {
    "ALREADY_ROUTED_TO_8400": {
        "label": "이미 8400으로 라우팅 중",
        "description": "nginx /orchestrator/api/ 덕분에 사용자 트래픽은 이미 8400 처리. "
                       "5050의 동명 route는 nginx 경유 시 무효.",
        "action": "8400 response contract 검증 후 5050 해당 route 폐기 가능",
        "risk": "MEDIUM — contract 검증 전 폐기 금지",
        "next_step": "characterization test로 response 잠금",
    },
    "HOLD_DANGEROUS": {
        "label": "위험 — 실행 보류",
        "description": "/api/v1/tasks/<task_id>/execute — email_task_executor 실행. 실제 업무 수행.",
        "action": "이관 전 email_task_executor 완전 감사 필수. 현재 HOLD.",
        "risk": "HIGH",
        "next_step": "executor 감사 공정 별도 생성",
    },
    "DO_NOT_TOUCH": {
        "label": "이관 금지 — 외부 webhook 계약 존재",
        "description": "카카오워크/카카오톡 채널 webhook. HMAC signature 검증 포함. "
                       "외부 서비스가 이 URL로 POST 전송. URL/로직 변경 시 서비스 단절.",
        "action": "이관 전 반드시 외부 서비스 URL 재등록 + compat 테스트 필요. 현재 금지.",
        "risk": "CRITICAL",
        "next_step": "별도 webhook compat 공정",
    },
    "CHARACTERIZATION_NEEDED": {
        "label": "특성화 테스트 필요",
        "description": "8400 대체 route와 response contract 비교 필요.",
        "action": "현재 5050 response를 테스트로 잠금 후 8400과 비교",
        "risk": "MEDIUM",
        "next_step": "characterization test 공정",
    },
    "LEGACY_ONLY_NEEDS_REVIEW": {
        "label": "5050 전용 — 사용 여부 조사 필요",
        "description": "8400에 대체 없음. 실제 사용 중인지 확인 후 결정.",
        "action": "사용 로그 조사. 미사용이면 폐기 후보.",
        "risk": "LOW-MEDIUM",
        "next_step": "사용 현황 감사",
    },
    "HOLD": {
        "label": "이관 보류",
        "description": "dashboard UI. 사용 여부 및 admin-web /ops 대체 가능 여부 확인 필요.",
        "action": "사용자가 5050 dashboard를 실제 쓰는지 확인 후 결정",
        "risk": "LOW",
        "next_step": "사용 현황 확인 후 admin-web 대체 여부 결정",
    },
}

# ── 추천 공정표 ───────────────────────────────────────────────────────────────

MIGRATION_ROADMAP = [
    {
        "phase": "1단계",
        "name": "Characterization Test",
        "target": "ALREADY_ROUTED_TO_8400 route",
        "work": [
            "8400 /api/v1/inbox GET response 구조 검증 테스트 추가",
            "8400 /api/v1/tasks POST/approve/reject response 계약 잠금",
            "8400 /api/v1/inbox/email/fetch response 잠금",
        ],
        "constraint": "5050 중단 금지. nginx 변경 금지. read-only 비교만.",
        "prerequisite": "없음 — 즉시 시작 가능",
    },
    {
        "phase": "2단계",
        "name": "Legacy Inbox Audit",
        "target": "LEGACY_ONLY_NEEDS_REVIEW — inbox/classify/candidates",
        "work": [
            "5050 /api/v1/inbox/email/classify 사용 로그 확인",
            "5050 /api/v1/inbox/candidates 사용 로그 확인",
            "미사용이면 폐기 후보 지정, 사용 중이면 FastAPI 이식 설계",
        ],
        "constraint": "실제 분류 실행 금지. 로그 read-only.",
        "prerequisite": "1단계 완료",
    },
    {
        "phase": "3단계",
        "name": "Dashboard 대체 전략 결정",
        "target": "HOLD — dashboard UI",
        "work": [
            "5050 dashboard 실제 사용자/사용 빈도 확인",
            "admin-web /ops로 대체 가능 여부 판단",
            "대체 가능하면 5050 dashboard 폐기 계획, 불가하면 FastAPI + 새 UI 설계",
        ],
        "constraint": "admin-web 수정 금지 (이번 공정). 조사만.",
        "prerequisite": "1단계, 2단계 완료",
    },
    {
        "phase": "4단계",
        "name": "Approval Legacy 이관",
        "target": "CHARACTERIZATION_NEEDED — approval-request, task/approval GET",
        "work": [
            "approval-request 흐름 FastAPI로 이식",
            "task approval GET FastAPI 추가",
            "response contract 검증 후 5050 해당 route 비활성화",
        ],
        "constraint": "실제 승인 실행 금지. 계약 검증 테스트 후 이관.",
        "prerequisite": "1단계 완료",
    },
    {
        "phase": "5단계",
        "name": "Webhook Compat 설계",
        "target": "DO_NOT_TOUCH — kakaowork/kakaotalk",
        "work": [
            "8400 /api/v1/webhooks/kakaowork 신규 구현 (HMAC 포함)",
            "외부 서비스 URL 재등록 계획 수립",
            "staging 환경에서 webhook compat 테스트",
            "전환 완료 후 5050 webhook route 폐기",
        ],
        "constraint": "외부 서비스 실제 URL 변경 전 compat 테스트 필수. 최후순위.",
        "prerequisite": "1~4단계 완료. 외부 서비스 협의 필요.",
    },
    {
        "phase": "6단계",
        "name": "5050 종료 및 nginx 정리",
        "target": "5050 전체 — dashboard/webhook 이관 완료 후",
        "work": [
            "5050 프로세스 중단",
            "nginx /orchestrator/ location 제거 또는 404 반환으로 교체",
            "최종 smoke",
        ],
        "constraint": "1~5단계 전체 완료 후에만 진행. 이번 공정에서 실행 금지.",
        "prerequisite": "1~5단계 전체 완료",
    },
]


def _build_route_matrix() -> dict:
    by_tier: dict[str, list] = {}
    for r in ROUTES_5050:
        tier = r["migration_tier"]
        by_tier.setdefault(tier, [])
        by_tier[tier].append({"path": r["path"], "methods": r["methods"], "category": r["category"]})
    return by_tier


def _find_overlaps() -> list[dict]:
    overlaps = []
    for r in ROUTES_5050:
        if r["8400_equiv"]:
            overlaps.append({
                "5050_path": r["path"],
                "8400_path": r["8400_equiv"],
                "risk": r["duplicate_risk"],
                "nginx_note": (
                    "nginx /orchestrator/api/ → 8400 이므로 사용자 트래픽은 8400 처리 중"
                    if r["nginx_location"] == "/orchestrator/api/"
                    else "nginx /orchestrator/ → 5050"
                ),
            })
    return overlaps


def _build_report() -> dict:
    matrix = _build_route_matrix()
    overlaps = _find_overlaps()

    return {
        "verdict": "MIGRATION_PLAN_READY",
        "read_only": READ_ONLY,
        "shutdown_5050_forbidden": SHUTDOWN_5050_FORBIDDEN,
        "nginx_change_forbidden": NGINX_CHANGE_FORBIDDEN,
        "full_route_switch_forbidden": FULL_ROUTE_SWITCH_FORBIDDEN,
        "routes_5050_total": len(ROUTES_5050),
        "routes_8400_relevant": len(ROUTES_8400_RELEVANT),
        "overlap_routes": overlaps,
        "migration_matrix": matrix,
        "nginx_analysis": NGINX_ANALYSIS,
        "migration_tiers": {k: {"label": v["label"], "risk": v["risk"], "next_step": v["next_step"]} for k, v in MIGRATION_TIERS.items()},
        "migration_roadmap": MIGRATION_ROADMAP,
        "critical_finding": NGINX_ANALYSIS["critical_finding"],
        "5050_actually_receives_via_nginx": NGINX_ANALYSIS["5050_actually_receives"],
        "do_not_touch_routes": [r["path"] for r in ROUTES_5050 if r["migration_tier"] == "DO_NOT_TOUCH"],
        "immediate_action_possible": [r["path"] for r in ROUTES_5050 if r["migration_tier"] == "ALREADY_ROUTED_TO_8400"],
    }


def _print_summary(report: dict) -> None:
    print(f"판정: {report['verdict']}")
    print(f"read_only: {report['read_only']}")
    print(f"shutdown_5050_forbidden: {report['shutdown_5050_forbidden']}")
    print()

    print("=== 핵심 발견사항 ===")
    print(f"  {report['critical_finding']}")
    print()

    print("=== nginx에서 5050이 실제 받는 경로 ===")
    for p in report["5050_actually_receives_via_nginx"]:
        print(f"  {p}")
    print()

    print("=== migration matrix ===")
    for tier, routes in report["migration_matrix"].items():
        ti = MIGRATION_TIERS.get(tier, {})
        label = ti.get("label", tier)
        risk = ti.get("risk", "?")
        print(f"\n  [{tier}] {label} (risk={risk})")
        for r in routes:
            print(f"    {r['methods']} {r['path']}  ({r['category']})")

    print()
    print("=== 중복/충돌 route ===")
    for o in report["overlap_routes"]:
        print(f"  5050: {o['5050_path']}  ↔  8400: {o['8400_path']}  risk={o['risk']}")
        print(f"    → {o['nginx_note']}")

    print()
    print("=== DO_NOT_TOUCH ===")
    for p in report["do_not_touch_routes"]:
        print(f"  {p}  (외부 webhook 계약 존재, 이관 금지)")

    print()
    print("=== 추천 공정표 ===")
    for phase in report["migration_roadmap"]:
        print(f"  {phase['phase']}: {phase['name']}")
        print(f"    대상: {phase['target']}")
        print(f"    선행: {phase['prerequisite']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = _build_report()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_summary(report)

    sys.exit(0)


if __name__ == "__main__":
    main()
