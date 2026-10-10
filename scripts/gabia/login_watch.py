"""가비아 로그인 실시간 감지 스크립트.

GABIA_LOGIN_WATCH_01

용도:
  가비아 로그인 화면에서 대표님이 직접 로그인할 때까지 실시간으로 감지하고,
  로그인 확인 즉시 DNS 관리 화면으로 자동 이동한다.

실행:
  python scripts/gabia/login_watch.py
  python scripts/gabia/login_watch.py --timeout 600
  python scripts/gabia/login_watch.py --no-navigate   # 로그인 감지만, DNS 이동 없음

금지:
  비밀번호/OTP 자동 입력 금지
  쿠키/session 추출 금지
  최종 저장 버튼 자동 클릭 금지
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # 저장소 루트 — sys.path 부트스트랩(scripts/gabia/ 깊이)
sys.path.insert(0, str(ROOT))

GABIA_LOGIN_URL = "https://accounts.gabia.com/"
GABIA_DNS_MGMT_URL = "https://my.gabia.com/service/domain/haehan-ai.kr/dns"
GABIA_MY_URL = "https://my.gabia.com/"

POLL_INTERVAL_S = 1
DEFAULT_TIMEOUT_S = 300

# 가비아 로그인 판정 신호 (DOM 기반)
_GABIA_LOGGED_IN_JS = r"""
() => {
    const txt = (document.body?.innerText || '').toLowerCase();
    const url = location.href.toLowerCase();

    // 로그아웃 텍스트/링크 존재 = 로그인됨
    if (/로그아웃|logout/i.test(txt)) return {logged_in: true, signal: 'logout_text'};

    // my.gabia.com 대시보드 도달 = 로그인됨
    if (url.includes('my.gabia.com') && !url.includes('accounts.gabia.com')) {
        const hasDash = !!document.querySelector('.my-header, .user-name, [class*="UserInfo"], [class*="mypage"]');
        if (hasDash) return {logged_in: true, signal: 'my_dashboard'};
        // 대시보드 페이지인데 로그인 요소 없으면 보류
        if (url.includes('/dashboard') || url === 'https://my.gabia.com/') {
            const hasLoginForm = !!document.querySelector('input[type="password"]');
            if (!hasLoginForm) return {logged_in: true, signal: 'dashboard_no_form'};
        }
    }

    // 로그인 폼 없고 accounts 아님 = 로그인됨
    const hasPasswordField = !!document.querySelector('input[type="password"]');
    const onLoginPage = url.includes('accounts.gabia.com');
    if (!hasPasswordField && !onLoginPage && url.includes('gabia')) {
        return {logged_in: true, signal: 'no_password_field'};
    }

    return {logged_in: false, signal: 'not_detected'};
}
"""


def _get_page():
    from scripts.browser.cdp.connection import get_page

    return get_page()


def _current_url(page) -> str:
    try:
        return page.url or ""
    except Exception:  # noqa: BLE001 - 가비아 로그인 상태 감시(읽기전용) - URL/JS 평가 실패 시 재획득/재시도, 실제 DNS 변경 없음
        return ""


def watch_gabia_login(timeout_s: int = DEFAULT_TIMEOUT_S, navigate_after: bool = True) -> dict:  # noqa: C901, PLR0915 - 이동 전부터 있던 복잡도
    """가비아 로그인 실시간 감지 메인 루프.

    Returns:
        {
            "logged_in": bool,
            "elapsed_s": int,
            "signal": str,
            "url": str,
            "navigated_to_dns": bool,
        }
    """
    page = _get_page()
    start = time.time()
    last_url = ""
    tick = 0

    print("=" * 60)
    print("가비아 로그인 실시간 감지 시작")
    print(f"  최대 대기: {timeout_s}초 / 폴링: {POLL_INTERVAL_S}초")
    print("  브라우저에서 가비아 로그인을 진행하세요.")
    print("  비밀번호/OTP는 대표님이 직접 입력하세요.")
    print("=" * 60)

    while time.time() - start < timeout_s:
        tick += 1
        elapsed = int(time.time() - start)

        try:
            # 활성 탭 재획득 (탭 이동 대응)
            try:
                current_url = _current_url(page)
                if not current_url or "about:blank" in current_url:
                    page = _get_page()
                    current_url = _current_url(page)
            except Exception:  # noqa: BLE001 - 가비아 로그인 상태 감시(읽기전용) - URL/JS 평가 실패 시 재획득/재시도, 실제 DNS 변경 없음
                page = _get_page()
                current_url = _current_url(page)

            # URL 변화 보고
            if current_url != last_url:
                last_url = current_url
                short = current_url[:80]
                print(f"  [{elapsed:>3}s] URL 변화 감지: {short}")

            # 로그인 판정 (JS)
            try:
                result = page.evaluate(_GABIA_LOGGED_IN_JS)
                if result and result.get("logged_in"):
                    signal = result.get("signal", "unknown")
                    print()
                    print(f"✓ 가비아 로그인 감지됨! ({elapsed}초, 신호: {signal})")
                    print(f"  URL: {current_url}")

                    dns_navigated = False
                    if navigate_after:
                        print()
                        print("  → DNS 관리 화면으로 이동 중...")
                        try:
                            from scripts.browser.navigator.navigator import goto

                            goto(GABIA_DNS_MGMT_URL)
                            dns_navigated = True
                            print(f"  → DNS 관리 화면 이동 완료: {GABIA_DNS_MGMT_URL}")
                        except Exception as nav_err:  # noqa: BLE001 - 가비아 로그인 상태 감시(읽기전용) - URL/JS 평가 실패 시 재획득/재시도, 실제 DNS 변경 없음
                            print(f"  ⚠ DNS 화면 자동 이동 실패: {nav_err}")
                            print(f"    수동으로 이동하세요: {GABIA_DNS_MGMT_URL}")

                    print()
                    print("=" * 60)
                    print("로그인 감지 완료 — 다음 단계: DNS 레코드 입력 준비")
                    print("=" * 60)

                    return {
                        "logged_in": True,
                        "elapsed_s": elapsed,
                        "signal": signal,
                        "url": current_url,
                        "navigated_to_dns": dns_navigated,
                    }
            except Exception as js_err:  # noqa: BLE001 - 가비아 로그인 상태 감시(읽기전용) - URL/JS 평가 실패 시 재획득/재시도, 실제 DNS 변경 없음
                # 탭 닫힘 등 예외 → 재획득
                if "has been closed" in str(js_err) or "Target" in str(js_err):
                    page = _get_page()

        except Exception as outer_err:  # noqa: BLE001 - 가비아 로그인 상태 감시(읽기전용) - URL/JS 평가 실패 시 재획득/재시도, 실제 DNS 변경 없음
            if tick % 10 == 0:
                print(f"  [{elapsed:>3}s] 대기 중... ({str(outer_err)[:50]})")

        # 진행 표시 (10초마다)
        if tick % 10 == 0:
            elapsed = int(time.time() - start)
            print(f"  [{elapsed:>3}s] 로그인 대기 중...")

        time.sleep(POLL_INTERVAL_S)

    elapsed = int(time.time() - start)
    print()
    print(f"✗ 타임아웃 — {elapsed}초 동안 로그인 감지 안됨")
    return {
        "logged_in": False,
        "elapsed_s": elapsed,
        "signal": "timeout",
        "url": last_url,
        "navigated_to_dns": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="가비아 로그인 실시간 감지")
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT_S, help=f"최대 대기 시간(초) (기본: {DEFAULT_TIMEOUT_S})"
    )
    parser.add_argument("--no-navigate", action="store_true", help="로그인 감지 후 DNS 관리 화면 자동 이동 안 함")
    args = parser.parse_args()

    result = watch_gabia_login(
        timeout_s=args.timeout,
        navigate_after=not args.no_navigate,
    )

    sys.exit(0 if result["logged_in"] else 1)


if __name__ == "__main__":
    main()
