"""autowork.haehan-ai.kr 서브도메인 기초 도면.

ASSISTANT_SUBDOMAIN_DNS_ROUTING_FOUNDATION_01

이 모듈은 DNS 초안, nginx 라우팅 계획, SSL 계획, smoke 체크리스트,
rollback 계획을 정의한다.

실제 시공 금지:
    - 가비아 DNS 저장 금지
    - nginx 파일 수정 금지
    - certbot 실행 금지
    - 서버 재시작 금지
    - DB/schema 변경 금지
    - UI 수정 금지
"""

from __future__ import annotations

from typing import Any

from ai_orchestrator.connectors.gabia.dns_models import (
    GabiaDnsApprovalSummary,
    GabiaDnsChangePreview,
    GabiaDnsRecordDraft,
    GabiaDnsRollbackPlan,
)

# ---------------------------------------------------------------------------
# 대표 FQDN 상수
# ---------------------------------------------------------------------------

AUTOWORK_FQDN = "autowork.haehan-ai.kr"
AUTOWORK_SUBDOMAIN = "autowork"
BASE_DOMAIN = "haehan-ai.kr"
VALUE_SOURCE_PENDING = "SERVER_PUBLIC_IP_PENDING_USER_CONFIRMATION"

# ---------------------------------------------------------------------------
# STEP 3. DNS 레코드 초안
# ---------------------------------------------------------------------------

AUTOWORK_DNS_DRAFT = GabiaDnsRecordDraft(
    record_id="draft_autowork_haehan_ai_kr_v1",
    domain=BASE_DOMAIN,
    host=AUTOWORK_SUBDOMAIN,
    record_type="A",
    value=VALUE_SOURCE_PENDING,
    ttl=600,
    purpose="AI 자동업무 본관 웹 진입 주소 (admin-web + FastAPI 백엔드)",
    created_by="ai_assistant",
    safe_to_prepare=True,
    requires_final_approval=True,
)

# 대안 CNAME 초안 (IP 변경 가능 환경)
AUTOWORK_DNS_DRAFT_CNAME = GabiaDnsRecordDraft(
    record_id="draft_autowork_haehan_ai_kr_cname_v1",
    domain=BASE_DOMAIN,
    host=AUTOWORK_SUBDOMAIN,
    record_type="CNAME",
    value="haehan-ai.kr",
    ttl=600,
    purpose="기존 haehan-ai.kr 위임 (IP 변경 가능 환경)",
    created_by="ai_assistant",
    safe_to_prepare=True,
    requires_final_approval=True,
)

# DNS 변경 승인 요약
AUTOWORK_DNS_APPROVAL_SUMMARY = GabiaDnsApprovalSummary(
    action="add_autowork_subdomain",
    domain=BASE_DOMAIN,
    records_to_add=(AUTOWORK_DNS_DRAFT,),
    records_to_change=(),
    records_to_remove=(),
    user_must_click_final_save=True,
    ai_may_prepare_only=True,
)

# ---------------------------------------------------------------------------
# STEP 4. nginx 라우팅 계획
# ---------------------------------------------------------------------------

# 현재 운영 중인 기존 구조 (변경 금지)
EXISTING_NGINX_ROUTES: tuple[dict, ...] = (
    {
        "location": "/orchestrator/api/v1/local-agents/ws",
        "backend": "haehan-ai-orchestrator-api:8400",
        "note": "WebSocket 전용",
    },
    {"location": "/orchestrator/api/", "backend": "haehan-ai-orchestrator-api:8400", "note": "FastAPI 신규 API 전체"},
    {
        "location": "/orchestrator/admin-web/",
        "backend": "haehan-ai-orchestrator-admin-web:3000",
        "note": "Next.js admin-web",
    },
    {"location": "/orchestrator/", "backend": "localhost:5050", "note": "Flask legacy. 5050 중단 금지."},
)

# 신규 nginx server block 후보 (실제 적용 금지 — 계획만)
NGINX_PLAN_CANDIDATE_1: dict[str, Any] = {
    "plan_id": "CANDIDATE_1_FULL_SEPARATION",
    "server_name": "autowork.haehan-ai.kr",
    "description": "autowork 전체를 admin-web + 전용 API로 연결",
    "routes": [
        {"location": "/api/", "backend": "haehan-ai-orchestrator-api:8400", "note": "FastAPI 전용 API"},
        {"location": "/", "backend": "haehan-ai-orchestrator-admin-web:3000", "note": "admin-web 루트"},
    ],
    "pros": ["사용자 주소 단순", "서브도메인 독립"],
    "cons": ["nginx server block 추가 필요", "SSL 신규 발급 필요"],
    "5050_impact": "없음 — /orchestrator/ 유지",
    "recommended_phase": "장기 목표",
    "actual_change_required": True,
    "change_allowed_now": False,
}

NGINX_PLAN_CANDIDATE_2: dict[str, Any] = {
    "plan_id": "CANDIDATE_2_REUSE_ORCHESTRATOR",
    "server_name": "autowork.haehan-ai.kr",
    "description": "autowork 웹만 연결, API는 기존 /orchestrator/api/ 유지",
    "routes": [
        {"location": "/", "backend": "haehan-ai-orchestrator-admin-web:3000", "note": "admin-web 루트"},
    ],
    "api_base_url": "https://haehan-ai.kr/orchestrator/api/v1",
    "pros": ["변경 최소", "기존 API 구조 유지"],
    "cons": ["프론트 API base URL 혼재 (향후 정리 필요)"],
    "5050_impact": "없음 — /orchestrator/ 유지",
    "recommended_phase": "1차 시공 추천",
    "actual_change_required": True,
    "change_allowed_now": False,
}

NGINX_PLAN_CANDIDATE_3: dict[str, Any] = {
    "plan_id": "CANDIDATE_3_WEB_ONLY_NO_API",
    "server_name": "autowork.haehan-ai.kr",
    "description": "autowork는 admin-web만, API는 haehan-ai.kr/orchestrator/api 유지",
    "routes": [
        {"location": "/", "backend": "haehan-ai-orchestrator-admin-web:3000", "note": "admin-web 루트"},
    ],
    "api_base_url": "https://haehan-ai.kr/orchestrator/api/v1",
    "pros": ["가장 안전", "기존 구조 변경 없음"],
    "cons": ["CORS/API base URL 정리 필요 (UI 공정에서)"],
    "5050_impact": "없음 — /orchestrator/ 유지",
    "recommended_phase": "즉시 도입 가능 (1순위 추천)",
    "actual_change_required": True,
    "change_allowed_now": False,
}

NGINX_RECOMMENDED_PLAN = NGINX_PLAN_CANDIDATE_3

# ---------------------------------------------------------------------------
# STEP 5. SSL 계획
# ---------------------------------------------------------------------------

SSL_PLAN: dict[str, Any] = {
    "plan_id": "SSL_AUTOWORK_HAEHAN_AI_KR",
    "fqdn": AUTOWORK_FQDN,
    "method": "certbot_standalone_or_webroot",
    "wildcard_check": "기존 *.haehan-ai.kr 와일드카드 인증서 존재 여부 확인 필요",
    "steps": [
        "1. DNS 전파 확인 (dig autowork.haehan-ai.kr 또는 nslookup)",
        "2. HTTP 80 reachability 확인",
        "3. certbot certonly --nginx -d autowork.haehan-ai.kr (실제 실행은 대표님 승인 후)",
        "4. nginx config에 ssl_certificate 경로 추가",
        "5. nginx -t 통과 확인",
        "6. nginx reload (smoke 확인 후)",
        "7. HTTPS smoke 체크",
    ],
    "preconditions": [
        "DNS 레코드 전파 완료 (최대 48시간)",
        "서버 80 포트 reachable",
        "nginx config 백업 완료",
    ],
    "actual_certbot_execution": False,
    "change_allowed_now": False,
    "failure_action": "기존 인증서 영향 없이 config 롤백",
}

# ---------------------------------------------------------------------------
# STEP 6. smoke 체크리스트
# ---------------------------------------------------------------------------

SMOKE_CHECKLIST: tuple[dict[str, Any], ...] = (
    {
        "id": "SM-01",
        "tier": "P0",
        "check": "DNS resolve autowork.haehan-ai.kr",
        "cmd": "dig autowork.haehan-ai.kr",
        "expected": "서버 공인 IP 응답",
    },
    {
        "id": "SM-02",
        "tier": "P0",
        "check": "HTTP 80 reachability",
        "cmd": "curl -I http://autowork.haehan-ai.kr/",
        "expected": "200 또는 301",
    },
    {
        "id": "SM-03",
        "tier": "P0",
        "check": "HTTPS 443 reachability",
        "cmd": "curl -I https://autowork.haehan-ai.kr/",
        "expected": "200",
    },
    {
        "id": "SM-04",
        "tier": "P0",
        "check": "TLS certificate CN/SAN 확인",
        "cmd": "curl -vI https://autowork.haehan-ai.kr/ 2>&1 | grep subject",
        "expected": "autowork.haehan-ai.kr 포함",
    },
    {
        "id": "SM-05",
        "tier": "P1",
        "check": "GET https://autowork.haehan-ai.kr/",
        "cmd": "curl -sk https://autowork.haehan-ai.kr/",
        "expected": "200",
    },
    {
        "id": "SM-06",
        "tier": "P1",
        "check": "GET /api/v1/health (결정된 API path)",
        "cmd": "curl -sk https://autowork.haehan-ai.kr/api/v1/health",
        "expected": "200",
    },
    {
        "id": "SM-07",
        "tier": "P1",
        "check": "GET /api/v1/ops/summary",
        "cmd": "curl -sk -H 'Host: haehan-ai.kr' https://haehan-ai.kr/orchestrator/api/v1/ops/summary",
        "expected": "200",
    },
    {
        "id": "SM-08",
        "tier": "P0",
        "check": "기존 /orchestrator/api/ 유지",
        "cmd": "curl -sk -H 'Host: haehan-ai.kr' https://haehan-ai.kr/orchestrator/api/v1/health",
        "expected": "200",
    },
    {
        "id": "SM-09",
        "tier": "P0",
        "check": "기존 /orchestrator/ 5050 legacy 유지",
        "cmd": "curl -sk -H 'Host: haehan-ai.kr' https://haehan-ai.kr/orchestrator/",
        "expected": "200 또는 302",
    },
    {
        "id": "SM-10",
        "tier": "P1",
        "check": "5050 Auth 401 유지 (보호 API)",
        "cmd": "curl -sk -H 'Host: haehan-ai.kr' https://haehan-ai.kr/orchestrator/api/v1/tasks",
        "expected": "401",
    },
)

# ---------------------------------------------------------------------------
# STEP 7. rollback 계획
# ---------------------------------------------------------------------------

AUTOWORK_ROLLBACK_PLAN = GabiaDnsRollbackPlan(
    rollback_available=True,
    previous_records_ref="gabia_dns_snapshot_before_autowork_addition",
    rollback_steps=(
        "1. 가비아 관리자 페이지 접속 (사용자 직접)",
        "2. DNS 관리 → autowork A/CNAME 레코드 선택",
        "3. 레코드 삭제 (사용자 승인 후)",
        "4. DNS 전파 확인 (최대 48시간 대기)",
        "5. nginx server block에서 autowork 설정 제거 (nginx -t 후 reload)",
        "6. autowork SSL 인증서 nginx config에서 제외 (인증서 파일 삭제 금지)",
    ),
    requires_user_approval=True,
    dns_propagation_notice="DNS 변경은 전파에 최대 48시간 소요. 롤백 후에도 즉시 반영되지 않을 수 있음.",
)

NGINX_ROLLBACK_PLAN: dict[str, Any] = {
    "precondition": "변경 전 nginx config 백업 필수",
    "steps": [
        "1. nginx -t로 config 검증",
        "2. 실패 시 backup config 복원",
        "3. nginx reload",
        "4. smoke 재확인",
        "5. /orchestrator/ 5050 정상 확인",
    ],
    "5050_protection": "rollback 후 5050 중단 여부 즉시 확인",
    "backup_location": "/etc/nginx/sites-available/haehan-ai.kr.bak (예시)",
}

SSL_ROLLBACK_PLAN: dict[str, Any] = {
    "steps": [
        "1. nginx config에서 autowork ssl_certificate 라인 제거",
        "2. nginx -t",
        "3. nginx reload",
        "4. 인증서 파일은 삭제하지 않고 보존",
    ],
    "existing_cert_impact": "기존 haehan-ai.kr 인증서에 영향 없음",
}

# ---------------------------------------------------------------------------
# STEP 8. Gabia approval flow 연결
# ---------------------------------------------------------------------------

AUTOWORK_DNS_CHANGE_PREVIEW = GabiaDnsChangePreview(
    domain=BASE_DOMAIN,
    before_records=(),
    after_records=(AUTOWORK_DNS_DRAFT,),
    added_records=(AUTOWORK_DNS_DRAFT,),
    changed_records=(),
    removed_records=(),
    risk_level="high",
    approval_required=True,
    final_button_blocked=True,
)


def get_full_foundation_plan() -> dict[str, Any]:
    """전체 도면 계획을 safe dict로 반환한다."""
    return {
        "plan_id": "ASSISTANT_SUBDOMAIN_DNS_ROUTING_FOUNDATION_01",
        "fqdn": AUTOWORK_FQDN,
        "read_only": True,
        "actual_dns_write": False,
        "actual_nginx_change": False,
        "actual_certbot": False,
        "actual_gabia_access": False,
        "dns_draft": AUTOWORK_DNS_DRAFT.to_safe_dict(),
        "dns_draft_cname_alt": AUTOWORK_DNS_DRAFT_CNAME.to_safe_dict(),
        "dns_approval_summary": AUTOWORK_DNS_APPROVAL_SUMMARY.to_safe_dict(),
        "dns_change_preview": AUTOWORK_DNS_CHANGE_PREVIEW.to_safe_dict(),
        "dns_rollback": AUTOWORK_ROLLBACK_PLAN.to_safe_dict(),
        "nginx_existing_routes": list(EXISTING_NGINX_ROUTES),
        "nginx_recommended_plan": NGINX_RECOMMENDED_PLAN,
        "nginx_rollback": NGINX_ROLLBACK_PLAN,
        "ssl_plan": SSL_PLAN,
        "ssl_rollback": SSL_ROLLBACK_PLAN,
        "smoke_checklist": list(SMOKE_CHECKLIST),
        "final_approval_gate": {
            "safe_to_prepare": True,
            "safe_to_click_final_button": False,
            "requires_final_approval": True,
            "user_must_approve": True,
        },
    }


__all__ = [
    "AUTOWORK_DNS_APPROVAL_SUMMARY",
    "AUTOWORK_DNS_CHANGE_PREVIEW",
    "AUTOWORK_DNS_DRAFT",
    "AUTOWORK_DNS_DRAFT_CNAME",
    "AUTOWORK_FQDN",
    "AUTOWORK_ROLLBACK_PLAN",
    "AUTOWORK_SUBDOMAIN",
    "BASE_DOMAIN",
    "EXISTING_NGINX_ROUTES",
    "NGINX_PLAN_CANDIDATE_1",
    "NGINX_PLAN_CANDIDATE_2",
    "NGINX_PLAN_CANDIDATE_3",
    "NGINX_RECOMMENDED_PLAN",
    "NGINX_ROLLBACK_PLAN",
    "SMOKE_CHECKLIST",
    "SSL_PLAN",
    "SSL_ROLLBACK_PLAN",
    "VALUE_SOURCE_PENDING",
    "get_full_foundation_plan",
]
