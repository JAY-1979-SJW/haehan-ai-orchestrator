"""local_agent visible browser probe (E-2 단계, F-2 Google open-only 정책).

목적:
  - 사용자 PC 에서 Playwright ``launch_persistent_context`` 로 **dedicated
    HaehanAI 프로필** 의 visible 브라우저를 띄우고, 페이지 상태를 read-only
    로 관찰한다.
  - ``open_local_browser`` (subprocess Popen 방식) 와는 별개. 이 모듈은
    오직 Playwright API 를 사용한다.

F-2 Google / YouTube open-only 정책:
  - ``accounts.google.com`` / ``google.com`` / ``studio.youtube.com`` /
    ``youtube.com`` / ``gmail.com`` / ``drive.google.com`` 및 그 서브
    도메인은 본 probe 의 대상이 아니다. Playwright 자동화 제어 브라우저는
    Google 로그인 페이지를 ``signin/rejected`` 로 차단당하는 사례가 있어,
    visible probe 시도 자체가 무의미하고 오히려 사용자의 정상 세션을
    오염시킬 위험이 있다.
  - 따라서 ``probe_visible_browser`` 는 위 도메인을 받으면 Playwright
    launch 전에 거절한다 (``success=False`` /
    ``error_code="GOOGLE_OPEN_ONLY"`` /
    ``warnings=["google_open_only_use_open_local_browser"]``). 결과 dict
    에는 raw URL 의 query/fragment 가 절대 포함되지 않는다 (host+path
    까지만 ``final_url_host_path`` 로 축약).
  - 이 도메인의 visible 세션 확보는 ``open_local_browser`` (dedicated
    프로필 + 사용자 수동 로그인) 만 사용한다.
  - Google API 작업은 본 probe / launcher 와 무관하게 별도 OAuth /
    API connector 로 처리한다.

본 모듈에서 절대 수행하지 않는 것:
  - ``headless=True`` / ``--headless`` 플래그
  - ``--remote-debugging-port`` 자동 부여
  - ID/PW 자동 입력 (``page.fill`` / ``page.type`` / ``page.press``)
  - 클릭 / 제출 / 업로드 (``page.click`` / ``page.set_input_files`` 등)
  - 키보드 / 마우스 직접 조작 (``page.keyboard`` / ``page.mouse``)
  - 페이지 본문 수집 (``page.content``)
  - 쿠키 / storage_state / localStorage / sessionStorage / token 수집
  - ``context.add_cookies`` / ``context.cookies()`` / ``evaluate``
  - 기본 Chrome / Edge 사용자 프로필 디렉터리 직접 사용
  - ``GOOGLE_PASSWORD`` / ``GOOGLE_LOGIN_PASSWORD`` / ``GOOGLE_COOKIE`` /
    ``GOOGLE_SESSION`` / ``GOOGLE_STORAGE_STATE`` / ``GOOGLE_OTP_SECRET``
    환경변수가 비어있지 않게 설정된 상태에서의 실행
  - 서버(ai_orchestrator) 코드에서 본 모듈 import / 호출

허용 Playwright API 만:
  - ``page.goto``
  - ``page.url`` (property)
  - ``page.title()``
  - ``context.pages`` (iterable)
  - ``page.bring_to_front()``
  - ``page.wait_for_load_state()``
  - ``context.close()``

반환 dict (성공/실패 동일 스키마):
  {
    "success":                            bool,
    "target_url":                         str,           # 입력 URL 그대로
    "browser_provider":                   str,           # msedge / chrome / chromium / ""
    "title_category":                     str,           # "empty" / "login_required" /
                                                         # "youtube_studio" / "youtube" /
                                                         # "google_account" / "naver" /
                                                         # "generic" / "error"
    "final_url_host_path":                str,           # host + path (query/fragment 제거)
    "pages_observed_count":               int,
    "success_url_observed_across_pages":  bool,
    "observed_login_page":                bool,
    "warnings":                           list[str],
  }

주의:
  - chrome.exe / msedge.exe 의 **전체 경로 미반환** (browser_provider 만).
  - 전용 프로필 **절대경로 미반환**.
  - **raw title 노출 금지** — 카테고리 토큰만.
  - **raw URL 노출 금지** — host + path 만.
  - cookie / session / storage / token 절대 미수집·미반환.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional, Sequence
from urllib.parse import urlparse

from . import browser_launcher

logger = logging.getLogger(__name__)


# ─── 정책 / 상수 ────────────────────────────────────────────────────────

_MIN_WAIT_SECONDS = 1
_MAX_WAIT_SECONDS = 600
_DEFAULT_WAIT_SECONDS = 30
_MIN_POLL_SECONDS = 1
_MAX_POLL_SECONDS = 30
_DEFAULT_POLL_SECONDS = 2
_MIN_GOTO_TIMEOUT_MS = 1000
_MAX_GOTO_TIMEOUT_MS = 60000
_DEFAULT_GOTO_TIMEOUT_MS = 15000

# title 토큰 → 카테고리. 우선순위 순.
_TITLE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("login_required", (
        "sign in", "sign-in", "signin",
        "log in", "log-in", "login",
        "로그인",
    )),
    ("youtube_studio", ("youtube studio", "youtube 스튜디오")),
    ("youtube", ("youtube",)),
    ("google_account", ("google account", "내 google 계정", "내 계정")),
    ("naver", ("naver", "네이버")),
)

# URL 경로 / 호스트 토큰 → 로그인 페이지 추정.
_LOGIN_URL_TOKENS: tuple[str, ...] = (
    "accounts.google.com",
    "/signin",
    "/sign-in",
    "/login",
    "/log-in",
    "/auth/oauth",
    "/oauth",
    "/identifier",
    "nid.naver.com",
)


# ─── 분류 / 정규화 helper ───────────────────────────────────────────────

def _title_category(title: Any) -> str:
    if not isinstance(title, str) or not title.strip():
        return "empty"
    lower = title.lower()
    for cat, keys in _TITLE_RULES:
        for k in keys:
            if k in lower:
                return cat
    return "generic"


def _url_host_path(url: Any) -> str:
    """raw URL 을 host + path 로 축약. query/fragment 는 제거."""
    if not isinstance(url, str) or not url.strip():
        return ""
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return ""
    host = (parsed.hostname or "").lower()
    if not host:
        return ""
    path = parsed.path or ""
    out = host + path
    return out[:200].rstrip("/")


def _looks_like_login(url: Any, title_cat: str) -> bool:
    if title_cat == "login_required":
        return True
    if not isinstance(url, str):
        return False
    u = url.lower()
    for tok in _LOGIN_URL_TOKENS:
        if tok in u:
            return True
    return False


def _target_host_token(target_url: str) -> str:
    """관찰된 다른 페이지에서 target host 가 발견되는지 비교할 lowercase 호스트."""
    try:
        parsed = urlparse(target_url)
    except Exception:
        return ""
    return (parsed.hostname or "").lower()


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


# ─── 결과 빌더 ──────────────────────────────────────────────────────────

def _fail_result(
    *, target_url: str, warnings: Sequence[str],
    title_category: str = "error",
    final_url_host_path: str = "",
    browser_provider: str = "",
    error_code: str = "",
) -> dict:
    out = {
        "success": False,
        "target_url": target_url if isinstance(target_url, str) else "",
        "browser_provider": browser_provider,
        "title_category": title_category,
        "final_url_host_path": final_url_host_path,
        "pages_observed_count": 0,
        "success_url_observed_across_pages": False,
        "observed_login_page": False,
        "warnings": list(warnings),
    }
    if error_code:
        out["error_code"] = error_code
    return out


def _google_open_only_result(*, target_url: str) -> dict:
    """F-2: Google/YouTube URL 은 Playwright launch 전에 차단.

    raw URL 의 query/fragment 는 결과에 절대 노출하지 않는다 (host+path
    까지만 ``final_url_host_path`` 로 축약). ``target_url`` 은 빈 문자열
    로 두어 입력 토큰이 결과 dict 어디에도 들어가지 않도록 한다.
    """
    safe_host_path = _url_host_path(target_url)
    return _fail_result(
        target_url="",
        warnings=["google_open_only_use_open_local_browser"],
        title_category="google_open_only",
        final_url_host_path=safe_host_path,
        browser_provider="",
        error_code="GOOGLE_OPEN_ONLY",
    )


# ─── 환경/프로필 검증 (browser_launcher 정책 재사용) ────────────────────

def _check_forbidden_env(env: dict) -> list[str]:
    hits: list[str] = []
    for key in browser_launcher._FORBIDDEN_ENV_VARS:
        v = env.get(key)
        if v is not None and str(v).strip() != "":
            hits.append(f"forbidden_env_present:{key}")
    return hits


def _resolve_provider_order(
    site_policy: str, provider_override: Optional[str],
) -> tuple[Sequence[str] | None, Optional[str]]:
    if provider_override is not None:
        if provider_override not in browser_launcher.SUPPORTED_PROVIDERS:
            return None, f"unsupported_provider:{provider_override}"
        return (provider_override,), None
    if site_policy == browser_launcher.SITE_POLICY_GOOGLE:
        return browser_launcher._PROVIDER_PRIORITY_GOOGLE, None
    if site_policy == browser_launcher.SITE_POLICY_AUTO:
        return browser_launcher._PROVIDER_PRIORITY_AUTO, None
    return None, f"unknown_site_policy:{site_policy}"


def _resolve_executable(
    order: Sequence[str], env: dict,
) -> tuple[Optional[str], Optional[str]]:
    for provider in order:
        path_str, _category = browser_launcher._find_executable(provider, env)
        if path_str:
            return provider, path_str
    return None, None


def _resolve_dedicated_profile(
    *, provider: str, profile_name: str, env: dict,
) -> tuple[Optional[Path], Optional[str]]:
    name_err = browser_launcher._validate_profile_name(profile_name)
    if name_err:
        return None, name_err

    profile_root = browser_launcher._profile_root(env)
    profile_dir = browser_launcher._profile_path_for(
        provider, profile_name, env,
    )
    try:
        root_res = profile_root.expanduser().resolve(strict=False)
        dir_res = profile_dir.expanduser().resolve(strict=False)
    except OSError:
        return None, "profile_path_resolve_failed"

    try:
        dir_res.relative_to(root_res)
    except ValueError:
        return None, "profile_not_within_root"

    marker = (
        browser_launcher._detect_default_profile(str(dir_res))
        or browser_launcher._detect_default_profile(str(root_res))
    )
    if marker:
        return None, f"default_profile_blocked:{marker}"

    try:
        profile_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return None, f"profile_dir_create_failed:{type(e).__name__}"

    return profile_dir, None


# ─── Playwright 실행 ────────────────────────────────────────────────────

def _build_launch_args() -> list[str]:
    """사용자가 아이콘으로 브라우저를 연 것과 가장 유사한 최소 인자.
    절대 ``--headless`` / ``--remote-debugging-port`` 를 추가하지 않는다."""
    return ["--no-first-run", "--no-default-browser-check"]


def probe_visible_browser(
    url: str,
    *,
    profile_name: str = "default",
    site_policy: str = browser_launcher.SITE_POLICY_AUTO,
    provider_override: Optional[str] = None,
    wait_seconds: int = _DEFAULT_WAIT_SECONDS,
    poll_interval_seconds: int = _DEFAULT_POLL_SECONDS,
    goto_timeout_ms: int = _DEFAULT_GOTO_TIMEOUT_MS,
    _browser_factory: Optional[Callable[[], Any]] = None,
    _clock: Any | None = None,
    _env: Optional[dict] = None,
) -> dict:
    """Playwright 로 visible 브라우저를 dedicated 프로필로 띄우고 read-only 관찰.

    절대 수행하지 않는 것 (모듈 docstring 참조).

    테스트 편의:
      - ``_browser_factory``: ``sync_playwright`` 대체 (context manager 형태).
      - ``_clock``: ``time`` 모듈 대체.
      - ``_env``: ``os.environ`` 대체.
    """
    eff_env = dict(os.environ) if _env is None else dict(_env)

    # 1) URL 유효성.
    if not isinstance(url, str) or not url.strip():
        return _fail_result(target_url="", warnings=["invalid_target_url"])
    target_url = url.strip()
    if not (target_url.startswith("http://") or target_url.startswith("https://")):
        return _fail_result(
            target_url=target_url,
            warnings=["target_url_scheme_forbidden"],
        )

    # 1.5) F-2: Google/YouTube 계열은 Playwright probe 대상이 아니다.
    #      Playwright 자동화 제어 브라우저는 Google 로그인 페이지를
    #      signin/rejected 로 차단당하는 사례가 있고, 해당 시도 자체에서
    #      쿠키/스토리지/세션을 수집할 위험이 있다. 따라서 launch 전에
    #      거절하고 사용자는 ``open_local_browser`` (subprocess Popen)
    #      경로로만 열도록 강제한다. raw URL query/fragment 는 결과에
    #      어떤 형태로도 반영되지 않는다.
    if browser_launcher.is_google_open_only_url(target_url):
        return _google_open_only_result(target_url=target_url)

    # 2) 민감 환경변수 차단.
    forbidden_hits = _check_forbidden_env(eff_env)
    if forbidden_hits:
        return _fail_result(target_url=target_url, warnings=forbidden_hits)

    # 3) provider 우선순위 결정.
    order, err = _resolve_provider_order(site_policy, provider_override)
    if err is not None:
        return _fail_result(target_url=target_url, warnings=[err])
    assert order is not None

    # 4) 실행 파일 탐색.
    chosen_provider, chosen_path = _resolve_executable(order, eff_env)
    if chosen_provider is None or chosen_path is None:
        return _fail_result(target_url=target_url, warnings=["no_browser_found"])

    # 5) dedicated 프로필 산출 + 기본 프로필 차단.
    profile_dir, perr = _resolve_dedicated_profile(
        provider=chosen_provider,
        profile_name=profile_name,
        env=eff_env,
    )
    if profile_dir is None:
        return _fail_result(
            target_url=target_url,
            warnings=[perr or "profile_resolve_failed"],
            browser_provider=chosen_provider,
        )

    # 6) 파라미터 정규화.
    wait_seconds = _clip_int(
        wait_seconds, _MIN_WAIT_SECONDS, _MAX_WAIT_SECONDS,
        _DEFAULT_WAIT_SECONDS,
    )
    poll_interval_seconds = _clip_int(
        poll_interval_seconds, _MIN_POLL_SECONDS, _MAX_POLL_SECONDS,
        _DEFAULT_POLL_SECONDS,
    )
    if poll_interval_seconds > wait_seconds:
        poll_interval_seconds = wait_seconds
    goto_timeout_ms = _clip_int(
        goto_timeout_ms, _MIN_GOTO_TIMEOUT_MS, _MAX_GOTO_TIMEOUT_MS,
        _DEFAULT_GOTO_TIMEOUT_MS,
    )

    # 7) Playwright factory 선택.
    factory = _browser_factory
    if factory is None:
        try:
            from playwright.sync_api import sync_playwright as _sync_playwright
        except ImportError:
            return _fail_result(
                target_url=target_url,
                warnings=["browser_dependency_missing"],
                browser_provider=chosen_provider,
            )
        factory = _sync_playwright

    import time as _time_default
    time_mod = _clock or _time_default

    return _run_probe(
        factory=factory,
        time_mod=time_mod,
        target_url=target_url,
        provider=chosen_provider,
        executable_path=chosen_path,
        profile_dir=profile_dir,
        wait_seconds=wait_seconds,
        poll_interval_seconds=poll_interval_seconds,
        goto_timeout_ms=goto_timeout_ms,
    )


def _run_probe(
    *,
    factory: Callable[[], Any],
    time_mod: Any,
    target_url: str,
    provider: str,
    executable_path: str,
    profile_dir: Path,
    wait_seconds: int,
    poll_interval_seconds: int,
    goto_timeout_ms: int,
) -> dict:
    warnings: list[str] = []
    target_host = _target_host_token(target_url)

    # headless 는 절대 True 로 설정하지 않는다 (모듈 docstring §금지).
    launch_kwargs: dict[str, Any] = {
        "user_data_dir": str(profile_dir),
        "headless": False,
        "args": _build_launch_args(),
    }
    if provider in ("chrome", "msedge"):
        # Playwright channel 매핑.
        launch_kwargs["channel"] = provider
    else:
        # chromium 은 ms-playwright 번들 또는 PATH 의 실행 파일을 직접 사용.
        launch_kwargs["executable_path"] = executable_path

    final_title_cat = "empty"
    final_url_host = ""
    pages_observed_count = 0
    success_url_observed_across_pages = False
    observed_login_page = False

    try:
        with factory() as pw:
            try:
                context = pw.chromium.launch_persistent_context(**launch_kwargs)
            except Exception as e:
                logger.exception("launch_persistent_context failed")
                return _fail_result(
                    target_url=target_url,
                    warnings=[f"browser_launch_failed:{type(e).__name__}"],
                    browser_provider=provider,
                )

            try:
                # context 내부에 빈 about:blank 탭이 있을 수 있다. 첫 번째
                # 탭을 재사용하거나 없으면 새로 만든다 (둘 다 허용 API).
                page = None
                existing_pages = _materialize_pages(context)
                if existing_pages:
                    page = existing_pages[0]
                if page is None:
                    page = context.new_page()

                try:
                    page.goto(
                        target_url, timeout=goto_timeout_ms,
                        wait_until="domcontentloaded",
                    )
                except Exception as e:
                    logger.exception("page.goto failed")
                    warnings.append(f"goto_failed:{type(e).__name__}")
                    return _fail_result(
                        target_url=target_url,
                        warnings=warnings,
                        browser_provider=provider,
                    )

                # best-effort: 사용자 화면에 노출.
                try:
                    page.bring_to_front()
                except Exception:
                    logger.debug("bring_to_front failed", exc_info=True)

                try:
                    page.wait_for_load_state("domcontentloaded")
                except Exception:
                    logger.debug("wait_for_load_state failed", exc_info=True)

                # 관찰 루프 (read-only).
                deadline_ts = time_mod.monotonic() + wait_seconds
                while True:
                    snapshot = _scan_pages(context, target_host=target_host)
                    pages_observed_count = max(
                        pages_observed_count, snapshot["count"],
                    )
                    if snapshot["target_host_seen"]:
                        success_url_observed_across_pages = True
                    if snapshot["any_login_page"]:
                        observed_login_page = True

                    now = time_mod.monotonic()
                    if now >= deadline_ts:
                        break
                    sleep_for = min(
                        poll_interval_seconds, deadline_ts - now,
                    )
                    if sleep_for > 0:
                        time_mod.sleep(sleep_for)

                # 마지막에 main page 의 url/title 만 categorize.
                try:
                    raw_title = page.title() or ""
                except Exception:
                    raw_title = ""
                    warnings.append("title_unavailable")
                try:
                    raw_url = page.url or ""
                except Exception:
                    raw_url = ""
                    warnings.append("url_unavailable")

                final_title_cat = _title_category(raw_title)
                final_url_host = _url_host_path(raw_url)
                if _looks_like_login(raw_url, final_title_cat):
                    observed_login_page = True
            finally:
                try:
                    context.close()
                except Exception:
                    logger.debug("context.close failed", exc_info=True)
    except Exception as e:
        logger.exception("playwright session failed")
        return _fail_result(
            target_url=target_url,
            warnings=[f"playwright_session_failed:{type(e).__name__}"],
            browser_provider=provider,
        )

    return {
        "success": True,
        "target_url": target_url,
        "browser_provider": provider,
        "title_category": final_title_cat,
        "final_url_host_path": final_url_host,
        "pages_observed_count": int(pages_observed_count),
        "success_url_observed_across_pages": bool(
            success_url_observed_across_pages,
        ),
        "observed_login_page": bool(observed_login_page),
        "warnings": list(warnings),
    }


def _materialize_pages(context: Any) -> list:
    pages_attr = getattr(context, "pages", None)
    if pages_attr is None:
        return []
    try:
        iterable = pages_attr() if callable(pages_attr) else pages_attr
    except Exception:
        return []
    if not iterable:
        return []
    try:
        return list(iterable)
    except Exception:
        return []


def _scan_pages(context: Any, *, target_host: str) -> dict:
    """context.pages 전수 순회. URL/title 만 read-only 로 본다."""
    out = {"count": 0, "target_host_seen": False, "any_login_page": False}
    pages = _materialize_pages(context)
    for pg in pages:
        out["count"] += 1
        try:
            u = pg.url or ""
        except Exception:
            u = ""
        if not isinstance(u, str):
            u = ""
        try:
            t = pg.title() or ""
        except Exception:
            t = ""
        if not isinstance(t, str):
            t = ""
        if target_host and target_host in u.lower():
            out["target_host_seen"] = True
        if _looks_like_login(u, _title_category(t)):
            out["any_login_page"] = True
    return out


__all__ = [
    "probe_visible_browser",
]
