"""개발자 등록 신청 어댑터 추상 기반 클래스.

각 사이트(hiworks/naver/google)별 구체 어댑터는 이 클래스를 상속하여
fill_form / submit_form / abort_form 을 구현한다.

보안 원칙:
  - fill_form 의 summary 에 패스워드/쿠키/세션 토큰 포함 금지.
  - submit_form 은 run_dev_reg 에서 승인 확인 후에만 호출된다.
  - CAPTCHA / 2FA / OTP 자동 우회 금지.

공통 입력 스키마 (DevRegParams 참고):
  app_name, company_name, service_url, redirect_uri,
  contact_email, purpose, requested_scopes
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ── 표준 에러 코드 ────────────────────────────────────────────────────────────

class ErrorCode:
    """fill_form / submit_form 실패 시 error_code 에 기록되는 코드."""

    PAGE_LOAD_FAILED        = "PAGE_LOAD_FAILED"
    LOGIN_REQUIRED          = "LOGIN_REQUIRED"
    CAPTCHA_REQUIRED        = "CAPTCHA_REQUIRED"
    FORM_FIELD_MISSING      = "FORM_FIELD_MISSING"
    SUBMIT_BUTTON_NOT_FOUND = "SUBMIT_BUTTON_NOT_FOUND"
    APPROVAL_REQUIRED       = "APPROVAL_REQUIRED"
    PROVIDER_LAYOUT_CHANGED = "PROVIDER_LAYOUT_CHANGED"

# summary 에 포함 가능한 안전 필드 (값이 그대로 노출돼도 무방한 필드)
# password/cookie/session/token/client_secret 은 포함 금지
_SAFE_SUMMARY_FIELDS: frozenset[str] = frozenset({
    "app_name",
    "company_name",
    "service_url",
    "redirect_uri",
    "contact_email",   # 부분 마스킹 적용
    "purpose",
    "requested_scopes",
})

# dry_run 포함 공통 파라미터 전체 목록
KNOWN_PARAM_KEYS: frozenset[str] = _SAFE_SUMMARY_FIELDS | frozenset({"dry_run"})


@dataclass
class FormFillResult:
    success: bool
    summary: str         # 입력 필드 요약 (사람이 읽을 수 있는 텍스트, 민감 원문 금지)
    field_names: list    # 입력된 필드명 목록 (값은 포함하지 않음)
    target_url: str      # 신청 페이지 현재 URL
    error: str = ""
    error_code: str = "" # ErrorCode 상수 (실패 시에만 설정)


@dataclass
class SubmitResult:
    success: bool
    result_summary: str  # 제출 후 결과 요약 (성공/반려/오류 메시지)
    error: str = ""
    error_code: str = "" # ErrorCode 상수 (실패 시에만 설정)


# ── 공통 유틸리티 ────────────────────────────────────────────────────────────

def _has_element(page, selector: str) -> bool:
    """selector 에 해당하는 요소가 DOM 에 존재하면 True.

    page.query_selector() 결과가 None 이면 미존재. 예외 시 False 반환.
    """
    try:
        return page.query_selector(selector) is not None
    except Exception:
        return False


def _is_login_redirect(page, hints: tuple[str, ...]) -> bool:
    """현재 page.url 에 로그인 페이지 힌트가 포함되어 있으면 True."""
    try:
        url = str(page.url or "").lower()
        return any(h.lower() in url for h in hints)
    except Exception:
        return False


def validate_params(params: dict) -> list[str]:
    """필수 파라미터 검증. 오류 목록 반환. 빈 리스트 = 정상."""
    errors: list[str] = []
    if not str(params.get("app_name", "")).strip():
        errors.append("app_name 은 필수입니다")
    return errors


def _mask_email(email: str) -> str:
    """이메일 @ 앞 최대 3자리만 노출: abc***@domain.com."""
    at = email.find("@")
    if at < 0:
        return email[:3] + "***"
    prefix = email[:min(3, at)]  # @ 위치보다 앞까지만
    return prefix + "***" + email[at:]


def _build_safe_summary(provider: str, params: dict, filled: list[str]) -> str:
    """안전한 summary 문자열 생성.

    _SAFE_SUMMARY_FIELDS 에 포함된 필드만 출력.
    contact_email 은 부분 마스킹, 값은 80자 초과 시 잘라낸다.
    password / cookie / session / token / client_secret 절대 포함 금지.
    """
    lines = [f"[{provider} 개발자 등록 신청]"]
    for f in filled:
        if f not in _SAFE_SUMMARY_FIELDS:
            continue
        val = params.get(f, "")
        if f == "contact_email":
            display = _mask_email(str(val))
        elif f == "requested_scopes":
            display = ", ".join(val) if isinstance(val, list) else str(val)[:80]
        else:
            display = str(val)[:80] + ("..." if len(str(val)) > 80 else "")
        lines.append(f"  {f}: {display}")
    return "\n".join(lines)


# ── 추상 기반 클래스 ─────────────────────────────────────────────────────────

class DevRegAdapterBase(ABC):
    """개발자 등록 신청 사이트 어댑터 추상 기반."""

    provider: str       # "hiworks" / "naver" / "google"
    action_type: str    # "developer_apply" / "app_register" / "oauth_submit"
    risk_level: str     # "medium" / "high"

    @abstractmethod
    def fill_form(self, page, params: dict) -> FormFillResult:
        """신청 폼 자동 입력.

        제출 버튼은 클릭하지 않는다. 입력 완료 후 반환.
        params["dry_run"]=True 이면 페이지 조작 없이 검증·요약만 반환.
        summary 에 패스워드·쿠키·세션 토큰을 포함해서는 안 된다.
        """

    @abstractmethod
    def submit_form(self, page) -> SubmitResult:
        """제출 버튼 클릭 — run_dev_reg 에서 승인 확인 후에만 호출된다."""

    def abort_form(self, page) -> None:
        """브라우저 세션 안전 중단. 거절/만료 시 호출."""
        try:
            page.goto("about:blank")
        except Exception as e:
            logger.warning("abort_form: 페이지 이동 실패 (무시) | %s", e)

    def capture_screenshot(self, page, path: Path) -> Path:
        """현재 화면 스크린샷. Playwright page.screenshot() 기본 구현."""
        try:
            page.screenshot(path=str(path))
            logger.debug("스크린샷 저장: %s", path)
        except Exception as e:
            logger.warning("capture_screenshot 실패 (무시): %s", e)
        return path
