"""local_agent 수동 로그인 확인 모드 (Stage 3 smoke probe).

실제 브라우저를 ``headless=False`` 로 열어 지정 URL 에 접속한 뒤, 사용자가
직접 로그인하는 동안 ``page.url`` / ``page.title`` / ``page.content`` 만
주기적으로 read-only 로 관찰해 "로그인 완료로 보이는 화면 변화" 가 발생
했는지 추정한다. 반환 dict 는 HTML 원문 전체/쿠키/세션/password 값을
포함하지 않는다.

절대 수행하지 않는 것:
  - 아이디/비밀번호 자동 입력 (page.fill / page.type / page.press)
  - 클릭/제출/파일업로드 (page.click / page.select_option / page.set_input_files)
  - evaluate 로 자바스크립트 주입
  - 쿠키 / storage_state / localStorage / sessionStorage 수집
  - password / hidden input value 수집
  - screenshot 저장

가시성/수동 확인 옵션:
  - ``require_visible_confirm``: 초기 관찰 뒤, 사용자가 실제 브라우저 창을
    봤다고 Enter 를 누르기 전까지 polling 루프로 넘어가지 않는다.
  - ``require_user_login_confirm``: 구조적 근거만으로 login_completed_hint=
    True 를 단정하지 않는다. 사용자가 Enter 로 확인해야 한다.
  - ``keep_open``: 종료 직전 사용자가 Enter 를 누를 때까지 브라우저를
    닫지 않는다.
  - ``browser_channel``: ``chromium`` / ``chrome`` / ``msedge`` 중 선택.

테스트 편의를 위해 ``_browser_factory``, ``_clock``, ``_input_reader`` 를
주입할 수 있다. None 이면 실제 ``playwright.sync_api.sync_playwright`` /
``time`` / ``builtins.input`` 이 사용된다.
"""

from __future__ import annotations

import logging
import time as _time_default
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from core.agent_runtime.browser.browser_reader import BrowserDependencyMissing, _detect_login_required, _safe_close
from core.agent_runtime.browser.web_reader import analyze_html_structure, validate_url_for_readonly_open
from scripts.browser.session.browser_sandbox_gate import assert_browser_launch_allowed

logger = logging.getLogger(__name__)


_ALLOWED_WAIT_UNTIL: frozenset[str] = frozenset(
    {
        "domcontentloaded",
        "load",
        "networkidle",
        "commit",
    }
)

_ALLOWED_BROWSER_CHANNELS: frozenset[str] = frozenset(
    {
        "chromium",
        "chrome",
        "msedge",
    }
)

_MIN_WAIT_SECONDS = 1
_MAX_WAIT_SECONDS = 600
_MIN_POLL_SECONDS = 1
_MAX_POLL_SECONDS = 30
_DEFAULT_MAX_HTML = 500_000
_MAX_HTML_CAP = 2_000_000
_MIN_SLOW_MO_MS = 0
_MAX_SLOW_MO_MS = 2000
_MIN_VIEWPORT = 200
_MAX_VIEWPORT = 4096

_VISIBLE_CONFIRM_PROMPT = (
    "\n[manual-login-probe] 브라우저 창이 실제 화면에 보이면 Enter를 누르세요.\n보이지 않으면 Ctrl+C로 중단하세요.\n> "
)
_USER_LOGIN_CONFIRM_PROMPT = (
    "\n[manual-login-probe] 로그인이 완료된 화면이 실제로 보이면 Enter 를,\n아직 아니면 n + Enter 를 누르세요.\n> "
)
_KEEP_OPEN_PROMPT = "\n[manual-login-probe] 브라우저를 닫으려면 Enter 를 누르세요.\n> "


def probe_manual_login_flow(  # noqa: PLR0913 - 공개 API keyword-only 시그니처 유지(호출부·테스트 다수)
    url: str,
    *,
    wait_seconds: int = 120,
    poll_interval_seconds: int = 3,
    success_url_contains: list[str] | None = None,
    success_text_hints: list[str] | None = None,
    allowed_hosts: list[str] | None = None,
    allow_private_network: bool = False,
    max_html_chars: int = _DEFAULT_MAX_HTML,
    wait_until: str = "domcontentloaded",
    goto_timeout_ms: int = 15000,
    browser_channel: str | None = None,
    require_visible_confirm: bool = False,
    require_user_login_confirm: bool = False,
    keep_open: bool = False,
    viewport: dict[str, int] | None = None,
    slow_mo_ms: int = 0,
    _browser_factory: Callable[[], Any] | None = None,
    _clock: Any | None = None,
    _input_reader: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """수동 로그인 확인 모드. 사용자가 직접 로그인하는 동안 read-only 관찰.

    어떤 경우에도 ID/PW 자동 입력, 클릭, 쿠키/스토리지 수집을 수행하지
    않는다. 구조적 근거 (password input 사라짐 / URL 이동 /
    login_required_hint 해소 / success_text_hints 관찰) 또는 사용자의
    명시적 Enter (require_user_login_confirm=True) 가 있을 때만
    ``login_completed_hint=True`` 로 판정한다.

    success_url_match 단독으로는 ``login_completed_hint=True`` 로 판정하지
    않으며, 초기 URL 이 이미 success 토큰을 포함하고 있고 password input 이
    없으면 ``login_state_hint="already_logged_in_or_public_page"`` 로 보고한다.
    """
    # 1) URL 안전성 (http/https + 공개 호스트).
    validation = validate_url_for_readonly_open(
        url,
        allow_private_network=allow_private_network,
    )
    if not validation.get("ok"):
        return _err(
            url=url,
            error_code=validation.get("error_code", "URL_INVALID"),
            reason=validation.get("reason", "url validation failed"),
        )

    # 2) allowed_hosts 화이트리스트 검사.
    allowed = _normalize_allowed_hosts(allowed_hosts)
    host = validation.get("host", "")
    if allowed is not None and not _host_allowed(host, allowed):
        return _err(
            url=url,
            error_code="HOST_NOT_ALLOWED",
            reason=f"host not in allowed_hosts: {host}",
        )

    # 3) 파라미터 정규화.
    if wait_until not in _ALLOWED_WAIT_UNTIL:
        wait_until = "domcontentloaded"
    wait_seconds = _clip_int(
        wait_seconds,
        _MIN_WAIT_SECONDS,
        _MAX_WAIT_SECONDS,
        120,
    )
    poll_interval_seconds = _clip_int(
        poll_interval_seconds,
        _MIN_POLL_SECONDS,
        _MAX_POLL_SECONDS,
        3,
    )
    if poll_interval_seconds > wait_seconds:
        poll_interval_seconds = wait_seconds
    max_html_chars = _clip_int(
        max_html_chars,
        1000,
        _MAX_HTML_CAP,
        _DEFAULT_MAX_HTML,
    )
    goto_timeout_ms = _clip_int(goto_timeout_ms, 1000, 60000, 15000)
    slow_mo_ms = _clip_int(slow_mo_ms, _MIN_SLOW_MO_MS, _MAX_SLOW_MO_MS, 0)

    channel = _normalize_browser_channel(browser_channel)
    if browser_channel is not None and channel is None:
        return _err(
            url=url,
            error_code="BROWSER_CHANNEL_INVALID",
            reason=(f"unknown browser_channel: {browser_channel!r} — allowed: chromium / chrome / msedge"),
        )

    viewport_norm = _normalize_viewport(viewport)

    success_urls = _normalize_str_list(success_url_contains)
    success_texts = _normalize_str_list(success_text_hints)

    time_mod = _clock or _time_default
    input_reader = _input_reader if _input_reader is not None else input

    factory = _browser_factory
    if factory is None:
        assert_browser_launch_allowed(component="core.agent_runtime.browser.browser_login_probe", action="playwright_launch")
        try:
            from playwright.sync_api import sync_playwright as _sync_playwright
        except ImportError:
            return _err(
                url=url,
                error_code="BROWSER_DEPENDENCY_MISSING",
                reason="playwright not installed: pip install playwright",
            )
        factory = _sync_playwright

    warnings: list[str] = []

    try:
        return _run_probe(
            factory=factory,
            time_mod=time_mod,
            input_reader=input_reader,
            url=url,
            wait_until=wait_until,
            goto_timeout_ms=goto_timeout_ms,
            wait_seconds=wait_seconds,
            poll_interval_seconds=poll_interval_seconds,
            max_html_chars=max_html_chars,
            success_urls=success_urls,
            success_texts=success_texts,
            browser_channel=channel,
            slow_mo_ms=slow_mo_ms,
            viewport=viewport_norm,
            require_visible_confirm=bool(require_visible_confirm),
            require_user_login_confirm=bool(require_user_login_confirm),
            keep_open=bool(keep_open),
            warnings=warnings,
        )
    except BrowserDependencyMissing as e:
        return _err(
            url=url,
            error_code="BROWSER_DEPENDENCY_MISSING",
            reason=str(e)[:200],
        )
    except Exception as e:  # pragma: no cover - 실제 환경 오류
        logger.exception("manual login probe failed")
        return _err(
            url=url,
            error_code="BROWSER_OPEN_FAILED",
            reason=str(e)[:200],
        )


# ── 내부 ────────────────────────────────────────────────────────────────


def _run_probe(  # noqa: PLR0913 - keyword-only 내부 함수, 호출 1곳(probe_manual_login_flow)
    *,
    factory: Callable[[], Any],
    time_mod: Any,
    input_reader: Callable[[str], str],
    url: str,
    wait_until: str,
    goto_timeout_ms: int,
    wait_seconds: int,
    poll_interval_seconds: int,
    max_html_chars: int,
    success_urls: list[str],
    success_texts: list[str],
    browser_channel: str | None,
    slow_mo_ms: int,
    viewport: dict[str, int] | None,
    require_visible_confirm: bool,
    require_user_login_confirm: bool,
    keep_open: bool,
    warnings: list[str],
) -> dict[str, Any]:
    launch_kwargs = _build_launch_kwargs(slow_mo_ms, browser_channel)

    context_kwargs: dict[str, Any] = {}
    if viewport:
        context_kwargs["viewport"] = dict(viewport)

    with factory() as pw:
        try:
            browser = pw.chromium.launch(**launch_kwargs)
        except Exception as e:  # pragma: no cover - 실제 채널 미설치 환경 오류
            logger.exception("browser launch failed")
            code = (
                "BROWSER_CHANNEL_NOT_AVAILABLE"
                if browser_channel and browser_channel != "chromium"
                else "BROWSER_OPEN_FAILED"
            )
            return _err(url=url, error_code=code, reason=str(e)[:200])
        try:
            context = browser.new_context(**context_kwargs)
            try:
                page = context.new_page()
                try:
                    page.goto(
                        url,
                        wait_until=wait_until,
                        timeout=goto_timeout_ms,
                    )

                    # 사용자 화면에 실제로 노출되도록 bring_to_front 시도
                    # (best-effort — 미지원 브라우저/버전에서는 조용히 skip).
                    _safe_bring_to_front(page)

                    initial = _observe(page, max_html_chars=max_html_chars)

                    visible_confirmed_by_user = False
                    if require_visible_confirm:
                        try:
                            input_reader(_VISIBLE_CONFIRM_PROMPT)
                            visible_confirmed_by_user = True
                        except (KeyboardInterrupt, EOFError):
                            return _build_canceled_result(
                                url=url,
                                initial=initial,
                                warnings=warnings,
                                success_urls=success_urls,
                            )

                    # 4) 관찰 루프.
                    last_obs, completed_reasons = _poll_for_completion(
                        page,
                        time_mod,
                        initial,
                        (wait_seconds, poll_interval_seconds, max_html_chars),
                        (success_urls, success_texts),
                    )

                    # 5) require_user_login_confirm 이면 사용자 Enter 수신.
                    login_confirmed_by_user = False
                    if require_user_login_confirm:
                        login_confirmed_by_user = _ask_user_login_confirm(
                            input_reader,
                            completed_reasons,
                        )

                    # 6) 상태 분류.
                    initial_is_already_logged_in = _initial_is_already_logged_in(
                        initial=initial,
                        success_urls=success_urls,
                    )
                    login_state_hint, login_completed_hint = _classify_login(
                        initial=initial,
                        completion_reasons=completed_reasons,
                        initial_is_already_logged_in=(initial_is_already_logged_in),
                        require_user_login_confirm=require_user_login_confirm,
                        login_confirmed_by_user=login_confirmed_by_user,
                    )

                    # 7) 다중 탭 스캔 (measurement gap 보완).
                    #    Studio/OAuth flow 가 window.open/팝업으로 target 페이지를
                    #    별도 탭에 열었을 경우, 단일 `page` 기준으로는 놓친다.
                    #    context.pages 전수 스캔으로 각 탭의 url/title 을
                    #    read-only 로만 수집해 집계한다. fake context 에서는
                    #    `pages` 속성이 없으므로 getattr default=None 로 안전
                    #    fallback 된다.
                    pages_observed_count, success_url_across_pages = _scan_pages_and_warn(
                        context,
                        success_urls,
                        login_confirmed_by_user,
                        warnings,
                    )

                    # 8) keep_open 시 닫기 전에 사용자 Enter 를 기다림.
                    if keep_open:
                        with suppress(KeyboardInterrupt, EOFError):
                            input_reader(_KEEP_OPEN_PROMPT)

                    return _build_result(
                        url=url,
                        initial=initial,
                        last_obs=last_obs,
                        completed_reasons=completed_reasons,
                        login_state_hint=login_state_hint,
                        login_completed_hint=login_completed_hint,
                        visible_confirmed_by_user=visible_confirmed_by_user,
                        login_confirmed_by_user=login_confirmed_by_user,
                        pages_observed_count=pages_observed_count,
                        success_url_observed_across_pages=(success_url_across_pages),
                        warnings=warnings,
                    )
                finally:
                    _safe_close(page)
            finally:
                _safe_close(context)
        finally:
            _safe_close(browser)


def _build_launch_kwargs(slow_mo_ms: int, browser_channel: str | None) -> dict[str, Any]:
    launch_kwargs: dict[str, Any] = {"headless": False}
    if slow_mo_ms > 0:
        launch_kwargs["slow_mo"] = slow_mo_ms
    if browser_channel and browser_channel != "chromium":
        launch_kwargs["channel"] = browser_channel
    return launch_kwargs


def _poll_for_completion(
    page: Any,
    time_mod: Any,
    initial: dict[str, Any],
    limits: tuple[int, int, int],
    success: tuple[list[str], list[str]],
) -> tuple[dict[str, Any], list[str]]:
    """관찰 루프. limits=(wait_seconds, poll_interval_seconds, max_html_chars), success=(urls, texts)."""
    wait_seconds, poll_interval_seconds, max_html_chars = limits
    success_urls, success_texts = success
    deadline_ts = time_mod.monotonic() + wait_seconds
    last_obs = initial
    completed_reasons: list[str] = []

    while True:
        now = time_mod.monotonic()
        if now >= deadline_ts:
            break
        sleep_for = min(
            poll_interval_seconds,
            deadline_ts - now,
        )
        if sleep_for > 0:
            time_mod.sleep(sleep_for)
        last_obs = _observe(
            page,
            max_html_chars=max_html_chars,
        )
        completed_reasons = _detect_completion(
            initial=initial,
            current=last_obs,
            success_urls=success_urls,
            success_texts=success_texts,
        )
        if _has_strong_reason(completed_reasons):
            break
    return last_obs, completed_reasons


def _ask_user_login_confirm(
    input_reader: Callable[[str], str],
    completed_reasons: list[str],
) -> bool:
    """사용자 Enter 수신. 확인되면 completed_reasons 에 user_confirmed_login 추가."""
    login_confirmed_by_user = False
    try:
        answer = input_reader(
            _USER_LOGIN_CONFIRM_PROMPT,
        )
    except (KeyboardInterrupt, EOFError):
        answer = None
    if answer is not None:
        stripped = (answer or "").strip().lower()
        if stripped not in {"n", "no", "아니오"}:
            login_confirmed_by_user = True
            if "user_confirmed_login" not in completed_reasons:
                completed_reasons.append(
                    "user_confirmed_login",
                )
    return login_confirmed_by_user


def _scan_pages_and_warn(
    context: Any,
    success_urls: list[str],
    login_confirmed_by_user: bool,
    warnings: list[str],
) -> tuple[int, bool]:
    """7) 다중 탭 스캔 (measurement gap 보완) + 경고 누적.

    Studio/OAuth flow 가 window.open/팝업으로 target 페이지를
    별도 탭에 열었을 경우, 단일 `page` 기준으로는 놓친다.
    context.pages 전수 스캔으로 각 탭의 url/title 을
    read-only 로만 수집해 집계한다. fake context 에서는
    `pages` 속성이 없으므로 getattr default=None 로 안전
    fallback 된다.
    """
    pages_observed_count, success_url_across_pages = _scan_context_pages_aggregate(
        context=context,
        success_urls=success_urls,
    )
    if success_url_across_pages and not login_confirmed_by_user:
        # 사용자 확인이 없는데 다른 탭에 target 이 열려 있는
        # 상태는 자동 단정하지 않는다 (§5.3, §8.4 WARN).
        if "success_url_observed_across_pages" not in (warnings or []):
            warnings.append("success_url_observed_across_pages")
    if login_confirmed_by_user and not success_url_across_pages:
        # 사용자 확인은 있는데 스크립트가 target URL 을 어느
        # 탭에서도 관측하지 못한 경우 — §8.4 "PASS with
        # measurement caveat" 케이스.
        if "script_observed_without_target_url" not in (warnings or []):
            warnings.append("script_observed_without_target_url")
    return pages_observed_count, success_url_across_pages


def _success_url_reason(success_urls: list[str], init_url: str, cur_url: str) -> str | None:
    init_url_lc = init_url.lower()
    cur_url_lc = cur_url.lower()
    for tok in success_urls:
        tok_lc = (tok or "").lower()
        if not tok_lc:
            continue
        # 초기에 이미 토큰이 포함돼 있었다면 success_url_match 는 약한
        # 신호가 아니라 "처음부터 그 상태" 이므로 reason 에 추가하지 않는다.
        if tok_lc in cur_url_lc and tok_lc not in init_url_lc:
            return f"success_url_match:{tok[:60]}"
    return None


def _success_text_reason(success_texts: list[str], initial: dict[str, Any], current: dict[str, Any]) -> str | None:
    text_blob_current = _visible_text_blob(current.get("page_structure") or {})
    text_blob_initial = _visible_text_blob(initial.get("page_structure") or {})
    for tok in success_texts:
        if not tok:
            continue
        if tok in text_blob_current and tok not in text_blob_initial:
            return f"success_text_match:{tok[:60]}"
    return None


def _build_result(  # noqa: PLR0913 - keyword-only 내부 결과 빌더, 호출 1곳
    *,
    url: str,
    initial: dict[str, Any],
    last_obs: dict[str, Any],
    completed_reasons: list[str],
    login_state_hint: str,
    login_completed_hint: bool,
    visible_confirmed_by_user: bool,
    login_confirmed_by_user: bool,
    warnings: list[str],
    pages_observed_count: int = 1,
    success_url_observed_across_pages: bool = False,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "mode": "manual_login_probe",
        "url": url,
        "visible_confirmed_by_user": bool(visible_confirmed_by_user),
        "login_confirmed_by_user": bool(login_confirmed_by_user),
        "login_state_hint": login_state_hint,
        "login_completed_hint": bool(login_completed_hint),
        "login_completion_reason": list(completed_reasons),
        "pages_observed_count": int(pages_observed_count),
        "success_url_observed_across_pages": bool(success_url_observed_across_pages),
        "initial": _redact_observation(initial, include_structure=False),
        "warnings": list(warnings),
    }

    if login_completed_hint:
        base["ok"] = True
        base["after"] = _redact_observation(
            last_obs,
            include_structure=True,
            login_completed_hint=True,
            login_completion_reason=completed_reasons,
        )
        base["summary"] = (
            "manual login completed hint=true state=" + login_state_hint + " reasons=" + ",".join(completed_reasons)
        )[:300]
        return base

    base["ok"] = False
    base["last_observation"] = _redact_observation(
        last_obs,
        include_structure=False,
        login_completed_hint=False,
        login_completion_reason=completed_reasons,
    )
    if login_state_hint == "already_logged_in_or_public_page":
        base["error_code"] = "LOGIN_NOT_CONFIRMED"
        base["summary"] = (
            "initial page already looked logged in or was a public page — manual login completion not confirmed"
        )[:300]
    else:
        base["error_code"] = "LOGIN_TIMEOUT"
        base["summary"] = ("Manual login was not detected before timeout")[:300]
    return base


def _build_canceled_result(
    *,
    url: str,
    initial: dict[str, Any],
    warnings: list[str],
    success_urls: list[str],
) -> dict[str, Any]:
    initial_is_already_logged_in = _initial_is_already_logged_in(
        initial=initial,
        success_urls=success_urls,
    )
    login_state_hint, _ = _classify_login(
        initial=initial,
        completion_reasons=[],
        initial_is_already_logged_in=initial_is_already_logged_in,
        require_user_login_confirm=False,
        login_confirmed_by_user=False,
    )
    return {
        "ok": False,
        "mode": "manual_login_probe",
        "url": url,
        "error_code": "VISIBILITY_NOT_CONFIRMED",
        "summary": "user did not confirm browser visibility",
        "initial": _redact_observation(initial, include_structure=False),
        "warnings": list(warnings),
        "visible_confirmed_by_user": False,
        "login_confirmed_by_user": False,
        "login_state_hint": login_state_hint,
        "login_completed_hint": False,
        "login_completion_reason": [],
    }


def _safe_bring_to_front(page: Any) -> None:
    """best-effort: 브라우저 창을 앞으로 끌어올려 사용자에게 보이게 시도."""
    try:
        fn = getattr(page, "bring_to_front", None)
        if callable(fn):
            fn()
    except Exception:
        logger.debug("bring_to_front failed", exc_info=True)


def _scan_context_pages_aggregate(
    *,
    context: Any,
    success_urls: list[str],
) -> tuple[int, bool]:
    """read-only 로 context 의 모든 page 를 훑어 target url 관측 여부만 집계.

    Studio / OAuth flow 처럼 target 페이지가 window.open / popup 으로 별도
    탭에 열리는 경우, 단일 `page` 객체만 추적하는 기존 관찰 루프는 이를
    놓친다. 관찰 종료 시점에 context.pages 를 전수 순회해 url 만 모아
    success_url_contains 토큰이 어떤 탭에서든 발견됐는지 집계한다.

    Playwright API 가 없거나 fake context (테스트) 에서 `pages` 속성이
    없으면 ``getattr(..., None)`` 으로 안전 fallback 되어 ``(0, False)``
    를 반환한다.

    허용 호출: ``page.url`` property 뿐. title / content / click / fill /
    cookies / storage_state 등은 절대 호출하지 않는다.

    Returns:
        (pages_observed_count, success_url_observed_across_pages)
    """
    ctx_pages = getattr(context, "pages", None)
    if ctx_pages is None:
        return 0, False
    try:
        iterable = ctx_pages() if callable(ctx_pages) else ctx_pages
    except Exception:  # noqa: BLE001 - 수동 로그인 프로브 -- 브라우저 오픈/런치 실패를 에러코드가 있는 결과로 변환, 탭 전면화 등 부가 동작 실패는 무시
        return 0, False
    if not iterable:
        return 0, False

    count = 0
    hit = False
    success_lower = [t.lower() for t in success_urls if t]
    for pg in iterable:
        try:
            u = getattr(pg, "url", "") or ""
        except Exception:  # noqa: BLE001 - 수동 로그인 프로브 -- 브라우저 오픈/런치 실패를 에러코드가 있는 결과로 변환, 탭 전면화 등 부가 동작 실패는 무시
            u = ""
        if not isinstance(u, str):
            u = ""
        count += 1
        if hit:
            continue
        u_lc = u.lower()
        for tok in success_lower:
            if tok and tok in u_lc:
                hit = True
                break
    return count, hit


def _observe(page: Any, *, max_html_chars: int) -> dict[str, Any]:
    """read-only 관찰 1회. 오직 title / url / content 만 호출."""
    title = page.title() or ""
    current_url = page.url or ""
    html = page.content() or ""
    if not isinstance(html, str):
        html = ""
    html_truncated = False
    if len(html) > max_html_chars:
        html = html[:max_html_chars]
        html_truncated = True
    structure = analyze_html_structure(html=html, base_url=current_url)
    login_hint, login_reason = _detect_login_required(structure)
    return {
        "title": (title or "")[:300],
        "current_url": (current_url or "")[:500],
        "html_truncated": html_truncated,
        "login_required_hint": login_hint,
        "login_reason": login_reason,
        "page_structure": structure,
    }


def _detect_completion(
    *,
    initial: dict[str, Any],
    current: dict[str, Any],
    success_urls: list[str],
    success_texts: list[str],
) -> list[str]:
    """로그인 완료로 보이는 구조 변화 감지.

    success_url_match 는 initial URL 에 이미 해당 토큰이 포함되어 있었으면
    추가하지 않는다. (이미 target 페이지에서 출발한 경우를 완료로 잘못
    판정하지 않도록.)
    """
    reasons: list[str] = []

    initial_pw = "password_input_detected" in (initial.get("login_reason") or [])
    current_pw = "password_input_detected" in (current.get("login_reason") or [])
    if initial_pw and not current_pw:
        reasons.append("password_input_disappeared")

    init_url = initial.get("current_url") or ""
    cur_url = current.get("current_url") or ""
    if init_url and cur_url and init_url != cur_url:
        reasons.append("url_changed")

    if initial.get("login_required_hint") and not current.get("login_required_hint"):
        reasons.append("login_required_hint_cleared")

    url_reason = _success_url_reason(success_urls, init_url, cur_url)
    if url_reason is not None:
        reasons.append(url_reason)

    text_reason = _success_text_reason(success_texts, initial, current)
    if text_reason is not None:
        reasons.append(text_reason)

    # de-dup, keep order.
    seen: set[str] = set()
    unique: list[str] = []
    for r in reasons:
        if r in seen:
            continue
        seen.add(r)
        unique.append(r)
    return unique


def _has_strong_reason(reasons: list[str]) -> bool:
    """success_url_match 이외의 근거가 하나라도 있으면 True."""
    for r in reasons:
        if r.startswith("success_url_match:"):
            continue
        return True
    return False


def _initial_is_already_logged_in(
    *,
    initial: dict[str, Any],
    success_urls: list[str],
) -> bool:
    """초기 페이지가 이미 target 상태 (로그인됨 또는 공개 페이지) 로 보이는지.

    조건 (모두 만족):
      - password input 감지되지 않음
      - login_required_hint 가 False (Sign in 버튼 등 로그인 CTA 없음)
      - URL 이 accounts.google.com 이 아님
      - URL 이 success_url_contains 토큰 중 하나를 포함함
    """
    init_url = (initial.get("current_url") or "").lower()
    init_reasons = initial.get("login_reason") or []
    if "password_input_detected" in init_reasons:
        return False
    if initial.get("login_required_hint"):
        return False
    if "accounts.google.com" in init_url:
        return False
    for tok in success_urls:
        tok_lc = (tok or "").lower()
        if tok_lc and tok_lc in init_url:
            return True
    return False


def _classify_login(
    *,
    initial: dict[str, Any],
    completion_reasons: list[str],
    initial_is_already_logged_in: bool,
    require_user_login_confirm: bool,
    login_confirmed_by_user: bool,
) -> tuple[str, bool]:
    """(login_state_hint, login_completed_hint) 결정.

    판정 규칙
      1) 사용자 Enter 로 확인된 경우 → manual_login_completed, hint=True
      2) 초기 페이지가 already_logged_in_or_public_page 면 → hint=False
         (사용자 확인 없이는 자동 True 로 올리지 않는다)
      3) strong 근거 (success_url_match 외) 있으면 → manual_login_completed
         (require_user_login_confirm=True 이면 hint=False 로 유지)
      4) 초기에 password input / login_required_hint 있었고 완료 근거 없으면
         → login_required, hint=False
      5) 나머지 → unknown, hint=False
    """
    if login_confirmed_by_user:
        return "manual_login_completed", True

    if initial_is_already_logged_in:
        return "already_logged_in_or_public_page", False

    if _has_strong_reason(completion_reasons):
        hint = not require_user_login_confirm
        return "manual_login_completed", hint

    init_reasons = initial.get("login_reason") or []
    if "password_input_detected" in init_reasons or initial.get("login_required_hint"):
        return "login_required", False

    return "unknown", False


def _visible_text_blob(structure: dict[str, Any]) -> str:
    chunks: list[str] = [str(structure.get("page_title") or "")]
    for h in structure.get("headings") or []:
        chunks.append(str((h or {}).get("text") or ""))
    for b in structure.get("buttons") or []:
        chunks.append(str((b or {}).get("text") or ""))
    for link in structure.get("links") or []:
        chunks.append(str((link or {}).get("text") or ""))
    return " ".join(chunks)


def _redact_observation(
    obs: dict[str, Any],
    *,
    include_structure: bool = False,
    login_completed_hint: bool | None = None,
    login_completion_reason: list[str] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "title": obs.get("title", ""),
        "current_url": obs.get("current_url", ""),
        "login_required_hint": bool(obs.get("login_required_hint", False)),
        "login_reason": list(obs.get("login_reason") or []),
    }
    if login_completed_hint is not None:
        out["login_completed_hint"] = bool(login_completed_hint)
    if login_completion_reason is not None:
        out["login_completion_reason"] = list(login_completion_reason)
    if include_structure:
        out["page_structure"] = obs.get("page_structure") or {}
    return out


def _err(*, url: str, error_code: str, reason: str) -> dict[str, Any]:
    return {
        "ok": False,
        "mode": "manual_login_probe",
        "url": url,
        "error_code": error_code,
        "summary": reason[:300],
        "reason": reason[:200],
    }


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


def _normalize_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip()[:200])
        if len(out) >= 50:
            break
    return out


def _normalize_allowed_hosts(value: Any) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip().lower()[:253])
    return out


def _normalize_browser_channel(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    if not v:
        return None
    if v not in _ALLOWED_BROWSER_CHANNELS:
        return None
    return v


def _normalize_viewport(value: Any) -> dict[str, int] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        return None
    try:
        w = int(value.get("width", 0))
        h = int(value.get("height", 0))
    except (TypeError, ValueError):
        return None
    if not (_MIN_VIEWPORT <= w <= _MAX_VIEWPORT):
        return None
    if not (_MIN_VIEWPORT <= h <= _MAX_VIEWPORT):
        return None
    return {"width": w, "height": h}


def _host_allowed(host: str, allowed: list[str]) -> bool:
    if not allowed:
        return False
    h = (host or "").lower()
    for a in allowed:
        if not a:
            continue
        if h == a:
            return True
        if h.endswith("." + a):
            return True
    return False


__all__ = [
    "probe_manual_login_flow",
]
