"""현재 열려있는 모든 탭의 로그인 상태 확인.

사용법:
  python scripts/auth/check_login_status.py

결과:
  모든 탭의 URL과 로그인 여부를 표로 출력
  감지된 로그인 사이트는 자동으로 DB에 저장
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _report_tab(page, tab_count: int, detected_logins: list, log, helpers: tuple) -> None:
    """탭 1개의 로그인 상태를 확인해 표의 한 줄로 출력. 새로 감지된 로그인은 저장."""
    extract_domain, find_site_by_domain, detect_login_on_current_tab, save_detected_login = helpers
    url = page.url
    domain = extract_domain(url)
    site = find_site_by_domain(domain) or domain or "unknown"

    # 로그인 상태 확인
    try:
        is_logged_in, detected_site = detect_login_on_current_tab(page)
        status = "✓ 로그인" if is_logged_in else "✗ 미로그인"

        if is_logged_in and detected_site:
            site = detected_site
            if detected_site not in [d["site"] for d in detected_logins]:
                detected_logins.append({"site": detected_site, "url": url})
                save_detected_login(detected_site, page)
                log.info("[check-login] %s 로그인 감지 및 저장", detected_site)

    except Exception as e:  # noqa: BLE001 - 여러 사이트 로그인 상태 읽기전용 확인 CLI — CDP 데몬 미가동/탭확인 실패 시 안내 메시지 출력 후 종료할 뿐 로그인 상태를 변경하지 않음
        status = f"⚠️  오류: {str(e)[:20]}"
        log.debug("[check-login] 탭 %d 확인 실패: %s", tab_count, e)

    # URL 줄임
    url_display = url[:48] if len(url) <= 48 else url[:45] + "..."
    print(f"{tab_count:<3} {url_display:<50} {site:<15} {status:<10}")


def _print_check_summary(tab_count: int, detected_logins: list) -> None:
    """탭 수와 감지된 로그인 사이트 요약 출력."""
    if tab_count == 0:
        print("⚠️  열려있는 탭이 없습니다")
    else:
        print(f"\n✓ 총 {tab_count}개 탭 확인")

    if detected_logins:
        print(f"\n✓ 로그인된 사이트: {len(detected_logins)}개")
        for login in detected_logins:
            print(f"  - {login['site']}")
        print("\n  세션이 자동으로 저장되었습니다.")
    else:
        print("\n  로그인된 사이트가 없습니다.")


def main() -> None:
    print("\n[작업] 현재 열려있는 탭의 로그인 상태 확인\n")

    try:
        import urllib.request

        from scripts.auth.login_detector import (
            _extract_domain,
            _find_site_by_domain,
            detect_login_on_current_tab,
            save_detected_login,
        )
        from scripts.browser.cdp import cdp_db
        from scripts.common.config import CDP_HOST, CDP_PORT
        from scripts.common.logger import get_logger

        log = get_logger(__name__)

        # CDP 포트 확인
        try:
            urllib.request.urlopen(f"http://{CDP_HOST}:{CDP_PORT}/json/version", timeout=2)
        except Exception:  # noqa: BLE001 - 여러 사이트 로그인 상태 읽기전용 확인 CLI — CDP 데몬 미가동/탭확인 실패 시 안내 메시지 출력 후 종료할 뿐 로그인 상태를 변경하지 않음
            print("✗ CDP 데몬이 실행 중이지 않습니다")
            print("  먼저 'python scripts/browser/cdp/cdp_daemon.py start' 실행하세요")
            return

        # Playwright로 현재 브라우저 상태 확인
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                # CDP 연결
                browser = p.chromium.connect_over_cdp(f"http://{CDP_HOST}:{CDP_PORT}")
                contexts = browser.contexts

                if not contexts:
                    print("⚠️  열려있는 탭/컨텍스트가 없습니다")
                    return

                cdp_db.init_db()
                detected_logins: list[Any] = []

                print("=" * 100)
                print(f"{'#':<3} {'URL':<50} {'사이트':<15} {'로그인':<10} 상태")
                print("=" * 100)

                tab_count = 0
                helpers = (_extract_domain, _find_site_by_domain, detect_login_on_current_tab, save_detected_login)
                for ctx_idx, context in enumerate(contexts):
                    pages = context.pages
                    for page_idx, page in enumerate(pages):
                        tab_count += 1
                        _report_tab(page, tab_count, detected_logins, log, helpers)

                print("=" * 100)
                _print_check_summary(tab_count, detected_logins)

                browser.close()

        except ImportError:
            print("✗ Playwright 설치 필요")
            print("  pip install playwright")
            return

    except Exception as e:  # noqa: BLE001 - 여러 사이트 로그인 상태 읽기전용 확인 CLI — CDP 데몬 미가동/탭확인 실패 시 안내 메시지 출력 후 종료할 뿐 로그인 상태를 변경하지 않음
        print(f"✗ 오류: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
