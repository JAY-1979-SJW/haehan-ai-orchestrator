"""하이웍스 개발자 신청 어댑터.

https://developers.hiworks.com 개발자 등록 신청 폼 자동 입력.

공통 파라미터 → 하이웍스 DOM 선택자 매핑 (우선순위: name/id 기반):
  app_name      → input[name='app_name']
  company_name  → input[name='company_name']
  purpose       → textarea[name='app_purpose']
  contact_email → input[name='contact_email']
  redirect_uri  → input[name='redirect_uri']
  service_url   → input[name='service_url']

submit 버튼: button[type='submit']
  — Hiworks apply 폼에서 type=submit 이 유일하므로 name/id 다음 안정 선택자.

구현 원칙:
  - 폼 입력만 수행. 제출 버튼은 run_dev_reg 의 승인 확인 후에만 클릭.
  - dry_run=True 이면 페이지 조작 없이 검증·요약만 반환.
  - 패스워드·쿠키·세션 토큰을 summary 에 포함 금지.
  - CAPTCHA / 2FA 자동 우회 금지.
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

_APPLY_URL = "https://developers.hiworks.com/apply"

# name/id 기반 선택자 (selector 우선순위 2순위)
_SELECTORS: dict[str, str] = {
    "app_name": "input[name='app_name']",
    "company_name": "input[name='company_name']",
    "purpose": "textarea[name='app_purpose']",
    "contact_email": "input[name='contact_email']",
    "redirect_uri": "input[name='redirect_uri']",
    "service_url": "input[name='service_url']",
}

# type=submit 은 Hiworks apply 폼 전용 제출 버튼 (페이지 내 유일)
_SUBMIT_BTN = "button[type='submit']"

# 로그인 리다이렉트 감지 URL 패턴
_LOGIN_HINTS = ("login", "signin", "account.hiworks.com/login")


class HiworksDevRegAdapter(DevRegAdapterBase):
    """하이웍스 개발자 등록 신청 어댑터."""

    provider = "hiworks"
    action_type = "developer_apply"
    risk_level = "high"

    def fill_form(self, page, params: dict) -> FormFillResult:
        """신청 폼 자동 입력 (제출 버튼 제외).

        params["dry_run"]=True 이면 페이지 조작 없이 검증·요약만 반환.
        """
        dry_run = bool(params.get("dry_run", False))

        errors = validate_params(params)
        if errors:
            return FormFillResult(
                success=False,
                summary="",
                field_names=[],
                target_url="",
                error="; ".join(errors),
                error_code=ErrorCode.FORM_FIELD_MISSING,
            )

        if dry_run:
            filled: list[str] = [k for k in _SELECTORS if params.get(k)]
            summary = _build_safe_summary(self.provider, params, filled)
            return FormFillResult(
                success=True,
                summary=f"[DRY RUN]\n{summary}",
                field_names=filled,
                target_url=_APPLY_URL,
            )

        try:
            page.goto(_APPLY_URL, wait_until="networkidle")
        except Exception as e:  # noqa: BLE001 - 하이웍스 개발자 등록 폼 자동입력 스크립트 — 페이지 로드/필드 입력/제출 실패 시 에러코드가 담긴 실패 결과(dict)를 반환하거나 개별 필드 오류를 누적할 뿐, 결제·삭제·자격증명 노출 없음
            return FormFillResult(
                success=False,
                summary="",
                field_names=[],
                target_url=_APPLY_URL,
                error=f"페이지 로드 실패: {e}",
                error_code=ErrorCode.PAGE_LOAD_FAILED,
            )

        if _is_login_redirect(page, _LOGIN_HINTS):
            return FormFillResult(
                success=False,
                summary="",
                field_names=[],
                target_url=_APPLY_URL,
                error="로그인이 필요합니다",
                error_code=ErrorCode.LOGIN_REQUIRED,
            )

        filled = []
        errors_fill: list[str] = []
        for field_name, selector in _SELECTORS.items():
            value = params.get(field_name, "")
            if not value:
                continue
            try:
                page.fill(selector, str(value))
                filled.append(field_name)
            except Exception as e:  # noqa: BLE001 - 하이웍스 개발자 등록 폼 자동입력 스크립트 — 페이지 로드/필드 입력/제출 실패 시 에러코드가 담긴 실패 결과(dict)를 반환하거나 개별 필드 오류를 누적할 뿐, 결제·삭제·자격증명 노출 없음
                errors_fill.append(f"{field_name}: {e}")
                logger.warning("하이웍스 폼 입력 실패 | field=%s | %s", field_name, e)

        if errors_fill:
            return FormFillResult(
                success=False,
                summary="",
                field_names=filled,
                target_url=page.url,
                error="; ".join(errors_fill),
                error_code=ErrorCode.PROVIDER_LAYOUT_CHANGED,
            )

        return FormFillResult(
            success=True,
            summary=_build_safe_summary(self.provider, params, filled),
            field_names=filled,
            target_url=page.url,
        )

    def submit_form(self, page) -> SubmitResult:
        """제출 버튼 클릭 — run_dev_reg 의 승인 확인 후에만 호출된다."""
        if not _has_element(page, _SUBMIT_BTN):
            return SubmitResult(
                success=False,
                result_summary="",
                error="제출 버튼을 찾을 수 없습니다",
                error_code=ErrorCode.SUBMIT_BUTTON_NOT_FOUND,
            )
        try:
            page.click(_SUBMIT_BTN)
            page.wait_for_load_state("networkidle")
            result_text = page.inner_text("body") or ""
            if "완료" in result_text or "success" in result_text.lower():
                return SubmitResult(success=True, result_summary="신청 완료")
            return SubmitResult(
                success=True,
                result_summary=f"제출 완료 (결과 확인 필요): {result_text[:200]}",
            )
        except Exception as e:  # noqa: BLE001 - 하이웍스 개발자 등록 폼 자동입력 스크립트 — 페이지 로드/필드 입력/제출 실패 시 에러코드가 담긴 실패 결과(dict)를 반환하거나 개별 필드 오류를 누적할 뿐, 결제·삭제·자격증명 노출 없음
            logger.error("하이웍스 submit_form 실패: %s", e)
            return SubmitResult(success=False, result_summary="", error=str(e))
