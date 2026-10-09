"""신규 웹/서브도메인 착공 표준 계획 생성기.

ASSISTANT_WEB_PROJECT_PROVISIONING_SCRIPT_FACTORY_01

실행:
    python tools/deploy/create_web_project_provisioning_plan.py --fqdn autowork.haehan-ai.kr
    python tools/deploy/create_web_project_provisioning_plan.py --fqdn newservice.haehan-ai.kr \\
        --project-id newservice --display-name "새 업무동" --json
    python tools/deploy/create_web_project_provisioning_plan.py --fqdn autowork.haehan-ai.kr --check-only

금지:
    실제 DNS 변경 금지 / nginx 수정 금지 / certbot 실행 금지
    서버 접속 금지 / DB write 금지 / UI 변경 금지
    secret/token/password 출력 금지
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = next(
    p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").is_file()
)  # haehan-root-bootstrap: 폴더 깊이와 무관 — pyproject.toml 이 있는 상위 폴더를 찾는다
sys.path.insert(0, str(ROOT))

# ── 전역 상수 ────────────────────────────────────────────────────────────────

DEFAULT_ROOT_DOMAIN = "haehan-ai.kr"
DEFAULT_SERVER_IP_VAR = "SERVER_PUBLIC_IP"
LEGACY_5050_TARGET = "172.18.0.1:5050"
LEGACY_ORCHESTRATOR_API = "haehan-ai-orchestrator-api:8400"
BASE_API_PATH = "/orchestrator/api/"

# API 전략 선택지
API_STRATEGIES = {
    "existing-orchestrator-api": {
        "base_url": f"https://{DEFAULT_ROOT_DOMAIN}{BASE_API_PATH}",
        "note": "기존 /orchestrator/api/ 경로 유지 — UI 인테리어 공정 전 변경 금지",
        "change_allowed_now": False,
    },
    "subdomain-api": {
        "base_url": f"https://api.{DEFAULT_ROOT_DOMAIN}/",
        "note": "전용 api 서브도메인 — 별도 DNS/nginx/SSL 공정 필요",
        "change_allowed_now": False,
    },
    "fqdn-api-path": {
        "base_url": "https://{fqdn}/api/",
        "note": "신규 FQDN 하위 /api/ 경로 — nginx 블록 추가 필요",
        "change_allowed_now": False,
    },
}

# 안전 경계 (절대 변경 금지)
SAFE_BOUNDARY = {
    "actual_dns_write": False,
    "actual_nginx_change": False,
    "actual_certbot": False,
    "actual_gabia_access": False,
    "actual_server_access": False,
    "actual_db_write": False,
    "actual_ui_change": False,
    "secret_output": False,
    "5050_stop": False,
    "nginx_reload": False,
    "docker_restart": False,
}


# ── 모델 ─────────────────────────────────────────────────────────────────────


def _split_fqdn(fqdn: str) -> tuple[str, str]:
    """fqdn → (host, root_domain). 예: autowork.haehan-ai.kr → ('autowork', 'haehan-ai.kr')"""
    parts = fqdn.strip().split(".", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return fqdn, DEFAULT_ROOT_DOMAIN


def make_dns_draft(
    fqdn: str,
    host: str,
    root_domain: str,
    record_type: str,
    value_source: str,
    ttl: int = 600,
) -> dict[str, Any]:
    return {
        "fqdn": fqdn,
        "root_domain": root_domain,
        "host": host,
        "record_type": record_type,
        "value_source": value_source,
        "ttl": ttl,
        "value_note": f"{value_source} — 실제 값은 사용자가 확인 후 입력",
        "final_save_required": True,
        "ai_may_prepare_only": True,
        "user_must_click_final_save": True,
        "gabia_workflow": "사용자 직접 가비아 DNS 관리 화면에서 최종 저장 클릭 필요",
        "safe_to_prepare": True,
        "actual_dns_write": False,
    }


def make_nginx_routing_plan(
    fqdn: str,
    frontend_target: str,
    api_strategy_key: str,
) -> dict[str, Any]:
    api_strat = API_STRATEGIES.get(api_strategy_key, API_STRATEGIES["existing-orchestrator-api"])
    return {
        "fqdn": fqdn,
        "frontend_proxy_target": frontend_target,
        "http_block": {
            "listen": 80,
            "server_name": fqdn,
            "acme_challenge_root": "/var/www/certbot",
            "redirect": f"https://{fqdn}$request_uri",
            "change_allowed_now": False,
            "note": "nginx 파일 수정은 사용자 승인 후 별도 공정으로 진행",
        },
        "https_block": {
            "listen": 443,
            "server_name": fqdn,
            "ssl_certificate": f"/etc/nginx/ssl/{fqdn.split('.')[0]}/fullchain.pem",
            "ssl_certificate_key": f"/etc/nginx/ssl/{fqdn.split('.')[0]}/privkey.pem",
            "proxy_pass": f"http://{frontend_target}",
            "change_allowed_now": False,
            "note": "nginx 파일 수정은 사용자 승인 후 별도 공정으로 진행",
        },
        "api_base_strategy": api_strat,
        "legacy_preservation": {
            "orchestrator_api": f"/orchestrator/api/ → {LEGACY_ORCHESTRATOR_API}",
            "orchestrator_legacy": f"/orchestrator/ → {LEGACY_5050_TARGET}",
            "do_not_stop_5050": True,
            "orchestrator_api_8400_required": True,
            "note": "기존 /orchestrator 구조 무변경 — 5050 중단 금지",
        },
        "change_allowed_now": False,
        "actual_nginx_change": False,
    }


def make_ssl_plan(fqdn: str, host: str) -> dict[str, Any]:
    return {
        "fqdn": fqdn,
        "certificate_required": True,
        "certbot_method": "webroot",
        "webroot_path": "/home/ubuntu/app/nginx/webroot",
        "certbot_execution_allowed": False,
        "dns_must_resolve_first": True,
        "nginx_http_block_must_exist_first": True,
        "certbot_command_candidate": (
            f"sudo certbot certonly --webroot "
            f"-w /home/ubuntu/app/nginx/webroot "
            f"-d {fqdn} "
            f"--non-interactive --agree-tos"
            f"  # [사용자 승인 후 별도 공정에서 실행]"
        ),
        "cert_path_after_issue": f"/home/ubuntu/app/nginx/ssl/{host}/fullchain.pem",
        "change_allowed_now": False,
        "actual_certbot": False,
        "steps": [
            "1. DNS A 레코드 저장 (사용자 가비아 직접 클릭)",
            "2. DNS 전파 확인 (host/dig 명령)",
            "3. nginx HTTP 80 ACME challenge 블록 추가 (사용자 승인 필요)",
            "4. nginx -t 검증",
            "5. nginx reload (사용자 승인 필요)",
            f"6. certbot --webroot -d {fqdn} 실행 (사용자 승인 필요)",
            "7. nginx SSL 경로 업데이트 (사용자 승인 필요)",
            "8. nginx -t 검증 후 reload",
        ],
    }


def make_smoke_checklist(fqdn: str, root_domain: str) -> list[dict[str, str]]:
    return [
        {
            "tier": "P0",
            "check": "DNS resolve",
            "cmd": f"host {fqdn} 8.8.8.8",
            "expect": "IP 주소 반환",
        },
        {
            "tier": "P0",
            "check": "HTTP 301 redirect",
            "cmd": f"curl -sI http://{fqdn}/",
            "expect": "301 Moved Permanently",
        },
        {
            "tier": "P0",
            "check": "HTTPS 200",
            "cmd": f"curl -sI https://{fqdn}/",
            "expect": "200 OK",
        },
        {
            "tier": "P0",
            "check": "TLS verify",
            "cmd": f"echo | openssl s_client -connect {fqdn}:443 -servername {fqdn} 2>&1 | grep 'Verify return'",
            "expect": "Verify return code: 0 (ok)",
        },
        {
            "tier": "P0",
            "check": "TLS CN/SAN 확인",
            "cmd": f"echo | openssl s_client -connect {fqdn}:443 -servername {fqdn} 2>&1 | grep subject",
            "expect": f"CN = {fqdn}",
        },
        {
            "tier": "P1",
            "check": "기존 orchestrator API 유지",
            "cmd": f"curl -sI https://{root_domain}/orchestrator/api/v1/health",
            "expect": "200 또는 403(auth) — 5xx 아님",
        },
        {
            "tier": "P1",
            "check": "5050 Flask legacy 유지",
            "cmd": "ss -tlnp | grep 5050",
            "expect": "LISTEN (pid 존재)",
        },
        {
            "tier": "P1",
            "check": "frontend 응답 no 5xx",
            "cmd": f"curl -sI https://{fqdn}/ 2>&1 | grep -v '5[0-9][0-9]'",
            "expect": "5xx 없음",
        },
        {
            "tier": "P2",
            "check": "nginx error log 확인",
            "cmd": "docker logs nginx --tail 20 2>&1 | grep -iE 'emerg|crit|error'",
            "expect": "fatal error 없음",
        },
        {
            "tier": "P2",
            "check": "인증서 만료일 확인",
            "cmd": f"openssl x509 -in /home/ubuntu/app/nginx/ssl/{fqdn.split('.')[0]}/fullchain.pem -noout -dates",
            "expect": "notAfter 90일 이상 남음",
        },
    ]


def make_rollback_plan(fqdn: str, host: str) -> dict[str, Any]:
    ts_placeholder = f"YYYYMMDD_HHMMSS_pre_{host}"
    return {
        "requires_user_approval": True,
        "rollback_forbidden_now": True,
        "rollback_conditions": [
            f"{fqdn} HTTPS 5xx 지속",
            "nginx reload 후 기존 /orchestrator 장애",
            "5050 legacy 장애",
            "TLS 설정으로 기존 SSL 블록 영향 발생",
            "admin-web 접근 장애",
        ],
        "dns_rollback": {
            "action": "가비아 DNS 관리 화면에서 해당 레코드 직접 삭제",
            "who": "사용자 직접 수행",
            "approval": "사용자 명시 승인 필요",
        },
        "nginx_rollback": {
            "default_conf_backup": f"default.conf.bak.{ts_placeholder}",
            "acme_conf_backup": f"acme.conf.bak.{ts_placeholder}",
            "command": (
                f"cp /home/ubuntu/app/nginx/conf.d/default.conf.bak.{ts_placeholder} "
                f"/home/ubuntu/app/nginx/conf.d/default.conf && "
                f"docker exec nginx nginx -s reload"
            ),
            "note": "백업 파일명은 실제 공정 시작 시 확정됨",
        },
        "ssl_rollback": {
            "command": f"sudo certbot delete --cert-name {fqdn}  # [사용자 승인 필요]",
            "cert_dir": f"/home/ubuntu/app/nginx/ssl/{host}/",
            "note": "인증서 삭제 시 기존 SSL 블록에 영향 없도록 nginx config 먼저 원복",
        },
        "rollback_steps": [
            "1. nginx config 백업 파일로 원복",
            "2. docker exec nginx nginx -t 검증",
            "3. docker exec nginx nginx -s reload (사용자 승인)",
            "4. certbot delete (선택, 사용자 승인)",
            "5. 가비아 DNS 레코드 삭제 (선택, 사용자 직접)",
        ],
        "5050_must_survive_rollback": True,
    }


def make_next_steps(fqdn: str) -> list[str]:
    return [
        f"1. [사용자] 가비아 DNS A 레코드 추가: {fqdn} → SERVER_PUBLIC_IP",
        "2. [AI] DNS 전파 확인 (host/dig — read-only)",
        "3. [사용자 승인] nginx HTTP 80 ACME challenge 블록 추가 공정",
        "4. [사용자 승인] nginx reload",
        f"5. [사용자 승인] certbot --webroot -d {fqdn} 실행",
        "6. [사용자 승인] nginx SSL 경로 업데이트 + reload",
        "7. [AI] smoke test 실행 (read-only)",
        "8. [AI] rollback 도면 확보 확인",
        "9. [GPT] 최종 검측 대기",
    ]


# ── 메인 계획 생성 ────────────────────────────────────────────────────────────


def create_provisioning_plan(  # noqa: PLR0913 - 공개 시그니처 유지(호출부 다수/CLI 인자 보존)
    fqdn: str,
    project_id: str,
    display_name: str,
    frontend_target: str,
    api_strategy: str,
    record_type: str,
    value_source: str,
) -> dict[str, Any]:
    host, root_domain = _split_fqdn(fqdn)

    dns_draft = make_dns_draft(fqdn, host, root_domain, record_type, value_source)
    nginx_plan = make_nginx_routing_plan(fqdn, frontend_target, api_strategy)
    ssl_plan = make_ssl_plan(fqdn, host)
    smoke = make_smoke_checklist(fqdn, root_domain)
    rollback = make_rollback_plan(fqdn, host)
    next_steps = make_next_steps(fqdn)

    api_strat = API_STRATEGIES.get(api_strategy, API_STRATEGIES["existing-orchestrator-api"])

    provisioning_request = {
        "project_id": project_id,
        "display_name": display_name,
        "fqdn": fqdn,
        "root_domain": root_domain,
        "host": host,
        "purpose": display_name,
        "frontend_target": frontend_target,
        "api_strategy": api_strategy,
        "api_base_url_short_term": api_strat["base_url"],
        "legacy_strategy": "orchestrator 구조 무변경 유지",
        "requires_final_approval": True,
    }

    boundary_violations = [k for k, v in SAFE_BOUNDARY.items() if v is True]
    safety_boundary = {
        **SAFE_BOUNDARY,
        "violations": boundary_violations,
        "boundary_ok": len(boundary_violations) == 0,
    }

    all_ok = (
        dns_draft["final_save_required"] is True
        and dns_draft["ai_may_prepare_only"] is True
        and nginx_plan["legacy_preservation"]["do_not_stop_5050"] is True
        and ssl_plan["certbot_execution_allowed"] is False
        and safety_boundary["boundary_ok"]
        and len(smoke) >= 8
        and len(rollback["rollback_steps"]) >= 4
    )

    return {
        "audit_id": "ASSISTANT_WEB_PROJECT_PROVISIONING_SCRIPT_FACTORY_01",
        "verdict": "PLAN_READY" if all_ok else "PLAN_FAIL",
        "all_ok": all_ok,
        "provisioning_request": provisioning_request,
        "dns_draft": dns_draft,
        "nginx_plan": nginx_plan,
        "ssl_plan": ssl_plan,
        "smoke_checklist": smoke,
        "rollback_plan": rollback,
        "safety_boundary": safety_boundary,
        "next_steps": next_steps,
    }


# ── 출력 ─────────────────────────────────────────────────────────────────────


def _print_plan(plan: dict) -> None:
    print("=" * 70)
    print("WEB PROJECT PROVISIONING PLAN")
    print(f"VERDICT: {plan['verdict']}")
    print("=" * 70)

    req = plan["provisioning_request"]
    print("\n[프로젝트]")
    print(f"  ID         : {req['project_id']}")
    print(f"  이름       : {req['display_name']}")
    print(f"  FQDN       : {req['fqdn']}")
    print(f"  host       : {req['host']}.{req['root_domain']}")
    print(f"  frontend   : {req['frontend_target']}")
    print(f"  API 전략   : {req['api_strategy']} → {req['api_base_url_short_term']}")

    dns = plan["dns_draft"]
    print("\n[DNS 초안]")
    print(f"  {dns['record_type']} {dns['host']}.{dns['root_domain']} → {dns['value_source']}")
    print(f"  final_save_required  : {dns['final_save_required']}")
    print(f"  ai_may_prepare_only  : {dns['ai_may_prepare_only']}")
    print(f"  actual_dns_write     : {dns['actual_dns_write']}")

    ng = plan["nginx_plan"]
    lp = ng["legacy_preservation"]
    print("\n[nginx 계획]")
    print(f"  frontend proxy : {ng['frontend_proxy_target']}")
    print(f"  5050 중단 금지 : {lp['do_not_stop_5050']}")
    print(f"  /orchestrator/api/ : {lp['orchestrator_api']}")
    print(f"  /orchestrator/     : {lp['orchestrator_legacy']}")
    print(f"  change_allowed_now : {ng['change_allowed_now']}")

    ssl = plan["ssl_plan"]
    print("\n[SSL 계획]")
    print(f"  certbot_execution_allowed : {ssl['certbot_execution_allowed']}")
    print(f"  dns_must_resolve_first    : {ssl['dns_must_resolve_first']}")
    print(f"  steps: {len(ssl['steps'])}개")

    print(f"\n[Smoke 체크리스트] ({len(plan['smoke_checklist'])}개)")
    for item in plan["smoke_checklist"]:
        print(f"  [{item['tier']}] {item['check']}  # {item['expect']}")

    rb = plan["rollback_plan"]
    print("\n[Rollback 계획]")
    print(f"  requires_user_approval       : {rb['requires_user_approval']}")
    print(f"  5050_must_survive_rollback   : {rb['5050_must_survive_rollback']}")
    print(f"  rollback_steps               : {len(rb['rollback_steps'])}개")

    print("\n[다음 단계]")
    for step in plan["next_steps"]:
        print(f"  {step}")

    sb = plan["safety_boundary"]
    print("\n[안전 경계]")
    if sb["violations"]:
        print(f"  ❌ 위반: {sb['violations']}")
    else:
        print("  ✅ 위반 없음")

    print("=" * 70)
    print(f"VERDICT: {plan['verdict']}")
    print("GPT 검측 대기 중 — 단독 PASS 확정 불가")
    print("=" * 70)


# ── CLI ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="신규 웹/서브도메인 착공 표준 계획 생성기 — plan-only, 실제 변경 없음")
    parser.add_argument("--fqdn", default="autowork.haehan-ai.kr", help="대상 FQDN (예: newservice.haehan-ai.kr)")
    parser.add_argument("--project-id", default="autowork", help="프로젝트 ID (영소문자, 하이픈 허용)")
    parser.add_argument("--display-name", default="AI 자동업무 본관", help="프로젝트 표시명")
    parser.add_argument(
        "--frontend-target", default="admin-web:3000", help="nginx proxy_pass 대상 (예: admin-web:3000)"
    )
    parser.add_argument(
        "--api-strategy",
        default="existing-orchestrator-api",
        choices=list(API_STRATEGIES.keys()),
        help="API base URL 전략",
    )
    parser.add_argument("--record-type", default="A", choices=["A", "CNAME", "AAAA"], help="DNS 레코드 타입")
    parser.add_argument(
        "--value-source", default="SERVER_PUBLIC_IP", help="DNS 레코드 값 출처 표시 (실제 IP는 사용자 확인 필요)"
    )
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    parser.add_argument("--check-only", action="store_true", help="생성 없이 입력 파라미터 유효성만 확인")
    args = parser.parse_args()

    if args.check_only:
        host, root_domain = _split_fqdn(args.fqdn)
        print("CHECK-ONLY:")
        print(f"  fqdn        : {args.fqdn}")
        print(f"  host        : {host}")
        print(f"  root_domain : {root_domain}")
        print(f"  project_id  : {args.project_id}")
        print(f"  frontend    : {args.frontend_target}")
        print(f"  api_strategy: {args.api_strategy}")
        print(f"  record_type : {args.record_type}")
        print(f"  value_source: {args.value_source}")
        print("OK — check-only 완료, 실제 변경 없음")
        sys.exit(0)

    plan = create_provisioning_plan(
        fqdn=args.fqdn,
        project_id=args.project_id,
        display_name=args.display_name,
        frontend_target=args.frontend_target,
        api_strategy=args.api_strategy,
        record_type=args.record_type,
        value_source=args.value_source,
    )

    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        _print_plan(plan)

    sys.exit(0 if plan["all_ok"] else 1)


if __name__ == "__main__":
    main()
