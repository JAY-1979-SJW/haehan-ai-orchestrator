"""브라우저 보안 로그인 헬퍼 — 공인인증서 / 간편인증 / OTP 이중 보안.

원칙
====
1. 자격증명(비밀번호·카드번호·주민번호·OTP 등)은 사용자 승인 후 AI가 입력 가능.
2. 간편인증(카카오/PASS/네이버)은 AI가 선택 버튼 클릭, 인증은 사용자 모바일 처리.
3. 공인인증서 PIN은 AI가 입력하지 않음 (보안 팝업 환경 제약).
4. 모든 로그인 시도는 감사 로그에 기록 (자격증명 값은 마스킹).

지원 로그인 방식
================
1. 세션 쿠키 자동 재사용 (Playwright persistent context)
2. 간편인증: 카카오, PASS, 네이버, 삼성패스
3. 공인인증서 (공동인증서): 사용자 직접 PIN 입력, AI는 트리거만
4. OTP / SMS / 이메일 인증: 사용자 승인 후 AI 자동 입력 또는 사용자 직접 입력
5. ID/PW 로그인: 사용자 승인 후 AI 자동 입력

사이트별 설정은 SITE_LOGIN_CONFIG 에 추가.
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass, field
from pathlib import Path

from ai_orchestrator.local_agent.browser.actions import (
    click,
    type_text,
    wait_ms,
)
from ai_orchestrator.local_agent.browser.approval_server import request_approval
from ai_orchestrator.local_agent.browser.audit_log import log_action
from ai_orchestrator.local_agent.browser.intent_token import IntentToken

# ── 로그인 상태 코드 ─────────────────────────────────────────────────────────

LOGIN_OK = "logged_in"
LOGIN_REQUIRED = "login_required"
LOGIN_TWO_FACTOR = "two_factor_required"
LOGIN_CERT = "cert_required"
LOGIN_UNKNOWN = "unknown"

# ── 간편인증 방식 ────────────────────────────────────────────────────────────

EASY_AUTH_KAKAO = "kakao"
EASY_AUTH_PASS = "pass"  # noqa: S105
EASY_AUTH_NAVER = "naver"
EASY_AUTH_SAMSUNG = "samsung"
EASY_AUTH_TOSS = "toss"

# ── 사이트별 로그인 설정 ─────────────────────────────────────────────────────

SITE_LOGIN_CONFIG: dict[str, dict] = {
    "www.gov.kr": {
        "name": "정부24",
        "login_indicators": ["로그인", "간편인증", "공동인증서"],
        "logged_in_indicators": ["마이페이지", "로그아웃", "내 신청내역"],
        "easy_auth": {
            EASY_AUTH_KAKAO: "li.kakao a, button[data-auth='kakao'], .kakao-login",
            EASY_AUTH_PASS: "li.pass a, button[data-auth='pass'], .pass-login",
            EASY_AUTH_NAVER: "li.naver a, button[data-auth='naver'], .naver-login",
        },
        "cert_btn": "button[data-login='cert'], a:has-text('공동인증서'), .cert-login",
        "two_factor_indicators": ["OTP", "추가인증", "2차 인증", "보안코드"],
    },
    "www.epeople.go.kr": {
        "name": "국민신문고",
        "login_indicators": ["로그인하세요", "로그인이 필요"],
        "logged_in_indicators": ["로그아웃", "마이페이지", "내 민원"],
        "easy_auth": {
            EASY_AUTH_KAKAO: "a.kakao-btn, .easy-login-kakao",
            EASY_AUTH_PASS: "a.pass-btn, .easy-login-pass",
        },
        "cert_btn": "a:has-text('공동인증서'), button:has-text('인증서 로그인')",
        "two_factor_indicators": ["OTP", "보안코드"],
    },
    "mail.google.com": {
        "name": "Gmail",
        "login_indicators": ["로그인", "Sign in", "이메일 또는 휴대전화"],
        "logged_in_indicators": ["받은편지함", "Inbox", "편지쓰기"],
        "easy_auth": {},
        "cert_btn": None,
        "two_factor_indicators": ["2단계 인증", "인증 코드", "Verify"],
    },
    "mail.naver.com": {
        "name": "네이버 메일",
        "login_indicators": ["로그인", "아이디"],
        "logged_in_indicators": ["받은메일함", "메일쓰기", "로그아웃"],
        "easy_auth": {},
        "cert_btn": None,
        "two_factor_indicators": ["일회용 번호", "OTP", "인증번호"],
    },
}


# ── 결과 ────────────────────────────────────────────────────────────────────


@dataclass
class LoginResult:
    status: str  # LOGIN_OK / LOGIN_REQUIRED / LOGIN_TWO_FACTOR / LOGIN_CERT
    site: str = ""
    method_used: str = ""
    message: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == LOGIN_OK


# ── 상태 감지 ────────────────────────────────────────────────────────────────


def detect_login_state(page, site_host: str = "") -> str:
    """현재 페이지의 로그인 상태를 감지."""
    try:
        text = page.inner_text("body")
    except Exception:  # noqa: BLE001 - 로그인 상태 감지/자격증명 입력 헬퍼 - 예외 발생 시 LOGIN_UNKNOWN 또는 False로 fail-closed 반환(로그인됨으로 오판하지 않음), 자격증명 값은 로그에 남기지 않고 길이만 기록
        return LOGIN_UNKNOWN

    cfg = _get_site_cfg(site_host or _extract_host(page))

    # 2FA/OTP 화면 먼저 확인
    two_factor_indicators = cfg.get("two_factor_indicators", [])
    if any(ind in text for ind in two_factor_indicators):
        return LOGIN_TWO_FACTOR

    # 공인인증서 요구 화면
    if any(kw in text for kw in ["공동인증서", "공인인증서", "인증서를 선택"]):
        return LOGIN_CERT

    # 로그인 완료 확인
    logged_in = cfg.get("logged_in_indicators", ["로그아웃"])
    if any(ind in text for ind in logged_in):
        return LOGIN_OK

    # 로그인 요구 화면
    login_req = cfg.get("login_indicators", ["로그인"])
    if any(ind in text for ind in login_req):
        return LOGIN_REQUIRED

    return LOGIN_UNKNOWN


def is_logged_in(page, site_host: str = "") -> bool:
    return detect_login_state(page, site_host) == LOGIN_OK


def is_two_factor_required(page, site_host: str = "") -> bool:
    return detect_login_state(page, site_host) == LOGIN_TWO_FACTOR


def is_cert_required(page, site_host: str = "") -> bool:
    return detect_login_state(page, site_host) == LOGIN_CERT


# ── 간편인증 ────────────────────────────────────────────────────────────────


def try_easy_auth(
    page,
    method: str = EASY_AUTH_KAKAO,
    *,
    site_host: str = "",
    intent: IntentToken | None = None,
    audit_path: Path | None = None,
    wait_seconds: int = 60,
) -> LoginResult:
    """간편인증 버튼 클릭 후 모바일 인증 완료 대기.

    AI는 버튼만 클릭. 사용자가 모바일 앱에서 인증을 완료하면 자동 감지.
    """
    host = site_host or _extract_host(page)
    cfg = _get_site_cfg(host)
    method_label = {
        EASY_AUTH_KAKAO: "카카오 간편인증",
        EASY_AUTH_PASS: "PASS 간편인증",
        EASY_AUTH_NAVER: "네이버 간편인증",
        EASY_AUTH_SAMSUNG: "삼성패스",
        EASY_AUTH_TOSS: "토스",
    }.get(method, method)

    selector = cfg.get("easy_auth", {}).get(method)
    if not selector:
        return LoginResult(
            status=LOGIN_REQUIRED,
            site=host,
            method_used=method,
            message=f"{method_label} 버튼 설정 없음",
        )

    print(f"[로그인] {method_label} 선택 중...")
    r = click(page, selector, label=f"{method_label} 버튼", intent=intent, audit_path=audit_path, force=True)
    if not r.ok:
        return LoginResult(
            status=LOGIN_REQUIRED,
            site=host,
            method_used=method,
            message=f"버튼 클릭 실패: {r.error}",
        )

    log_action(
        "easy_auth_initiated",
        url=page.url,
        extra={"method": method, "site": host},
        risk_level="AUTO",
        audit_path=audit_path,
    )

    print(f"[로그인] 모바일 {method_label} 인증을 완료해주세요. (최대 {wait_seconds}초 대기)")

    # 모바일 인증 완료 감지 (폴링)
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        time.sleep(2)
        state = detect_login_state(page, host)
        if state == LOGIN_OK:
            log_action(
                "login_success",
                url=page.url,
                extra={"method": method, "site": host},
                risk_level="AUTO",
                audit_path=audit_path,
            )
            print(f"[로그인] ✓ {method_label} 인증 완료")
            return LoginResult(status=LOGIN_OK, site=host, method_used=method)
        if state == LOGIN_TWO_FACTOR:
            print("[로그인] 추가 인증 단계 감지")
            return LoginResult(status=LOGIN_TWO_FACTOR, site=host, method_used=method)

    return LoginResult(
        status=LOGIN_REQUIRED,
        site=host,
        method_used=method,
        message=f"{wait_seconds}초 초과 — 인증 완료 감지 실패",
    )


# ── 공인인증서 로그인 ────────────────────────────────────────────────────────


def handle_cert_login(
    page,
    *,
    site_host: str = "",
    intent: IntentToken | None = None,
    audit_path: Path | None = None,
    wait_seconds: int = 120,
) -> LoginResult:
    """공인인증서(공동인증서) 로그인.

    AI는 인증서 로그인 버튼 클릭까지만 수행.
    인증서 선택 및 PIN 입력은 사용자가 브라우저 팝업에서 직접 처리.
    """
    host = site_host or _extract_host(page)
    cfg = _get_site_cfg(host)
    cert_sel = cfg.get("cert_btn")

    if cert_sel:
        print("[로그인] 공동인증서 로그인 버튼 클릭...")
        r = click(page, cert_sel, label="공동인증서 로그인", intent=intent, audit_path=audit_path, force=True)
        if not r.ok:
            print("[로그인] 버튼 클릭 실패, 수동으로 '공동인증서' 클릭 후 진행하세요.")

    log_action("cert_login_initiated", url=page.url, extra={"site": host}, risk_level="AUTO", audit_path=audit_path)

    print("\n[로그인] 공동인증서 로그인")
    print("  브라우저 팝업에서:")
    print("  1. 인증서를 선택하세요")
    print("  2. PIN 번호를 입력하세요")
    print("  ※ AI는 PIN을 입력하지 않습니다 (보안 원칙)")
    print(f"  로그인 완료 후 최대 {wait_seconds}초 대기합니다.")

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        time.sleep(2)
        state = detect_login_state(page, host)
        if state == LOGIN_OK:
            log_action(
                "cert_login_success", url=page.url, extra={"site": host}, risk_level="AUTO", audit_path=audit_path
            )
            print("[로그인] ✓ 공동인증서 로그인 완료")
            return LoginResult(status=LOGIN_OK, site=host, method_used="cert")
        if state == LOGIN_TWO_FACTOR:
            return LoginResult(status=LOGIN_TWO_FACTOR, site=host, method_used="cert")

    print("[로그인] 타임아웃: 브라우저에서 직접 로그인 후 엔터를 눌러주세요.")
    input("→ 로그인 완료 후 엔터: ")
    return LoginResult(
        status=detect_login_state(page, host),
        site=host,
        method_used="cert_manual",
    )


# ── OTP / 2단계 인증 ─────────────────────────────────────────────────────────


def handle_two_factor(
    page,
    *,
    site_host: str = "",
    intent: IntentToken | None = None,
    audit_path: Path | None = None,
    wait_seconds: int = 120,
) -> LoginResult:
    """OTP / SMS / 이메일 2단계 인증 처리.

    AI는 어떤 코드도 입력하지 않는다.
    사용자가 직접 코드를 입력하면 완료 자동 감지.
    """
    host = site_host or _extract_host(page)

    log_action("two_factor_started", url=page.url, extra={"site": host}, risk_level="AUTO", audit_path=audit_path)

    print("\n[로그인] 2단계 인증 필요")
    print("  OTP 앱, SMS, 또는 이메일의 인증 코드를 브라우저에 직접 입력하세요.")
    print("  ※ AI는 OTP 코드를 입력하지 않습니다 (보안 원칙)")
    print(f"  입력 완료 후 자동으로 감지합니다. (최대 {wait_seconds}초)")

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        time.sleep(2)
        state = detect_login_state(page, host)
        if state == LOGIN_OK:
            log_action(
                "two_factor_success", url=page.url, extra={"site": host}, risk_level="AUTO", audit_path=audit_path
            )
            print("[로그인] ✓ 2단계 인증 완료")
            return LoginResult(status=LOGIN_OK, site=host, method_used="two_factor")
        if state not in (LOGIN_TWO_FACTOR, LOGIN_UNKNOWN):
            break

    # 타임아웃 → 수동 확인
    print("[로그인] 타임아웃: 브라우저에서 인증 완료 후 엔터를 눌러주세요.")
    input("→ 인증 완료 후 엔터: ")
    return LoginResult(
        status=detect_login_state(page, host),
        site=host,
        method_used="two_factor_manual",
    )


# ── ID/PW 로그인 (사용자 직접) ───────────────────────────────────────────────


def handle_idpw_login(
    page,
    id_selector: str = "input[type='text'], input[name='userId'], input[name='id']",
    pw_selector: str = "input[type='password'], input[name='password'], input[name='pwd']",
    *,
    username: str = "",
    password: str = "",
    site_host: str = "",
    intent: IntentToken | None = None,
    audit_path: Path | None = None,
    wait_seconds: int = 120,
) -> LoginResult:
    """ID/PW 로그인.

    username/password 제공 시: 사용자 승인 후 AI가 직접 입력.
    제공 안 할 시: 사용자가 브라우저에서 직접 입력 후 완료 감지.
    """
    host = site_host or _extract_host(page)

    log_action(
        "idpw_login_started",
        url=page.url,
        extra={"site": host, "has_credentials": bool(username)},
        risk_level="AUTO",
        audit_path=audit_path,
    )

    if username and password:
        # 승인 후 AI 자동 입력 — 브라우저 팝업 승인
        approved = request_approval(
            action="login",
            label="아이디/비밀번호 자동 입력",
            category="CREDENTIAL",
            detail={"아이디": username, "비밀번호": "*" * min(len(password), 8), "사이트": host},
        )
        if not approved:
            print("[로그인] 사용자 거부 → 수동 입력 모드로 전환")
        else:
            try:
                type_text(page, id_selector, username, label="아이디", intent=intent, audit_path=audit_path, force=True)
                wait_ms(300)
                type_text(
                    page, pw_selector, password, label="password", intent=intent, audit_path=audit_path, force=True
                )
                wait_ms(300)
                # 로그인 버튼 클릭
                for btn_sel in (
                    "button[type='submit']",
                    "input[type='submit']",
                    "button:has-text('로그인')",
                    ".btn-login",
                    "#loginBtn",
                ):
                    try:
                        page.click(btn_sel, timeout=2000)
                        break
                    except Exception:  # noqa: BLE001, S112
                        continue
                wait_ms(2000)
                page.wait_for_load_state("networkidle", timeout=15000)
                state = detect_login_state(page, host)
                if state == LOGIN_OK:
                    log_action(
                        "idpw_login_success",
                        url=page.url,
                        extra={"site": host, "method": "ai_input"},
                        risk_level="APPROVE",
                        audit_path=audit_path,
                    )
                    print("[로그인] ✓ 자동 로그인 완료")
                    return LoginResult(status=LOGIN_OK, site=host, method_used="idpw_auto")
                if state == LOGIN_TWO_FACTOR:
                    return LoginResult(status=LOGIN_TWO_FACTOR, site=host, method_used="idpw_auto")
                if state == LOGIN_CERT:
                    return LoginResult(status=LOGIN_CERT, site=host, method_used="idpw_auto")
            except Exception as e:  # noqa: BLE001 - 로그인 상태 감지/자격증명 입력 헬퍼 - 예외 발생 시 LOGIN_UNKNOWN 또는 False로 fail-closed 반환(로그인됨으로 오판하지 않음), 자격증명 값은 로그에 남기지 않고 길이만 기록
                print(f"[로그인] 자동 입력 실패: {e} → 수동 입력 모드")

    # 수동 입력 모드 (자격증명 없거나 실패 시) - 포커스 실패해도 계속 진행(UI 편의 동작일 뿐)
    with contextlib.suppress(Exception):
        page.focus(id_selector)

    print("\n[로그인] 아이디/비밀번호를 브라우저에서 직접 입력 후 로그인하세요.")

    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        time.sleep(2)
        state = detect_login_state(page, host)
        if state == LOGIN_OK:
            log_action(
                "idpw_login_success",
                url=page.url,
                extra={"site": host, "method": "manual"},
                risk_level="AUTO",
                audit_path=audit_path,
            )
            print("[로그인] ✓ 로그인 완료")
            return LoginResult(status=LOGIN_OK, site=host, method_used="idpw")
        if state == LOGIN_TWO_FACTOR:
            return LoginResult(status=LOGIN_TWO_FACTOR, site=host, method_used="idpw")
        if state == LOGIN_CERT:
            return LoginResult(status=LOGIN_CERT, site=host, method_used="idpw")

    # 타임아웃 시 승인 팝업으로 안내
    request_approval(
        action="login_wait",
        label="로그인 완료 후 확인 버튼을 눌러주세요",
        category="CREDENTIAL",
        detail={"사이트": host, "안내": "브라우저에서 로그인 완료 후 승인을 클릭하세요"},
    )
    return LoginResult(
        status=detect_login_state(page, host),
        site=host,
        method_used="idpw_manual",
    )


def input_credential(
    page,
    selector: str,
    value: str,
    *,
    field_label: str = "자격증명",
    intent: IntentToken | None = None,
    audit_path: Path | None = None,
) -> bool:
    """자격증명(비밀번호·OTP·카드번호 등) 사용자 승인 후 AI 입력.

    승인 거부 시 False 반환. 입력 성공 시 True.
    감사 로그에는 값 길이만 기록 (실제 값 마스킹).
    """
    approved = request_approval(
        action="credential_input",
        label=f"{field_label} 입력",
        category="CREDENTIAL",
        detail={
            "필드": selector[:80],
            "길이": f"{len(value)}자",
            "값": "*" * min(len(value), 8),
        },
    )
    if not approved:
        log_action(
            "credential_input_rejected",
            url=page.url,
            extra={"field_label": field_label},
            risk_level="APPROVE",
            audit_path=audit_path,
        )
        return False

    try:
        type_text(page, selector, value, label=field_label, intent=intent, audit_path=audit_path, force=True)
        log_action(
            "credential_input_ok",
            url=page.url,
            extra={"field_label": field_label, "length": len(value)},
            risk_level="APPROVE",
            audit_path=audit_path,
        )
        return True
    except Exception as e:  # noqa: BLE001 - 로그인 상태 감지/자격증명 입력 헬퍼 - 예외 발생 시 LOGIN_UNKNOWN 또는 False로 fail-closed 반환(로그인됨으로 오판하지 않음), 자격증명 값은 로그에 남기지 않고 길이만 기록
        log_action(
            "credential_input_error",
            url=page.url,
            extra={"field_label": field_label, "error": str(e)[:100]},
            risk_level="APPROVE",
            audit_path=audit_path,
        )
        print(f"[자격증명] 입력 실패: {e}")
        return False


# ── 통합 로그인 오케스트레이터 ───────────────────────────────────────────────


def ensure_logged_in(
    page,
    *,
    site_host: str = "",
    preferred_method: str = EASY_AUTH_KAKAO,
    fallback_to_cert: bool = True,
    fallback_to_idpw: bool = True,
    intent: IntentToken | None = None,
    audit_path: Path | None = None,
) -> LoginResult:
    """로그인 상태 확인 → 필요 시 자동 로그인 처리.

    순서
    ----
    1. 이미 로그인 → 바로 반환 (세션 쿠키 재사용)
    2. 간편인증 시도 (preferred_method)
    3. 2FA 감지 → handle_two_factor()
    4. 공인인증서 감지 → handle_cert_login()
    5. 실패 시 ID/PW 로그인 안내 (fallback)
    """
    host = site_host or _extract_host(page)

    # 1. 이미 로그인 상태
    state = detect_login_state(page, host)
    if state == LOGIN_OK:
        print(f"[로그인] 이미 로그인 상태 ({host})")
        return LoginResult(status=LOGIN_OK, site=host, method_used="session")

    # 2. 공인인증서 화면
    if state == LOGIN_CERT:
        result = handle_cert_login(page, site_host=host, intent=intent, audit_path=audit_path)
        if result.ok:
            return result

    # 3. 2FA 화면
    if state == LOGIN_TWO_FACTOR:
        result = handle_two_factor(page, site_host=host, intent=intent, audit_path=audit_path)
        if result.ok:
            return result

    # 4. 간편인증 시도
    cfg = _get_site_cfg(host)
    if preferred_method in cfg.get("easy_auth", {}):
        result = try_easy_auth(page, preferred_method, site_host=host, intent=intent, audit_path=audit_path)
        if result.ok:
            return result
        if result.status == LOGIN_TWO_FACTOR:
            result2 = handle_two_factor(page, site_host=host, intent=intent, audit_path=audit_path)
            if result2.ok:
                return result2

    # 5. 공인인증서 fallback
    if fallback_to_cert and cfg.get("cert_btn"):
        print("\n[로그인] 간편인증 실패 → 공동인증서로 전환")
        result = handle_cert_login(page, site_host=host, intent=intent, audit_path=audit_path)
        if result.ok:
            return result

    # 6. ID/PW fallback
    if fallback_to_idpw:
        print("\n[로그인] 다른 방법 실패 → 아이디/비밀번호 로그인")
        result = handle_idpw_login(page, site_host=host, intent=intent, audit_path=audit_path)
        if result.ok:
            return result

    return LoginResult(
        status=LOGIN_REQUIRED,
        site=host,
        message="모든 로그인 방법 실패",
    )


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────────


def _extract_host(page) -> str:
    try:
        from urllib.parse import urlparse

        return urlparse(page.url).netloc
    except Exception:  # noqa: BLE001 - 로그인 상태 감지/자격증명 입력 헬퍼 - 예외 발생 시 LOGIN_UNKNOWN 또는 False로 fail-closed 반환(로그인됨으로 오판하지 않음), 자격증명 값은 로그에 남기지 않고 길이만 기록
        return ""


def _get_site_cfg(host: str) -> dict:
    return SITE_LOGIN_CONFIG.get(
        host,
        {
            "name": host,
            "login_indicators": ["로그인"],
            "logged_in_indicators": ["로그아웃"],
            "easy_auth": {},
            "cert_btn": None,
            "two_factor_indicators": ["OTP", "인증코드"],
        },
    )
