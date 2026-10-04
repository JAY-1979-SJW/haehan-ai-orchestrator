"""네이버 개발자 애플리케이션 등록 어댑터.

https://developers.naver.com/apps/#/register 앱 등록 폼 자동 입력.

공통 파라미터 → 네이버 DOM 선택자 매핑 (우선순위: name/id 기반):
  app_name         → input[name='applicationName']
  purpose          → textarea[name='description']
  service_url      → input[name='webServiceUrl']
  redirect_uri     → input[name='callbackUrl']
  requested_scopes → input[type='checkbox'][value='{scope}'] (목록)

submit 버튼 우선순위:
  1순위: button.btn-register  (class 기반 — 네이버 devcentner 관례)
  폴백:  button[type='submit'] (type 기반)

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

_REGISTER_URL = "https://developers.naver.com/apps/#/register"

# name/id 기반 선택자 (selector 우선순위 2순위)
_SELECTORS: dict[str, str] = {
    "app_name": "input[name='applicationName']",
    "purpose": "textarea[name='description']",
    "service_url": "input[name='webServiceUrl']",
    "redirect_uri": "input[name='callbackUrl']",
}

# 제출 버튼: class 기반(1순위) → type=submit 폴백
# 네이버 devcenter 의 btn-register 는 고유 class 이므로 우선 시도
_SUBMIT_BTN_SELECTORS = (
    "button.btn-register",
    "button[type='submit']",
)

# 로그인 리다이렉트 감지 URL 패턴
_LOGIN_HINTS = ("nid.naver.com/nidlogin", "nid.naver.com/login2", "/login")


def _fill_fields_and_scopes(page, params: dict, filled: list[str], errors_fill: list[str]) -> None:
    """앱 등록 폼 필드 입력 + scope 체크박스 선택 (filled/errors_fill 에 누적)."""
    for field_name, selector in _SELECTORS.items():
        value = params.get(field_name, "")
        if not value:
            continue
        try:
            page.fill(selector, str(value))
            filled.append(field_name)
        except Exception as e:  # noqa: BLE001 - 네이버 개발자센터 앱 등록 폼 자동입력 — 페이지이동/필드입력/체크박스/제출 실패 시 모두 error 필드를 채운 명시적 실패 결과(FormFillResult/SubmitResult)를 반환, 승인 없이 제출 진행 없음.
            errors_fill.append(f"{field_name}: {e}")
            logger.warning("네이버 폼 입력 실패 | field=%s | %s", field_name, e)

    scopes = params.get("requested_scopes", [])
    if isinstance(scopes, list):
        for scope in scopes:
            try:
                page.check(f"input[type='checkbox'][value='{scope}']")
                filled.append(f"scope:{scope}")
            except Exception as e:  # noqa: BLE001 - 네이버 개발자센터 앱 등록 폼 자동입력 — 페이지이동/필드입력/체크박스/제출 실패 시 모두 error 필드를 채운 명시적 실패 결과(FormFillResult/SubmitResult)를 반환, 승인 없이 제출 진행 없음.
                logger.warning("네이버 scope 체크 실패 | scope=%s | %s", scope, e)


class NaverDevRegAdapter(DevRegAdapterBase):
    """네이버 개발자센터 앱 등록 어댑터."""

    provider = "naver"
    action_type = "app_register"
    risk_level = "high"

    def fill_form(self, page, params: dict) -> FormFillResult:
        """앱 등록 폼 자동 입력 (제출 버튼 제외).

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
            filled = [k for k in _SELECTORS if params.get(k)]
            scopes = params.get("requested_scopes", [])
            if scopes:
                filled += [f"scope:{s}" for s in (scopes if isinstance(scopes, list) else [])]
            summary = _build_safe_summary(self.provider, params, filled)
            return FormFillResult(
                success=True,
                summary=f"[DRY RUN]\n{summary}",
                field_names=filled,
                target_url=_REGISTER_URL,
            )

        try:
            page.goto(_REGISTER_URL, wait_until="networkidle")
        except Exception as e:  # noqa: BLE001 - 네이버 개발자센터 앱 등록 폼 자동입력 — 페이지이동/필드입력/체크박스/제출 실패 시 모두 error 필드를 채운 명시적 실패 결과(FormFillResult/SubmitResult)를 반환, 승인 없이 제출 진행 없음.
            return FormFillResult(
                success=False,
                summary="",
                field_names=[],
                target_url=_REGISTER_URL,
                error=f"페이지 로드 실패: {e}",
                error_code=ErrorCode.PAGE_LOAD_FAILED,
            )

        if _is_login_redirect(page, _LOGIN_HINTS):
            return FormFillResult(
                success=False,
                summary="",
                field_names=[],
                target_url=_REGISTER_URL,
                error="로그인이 필요합니다",
                error_code=ErrorCode.LOGIN_REQUIRED,
            )

        filled: list[str] = []
        errors_fill: list[str] = []

        _fill_fields_and_scopes(page, params, filled, errors_fill)

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
        btn_sel = next((s for s in _SUBMIT_BTN_SELECTORS if _has_element(page, s)), None)
        if btn_sel is None:
            return SubmitResult(
                success=False,
                result_summary="",
                error="제출 버튼을 찾을 수 없습니다",
                error_code=ErrorCode.SUBMIT_BUTTON_NOT_FOUND,
            )
        try:
            page.click(btn_sel)
            page.wait_for_load_state("networkidle")
            result_text = page.inner_text("body") or ""
            if "등록" in result_text and ("완료" in result_text or "success" in result_text.lower()):
                return SubmitResult(success=True, result_summary="앱 등록 완료")
            return SubmitResult(
                success=True,
                result_summary=f"제출 완료 (결과 확인 필요): {result_text[:200]}",
            )
        except Exception as e:  # noqa: BLE001 - 네이버 개발자센터 앱 등록 폼 자동입력 — 페이지이동/필드입력/체크박스/제출 실패 시 모두 error 필드를 채운 명시적 실패 결과(FormFillResult/SubmitResult)를 반환, 승인 없이 제출 진행 없음.
            logger.error("네이버 submit_form 실패: %s", e)
            return SubmitResult(success=False, result_summary="", error=str(e))
