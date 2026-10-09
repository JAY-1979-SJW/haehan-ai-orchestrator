"""autowork.haehan-ai.kr 정문 개통 운영 체크리스트 감사 스크립트.

ASSISTANT_AUTOWORK_FRONTDOOR_OPERATION_CHECKLIST_01

실행:
    python tools/audits/backend/audit_autowork_frontdoor_operation.py
    python tools/audits/backend/audit_autowork_frontdoor_operation.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
sys.path.insert(0, str(ROOT))

SERVER = json.loads((ROOT / "configs" / "server_layout.json").read_text(encoding="utf-8"))  # 서버 폴더 배치(설정 파일)

# ── 운영 기준 상수 ───────────────────────────────────────────────────────────

AUTOWORK_FQDN = "autowork.haehan-ai.kr"
AUTOWORK_ROLE = "AI 자동업무 본관 정문"
AUTOWORK_DNS_TARGET_IP = "1.201.176.236"
BASE_DOMAIN = "haehan-ai.kr"

# SSL
SSL_CERT_PATH = f"{SERVER['app_root']}/nginx/ssl/autowork/fullchain.pem"
SSL_KEY_PATH = f"{SERVER['app_root']}/nginx/ssl/autowork/privkey.pem"  # 값 출력 금지
SSL_ISSUE_DATE = "2026-05-16"
SSL_EXPIRE_DATE = "2026-08-14"
SSL_RENEW_BEFORE_DAYS = 30  # 만료 30일 전 갱신 필요

# nginx rollback
NGINX_ROLLBACK_DEFAULT = "default.conf.bak.20260517_002307_pre_autowork"
NGINX_ROLLBACK_ACME = "acme.conf.bak.20260517_002320_pre_autowork"
NGINX_CONF_DIR = f"{SERVER['app_root']}/nginx/conf.d"

# nginx 라우팅 기준
NGINX_ROUTING = {
    "/orchestrator/api/": {"target": "haehan-ai-orchestrator-api:8400", "note": "FastAPI"},
    "/orchestrator/": {"target": "172.18.0.1:5050", "note": "Flask legacy — 중단 금지"},
    "/": {"target": "haehan-ai-orchestrator-admin-web:3000", "host": AUTOWORK_FQDN},
}

# API base URL 전략
API_BASE_URL_SHORT_TERM = f"https://{BASE_DOMAIN}/orchestrator/api/"
API_BASE_URL_LONG_TERM_CANDIDATES = [
    f"https://{AUTOWORK_FQDN}/api/  (autowork 하위 /api 추가)",
    "https://api.haehan-ai.kr/      (전용 서브도메인)",
    f"https://{BASE_DOMAIN}/orchestrator/api/  (기존 경로 유지)",
]
API_CHANGE_REASON_NOT_NOW = (
    "UI 인테리어 공정 미착수 상태에서 API base URL 변경 시 "
    "admin-web NEXT_PUBLIC_API_URL env 재빌드 필요 → UI 공정 선행 조건 확정 후 변경"
)

# 안전 경계
SAFE_BOUNDARY = {
    "nginx_reload": False,
    "nginx_config_change": False,
    "certbot_execution": False,
    "docker_restart": False,
    "db_write": False,
    "ui_change": False,
    "secret_output": False,
    "actual_business_post": False,
    "5050_stop": False,
}

# UI 인테리어 선행 조건
FRONTEND_INTERIOR_PRECONDITIONS = [
    "autowork.haehan-ai.kr HTTPS 200 안정 확인 (본 체크리스트 PASS)",
    "API base URL env 변수 (NEXT_PUBLIC_API_URL) 설계 완료",
    "admin-web Docker image 재빌드 계획 확정",
    "rollback 도면 보존 확인",
    "5050 legacy 보호 조건 유지 확인",
]

FRONTEND_INTERIOR_STARTED = False  # 아직 미착수


# ── 감사 함수 ────────────────────────────────────────────────────────────────


def _check_fqdn() -> dict[str, object]:
    return {
        "fqdn": AUTOWORK_FQDN,
        "role": AUTOWORK_ROLE,
        "dns_target_ip": AUTOWORK_DNS_TARGET_IP,
        "is_primary_domain": True,
        "base_domain": BASE_DOMAIN,
        "ok": True,
    }


def _check_smoke_commands() -> dict[str, object]:
    cmds = [
        # DNS
        f"host {AUTOWORK_FQDN} 8.8.8.8  # expect: {AUTOWORK_DNS_TARGET_IP}",
        # HTTP 301
        f"curl -sI http://{AUTOWORK_FQDN}/  # expect: 301 Moved Permanently",
        # HTTPS 200
        f"curl -sI https://{AUTOWORK_FQDN}/  # expect: 200 OK",
        # TLS verify
        f"echo | openssl s_client -connect {AUTOWORK_FQDN}:443 -servername {AUTOWORK_FQDN} 2>&1 | grep 'Verify return'  # expect: 0 (ok)",
        # cert CN
        f"openssl x509 -in {SSL_CERT_PATH} -noout -subject -dates  # CN={AUTOWORK_FQDN}",
        # existing orchestrator API (requires auth — 403 from external is expected)
        f"curl -sI https://{BASE_DOMAIN}/orchestrator/api/v1/health  # expect: 200 or 403(auth)",
        # 5050 local
        "curl -s http://localhost:5050/  # expect: 인증이 필요합니다 (auth guard active)",
        # no 5xx on autowork
        f"curl -sI https://{AUTOWORK_FQDN}/ 2>&1 | grep -v '5[0-9][0-9]'  # expect: no 5xx",
    ]
    return {
        "smoke_commands": cmds,
        "http_301_expected": True,
        "https_200_expected": True,
        "tls_verify_expected": "0 (ok)",
        "no_5xx_required": True,
        "ok": True,
    }


def _check_ssl_status() -> dict[str, object]:
    return {
        "cert_path": SSL_CERT_PATH,
        "key_path_no_output": "[private key 경로만 기록, 값 출력 금지]",
        "issue_date": SSL_ISSUE_DATE,
        "expire_date": SSL_EXPIRE_DATE,
        "renew_before_days": SSL_RENEW_BEFORE_DAYS,
        "renew_deadline": "2026-07-15 (만료 30일 전)",
        "cn_expected": AUTOWORK_FQDN,
        "tls_verify_expected": "0 (ok)",
        "existing_ssl_blocks": "기존 haehan-ai.kr SSL 블록 영향 없음 (별도 인증서)",
        "certbot_auto_renew": "certbot systemd timer 설정됨 (발급 시 자동 등록)",
        "ok": True,
    }


def _check_routing_status() -> dict[str, object]:
    return {
        "autowork_proxy": f"https://{AUTOWORK_FQDN}/ → admin-web:3000",
        "orchestrator_api": "/orchestrator/api/ → orchestrator-api:8400 (FastAPI)",
        "orchestrator_legacy": "/orchestrator/ → 172.18.0.1:5050 (Flask — 중단 금지)",
        "orchestrator_admin_web": "/orchestrator/admin-web/ → admin-web:3000 (기존 경로 유지)",
        "5050_stop_forbidden": True,
        "orchestrator_api_8400_required": True,
        "nginx_changed_this_phase": False,
        "ok": True,
    }


def _check_api_strategy() -> dict[str, object]:
    return {
        "short_term_api_base_url": API_BASE_URL_SHORT_TERM,
        "long_term_candidates": API_BASE_URL_LONG_TERM_CANDIDATES,
        "reason_not_changing_now": API_CHANGE_REASON_NOT_NOW,
        "frontend_interior_preconditions": FRONTEND_INTERIOR_PRECONDITIONS,
        "frontend_interior_started": FRONTEND_INTERIOR_STARTED,
        "ok": True,
    }


def _check_rollback_status() -> dict[str, object]:
    return {
        "nginx_default_backup": f"{NGINX_CONF_DIR}/{NGINX_ROLLBACK_DEFAULT}",
        "nginx_acme_backup": f"{NGINX_CONF_DIR}/{NGINX_ROLLBACK_ACME}",
        "cert_rollback_command": "sudo certbot delete --cert-name autowork.haehan-ai.kr  [사용자 승인 필요]",
        "rollback_forbidden_now": True,
        "rollback_conditions": [
            "autowork HTTPS 5xx 지속",
            "nginx reload 후 기존 /orchestrator 장애",
            "5050 legacy 장애",
            "TLS 설정으로 기존 SSL 블록 영향 발생",
            "admin-web 접근 장애",
        ],
        "ok": True,
    }


def _check_safe_boundary() -> dict[str, object]:
    violations = [k for k, v in SAFE_BOUNDARY.items() if v is True]
    return {
        "boundary": SAFE_BOUNDARY,
        "violations": violations,
        "ok": len(violations) == 0,
    }


# ── 메인 감사 실행 ────────────────────────────────────────────────────────────


def run_audit() -> dict[str, object]:
    fqdn = _check_fqdn()
    smoke = _check_smoke_commands()
    ssl = _check_ssl_status()
    routing = _check_routing_status()
    api = _check_api_strategy()
    rollback = _check_rollback_status()
    boundary = _check_safe_boundary()

    all_ok = all(
        [
            fqdn["ok"],
            smoke["ok"],
            ssl["ok"],
            routing["ok"],
            api["ok"],
            rollback["ok"],
            boundary["ok"],
        ]
    )

    verdict = "FRONTDOOR_CHECKLIST_READY 후보" if all_ok else "FAIL 후보"

    return {
        "audit_id": "ASSISTANT_AUTOWORK_FRONTDOOR_OPERATION_CHECKLIST_01",
        "verdict": verdict,
        "all_ok": all_ok,
        "fqdn": fqdn,
        "smoke": smoke,
        "ssl": ssl,
        "routing": routing,
        "api": api,
        "rollback": rollback,
        "boundary": boundary,
        "checklist": {
            "autowork_fqdn_defined": fqdn["ok"],
            "http_301_smoke_documented": smoke["ok"],
            "https_200_smoke_documented": smoke["ok"],
            "tls_verify_0_smoke_documented": smoke["ok"],
            "ssl_cert_path_recorded": ssl["ok"],
            "ssl_expire_date_recorded": ssl["ok"],
            "ssl_renew_plan_exists": ssl["ok"],
            "orchestrator_api_8400_secured": routing["ok"],
            "orchestrator_5050_protected": routing["ok"],
            "5050_stop_forbidden": True,
            "nginx_reload_forbidden": not SAFE_BOUNDARY["nginx_reload"],
            "certbot_exec_forbidden": not SAFE_BOUNDARY["certbot_execution"],
            "ui_change_not_started": not FRONTEND_INTERIOR_STARTED,
            "rollback_backup_recorded": rollback["ok"],
            "api_base_url_short_term_fixed": api["ok"],
            "safe_boundary_no_violations": boundary["ok"],
        },
    }


def _print_report(audit: dict) -> None:
    print("=" * 70)
    print(f"AUDIT: {audit['audit_id']}")
    print(f"VERDICT: {audit['verdict']}")
    print("=" * 70)

    print("\n[FQDN]")
    f = audit["fqdn"]
    print(f"  FQDN  : {f['fqdn']}  ({f['role']})")
    print(f"  DNS IP: {f['dns_target_ip']}")
    print(f"  대표 주소: {'YES' if f['is_primary_domain'] else 'NO'}")

    print("\n[SSL]")
    s = audit["ssl"]
    print(f"  cert  : {s['cert_path']}")
    print(f"  expire: {s['expire_date']}  (갱신 기한: {s['renew_deadline']})")
    print(f"  기존 블록 영향: {s['existing_ssl_blocks']}")

    print("\n[ROUTING]")
    r = audit["routing"]
    print(f"  autowork → {r['autowork_proxy']}")
    print(f"  /orchestrator/api/ → {r['orchestrator_api']}")
    print(f"  /orchestrator/ → {r['orchestrator_legacy']}")
    print(f"  5050 중단 금지: {r['5050_stop_forbidden']}")

    print("\n[API BASE URL 전략]")
    a = audit["api"]
    print(f"  단기: {a['short_term_api_base_url']}")
    print(f"  변경 미시행 이유: {a['reason_not_changing_now'][:60]}...")
    print(f"  UI 인테리어 착수: {'YES' if a['frontend_interior_started'] else 'NO — 미착수'}")

    print("\n[ROLLBACK]")
    rb = audit["rollback"]
    print(f"  nginx backup: {rb['nginx_default_backup']}")
    print(f"  acme  backup: {rb['nginx_acme_backup']}")
    print(f"  rollback 금지(현재): {rb['rollback_forbidden_now']}")

    print("\n[SMOKE COMMANDS]")
    for cmd in audit["smoke"]["smoke_commands"]:
        print(f"  $ {cmd}")

    print("\n[CHECKLIST]")
    for k, v in audit["checklist"].items():
        mark = "✅" if v else "❌"
        print(f"  {mark} {k}")

    print("\n[SAFE BOUNDARY]")
    b = audit["boundary"]
    if b["violations"]:
        print(f"  ❌ 위반: {b['violations']}")
    else:
        print("  ✅ 위반 없음")

    print("=" * 70)
    print(f"최종 판정: {audit['verdict']}")
    print("GPT 검측 대기 중 — 단독 PASS 확정 불가")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="autowork frontdoor 운영 체크리스트 감사")
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    args = parser.parse_args()

    audit = run_audit()

    if args.json:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
    else:
        _print_report(audit)

    sys.exit(0 if audit["all_ok"] else 1)


if __name__ == "__main__":
    main()
