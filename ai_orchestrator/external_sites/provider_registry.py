"""External Site Provider Canonical Registry.

[ASSISTANT_EXTERNAL_SITE_MANAGEMENT_CANONICAL_REGISTRY_01]

모든 외부 사이트의 로그인 정책, 자동화 범위, 위험도를 단일 소스로 관리한다.
DNS 저장/변경 없음. 실제 사이트 접속 없음. 쿠키 저장 없음.
"""
from __future__ import annotations

from ai_orchestrator.external_sites.provider_models import (
    SiteProviderEntry,
    RISK_CRITICAL, RISK_HIGH,
    STATUS_CURRENT, STATUS_PLANNED,
    CAT_DOMAIN_DNS, CAT_SOCIAL_LOGIN, CAT_PORTAL_LOGIN,
    CAT_COMMERCE, CAT_OFFICIAL_API, CAT_GROUPWARE,
    CAT_PUBLIC_BID, CAT_PUBLIC_ADMIN, CAT_EMAIL, CAT_BANK,
    AUTOMATION_PLANNED, AUTOMATION_PLANNED_USER, AUTOMATION_PLANNED_CERT,
    AUTOMATION_PLANNED_API, AUTOMATION_RECOVERED, AUTOMATION_LOGIN_ONLY,
    AUTOMATION_LOGIN_GABIA,
)

# ---------------------------------------------------------------------------
# Provider 정의
# ---------------------------------------------------------------------------

_GABIA = SiteProviderEntry(
    provider_id="GABIA",
    display_name="가비아",
    category=CAT_DOMAIN_DNS,
    primary_url="https://www.gabia.com/",
    login_url="https://www.gabia.com/?r=member/login",
    management_url="https://dns.gabia.com/",
    official_navigation_required=True,
    guessed_url_allowed=False,
    user_present_login_required=True,
    desktop_app_required=True,
    server_remote_login_allowed=False,
    cookie_storage_allowed=False,
    token_storage_allowed=False,
    browser_profile_reuse_allowed=True,
    official_api_preferred=False,
    cdp_browser_allowed=True,
    headless_allowed=False,
    approval_gate_required=True,
    certificate_login_required=False,
    high_risk_actions=(
        "DNS_RECORD_SAVE", "DOMAIN_TRANSFER",
        "NAMESERVER_CHANGE", "PAYMENT", "ACCOUNT_CHANGE",
    ),
    allowed_automation_scope=(
        "open login page",
        "navigate by official menu or actual DOM link",
        "read visible DNS table",
        "prepare draft",
        "compare before/after",
        "stop at final approval",
    ),
    forbidden_automation_scope=(
        "save DNS without approval",
        "change nameserver",
        "store cookies",
        "guess management URL",
    ),
    navigation_status=AUTOMATION_RECOVERED,
    automation_status=AUTOMATION_PLANNED_USER,
    risk_level=RISK_HIGH,
    current_status=STATUS_CURRENT,
    notes="DNS 관리툴 URL: dns.gabia.com. 카카오 로그인 사용. 쿠키 추출 절대 금지.",
)

_KAKAO = SiteProviderEntry(
    provider_id="KAKAO",
    display_name="카카오",
    category=CAT_SOCIAL_LOGIN,
    primary_url="https://accounts.kakao.com/",
    login_url="https://accounts.kakao.com/login",
    management_url="",
    official_navigation_required=True,
    guessed_url_allowed=False,
    user_present_login_required=True,
    desktop_app_required=True,
    server_remote_login_allowed=False,
    cookie_storage_allowed=False,
    token_storage_allowed=False,
    browser_profile_reuse_allowed=True,
    official_api_preferred=False,
    cdp_browser_allowed=True,
    headless_allowed=False,
    approval_gate_required=False,
    certificate_login_required=False,
    high_risk_actions=("OAUTH_TOKEN_STORE",),
    allowed_automation_scope=(
        "open kakao login page",
        "wait for user login",
        "detect login completion",
    ),
    forbidden_automation_scope=(
        "automate password input",
        "bypass 2FA",
        "store oauth token",
        "replay oauth callback",
    ),
    navigation_status=STATUS_CURRENT,
    automation_status=AUTOMATION_LOGIN_GABIA,
    risk_level=RISK_HIGH,
    current_status=STATUS_CURRENT,
    notes="가비아 로그인 OAuth 제공자. 별도 세션 저장 금지.",
)

_NAVER = SiteProviderEntry(
    provider_id="NAVER",
    display_name="네이버",
    category=CAT_PORTAL_LOGIN,
    primary_url="https://www.naver.com/",
    login_url="https://nid.naver.com/nidlogin.login",
    management_url="https://www.naver.com/",
    official_navigation_required=True,
    guessed_url_allowed=False,
    user_present_login_required=True,
    desktop_app_required=True,
    server_remote_login_allowed=False,
    cookie_storage_allowed=False,
    token_storage_allowed=False,
    browser_profile_reuse_allowed=True,
    official_api_preferred=False,
    cdp_browser_allowed=True,
    headless_allowed=False,
    approval_gate_required=True,
    certificate_login_required=False,
    high_risk_actions=(
        "BLOG_PUBLISH", "SMARTSTORE_CHANGE", "PAYMENT", "ACCOUNT_CHANGE",
    ),
    allowed_automation_scope=(
        "navigate portal",
        "search",
        "read content",
        "prepare draft",
        "stop before publish",
    ),
    forbidden_automation_scope=(
        "store login cookies",
        "automate password",
        "publish without approval",
    ),
    navigation_status=AUTOMATION_PLANNED,
    automation_status=AUTOMATION_PLANNED,
    risk_level=RISK_HIGH,
    current_status=STATUS_PLANNED,
    notes="블로그 자동화 계획 중. 1회 로그인 후 CDP 프로필 재사용.",
)

_NAVER_SMARTSTORE = SiteProviderEntry(
    provider_id="NAVER_SMARTSTORE",
    display_name="네이버 스마트스토어",
    category=CAT_COMMERCE,
    primary_url="https://sell.smartstore.naver.com/",
    login_url="https://sell.smartstore.naver.com/#/home/dashboard",
    management_url="https://sell.smartstore.naver.com/",
    official_navigation_required=True,
    guessed_url_allowed=False,
    user_present_login_required=True,
    desktop_app_required=True,
    server_remote_login_allowed=False,
    cookie_storage_allowed=False,
    token_storage_allowed=False,
    browser_profile_reuse_allowed=True,
    official_api_preferred=False,
    cdp_browser_allowed=True,
    headless_allowed=False,
    approval_gate_required=True,
    certificate_login_required=False,
    high_risk_actions=(
        "PRODUCT_CREATE", "PRODUCT_UPDATE", "ORDER_ACTION",
        "SETTLEMENT_ACTION", "PAYMENT_ACTION",
    ),
    allowed_automation_scope=(
        "navigate",
        "read table",
        "prepare draft",
        "upload file after approval",
        "stop before final submit",
    ),
    forbidden_automation_scope=(
        "final save without approval",
        "settlement without approval",
        "delete product without approval",
    ),
    navigation_status=AUTOMATION_PLANNED,
    automation_status=AUTOMATION_PLANNED,
    risk_level=RISK_CRITICAL,
    current_status=STATUS_PLANNED,
    notes="상품/주문/정산 변경은 모두 사용자 승인 필수.",
)

_GOOGLE = SiteProviderEntry(
    provider_id="GOOGLE",
    display_name="구글",
    category=CAT_OFFICIAL_API,
    primary_url="https://www.google.com/",
    login_url="https://accounts.google.com/",
    management_url="https://myaccount.google.com/",
    official_navigation_required=True,
    guessed_url_allowed=False,
    user_present_login_required=True,
    desktop_app_required=False,
    server_remote_login_allowed=False,
    cookie_storage_allowed=False,
    token_storage_allowed=True,
    browser_profile_reuse_allowed=True,
    official_api_preferred=True,
    cdp_browser_allowed=True,
    headless_allowed=False,
    approval_gate_required=True,
    certificate_login_required=False,
    high_risk_actions=("ACCOUNT_CHANGE", "DATA_DELETE", "PAYMENT"),
    allowed_automation_scope=(
        "official OAuth flow",
        "Gmail API",
        "Drive API",
        "Calendar API",
    ),
    forbidden_automation_scope=(
        "scrape account pages",
        "store raw cookies",
        "bypass login",
        "store token outside secure storage",
    ),
    navigation_status=AUTOMATION_PLANNED,
    automation_status=AUTOMATION_PLANNED_API,
    risk_level=RISK_HIGH,
    current_status=STATUS_PLANNED,
    notes="공식 OAuth만 허용. 토큰은 secure storage에만 보관. raw cookie 금지.",
)

_HIWORKS = SiteProviderEntry(
    provider_id="HIWORKS",
    display_name="하이웍스",
    category=CAT_GROUPWARE,
    primary_url="https://office.hiworks.com/",
    login_url="https://office.hiworks.com/",
    management_url="https://office.hiworks.com/",
    official_navigation_required=True,
    guessed_url_allowed=False,
    user_present_login_required=True,
    desktop_app_required=True,
    server_remote_login_allowed=False,
    cookie_storage_allowed=False,
    token_storage_allowed=False,
    browser_profile_reuse_allowed=True,
    official_api_preferred=False,
    cdp_browser_allowed=True,
    headless_allowed=False,
    approval_gate_required=True,
    certificate_login_required=False,
    high_risk_actions=("SEND_EMAIL", "DELETE_EMAIL", "ACCOUNT_CHANGE"),
    allowed_automation_scope=(
        "navigate",
        "read inbox",
        "prepare draft",
        "stop before send",
    ),
    forbidden_automation_scope=(
        "send email without approval",
        "delete email without approval",
        "store cookies",
    ),
    navigation_status=AUTOMATION_PLANNED,
    automation_status=AUTOMATION_PLANNED,
    risk_level=RISK_HIGH,
    current_status=STATUS_PLANNED,
    notes="메일 발송은 반드시 사용자 승인 후. 자동 전송 금지.",
)

_G2B_NARA = SiteProviderEntry(
    provider_id="G2B_NARA",
    display_name="나라장터 G2B",
    category=CAT_PUBLIC_BID,
    primary_url="https://www.g2b.go.kr/",
    login_url="https://www.g2b.go.kr/",
    management_url="https://www.g2b.go.kr/",
    official_navigation_required=True,
    guessed_url_allowed=False,
    user_present_login_required=True,
    desktop_app_required=True,
    server_remote_login_allowed=False,
    cookie_storage_allowed=False,
    token_storage_allowed=False,
    browser_profile_reuse_allowed=False,
    official_api_preferred=False,
    cdp_browser_allowed=True,
    headless_allowed=False,
    approval_gate_required=True,
    certificate_login_required=True,
    high_risk_actions=(
        "BID_SUBMIT", "CERTIFICATE_SIGN", "DOCUMENT_SUBMIT", "PAYMENT",
    ),
    allowed_automation_scope=(
        "notice search",
        "file download",
        "form prepare",
        "document parse",
        "stop before submit/sign",
    ),
    forbidden_automation_scope=(
        "bid submit without approval",
        "certificate password storage",
        "certificate signing without user",
        "auto submit",
    ),
    navigation_status=AUTOMATION_PLANNED,
    automation_status=AUTOMATION_PLANNED_CERT,
    risk_level=RISK_CRITICAL,
    current_status=STATUS_PLANNED,
    notes="공인인증서 로그인. 투찰/서명은 사용자 직접. 인증서 비밀번호 저장 절대 금지.",
)

_HOMETAX = SiteProviderEntry(
    provider_id="HOMETAX",
    display_name="홈택스",
    category=CAT_PUBLIC_ADMIN,
    primary_url="https://www.hometax.go.kr/",
    login_url="https://www.hometax.go.kr/",
    management_url="https://www.hometax.go.kr/",
    official_navigation_required=True,
    guessed_url_allowed=False,
    user_present_login_required=True,
    desktop_app_required=True,
    server_remote_login_allowed=False,
    cookie_storage_allowed=False,
    token_storage_allowed=False,
    browser_profile_reuse_allowed=False,
    official_api_preferred=False,
    cdp_browser_allowed=True,
    headless_allowed=False,
    approval_gate_required=True,
    certificate_login_required=True,
    high_risk_actions=(
        "TAX_SUBMIT", "CERTIFICATE_SIGN", "PAYMENT", "DOCUMENT_ISSUE",
    ),
    allowed_automation_scope=(
        "navigate",
        "read tax data",
        "prepare form",
        "stop before submit",
    ),
    forbidden_automation_scope=(
        "tax submit without approval",
        "certificate signing without user",
        "store certificate password",
    ),
    navigation_status=AUTOMATION_PLANNED,
    automation_status=AUTOMATION_PLANNED_CERT,
    risk_level=RISK_CRITICAL,
    current_status=STATUS_PLANNED,
    notes="공인인증서 또는 간편인증. 세금 신고/납부는 사용자 직접.",
)

_WETAX = SiteProviderEntry(
    provider_id="WETAX",
    display_name="위택스",
    category=CAT_PUBLIC_ADMIN,
    primary_url="https://www.wetax.go.kr/",
    login_url="https://www.wetax.go.kr/",
    management_url="https://www.wetax.go.kr/",
    official_navigation_required=True,
    guessed_url_allowed=False,
    user_present_login_required=True,
    desktop_app_required=True,
    server_remote_login_allowed=False,
    cookie_storage_allowed=False,
    token_storage_allowed=False,
    browser_profile_reuse_allowed=False,
    official_api_preferred=False,
    cdp_browser_allowed=True,
    headless_allowed=False,
    approval_gate_required=True,
    certificate_login_required=True,
    high_risk_actions=("TAX_SUBMIT", "CERTIFICATE_SIGN", "PAYMENT", "DOCUMENT_ISSUE"),
    allowed_automation_scope=(
        "navigate", "read tax data", "prepare form", "stop before submit",
    ),
    forbidden_automation_scope=(
        "tax submit without approval", "certificate signing without user",
    ),
    navigation_status=AUTOMATION_PLANNED,
    automation_status=AUTOMATION_PLANNED_CERT,
    risk_level=RISK_CRITICAL,
    current_status=STATUS_PLANNED,
    notes="지방세 납부 사이트. 공인인증서 필요. 납부는 사용자 직접.",
)

_GOVERNMENT24 = SiteProviderEntry(
    provider_id="GOVERNMENT24",
    display_name="정부24",
    category=CAT_PUBLIC_ADMIN,
    primary_url="https://www.gov.kr/",
    login_url="https://www.gov.kr/",
    management_url="https://www.gov.kr/",
    official_navigation_required=True,
    guessed_url_allowed=False,
    user_present_login_required=True,
    desktop_app_required=True,
    server_remote_login_allowed=False,
    cookie_storage_allowed=False,
    token_storage_allowed=False,
    browser_profile_reuse_allowed=False,
    official_api_preferred=False,
    cdp_browser_allowed=True,
    headless_allowed=False,
    approval_gate_required=True,
    certificate_login_required=True,
    high_risk_actions=(
        "DOCUMENT_ISSUE", "CERTIFICATE_SIGN", "DOCUMENT_FINAL_SUBMIT",
    ),
    allowed_automation_scope=(
        "navigate", "search service", "prepare form", "stop before submit",
    ),
    forbidden_automation_scope=(
        "document issue without approval", "certificate signing without user",
    ),
    navigation_status=AUTOMATION_PLANNED,
    automation_status=AUTOMATION_PLANNED_CERT,
    risk_level=RISK_CRITICAL,
    current_status=STATUS_PLANNED,
    notes="공공서비스 발급/신청 사이트. 모든 제출은 사용자 직접.",
)

_EMAIL_GENERIC = SiteProviderEntry(
    provider_id="EMAIL_GENERIC",
    display_name="이메일 (일반)",
    category=CAT_EMAIL,
    primary_url="",
    login_url="",
    management_url="",
    official_navigation_required=True,
    guessed_url_allowed=False,
    user_present_login_required=True,
    desktop_app_required=False,
    server_remote_login_allowed=False,
    cookie_storage_allowed=False,
    token_storage_allowed=False,
    browser_profile_reuse_allowed=True,
    official_api_preferred=True,
    cdp_browser_allowed=False,
    headless_allowed=False,
    approval_gate_required=True,
    certificate_login_required=False,
    high_risk_actions=("EMAIL_SEND", "EMAIL_DELETE", "ACCOUNT_CHANGE"),
    allowed_automation_scope=(
        "read inbox via official API",
        "prepare draft",
        "stop before send",
    ),
    forbidden_automation_scope=(
        "send without approval",
        "store raw credentials",
        "scrape webmail",
    ),
    navigation_status=AUTOMATION_PLANNED,
    automation_status=AUTOMATION_PLANNED_API,
    risk_level=RISK_HIGH,
    current_status=STATUS_PLANNED,
    notes="공식 API 우선. 발송은 반드시 사용자 승인 후.",
)

_BANK_GENERIC = SiteProviderEntry(
    provider_id="BANK_GENERIC",
    display_name="은행 (일반)",
    category=CAT_BANK,
    primary_url="",
    login_url="",
    management_url="",
    official_navigation_required=True,
    guessed_url_allowed=False,
    user_present_login_required=True,
    desktop_app_required=True,
    server_remote_login_allowed=False,
    cookie_storage_allowed=False,
    token_storage_allowed=False,
    browser_profile_reuse_allowed=False,
    official_api_preferred=False,
    cdp_browser_allowed=False,
    headless_allowed=False,
    approval_gate_required=True,
    certificate_login_required=True,
    high_risk_actions=(
        "PAYMENT", "TRANSFER", "CERTIFICATE_SIGN", "ACCOUNT_CHANGE",
    ),
    allowed_automation_scope=("read balance via approved API",),
    forbidden_automation_scope=(
        "transfer without approval",
        "store certificate password",
        "automate banking login",
    ),
    navigation_status=AUTOMATION_PLANNED,
    automation_status=AUTOMATION_PLANNED_CERT,
    risk_level=RISK_CRITICAL,
    current_status=STATUS_PLANNED,
    notes="이체/결제는 절대 자동화 금지. 사용자 직접 실행만 허용.",
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PROVIDER_REGISTRY: tuple[SiteProviderEntry, ...] = (
    _GABIA, _KAKAO, _NAVER, _NAVER_SMARTSTORE,
    _GOOGLE, _HIWORKS, _G2B_NARA,
    _HOMETAX, _WETAX, _GOVERNMENT24,
    _EMAIL_GENERIC, _BANK_GENERIC,
)

_INDEX: dict[str, SiteProviderEntry] = {p.provider_id: p for p in PROVIDER_REGISTRY}


def get_provider(provider_id: str) -> SiteProviderEntry | None:
    return _INDEX.get(provider_id)


def list_by_risk(risk_level: str) -> list[SiteProviderEntry]:
    return [p for p in PROVIDER_REGISTRY if p.risk_level == risk_level]


def list_by_status(status: str) -> list[SiteProviderEntry]:
    return [p for p in PROVIDER_REGISTRY if p.current_status == status]


__all__ = [
    "PROVIDER_REGISTRY",
    "get_provider",
    "list_by_risk",
    "list_by_status",
]
