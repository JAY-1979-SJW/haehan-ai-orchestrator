"""브라우저 탭 상태 모니터링 및 제어.

기능:
  1. 현재 활성 탭 개수 탐지
  2. 각 탭의 URL 조회
  3. 유휴 탭 자동 정리
  4. 탭 개수 제한 (비정상 접근 방지)
"""
from __future__ import annotations

import time
from typing import Any

from scripts.logger import get_logger

log = get_logger(__name__)


def get_active_tabs() -> list[dict[str, Any]]:
    """현재 활성 탭 목록 반환."""
    try:
        from scripts.web_connector import get_page

        page = get_page()
        context = page.context

        tabs = []
        for i, p in enumerate(context.pages, 1):
            # title은 메서드이므로 호출해야 함
            title_str = p.title() if callable(p.title) else str(p.title)
            tabs.append({
                "index": i,
                "url": p.url,
                "title": title_str,
                "page_obj": p,  # 페이지 객체 저장
            })

        return tabs
    except Exception as e:
        log.debug(f"탭 조회 실패: {e}")
        return []


def get_tab_count() -> int:
    """현재 활성 탭 개수."""
    return len(get_active_tabs())


def close_extra_tabs(keep_count: int = 1, target_domain: str | None = None) -> int:
    """초과 탭 닫기.

    Args:
        keep_count: 유지할 탭 개수 (기본값: 1)
        target_domain: 특정 도메인만 닫기 (예: "naver.com")

    Returns:
        닫은 탭 개수
    """
    try:
        from playwright.sync_api import sync_playwright

        tabs = get_active_tabs()
        closed = 0

        # 도메인별 필터링
        if target_domain:
            target_tabs = [t for t in tabs if target_domain in t["url"]]
        else:
            target_tabs = tabs[keep_count:]

        # 뒤쪽부터 닫기 (활성 탭은 유지)
        for i, tab in enumerate(target_tabs):
            try:
                page_obj = tab.get("page_obj")
                if page_obj and not page_obj.is_closed():
                    page_obj.close()
                    closed += 1
                    log.info(f"[탭 제어] 탭 닫음: {tab['url']}")
                    time.sleep(0.3)  # 탭 닫기 간 대기
            except Exception as e:
                log.debug(f"[탭 제어] 탭 종료 실패: {e}")

        return closed

    except Exception as e:
        log.error(f"[탭 제어] 정리 실패: {e}")
        return 0


def close_tabs_by_domain(domain: str) -> int:
    """특정 도메인의 모든 탭 닫기.

    Args:
        domain: 닫을 도메인 (예: "naver.com", "smartstore.naver.com")

    Returns:
        닫은 탭 개수
    """
    try:
        tabs = get_active_tabs()
        closed = 0

        for tab in tabs:
            if domain in tab["url"]:
                try:
                    page_obj = tab.get("page_obj")
                    if page_obj:
                        page_obj.close()
                        closed += 1
                        log.info(f"[탭 제어] {domain} 탭 닫음: {tab['url']}")
                        time.sleep(0.2)
                except Exception as e:
                    log.debug(f"[탭 제어] 탭 종료 실패: {e}")

        return closed

    except Exception as e:
        log.error(f"[탭 제어] 도메인 정리 실패: {e}")
        return 0


def log_tab_status() -> None:
    """현재 탭 상태 로깅."""
    tabs = get_active_tabs()
    log.info(f"[탭 상태] 현재 활성 탭: {len(tabs)}개")
    for tab in tabs:
        log.info(f"  [{tab['index']}] {tab['url']}")


def print_tab_list(filter_domain: str | None = None) -> None:
    """탭 목록을 보기 좋게 출력.

    Args:
        filter_domain: 특정 도메인만 필터 (예: "eum.cw.or.kr")
    """
    tabs = get_active_tabs()

    print("\n" + "=" * 80)
    print(f"  브라우저 탭 목록 ({len(tabs)}개)")
    print("=" * 80)

    if not tabs:
        print("  (탭 없음)")
        print("=" * 80 + "\n")
        return

    # 필터링
    if filter_domain:
        filtered = [t for t in tabs if filter_domain in t["url"]]
        print(f"  필터: {filter_domain} ({len(filtered)}개)")
    else:
        filtered = tabs

    # 출력
    for tab in filtered:
        idx = tab["index"]
        url = tab["url"]
        title = tab["title"]

        # URL 길이 제한
        if len(url) > 70:
            url_display = url[:67] + "..."
        else:
            url_display = url

        # 제목 추출
        if title and title != "":
            title_display = f" - {title[:40]}"
        else:
            title_display = ""

        print(f"  [{idx:2d}] {url_display}{title_display}")

    print("=" * 80 + "\n")


def cleanup_idle_tabs(target_count: int = 5) -> int:
    """유휴 탭 정리 (전체 탭 개수 제한).

    Args:
        target_count: 목표 탭 개수 (기본값: 5)

    Returns:
        닫은 탭 개수
    """
    count = get_tab_count()
    if count > target_count:
        excess = count - target_count
        log.warning(f"[탭 제어] 과도한 탭 감지: {count}개 → {target_count}개로 정리")
        return close_extra_tabs(keep_count=target_count)
    return 0


def ensure_single_tab() -> None:
    """단일 탭 유지 (비정상 접근 방지).

    초과 탭을 모두 닫고 활성 탭 1개만 유지합니다.
    이를 통해 순차적 요청을 보장하고 비정상 접근 감지를 회피합니다.
    """
    count = get_tab_count()
    if count > 1:
        closed = close_extra_tabs(keep_count=1)
        log.warning(f"[탭 제어] {closed}개 탭 닫음 (단일 탭 유지)")
    log_tab_status()


if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "list":
        # 탭 목록 출력
        filter_domain = sys.argv[2] if len(sys.argv) > 2 else None
        print_tab_list(filter_domain=filter_domain)

    elif cmd == "count":
        # 탭 개수만 출력
        count = get_tab_count()
        print(f"현재 활성 탭: {count}개")

    elif cmd == "cleanup":
        # 탭 정리
        target = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        print(f"\n탭 정리 (목표: {target}개)...")
        closed = cleanup_idle_tabs(target_count=target)
        print(f"✓ {closed}개 탭 닫음")
        print_tab_list()

    elif cmd == "close-domain":
        # 특정 도메인 탭 닫기
        domain = sys.argv[2] if len(sys.argv) > 2 else "naver.com"
        print(f"\n{domain} 탭 닫기...")
        closed = close_tabs_by_domain(domain)
        print(f"✓ {closed}개 탭 닫음")
        print_tab_list()

    elif cmd == "test":
        # 진단용
        log_tab_status()
        print(f"\n총 {get_tab_count()}개 탭")

    else:
        print("""탭 관리 CLI

사용법:
  python scripts/browser_tab_monitor.py list              # 탭 목록 출력
  python scripts/browser_tab_monitor.py list eum.cw      # 특정 도메인 탭만 출력
  python scripts/browser_tab_monitor.py count             # 탭 개수만 출력
  python scripts/browser_tab_monitor.py cleanup 5         # 5개까지 정리
  python scripts/browser_tab_monitor.py close-domain naver.com  # naver.com 탭 닫기
  python scripts/browser_tab_monitor.py test              # 진단용

예시:
  python scripts/browser_tab_monitor.py list              # 모든 탭 표시
  python scripts/browser_tab_monitor.py cleanup 10        # 10개 탭으로 정리
  python scripts/browser_tab_monitor.py close-domain smartstore  # smartstore 탭 정리
""")
