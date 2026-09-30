"""Safety Policy Registry — Policy Layer 방화구획 단일 기준선.

이 모듈이 프로젝트 내 SafetyPolicy registry의 단일 source of truth다.
기존 execution_location_guard, action_risk_policy, server_egress_policy는
원본을 유지하며, 이 registry는 통합 참조 기준선으로만 사용된다.

각 정책의 decision 값:
- SafetyDecision.block       → 실행 절대 불가
- SafetyDecision.hold        → 외부 앱 계약/설정 전 대기
- SafetyDecision.require_approval → 승인 없이 실행 불가
- SafetyDecision.require_user_direct → 사용자 직접 수행 필요
- SafetyDecision.require_local_agent → 로컬 에이전트 필요
- SafetyDecision.allow       → 서버 내부 실행 허용

금지:
- 기존 guard/policy 대체 금지
- API 응답 변경 금지
- DB write 금지
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# 정책 분류 상수
# ---------------------------------------------------------------------------

# execution_location 값 (execution_location_guard 호환)
LOC_SERVER = "SERVER_INTERNAL_ONLY"
LOC_AGENT = "LOCAL_AGENT_REQUIRED"
LOC_USER = "USER_DIRECT_REQUIRED"
LOC_BLOCKED = "BLOCKED"

# external work classification (external_work_registry 호환)
CLS_SERVER_READONLY = "SERVER_READONLY_ALLOWED"
CLS_OAUTH_REQUIRED = "OFFICIAL_API_OR_OAUTH_REQUIRED"
CLS_LOCAL_AGENT = "LOCAL_AGENT_REQUIRED"
CLS_USER_DIRECT = "USER_DIRECT_REQUIRED"
CLS_WEB_TASK = "WEB_TASK_REGISTRY"
CLS_QUARANTINE = "QUARANTINE_OR_HOLD"
CLS_EXTERNAL_APP_HOLD = "EXTERNAL_APP_HOLD"
CLS_FUTURE = "FUTURE_INTEGRATION"
CLS_IN_SCOPE = "IN_SCOPE"

# SafetyDecision 값 (domain/models.SafetyDecision 호환)
DECISION_ALLOW = "allow"
DECISION_BLOCK = "block"
DECISION_HOLD = "hold"
DECISION_REQUIRE_APPROVAL = "require_approval"
DECISION_REQUIRE_AGENT = "require_local_agent"
DECISION_REQUIRE_USER = "require_user_direct"

# severity
SEV_CRITICAL = "critical"
SEV_HIGH = "high"
SEV_MEDIUM = "medium"
SEV_LOW = "low"

# ---------------------------------------------------------------------------
# 신뢰 세션 / 최종 승인 게이트 — TRUSTED_SESSION_AND_USER_APPROVAL v1.0
# ---------------------------------------------------------------------------

# AuthMode — 인증 방식 상수
AUTH_MODE_USER_PRESENT = "USER_PRESENT_AUTH"  # 최초 1회 사용자 직접 인증
AUTH_MODE_TRUSTED_REUSE = "TRUSTED_SESSION_REUSE"  # 승인된 세션 재사용
AUTH_MODE_OAUTH_API = "OAUTH_API"  # OAuth/공식 API

# SessionTrustLevel — 세션 신뢰 등급
SESSION_TRUST_NONE = "NONE"  # 세션 없음/만료
SESSION_TRUST_PRESENT = "USER_PRESENT"  # 사용자 직접 로그인한 세션
SESSION_TRUST_REUSABLE = "REUSABLE"  # AI 재사용 허용 세션

# FinalActionType — 사용자 승인 없이 자동 클릭 절대 금지 행위
FINAL_ACTION_SAVE = "SAVE"
FINAL_ACTION_SUBMIT = "SUBMIT"
FINAL_ACTION_PAY = "PAYMENT"
FINAL_ACTION_SIGN = "ELECTRONIC_SIGN"
FINAL_ACTION_DOMAIN_CHANGE = "DOMAIN_DNS_CHANGE"
FINAL_ACTION_SEND = "SEND"
FINAL_ACTION_BID = "BID_SUBMIT"
FINAL_ACTION_TRANSFER = "BANK_TRANSFER"

FINAL_ACTION_TYPES: frozenset[str] = frozenset(
    {
        FINAL_ACTION_SAVE,
        FINAL_ACTION_SUBMIT,
        FINAL_ACTION_PAY,
        FINAL_ACTION_SIGN,
        FINAL_ACTION_DOMAIN_CHANGE,
        FINAL_ACTION_SEND,
        FINAL_ACTION_BID,
        FINAL_ACTION_TRANSFER,
    }
)

# ApprovalGate — 실행 단계 게이트
GATE_PREPARE_ALLOWED = "PREPARE_ALLOWED"  # AI 준비/폼 입력 허용
GATE_FINAL_BLOCKED = "FINAL_BLOCKED"  # 최종 버튼 자동 클릭 금지
GATE_USER_APPROVAL_NEEDED = "USER_APPROVAL_NEEDED"  # 사용자 승인 게이트
GATE_REAUTH_REQUIRED = "REAUTH_REQUIRED"  # 재인증 필요

# 신뢰 세션/최종행위 분류 scope 상수
CLS_TRUSTED_SESSION = "TRUSTED_SESSION_SCOPE"
CLS_FINAL_ACTION = "FINAL_ACTION_SCOPE"
CLS_CERT_AUTH = "CERT_AUTH_SCOPE"
CLS_DOMAIN_CHANGE = "DOMAIN_DNS_CHANGE_SCOPE"
CLS_SECRET_STORAGE = "SECRET_STORAGE_SCOPE"  # noqa: S105 - 분류 이름 상수(비밀값 아님)


# ---------------------------------------------------------------------------
# SafetyPolicyRecord — registry 레코드 (frozen dict 대용)
# ---------------------------------------------------------------------------


class SafetyPolicyRecord:
    """Registry에 저장되는 정책 레코드."""

    __slots__ = (
        "applies_to",
        "blocked_scopes",
        "category",
        "decision",
        "name",
        "policy_id",
        "reason",
        "required_execution_location",
        "safe_to_execute_on_server",
        "severity",
        "test_required",
    )

    def __init__(
        self,
        policy_id: str,
        name: str,
        category: str,
        severity: str,
        applies_to: tuple[str, ...],
        decision: str,
        reason: str,
        required_execution_location: str | None = None,
        blocked_scopes: tuple[str, ...] = (),
        test_required: bool = True,
        safe_to_execute_on_server: bool = False,
    ) -> None:
        object.__setattr__(self, "policy_id", policy_id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "severity", severity)
        object.__setattr__(self, "applies_to", applies_to)
        object.__setattr__(self, "decision", decision)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "required_execution_location", required_execution_location)
        object.__setattr__(self, "blocked_scopes", blocked_scopes)
        object.__setattr__(self, "test_required", test_required)
        object.__setattr__(self, "safe_to_execute_on_server", safe_to_execute_on_server)

    def __setattr__(self, *_: Any) -> None:
        raise AttributeError("SafetyPolicyRecord는 read-only입니다.")

    def blocks_server_execution(self) -> bool:
        return not self.safe_to_execute_on_server

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "category": self.category,
            "severity": self.severity,
            "applies_to": list(self.applies_to),
            "decision": self.decision,
            "reason": self.reason,
            "required_execution_location": self.required_execution_location,
            "blocked_scopes": list(self.blocked_scopes),
            "test_required": self.test_required,
            "safe_to_execute_on_server": self.safe_to_execute_on_server,
        }


# ---------------------------------------------------------------------------
# Policy Registry — 8개 필수 정책
# ---------------------------------------------------------------------------

_POLICY_REGISTRY: dict[str, SafetyPolicyRecord] = {
    # 1. EXTERNAL_APP_HOLD_BLOCK
    "EXTERNAL_APP_HOLD_BLOCK": SafetyPolicyRecord(
        policy_id="EXTERNAL_APP_HOLD_BLOCK",
        name="외부 전문 앱 연동 대기 항목 실행 차단",
        category="external_app_hold",
        severity=SEV_CRITICAL,
        applies_to=(
            CLS_EXTERNAL_APP_HOLD,
            CLS_FUTURE,
            "CAD_EXTERNAL_APP_BRIDGE",
            "HWPX_EXTERNAL_APP_BRIDGE",
            "OFFICE_EXTERNAL_APP_BRIDGE",
            "TAX_EXTERNAL_APP_BRIDGE",
            "BID_EXTERNAL_APP_BRIDGE",
            "DOCUMENT_AUTOMATION_EXTERNAL_APP_BRIDGE",
        ),
        decision=DECISION_HOLD,
        reason=("CAD/HWPX/Excel/Tax/Bid/문서자동화 등 외부 전문 앱 연동은 계약·bridge 구현 전까지 실행 불가."),
        required_execution_location=LOC_BLOCKED,
        blocked_scopes=(CLS_EXTERNAL_APP_HOLD, CLS_FUTURE),
        test_required=True,
        safe_to_execute_on_server=False,
    ),
    # 2. OAUTH_API_REQUIRED_BLOCK
    "OAUTH_API_REQUIRED_BLOCK": SafetyPolicyRecord(
        policy_id="OAUTH_API_REQUIRED_BLOCK",
        name="OAuth/API 설정 전 실행 차단",
        category="oauth_api_required",
        severity=SEV_HIGH,
        applies_to=(CLS_OAUTH_REQUIRED,),
        decision=DECISION_BLOCK,
        reason=(
            "Gmail/Calendar/Drive 등 공식 API OAuth 설정이 완료되지 않으면 "
            "서버 자동 실행 불가. 브라우저 로그인 자동화도 금지."
        ),
        required_execution_location=LOC_BLOCKED,
        blocked_scopes=(CLS_OAUTH_REQUIRED,),
        test_required=True,
        safe_to_execute_on_server=False,
    ),
    # 3. USER_DIRECT_REQUIRED_BLOCK
    "USER_DIRECT_REQUIRED_BLOCK": SafetyPolicyRecord(
        policy_id="USER_DIRECT_REQUIRED_BLOCK",
        name="사용자 직접 수행 필요 항목 자동 실행 차단",
        category="user_direct_required",
        severity=SEV_HIGH,
        applies_to=(CLS_USER_DIRECT, LOC_USER),
        decision=DECISION_REQUIRE_USER,
        reason=(
            "전자서명/투찰/결제/송금/OTP 입력 등 사용자가 직접 수행해야 하는 작업은 "
            "서버 및 로컬 에이전트 자동 실행이 금지된다."
        ),
        required_execution_location=LOC_USER,
        blocked_scopes=(CLS_USER_DIRECT,),
        test_required=True,
        safe_to_execute_on_server=False,
    ),
    # 4. LOCAL_AGENT_REQUIRED_SERVER_BLOCK
    "LOCAL_AGENT_REQUIRED_SERVER_BLOCK": SafetyPolicyRecord(
        policy_id="LOCAL_AGENT_REQUIRED_SERVER_BLOCK",
        name="로컬 에이전트 필요 항목 서버 직접 실행 차단",
        category="local_agent_required",
        severity=SEV_HIGH,
        applies_to=(CLS_LOCAL_AGENT, LOC_AGENT),
        decision=DECISION_REQUIRE_AGENT,
        reason=(
            "블로그 작성/카페 게시/외부 브라우저 자동화 등 로컬 에이전트가 필요한 작업은 서버에서 직접 실행할 수 없다."
        ),
        required_execution_location=LOC_AGENT,
        blocked_scopes=(CLS_LOCAL_AGENT,),
        test_required=True,
        safe_to_execute_on_server=False,
    ),
    # 5. BLOCKED_ACTION_DENY
    "BLOCKED_ACTION_DENY": SafetyPolicyRecord(
        policy_id="BLOCKED_ACTION_DENY",
        name="BLOCKED 항목 실행 차단",
        category="blocked_action",
        severity=SEV_CRITICAL,
        applies_to=(LOC_BLOCKED, CLS_QUARANTINE),
        decision=DECISION_BLOCK,
        reason=("BLOCKED 또는 QUARANTINE_OR_HOLD 분류 항목은 어떤 실행 주체도 실행할 수 없다."),
        required_execution_location=LOC_BLOCKED,
        blocked_scopes=(LOC_BLOCKED, CLS_QUARANTINE),
        test_required=True,
        safe_to_execute_on_server=False,
    ),
    # 6. SECRET_REDACTION_REQUIRED
    "SECRET_REDACTION_REQUIRED": SafetyPolicyRecord(
        policy_id="SECRET_REDACTION_REQUIRED",
        name="비밀 필드 비노출 강제",
        category="secret_redaction",
        severity=SEV_CRITICAL,
        applies_to=("*",),
        decision=DECISION_BLOCK,
        reason=(
            "secret/token/password/session/cookie/authorization/credential/private_key 등 "
            "민감 필드는 어떤 응답/로그/테스트에서도 원문 출력이 금지된다."
        ),
        required_execution_location=None,
        blocked_scopes=(),
        test_required=True,
        safe_to_execute_on_server=True,  # 정책 자체는 서버에서 집행 가능
    ),
    # 7. SERVER_EXTERNAL_WEB_BLOCK
    "SERVER_EXTERNAL_WEB_BLOCK": SafetyPolicyRecord(
        policy_id="SERVER_EXTERNAL_WEB_BLOCK",
        name="서버 외부 웹 브라우저 실행 차단",
        category="server_egress",
        severity=SEV_CRITICAL,
        applies_to=(
            "open_url",
            "read_page",
            "fill_form",
            "navigate",
            "login",
            "screenshot",
            "extract_text",
            "extract_tables",
        ),
        decision=DECISION_BLOCK,
        reason=("서버에서 외부 사이트 브라우저 자동화 실행은 절대 금지. 반드시 local agent로 handoff해야 한다."),
        required_execution_location=LOC_AGENT,
        blocked_scopes=(),
        test_required=True,
        safe_to_execute_on_server=False,
    ),
    # 8. APPROVAL_REQUIRED_GATE
    "APPROVAL_REQUIRED_GATE": SafetyPolicyRecord(
        policy_id="APPROVAL_REQUIRED_GATE",
        name="승인 필요 작업 무단 실행 차단",
        category="approval_gate",
        severity=SEV_HIGH,
        applies_to=("blog_publish", "cafe_post_write", "send_email", "send_message", "form_submit", "file_upload"),
        decision=DECISION_REQUIRE_APPROVAL,
        reason=("게시/발송/제출 등 외부 가시적 작업은 사용자 명시적 승인 없이 실행할 수 없다."),
        required_execution_location=None,
        blocked_scopes=(),
        test_required=True,
        safe_to_execute_on_server=False,
    ),
    # ── 신뢰 세션 / 최종 승인 게이트 정책 (9~18) ──────────────────────────
    # 9. USER_PRESENT_AUTH_REQUIRED
    "USER_PRESENT_AUTH_REQUIRED": SafetyPolicyRecord(
        policy_id="USER_PRESENT_AUTH_REQUIRED",
        name="최초 인증은 사용자 직접 수행 필수",
        category="auth_session",
        severity=SEV_CRITICAL,
        applies_to=(
            AUTH_MODE_USER_PRESENT,
            "login_new_session",
            "otp_input",
            "cert_login",
            "password_input",
            "captcha_solve",
        ),
        decision=DECISION_REQUIRE_USER,
        reason=(
            "신규 세션 생성 시 최초 로그인/OTP/인증서 비밀번호 입력은 반드시 사용자가 직접 수행한다. AI 자동화 금지."
        ),
        required_execution_location=LOC_USER,
        blocked_scopes=("login_new_session", "otp_input", "cert_login"),
        test_required=True,
        safe_to_execute_on_server=False,
    ),
    # 10. TRUSTED_SESSION_REUSE_ALLOWED
    "TRUSTED_SESSION_REUSE_ALLOWED": SafetyPolicyRecord(
        policy_id="TRUSTED_SESSION_REUSE_ALLOWED",
        name="사용자 승인 신뢰 세션 AI 재사용 허용",
        category="auth_session",
        severity=SEV_LOW,
        applies_to=(
            AUTH_MODE_TRUSTED_REUSE,
            CLS_TRUSTED_SESSION,
            "navigate_to_work_screen",
            "fill_form",
            "read_page",
        ),
        decision=DECISION_ALLOW,
        reason=("사용자가 직접 로그인한 이후 승인된 신뢰 세션은 AI가 재사용하여 업무 화면까지 자동 진입할 수 있다."),
        required_execution_location=LOC_AGENT,
        blocked_scopes=(),
        test_required=True,
        safe_to_execute_on_server=False,
    ),
    # 11. SECRET_STORAGE_FORBIDDEN
    "SECRET_STORAGE_FORBIDDEN": SafetyPolicyRecord(
        policy_id="SECRET_STORAGE_FORBIDDEN",
        name="인증 비밀값 저장/기록 절대 금지",
        category="secret_storage",
        severity=SEV_CRITICAL,
        applies_to=(
            CLS_SECRET_STORAGE,
            "store_password",
            "store_otp",
            "store_cert_password",
            "store_token",
            "store_cookie",
            "store_session",
            "store_credential",
            "store_private_key",
            "dump_cookie",
            "extract_session",
        ),
        decision=DECISION_BLOCK,
        reason=(
            "password/otp/cert_password/token/cookie/session/credential/private_key는 "
            "어디에도 저장/기록/출력 불가. 세션 탈취 금지."
        ),
        required_execution_location=LOC_BLOCKED,
        blocked_scopes=(
            CLS_SECRET_STORAGE,
            "store_password",
            "store_otp",
            "store_cert_password",
            "dump_cookie",
            "extract_session",
        ),
        test_required=True,
        safe_to_execute_on_server=False,
    ),
    # 12. SERVER_SECURITY_LOGIN_BLOCKED
    "SERVER_SECURITY_LOGIN_BLOCKED": SafetyPolicyRecord(
        policy_id="SERVER_SECURITY_LOGIN_BLOCKED",
        name="서버에서 보안 로그인 자동화 절대 금지",
        category="server_security",
        severity=SEV_CRITICAL,
        applies_to=(
            "server_browser_login",
            "server_cert_login",
            "server_otp_automation",
            "server_password_submit",
        ),
        decision=DECISION_BLOCK,
        reason=(
            "서버에서 보안 로그인(인증서/OTP/패스워드 제출)을 자동화하는 것은 "
            "인증서 파일 서버 복사·쿠키 덤프·세션 탈취 위험으로 절대 금지."
        ),
        required_execution_location=LOC_BLOCKED,
        blocked_scopes=(
            "server_browser_login",
            "server_cert_login",
            "server_otp_automation",
            "server_password_submit",
        ),
        test_required=True,
        safe_to_execute_on_server=False,
    ),
    # 13. LOCAL_AGENT_SECURE_LOGIN_REQUIRED
    "LOCAL_AGENT_SECURE_LOGIN_REQUIRED": SafetyPolicyRecord(
        policy_id="LOCAL_AGENT_SECURE_LOGIN_REQUIRED",
        name="보안 로그인은 로컬 에이전트에서만 허용",
        category="auth_session",
        severity=SEV_HIGH,
        applies_to=(
            CLS_CERT_AUTH,
            "cert_based_login_local",
            "browser_session_local",
        ),
        decision=DECISION_REQUIRE_AGENT,
        reason=(
            "인증서 기반 로그인 등 보안 인증은 로컬 PC 에이전트에서만 수행한다. "
            "인증서 파일을 서버로 복사하거나 서버에서 실행하는 것은 금지."
        ),
        required_execution_location=LOC_AGENT,
        blocked_scopes=(),
        test_required=True,
        safe_to_execute_on_server=False,
    ),
    # 14. FINAL_APPROVAL_GATE_REQUIRED
    "FINAL_APPROVAL_GATE_REQUIRED": SafetyPolicyRecord(
        policy_id="FINAL_APPROVAL_GATE_REQUIRED",
        name="최종 저장/제출/결제/서명/도메인 변경 자동 실행 금지",
        category="final_approval_gate",
        severity=SEV_CRITICAL,
        applies_to=(
            CLS_FINAL_ACTION,
            FINAL_ACTION_SAVE,
            FINAL_ACTION_SUBMIT,
            FINAL_ACTION_PAY,
            FINAL_ACTION_SIGN,
            FINAL_ACTION_DOMAIN_CHANGE,
            FINAL_ACTION_SEND,
            FINAL_ACTION_BID,
            FINAL_ACTION_TRANSFER,
            "click_save_button",
            "click_submit_button",
            "click_pay_button",
            "click_sign_button",
            "click_apply_dns",
            "click_send_button",
            "click_bid_submit",
            "click_transfer_confirm",
        ),
        decision=DECISION_REQUIRE_APPROVAL,
        reason=(
            "저장/제출/결제/전자서명/DNS변경/발송/입찰/송금 등 최종 확정 버튼은 "
            "사용자 명시적 승인 게이트 통과 전까지 AI가 자동 클릭 절대 금지."
        ),
        required_execution_location=LOC_USER,
        blocked_scopes=(CLS_FINAL_ACTION,),
        test_required=True,
        safe_to_execute_on_server=False,
    ),
    # 15. CERTIFICATE_PASSWORD_NEVER_STORED
    "CERTIFICATE_PASSWORD_NEVER_STORED": SafetyPolicyRecord(
        policy_id="CERTIFICATE_PASSWORD_NEVER_STORED",
        name="인증서 비밀번호 저장/전달 절대 금지",
        category="secret_storage",
        severity=SEV_CRITICAL,
        applies_to=(
            "cert_password_store",
            "cert_password_transmit",
            "cert_password_log",
            "cert_file_server_copy",
        ),
        decision=DECISION_BLOCK,
        reason=("전자서명 인증서 비밀번호는 AI/서버/로그 어디에도 저장·전달·출력 불가. 인증서 파일 서버 복사 금지."),
        required_execution_location=LOC_BLOCKED,
        blocked_scopes=(
            "cert_password_store",
            "cert_password_transmit",
            "cert_password_log",
            "cert_file_server_copy",
        ),
        test_required=True,
        safe_to_execute_on_server=False,
    ),
    # 16. OAUTH_REFRESH_TOKEN_SECURE_STORE_ONLY
    "OAUTH_REFRESH_TOKEN_SECURE_STORE_ONLY": SafetyPolicyRecord(
        policy_id="OAUTH_REFRESH_TOKEN_SECURE_STORE_ONLY",
        name="OAuth refresh token 보안 저장소 전용",
        category="secret_storage",
        severity=SEV_HIGH,
        applies_to=("oauth_refresh_token_plain_store", "oauth_token_log"),
        decision=DECISION_BLOCK,
        reason=("OAuth refresh token은 암호화된 보안 저장소 외에 저장 금지. 로그/응답/파일에 plain text 출력 금지."),
        required_execution_location=LOC_BLOCKED,
        blocked_scopes=("oauth_refresh_token_plain_store", "oauth_token_log"),
        test_required=True,
        safe_to_execute_on_server=False,
    ),
    # 17. DOMAIN_DNS_CHANGE_APPROVAL_REQUIRED
    "DOMAIN_DNS_CHANGE_APPROVAL_REQUIRED": SafetyPolicyRecord(
        policy_id="DOMAIN_DNS_CHANGE_APPROVAL_REQUIRED",
        name="도메인/DNS 변경 사용자 승인 필수",
        category="final_approval_gate",
        severity=SEV_CRITICAL,
        applies_to=(
            CLS_DOMAIN_CHANGE,
            "gabia_dns_apply",
            "gabia_domain_modify",
            "dns_record_change",
            "nameserver_change",
        ),
        decision=DECISION_REQUIRE_APPROVAL,
        reason=(
            "도메인/DNS 변경은 서비스 전체에 영향을 주므로 사용자 명시적 승인 없이 AI가 적용 버튼을 클릭할 수 없다."
        ),
        required_execution_location=LOC_USER,
        blocked_scopes=(CLS_DOMAIN_CHANGE,),
        test_required=True,
        safe_to_execute_on_server=False,
    ),
    # 18. TRUSTED_SESSION_EXPIRE_REAUTH_REQUIRED
    "TRUSTED_SESSION_EXPIRE_REAUTH_REQUIRED": SafetyPolicyRecord(
        policy_id="TRUSTED_SESSION_EXPIRE_REAUTH_REQUIRED",
        name="신뢰 세션 만료 시 재인증 필수",
        category="auth_session",
        severity=SEV_HIGH,
        applies_to=(
            "trusted_session_expired",
            "session_timeout",
            "auth_cookie_expired",
            "login_redirect_detected",
        ),
        decision=DECISION_REQUIRE_USER,
        reason=("신뢰 세션이 만료되면 AI가 자동으로 재로그인하지 않는다. 사용자에게 재인증을 요청하고 대기한다."),
        required_execution_location=LOC_USER,
        blocked_scopes=("trusted_session_expired",),
        test_required=True,
        safe_to_execute_on_server=False,
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_policy(policy_id: str) -> SafetyPolicyRecord | None:
    """policy_id로 정책을 조회한다."""
    return _POLICY_REGISTRY.get(policy_id)


def list_all_policies() -> list[SafetyPolicyRecord]:
    """전체 정책 목록을 반환한다."""
    return list(_POLICY_REGISTRY.values())


def list_policy_ids() -> list[str]:
    """전체 정책 ID 목록을 반환한다."""
    return list(_POLICY_REGISTRY.keys())


def get_policies_by_category(category: str) -> list[SafetyPolicyRecord]:
    """category별 정책 목록을 반환한다."""
    return [p for p in _POLICY_REGISTRY.values() if p.category == category]


def is_scope_blocked_by_policy(scope: str) -> bool:
    """classification/scope 값이 어느 정책에서든 blocked_scopes에 포함되면 True."""
    for policy in _POLICY_REGISTRY.values():
        if scope in policy.blocked_scopes:
            return True
    return False


def get_enforcement_decision(classification: str) -> str:
    """classification 값에 대한 강제 decision을 반환한다.

    여러 정책이 매칭되면 가장 restrictive한 decision을 반환한다.
    우선순위: block > hold > require_approval > require_user_direct > require_local_agent > allow
    """
    priority = {
        DECISION_BLOCK: 0,
        DECISION_HOLD: 1,
        DECISION_REQUIRE_APPROVAL: 2,
        DECISION_REQUIRE_USER: 3,
        DECISION_REQUIRE_AGENT: 4,
        DECISION_ALLOW: 5,
    }
    best: str | None = None
    for policy in _POLICY_REGISTRY.values():
        if classification in policy.applies_to or classification in policy.blocked_scopes:
            if best is None or priority.get(policy.decision, 99) < priority.get(best, 99):
                best = policy.decision
    return best or DECISION_ALLOW


def get_safe_to_execute_on_server(classification: str) -> bool:
    """classification이 서버 실행 안전한지 모든 관련 정책을 검토하여 반환한다."""
    for policy in _POLICY_REGISTRY.values():
        if classification in policy.applies_to or classification in policy.blocked_scopes:
            if not policy.safe_to_execute_on_server:
                return False
    return True


# External app hold 분류 집합 (STEP 6 대상)
EXTERNAL_APP_HOLD_SCOPES: frozenset[str] = frozenset(
    {
        CLS_EXTERNAL_APP_HOLD,
        CLS_FUTURE,
        "CAD_EXTERNAL_APP_BRIDGE",
        "HWPX_EXTERNAL_APP_BRIDGE",
        "OFFICE_EXTERNAL_APP_BRIDGE",
        "TAX_EXTERNAL_APP_BRIDGE",
        "BID_EXTERNAL_APP_BRIDGE",
        "DOCUMENT_AUTOMATION_EXTERNAL_APP_BRIDGE",
    }
)

# OAuth/API 필요 분류 집합 (STEP 7 대상)
OAUTH_REQUIRED_SCOPES: frozenset[str] = frozenset(
    {
        CLS_OAUTH_REQUIRED,
    }
)

# user direct 분류 집합 (STEP 8 대상)
USER_DIRECT_SCOPES: frozenset[str] = frozenset(
    {
        CLS_USER_DIRECT,
        LOC_USER,
    }
)

# local agent 분류 집합 (STEP 9 대상)
LOCAL_AGENT_SCOPES: frozenset[str] = frozenset(
    {
        CLS_LOCAL_AGENT,
        LOC_AGENT,
    }
)

# 신뢰 세션 관련 분류 집합
TRUSTED_SESSION_SCOPES: frozenset[str] = frozenset(
    {
        AUTH_MODE_TRUSTED_REUSE,
        CLS_TRUSTED_SESSION,
        "navigate_to_work_screen",
        "fill_form",
    }
)

# 최종 승인 게이트 분류 집합
FINAL_ACTION_SCOPES: frozenset[str] = frozenset(
    {
        CLS_FINAL_ACTION,
        *FINAL_ACTION_TYPES,
        "click_save_button",
        "click_submit_button",
        "click_pay_button",
        "click_sign_button",
        "click_apply_dns",
        "click_send_button",
        "click_bid_submit",
        "click_transfer_confirm",
    }
)

# 시크릿 저장 금지 집합
SECRET_STORAGE_SCOPES: frozenset[str] = frozenset(
    {
        CLS_SECRET_STORAGE,
        "store_password",
        "store_otp",
        "store_cert_password",
        "store_token",
        "store_cookie",
        "dump_cookie",
        "extract_session",
        "cert_password_store",
        "cert_password_transmit",
        "cert_file_server_copy",
        "oauth_refresh_token_plain_store",
    }
)

# 도메인/DNS 변경 분류 집합
DOMAIN_CHANGE_SCOPES: frozenset[str] = frozenset(
    {
        CLS_DOMAIN_CHANGE,
        "gabia_dns_apply",
        "gabia_domain_modify",
        "dns_record_change",
        "nameserver_change",
    }
)
