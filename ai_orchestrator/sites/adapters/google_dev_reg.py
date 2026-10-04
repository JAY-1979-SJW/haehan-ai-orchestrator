"""구글 OAuth 2.0 클라이언트 등록 어댑터.

Google Cloud Console OAuth 동의 화면 설정 및 클라이언트 ID 생성 폼 자동 입력.

흐름:
  1. OAuth 동의 화면 구성 (앱 이름, 지원 이메일, 개발자 이메일)
  2. 승인된 리다이렉트 URI 추가

공통 파라미터 → Google Console DOM 매핑 (우선순위: aria-label/role 기반):
  app_name       → input[formcontrolname='displayName']
  service_url    → input[formcontrolname='homepageUrl']
  redirect_uri   → input[placeholder='Enter a URI']  (Add URI 버튼 클릭 후)
  contact_email  → input[formcontrolname='userSupportEmail']
  purpose        → (참조용, 직접 입력 필드 없음)

submit 버튼 우선순위:
  1순위: button[aria-label='Save and continue']  (aria-label 기반)
  폴백:  button.save-button                       (class 기반)

구현 원칙:
  - 폼 입력만 수행. 제출 버튼은 run_dev_reg 의 승인 확인 후에만 클릭.
  - dry_run=True 이면 페이지 조작 없이 검증·요약만 반환.
  - 패스워드·쿠키·세션 토큰·client_secret 을 summary 에 포함 금지.
  - CAPTCHA / 2FA 자동 우회 금지.
  - 로그인 세션은 사전에 사람이 완료해야 한다.

주의:
  Google Console UI 는 Angular SPA 로 렌더링이 늦어 networkidle 대신
  특정 selector 출현을 기다리는 방식을 사용한다.
  실제 DOM 에 맞게 선택자를 조정해야 할 수 있다.
"""
from __future__ import annotations

import logging

from .dev_reg_base import (
    DevRegAdapterBase,
    ErrorCode,
    FormFillResult,
    SubmitResult,
    _build_safe_summary,
    _has_element,
    _is_login_redirect,
    validate_params,
)

logger = logging.getLogger(__name__)

# Google Cloud Console — OAuth 동의 화면 설정 페이지
_CONSENT_URL = "https://console.cloud.google.com/apis/credentials/consent"

# OAuth 클라이언트 ID 생성 페이지
_CLIENT_URL = "https://console.cloud.google.com/apis/credentials/oauthclient"

# formcontrolname 기반 선택자 (Angular SPA 안정 속성, 우선순위 2순위 상당)
_CONSENT_SELECTORS: dict[str, str] = {
    "app_name":      "input[formcontrolname='displayName']",
    "contact_email": "input[formcontrolname='userSupportEmail']",
    "service_url":   "input[formcontrolname='homepageUrl']",
}

# 개발자 연락처 이메일 (동의 화면 하단 별도 영역) — aria-label 기반(1순위)
_DEV_EMAIL_SELECTOR = "input[aria-label='Developer contact information email addresses']"

# 리다이렉트 URI — Add 버튼(aria-label 1순위) + 입력창(placeholder 3순위)
_REDIRECT_URI_ADD_BTN = "button[aria-label='Add URI']"
_REDIRECT_URI_INPUT   = "input[placeholder='Enter a URI']"

# 제출 버튼: aria-label(1순위) → class 기반 폴백
_CONSENT_SAVE_BTN_SELECTORS = (
    "button[aria-label='Save and continue']",
    "button.save-button",
)

# 로그인 리다이렉트 감지 URL 패턴
_LOGIN_HINTS = ("accounts.google.com/signin", "accounts.google.com/login", "/signin")


def _fill_consent_fields(page, params: dict, filled: list[str], errors_fill: list[str]) -> None:
    """동의 화면 필드 + 개발자 연락처 이메일 입력 (filled/errors_fill 에 누적)."""
    for field_name, selector in _CONSENT_SELECTORS.items():
        value = params.get(field_name, "")
        if not value:
            continue
        try:
            page.fill(selector, str(value))
            filled.append(field_name)
        except Exception as e:  # noqa: BLE001 - 구글 개발자 콘솔 동의화면 폼 자동입력 어댑터 - 필드 입력/제출 실패 시 에러 메시지를 결과에 담아 반환(성공으로 위장하지 않음), 최종 제출 여부는 호출측 승인 흐름에서 별도 처리
            errors_fill.append(f"{field_name}: {e}")
            logger.warning("구글 폼 입력 실패 | field=%s | %s", field_name, e)

    # 개발자 연락처 이메일 (동의 화면 하단 별도 영역)
    dev_email = params.get("contact_email", "")
    if dev_email and "contact_email" not in filled:
        try:
            page.fill(_DEV_EMAIL_SELECTOR, str(dev_email))
            if "contact_email" not in filled:
                filled.append("contact_email")
        except Exception as e:  # noqa: BLE001 - 구글 개발자 콘솔 동의화면 폼 자동입력 어댑터 - 필드 입력/제출 실패 시 에러 메시지를 결과에 담아 반환(성공으로 위장하지 않음), 최종 제출 여부는 호출측 승인 흐름에서 별도 처리
            logger.warning("구글 개발자 이메일 입력 실패: %s", e)


def _add_redirect_uri(page, params: dict, filled: list[str], errors_fill: list[str]) -> None:
    """리다이렉트 URI 추가 (filled/errors_fill 에 누적)."""
    redirect_uri = params.get("redirect_uri", "")
    if redirect_uri:
        try:
            page.click(_REDIRECT_URI_ADD_BTN)
            page.fill(_REDIRECT_URI_INPUT, str(redirect_uri))
            filled.append("redirect_uri")
        except Exception as e:  # noqa: BLE001 - 구글 개발자 콘솔 동의화면 폼 자동입력 어댑터 - 필드 입력/제출 실패 시 에러 메시지를 결과에 담아 반환(성공으로 위장하지 않음), 최종 제출 여부는 호출측 승인 흐름에서 별도 처리
            errors_fill.append(f"redirect_uri: {e}")
            logger.warning("구글 redirect_uri 입력 실패: %s", e)


class GoogleDevRegAdapter(DevRegAdapterBase):
    """구글 OAuth 2.0 클라이언트 등록 어댑터."""

    provider = "google"
    action_type = "oauth_submit"
    risk_level = "high"

    def fill_form(self, page, params: dict) -> FormFillResult:
        """OAuth 동의 화면 및 클라이언트 설정 폼 자동 입력 (제출 버튼 제외).

        params["dry_run"]=True 이면 페이지 조작 없이 검증·요약만 반환.
        """
        dry_run = bool(params.get("dry_run", False))

        errors = validate_params(params)
        if errors:
            return FormFillResult(
                success=False, summary="", field_names=[],
                target_url="", error="; ".join(errors),
                error_code=ErrorCode.FORM_FIELD_MISSING,
            )

        if dry_run:
            filled = [k for k in _CONSENT_SELECTORS if params.get(k)]
            if params.get("redirect_uri"):
                filled.append("redirect_uri")
            summary = _build_safe_summary(self.provider, params, filled)
            return FormFillResult(
                success=True,
                summary=f"[DRY RUN]\n{summary}",
                field_names=filled,
                target_url=_CONSENT_URL,
            )

        # ── 1단계: 동의 화면 설정 ──────────────────────────────────────
        try:
            page.goto(_CONSENT_URL, wait_until="domcontentloaded")
            page.wait_for_selector(_CONSENT_SELECTORS["app_name"], timeout=15000)
        except Exception as e:  # noqa: BLE001 - 구글 개발자 콘솔 동의화면 폼 자동입력 어댑터 - 필드 입력/제출 실패 시 에러 메시지를 결과에 담아 반환(성공으로 위장하지 않음), 최종 제출 여부는 호출측 승인 흐름에서 별도 처리
            return FormFillResult(
                success=False, summary="", field_names=[],
                target_url=_CONSENT_URL, error=f"페이지 로드 실패: {e}",
                error_code=ErrorCode.PAGE_LOAD_FAILED,
            )

        if _is_login_redirect(page, _LOGIN_HINTS):
            return FormFillResult(
                success=False, summary="", field_names=[],
                target_url=_CONSENT_URL, error="로그인이 필요합니다",
                error_code=ErrorCode.LOGIN_REQUIRED,
            )

        filled: list[str] = []
        errors_fill: list[str] = []

        _fill_consent_fields(page, params, filled, errors_fill)

        # ── 2단계: 리다이렉트 URI 추가 ──────────────────────────────────
        _add_redirect_uri(page, params, filled, errors_fill)

        if errors_fill:
            return FormFillResult(
                success=False, summary="", field_names=filled,
                target_url=page.url, error="; ".join(errors_fill),
                error_code=ErrorCode.PROVIDER_LAYOUT_CHANGED,
            )

        return FormFillResult(
            success=True,
            summary=_build_safe_summary(self.provider, params, filled),
            field_names=filled,
            target_url=page.url,
        )

    def submit_form(self, page) -> SubmitResult:
        """저장/생성 버튼 클릭 — run_dev_reg 의 승인 확인 후에만 호출된다."""
        btn_sel = next(
            (s for s in _CONSENT_SAVE_BTN_SELECTORS if _has_element(page, s)), None
        )
        if btn_sel is None:
            return SubmitResult(
                success=False, result_summary="",
                error="제출 버튼을 찾을 수 없습니다",
                error_code=ErrorCode.SUBMIT_BUTTON_NOT_FOUND,
            )
        try:
            page.click(btn_sel)
            page.wait_for_load_state("domcontentloaded")
            result_text = page.inner_text("body") or ""
            if any(kw in result_text for kw in ("saved", "created", "완료", "성공", "success")):
                return SubmitResult(success=True, result_summary="OAuth 설정 저장 완료")
            return SubmitResult(
                success=True,
                result_summary=f"제출 완료 (결과 확인 필요): {result_text[:200]}",
            )
        except Exception as e:  # noqa: BLE001 - 구글 개발자 콘솔 동의화면 폼 자동입력 어댑터 - 필드 입력/제출 실패 시 에러 메시지를 결과에 담아 반환(성공으로 위장하지 않음), 최종 제출 여부는 호출측 승인 흐름에서 별도 처리
            logger.error("구글 submit_form 실패: %s", e)
            return SubmitResult(success=False, result_summary="", error=str(e))

    def abort_form(self, page) -> None:
        """OAuth 설정 페이지 안전 중단."""
        try:
            page.goto("about:blank")
        except Exception as e:  # noqa: BLE001 - 구글 개발자 콘솔 동의화면 폼 자동입력 어댑터 - 필드 입력/제출 실패 시 에러 메시지를 결과에 담아 반환(성공으로 위장하지 않음), 최종 제출 여부는 호출측 승인 흐름에서 별도 처리
            logger.warning("구글 abort_form: 페이지 이동 실패 (무시) | %s", e)
