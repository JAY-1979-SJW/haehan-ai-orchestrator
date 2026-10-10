"""EUM 자동 로그인 (ID/PW).

자격증명 저장:
    python scripts/auth/credentials.py set eum

사용:
    from scripts.eum.auth import login, is_logged_in

    page = get_page()
    result = login(page)
    if result["ok"]:
        print("로그인 성공:", result["user"])
    else:
        print("로그인 실패:", result["reason"])
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.browser.page.human_input import safe_human_input  # noqa: E402
from scripts.common.logger import get_logger  # noqa: E402
from scripts.common.op_log import op_context  # noqa: E402

log = get_logger(__name__)

EUM_BASE = "https://eum.cw.or.kr"

# 로그인 URL — WEBLOG400M00 (단말기 업체 등 기타기관 로그인 진입점) 우선
EUM_PRIMARY_LOGIN_URL = f"{EUM_BASE}/web/log/WEBLOG400M00"
_LOGIN_URL_CANDIDATES = [
    EUM_PRIMARY_LOGIN_URL,  # 단말기 업체 (우리 사용)
    f"{EUM_BASE}/login",
    f"{EUM_BASE}/web/login",
    f"{EUM_BASE}/user/login",
    f"{EUM_BASE}/member/login",
]
_LOGIN_URL_FALLBACKS = _LOGIN_URL_CANDIDATES[1:]

# 우리 회원 분류 — 비전아이(주)는 단말기 업체
_MEMBER_CATEGORY = "단말기 업체"
_TERMINAL_COMPANY_SUBTYPE = "유통업체"
# #radio_b2 하드코딩 제거 — _select_terminal_company_subtype에서 동적 탐색
_TERMINAL_COMPANY_SUBTYPE_SELECTOR_FALLBACK = "#radio_b2"


def _select_member_category(page, category: str = _MEMBER_CATEGORY) -> bool:
    """WEBLOG400M00 페이지에서 회원 분류 선택. 성공 여부 반환."""
    try:
        # 클릭 가능한 후보: button/a/label/radio with text
        # 단말기 업체 텍스트의 button 우선
        loc = page.locator(f'button:has-text("{category}")').first
        try:
            loc.wait_for(state="visible", timeout=2000)
            loc.click(timeout=3000)
            log.info("[eum-auth] 회원 분류 선택: %s (button)", category)
            return True
        except Exception:  # noqa: BLE001 - 여러 셀렉터/신호를 순차 시도하는 best-effort — 하나 실패해도 다음 신호로 계속(2026-09-28 검토)
            pass
        # 라벨/링크 폴백
        for sel in [f'label:has-text("{category}")', f'a:has-text("{category}")', f'[onclick*="{category}"]']:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=1000):
                    loc.click(timeout=3000)
                    log.info("[eum-auth] 회원 분류 선택: %s (%s)", category, sel)
                    return True
            except Exception:  # noqa: BLE001 - EUM 로그인 자동화 — 로그인 상태 판정은 여러 DOM 신호를 순차 확인하고 실패 시 항상 미로그인(fail-closed)으로 처리, 로그인 결과는 항상 {ok, reason} 구조로 반환, 자격증명 값은 로그에 남기지 않음(2026-09-28 검토)
                continue
        log.warning("[eum-auth] 회원 분류 '%s' 선택 실패", category)
        return False
    except Exception as e:  # noqa: BLE001 - EUM 로그인 자동화 — 로그인 상태 판정은 여러 DOM 신호를 순차 확인하고 실패 시 항상 미로그인(fail-closed)으로 처리, 로그인 결과는 항상 {ok, reason} 구조로 반환, 자격증명 값은 로그에 남기지 않음(2026-09-28 검토)
        log.warning("[eum-auth] 회원 분류 선택 예외: %s", e)
        return False


def _select_terminal_company_subtype(page, subtype: str = _TERMINAL_COMPANY_SUBTYPE) -> bool:
    """단말기 업체 탭 안의 세부 유형을 선택한다.

    텍스트 기반 동적 탐색 우선. 하드코딩 ID(#radio_b2)는 최후 폴백.
    """
    try:
        # 1. #tab4 내 텍스트 라벨 (가장 안전)
        for sel in [
            f'#tab4 label:has-text("{subtype}")',
            f'label:has-text("{subtype}")',
            f'[id^="tab"] label:has-text("{subtype}")',
        ]:
            try:
                loc = page.locator(sel).first
                loc.wait_for(state="visible", timeout=1000)
                loc.click(timeout=3000)
                log.info("[eum-auth] 단말기 업체 세부 유형 선택: %s (%s)", subtype, sel)
                return True
            except Exception:  # noqa: BLE001 - EUM 로그인 자동화 — 로그인 상태 판정은 여러 DOM 신호를 순차 확인하고 실패 시 항상 미로그인(fail-closed)으로 처리, 로그인 결과는 항상 {ok, reason} 구조로 반환, 자격증명 값은 로그에 남기지 않음(2026-09-28 검토)
                continue

        # 2. radio input value/aria-label 기반
        for sel in [
            f'input[type="radio"][value*="{subtype}"]',
            f'input[type="radio"][aria-label*="{subtype}"]',
        ]:
            try:
                loc = page.locator(sel).first
                loc.wait_for(state="attached", timeout=1000)
                loc.check(timeout=3000, force=True)
                log.info("[eum-auth] 단말기 업체 세부 유형 선택: %s (%s)", subtype, sel)
                return True
            except Exception:  # noqa: BLE001 - EUM 로그인 자동화 — 로그인 상태 판정은 여러 DOM 신호를 순차 확인하고 실패 시 항상 미로그인(fail-closed)으로 처리, 로그인 결과는 항상 {ok, reason} 구조로 반환, 자격증명 값은 로그에 남기지 않음(2026-09-28 검토)
                continue

        # 3. 하드코딩 ID 폴백 (사이트 변경 전 구 셀렉터)
        try:
            loc = page.locator(_TERMINAL_COMPANY_SUBTYPE_SELECTOR_FALLBACK).first
            loc.wait_for(state="attached", timeout=2000)
            loc.check(timeout=3000, force=True)
            log.info(
                "[eum-auth] 단말기 업체 세부 유형 선택: %s (fallback %s)",
                subtype,
                _TERMINAL_COMPANY_SUBTYPE_SELECTOR_FALLBACK,
            )
            return True
        except Exception:  # noqa: BLE001 - 여러 셀렉터/신호를 순차 시도하는 best-effort — 하나 실패해도 다음 신호로 계속(2026-09-28 검토)
            pass

        log.warning("[eum-auth] 단말기 업체 세부 유형 '%s' 선택 실패", subtype)
        return False
    except Exception as e:  # noqa: BLE001 - EUM 로그인 자동화 — 로그인 상태 판정은 여러 DOM 신호를 순차 확인하고 실패 시 항상 미로그인(fail-closed)으로 처리, 로그인 결과는 항상 {ok, reason} 구조로 반환, 자격증명 값은 로그에 남기지 않음(2026-09-28 검토)
        log.warning("[eum-auth] 단말기 업체 세부 유형 선택 예외: %s", e)
        return False


# 로그인 성공 판단 URL 패턴
_SUCCESS_URL_PATTERNS = ["/main", "/mypage", "/web/man", "/dashboard"]

# ID/PW 입력 필드 selector 후보
_ID_SELECTORS = [
    "#tab4 input[placeholder*='아이디']",
    "#tab4 input[type='search'][placeholder*='아이디']",
    "input[name='id']",
    "input[name='userId']",
    "input[name='username']",
    "input[name='loginId']",
    "input[placeholder*='아이디']:not([type='hidden'])",
    "input[placeholder*='ID']:not([type='hidden'])",
    "input[type='text'][id*='id']",
    "input[type='text'][id*='Id']",
    "input[type='text'][placeholder*='아이디']",
    "input[type='text'][placeholder*='ID']",
    "input[type='search'][placeholder*='아이디']",
    "input[type='search'][placeholder*='ID']",
    "#id",
    "#userId",
    "#loginId",
    "#username",
]

_PW_SELECTORS = [
    "#tab4 input[type='password']",
    "#tab4 input[placeholder*='비밀번호']",
    "input[name='password']",
    "input[name='pw']",
    "input[name='passwd']",
    "input[type='password']",
    "#password",
    "#pw",
    "#passwd",
]

# 로그인 버튼 selector 후보
_BTN_SELECTORS = [
    "#tab4 button.btn_l:has-text('로그인')",
    "#tab4 button.w100p:has-text('로그인')",
    "#tab4 button:has-text('로그인')",
    "button[type='submit']",
    "input[type='submit']",
    "button.btn_l:has-text('로그인')",
    "button.w100p:has-text('로그인')",
    "button[class*='btn_ty']:has-text('로그인')",
    "button:has-text('로그인')",
    "a:has-text('로그인')",
    ".btn-login",
    "#btnLogin",
    "[id*='login'][id*='btn']",
    "[class*='login'][class*='btn']",
]


def _find_selector(page, candidates: list[str]) -> str | None:
    """selector 후보 목록에서 실제로 존재하는 첫 번째 selector 반환."""
    for sel in candidates:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                return sel
        except Exception:  # noqa: BLE001 - 여러 셀렉터/신호를 순차 시도하는 best-effort — 하나 실패해도 다음 신호로 계속(2026-09-28 검토)
            pass
    return None


def _eum_session_signal(page, current_url: str, form_visible: bool) -> bool:
    """로그인 폼이 안 보일 때 대시보드 요소/세션 텍스트로 로그인 신호를 확인."""
    try:
        if not form_visible and page.query_selector(".login_dashboard"):
            log.debug("is_logged_in: EUM login dashboard detected url=%s", current_url)
            return True
    except Exception:  # noqa: BLE001 - 여러 셀렉터/신호를 순차 시도하는 best-effort — 하나 실패해도 다음 신호로 계속(2026-09-28 검토)
        pass
    try:
        if not form_visible:
            body_text = page.locator("body").inner_text(timeout=2000)
            if any(token in body_text for token in ("로그아웃", "로그인연장", "마이페이지")):
                log.debug("is_logged_in: EUM session text detected url=%s", current_url)
                return True
    except Exception:  # noqa: BLE001 - 여러 셀렉터/신호를 순차 시도하는 best-effort — 하나 실패해도 다음 신호로 계속(2026-09-28 검토)
        pass
    return False


def _login_button_visible(page, current_url: str) -> bool:
    """visible '로그인' 버튼이 있으면 True (R2 핵심 — /main 공개 페이지 false positive 차단)."""
    login_button_selectors = [
        "a:has-text('로그인')",
        "button:has-text('로그인')",
        "[onclick*='login']:not([onclick*='logout'])",
    ]
    for sel in login_button_selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                # "로그아웃"도 "로그인"을 포함하므로 텍스트 한 번 더 확인
                txt = (el.inner_text() or "").strip()
                if txt == "로그인" or ("로그인" in txt and "로그아웃" not in txt):
                    log.debug("is_logged_in: '로그인' 버튼 visible — 미로그인 url=%s", current_url)
                    return True
        except Exception:  # noqa: BLE001 - 여러 셀렉터/신호를 순차 시도하는 best-effort — 하나 실패해도 다음 신호로 계속(2026-09-28 검토)
            pass
    return False


def _logout_button_visible(page) -> bool:
    """명시적 로그아웃 버튼이 보이면 True (강한 로그인 신호)."""
    strong_logged_in_selectors = [
        "a:has-text('로그아웃')",
        "button:has-text('로그아웃')",
        "[onclick*='logout']",
        "[href*='logout']",
        "[id='btnLogout']",
        ".btn-logout",
    ]
    for sel in strong_logged_in_selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                log.debug("is_logged_in: 로그아웃 버튼 발견 sel=%s", sel)
                return True
        except Exception:  # noqa: BLE001 - 여러 셀렉터/신호를 순차 시도하는 best-effort — 하나 실패해도 다음 신호로 계속(2026-09-28 검토)
            pass
    return False


def is_logged_in(page) -> bool:
    """현재 페이지가 로그인 상태인지 확인.

    판정 순서 (false positive 방지):
        1. 로그인 폼(ID/PW 입력)이 visible → 무조건 미로그인 (R1 차단)
        2. URL이 login 페이지 → 미로그인
        3. 로그아웃 버튼 또는 사용자명 존재 → 로그인됨
        4. 성공 URL 패턴 매치 + 폼/로그인 페이지 아님 → 로그인됨
        5. 그 외 → 미로그인 (보수적)
    """
    current_url = ""
    try:
        current_url = page.url or ""
    except Exception:  # noqa: BLE001 - EUM 로그인 자동화 — 로그인 상태 판정은 여러 DOM 신호를 순차 확인하고 실패 시 항상 미로그인(fail-closed)으로 처리, 로그인 결과는 항상 {ok, reason} 구조로 반환, 자격증명 값은 로그에 남기지 않음(2026-09-28 검토)
        return False

    # 1. 로그인 폼(ID+PW)이 보이면 = 미로그인 (R1 핵심)
    if "/main" in current_url:
        # 여러 셀렉터/신호를 순차 시도하는 best-effort — 하나 실패해도 다음 신호로 계속(2026-09-28 검토)
        with contextlib.suppress(Exception):
            page.wait_for_selector(".login_dashboard", state="attached", timeout=5000)
    id_visible = _find_selector(page, _ID_SELECTORS) is not None
    pw_visible = _find_selector(page, _PW_SELECTORS) is not None
    if _eum_session_signal(page, current_url, id_visible and pw_visible):
        return True
    if id_visible and pw_visible:
        log.debug("is_logged_in: 로그인 폼 visible — 미로그인 확정 url=%s", current_url)
        return False

    # 2. URL이 로그인 페이지면 미로그인
    if "login" in current_url.lower() or "WEBLOG" in current_url:
        log.debug("is_logged_in: login URL — 미로그인 url=%s", current_url)
        return False

    # 3. visible "로그인" 버튼이 있으면 미로그인 (R2 핵심 — /main 공개 페이지 false positive 차단)
    if _login_button_visible(page, current_url):
        return False

    # 4. 명시적 로그아웃 버튼 (강한 신호 — 로그인됨)
    if _logout_button_visible(page):
        return True

    # 5. 보호된 페이지 패턴 (/web/man/ 등) + 폼/로그인버튼 없음 → 로그인된 것으로 추정
    protected_patterns = ["/web/man/", "/mypage", "/dashboard"]
    for pattern in protected_patterns:
        if pattern in current_url:
            log.debug("is_logged_in: 보호 영역 URL 매치 → 로그인 추정 url=%s", current_url)
            return True

    # 6. 그 외(예: /main 공개 페이지) → 보수적으로 미로그인
    log.debug("is_logged_in: 명확한 로그인 신호 없음 — 미로그인 처리 url=%s", current_url)
    return False


def _try_goto(page, url: str) -> bool:
    """URL로 이동. 성공 여부 반환."""
    try:
        page.goto(url, timeout=15000, wait_until="domcontentloaded")
        return True
    except Exception as e:  # noqa: BLE001 - EUM 로그인 자동화 — 로그인 상태 판정은 여러 DOM 신호를 순차 확인하고 실패 시 항상 미로그인(fail-closed)으로 처리, 로그인 결과는 항상 {ok, reason} 구조로 반환, 자격증명 값은 로그에 남기지 않음(2026-09-28 검토)
        log.debug("goto 실패: url=%s err=%s", url, e)
        return False


_USER_NAME_SELECTORS = [".user-name", ".login-user", "[class*='user-nm']", ".name"]

def _first_selector_text(page, selectors: list[str]) -> str | None:
    """selector 순서대로 첫 번째 비어있지 않은 텍스트(strip) 반환. 개별 실패는 무시."""
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                txt = el.inner_text().strip()
                if txt:
                    return txt
        except Exception:  # noqa: BLE001 - 여러 셀렉터/신호를 순차 시도하는 best-effort — 하나 실패해도 다음 신호로 계속(2026-09-28 검토)
            pass
    return None


def _reach_login_form(page) -> bool:
    """로그인 URL 후보로 이동해 ID 입력 폼을 찾는다. 못 찾으면 현재 페이지에서 재시도."""
    # 로그인 URL 후보 순서대로 시도
    for login_url in [EUM_PRIMARY_LOGIN_URL]:
        ok = _try_goto(page, login_url)
        if not ok:
            continue
        current = page.url

        # WEBLOG400M00 진입 시 회원 분류 (단말기 업체) 선택 필요
        if "WEBLOG400M00" in current and _select_member_category(page, _MEMBER_CATEGORY):
            _select_terminal_company_subtype(page, _TERMINAL_COMPANY_SUBTYPE)
            # 폼이 visible 로 바뀔 때까지 잠깐 대기 (best-effort, 실패해도 다음 신호로 계속, 2026-09-28 검토)
            with contextlib.suppress(Exception):
                page.wait_for_selector(
                    "input[type='password']:visible",
                    state="visible",
                    timeout=3000,
                )
                pass

        id_sel = _find_selector(page, _ID_SELECTORS)
        if id_sel:
            log.info("로그인 페이지 발견: url=%s id_sel=%s", current, id_sel)
            return True

    # 현재 페이지에서 폼 재시도 (혹은 단말기 업체 선택 재시도)
    if "WEBLOG400M00" in page.url:
        _select_member_category(page, _MEMBER_CATEGORY)
        _select_terminal_company_subtype(page, _TERMINAL_COMPANY_SUBTYPE)
    return bool(_find_selector(page, _ID_SELECTORS))


def _submit_credentials(page, id_sel: str, pw_sel: str, eum_id: str, eum_pw: str) -> str | None:
    """ID/PW 를 사람처럼 입력하고 로그인 버튼(또는 Enter)을 눌러 제출. 입력 실패 시 오류 메시지, 성공 시 None."""
    # 휴먼 타이핑 (봇 감지 회피)
    r_id = safe_human_input(page, id_sel, eum_id, label="ID", delay_ms=80)
    if not r_id.get("ok"):
        return f"ID 입력 실패: {r_id.get('reason', '')}"
    r_pw = safe_human_input(page, pw_sel, eum_pw, label="PW", delay_ms=80)
    if not r_pw.get("ok"):
        return f"PW 입력 실패: {r_pw.get('reason', '')}"

    # 로그인 버튼 클릭
    btn_sel = _find_selector(page, _BTN_SELECTORS)
    if btn_sel:
        log.info("로그인 버튼 클릭: sel=%s", btn_sel)
        page.click(btn_sel)
    else:
        # 버튼 없으면 Enter 키
        log.info("로그인 버튼 미발견 — Enter 키 사용")
        page.locator(pw_sel).press("Enter")

    # 페이지 로딩 대기 (best-effort, 실패해도 다음 신호로 계속, 2026-09-28 검토)
    with contextlib.suppress(Exception):
        page.wait_for_load_state("networkidle", timeout=15000)

    # 팝업/알림 처리 (로그인 실패 메시지, best-effort, 2026-09-28 검토)
    with contextlib.suppress(Exception):
        page.wait_for_timeout(1000)
    return None


def _save_eum_session(page) -> None:
    """세션 자동 저장 (다음 실행 시 복원). 실패는 무시."""
    try:
        from scripts.auth.auth_session import save_session as _save

        _save("eum.cw.or.kr", page)
        log.info("[eum-auth] 세션 저장 완료")
    except Exception as _e:  # noqa: BLE001 - EUM 로그인 자동화 — 로그인 상태 판정은 여러 DOM 신호를 순차 확인하고 실패 시 항상 미로그인(fail-closed)으로 처리, 로그인 결과는 항상 {ok, reason} 구조로 반환, 자격증명 값은 로그에 남기지 않음(2026-09-28 검토)
        log.debug("[eum-auth] 세션 저장 실패 (무시): %s", _e)


def login(page) -> dict:
    """EUM ID/PW 자동 로그인.

    Args:
        page: Playwright Page 객체

    Returns:
        dict{ok: bool, reason: str, user: str}
    """
    from scripts.auth.credentials import get_cred

    cred = get_cred("eum")
    eum_id = cred.get("id", "").strip()
    eum_pw = cred.get("pw", "").strip()

    if not eum_id or not eum_pw:
        return {
            "ok": False,
            "reason": "EUM 자격증명 없음. 먼저 실행: python scripts/auth/credentials.py set eum",
            "user": "",
        }

    with op_context("eum_login", url=EUM_BASE) as ctx:
        # 이미 로그인된 경우 메인으로 이동해 확인
        if is_logged_in(page):
            log.info("이미 로그인된 상태")
            ctx.set_result(msg="기존 세션 재사용", ok=True)
            return {"ok": True, "reason": "기존 세션 재사용", "user": eum_id}

        # 메인 페이지 우회 단축경로 제거됨 — EUM /main 은 미로그인도 공개라 false positive.
        # 바로 로그인 URL 후보부터 시도하여 실제 폼/세션을 확인한다.

        if not _reach_login_form(page):
            msg = "로그인 페이지/폼을 찾을 수 없습니다."
            log.warning(msg)
            ctx.set_result(msg=msg, ok=False)
            return {"ok": False, "reason": msg, "user": ""}

        # ID 입력
        id_sel = _find_selector(page, _ID_SELECTORS)
        if not id_sel:
            msg = "ID 입력 필드를 찾을 수 없습니다."
            ctx.set_result(msg=msg, ok=False)
            return {"ok": False, "reason": msg, "user": ""}

        pw_sel = _find_selector(page, _PW_SELECTORS)
        if not pw_sel:
            msg = "비밀번호 입력 필드를 찾을 수 없습니다."
            ctx.set_result(msg=msg, ok=False)
            return {"ok": False, "reason": msg, "user": ""}

        log.info("로그인 폼 입력 시작: id_sel=%s pw_sel=%s", id_sel, pw_sel)

        input_err = _submit_credentials(page, id_sel, pw_sel, eum_id, eum_pw)
        if input_err:
            ctx.set_result(msg=input_err, ok=False)
            return {"ok": False, "reason": input_err, "user": ""}

        # 로그인 성공 여부 확인
        if is_logged_in(page):
            # 사용자명 추출 시도
            user_name = _first_selector_text(page, _USER_NAME_SELECTORS) or eum_id

            log.info("로그인 성공: user=%s url=%s", user_name, page.url)
            ctx.set_result(msg="로그인 성공", ok=True, user=user_name)
            _save_eum_session(page)
            return {"ok": True, "reason": "로그인 성공", "user": user_name}

        # 실패 메시지 추출 시도
        fail_selectors = [
            "#alertMsg0",
            ".pop_modal_alert .pop_msg",
            ".pop_modal_alert",
            ".error-msg",
            ".alert",
            ".warning",
            "[class*='error']",
            "[class*='fail']",
            "p:has-text('아이디')",
            "p:has-text('비밀번호')",
            "span:has-text('오류')",
            "div:has-text('실패')",
        ]
        fail_text = _first_selector_text(page, fail_selectors)
        fail_msg = fail_text[:200] if fail_text else "로그인 실패 (이유 불명)"

        log.warning("로그인 실패: url=%s msg=%s", page.url, fail_msg)
        ctx.set_result(msg=fail_msg, ok=False)
        return {"ok": False, "reason": fail_msg, "user": ""}


def ensure_logged_in(page) -> None:
    """로그인 상태를 보장한다. 세션 없으면 저장 세션 복원 → 자동 로그인 순으로 시도.

    모든 EUM 명령 진입 시 자동 호출됨.
    로그인 실패 시 RuntimeError 발생 → 작업 중단.
    """
    if is_logged_in(page):
        log.debug("EUM 세션 유효 — 로그인 생략")
        return

    # 저장된 세션 복원 시도
    try:
        from scripts.auth.auth_session import restore_session as _restore

        r = _restore("eum.cw.or.kr", page)
        if r.get("ok"):
            log.info("[eum-auth] 저장 세션 복원 완료 (saved_at=%s)", r.get("saved_at"))
            print(f"  [EUM] 세션 복원 ✔ ({r.get('saved_at', '?')} 저장본)", flush=True)
            # 복원 후 페이지 이동해 로그인 확인 (best-effort, 2026-09-28 검토)
            with contextlib.suppress(Exception):
                page.goto(EUM_BASE + "/web/man/WEBMAN390M00", timeout=12000, wait_until="domcontentloaded")
            if is_logged_in(page):
                log.info("[eum-auth] 세션 복원 후 로그인 확인됨")
                return
            log.info("[eum-auth] 세션 복원 후 로그인 미확인 — 신규 로그인 진행")
    except Exception as _e:  # noqa: BLE001 - EUM 로그인 자동화 — 로그인 상태 판정은 여러 DOM 신호를 순차 확인하고 실패 시 항상 미로그인(fail-closed)으로 처리, 로그인 결과는 항상 {ok, reason} 구조로 반환, 자격증명 값은 로그에 남기지 않음(2026-09-28 검토)
        log.debug("[eum-auth] 세션 복원 시도 실패 (무시): %s", _e)

    log.info("EUM 세션 없음 — 자동 로그인 시도")
    print("  [EUM] 세션 없음 → 자동 로그인 중...", end=" ", flush=True)
    result = login(page)
    if result["ok"]:
        print(f"✔ ({result['user']})")
    else:
        print("✘ 실패")
        raise RuntimeError(
            f"EUM 자동 로그인 실패: {result['reason']}\n  자격증명 확인: python scripts/entry/cdp_cli.py cred set eum"
        )


def main() -> None:
    """CLI 실행: 로그인 시도 및 결과 출력."""
    from scripts.browser.cdp.connection import get_page

    print("=" * 60)
    print("EUM 자동 로그인")
    print("=" * 60)

    page = get_page()
    result = login(page)

    if result["ok"]:
        print(f"✔ 로그인 성공: {result['user']}")
        print(f"  현재 URL: {page.url}")
    else:
        print(f"✘ 로그인 실패: {result['reason']}")
        print(f"  현재 URL: {page.url}")

    print("=" * 60)


if __name__ == "__main__":
    main()
