"""local_agent 공개 페이지 read-only observer (F-4B 단계).

목적:
  - 공개 웹페이지를 fresh BrowserContext (no storage_state / no persistent
    profile) 로 열어 read-only 로 구조를 수집하고 ``page_state`` 를 1차
    분류한다. 결과는 오케스트레이터/관리 UI 가 "이 페이지가 로그인 필요/
    captcha/개발자문서/포털/일반 공개 페이지 중 무엇인지" 빠르게 판단하기
    위해 사용된다.
  - ``open_local_browser`` (subprocess Popen) / ``probe_visible_browser``
    (dedicated 프로필 visible 로그인 probe) 와는 모듈/책임 분리. 본 observer
    는 사용자 세션을 절대 사용하지 않으며, 공개 페이지 정보 수집만 한다.

Google/YouTube open-only 정책 (F-2 와 동일):
  - ``accounts.google.com`` / ``google.com`` / ``studio.youtube.com`` /
    ``youtube.com`` / ``gmail.com`` / ``drive.google.com`` 및 서브도메인은
    Playwright launch 전에 거절한다 (``error_code="GOOGLE_OPEN_ONLY"``,
    ``warnings=["google_open_only_use_open_local_browser"]``). 결과 dict 에
    raw URL query/fragment 가 어떤 형태로도 노출되지 않는다.

본 모듈에서 절대 수행하지 않는 것:
  - ID/PW 자동 입력 (``page.fill`` / ``page.type`` / ``page.press``)
  - 클릭 / 제출 / 업로드 (``page.click`` / ``page.set_input_files`` /
    ``page.select_option``)
  - 키보드 / 마우스 조작 (``page.keyboard`` / ``page.mouse``)
  - 폼 전송 / 다운로드 이벤트 처리
  - 쿠키 / storage_state / localStorage / sessionStorage 수집·주입
  - ``context.add_cookies`` / ``context.cookies()`` / ``evaluate`` /
    ``evaluate_handle``
  - ``--remote-debugging-port`` 자동 부여 / ``--headless`` 사용
  - 사용자 기존 브라우저 프로필 / 세션 디렉터리 사용 (fresh context only)
  - ``GOOGLE_PASSWORD`` / ``GOOGLE_LOGIN_PASSWORD`` / ``GOOGLE_COOKIE`` /
    ``GOOGLE_SESSION`` / ``GOOGLE_STORAGE_STATE`` / ``GOOGLE_OTP_SECRET``
    환경변수가 비어있지 않게 설정된 상태에서의 실행
  - input value / textarea value 수집 (web_reader 가 이미 drop)

허용 Playwright API (read-only):
  - ``pw.chromium.launch(headless=False)``  — 사용자 시각 정책에 맞춤
  - ``browser.new_context()``  — fresh, storage_state 미주입
  - ``context.new_page()``
  - ``page.goto(url, wait_until="domcontentloaded")`` — Response 반환
  - ``page.title()``  / ``page.url`` (property)
  - ``page.content()``  — 본 모듈은 read-only 분석 전용이므로 허용
  - ``response.status``  (page.goto 의 Response)

반환 dict 핵심 필드:
  success / error_code / warnings / target_url / final_url_host_path /
  title / status_code / page_state / text_excerpt / text_length /
  links_count / buttons_count / forms_count / inputs_count /
  links (≤20) / buttons (≤20) / forms (≤10) / screenshot_path (optional)

target_url 은 raw query/fragment 가 제거된 host+path 까지만 노출된다.
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Callable, Optional
from urllib.parse import urljoin, urlparse

from . import browser_launcher
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

# Playwright page.goto 의 valid wait_until 값. SPA (홈택스 등) 는 본문이
# domcontentloaded 이후 XHR 로 렌더링되므로 호출자가 "networkidle" 을
# 선택할 수 있어야 한다. 기본값은 backward compat 을 위해 보존.
_DEFAULT_WAIT_UNTIL = "domcontentloaded"
_ALLOWED_WAIT_UNTIL: tuple[str, ...] = (
    "commit", "domcontentloaded", "load", "networkidle",
)

# dwell_seconds 는 결과 추출 직후 close 전에 화면을 일시적으로 유지하기 위한
# smoke/debug 전용 옵션이다. 0 이면 즉시 close (기존 동작). 음수/30 초과는
# reject — 무한 keep-open 은 만들지 않는다.
_DEFAULT_DWELL_SECONDS = 0
_MAX_DWELL_SECONDS = 30

_LINKS_SAMPLE_CAP = 20
_BUTTONS_SAMPLE_CAP = 20
_FORMS_SAMPLE_CAP = 10
_INPUTS_TYPE_SAMPLE_CAP = 20

_BLANK_TEXT_THRESHOLD = 80          # 본문 visible text 가 이보다 짧으면 blank_or_empty 후보

# F-2 ``_FORBIDDEN_ENV_VARS`` 와 동치 — 본 observer 도 같은 환경변수가
# 존재하면 Playwright 를 띄우지 않는다.
_FORBIDDEN_ENV_VARS: tuple[str, ...] = browser_launcher._FORBIDDEN_ENV_VARS


# ─── page_state 분류 키워드 ──────────────────────────────────────────────

_LOGIN_TEXT_TOKENS: tuple[str, ...] = (
    "로그인", "sign in", "sign-in", "signin", "log in", "log-in", "login",
    "아이디", "비밀번호",
)
_CAPTCHA_TEXT_TOKENS: tuple[str, ...] = (
    "captcha", "robot", "are you human", "verify you are human",
    "보안문자", "자동입력방지", "자동 입력 방지", "안전한 접속",
    "i'm not a robot", "im not a robot",
)
_ACCESS_DENIED_TEXT_TOKENS: tuple[str, ...] = (
    "access denied", "forbidden", "not authorized", "permission denied",
    "권한 없음", "접근이 거부", "접근 권한이 없",
)
_NOT_FOUND_TEXT_TOKENS: tuple[str, ...] = (
    "not found", "page not found", "404", "찾을 수 없",
)
_DEVELOPER_DOCS_TEXT_TOKENS: tuple[str, ...] = (
    "developers", "developer", "개발자센터", "개발자 센터",
    "documentation", "docs", "api reference", "sdk",
    "rest api", "openapi",
)
_DEVELOPER_DOCS_HOST_TOKENS: tuple[str, ...] = (
    "developers.", "developer.", "docs.", "developer-",
)
_SEARCH_PORTAL_TEXT_TOKENS: tuple[str, ...] = (
    "검색", "뉴스", "메일", "카페", "블로그",
    "search", "news", "webmail",
)

# 은행/공공기관/세무 사이트가 요구하는 보안프로그램 / 인증서 플러그인 /
# 키보드보안 / 브라우저 비호환 / 수동설치 신호. 자동 클릭/다운로드/설치는
# 절대 수행하지 않으며, 본 토큰은 page_state 분류 (manual_action_required)
# 와 ``extract_security_program_signals`` helper 에서 공동 사용한다.
_SECURITY_PROGRAM_TEXT_TOKENS: tuple[str, ...] = (
    "보안프로그램", "통합설치", "보안모듈", "보안 솔루션",
    "프로그램 설치가 필요", "설치 완료 후 새로고침",
    "필수 프로그램 설치",
)
_KEYBOARD_SECURITY_TEXT_TOKENS: tuple[str, ...] = (
    "키보드보안", "보안키패드", "키보드 보안 프로그램",
)
_CERTIFICATE_PLUGIN_TEXT_TOKENS: tuple[str, ...] = (
    "공동인증서 프로그램", "인증서 프로그램", "인증서 보안 프로그램",
    "개인방화벽",
)
_BROWSER_NOT_SUPPORTED_TEXT_TOKENS: tuple[str, ...] = (
    "지원하지 않는 브라우저", "브라우저 확장 프로그램",
    "ActiveX", "Internet Explorer 전용",
    # ".exe" 는 확장자 표기로만 매칭한다. 단순 "EXE" 는 "execute" 등에
    # false-positive 를 일으키므로 사용하지 않는다.
    ".exe",
)
# 단독 "설치" 한 단어로는 분류하지 않는다 — 다른 보안프로그램 신호 토큰이
# 매칭되지 않을 때만, 명시적 "설치하기/수동 설치/설치파일/다운로드 후 설치"
# 같은 동사·문맥 결합 토큰만 manual_install_required 로 분류한다.
_MANUAL_INSTALL_TEXT_TOKENS: tuple[str, ...] = (
    "설치하기", "다운로드 후 설치", "수동 설치", "설치파일",
)


# ─── 결과 빌더 ───────────────────────────────────────────────────────────

def _empty_result(
    *,
    target_url: str,
    error_code: str,
    warnings: list[str],
    page_state: str = "unknown",
) -> dict[str, Any]:
    """Playwright launch 이전 단계 실패용. 결과 스키마는 success 케이스와
    동일 keys 를 유지해 호출자가 분기 없이 dict 접근하도록 한다."""
    return {
        "success": False,
        "error_code": error_code,
        "warnings": list(warnings),
        "target_url": _safe_target_url(target_url),
        "final_url_host_path": "",
        "title": "",
        "status_code": 0,
        "page_state": page_state,
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
        "screenshot_path": None,
    }


def _safe_target_url(url: str) -> str:
    """raw URL 의 query/fragment 를 제거해 host+path 까지만 보존."""
    if not isinstance(url, str) or not url.strip():
        return ""
    try:
        parsed = urlparse(url.strip())
    except Exception:  # noqa: BLE001
        return ""
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        return ""
    host = (parsed.hostname or "").lower()
    if not host:
        return ""
    path = parsed.path or ""
    out = f"{scheme}://{host}{path}"
    return out[:300].rstrip("/") or out[:300]


def _url_host_path(url: str) -> str:
    if not isinstance(url, str) or not url.strip():
        return ""
    try:
        parsed = urlparse(url.strip())
    except Exception:  # noqa: BLE001
        return ""
    host = (parsed.hostname or "").lower()
    if not host:
        return ""
    path = parsed.path or ""
    return (host + path)[:200].rstrip("/")


# ─── 외부 API ────────────────────────────────────────────────────────────

def observe_public_browser_page(
    url: str,
    *,
    site_policy: str = "auto",
    timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    max_text_chars: int = _DEFAULT_MAX_TEXT_CHARS,
    capture_screenshot: bool = False,
    wait_until: str = _DEFAULT_WAIT_UNTIL,
    dwell_seconds: int = _DEFAULT_DWELL_SECONDS,
    headless: bool = False,
    _browser_factory: Optional[Callable[[], Any]] = None,
    _env: Optional[dict] = None,
) -> dict[str, Any]:
    """공개 웹페이지를 fresh BrowserContext 로 열어 read-only 로 관찰.

    URL scheme / Google open-only 도메인 / 금지 환경변수를 launch 전에
    검증하고, Playwright 로 page.goto → title / final_url / content /
    response.status 만 수집한다. 클릭/입력/쿠키/스토리지 접근은 절대
    수행하지 않는다.

    site_policy 는 추후 확장 자리. 현재는 일반 공개 페이지 흐름만 사용.

    headless=True: 자동화 health check 등 UI가 불필요한 경우 사용.
    headless=False(기본): 사용자에게 브라우저 창이 보이는 가시적 모드.

    테스트 편의:
      - ``_browser_factory``: ``sync_playwright`` 대체 (context manager).
      - ``_env``: ``os.environ`` 대체.
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
        )
    target_url = (url or "").strip()

    # 2) Google/YouTube open-only 정책 (F-2 와 동일).
    if browser_launcher.is_google_open_only_url(target_url):
        return _empty_result(
            target_url=target_url,
            error_code="GOOGLE_OPEN_ONLY",
            warnings=["google_open_only_use_open_local_browser"],
            page_state="unknown",
        )

    # 3) 민감 환경변수 차단 (값은 절대 로깅/반영하지 않음).
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
        )

    # 4) 파라미터 정규화.
    timeout_ms_v = _clip_int(
        timeout_ms, _MIN_TIMEOUT_MS, _MAX_TIMEOUT_MS, _DEFAULT_TIMEOUT_MS,
    )
    max_text_chars_v = _clip_int(
        max_text_chars, _MIN_MAX_TEXT_CHARS, _MAX_MAX_TEXT_CHARS,
        _DEFAULT_MAX_TEXT_CHARS,
    )
    capture_screenshot_v = bool(capture_screenshot)

    # 4.5) wait_until 화이트리스트. SPA 사이트는 "networkidle" 권장.
    # 허용외 값은 silent fallback 하지 않고 reject — 잘못된 값을 호출자가
    # 빠르게 알 수 있어야 한다. _safe_target_url 이 이미 query/fragment 를
    # 제거하므로 reject 결과에 민감정보가 새지 않는다.
    if not isinstance(wait_until, str) or wait_until not in _ALLOWED_WAIT_UNTIL:
        return _empty_result(
            target_url=target_url,
            error_code="WAIT_UNTIL_INVALID",
            warnings=["wait_until_invalid"],
        )
    wait_until_v = wait_until

    # 4.6) dwell_seconds — smoke/debug 전용. 0 이면 기존처럼 즉시 close.
    # bool 은 int 의 subclass 라 isinstance(True, int) == True 이므로 명시 차단.
    if isinstance(dwell_seconds, bool) or not isinstance(dwell_seconds, int):
        return _empty_result(
            target_url=target_url,
            error_code="DWELL_SECONDS_INVALID",
            warnings=["dwell_seconds_invalid"],
        )
    if dwell_seconds < 0 or dwell_seconds > _MAX_DWELL_SECONDS:
        return _empty_result(
            target_url=target_url,
            error_code="DWELL_SECONDS_INVALID",
            warnings=["dwell_seconds_invalid"],
        )
    dwell_seconds_v = dwell_seconds

    # 5) Playwright factory 결정.
    factory = _browser_factory
    if factory is None:
        try:
            from playwright.sync_api import sync_playwright as _sync
        except ImportError:
            return _empty_result(
                target_url=target_url,
                error_code="BROWSER_DEPENDENCY_MISSING",
                warnings=["browser_dependency_missing"],
            )
        factory = _sync

    try:
        return _run_observation(
            factory=factory,
            target_url=target_url,
            timeout_ms=timeout_ms_v,
            max_text_chars=max_text_chars_v,
            capture_screenshot=capture_screenshot_v,
            wait_until=wait_until_v,
            dwell_seconds=dwell_seconds_v,
            headless=bool(headless),
        )
    except BrowserDependencyMissing as e:
        return _empty_result(
            target_url=target_url,
            error_code="BROWSER_DEPENDENCY_MISSING",
            warnings=[f"browser_dependency_missing:{type(e).__name__}"],
        )
    except Exception as e:  # pragma: no cover - 실제 런타임 오류
        logger.exception("observe_public_browser_page failed")
        return _empty_result(
            target_url=target_url,
            error_code="BROWSER_OBSERVATION_FAILED",
            warnings=[f"observation_failed:{type(e).__name__}"],
        )


# ─── 내부 ─────────────────────────────────────────────────────────────────

def _run_observation(
    *,
    factory: Callable[[], Any],
    target_url: str,
    timeout_ms: int,
    max_text_chars: int,
    capture_screenshot: bool,
    wait_until: str = _DEFAULT_WAIT_UNTIL,
    dwell_seconds: int = _DEFAULT_DWELL_SECONDS,
    headless: bool = False,
) -> dict[str, Any]:
    warnings: list[str] = []
    launch_kwargs: dict[str, Any] = {"headless": bool(headless)}

    with factory() as pw:
        try:
            browser = pw.chromium.launch(**launch_kwargs)
        except Exception as e:  # pragma: no cover - 실제 런타임 오류
            logger.exception("browser launch failed")
            return _empty_result(
                target_url=target_url,
                error_code="BROWSER_OPEN_FAILED",
                warnings=[f"launch_failed:{type(e).__name__}"],
            )
        try:
            # storage_state 미주입 / cookies 미주입 / persistent profile 미사용.
            context = browser.new_context()
            try:
                page = context.new_page()
                try:
                    response = None
                    try:
                        response = page.goto(
                            target_url,
                            timeout=timeout_ms,
                            wait_until=wait_until,
                        )
                    except Exception as e:
                        warnings.append(f"goto_failed:{type(e).__name__}")
                        return _empty_result(
                            target_url=target_url,
                            error_code="GOTO_FAILED",
                            warnings=warnings,
                        )

                    status_code = _safe_status(response)

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

                    screenshot_path: Optional[str] = None
                    if capture_screenshot:
                        try:
                            screenshot_path = _take_screenshot(page)
                        except Exception as e:
                            screenshot_path = None
                            warnings.append(
                                f"screenshot_failed:{type(e).__name__}",
                            )

                    result = _build_result(
                        target_url=target_url,
                        title=raw_title,
                        final_url=final_url_raw,
                        status_code=status_code,
                        structure=structure,
                        max_text_chars=max_text_chars,
                        screenshot_path=screenshot_path,
                        warnings=warnings,
                    )
                    # smoke/debug 용 화면 유지. 클릭/입력/스크롤/다운로드 없이
                    # 단순 sleep — page 객체는 외부에 노출되지 않는다.
                    if dwell_seconds > 0:
                        try:
                            time.sleep(dwell_seconds)
                        except Exception:  # pragma: no cover - sleep 자체 실패
                            pass
                    return result
                finally:
                    _safe_close(page)
            finally:
                _safe_close(context)
        finally:
            _safe_close(browser)


def _safe_status(response: Any) -> int:
    if response is None:
        return 0
    try:
        s = getattr(response, "status", None)
        if callable(s):
            s = s()
        return int(s) if s is not None else 0
    except Exception:
        return 0


def _take_screenshot(page: Any) -> Optional[str]:
    """capture_screenshot=True 때만 호출. 임시 PNG 파일에 저장하고 경로 반환.

    페이지 본문은 저장하지 않는다 (html / cookies / storage_state 미접근).
    저장 실패 시 None 반환은 호출부에서 warnings 로 기록.
    """
    import tempfile
    fd, path = tempfile.mkstemp(prefix="haehan_observer_", suffix=".png")
    try:
        os.close(fd)
        page.screenshot(path=path, full_page=False)
        return path
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def _build_result(
    *,
    target_url: str,
    title: str,
    final_url: str,
    status_code: int,
    structure: dict[str, Any],
    max_text_chars: int,
    screenshot_path: Optional[str],
    warnings: list[str],
) -> dict[str, Any]:
    title_safe = (title or "")[:300]
    final_host_path = _url_host_path(final_url) or _url_host_path(target_url)

    raw_links = list(structure.get("links") or [])
    raw_buttons = list(structure.get("buttons") or [])
    raw_forms = list(structure.get("forms") or [])
    raw_inputs = list(structure.get("inputs") or [])

    links_sample = _sanitize_links(raw_links)[:_LINKS_SAMPLE_CAP]
    buttons_sample = _sanitize_buttons(raw_buttons)[:_BUTTONS_SAMPLE_CAP]
    forms_sample = _sanitize_forms(raw_forms)[:_FORMS_SAMPLE_CAP]
    input_types = _sanitize_input_types(raw_inputs)[:_INPUTS_TYPE_SAMPLE_CAP]

    text_blob = _build_text_blob(structure)
    text_length = len(text_blob)
    text_excerpt = text_blob[:max_text_chars]

    page_state = _classify_page_state(
        target_url=target_url,
        final_url=final_url,
        title=title_safe,
        status_code=status_code,
        text_blob=text_blob,
        structure=structure,
        forms_sample=forms_sample,
    )

    success = _is_success_status(status_code)
    error_code = "" if success else _error_code_from_status(status_code)

    return {
        "success": bool(success),
        "error_code": error_code,
        "warnings": list(warnings),
        "target_url": _safe_target_url(target_url),
        "final_url_host_path": final_host_path,
        "title": title_safe,
        "status_code": int(status_code),
        "page_state": page_state,
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
        "screenshot_path": screenshot_path if screenshot_path else None,
    }


def _is_success_status(status_code: int) -> bool:
    """200~399 는 success. 0 (status 추출 실패 — about:blank 등) 도 success
    로 본다 (page.content 가 빈 문자열이라도 build_result 가 정상 페이지로
    classify 가능)."""
    if status_code == 0:
        return True
    return 200 <= status_code < 400


def _error_code_from_status(status_code: int) -> str:
    if status_code == 404:
        return "PAGE_NOT_FOUND"
    if 400 <= status_code < 500:
        return f"HTTP_{status_code}"
    if 500 <= status_code:
        return f"HTTP_{status_code}"
    return f"HTTP_{status_code}"


# ─── sanitize helpers (raw URL query/fragment / value 제거) ──────────────

_QUERY_FRAG_RE = re.compile(r"[?#].*$")


def _strip_query_fragment(href: str) -> str:
    if not isinstance(href, str):
        return ""
    return _QUERY_FRAG_RE.sub("", href.strip())[:300]


def _sanitize_links(links: list[dict]) -> list[dict]:
    out: list[dict] = []
    for link in links:
        if not isinstance(link, dict):
            continue
        text = (link.get("text") or "")[:200]
        href_raw = link.get("normalized_href") or link.get("href") or ""
        href = _strip_query_fragment(href_raw)
        out.append({
            "text": text,
            "href": href,
            "risk_hint": link.get("risk_hint", ""),
        })
    return out


def _sanitize_buttons(buttons: list[dict]) -> list[dict]:
    out: list[dict] = []
    for btn in buttons:
        if not isinstance(btn, dict):
            continue
        text = (btn.get("text") or "")[:200]
        out.append({
            "text": text,
            "type": (btn.get("type") or "")[:40],
            "risk_level": (btn.get("risk_level") or "")[:40],
        })
    return out


def _sanitize_forms(forms: list[dict]) -> list[dict]:
    """form 메타데이터만. action 의 query/fragment 제거. 입력 value 미수집."""
    out: list[dict] = []
    for form in forms:
        if not isinstance(form, dict):
            continue
        action = _strip_query_fragment(form.get("action") or "")
        out.append({
            "action": action,
            "method": (form.get("method") or "")[:10],
            "has_password": bool(form.get("has_password")),
            "input_count": int(form.get("input_count") or 0),
            "risk_level": (form.get("risk_level") or "")[:40],
        })
    return out


def _sanitize_input_types(inputs: list[dict]) -> list[str]:
    """input value 는 절대 수집하지 않는다 — type 토큰만 카운트."""
    seen: dict[str, int] = {}
    for inp in inputs:
        if not isinstance(inp, dict):
            continue
        t = (inp.get("type") or "").strip().lower()
        if not t:
            t = "text"
        seen[t] = seen.get(t, 0) + 1
    return [f"{t}:{c}" for t, c in seen.items()]


def _build_text_blob(structure: dict) -> str:
    chunks: list[str] = []
    pt = (structure.get("page_title") or "").strip()
    if pt:
        chunks.append(pt)
    for h in (structure.get("headings") or []):
        if isinstance(h, dict):
            t = (h.get("text") or "").strip()
            if t:
                chunks.append(t)
    for link in (structure.get("links") or []):
        if isinstance(link, dict):
            t = (link.get("text") or "").strip()
            if t:
                chunks.append(t)
    for btn in (structure.get("buttons") or []):
        if isinstance(btn, dict):
            t = (btn.get("text") or "").strip()
            if t:
                chunks.append(t)
    for tbl in (structure.get("tables") or []):
        if isinstance(tbl, dict):
            for hd in (tbl.get("headers") or []):
                if isinstance(hd, str):
                    hd_s = hd.strip()
                    if hd_s:
                        chunks.append(hd_s)
    return " ".join(chunks)


# ─── page_state 분류 ────────────────────────────────────────────────────

def _classify_page_state(
    *,
    target_url: str,
    final_url: str,
    title: str,
    status_code: int,
    text_blob: str,
    structure: dict,
    forms_sample: list[dict],
) -> str:
    """규칙 기반 1차 분류. 우선순위 (높음→낮음):

      1) status_code 404                       → not_found
      2) status_code >= 500                    → server_error
      3) captcha 토큰                          → captcha_or_bot_check
      4a) 보안프로그램 토큰                    → security_program_required
      4b) 키보드보안 토큰                      → keyboard_security_required
      4c) 인증서 플러그인 토큰                 → certificate_plugin_required
      4d) 브라우저 비호환 토큰                 → browser_not_supported
      4e) 수동 설치 토큰 (다른 4a~4d 미매칭)   → manual_install_required
      5) access denied 토큰                    → access_denied
      6) login 토큰 + password input           → login_required
      7) developer docs 토큰 (host or text)    → developer_docs
      8) search portal 토큰                    → search_portal
      9) visible text 거의 없음                → blank_or_empty
     10) 그 외                                  → public_page

    4a~4e (manual_action_required 군) 정책:
      captcha 다음, access_denied 앞에서 검사한다. 사용자가 직접 보안프로그램/
      인증서 플러그인을 설치한 뒤 재시도하는 흐름이며, 자동 클릭/다운로드/
      설치/silent install/관리자 권한 실행/보안모듈 우회는 일체 수행하지
      않는다. 본 분류기는 read-only 신호 매칭만 한다.
    """
    text_lower = (text_blob or "").lower()
    title_lower = (title or "").lower()
    final_url_lower = (final_url or "").lower()

    # 1) 404
    if status_code == 404:
        return "not_found"
    # 2) 5xx
    if status_code >= 500:
        return "server_error"
    # 3) captcha — 신호 강. 다른 분류보다 먼저 검사.
    if _has_any_token(text_lower, _CAPTCHA_TEXT_TOKENS) or \
            _has_any_token(title_lower, _CAPTCHA_TEXT_TOKENS):
        return "captcha_or_bot_check"
    # 4) 보안프로그램/인증서 플러그인/키보드보안/브라우저 비호환/수동 설치.
    #    captcha 다음, access_denied 앞에서 검사한다.
    #    a~d 의 강한 신호가 있으면 manual_install_required 보다 우선한다.
    sec_state = _classify_security_program_state(
        text_lower=text_lower, title_lower=title_lower,
    )
    if sec_state:
        return sec_state
    # 5) access denied — captcha / 보안프로그램 다음.
    if _has_any_token(text_lower, _ACCESS_DENIED_TEXT_TOKENS) or \
            _has_any_token(title_lower, _ACCESS_DENIED_TEXT_TOKENS):
        return "access_denied"
    # 4.5) HTTP 4xx (404/captcha/access denied 외)
    if 400 <= status_code < 500:
        return "access_denied"
    # 5) login required = login 토큰 + password input
    has_password_input = any(
        bool(f.get("has_password")) for f in forms_sample
    )
    if has_password_input and (
        _has_any_token(text_lower, _LOGIN_TEXT_TOKENS)
        or _has_any_token(title_lower, _LOGIN_TEXT_TOKENS)
    ):
        return "login_required"
    # text 가 비었더라도 password 만으로도 login_required 로 판정 (HTML 전체가
    # 로그인 입력만 있는 미니 페이지 케이스).
    if has_password_input:
        return "login_required"
    # 6) developer docs — host 토큰 우선, 그다음 text.
    host = ""
    try:
        host = (urlparse(final_url or target_url).hostname or "").lower()
    except Exception:
        host = ""
    if any(host.startswith(t) or ("." + t.rstrip(".")) in host
           for t in _DEVELOPER_DOCS_HOST_TOKENS):
        return "developer_docs"
    if _has_any_token(text_lower, _DEVELOPER_DOCS_TEXT_TOKENS) or \
            _has_any_token(title_lower, _DEVELOPER_DOCS_TEXT_TOKENS):
        return "developer_docs"
    # 7) search/portal — 단순 토큰 매칭.
    if _has_any_token(text_lower, _SEARCH_PORTAL_TEXT_TOKENS) or \
            _has_any_token(title_lower, _SEARCH_PORTAL_TEXT_TOKENS):
        return "search_portal"
    # 8) blank / empty
    if len(text_blob.strip()) < _BLANK_TEXT_THRESHOLD:
        return "blank_or_empty"
    # 9) 일반 공개 페이지
    return "public_page"


def _has_any_token(haystack: str, tokens: tuple[str, ...]) -> bool:
    if not haystack:
        return False
    for t in tokens:
        if not t:
            continue
        if t in haystack:
            return True
    return False


def _has_any_token_ci(haystack: str, tokens: tuple[str, ...]) -> bool:
    """case-insensitive 매칭. browser_not_supported 토큰처럼 영문 대소문자
    혼합 (ActiveX/activex/EXE) 이 섞일 때 사용. 한글 토큰에는 영향 없음."""
    if not haystack:
        return False
    h = haystack.lower()
    for t in tokens:
        if not t:
            continue
        if t.lower() in h:
            return True
    return False


def _classify_security_program_state(
    *, text_lower: str, title_lower: str,
) -> str:
    """보안프로그램/인증서 플러그인/키보드보안/브라우저 비호환/수동 설치 분류.

    매칭 시 page_state 문자열을 반환, 어디에도 매칭 안 되면 빈 문자열.

    내부 우선순위 (a → e):
      a) security_program_required        — 강한 신호 (보안프로그램, 통합설치 등)
      b) keyboard_security_required       — 키보드보안 / 보안키패드
      c) certificate_plugin_required      — 인증서 프로그램 / 개인방화벽
      d) browser_not_supported            — 지원하지 않는 브라우저 / ActiveX
      e) manual_install_required          — a~d 미매칭 시에만, 명시적 설치 토큰

    "설치" 단독 단어로는 분류하지 않는다 — manual_install_required 토큰은
    "설치하기/수동 설치/설치파일/다운로드 후 설치" 처럼 동사·문맥 결합형만
    포함되어 있다. 일반 페이지에서 "설치" 가 단순 언급될 때 과분류되지
    않게 하기 위함이다.
    """
    if _has_any_token(text_lower, _SECURITY_PROGRAM_TEXT_TOKENS) or \
            _has_any_token(title_lower, _SECURITY_PROGRAM_TEXT_TOKENS):
        return "security_program_required"
    if _has_any_token(text_lower, _KEYBOARD_SECURITY_TEXT_TOKENS) or \
            _has_any_token(title_lower, _KEYBOARD_SECURITY_TEXT_TOKENS):
        return "keyboard_security_required"
    if _has_any_token(text_lower, _CERTIFICATE_PLUGIN_TEXT_TOKENS) or \
            _has_any_token(title_lower, _CERTIFICATE_PLUGIN_TEXT_TOKENS):
        return "certificate_plugin_required"
    if _has_any_token_ci(text_lower, _BROWSER_NOT_SUPPORTED_TEXT_TOKENS) or \
            _has_any_token_ci(title_lower, _BROWSER_NOT_SUPPORTED_TEXT_TOKENS):
        return "browser_not_supported"
    if _has_any_token(text_lower, _MANUAL_INSTALL_TEXT_TOKENS) or \
            _has_any_token(title_lower, _MANUAL_INSTALL_TEXT_TOKENS):
        return "manual_install_required"
    return ""


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


# ─── 보안프로그램 신호 추출 helper ───────────────────────────────────────

# helper 출력 길이 상한 (홈택스 어댑터와 동일 수준).
_SP_OUT_TEXT_CAP = 200
_SP_OUT_HREF_CAP = 300

# detected_programs 에서 short token 한 단어로는 잡지 않을 키워드. 단순
# "설치하기" 만 본 페이지에 있어도 "감지된 프로그램명" 으로 보고하는 건
# 의미가 약하므로 detected_programs 에는 강한 신호 토큰만 포함한다.
_DETECTED_PROGRAM_TOKENS: tuple[str, ...] = (
    *_SECURITY_PROGRAM_TEXT_TOKENS,
    *_KEYBOARD_SECURITY_TEXT_TOKENS,
    *_CERTIFICATE_PLUGIN_TEXT_TOKENS,
    "ActiveX", "Internet Explorer 전용", ".exe",
)

# install_links 추출 시 link text 가 "설치/다운로드" 류 토큰을 포함해야
# 한다 — 일반 페이지의 모든 a 태그를 "install_link" 로 보고하지 않기 위함.
_INSTALL_LINK_TEXT_TOKENS: tuple[str, ...] = (
    "설치", "다운로드", "통합설치", "보안프로그램", "키보드보안",
    "보안키패드", "공동인증서", "인증서 프로그램", "개인방화벽",
    "install", "download",
)


def extract_security_program_signals(observer_result: Any) -> dict[str, Any]:
    """observer 결과에서 보안프로그램 / 인증서 / 키보드보안 / 브라우저 비호환
    / 수동 설치 신호를 read-only 로 추출.

    pure dict-in / dict-out — 본 helper 는 브라우저를 새로 열지 않고, 클릭/
    다운로드/설치/JS 실행을 일체 수행하지 않는다. 입력은 ``observer_result``
    dict 의 ``page_state`` / ``title`` / ``text_excerpt`` / ``links`` /
    ``buttons`` 만 사용한다.

    출력 스키마 (사용자 정책 §보고 스키마와 일치):
      {
        "page_state":             "...",                  # observer 가 분류한 값
        "manual_action_required": True / False,
        "detected_programs":      ["키보드보안", "공동인증서 프로그램", ...],
        "install_links":          [{"text": "...", "href": "..."}, ...],
        "warnings":               ["manual_security_program_install_required",
                                   ...],
      }

    원칙:
      - href 는 query/fragment 가 제거된 값만 사용한다 (observer 가 이미
        한 번 제거하지만 helper 도 한 번 더 방어).
      - input value / cookie / storage_state / 비밀값은 절대 출력하지
        않는다.
      - 보안프로그램 자동 설치는 본 helper 의 책임이 아니며, 어떤 경우에도
        만들지 않는다. install_links 는 "사용자가 직접 클릭해서 설치할
        수 있는 후보 링크" 만 보고 목적으로 노출한다.
    """
    if not isinstance(observer_result, dict):
        return _empty_security_signal_result(["observer_result_not_dict"])

    warnings: list[str] = []

    page_state = observer_result.get("page_state")
    if not isinstance(page_state, str):
        page_state = ""

    title = observer_result.get("title") or ""
    if not isinstance(title, str):
        title = ""
    text_excerpt = observer_result.get("text_excerpt") or ""
    if not isinstance(text_excerpt, str):
        text_excerpt = ""

    links = observer_result.get("links")
    if not isinstance(links, list):
        if links is not None:
            warnings.append("links_not_list")
        links = []

    buttons = observer_result.get("buttons")
    if not isinstance(buttons, list):
        if buttons is not None:
            warnings.append("buttons_not_list")
        buttons = []

    blob_parts = [title, text_excerpt]
    for link in links:
        if isinstance(link, dict):
            t = link.get("text") or ""
            if isinstance(t, str) and t:
                blob_parts.append(t)
    for btn in buttons:
        if isinstance(btn, dict):
            t = btn.get("text") or ""
            if isinstance(t, str) and t:
                blob_parts.append(t)
    blob_lower = " ".join(blob_parts).lower()

    detected_programs = _detect_program_names(blob_lower)
    install_links = _extract_install_links(links)

    is_security_state = page_state in _MANUAL_ACTION_PAGE_STATES
    has_signal = bool(detected_programs) or bool(install_links)
    manual_action_required = is_security_state or has_signal

    if manual_action_required:
        warnings.append("manual_security_program_install_required")

    return {
        "page_state": page_state,
        "manual_action_required": bool(manual_action_required),
        "detected_programs": detected_programs,
        "install_links": install_links,
        "warnings": warnings,
    }


# 보안프로그램 군 page_state 셋. 분류기 / helper / trusted policy 가 공유.
_MANUAL_ACTION_PAGE_STATES: frozenset[str] = frozenset({
    "security_program_required",
    "keyboard_security_required",
    "certificate_plugin_required",
    "browser_not_supported",
    "manual_install_required",
})


def manual_action_page_states() -> frozenset[str]:
    """다른 모듈 (trusted_browser_policy 등) 이 본 set 을 import 해
    REQUIRES_USER_PRESENCE 등에 통합할 수 있도록 한 진입점 노출."""
    return _MANUAL_ACTION_PAGE_STATES


def _detect_program_names(blob_lower: str) -> list[str]:
    """blob 안에서 발견된 강한 토큰만 detected_programs 로 반환.

    ".exe" / "ActiveX" 처럼 영문 대소문자 혼합 토큰은 case-insensitive
    매칭하지만, 출력은 원래 토큰 문자열을 그대로 보존해 "사용자가 본
    화면에서 본 표기" 와 가까운 형태로 보고한다.
    """
    if not blob_lower:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for tok in _DETECTED_PROGRAM_TOKENS:
        if not tok:
            continue
        if tok.lower() in blob_lower and tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


def _extract_install_links(links: list[Any]) -> list[dict[str, str]]:
    """observer 가 sanitize 한 links 중 "설치/다운로드" 토큰이 텍스트에
    포함된 후보만 추출. href 는 query/fragment 한 번 더 제거하고 길이 상한.

    raw URL / cookie / storage / value 는 절대 출력하지 않는다.
    """
    out: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str]] = set()
    for link in links:
        if not isinstance(link, dict):
            continue
        text = link.get("text") or ""
        if not isinstance(text, str):
            text = ""
        href_raw = link.get("href") or ""
        if not isinstance(href_raw, str):
            href_raw = ""
        # observer 가 이미 query/fragment 를 제거하지만 한 번 더 방어.
        href = _QUERY_FRAG_RE.sub("", href_raw.strip())[:_SP_OUT_HREF_CAP]
        text_l = text.lower()
        if not _has_any_token(text_l, _INSTALL_LINK_TEXT_TOKENS):
            continue
        key = (text[:_SP_OUT_TEXT_CAP], href)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out.append({
            "text": text[:_SP_OUT_TEXT_CAP],
            "href": href,
        })
    return out


def _empty_security_signal_result(warnings: list[str]) -> dict[str, Any]:
    return {
        "page_state": "",
        "manual_action_required": False,
        "detected_programs": [],
        "install_links": [],
        "warnings": list(warnings),
    }


__all__ = [
    "observe_public_browser_page",
    "extract_security_program_signals",
    "manual_action_page_states",
]
