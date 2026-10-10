"""사이트별 로그인·로그인 상태 확인 함수와 사이트 등록 항목, 그리고 진입점이 부르는 `install()` (조합 모듈).

사이트 등록표 코어(`scripts/site_engine/site_registry.py`)는 사이트 지식도, 이 모듈도 import 하지 않는다(결함 #113).
프로세스 진입점(cdp_cli·직접 실행 main·서버 조합 루트·시험 conftest)이 시작할 때 `install()` 을 부르면
코어에 사이트 목록 공급자(`build_sites`)가 알려지고, 처음 `get_site`/`list_sites` 가 불릴 때 목록이 만들어진다.
이 모듈은 모든 사이트 모듈을 아는 맨 위 층이라 `scripts/entry/` 에 두고 어떤 도구도 import 하지 않는다 —
(사이트 모듈이 이 모듈을 import 하면 순환이 된다). 진입점이 `install()` 을 빠뜨리면 코어가 RuntimeError 로 알린다.

신규 사이트 추가:
    1. 아래 `build_sites()` 의 반환 목록에 항목 추가(순서 = `list_sites()` 순서)
    2. 사이트별 auth 모듈에 login() / is_logged_in() 제공
"""

from __future__ import annotations

from scripts.site_engine import site_registry

# ── lazy 로더 ─────────────────────────────────────────────────────────────


def _eum_is_logged_in(page):
    from scripts.eum.auth import is_logged_in

    return is_logged_in(page)


def _eum_login(page):
    from scripts.eum.auth import login

    return login(page)


def _naver_is_logged_in(page):
    from scripts.auth.login_detector import detect_login_state

    s = detect_login_state(page)
    return bool(s.get("logged_in"))


def _naver_login(page, *, force_login: bool = False):
    from scripts.naver.common.auth import login_naver

    # wait_for_user_s 짧게 (B방식 fallback은 site_access에서 제어)
    r = login_naver(page, wait_for_user_s=10, force_relogin=force_login)
    # 통일된 스키마로 변환
    return {
        "ok": bool(r.get("logged_in") or r.get("ok")),
        "reason": r.get("reason") or r.get("hint") or "",
        "user": r.get("user") or "",
        "needs_manual": bool(r.get("needs_manual") or r.get("captcha") or r.get("captcha_required")),
    }


def _smartstore_is_logged_in(page):
    try:
        from scripts.naver.smartstore.live_probe import classify_probe

        raw = page.evaluate(
            """() => {
              const clean = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
              const body = clean(document.body ? document.body.innerText : '');
              const href = String(location.href || '');
              const host = String(location.host || '').toLowerCase();
              const title = String(document.title || '');
              const combined = `${href} ${title} ${body}`;
              return {
                href,
                host,
                title,
                markers: {
                  naverLogin: /nid\\.naver\\.com|로그인|아이디|비밀번호|sign in/i.test(combined),
                  smartstore: /스마트스토어|스마트스토어센터|상품관리|판매관리|정산관리|문의\\/리뷰관리|스토어/i.test(combined),
                  sellerCenter: /sell\\.smartstore\\.naver\\.com|판매자|센터/i.test(combined),
                  challenge: /보안|captcha|자동입력|로봇|인증번호|비정상|차단/i.test(combined)
                },
                bodySample: body.slice(0, 500)
              };
            }"""
        )
        return bool(classify_probe(raw or {}).get("logged_in"))
    except Exception:  # noqa: BLE001 - 로그인 상태 확인 헬퍼 — 예외 시 False(로그인 안 됨)로 fail-closed 반환, 읽기 전용 DOM 텍스트 검사, 쓰기 없음
        return False


def _smartstore_login(page):
    return {
        "ok": False,
        "reason": "manual_smartstore_login_required",
        "user": "",
        "needs_manual": True,
    }


def _google_is_logged_in(page):
    from scripts.auth.login_detector import detect_login_state

    s = detect_login_state(page)
    return bool(s.get("logged_in"))


def _google_login(page):
    from scripts.google.auth import login_google

    r = login_google(page, wait_for_user_s=10)
    return {
        "ok": bool(r.get("logged_in") or r.get("ok")),
        "reason": r.get("reason") or r.get("hint") or "",
        "user": r.get("user") or "",
        "needs_manual": bool(r.get("needs_manual") or r.get("challenge")),
    }


def _gabia_is_logged_in(page):
    from scripts.gabia.auth import is_logged_in

    return is_logged_in(page)


def _gabia_login(page):
    from scripts.gabia.auth import login

    return login(page)


def _kakao_is_logged_in(page):
    from scripts.kakao.auth import is_logged_in

    return is_logged_in(page)


def _kakao_login(page):
    from scripts.kakao.auth import login

    return login(page)


def _hiworks_is_logged_in(page):
    try:
        url = page.url or ""
        if "login.office.hiworks.com" in url:
            return False
        if "office.hiworks.com" not in url:
            return False
        text = page.locator("body").inner_text(timeout=2000)
        return any(token in text for token in ("오피스 홈", "메일", "전자결재", "업무관리", "로그아웃"))
    except Exception:  # noqa: BLE001 - 로그인 상태 확인 헬퍼 — 예외 시 False(로그인 안 됨)로 fail-closed 반환, 읽기 전용 DOM 텍스트 검사, 쓰기 없음
        return False


def _hiworks_login(page):
    from scripts.auth.login_detector import monitor_for_login

    return {
        "ok": False,
        "reason": "manual_login_required",
        "user": "",
        "needs_manual": True,
        "monitor": monitor_for_login,
    }


def build_sites(spec_cls):
    """등록할 사이트 목록(순서 유지 — `list_sites()` 순서와 같다). `spec_cls` 는 코어의 SiteSpec."""
    return [
        spec_cls(
            key="eum",
            base_url="https://eum.cw.or.kr/main",
            login_domain_hints=("eum.cw.or.kr/web/log/WEBLOG400M00", "eum.cw.or.kr/login", "eum.cw.or.kr/web/login"),
            is_logged_in=_eum_is_logged_in,
            login=_eum_login,
            login_strategy="registered_only",
        ),
        spec_cls(
            key="naver",
            base_url="https://www.naver.com",
            login_domain_hints=("nid.naver.com", "/nidlogin"),
            is_logged_in=_naver_is_logged_in,
            login=_naver_login,
            login_strategy="registered_only",
        ),
        spec_cls(
            key="smartstore",
            base_url="https://sell.smartstore.naver.com/#/home/dashboard",
            login_domain_hints=("sell.smartstore.naver.com", "nid.naver.com", "/nidlogin"),
            is_logged_in=_smartstore_is_logged_in,
            login=_smartstore_login,
            login_strategy="manual_only",
        ),
        spec_cls(
            key="google",
            base_url="https://www.google.com",
            login_domain_hints=("accounts.google.com",),
            is_logged_in=_google_is_logged_in,
            login=_google_login,
            login_strategy="registered_only",
        ),
        spec_cls(
            key="hiworks",
            base_url="https://dashboard.office.hiworks.com/",
            login_domain_hints=("login.office.hiworks.com", "office.hiworks.com"),
            is_logged_in=_hiworks_is_logged_in,
            login=_hiworks_login,
            login_strategy="manual_only",
        ),
        spec_cls(
            key="gabia",
            base_url="https://www.gabia.com",
            login_domain_hints=("account.gabia.com",),
            is_logged_in=_gabia_is_logged_in,
            login=_gabia_login,
            login_strategy="manual_only",
        ),
        spec_cls(
            key="kakao",
            base_url="https://www.kakao.com",
            login_domain_hints=("accounts.kakao.com",),
            is_logged_in=_kakao_is_logged_in,
            login=_kakao_login,
            login_strategy="manual_only",
        ),
    ]


def install() -> None:
    """사이트 등록표 코어에 사이트 목록 공급자를 알린다. 여러 번 불러도 같다(멱등)."""
    site_registry.configure(build_sites)
