"""local_agent manual handoff observer (F-4F-2A 단계).

목적:
  - 홈택스/은행/공공기관처럼 메인 화면의 로그인 진입점이
    ``javascript:void(0)`` SPA 핸들러로 구성되어 있어 단순 URL ``page.goto``
    만으로는 로그인 모달/레이어가 렌더링되지 않는 경우, 사용자가 직접
    "로그인 버튼만" 클릭한 뒤 열린 화면을 read-only 로 한 번 캡처하기 위한
    별도 책임 모듈.
  - ``browser_observer.observe_public_browser_page`` 가 1회성 공개 페이지
    관찰이라면, 본 모듈은 사용자 수동 조작 → 코드 수동 캡처 흐름이라
    책임/정책이 다르다. 두 모듈을 섞으면 자동 클릭 정책이 흐려질 수 있어
    독립 모듈로 둔다.

본 모듈에서 절대 수행하지 않는 것:
  - ``page.click`` / ``page.fill`` / ``page.type`` / ``page.press``
  - ``page.keyboard.*`` / ``page.mouse.*``
  - ``page.set_input_files`` / ``page.select_option``
  - 폼 ``submit`` / 파일 다운로드 / 보안프로그램 자동 설치
  - ID / PW / 인증서 비밀번호 입력
  - secret 등록 시도
  - 쿠키 / storage_state / localStorage / sessionStorage / cookies 접근
  - ``--remote-debugging-port`` / ``--headless`` launch 옵션
  - 사용자 기존 브라우저 프로필 / 세션 디렉터리 사용 (fresh context only)
  - ``GOOGLE_PASSWORD`` / ``GOOGLE_LOGIN_PASSWORD`` / ``GOOGLE_COOKIE`` /
    ``GOOGLE_SESSION`` / ``GOOGLE_STORAGE_STATE`` / ``GOOGLE_OTP_SECRET``
    환경변수가 비어있지 않은 상태에서의 실행
  - input value / textarea value 수집

허용 Playwright API (read-only):
  - ``pw.chromium.launch(headless=False)``
  - ``browser.new_context()`` (fresh, no storage_state)
  - ``context.new_page()``
  - ``page.goto(url, wait_until=...)`` (Response 반환)
  - ``page.title()`` / ``page.url`` / ``page.content()``
  - ``response.status``

handoff 흐름:
  1. URL scheme + Google open-only 검증
  2. 금지 env 검증
  3. visible Playwright launch + fresh context
  4. ``page.goto(url, wait_until=...)``
  5. 호출자 (오케스트레이터/CLI) 가 사용자에게 미리 안내한다고 가정하고,
     ``handoff_seconds`` 동안 코드는 그저 sleep — 사용자가 화면에서
     로그인 버튼만 클릭한다.
  6. 대기 완료 후 한 번만 DOM/text/link/button/form 메타데이터를 읽고,
     ``browser_observer`` 와 동일한 sanitize 규칙을 적용해 결과 dict 빌드.
  7. ``extract_security_program_signals`` / ``extract_hometax_login_candidates``
     helper 가 import 가능하면 결과에 함께 반환.
  8. ``dwell_after_capture_seconds > 0`` 이면 결과 추출 후 잠깐 화면 유지
     (어떤 입력/클릭도 하지 않음).
  9. page/context/browser close.

반환 dict 핵심 필드:
  success / error_code / warnings / target_url / final_url_host_path /
  title / status_code / page_state / handoff (mode/handoff_seconds/
  instruction/captured_after_handoff) / text_excerpt / text_length /
  links_count / buttons_count / forms_count / inputs_count /
  links / buttons / forms / input_types / security_program_signals /
  hometax_login_candidates.

target_url / final_url 은 raw query/fragment 가 제거된 host+path 까지만
노출된다. 본 모듈은 어떤 경우에도 page 객체나 cookies / storage_state 를
외부로 반환하지 않는다.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Optional

from . import browser_launcher
from . import browser_observer as _bo
from .browser_reader import BrowserDependencyMissing, _safe_close
from .web_reader import analyze_html_structure, validate_url_for_readonly_open

logger = logging.getLogger(__name__)


# ─── 상수 / 정책 ─────────────────────────────────────────────────────────

_DEFAULT_TIMEOUT_MS = 15_000
_MIN_TIMEOUT_MS = 1_000
_MAX_TIMEOUT_MS = 60_000

_DEFAULT_MAX_TEXT_CHARS = 5_000
_MIN_MAX_TEXT_CHARS = 200
_MAX_MAX_TEXT_CHARS = 50_000

# observer 와 동일 set — networkidle 권장 (홈택스 SPA).
_DEFAULT_WAIT_UNTIL = "networkidle"
_ALLOWED_WAIT_UNTIL: tuple[str, ...] = (
    "commit", "domcontentloaded", "load", "networkidle",
)

# F-4G-3E — fresh Chromium 첫 hometax 접속에서 발생 가능한
# net::ERR_CONNECTION_RESET 대응. wait_until 변경이 아니라 warmup +
# retry 로 흡수한다. 진단 결과 (runs/local_agent/diagnostics/
# goto_diagnostic_*.json) 상 example/google 은 정상이고 hometax 만
# 첫 접속 reset 가능 → Chromium 미설치/일반 네트워크 문제 아님.
_DEFAULT_WARMUP_WAIT_UNTIL = "load"
_DEFAULT_GOTO_RETRIES = 1
_MIN_GOTO_RETRIES = 1
_MAX_GOTO_RETRIES = 5
_DEFAULT_GOTO_RETRY_DELAY_SECONDS = 1.0
_MIN_GOTO_RETRY_DELAY_SECONDS = 0.0
_MAX_GOTO_RETRY_DELAY_SECONDS = 10.0
# goto_timeout_ms 는 regular timeout_ms 와 별도로 더 큰 cap 을 허용.
# fresh hometax 첫 접속이 느릴 수 있어 90~180초까지 허용.
_MIN_GOTO_TIMEOUT_MS = _MIN_TIMEOUT_MS
_MAX_GOTO_TIMEOUT_MS = 180_000

# handoff_seconds — 사용자가 로그인 버튼을 클릭하기까지의 대기 시간.
# 무한 대기는 만들지 않는다. 사용자 정책상 60초 이내로 권장.
_DEFAULT_HANDOFF_SECONDS = 20
_MIN_HANDOFF_SECONDS = 0
_MAX_HANDOFF_SECONDS = 60

# dwell_after_capture_seconds — 결과 캡처 직후 close 전에 화면을 유지하는
# smoke/debug 전용 옵션. 0 이면 즉시 close. 음수 / 30 초과는 reject.
_DEFAULT_DWELL_AFTER_CAPTURE = 0
_MAX_DWELL_AFTER_CAPTURE = 30

_HANDOFF_INSTRUCTION = "click_login_only_no_credentials"

# F-4G-3 — post-login observe wrapper 용 별도 정책 상수.
# observe_after_user_ready 는 사용자가 "로그인 버튼만" 클릭이 아니라
# 로그인 + 인증서 + 보안프로그램 설치 + 메뉴 이동까지 모두 끝낸 *후* 화면을
# 한 번 캡처하는 시나리오다. 60 초로는 부족할 수 있어 한도를 180 초까지
# 허용한다 (최소 0 / 무한 대기는 만들지 않는다).
_DEFAULT_USER_READY_SECONDS = 60
_MIN_USER_READY_SECONDS = 0
_MAX_USER_READY_SECONDS = 180
_USER_READY_INSTRUCTION = "user_completes_login_and_navigation_no_credentials"
_DEFAULT_USER_READY_MAX_TEXT_CHARS = 10_000

# observer 와 동일 cap.
_LINKS_SAMPLE_CAP = _bo._LINKS_SAMPLE_CAP
_BUTTONS_SAMPLE_CAP = _bo._BUTTONS_SAMPLE_CAP
_FORMS_SAMPLE_CAP = _bo._FORMS_SAMPLE_CAP
_INPUTS_TYPE_SAMPLE_CAP = _bo._INPUTS_TYPE_SAMPLE_CAP

_FORBIDDEN_ENV_VARS: tuple[str, ...] = browser_launcher._FORBIDDEN_ENV_VARS


# ─── 결과 빌더 ───────────────────────────────────────────────────────────

def _empty_handoff_block(
    *,
    handoff_seconds: int,
    instruction: str = _HANDOFF_INSTRUCTION,
) -> dict[str, Any]:
    return {
        "mode": "manual",
        "handoff_seconds": int(handoff_seconds),
        "instruction": instruction,
        "captured_after_handoff": False,
    }


def _empty_result(
    *,
    target_url: str,
    error_code: str,
    warnings: list[str],
    handoff_seconds: int = _DEFAULT_HANDOFF_SECONDS,
    page_state: str = "unknown",
    instruction: str = _HANDOFF_INSTRUCTION,
    warmup_attempted: bool = False,
    warmup_success: bool = False,
    warmup_url: str = "",
    goto_attempts_used: int = 0,
) -> dict[str, Any]:
    """Playwright launch 이전/실패 시 반환. observer 와 동일한 키 셋에
    handoff / security_program_signals / hometax_login_candidates 와
    F-4G-3E warmup/retry 메타를 추가."""
    return {
        "success": False,
        "error_code": error_code,
        "warnings": list(warnings),
        "target_url": _bo._safe_target_url(target_url),
        "final_url_host_path": "",
        "title": "",
        "status_code": 0,
        "page_state": page_state,
        "handoff": _empty_handoff_block(
            handoff_seconds=handoff_seconds, instruction=instruction,
        ),
        "text_excerpt": "",
        "text_length": 0,
        "links_count": 0,
        "buttons_count": 0,
        "forms_count": 0,
        "inputs_count": 0,
        "links": [],
        "buttons": [],
        "forms": [],
        "input_types": [],
        "security_program_signals": None,
        "hometax_login_candidates": None,
        "warmup_attempted": bool(warmup_attempted),
        "warmup_success": bool(warmup_success),
        "warmup_url": warmup_url or "",
        "goto_attempts_used": int(goto_attempts_used),
    }


# ─── 외부 API ────────────────────────────────────────────────────────────

def observe_after_manual_handoff(
    url: str,
    *,
    site_policy: str = "auto",
    timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    wait_until: str = _DEFAULT_WAIT_UNTIL,
    handoff_seconds: int = _DEFAULT_HANDOFF_SECONDS,
    max_text_chars: int = _DEFAULT_MAX_TEXT_CHARS,
    dwell_after_capture_seconds: int = _DEFAULT_DWELL_AFTER_CAPTURE,
    _browser_factory: Optional[Callable[[], Any]] = None,
    _env: Optional[dict] = None,
    _sleep: Optional[Callable[[float], None]] = None,
) -> dict[str, Any]:
    """visible 브라우저를 띄운 뒤 사용자가 직접 "로그인 버튼만" 클릭하는 동안
    ``handoff_seconds`` 만큼 대기하고, 그 다음 read-only 로 현재 페이지를
    한 번만 관찰한다.

    파라미터:
      url:                            대상 URL.
      site_policy:                    추후 확장 자리 (현재 미사용).
      timeout_ms:                     ``page.goto`` 타임아웃 (1000~60000).
      wait_until:                     Playwright wait_until 화이트리스트.
      handoff_seconds:                사용자 수동 클릭 대기 시간 (0~60).
      max_text_chars:                 text_excerpt 길이 상한 (200~50000).
      dwell_after_capture_seconds:    캡처 후 close 까지 추가 유지 (0~30).
      _browser_factory / _env / _sleep:
                                      테스트 편의용 주입. None 이면 실제
                                      ``sync_playwright`` / ``os.environ`` /
                                      ``time.sleep`` 사용.

    절대 보장:
      - 본 함수는 어떤 경우에도 클릭/입력/키보드/마우스/다운로드/cookies/
        storage_state API 를 호출하지 않는다.
      - 페이지 객체 / 쿠키 / 스토리지 / HTML 원문은 결과에 포함되지 않는다.
    """
    eff_env = dict(os.environ) if _env is None else dict(_env)

    # 1) URL 안전성 (http/https + 공개 호스트).
    validation = validate_url_for_readonly_open(
        url or "", allow_private_network=False,
    )
    if not validation.get("ok"):
        return _empty_result(
            target_url=url or "",
            error_code=validation.get("error_code", "URL_INVALID"),
            warnings=[validation.get("error_code", "URL_INVALID").lower()],
            handoff_seconds=_clip_handoff_seconds_for_empty(handoff_seconds),
        )
    target_url = (url or "").strip()

    # 2) Google/YouTube open-only 정책 (F-2 와 동일).
    if browser_launcher.is_google_open_only_url(target_url):
        return _empty_result(
            target_url=target_url,
            error_code="GOOGLE_OPEN_ONLY",
            warnings=["google_open_only_use_open_local_browser"],
            handoff_seconds=_clip_handoff_seconds_for_empty(handoff_seconds),
        )

    # 3) 민감 환경변수 차단.
    forbidden_hits: list[str] = []
    for key in _FORBIDDEN_ENV_VARS:
        v = eff_env.get(key)
        if v is not None and str(v).strip() != "":
            forbidden_hits.append(f"forbidden_env_present:{key}")
    if forbidden_hits:
        return _empty_result(
            target_url=target_url,
            error_code="FORBIDDEN_ENV_PRESENT",
            warnings=forbidden_hits,
            handoff_seconds=_clip_handoff_seconds_for_empty(handoff_seconds),
        )

    # 4) 파라미터 정규화 / 검증.
    timeout_ms_v = _clip_int(
        timeout_ms, _MIN_TIMEOUT_MS, _MAX_TIMEOUT_MS, _DEFAULT_TIMEOUT_MS,
    )
    max_text_chars_v = _clip_int(
        max_text_chars, _MIN_MAX_TEXT_CHARS, _MAX_MAX_TEXT_CHARS,
        _DEFAULT_MAX_TEXT_CHARS,
    )

    if not isinstance(wait_until, str) or wait_until not in _ALLOWED_WAIT_UNTIL:
        return _empty_result(
            target_url=target_url,
            error_code="WAIT_UNTIL_INVALID",
            warnings=["wait_until_invalid"],
            handoff_seconds=_clip_handoff_seconds_for_empty(handoff_seconds),
        )
    wait_until_v = wait_until

    # bool 은 int 의 subclass — 명시 차단.
    if isinstance(handoff_seconds, bool) or \
            not isinstance(handoff_seconds, int):
        return _empty_result(
            target_url=target_url,
            error_code="HANDOFF_SECONDS_INVALID",
            warnings=["handoff_seconds_invalid"],
        )
    if handoff_seconds < _MIN_HANDOFF_SECONDS or \
            handoff_seconds > _MAX_HANDOFF_SECONDS:
        return _empty_result(
            target_url=target_url,
            error_code="HANDOFF_SECONDS_INVALID",
            warnings=["handoff_seconds_invalid"],
        )
    handoff_seconds_v = handoff_seconds

    if isinstance(dwell_after_capture_seconds, bool) or \
            not isinstance(dwell_after_capture_seconds, int):
        return _empty_result(
            target_url=target_url,
            error_code="DWELL_AFTER_CAPTURE_INVALID",
            warnings=["dwell_after_capture_invalid"],
            handoff_seconds=handoff_seconds_v,
        )
    if dwell_after_capture_seconds < 0 or \
            dwell_after_capture_seconds > _MAX_DWELL_AFTER_CAPTURE:
        return _empty_result(
            target_url=target_url,
            error_code="DWELL_AFTER_CAPTURE_INVALID",
            warnings=["dwell_after_capture_invalid"],
            handoff_seconds=handoff_seconds_v,
        )
    dwell_after_capture_v = dwell_after_capture_seconds

    sleep_fn = _sleep if _sleep is not None else time.sleep

    # 5) Playwright factory.
    factory = _browser_factory
    if factory is None:
        try:
            from playwright.sync_api import sync_playwright as _sync
        except ImportError:
            return _empty_result(
                target_url=target_url,
                error_code="BROWSER_DEPENDENCY_MISSING",
                warnings=["browser_dependency_missing"],
                handoff_seconds=handoff_seconds_v,
            )
        factory = _sync

    try:
        return _run_handoff_observation(
            factory=factory,
            target_url=target_url,
            timeout_ms=timeout_ms_v,
            wait_until=wait_until_v,
            handoff_seconds=handoff_seconds_v,
            max_text_chars=max_text_chars_v,
            dwell_after_capture=dwell_after_capture_v,
            sleep_fn=sleep_fn,
        )
    except BrowserDependencyMissing as e:
        return _empty_result(
            target_url=target_url,
            error_code="BROWSER_DEPENDENCY_MISSING",
            warnings=[f"browser_dependency_missing:{type(e).__name__}"],
            handoff_seconds=handoff_seconds_v,
        )
    except Exception as e:  # pragma: no cover - 실제 런타임 오류
        logger.exception("observe_after_manual_handoff failed")
        return _empty_result(
            target_url=target_url,
            error_code="BROWSER_OBSERVATION_FAILED",
            warnings=[f"observation_failed:{type(e).__name__}"],
            handoff_seconds=handoff_seconds_v,
        )


# ─── 내부 ─────────────────────────────────────────────────────────────────

def _run_handoff_observation(
    *,
    factory: Callable[[], Any],
    target_url: str,
    timeout_ms: int,
    wait_until: str,
    handoff_seconds: int,
    max_text_chars: int,
    dwell_after_capture: int,
    sleep_fn: Callable[[float], None],
    instruction: str = _HANDOFF_INSTRUCTION,
    warmup_url: Optional[str] = None,
    warmup_wait_until: str = _DEFAULT_WARMUP_WAIT_UNTIL,
    goto_retries: int = _DEFAULT_GOTO_RETRIES,
    goto_retry_delay_seconds: float = _DEFAULT_GOTO_RETRY_DELAY_SECONDS,
    extra_warnings: Optional[list[str]] = None,
) -> dict[str, Any]:
    warnings: list[str] = list(extra_warnings or [])
    launch_kwargs: dict[str, Any] = {"headless": False}
    warmup_attempted = False
    warmup_success = False
    goto_attempts_used = 0

    with factory() as pw:
        try:
            browser = pw.chromium.launch(**launch_kwargs)
        except Exception as e:  # pragma: no cover - 실제 런타임 오류
            logger.exception("browser launch failed")
            return _empty_result(
                target_url=target_url,
                error_code="BROWSER_OPEN_FAILED",
                warnings=warnings + [f"launch_failed:{type(e).__name__}"],
                handoff_seconds=handoff_seconds,
                instruction=instruction,
                warmup_attempted=warmup_attempted,
                warmup_success=warmup_success,
                warmup_url=warmup_url or "",
                goto_attempts_used=goto_attempts_used,
            )
        try:
            context = browser.new_context()
            try:
                page = context.new_page()
                try:
                    # ── F-4G-3E warmup goto (옵션) ─────────────────────
                    # 본 target_url 접속 전에 warmup_url 로 1회 navigate.
                    # 실패는 치명 오류로 처리하지 않는다.
                    if warmup_url:
                        warmup_attempted = True
                        try:
                            page.goto(
                                warmup_url,
                                timeout=timeout_ms,
                                wait_until=warmup_wait_until,
                            )
                            warmup_success = True
                        except Exception as e:
                            warnings.append(
                                f"warmup_failed:{type(e).__name__}",
                            )

                    # ── target_url goto with retry ────────────────────
                    response = None
                    last_error: Optional[Exception] = None
                    max_attempts = max(1, int(goto_retries))
                    for attempt in range(1, max_attempts + 1):
                        goto_attempts_used = attempt
                        try:
                            response = page.goto(
                                target_url,
                                timeout=timeout_ms,
                                wait_until=wait_until,
                            )
                            last_error = None
                            break
                        except Exception as e:
                            last_error = e
                            warnings.append(
                                f"goto_attempt_failed:{attempt}:"
                                f"{type(e).__name__}",
                            )
                            if attempt < max_attempts and \
                                    goto_retry_delay_seconds > 0:
                                try:
                                    sleep_fn(float(goto_retry_delay_seconds))
                                except Exception:  # pragma: no cover
                                    pass

                    if last_error is not None:
                        return _empty_result(
                            target_url=target_url,
                            error_code="GOTO_FAILED",
                            warnings=warnings,
                            handoff_seconds=handoff_seconds,
                            instruction=instruction,
                            warmup_attempted=warmup_attempted,
                            warmup_success=warmup_success,
                            warmup_url=warmup_url or "",
                            goto_attempts_used=goto_attempts_used,
                        )

                    # ── 사용자 수동 조작 대기 구간 ─────────────────────
                    # 본 sleep 동안 코드는 어떤 클릭/입력도 하지 않는다.
                    # 사용자가 직접 화면의 로그인 버튼만 클릭한다.
                    if handoff_seconds > 0:
                        try:
                            sleep_fn(handoff_seconds)
                        except Exception:  # pragma: no cover - sleep 자체 실패
                            warnings.append("handoff_sleep_failed")

                    status_code = _bo._safe_status(response)

                    try:
                        raw_title = page.title() or ""
                    except Exception:
                        raw_title = ""
                        warnings.append("title_unavailable")

                    try:
                        final_url_raw = page.url or ""
                    except Exception:
                        final_url_raw = ""
                        warnings.append("url_unavailable")

                    try:
                        html = page.content() or ""
                    except Exception:
                        html = ""
                        warnings.append("content_unavailable")
                    if not isinstance(html, str):
                        html = ""

                    structure = analyze_html_structure(
                        html=html,
                        base_url=final_url_raw or target_url,
                    )

                    result = _build_handoff_result(
                        target_url=target_url,
                        title=raw_title,
                        final_url=final_url_raw,
                        status_code=status_code,
                        structure=structure,
                        max_text_chars=max_text_chars,
                        handoff_seconds=handoff_seconds,
                        warnings=warnings,
                        instruction=instruction,
                        warmup_attempted=warmup_attempted,
                        warmup_success=warmup_success,
                        warmup_url=warmup_url or "",
                        goto_attempts_used=goto_attempts_used,
                    )

                    # 결과 dict 만으로 helper 호출 — 브라우저 미접촉.
                    result["security_program_signals"] = \
                        _try_security_program_signals(result)
                    result["hometax_login_candidates"] = \
                        _try_hometax_candidates(result)

                    if dwell_after_capture > 0:
                        try:
                            sleep_fn(dwell_after_capture)
                        except Exception:  # pragma: no cover
                            pass
                    return result
                finally:
                    _safe_close(page)
            finally:
                _safe_close(context)
        finally:
            _safe_close(browser)


def _build_handoff_result(
    *,
    target_url: str,
    title: str,
    final_url: str,
    status_code: int,
    structure: dict[str, Any],
    max_text_chars: int,
    handoff_seconds: int,
    warnings: list[str],
    instruction: str = _HANDOFF_INSTRUCTION,
    warmup_attempted: bool = False,
    warmup_success: bool = False,
    warmup_url: str = "",
    goto_attempts_used: int = 0,
) -> dict[str, Any]:
    title_safe = (title or "")[:300]
    final_host_path = (
        _bo._url_host_path(final_url) or _bo._url_host_path(target_url)
    )

    raw_links = list(structure.get("links") or [])
    raw_buttons = list(structure.get("buttons") or [])
    raw_forms = list(structure.get("forms") or [])
    raw_inputs = list(structure.get("inputs") or [])

    links_sample = _bo._sanitize_links(raw_links)[:_LINKS_SAMPLE_CAP]
    buttons_sample = _bo._sanitize_buttons(raw_buttons)[:_BUTTONS_SAMPLE_CAP]
    forms_sample = _bo._sanitize_forms(raw_forms)[:_FORMS_SAMPLE_CAP]
    input_types = _bo._sanitize_input_types(raw_inputs)[:_INPUTS_TYPE_SAMPLE_CAP]

    text_blob = _bo._build_text_blob(structure)
    text_length = len(text_blob)
    text_excerpt = text_blob[:max_text_chars]

    page_state = _bo._classify_page_state(
        target_url=target_url,
        final_url=final_url,
        title=title_safe,
        status_code=status_code,
        text_blob=text_blob,
        structure=structure,
        forms_sample=forms_sample,
    )

    success = _bo._is_success_status(status_code)
    error_code = "" if success else _bo._error_code_from_status(status_code)

    return {
        "success": bool(success),
        "error_code": error_code,
        "warnings": list(warnings),
        "target_url": _bo._safe_target_url(target_url),
        "final_url_host_path": final_host_path,
        "title": title_safe,
        "status_code": int(status_code),
        "page_state": page_state,
        "handoff": {
            "mode": "manual",
            "handoff_seconds": int(handoff_seconds),
            "instruction": instruction,
            "captured_after_handoff": True,
        },
        "text_excerpt": text_excerpt,
        "text_length": int(text_length),
        "links_count": int(len(raw_links)),
        "buttons_count": int(len(raw_buttons)),
        "forms_count": int(len(raw_forms)),
        "inputs_count": int(len(raw_inputs)),
        "links": links_sample,
        "buttons": buttons_sample,
        "forms": forms_sample,
        "input_types": input_types,
        "security_program_signals": None,
        "hometax_login_candidates": None,
        "warmup_attempted": bool(warmup_attempted),
        "warmup_success": bool(warmup_success),
        "warmup_url": warmup_url or "",
        "goto_attempts_used": int(goto_attempts_used),
    }


def _try_security_program_signals(result: dict[str, Any]) -> Any:
    """browser_observer 의 helper 가 import 가능하면 호출해 결과에 부착.
    어떤 경우에도 브라우저/네트워크/스토리지 접촉 없이 dict 만 다룬다."""
    try:
        return _bo.extract_security_program_signals(result)
    except Exception:
        logger.debug("extract_security_program_signals failed", exc_info=True)
        return None


def _try_hometax_candidates(result: dict[str, Any]) -> Any:
    """홈택스 호스트인 경우에만 candidate helper 호출. 다른 호스트면 None.

    helper 자체는 dict-in/dict-out 이지만, 결과가 홈택스 외 사이트의
    "로그인 후보" 로 오해되지 않도록 호스트 게이팅을 둔다.
    """
    try:
        from .site_adapters import hometax as _hometax_adapter
    except Exception:
        logger.debug("hometax adapter import failed", exc_info=True)
        return None
    # final_url_host_path 는 host+path 형태이므로 첫 "/" 앞 host 부분만 추출.
    # 빈 문자열이면 target_url 의 host 를 fallback 으로 사용한다.
    final_host_path = result.get("final_url_host_path") or ""
    target_url = result.get("target_url") or ""
    host_only = final_host_path.split("/", 1)[0] if final_host_path else ""
    if not host_only:
        host_only = target_url
    if not _hometax_adapter.is_hometax_host(host_only):
        return None
    try:
        return _hometax_adapter.extract_hometax_login_candidates(result)
    except Exception:
        logger.debug("extract_hometax_login_candidates failed", exc_info=True)
        return None


# ─── helpers ─────────────────────────────────────────────────────────────

def _clip_int(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _clip_float(value: Any, lo: float, hi: float, default: float) -> float:
    if isinstance(value, bool):
        return float(default)
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float(default)
    if v < lo:
        return float(lo)
    if v > hi:
        return float(hi)
    return float(v)


def _clip_handoff_seconds_for_empty(handoff_seconds: Any) -> int:
    """_empty_result 에 표기할 handoff_seconds 정규화. 잘못된 입력은 기본값."""
    if isinstance(handoff_seconds, bool):
        return _DEFAULT_HANDOFF_SECONDS
    if not isinstance(handoff_seconds, int):
        return _DEFAULT_HANDOFF_SECONDS
    if handoff_seconds < _MIN_HANDOFF_SECONDS or \
            handoff_seconds > _MAX_HANDOFF_SECONDS:
        return _DEFAULT_HANDOFF_SECONDS
    return handoff_seconds


# ─── F-4G-3 — post-login observe wrapper ────────────────────────────────

def observe_after_user_ready(
    url: str,
    *,
    site_policy: str = "auto",
    timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    wait_until: str = _DEFAULT_WAIT_UNTIL,
    user_ready_seconds: int = _DEFAULT_USER_READY_SECONDS,
    max_text_chars: int = _DEFAULT_USER_READY_MAX_TEXT_CHARS,
    dwell_after_capture_seconds: int = _DEFAULT_DWELL_AFTER_CAPTURE,
    warmup_url: Optional[str] = None,
    warmup_wait_until: str = _DEFAULT_WARMUP_WAIT_UNTIL,
    goto_retries: int = _DEFAULT_GOTO_RETRIES,
    goto_retry_delay_seconds: float = _DEFAULT_GOTO_RETRY_DELAY_SECONDS,
    goto_timeout_ms: Optional[int] = None,
    _browser_factory: Optional[Callable[[], Any]] = None,
    _env: Optional[dict] = None,
    _sleep: Optional[Callable[[float], None]] = None,
) -> dict[str, Any]:
    """visible 브라우저를 띄운 뒤 사용자가 로그인 + 인증서 + 보안프로그램
    설치 + 메뉴 이동까지 모두 직접 끝낼 동안 ``user_ready_seconds`` 만큼
    대기하고, 그 다음 read-only 로 현재 페이지를 한 번 관찰한다.

    ``observe_after_manual_handoff`` 와 동일한 정책 (자동 클릭/입력/쿠키/
    스토리지 절대 금지) 위에서 동작하지만, 시나리오/한도/instruction 만
    다르다:

      - ``user_ready_seconds`` 한도: 0~180 (manual_handoff 의 60 보다 김).
      - 기본 ``max_text_chars`` 10_000 (handoff 5_000 보다 큼).
      - ``handoff.instruction`` =
        ``"user_completes_login_and_navigation_no_credentials"``.

    절대 보장 (manual_handoff 와 동일):
      - 본 함수는 어떤 경우에도 클릭/입력/키보드/마우스/다운로드/cookies/
        storage_state API 를 호출하지 않는다.
      - 페이지 객체 / 쿠키 / 스토리지 / HTML 원문은 결과에 포함되지 않는다.
    """
    eff_env = dict(os.environ) if _env is None else dict(_env)

    # 1) URL 안전성.
    validation = validate_url_for_readonly_open(
        url or "", allow_private_network=False,
    )
    if not validation.get("ok"):
        return _empty_result(
            target_url=url or "",
            error_code=validation.get("error_code", "URL_INVALID"),
            warnings=[validation.get("error_code", "URL_INVALID").lower()],
            handoff_seconds=_clip_user_ready_seconds_for_empty(
                user_ready_seconds,
            ),
            instruction=_USER_READY_INSTRUCTION,
        )
    target_url = (url or "").strip()

    # 2) Google open-only 정책.
    if browser_launcher.is_google_open_only_url(target_url):
        return _empty_result(
            target_url=target_url,
            error_code="GOOGLE_OPEN_ONLY",
            warnings=["google_open_only_use_open_local_browser"],
            handoff_seconds=_clip_user_ready_seconds_for_empty(
                user_ready_seconds,
            ),
            instruction=_USER_READY_INSTRUCTION,
        )

    # 3) 민감 환경변수 차단.
    forbidden_hits: list[str] = []
    for key in _FORBIDDEN_ENV_VARS:
        v = eff_env.get(key)
        if v is not None and str(v).strip() != "":
            forbidden_hits.append(f"forbidden_env_present:{key}")
    if forbidden_hits:
        return _empty_result(
            target_url=target_url,
            error_code="FORBIDDEN_ENV_PRESENT",
            warnings=forbidden_hits,
            handoff_seconds=_clip_user_ready_seconds_for_empty(
                user_ready_seconds,
            ),
            instruction=_USER_READY_INSTRUCTION,
        )

    # 4) 파라미터 정규화 / 검증.
    timeout_ms_v = _clip_int(
        timeout_ms, _MIN_TIMEOUT_MS, _MAX_TIMEOUT_MS, _DEFAULT_TIMEOUT_MS,
    )
    max_text_chars_v = _clip_int(
        max_text_chars, _MIN_MAX_TEXT_CHARS, _MAX_MAX_TEXT_CHARS,
        _DEFAULT_USER_READY_MAX_TEXT_CHARS,
    )

    if not isinstance(wait_until, str) or wait_until not in _ALLOWED_WAIT_UNTIL:
        return _empty_result(
            target_url=target_url,
            error_code="WAIT_UNTIL_INVALID",
            warnings=["wait_until_invalid"],
            handoff_seconds=_clip_user_ready_seconds_for_empty(
                user_ready_seconds,
            ),
            instruction=_USER_READY_INSTRUCTION,
        )
    wait_until_v = wait_until

    # bool 은 int 의 subclass — 명시 차단.
    if isinstance(user_ready_seconds, bool) or \
            not isinstance(user_ready_seconds, int):
        return _empty_result(
            target_url=target_url,
            error_code="USER_READY_SECONDS_INVALID",
            warnings=["user_ready_seconds_invalid"],
            instruction=_USER_READY_INSTRUCTION,
        )
    if user_ready_seconds < _MIN_USER_READY_SECONDS or \
            user_ready_seconds > _MAX_USER_READY_SECONDS:
        return _empty_result(
            target_url=target_url,
            error_code="USER_READY_SECONDS_INVALID",
            warnings=["user_ready_seconds_invalid"],
            instruction=_USER_READY_INSTRUCTION,
        )
    user_ready_seconds_v = user_ready_seconds

    if isinstance(dwell_after_capture_seconds, bool) or \
            not isinstance(dwell_after_capture_seconds, int):
        return _empty_result(
            target_url=target_url,
            error_code="DWELL_AFTER_CAPTURE_INVALID",
            warnings=["dwell_after_capture_invalid"],
            handoff_seconds=user_ready_seconds_v,
            instruction=_USER_READY_INSTRUCTION,
        )
    if dwell_after_capture_seconds < 0 or \
            dwell_after_capture_seconds > _MAX_DWELL_AFTER_CAPTURE:
        return _empty_result(
            target_url=target_url,
            error_code="DWELL_AFTER_CAPTURE_INVALID",
            warnings=["dwell_after_capture_invalid"],
            handoff_seconds=user_ready_seconds_v,
            instruction=_USER_READY_INSTRUCTION,
        )
    dwell_after_capture_v = dwell_after_capture_seconds

    # 4-1) F-4G-3E warmup / retry 옵션 정규화. 잘못된 값은 default 로
    # 클립하고 warning 을 남긴다 (치명 오류 아님 — backward compat 유지).
    pre_warnings: list[str] = []

    if warmup_url is None:
        warmup_url_v: Optional[str] = None
    elif isinstance(warmup_url, str) and warmup_url.strip():
        warmup_validation = validate_url_for_readonly_open(
            warmup_url.strip(), allow_private_network=False,
        )
        if warmup_validation.get("ok"):
            warmup_url_v = warmup_url.strip()
        else:
            warmup_url_v = None
            pre_warnings.append("warmup_url_invalid")
    else:
        warmup_url_v = None
        pre_warnings.append("warmup_url_invalid")

    if not isinstance(warmup_wait_until, str) or \
            warmup_wait_until not in _ALLOWED_WAIT_UNTIL:
        warmup_wait_until_v = _DEFAULT_WARMUP_WAIT_UNTIL
        pre_warnings.append("warmup_wait_until_invalid")
    else:
        warmup_wait_until_v = warmup_wait_until

    goto_retries_v = _clip_int(
        goto_retries, _MIN_GOTO_RETRIES, _MAX_GOTO_RETRIES,
        _DEFAULT_GOTO_RETRIES,
    )
    if isinstance(goto_retries, bool) or not isinstance(goto_retries, int):
        # _clip_int returned default, but bool/non-int is suspicious — record.
        pre_warnings.append("goto_retries_invalid")

    goto_retry_delay_v = _clip_float(
        goto_retry_delay_seconds,
        _MIN_GOTO_RETRY_DELAY_SECONDS,
        _MAX_GOTO_RETRY_DELAY_SECONDS,
        _DEFAULT_GOTO_RETRY_DELAY_SECONDS,
    )

    if goto_timeout_ms is None:
        goto_timeout_ms_v = timeout_ms_v
    else:
        goto_timeout_ms_v = _clip_int(
            goto_timeout_ms,
            _MIN_GOTO_TIMEOUT_MS,
            _MAX_GOTO_TIMEOUT_MS,
            timeout_ms_v,
        )

    sleep_fn = _sleep if _sleep is not None else time.sleep

    # 5) Playwright factory.
    factory = _browser_factory
    if factory is None:
        try:
            from playwright.sync_api import sync_playwright as _sync
        except ImportError:
            return _empty_result(
                target_url=target_url,
                error_code="BROWSER_DEPENDENCY_MISSING",
                warnings=["browser_dependency_missing"] + pre_warnings,
                handoff_seconds=user_ready_seconds_v,
                instruction=_USER_READY_INSTRUCTION,
            )
        factory = _sync

    try:
        return _run_handoff_observation(
            factory=factory,
            target_url=target_url,
            timeout_ms=goto_timeout_ms_v,
            wait_until=wait_until_v,
            handoff_seconds=user_ready_seconds_v,
            max_text_chars=max_text_chars_v,
            dwell_after_capture=dwell_after_capture_v,
            sleep_fn=sleep_fn,
            instruction=_USER_READY_INSTRUCTION,
            warmup_url=warmup_url_v,
            warmup_wait_until=warmup_wait_until_v,
            goto_retries=goto_retries_v,
            goto_retry_delay_seconds=goto_retry_delay_v,
            extra_warnings=pre_warnings,
        )
    except BrowserDependencyMissing as e:
        return _empty_result(
            target_url=target_url,
            error_code="BROWSER_DEPENDENCY_MISSING",
            warnings=(
                [f"browser_dependency_missing:{type(e).__name__}"]
                + pre_warnings
            ),
            handoff_seconds=user_ready_seconds_v,
            instruction=_USER_READY_INSTRUCTION,
        )
    except Exception as e:  # pragma: no cover - 실제 런타임 오류
        logger.exception("observe_after_user_ready failed")
        return _empty_result(
            target_url=target_url,
            error_code="BROWSER_OBSERVATION_FAILED",
            warnings=(
                [f"observation_failed:{type(e).__name__}"] + pre_warnings
            ),
            handoff_seconds=user_ready_seconds_v,
            instruction=_USER_READY_INSTRUCTION,
        )


def _clip_user_ready_seconds_for_empty(user_ready_seconds: Any) -> int:
    """_empty_result 에 표기할 user_ready_seconds 정규화."""
    if isinstance(user_ready_seconds, bool):
        return _DEFAULT_USER_READY_SECONDS
    if not isinstance(user_ready_seconds, int):
        return _DEFAULT_USER_READY_SECONDS
    if user_ready_seconds < _MIN_USER_READY_SECONDS or \
            user_ready_seconds > _MAX_USER_READY_SECONDS:
        return _DEFAULT_USER_READY_SECONDS
    return user_ready_seconds


__all__ = [
    "observe_after_manual_handoff",
    "observe_after_user_ready",
]
