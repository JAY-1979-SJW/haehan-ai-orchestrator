"""EUM 자동 로그인 (ID/PW).

자격증명 저장:
    python scripts/credentials.py set eum

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

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.logger import get_logger
from scripts.op_log import op_context

log = get_logger(__name__)

EUM_BASE = "https://eum.cw.or.kr"

# 로그인 URL 후보 (순서대로 시도)
_LOGIN_URL_CANDIDATES = [
    f"{EUM_BASE}/login",
    f"{EUM_BASE}/web/login",
    f"{EUM_BASE}/user/login",
    f"{EUM_BASE}/member/login",
]

# 로그인 성공 판단 URL 패턴
_SUCCESS_URL_PATTERNS = ["/main", "/mypage", "/web/man", "/dashboard"]

# ID/PW 입력 필드 selector 후보
_ID_SELECTORS = [
    "input[name='id']",
    "input[name='userId']",
    "input[name='username']",
    "input[name='loginId']",
    "input[type='text'][id*='id']",
    "input[type='text'][id*='Id']",
    "input[type='text'][placeholder*='아이디']",
    "input[type='text'][placeholder*='ID']",
    "#id", "#userId", "#loginId", "#username",
]

_PW_SELECTORS = [
    "input[name='password']",
    "input[name='pw']",
    "input[name='passwd']",
    "input[type='password']",
    "#password", "#pw", "#passwd",
]

# 로그인 버튼 selector 후보
_BTN_SELECTORS = [
    "button[type='submit']",
    "input[type='submit']",
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
        except Exception:
            pass
    return None


def is_logged_in(page) -> bool:
    """현재 페이지가 로그인 상태인지 확인.

    Returns:
        True — 로그인된 상태
        False — 로그아웃 또는 세션 만료
    """
    current_url = page.url
    # URL 기반 판단
    for pattern in _SUCCESS_URL_PATTERNS:
        if pattern in current_url and "login" not in current_url:
            log.debug("is_logged_in: URL 패턴 매치 url=%s", current_url)
            return True

    # DOM 기반 판단: 로그아웃 버튼 또는 사용자명 존재
    logout_selectors = [
        "a:has-text('로그아웃')",
        "button:has-text('로그아웃')",
        "[class*='logout']",
        "[id*='logout']",
        ".user-name",
        ".login-user",
        "[class*='user'][class*='info']",
    ]
    for sel in logout_selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                log.debug("is_logged_in: 로그아웃 버튼/사용자명 발견 sel=%s", sel)
                return True
        except Exception:
            pass

    return False


def _try_goto(page, url: str) -> bool:
    """URL로 이동. 성공 여부 반환."""
    try:
        page.goto(url, timeout=15000)
        page.wait_for_load_state("networkidle", timeout=15000)
        return True
    except Exception as e:
        log.debug("goto 실패: url=%s err=%s", url, e)
        return False


def login(page) -> dict:
    """EUM ID/PW 자동 로그인.

    Args:
        page: Playwright Page 객체

    Returns:
        dict{ok: bool, reason: str, user: str}
    """
    from scripts.credentials import get_cred
    cred = get_cred("eum")
    eum_id = cred.get("id", "").strip()
    eum_pw = cred.get("pw", "").strip()

    if not eum_id or not eum_pw:
        return {
            "ok": False,
            "reason": "EUM 자격증명 없음. 먼저 실행: python scripts/credentials.py set eum",
            "user": "",
        }

    with op_context("eum_login", url=EUM_BASE) as ctx:
        # 이미 로그인된 경우 메인으로 이동해 확인
        if is_logged_in(page):
            log.info("이미 로그인된 상태")
            ctx.set_result(msg="기존 세션 재사용", ok=True)
            return {"ok": True, "reason": "기존 세션 재사용", "user": eum_id}

        # 메인 페이지 먼저 이동 (리다이렉트로 로그인 페이지 자동 이동 기대)
        main_ok = _try_goto(page, f"{EUM_BASE}/main")
        if main_ok and is_logged_in(page):
            log.info("메인 이동 후 로그인 확인됨")
            ctx.set_result(msg="메인 이동 후 세션 확인", ok=True)
            return {"ok": True, "reason": "메인 이동 후 세션 확인", "user": eum_id}

        # 로그인 URL 후보 순서대로 시도
        login_page_reached = False
        for login_url in _LOGIN_URL_CANDIDATES:
            ok = _try_goto(page, login_url)
            if ok:
                current = page.url
                # 로그인 폼 존재 여부 확인
                id_sel = _find_selector(page, _ID_SELECTORS)
                if id_sel:
                    log.info("로그인 페이지 발견: url=%s id_sel=%s", current, id_sel)
                    login_page_reached = True
                    break

        if not login_page_reached:
            # 현재 페이지에서 폼 재시도
            id_sel = _find_selector(page, _ID_SELECTORS)
            if not id_sel:
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

        # 필드 초기화 후 입력
        page.fill(id_sel, "")
        page.fill(id_sel, eum_id)
        page.fill(pw_sel, "")
        page.fill(pw_sel, eum_pw)

        # 로그인 버튼 클릭
        btn_sel = _find_selector(page, _BTN_SELECTORS)
        if btn_sel:
            log.info("로그인 버튼 클릭: sel=%s", btn_sel)
            page.click(btn_sel)
        else:
            # 버튼 없으면 Enter 키
            log.info("로그인 버튼 미발견 — Enter 키 사용")
            page.locator(pw_sel).press("Enter")

        # 페이지 로딩 대기
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        # 팝업/알림 처리 (로그인 실패 메시지)
        try:
            page.wait_for_timeout(1000)
        except Exception:
            pass

        # 로그인 성공 여부 확인
        if is_logged_in(page):
            # 사용자명 추출 시도
            user_name = eum_id
            user_selectors = [".user-name", ".login-user", "[class*='user-nm']", ".name"]
            for sel in user_selectors:
                try:
                    el = page.query_selector(sel)
                    if el:
                        txt = el.inner_text().strip()
                        if txt:
                            user_name = txt
                            break
                except Exception:
                    pass

            log.info("로그인 성공: user=%s url=%s", user_name, page.url)
            ctx.set_result(msg="로그인 성공", ok=True, user=user_name)
            return {"ok": True, "reason": "로그인 성공", "user": user_name}

        # 실패 메시지 추출 시도
        fail_msg = "로그인 실패 (이유 불명)"
        fail_selectors = [
            ".error-msg", ".alert", ".warning",
            "[class*='error']", "[class*='fail']",
            "p:has-text('아이디')", "p:has-text('비밀번호')",
            "span:has-text('오류')", "div:has-text('실패')",
        ]
        for sel in fail_selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    txt = el.inner_text().strip()
                    if txt:
                        fail_msg = txt[:200]
                        break
            except Exception:
                pass

        log.warning("로그인 실패: url=%s msg=%s", page.url, fail_msg)
        ctx.set_result(msg=fail_msg, ok=False)
        return {"ok": False, "reason": fail_msg, "user": ""}


def ensure_logged_in(page) -> None:
    """로그인 상태를 보장한다. 세션 없으면 자동 로그인.

    모든 EUM 명령 진입 시 자동 호출됨.
    로그인 실패 시 RuntimeError 발생 → 작업 중단.
    """
    if is_logged_in(page):
        log.debug("EUM 세션 유효 — 로그인 생략")
        return

    log.info("EUM 세션 없음 — 자동 로그인 시도")
    print("  [EUM] 세션 없음 → 자동 로그인 중...", end=" ", flush=True)
    result = login(page)
    if result["ok"]:
        print(f"✔ ({result['user']})")
    else:
        print(f"✘ 실패")
        raise RuntimeError(
            f"EUM 자동 로그인 실패: {result['reason']}\n"
            "  자격증명 확인: python scripts/cdp_client.py cred set eum"
        )


def main() -> None:
    """CLI 실행: 로그인 시도 및 결과 출력."""
    from scripts.web_connector import get_page

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
