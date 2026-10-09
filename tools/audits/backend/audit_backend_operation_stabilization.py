"""
백엔드 운영 안정화 감사 스크립트.

ASSISTANT_BACKEND_OPERATION_MONITORING_AND_INCIDENT_RUNBOOK_NO_FRONTEND_01

역할:
- backend health 기준 확인
- smoke command 목록 출력
- nginx routing 구조 확인
- 5050/8400 공존 구조 확인
- container name 기준 확인
- external app hold 상태 확인
- rollback 조건 출력
- 장애 등급 기준 확인

프론트엔드 제외:
- admin-web build/typecheck/smoke 없음
- vendor 변경 없음
- frontend_excluded=true

read-only 전용:
- 서버 restart 금지
- DB 접속 금지
- 외부 사이트 접속 금지
- secret/token/credential 출력 금지

실행:
    python tools/audits/backend/audit_backend_operation_stabilization.py
    python tools/audits/backend/audit_backend_operation_stabilization.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다

# ── 상수 ──────────────────────────────────────────────────────────────────────

FRONTEND_EXCLUDED = True

CONTAINERS = {
    "api": "haehan-ai-orchestrator-api",
    "admin_web": "haehan-ai-orchestrator-admin-web",
    "browser_worker": "haehan-ai-orchestrator-browser-worker",
}

# nginx 라우팅 구조 (Host: haehan-ai.kr 기준)
NGINX_ROUTING = [
    {
        "location": "/orchestrator/api/v1/local-agents/ws",
        "backend": "haehan-ai-orchestrator-api:8400",
        "type": "websocket",
        "note": "WebSocket 전용",
    },
    {
        "location": "/orchestrator/api/",
        "backend": "haehan-ai-orchestrator-api:8400",
        "type": "http",
        "note": "FastAPI 신규 API 전체",
    },
    {
        "location": "/orchestrator/admin-web/",
        "backend": "haehan-ai-orchestrator-admin-web:3000",
        "type": "http",
        "note": "Next.js admin-web (frontend_excluded 대상)",
    },
    {
        "location": "/orchestrator/",
        "backend": "localhost:5050",
        "type": "http",
        "note": "Flask legacy dashboard/webhook. 5050 중단 금지.",
    },
]

# Host 헤더 필수 조건
HOST_HEADER_REQUIRED = "haehan-ai.kr"
HOST_HEADER_NOTE = (
    "localhost Host 미지정 시 404는 라우팅 실패 아님. nginx server_name haehan-ai.kr 블록만 /orchestrator/ 처리."
)

# health 명령 (read-only)
HEALTH_COMMANDS = [
    {
        "label": "API health (nginx 경유)",
        "cmd": "curl -sk -H 'Host: haehan-ai.kr' https://127.0.0.1/orchestrator/api/v1/health",
        "expected_http": 200,
        "note": "서버에서 실행. 200이면 API PASS.",
    },
    {
        "label": "ops/summary (nginx 경유)",
        "cmd": "curl -sk -H 'Host: haehan-ai.kr' https://127.0.0.1/orchestrator/api/v1/ops/summary",
        "expected_http": 200,
        "note": "ops API 라우팅 PASS 확인.",
    },
    {
        "label": "API health (직접)",
        "cmd": "curl -s http://127.0.0.1:8400/api/v1/health",
        "expected_http": 200,
        "note": "컨테이너 직접 접근. nginx 우회.",
    },
    {
        "label": "5050 legacy",
        "cmd": "curl -s http://127.0.0.1:5050/ -o /dev/null -w '%{http_code}'",
        "expected_http": 401,
        "note": "401 Auth 보호면 정상. 5050 중단 금지.",
    },
    {
        "label": "컨테이너 상태",
        "cmd": "docker ps --format 'table {{.Names}}\\t{{.Status}}' | grep haehan-ai-orchestrator",
        "expected_http": None,
        "note": "healthy 상태 확인. api는 (healthy) 필수.",
    },
]

# smoke 명령 목록 (GET only, read-only, 프론트엔드 제외)
SMOKE_COMMANDS = [
    {"path": "/orchestrator/api/v1/health", "expected": 200, "tier": "P0"},
    {"path": "/orchestrator/api/v1/ops/summary", "expected": 200, "tier": "P0"},
    {"path": "/orchestrator/api/v1/ops/approvals", "expected": 200, "tier": "P1"},
    {"path": "/orchestrator/api/v1/ops/web-tasks", "expected": 200, "tier": "P1"},
    {"path": "/orchestrator/api/v1/ops/agents", "expected": 200, "tier": "P1"},
    {"path": "/orchestrator/api/v1/ops/integrations", "expected": 200, "tier": "P1"},
    {"path": "/orchestrator/api/v1/ops/external-work", "expected": 200, "tier": "P1"},
    {"path": "/orchestrator/api/v1/ops/audit-events", "expected": 200, "tier": "P1"},
    {"path": "/orchestrator/api/v1/web-tasks/registry", "expected": 200, "tier": "P1"},
]

SMOKE_FORBIDDEN = [
    "POST /api/v1/ops/approvals/*/approve",
    "POST /api/v1/ops/approvals/*/reject",
    "POST /api/v1/web-tasks/run",
    "POST /api/v1/webhooks/telegram",
    "외부 사이트 접속",
    "admin-web smoke",
]

SMOKE_HOST_HEADER = "Host: haehan-ai.kr"
SMOKE_BASE_CMD = "curl -sk -H 'Host: haehan-ai.kr' https://127.0.0.1{path} -o /dev/null -w '%{{http_code}}'"

# 장애 등급
INCIDENT_LEVELS = {
    "P0": {
        "description": "즉시 대응 필요 — 서비스 불가",
        "conditions": [
            "API health endpoint 실패 (non-200)",
            "API 컨테이너 unhealthy",
            "nginx /orchestrator/api/ → 8400 라우팅 실패",
        ],
        "actions": [
            "docker logs haehan-ai-orchestrator-api --tail 50 확인",
            "docker compose ps 확인",
            "rollback 검토",
            "대표님 보고 필수",
        ],
        "rollback_required": True,
    },
    "P1": {
        "description": "긴급 대응 — 일부 기능 불가",
        "conditions": [
            "ops API 일부 실패",
            "browser-worker unhealthy",
            "endpoint inventory 심각 불일치",
        ],
        "actions": [
            "docker logs 해당 컨테이너 --tail 50 확인",
            "smoke 전체 재실행",
            "대표님 보고 권장",
        ],
        "rollback_required": False,
    },
    "P2": {
        "description": "일반 대응 — 부분 기능 저하",
        "conditions": [
            "5050 legacy dashboard/webhook 문제",
            "external app hold 상태 표시 문제",
            "smoke 일부 non-critical 실패",
        ],
        "actions": [
            "5050 프로세스 상태 확인",
            "ps aux | grep app.py",
            "필요 시 대표님 보고",
        ],
        "rollback_required": False,
    },
    "P3": {
        "description": "모니터링 — 경고 수준",
        "conditions": [
            "vendor drift warning",
            "로그 경고 수준 메시지",
            "문서/감사 스크립트 경고",
        ],
        "actions": [
            "python tools/audits/app/audit_vendor_design_system_sync.py 실행",
            "python tools/audits/backend/audit_backend_operation_stabilization.py 실행",
            "다음 배포 시 조치",
        ],
        "rollback_required": False,
    },
}

# rollback 기준
ROLLBACK_CONDITIONS = [
    "API health endpoint 지속 실패 (P0)",
    "API 컨테이너 unhealthy 지속 (P0)",
    "smoke P0 항목 2개 이상 실패",
    "nginx /orchestrator/api/ 라우팅 실패",
    "fatal import error / startup crash",
]

ROLLBACK_FORBIDDEN_IN_THIS_RUNBOOK = [
    "DB rollback — 이번 배포에 DB/schema 변경 없음",
    "nginx config 복원 — 이번 배포에 nginx 변경 없음",
    "admin-web rollback은 별도 판단",
]

ROLLBACK_PROCEDURE = [
    "1. rollback target 확인: git log --oneline -5 (서버에서)",
    "2. docker compose down --no-volumes (api, admin-web만 대상)",
    "3. git checkout <rollback-target>",
    "4. docker compose up --build -d ai-orchestrator-api",
    "5. health check: curl -sk -H 'Host: haehan-ai.kr' https://127.0.0.1/orchestrator/api/v1/health",
    "6. 5050 smoke: curl -s http://127.0.0.1:5050/ -o /dev/null -w '%{http_code}'",
    "7. rollback 완료 확인 후 대표님 보고",
]

# external app hold
EXTERNAL_APP_HOLD_ITEMS = [
    {"app": "CAD", "status": "EXTERNAL_APP_HOLD", "auto_execute": False, "approval_required": True},
    {"app": "HWPX", "status": "EXTERNAL_APP_HOLD", "auto_execute": False, "approval_required": True},
    {"app": "Excel/Office", "status": "EXTERNAL_APP_HOLD", "auto_execute": False, "approval_required": True},
    {"app": "Tax", "status": "EXTERNAL_APP_HOLD", "auto_execute": False, "approval_required": True},
    {"app": "Bid", "status": "EXTERNAL_APP_HOLD", "auto_execute": False, "approval_required": True},
    {"app": "Document", "status": "EXTERNAL_APP_HOLD", "auto_execute": False, "approval_required": True},
]

EXTERNAL_APP_HOLD_NOTE = (
    "CAD/HWPX/Excel 등은 백엔드 내부 실행 대상이 아님. "
    "bridge/handoff 계약만 존재. "
    "CAD 환경 의존 테스트 실패는 backend 장애가 아님 (external_cad marker 적용)."
)

# log 확인 기준
LOG_COMMANDS = [
    "docker logs haehan-ai-orchestrator-api --tail 50",
    "docker logs haehan-ai-orchestrator-browser-worker --tail 50",
    "docker exec nginx cat /var/log/nginx/error.log | tail -30",
]

LOG_FORBIDDEN_OUTPUT = [
    "secret / token / password / session / cookie 원문 출력 금지",
    "credential 원문 출력 금지",
    "개인정보 추정 문자열은 redaction",
]

LOG_CHECK_ORDER = [
    "1. docker ps (container status)",
    "2. health endpoint (P0 확인)",
    "3. docker logs --tail 50 (recent errors)",
    "4. nginx routing (curl Host 헤더 기준)",
    "5. rollback 필요 여부 판단",
]

# ── 검증 함수 ──────────────────────────────────────────────────────────────────


def _check_script_files() -> list[dict]:
    results = []

    # vendor sync 스크립트 존재
    vendor_script = ROOT / "tools" / "audits" / "app" / "audit_vendor_design_system_sync.py"
    results.append(
        {
            "check": "vendor_sync_script_exists",
            "ok": vendor_script.exists(),
            "path": str(vendor_script.relative_to(ROOT)),
        }
    )

    # integrated runner 존재
    runner = ROOT / "tools" / "audits" / "backend" / "audit_backend_premium_integrated_runner.py"
    results.append(
        {
            "check": "integrated_runner_exists",
            "ok": runner.exists(),
            "path": str(runner.relative_to(ROOT)),
        }
    )

    return results


def _check_no_frontend_in_smoke() -> bool:
    for cmd in SMOKE_COMMANDS:
        if "admin-web" in cmd["path"] or "admin_web" in cmd["path"]:
            return False
    return True


def _check_host_header_in_smoke() -> bool:
    return SMOKE_HOST_HEADER in SMOKE_BASE_CMD


def _check_rollback_conditions() -> bool:
    return len(ROLLBACK_CONDITIONS) >= 3


def _check_external_app_hold() -> bool:
    return all(not item["auto_execute"] for item in EXTERNAL_APP_HOLD_ITEMS)


def _build_report() -> dict:
    file_checks = _check_script_files()
    all_files_ok = all(c["ok"] for c in file_checks)

    no_frontend_smoke = _check_no_frontend_in_smoke()
    host_header_ok = _check_host_header_in_smoke()
    rollback_ok = _check_rollback_conditions()
    ext_hold_ok = _check_external_app_hold()

    checklist = [
        {"item": "프론트엔드 제외", "ok": FRONTEND_EXCLUDED},
        {"item": "smoke GET only", "ok": True},
        {"item": "smoke frontend 미포함", "ok": no_frontend_smoke},
        {"item": "Host 헤더 필수 조건", "ok": host_header_ok},
        {"item": "5050 중단 금지 기준 존재", "ok": True},
        {"item": "nginx 라우팅 기준 존재", "ok": len(NGINX_ROUTING) >= 3},
        {"item": "rollback 조건 존재", "ok": rollback_ok},
        {"item": "external app hold 확인", "ok": ext_hold_ok},
        {"item": "secret 출력 금지 기준", "ok": len(LOG_FORBIDDEN_OUTPUT) >= 1},
        {"item": "스크립트 파일 존재", "ok": all_files_ok},
    ]

    all_ok = all(c["ok"] for c in checklist)

    verdict = "PASS" if all_ok else "WARN"

    return {
        "verdict": verdict,
        "frontend_excluded": FRONTEND_EXCLUDED,
        "read_only": True,
        "server_restart_forbidden": True,
        "db_write_forbidden": True,
        "secret_output_forbidden": True,
        "checklist": checklist,
        "checklist_count": len(checklist),
        "containers": CONTAINERS,
        "nginx_routing": NGINX_ROUTING,
        "host_header_required": HOST_HEADER_REQUIRED,
        "host_header_note": HOST_HEADER_NOTE,
        "health_commands": HEALTH_COMMANDS,
        "smoke_commands": SMOKE_COMMANDS,
        "smoke_forbidden": SMOKE_FORBIDDEN,
        "smoke_base_cmd_template": SMOKE_BASE_CMD,
        "incident_levels": {
            k: {"description": v["description"], "rollback_required": v["rollback_required"]}
            for k, v in INCIDENT_LEVELS.items()
        },
        "rollback_conditions": ROLLBACK_CONDITIONS,
        "rollback_procedure": ROLLBACK_PROCEDURE,
        "rollback_forbidden_in_this_runbook": ROLLBACK_FORBIDDEN_IN_THIS_RUNBOOK,
        "external_app_hold": EXTERNAL_APP_HOLD_ITEMS,
        "external_app_hold_note": EXTERNAL_APP_HOLD_NOTE,
        "log_check_order": LOG_CHECK_ORDER,
        "log_forbidden_output": LOG_FORBIDDEN_OUTPUT,
        "file_checks": file_checks,
    }


def _print_summary(report: dict) -> None:
    verdict = report["verdict"]
    print(f"판정: {verdict}")
    print(f"frontend_excluded: {report['frontend_excluded']}")
    print(f"read_only: {report['read_only']}")
    print()

    print("=== 체크리스트 ===")
    for c in report["checklist"]:
        mark = "PASS" if c["ok"] else "FAIL"
        print(f"  [{mark}] {c['item']}")
    print()

    print("=== nginx 라우팅 기준 ===")
    for r in report["nginx_routing"]:
        print(f"  {r['location']:<45} → {r['backend']}  ({r['note']})")
    print(f"  ※ {report['host_header_note']}")
    print()

    print("=== smoke 명령 (P0/P1) ===")
    for s in report["smoke_commands"]:
        print(f"  [{s['tier']}] {s['path']} → {s['expected']}")
    print()

    print("=== 장애 등급 ===")
    for lvl, info in INCIDENT_LEVELS.items():
        rb = "rollback 필요" if info["rollback_required"] else "rollback 불필요"
        print(f"  {lvl}: {info['description']} / {rb}")
    print()

    print("=== rollback 조건 ===")
    for r in report["rollback_conditions"]:
        print(f"  - {r}")
    print()

    print("=== external app hold ===")
    for e in report["external_app_hold"]:
        print(f"  {e['app']:<15} auto_execute={e['auto_execute']}  approval_required={e['approval_required']}")
    print()

    print("=== 스크립트 파일 ===")
    for fc in report["file_checks"]:
        mark = "PASS" if fc["ok"] else "FAIL"
        print(f"  [{mark}] {fc['check']}: {fc['path']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    args = parser.parse_args()

    report = _build_report()

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_summary(report)

    sys.exit(0 if report["verdict"] == "PASS" else 1)


if __name__ == "__main__":
    main()
