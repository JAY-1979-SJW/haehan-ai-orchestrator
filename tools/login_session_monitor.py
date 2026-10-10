"""실시간 로그인 세션 감시 데몬.

네이버 / Google / 스마트스토어 세션 상태를 주기적으로 CDP 폴링하여
세션 만료·로그인 페이지 진입·챌린지 감지 시 즉시 콘솔 경고와
data/login_session_monitor_latest.json 갱신.

사용:
    python scripts/ops/session_monitor.py              # 기본 30초 간격
    python scripts/ops/session_monitor.py --interval 10
    python scripts/ops/session_monitor.py --once        # 1회 체크 후 종료

보안:
    쿠키/토큰/비밀번호 값 출력 금지.
    세션 존재 여부(bool)만 출력.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

_BOOT = Path(__file__).resolve().parents[1]  # 정본을 import 하기 전 sys.path 부트스트랩(G5 예외: scripts/ 독립 실행)
if str(_BOOT) not in sys.path:
    sys.path.insert(0, str(_BOOT))

from scripts.common.app_paths import repo_root  # noqa: E402

ROOT = repo_root()
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_PATH = DATA_DIR / "login_session_monitor_latest.json"

CDP_PORT = 9222


# ── 사이트 정의 ───────────────────────────────────────────────────────────────

SITES: list[dict] = [
    {
        "key": "naver",
        "label": "네이버",
        "url_hints": ["naver.com"],
        "session_cookie_pattern": r"NID_SES|NID_AUT|NID_JKL",
        "logged_in_js": """(() => {
            const t = document.body && document.body.innerText || '';
            const cookies = document.cookie || '';
            const has_session = /NID_SES|NID_AUT|NID_JKL/.test(cookies);
            const has_logout = /로그아웃/.test(t);
            const has_mypage = /마이페이지|MY프로필|내 정보/.test(t);
            const has_login_form = !!document.querySelector('#id,input[name="id"]');
            const challenge = /SMS|추가 인증|본인 확인|보안 인증|OTP/.test(t);
            const login_error = /비밀번호가 틀|로그인 오류|잠금|차단/.test(t);
            return JSON.stringify({
                href: location.href,
                title: document.title,
                has_session_cookie: has_session,
                has_logout_link: has_logout,
                has_mypage: has_mypage,
                has_login_form: has_login_form,
                challenge: challenge,
                login_error: login_error,
            });
        })()""",
        "login_url": "https://nid.naver.com/nidlogin.login",
    },
    {
        "key": "google",
        "label": "Google",
        "url_hints": ["google.com", "accounts.google.com"],
        "session_cookie_pattern": r"SSID|SID|HSID|APISID|__Secure-3PSID",
        "logged_in_js": """(() => {
            const t = document.body && document.body.innerText || '';
            const cookies = document.cookie || '';
            const has_session = /SSID|^SID=|HSID|APISID/.test(cookies);
            const has_account_menu = !!document.querySelector(
                'a[aria-label*="Google 계정"], a[aria-label*="Google Account"], [data-ogsr-up]'
            );
            const has_login_form = !!document.querySelector(
                'input[type="email"], input[name="identifier"]'
            );
            const has_pw_form = !!document.querySelector('input[type="password"]');
            const challenge = /2단계|2-Step|본인 확인|추가 인증|보안 코드/.test(t);
            const login_error = /잘못된 비밀번호|이 계정은|찾을 수 없/.test(t);
            return JSON.stringify({
                href: location.href,
                title: document.title,
                has_session_cookie: has_session,
                has_account_menu: has_account_menu,
                has_login_form: has_login_form,
                has_pw_form: has_pw_form,
                challenge: challenge,
                login_error: login_error,
            });
        })()""",
        "login_url": "https://accounts.google.com/signin",
    },
    {
        "key": "smartstore",
        "label": "스마트스토어",
        "url_hints": ["sell.smartstore.naver.com", "smartstore.naver.com"],
        "session_cookie_pattern": r"NID_SES|NID_AUT|smc_session",
        "logged_in_js": """(() => {
            const t = document.body && document.body.innerText || '';
            const cookies = document.cookie || '';
            const has_session = /NID_SES|NID_AUT|smc_session/.test(cookies);
            const has_logout = /로그아웃/.test(t);
            const has_dashboard = /스토어 현황|판매 관리|상품 관리|주문 관리/.test(t);
            const has_login_form = !!document.querySelector('#id,input[name="id"],input[type="password"]');
            const challenge = /보안 인증|추가 인증|SMS/.test(t);
            return JSON.stringify({
                href: location.href,
                title: document.title,
                has_session_cookie: has_session,
                has_logout_link: has_logout,
                has_dashboard: has_dashboard,
                has_login_form: has_login_form,
                challenge: challenge,
            });
        })()""",
        "login_url": "https://sell.smartstore.naver.com/",
    },
    {
        "key": "gabia",
        "label": "가비아",
        "url_hints": ["gabia.com", "my.gabia.com", "account.gabia.com"],
        "session_cookie_pattern": r"gabia_session|gab_|PHPSESSID",
        "logged_in_js": """(() => {
            const t = document.body && document.body.innerText || '';
            const url = location.href.toLowerCase();
            const has_logout = /로그아웃|logout/i.test(t);
            const has_my = /마이가비아|내정보|계정관리|my.gabia/i.test(t);
            const has_login_form = !!document.querySelector('input[type="password"]');
            const on_login_page = url.includes('account.gabia.com');
            const challenge = /OTP|2단계|추가 인증/.test(t);
            return JSON.stringify({
                href: location.href,
                title: document.title,
                has_session_cookie: has_logout || has_my,
                has_logout_link: has_logout,
                has_mypage: has_my,
                has_login_form: has_login_form || on_login_page,
                challenge: challenge,
                login_error: false,
            });
        })()""",
        "login_url": "https://account.gabia.com/gabia/login",
    },
    {
        "key": "eum",
        "label": "EUM (건설근로자공제회)",
        "url_hints": ["eum.cw.or.kr"],
        "session_cookie_pattern": r"JSESSIONID|eum_session",
        "logged_in_js": """(() => {
            const t = document.body && document.body.innerText || '';
            const url = location.href;
            const has_logout = /로그아웃/.test(t);
            const has_dashboard = /단말기|현장|공제|임대|관리/.test(t) && !url.includes('login') && !url.includes('WEBLOG');
            const has_login_form = !!document.querySelector('input[type="password"], input[name="userId"], input[name="password"]');
            const on_login = url.includes('WEBLOG') || url.includes('login');
            const challenge = /인증|보안/.test(t) && has_login_form;
            return JSON.stringify({
                href: location.href,
                title: document.title,
                has_session_cookie: has_logout || has_dashboard,
                has_logout_link: has_logout,
                has_dashboard: has_dashboard,
                has_login_form: has_login_form || on_login,
                challenge: challenge,
                login_error: false,
            });
        })()""",
        "login_url": "https://eum.cw.or.kr/web/log/WEBLOG400M00",
    },
    {
        "key": "youtube_studio",
        "label": "YouTube Studio",
        "url_hints": ["studio.youtube.com"],
        "session_cookie_pattern": r"SSID|SID|HSID|LOGIN_INFO",
        "logged_in_js": """(() => {
            const t = document.body && document.body.innerText || '';
            const url = location.href;
            const has_studio = url.includes('studio.youtube.com') && !url.includes('accounts.google');
            const has_dashboard = /채널|영상|분석|구독자|수익/.test(t);
            const has_login_form = !!document.querySelector('input[type="email"], input[name="identifier"]');
            const has_account = !!document.querySelector('[aria-label*="계정"], [aria-label*="Account"]');
            const challenge = /2단계|2-Step|추가 인증/.test(t);
            return JSON.stringify({
                href: location.href,
                title: document.title,
                has_session_cookie: has_studio && !has_login_form,
                has_logout_link: false,
                has_account_menu: has_account || has_dashboard,
                has_login_form: has_login_form,
                challenge: challenge,
                login_error: false,
            });
        })()""",
        "login_url": "https://studio.youtube.com/",
    },
    {
        "key": "kakao",
        "label": "카카오",
        "url_hints": ["kakao.com", "accounts.kakao.com", "talk.kakao.com"],
        "session_cookie_pattern": r"TIARA|_kauth_|kc_",
        "logged_in_js": """(() => {
            const t = document.body && document.body.innerText || '';
            const url = location.href.toLowerCase();
            const has_logout = /로그아웃|logout/i.test(t);
            const has_profile = /닉네임|프로필|내 계정|마이카카오/i.test(t);
            const has_login_form = !!document.querySelector('input[type="password"], #loginId, #loginKey');
            const on_login = url.includes('accounts.kakao.com/login') || url.includes('/login');
            const challenge = /SMS|인증|카카오톡 인증/i.test(t) && has_login_form;
            return JSON.stringify({
                href: location.href,
                title: document.title,
                has_session_cookie: has_logout || has_profile,
                has_logout_link: has_logout,
                has_mypage: has_profile,
                has_login_form: has_login_form || on_login,
                challenge: challenge,
                login_error: false,
            });
        })()""",
        "login_url": "https://accounts.kakao.com/login",
    },
    {
        "key": "hiworks",
        "label": "하이웍스",
        "url_hints": ["hiworks.com", "mail.hiworks.com"],
        "session_cookie_pattern": r"hiworks_|hw_sess|PHPSESSID",
        "logged_in_js": """(() => {
            const t = document.body && document.body.innerText || '';
            const url = location.href.toLowerCase();
            const has_logout = /로그아웃|logout/i.test(t);
            const has_dashboard = /받은편지|캘린더|주소록|그룹웨어|업무/i.test(t);
            const has_login_form = !!document.querySelector('input[type="password"], input[name="pw"], input[name="password"]');
            const on_login = url.includes('/login') || url.includes('/auth');
            const challenge = false;
            return JSON.stringify({
                href: location.href,
                title: document.title,
                has_session_cookie: has_logout || has_dashboard,
                has_logout_link: has_logout,
                has_dashboard: has_dashboard,
                has_login_form: has_login_form || on_login,
                challenge: challenge,
                login_error: false,
            });
        })()""",
        "login_url": "https://www.hiworks.com/login",
    },
    {
        "key": "dataportal",
        "label": "공공데이터포털",
        "url_hints": ["data.go.kr", "auth.data.go.kr"],
        "session_cookie_pattern": r"JSESSIONID|dataportal_",
        "logged_in_js": """(() => {
            const t = document.body && document.body.innerText || '';
            const url = location.href.toLowerCase();
            const has_logout = /로그아웃|logout/i.test(t);
            const has_mypage = /마이페이지|내 정보|활용현황|인증키/i.test(t);
            const on_mypage = url.includes('my-page') || url.includes('mypage') || url.includes('member/info');
            const has_login_form = !on_mypage && !!document.querySelector('input[type="password"], #loginId, input[name="password"]');
            const on_login = !on_mypage && (url.includes('/login') || url.includes('/member/login') || url.includes('common-login'));
            const challenge = false;
            return JSON.stringify({
                href: location.href,
                title: document.title,
                has_session_cookie: has_logout || has_mypage,
                has_logout_link: has_logout,
                has_mypage: has_mypage,
                has_login_form: has_login_form || on_login,
                challenge: challenge,
                login_error: false,
            });
        })()""",
        "login_url": "https://www.data.go.kr/login/loginForm.do",
    },
]


# ── 상태 모델 ─────────────────────────────────────────────────────────────────


@dataclass
class SessionState:
    key: str
    label: str
    status: str  # LOGGED_IN | SESSION_EXPIRED | LOGIN_REQUIRED | CHALLENGE | ERROR | NO_TAB
    detail: str
    href: str
    title: str
    has_session_cookie: bool
    checked_at: str
    prev_status: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── CDP 헬퍼 ──────────────────────────────────────────────────────────────────


def _cdp_targets() -> list[dict]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=2.0) as r:
            return [t for t in json.loads(r.read()) if isinstance(t, dict)]
    except Exception:  # noqa: BLE001 - CDP 탭 목록 조회/JS 평가 실패시 빈 목록·오류 dict를 반환하는 읽기전용 로그인상태 모니터링 — 로그인 상태를 바꾸지 않음
        return []


async def _eval_js(ws_url: str, expr: str, timeout: float = 5.0) -> dict | None:
    try:
        import websockets as _ws

        async with _ws.connect(ws_url, max_size=4 * 1024 * 1024, open_timeout=4) as conn:
            await conn.send(
                json.dumps(
                    {
                        "id": 1,
                        "method": "Runtime.evaluate",
                        "params": {"expression": expr, "returnByValue": True},
                    }
                )
            )
            raw = await asyncio.wait_for(conn.recv(), timeout=timeout)
            val = json.loads(raw).get("result", {}).get("result", {}).get("value")
            if isinstance(val, str):
                return json.loads(val)
            return val
    except Exception as exc:  # noqa: BLE001 - CDP 탭 목록 조회/JS 평가 실패시 빈 목록·오류 dict를 반환하는 읽기전용 로그인상태 모니터링 — 로그인 상태를 바꾸지 않음
        return {"_err": str(exc)[:120]}


def _find_tab_for_site(targets: list[dict], url_hints: list[str]) -> dict | None:
    for t in targets:
        if t.get("type") != "page":
            continue
        url = t.get("url", "")
        if any(h in url for h in url_hints):
            return t
    return None


# ── 사이트별 세션 체크 ────────────────────────────────────────────────────────


async def check_site(site: dict, targets: list[dict]) -> SessionState:
    now = datetime.now(UTC).isoformat()
    tab = _find_tab_for_site(targets, site["url_hints"])

    if tab is None:
        return SessionState(
            key=site["key"],
            label=site["label"],
            status="NO_TAB",
            detail="브라우저에 해당 탭 없음",
            href="",
            title="",
            has_session_cookie=False,
            checked_at=now,
        )

    ws_url = tab.get("webSocketDebuggerUrl", "")
    if not ws_url:
        return SessionState(
            key=site["key"],
            label=site["label"],
            status="ERROR",
            detail="webSocketDebuggerUrl 없음",
            href=tab.get("url", ""),
            title=tab.get("title", ""),
            has_session_cookie=False,
            checked_at=now,
        )

    data = await _eval_js(ws_url, site["logged_in_js"])

    if data is None or (isinstance(data, dict) and data.get("_err")):
        err = (data or {}).get("_err", "eval 실패")
        return SessionState(
            key=site["key"],
            label=site["label"],
            status="ERROR",
            detail=err,
            href=tab.get("url", ""),
            title=tab.get("title", ""),
            has_session_cookie=False,
            checked_at=now,
        )

    href = data.get("href", "")
    title = data.get("title", "")
    has_session = bool(data.get("has_session_cookie"))

    # 상태 판정
    if data.get("challenge"):
        status = "CHALLENGE"
        detail = "추가 인증 / 2단계 인증 요구됨"
    elif data.get("login_error"):
        status = "LOGIN_ERROR"
        detail = "로그인 오류 메시지 감지"
    elif data.get("has_login_form"):
        status = "LOGIN_REQUIRED"
        detail = "로그인 폼 감지 — 세션 만료"
    elif has_session and (
        data.get("has_logout_link")
        or data.get("has_account_menu")
        or data.get("has_dashboard")
        or data.get("has_mypage")
    ):
        status = "LOGGED_IN"
        detail = "세션 정상"
    elif has_session:
        status = "LOGGED_IN"
        detail = "세션 쿠키 존재 (UI 확인 불가)"
    else:
        status = "SESSION_EXPIRED"
        detail = "세션 쿠키 없음"

    return SessionState(
        key=site["key"],
        label=site["label"],
        status=status,
        detail=detail,
        href=href,
        title=title,
        has_session_cookie=has_session,
        checked_at=now,
    )


# ── 보고 / 저장 ───────────────────────────────────────────────────────────────

_ALERT_STATUSES = {"SESSION_EXPIRED", "LOGIN_REQUIRED", "CHALLENGE", "LOGIN_ERROR"}
_prev_states: dict[str, str] = {}


def _report(states: list[SessionState], elapsed: float) -> None:
    ts = datetime.now().strftime("%H:%M:%S")

    for s in states:
        prev = _prev_states.get(s.key, "")
        changed = s.status != prev
        icon = (
            "✅"
            if s.status == "LOGGED_IN"
            else ("🔴" if s.status in _ALERT_STATUSES else "⚠️" if s.status in ("ERROR", "NO_TAB") else "❓")
        )

        if changed:
            if s.status in _ALERT_STATUSES:
                print(
                    f"\n{'=' * 60}\n"
                    f"[{ts}] 🚨 세션 경고 — {s.label}\n"
                    f"  상태: {s.status}\n"
                    f"  원인: {s.detail}\n"
                    f"  URL : {s.href[:100]}\n"
                    f"{'=' * 60}\n",
                    flush=True,
                )
            else:
                print(
                    f"[{ts}] {icon} {s.label} {prev or 'INIT'} → {s.status}  {s.detail}",
                    flush=True,
                )
        else:
            print(
                f"[{ts}] {icon} {s.label:12s} {s.status:16s}  {s.detail}",
                flush=True,
            )

        _prev_states[s.key] = s.status

    # JSON 저장
    payload = {
        "checked_at": datetime.now(UTC).isoformat(),
        "elapsed_sec": round(elapsed, 2),
        "cdp_available": len(_cdp_targets()) > 0,
        "sites": [s.to_dict() for s in states],
        "alert": any(s.status in _ALERT_STATUSES for s in states),
    }
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 메인 루프 ─────────────────────────────────────────────────────────────────


async def run_once() -> list[SessionState]:
    targets = _cdp_targets()
    if not targets:
        print("[session_monitor] CDP 연결 없음 — Chrome CDP 미실행 상태", flush=True)
        return []
    tasks = [check_site(site, targets) for site in SITES]
    return await asyncio.gather(*tasks)


async def monitor_loop(interval: int) -> None:
    print(
        f"[session_monitor] 실시간 세션 감시 시작 "
        f"(간격={interval}s, 사이트={[s['label'] for s in SITES]})\n"
        f"  결과파일: {OUTPUT_PATH}\n"
        f"  Ctrl+C 로 종료\n",
        flush=True,
    )
    while True:
        t0 = time.monotonic()
        states = await run_once()
        elapsed = time.monotonic() - t0
        if states:
            _report(states, elapsed)
        await asyncio.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="실시간 로그인 세션 감시")
    parser.add_argument("--interval", type=int, default=30, help="폴링 간격(초)")
    parser.add_argument("--once", action="store_true", help="1회 체크 후 종료")
    args = parser.parse_args()

    if args.once:
        states = asyncio.run(run_once())
        if states:
            _report(states, 0)
            has_alert = any(s.status in _ALERT_STATUSES for s in states)
            sys.exit(1 if has_alert else 0)
        sys.exit(0)

    try:
        asyncio.run(monitor_loop(args.interval))
    except KeyboardInterrupt:
        print("\n[session_monitor] 종료.", flush=True)


if __name__ == "__main__":
    main()
