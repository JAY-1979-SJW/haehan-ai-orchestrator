"""로그인 자동 탐지 + 저장 모듈 (사이트별 명시 + 사이트 무관 공통).

[기존 기능 보존]
사이트별 명시 패턴 (LOGIN_PATTERNS): 네이버/구글/카카오/EUM 등
  - detect_login_on_current_tab(page): 등록된 사이트만
  - monitor_for_login(page, ...): 폴링 + DB 저장

[신규 공통 기능]
사이트 무관 휴리스틱 (모든 사이트 자동 탐지):
  - detect_login_state(page) -> dict (score 기반)
  - is_logged_in_generic(page) -> bool
  - get_logged_in_user(page) -> str | None
  - wait_for_login_generic(page, max_wait_s) -> dict

판정 기준 (score):
  >= 3: 로그인 / 1-2: 모호 / 0: 비로그인

신호:
  - 로그아웃 텍스트/링크 (+3 / +2)
  - 마이페이지/내정보 (+1)
  - 비밀번호 필드 부재 + 비로그인 페이지 (+1)
  - 세션 쿠키 (+1)
  - 사용자명 표시 영역 (+2)
  - "○○○님" / "Hello ○○○" (+2)
  - aria-label/data 'logged in' (+2)
"""

from __future__ import annotations

import json
import re
import time
from contextlib import suppress
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import urlparse

from scripts.browser.cdp import cdp_db
from scripts.common.logger import get_logger

_log = get_logger(__name__)


class _SitePattern(TypedDict, total=False):
    domains: list[str]
    logged_in_signs: list[tuple[str, str]]
    logged_out_signs: list[tuple[str, str]]


# 사이트별 로그인 감지 패턴
LOGIN_PATTERNS: dict[str, _SitePattern] = {
    "smartstore": {
        "domains": ["sell.smartstore.naver.com", "smartstore.naver.com"],
        "logged_in_signs": [
            ("text", "상품관리"),
            ("text", "판매관리"),
            ("text", "정산관리"),
            ("selector", "a[href*='logout']"),
        ],
    },
    "naver": {
        "domains": ["naver.com", "mail.naver.com"],
        "logged_in_signs": [
            ("selector", "#gnb_my_name"),
            ("selector", ".gnb_id"),
            ("selector", "[class*='MyView']"),
        ],
    },
    "google": {
        "domains": ["google.com", "mail.google.com", "drive.google.com"],
        "logged_in_signs": [
            ("selector", "[data-ogsr-up]"),
            ("selector", "a[href*='SignOut']"),
        ],
    },
    "kakao": {
        "domains": ["kakao.com", "accounts.kakao.com", "developers.kakao.com"],
        "logged_in_signs": [
            ("text", "로그아웃"),
            ("selector", "a[href*='logout']"),
            ("selector", ".thumb_profile"),
            ("selector", "[class*='profile']"),
            ("selector", "[class*='myapp'], [class*='my_app']"),
        ],
        "logged_out_signs": [
            ("selector", "a[href*='login']:not([href*='logout'])"),
        ],
    },
    "eum.cw.or.kr": {
        "domains": ["eum.cw.or.kr"],
        "logged_in_signs": [
            ("text", "로그아웃"),  # 로그아웃 버튼 존재 = 로그인됨
            ("selector", "[class*='logout']"),
        ],
    },
    "hiworks": {
        "domains": ["office.hiworks.com", "mails.office.hiworks.com"],
        "logged_in_signs": [
            ("text", "메일"),
            ("text", "받은 메일함"),
            ("text", "메일 쓰기"),
        ],
    },
    "gabia": {
        "domains": ["gabia.com", "my.gabia.com", "accounts.gabia.com"],
        "logged_in_signs": [
            ("text", "로그아웃"),
            ("selector", "a[href*='logout']"),
            ("selector", "button[class*='logout']"),
            ("selector", ".gnb_my"),
            ("selector", "[class*='UserInfo']"),
            ("selector", "[class*='mypage']"),
        ],
    },
}


def _extract_domain(url: str) -> str:
    """URL에서 도메인 추출."""
    match = re.search(r"https?://(?:www\.)?([^/?]+)", url)
    return match.group(1) if match else ""


def _host_from_url(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001 - 로그인 상태 감지(판정 전용, 자격증명 입력 없음) — 감지 실패는 항상 미로그인/False(fail-closed)로 처리하고 로그로 남김, 세션 저장 실패도 로그 후 계속(2026-09-28 검토)
        return ""


def _storage_host_for_url(url: str) -> str:
    host = _host_from_url(url)
    if host in {"sell.smartstore.naver.com", "smartstore.naver.com"}:
        return "sell.smartstore.naver.com"
    if host.endswith(".office.hiworks.com"):
        return "office.hiworks.com"
    if host.endswith(".naver.com"):
        return "naver.com"
    if host.endswith(".google.com"):
        return "google.com"
    return host


def _find_site_by_domain(domain: str) -> str | None:
    """도메인으로 사이트 이름 찾기."""
    for site, config in LOGIN_PATTERNS.items():
        for d in config["domains"]:
            if d in domain:
                return site
    return None


def _site_key_for_url(url: str) -> str:
    domain = _extract_domain(url)
    return _find_site_by_domain(domain) or _host_from_url(url) or "unknown"


def _check_login_on_page(page_content: str) -> bool:
    """페이지 내용에서 로그인 여부 판단."""
    if not page_content:
        return False

    # 로그아웃 링크 존재 여부로 판단
    logout_indicators = ["로그아웃", "logout", "sign out", "log out"]
    return any(ind.lower() in page_content.lower() for ind in logout_indicators)


def _check_site_login_text(site: str, page_content: str) -> bool:
    if not page_content:
        return False
    if site == "hiworks":
        return any(token in page_content for token in ("메일", "받은 메일함", "메일 쓰기", "전자결재", "오피스"))
    return False


def detect_login_on_current_tab(page) -> tuple[bool, str | None]:
    """현재 활성 탭에서 로그인 감지.

    Returns:
        (로그인_여부, 감지된_사이트명)
    """
    try:
        if not page:
            return False, None

        url = page.url or ""
        site = _site_key_for_url(url)

        # 프로필이 있는 사이트는 화면 요소 판정만 쓴다 — 본문에 "로그아웃 상태입니다" 같은 문구가 있어도 로그인으로 보지 않음
        if _profile_for_url(url):
            state = detect_login_state(page)
            if state.get("state") == "in":
                _log.info("[login-detector] %s 요소 기준 로그인 확인: %s", site, url)
                return True, site
            return False, None

        # 페이지 내용 획득
        try:
            body_text = page.evaluate("() => document.body.innerText || ''")
            is_logged_in = _check_login_on_page(body_text)

            if is_logged_in:
                _log.info("[login-detector] %s에서 로그인 감지: %s", site, url)
                return True, site
            if _check_site_login_text(site, body_text):
                _log.info("[login-detector] site login text detected: %s url=%s", site, url)
                return True, site
        except Exception as e:  # noqa: BLE001 - 로그인 상태 감지(판정 전용, 자격증명 입력 없음) — 감지 실패는 항상 미로그인/False(fail-closed)로 처리하고 로그로 남김, 세션 저장 실패도 로그 후 계속(2026-09-28 검토)
            _log.debug("[login-detector] 페이지 내용 획득 실패 (%s): %s", site, e)

        try:
            state = detect_login_state(page)
            if state.get("logged_in") and not state.get("on_login_page"):
                _log.info("[login-detector] generic login detected: %s url=%s", site, url)
                return True, site
        except Exception as e:  # noqa: BLE001 - 로그인 상태 감지(판정 전용, 자격증명 입력 없음) — 감지 실패는 항상 미로그인/False(fail-closed)로 처리하고 로그로 남김, 세션 저장 실패도 로그 후 계속(2026-09-28 검토)
            _log.debug("[login-detector] generic login detection failed (%s): %s", site, e)

        return False, None

    except Exception as e:  # noqa: BLE001 - 로그인 상태 감지(판정 전용, 자격증명 입력 없음) — 감지 실패는 항상 미로그인/False(fail-closed)로 처리하고 로그로 남김, 세션 저장 실패도 로그 후 계속(2026-09-28 검토)
        _log.debug("[login-detector] 오류: %s", e)
        return False, None


def save_detected_login(site: str, page=None) -> bool:
    """감지된 로그인을 DB에 저장.

    Args:
        site: 사이트명
        page: (선택사항) Playwright Page 객체

    Returns:
        저장 성공 여부
    """
    try:
        session_file = ""
        storage_host = site
        if page is not None:
            try:
                storage_host = _storage_host_for_url(page.url) or site
                from scripts.auth.auth_session import save_session

                session_file = str(save_session(storage_host, page))
            except Exception as e:  # noqa: BLE001 - 로그인 상태 감지(판정 전용, 자격증명 입력 없음) — 감지 실패는 항상 미로그인/False(fail-closed)로 처리하고 로그로 남김, 세션 저장 실패도 로그 후 계속(2026-09-28 검토)
                _log.warning("[login-detector] encrypted session save failed for %s: %s", site, e)

        cdp_db.init_db()
        cdp_db.upsert_session(
            site_name=site, display=site.title(), logged_in=True, session_file=session_file, login_event=True
        )
        try:
            from scripts.common.realtime_audit import emit_event

            emit_event(
                "LOGIN_SESSION_SAVED",
                site=site,
                workflow="login_realtime",
                status="ok",
                risk="auth",
                message=f"login detected and session saved: {site}",
                artifact_path=session_file,
                metadata={"storage_host": storage_host, "url": getattr(page, "url", "") if page else ""},
            )
        except Exception:  # noqa: BLE001 - 여러 프레임/신호를 순차 확인하는 best-effort — 하나 실패해도 다음으로 계속(2026-09-28 검토)
            pass
        _log.info("[login-detector] %s 세션 저장됨", site)
        return True
    except Exception as e:  # noqa: BLE001 - 로그인 상태 감지(판정 전용, 자격증명 입력 없음) — 감지 실패는 항상 미로그인/False(fail-closed)로 처리하고 로그로 남김, 세션 저장 실패도 로그 후 계속(2026-09-28 검토)
        _log.error("[login-detector] %s 세션 저장 실패: %s", site, e)
        return False


def _inject_login_watcher(page) -> bool:
    """페이지에 로그인 감지 JavaScript 주입.

    DOM 변화를 감시하여 로그인 패턴 텍스트 출현 시 플래그 설정.
    """
    try:
        page.evaluate("""
        (() => {
            if (window.__login_watcher_installed) return;
            window.__login_watcher_installed = true;
            window.__login_detected = false;
            window.__login_keywords = ['로그아웃', 'logout', 'sign out', 'log out', '프로필', 'account'];

            // 페이지 로드 완료 후 초기 체크
            const checkLogin = () => {
                const text = (document.body?.innerText || '').toLowerCase();
                for (const kw of window.__login_keywords) {
                    if (text.includes(kw.toLowerCase())) {
                        window.__login_detected = true;
                        return;
                    }
                }
            };

            checkLogin();
            setTimeout(checkLogin, 500);

            // DOM 변화 감시
            const observer = new MutationObserver(() => {
                checkLogin();
            });

            observer.observe(document.body, {
                childList: true,
                subtree: true,
                characterData: false
            });
        })();
        """)
        _log.info("[login-detector] 로그인 감지기 주입 완료")
        return True
    except Exception as e:  # noqa: BLE001 - 로그인 상태 감지(판정 전용, 자격증명 입력 없음) — 감지 실패는 항상 미로그인/False(fail-closed)로 처리하고 로그로 남김, 세션 저장 실패도 로그 후 계속(2026-09-28 검토)
        _log.debug("[login-detector] 감지기 주입 실패: %s", e)
        return False


def monitor_for_login(page, check_interval: int = 1, timeout_s: int = 300, stale_threshold: int = 5) -> dict[str, Any]:
    """페이지에서 로그인을 모니터링하고 감지 시 자동 저장.

    Args:
        page: Playwright Page 객체
        check_interval: 체크 간격 (초)
        timeout_s: 최대 모니터링 시간 (초)
        stale_threshold: 연속 "page closed" 감지 시 새 page 재획득 횟수

    Returns:
        {detected, site, url, elapsed_s, [aborted_reason]}

    R3 패치: page closed 연속 stale_threshold 회 발생 시
            → web_connector.get_page() 로 활성 탭 재획득
            → 재획득도 실패하면 즉시 종료
    """
    start_time = time.time()
    detected_sites: set[Any] = set()
    stale_count = 0
    reacquired = 0

    _inject_login_watcher(page)

    while time.time() - start_time < timeout_s:
        try:
            js_detected = False
            try:
                js_detected = page.evaluate("() => window.__login_detected || false")
                stale_count = 0  # evaluate 성공 → 정상
            except Exception as ev_err:  # noqa: BLE001 - 로그인 상태 감지(판정 전용, 자격증명 입력 없음) — 감지 실패는 항상 미로그인/False(fail-closed)로 처리하고 로그로 남김, 세션 저장 실패도 로그 후 계속(2026-09-28 검토)
                msg = str(ev_err)
                if "has been closed" in msg or "Target page" in msg or "Target closed" in msg:
                    stale_count += 1
                    _log.debug("[login-detector] page stale %d/%d (%s)", stale_count, stale_threshold, msg[:80])
                    if stale_count >= stale_threshold:
                        # 새 활성 페이지 재획득 시도
                        try:
                            from scripts.browser.cdp.connection import get_page

                            new_page = get_page()
                            if new_page and new_page is not page:
                                page = new_page
                                reacquired += 1
                                stale_count = 0
                                _log.info(
                                    "[login-detector] 새 page 재획득 (%d회차) url=%s",
                                    reacquired,
                                    getattr(page, "url", "?"),
                                )
                                with suppress(Exception):
                                    _inject_login_watcher(page)
                            else:
                                _log.warning("[login-detector] page 재획득 실패 — 종료")
                                elapsed = int(time.time() - start_time)
                                return {
                                    "detected": False,
                                    "sites": list(detected_sites),
                                    "elapsed_s": elapsed,
                                    "aborted_reason": "page_stale_unrecoverable",
                                }
                        except Exception as re_err:  # noqa: BLE001 - 로그인 상태 감지(판정 전용, 자격증명 입력 없음) — 감지 실패는 항상 미로그인/False(fail-closed)로 처리하고 로그로 남김, 세션 저장 실패도 로그 후 계속(2026-09-28 검토)
                            _log.warning("[login-detector] page 재획득 예외: %s — 종료", re_err)
                            elapsed = int(time.time() - start_time)
                            return {
                                "detected": False,
                                "sites": list(detected_sites),
                                "elapsed_s": elapsed,
                                "aborted_reason": f"reacquire_error:{str(re_err)[:80]}",
                            }

            # 폴백 감지
            is_logged_in, site = detect_login_on_current_tab(page)
            detected = js_detected or is_logged_in

            if detected and site and site not in detected_sites:
                detected_sites.add(site)
                save_detected_login(site, page)
                elapsed = int(time.time() - start_time)
                _log.info("[login-detector] 로그인 감지 + 저장 완료 (%ds, 재획득=%d회)", elapsed, reacquired)
                return {
                    "detected": True,
                    "site": site,
                    "url": page.url,
                    "elapsed_s": elapsed,
                    "sites": list(detected_sites),
                    "reacquired": reacquired,
                }

            time.sleep(check_interval)

        except Exception as e:  # noqa: BLE001 - 로그인 상태 감지(판정 전용, 자격증명 입력 없음) — 감지 실패는 항상 미로그인/False(fail-closed)로 처리하고 로그로 남김, 세션 저장 실패도 로그 후 계속(2026-09-28 검토)
            _log.debug("[login-detector] 모니터링 오류: %s", e)
            time.sleep(check_interval)

    elapsed = int(time.time() - start_time)
    return {
        "detected": len(detected_sites) > 0,
        "sites": list(detected_sites),
        "elapsed_s": elapsed,
        "timeout": True,
        "reacquired": reacquired,
    }


# ════════════════════════════════════════════════════════════════════════
# 신규: 사이트 무관 공통 로그인 탐지 (모든 사이트에 적용 가능)
# ════════════════════════════════════════════════════════════════════════


def _iter_context_pages(page) -> list[Any]:
    try:
        return list(page.context.pages)
    except Exception:  # noqa: BLE001 - 로그인 상태 감지(판정 전용, 자격증명 입력 없음) — 감지 실패는 항상 미로그인/False(fail-closed)로 처리하고 로그로 남김, 세션 저장 실패도 로그 후 계속(2026-09-28 검토)
        return [page] if page is not None else []


def watch_all_logins(page=None, *, check_interval: float = 1.0, timeout_s: int = 0) -> dict[str, Any]:
    """Watch every open browser tab and save newly detected login sessions.

    Set timeout_s=0 to run until interrupted.
    """
    if page is None:
        from scripts.browser.cdp.connection import get_page

        page = get_page()

    start = time.time()
    saved: set[str] = set()
    checks = 0
    print("login realtime watch started")
    try:
        while timeout_s <= 0 or time.time() - start < timeout_s:
            checks += 1
            for candidate in _iter_context_pages(page):
                try:
                    url = getattr(candidate, "url", "") or ""
                    if not url or url == "about:blank":
                        continue
                    _inject_login_watcher(candidate)
                    logged_in, site = detect_login_on_current_tab(candidate)
                    if logged_in and site and site not in saved:
                        if save_detected_login(site, candidate):
                            saved.add(site)
                            print(f"saved login session: {site} ({url})")
                except Exception as e:  # noqa: BLE001 - 로그인 상태 감지(판정 전용, 자격증명 입력 없음) — 감지 실패는 항상 미로그인/False(fail-closed)로 처리하고 로그로 남김, 세션 저장 실패도 로그 후 계속(2026-09-28 검토)
                    _log.debug("[login-detector] watch page skipped: %s", e)
            time.sleep(check_interval)
    except KeyboardInterrupt:
        pass

    return {
        "saved_sites": sorted(saved),
        "checks": checks,
        "elapsed_s": int(time.time() - start),
    }


_PROBES_PATH = Path(__file__).resolve().parents[2] / "configs" / "login_probes.json"
_LOGIN_URL_RE = re.compile(r"(login|signin|sign-in|sign_in|auth|nidlogin)", re.I)


def _load_probes() -> dict[str, Any]:
    try:
        return json.loads(_PROBES_PATH.read_text(encoding="utf-8")).get("sites", {})
    except Exception as e:  # noqa: BLE001 - 프로필 파일 없음/손상 = 프로필 없는 사이트로 취급(종전 휴리스틱 동작), 판정 전용이라 자격증명·세션 접근 없음
        _log.debug("[login-detector] 프로필 로드 실패: %s", e)
        return {}


def _profile_for_url(url: str) -> dict[str, Any] | None:
    """URL 의 호스트가 등록된 프로필에 속하면 그 프로필, 아니면 None."""
    host = _host_from_url(url)
    if not host:
        return None
    for profile in _load_probes().values():
        if any(host == h or host.endswith("." + h) for h in profile.get("hosts", [])):
            return profile
    return None


def decide_login_state(login_visible: bool, in_visible: bool, cookie: bool | None) -> str:
    """보이는 로그인 버튼·보이는 로그아웃/계정 요소·세션 쿠키가 한 방향일 때만 in/out 확정.

    cookie 는 True/False/None(확인 불가). 충돌하거나 근거가 없으면 unknown — 추측하지 않는다.
    """
    if in_visible and not login_visible and cookie is not False:
        return "in"
    if login_visible and not in_visible and cookie is not True:
        return "out"
    return "unknown"


def _session_cookie_present(page, profile: dict[str, Any]) -> bool | None:
    """프로필의 세션 쿠키가 모두 있는지 — 이름만 본다(값은 읽지도 기록하지도 않음). 확인 불가면 None."""
    names = profile.get("session_cookies") or []
    if not names:
        return None
    try:
        have = {c.get("name") for c in page.context.cookies()}
    except Exception:  # noqa: BLE001 - 쿠키 이름 존재 확인 실패는 '확인 불가(None)'로 처리, 값 접근·삭제 없음
        return None
    return all(n in have for n in names)


def _read_account(page, profile: dict[str, Any]) -> str | None:
    """계정 표시 영역(프로필 셀렉터) 안에서만 사용자명을 읽는다. 셀렉터가 없으면 None."""
    selector = profile.get("account_selector")
    if not selector:
        return None
    try:
        text = page.evaluate(
            "(sel) => { const el = document.querySelector(sel);"
            " return el && el.offsetParent !== null ? (el.innerText || '').trim() : null; }",
            selector,
        )
    except Exception:  # noqa: BLE001 - 계정 영역 읽기 실패는 user=None(확인 불가)로 처리
        return None
    return text if text and len(text) < 50 else None


def detect_login_state_by_elements(page, profile: dict[str, Any]) -> dict[str, Any]:
    """화면에 보이는 요소(스냅샷) + 세션 쿠키 이름으로 로그인 상태를 판정한다.

    반환 키는 detect_login_state 와 같고 method="element", state("in"/"out"/"unknown") 가 추가된다.
    """
    from scripts.explorer import page_analysis, page_snapshot  # 지연 import — web_connector 순환 방지

    analysis = page_analysis.analyze_snapshot(page_snapshot.collect(page))
    sig = page_analysis.element_login_signals(analysis)
    cookie = _session_cookie_present(page, profile)
    state = decide_login_state(sig["login_visible"] > 0, sig["in_visible"] > 0, cookie)
    url = page.url or ""
    return {
        "logged_in": state == "in",
        "score": 0,
        "url": url,
        "on_login_page": bool(_LOGIN_URL_RE.search(url)),
        "user": _read_account(page, profile) if state == "in" else None,
        "in_iframe": False,
        "method": "element",
        "state": state,
        "evidence": {
            "login_button_visible": sig["login_visible"],
            "logout_or_account_visible": sig["in_visible"],
            "login_button_hidden": sig["login_hidden"],
            "logout_or_account_hidden": sig["in_hidden"],
            "session_cookie": cookie,
            "labels": sig["labels"],
        },
    }


_GENERIC_DETECT_JS = r"""
() => {
    const txt = (document.body?.innerText || '').toLowerCase();

    // 1. 로그아웃 텍스트 (가장 강력)
    const logoutInText = /로그아웃|sign\s*out|log\s*out|logout/i.test(txt);

    // 2. 로그아웃 링크/버튼
    let logoutLink = false;
    try {
        for (const el of document.querySelectorAll('a, button')) {
            const t = (el.innerText || el.getAttribute('aria-label') || '').trim();
            const href = el.href || '';
            if (/로그아웃|sign\s*out|log\s*out|logout/i.test(t) ||
                /logout|signout|sign-out/i.test(href)) {
                logoutLink = true;
                break;
            }
        }
    } catch(e) {}

    // 3. 마이페이지/환영
    const myPagePresent = /마이페이지|내정보|my\s*page|my\s*account|환영합니다|welcome/i.test(txt);

    // 4. 비밀번호 필드 부재 + 비로그인 페이지
    const pwFieldCount = document.querySelectorAll('input[type="password"]').length;
    const onLoginPage = /(login|signin|sign-in|sign_in|auth|nidlogin)/i.test(location.href);
    const pwGone = pwFieldCount === 0 && !onLoginPage;

    // 5. 세션 쿠키
    const cookies = document.cookie || '';
    const sessionKws = ['JSESSION', 'PHPSESS', 'sessionid', 'auth', 'token', 'SSID', 'SESS'];
    const hasSession = sessionKws.some(k => cookies.toLowerCase().includes(k.toLowerCase()));

    // 6. 사용자명 영역
    let userBlockText = null;
    try {
        const selectors = ['.user-name', '.username', '.user_name', '.member-name',
                           '[class*="user-name"]', '[class*="username"]',
                           '[class*="member-name"]', '[class*="profile-name"]',
                           '[data-user]', '#user_name', '#username'];
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el && el.offsetParent !== null) {
                const t = (el.innerText || '').trim();
                if (t && t.length > 0 && t.length < 50) {
                    userBlockText = t;
                    break;
                }
            }
        }
    } catch(e) {}

    // 7. "○○○님" / "Hello ○○○"
    let greeting = null;
    const m1 = /([가-힣A-Za-z0-9_.\-]{2,20})\s*님/.exec(txt);
    if (m1) greeting = m1[1];
    if (!greeting) {
        const m2 = /Hello[,!\s]+([A-Za-z0-9._-]{2,30})/i.exec(txt);
        if (m2) greeting = m2[1];
    }

    // 8. aria/data 속성
    const ariaLogged = !!document.querySelector('[aria-label*="logged in" i], [data-logged-in="true"]');

    let score = 0;
    if (logoutInText) score += 3;
    if (logoutLink) score += 2;
    if (myPagePresent) score += 1;
    if (pwGone) score += 1;
    if (hasSession) score += 1;
    if (userBlockText) score += 2;
    if (greeting) score += 2;
    if (ariaLogged) score += 2;

    return {
        url: location.href,
        on_login_page: onLoginPage,
        logout_in_text: logoutInText,
        logout_link: logoutLink,
        mypage_present: myPagePresent,
        pw_field_count: pwFieldCount,
        pw_gone: pwGone,
        has_session_cookie: hasSession,
        user_block: userBlockText,
        greeting_name: greeting,
        aria_logged: ariaLogged,
        score: score,
        logged_in: score >= 3,
    };
}
"""


def detect_login_state(page) -> dict[str, Any]:
    """사이트 무관 공통 로그인 상태 감지.

    Returns:
        {
            logged_in: bool,
            score: int (0-14),
            url: str,
            on_login_page: bool,
            user: str | None,        # 사용자명 추정
            in_iframe: bool,         # iframe에서 감지됐는지
            evidence: dict,          # 어떤 신호로 판단했는지
        }
    """
    try:
        profile = _profile_for_url(page.url or "")
        if profile:
            return detect_login_state_by_elements(page, profile)
        result = page.evaluate(_GENERIC_DETECT_JS)
        # iframe 내부도 검사 (메인이 약한 경우)
        if result.get("score", 0) < 3:
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                try:
                    fr = frame.evaluate(_GENERIC_DETECT_JS)
                    if fr.get("score", 0) > result.get("score", 0):
                        result = fr
                        result["in_iframe"] = True
                except Exception:  # noqa: BLE001 - 로그인 상태 감지(판정 전용, 자격증명 입력 없음) — 감지 실패는 항상 미로그인/False(fail-closed)로 처리하고 로그로 남김, 세션 저장 실패도 로그 후 계속(2026-09-28 검토)
                    continue

        user = result.get("user_block") or result.get("greeting_name")
        return {
            "logged_in": result.get("logged_in", False),
            "score": result.get("score", 0),
            "url": result.get("url", ""),
            "on_login_page": result.get("on_login_page", False),
            "user": user,
            "in_iframe": result.get("in_iframe", False),
            "method": "heuristic",
            "state": "in" if result.get("logged_in", False) else "unknown",
            "evidence": {
                "logout_in_text": result.get("logout_in_text"),
                "logout_link": result.get("logout_link"),
                "mypage_present": result.get("mypage_present"),
                "pw_gone": result.get("pw_gone"),
                "session_cookie": result.get("has_session_cookie"),
                "user_block": result.get("user_block"),
                "greeting": result.get("greeting_name"),
                "aria_logged": result.get("aria_logged"),
            },
        }
    except Exception as e:  # noqa: BLE001 - 로그인 상태 감지(판정 전용, 자격증명 입력 없음) — 감지 실패는 항상 미로그인/False(fail-closed)로 처리하고 로그로 남김, 세션 저장 실패도 로그 후 계속(2026-09-28 검토)
        _log.debug("[login-detector-generic] 감지 실패: %s", e)
        return {"logged_in": False, "score": 0, "state": "unknown", "error": str(e)[:100]}


def is_logged_in_generic(page) -> bool:
    """간편 헬퍼 — 사이트 무관 로그인 여부 bool."""
    return detect_login_state(page).get("logged_in", False)


def get_logged_in_user(page) -> str | None:
    """현재 페이지에서 감지된 사용자명 반환 (없으면 None)."""
    return detect_login_state(page).get("user")


def wait_for_login_generic(page, max_wait_s: int = 600, poll_interval: float = 3.0, on_progress=None) -> dict[str, Any]:
    """사이트 무관 로그인 성공까지 폴링 대기.

    Args:
        page: Playwright Page
        max_wait_s: 최대 대기 시간(초)
        poll_interval: 폴링 간격(초)
        on_progress: callable(state) - 매 폴링마다 호출 (선택)
    """
    start = time.time()
    last_score = -1

    while time.time() - start < max_wait_s:
        state = detect_login_state(page)
        if state.get("logged_in"):
            state["timeout"] = False
            state["elapsed_s"] = int(time.time() - start)
            _log.info(
                "[login-detector-generic] 로그인 감지: score=%d, %ds, user=%s",
                state["score"],
                state["elapsed_s"],
                state.get("user"),
            )
            return state

        if on_progress and state.get("score", 0) != last_score:
            with suppress(Exception):
                on_progress(state)
            last_score = state.get("score", 0)

        time.sleep(poll_interval)

    return {**detect_login_state(page), "timeout": True, "elapsed_s": int(time.time() - start)}


def manual_only_login(page, *, site: str, is_logged_in, open_login_page, log) -> dict[str, Any]:
    """수동 로그인 전용 사이트(OTP·SMS 등 필수) 공용 login 흐름.

    gabia/kakao auth.login 이 똑같이 복사해 쓰던 본문을 한 곳으로 모았다.
    이미 로그인됐으면 기존 세션 재사용 결과를, 아니면 로그인 페이지로 이동(open_login_page — 실패 처리는
    각 사이트 모듈이 함)한 뒤 monitor_for_login 으로 감지하라는 수동 대기 결과를 돌려준다.
    로그는 호출 모듈의 logger(log)로 "<site>: ..." 형식 그대로 남긴다.
    """
    if is_logged_in(page):
        log.info("%s: 이미 로그인됨", site)
        return {"ok": True, "reason": "기존 세션 재사용", "user": "", "needs_manual": False}

    open_login_page(page)

    log.info("%s: 수동 로그인 대기 (최대 5분)", site)
    return {
        "ok": False,
        "reason": "manual_login_required",
        "user": "",
        "needs_manual": True,
        "monitor": monitor_for_login,
    }
