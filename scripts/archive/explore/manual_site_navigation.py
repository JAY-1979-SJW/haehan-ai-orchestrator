"""사이트 수동 네비게이션 + 스크린샷 캡처
- 각 주요 관리 페이지 방문
- 단말기 현황 정보 수집
- 임대 현장별 분류
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.web_connector import get_page
from scripts.logger import get_logger

_log = get_logger(__name__)


def visit_page(page, url: str, page_name: str) -> dict:
    """페이지 방문 및 정보 수집"""
    print(f"\n{'─'*80}")
    print(f"[{page_name}]")
    print(f"{url}")
    print(f"{'─'*80}")

    try:
        page.goto(url, timeout=30000)
        page.wait_for_load_state("load", timeout=5000)

        try:
            from scripts.popup_detector import handle_page_popups
            handle_page_popups(page, timeout_s=1.0)
        except:
            pass

        # 페이지 정보 추출
        info = page.evaluate("""
        (() => {
            return {
                title: document.title,
                pageText: document.body.innerText.substring(0, 2000),
                tables: Array.from(document.querySelectorAll('table')).length,
                tableRows: Array.from(document.querySelectorAll('table tbody tr')).length,
                hasData: document.body.innerText.includes('조회된 내역') ? '없음' : '있음'
            };
        })();
        """)

        print(f"  제목: {info['title']}")
        print(f"  테이블: {info['tables']}개, 행: {info['tableRows']}개")
        print(f"  데이터: {info['hasData']}")

        return {
            'name': page_name,
            'url': url,
            'info': info,
            'success': True
        }

    except Exception as e:
        print(f"  ✗ 오류: {e}")
        return {
            'name': page_name,
            'url': url,
            'error': str(e),
            'success': False
        }


def main():
    page = get_page()

    # 주요 관리 페이지들
    pages_to_visit = [
        ("https://eum.cw.or.kr/web/man/WEBMAN380M00", "단말기 관리 - 현장별 단말기 목록"),
        ("https://eum.cw.or.kr/web/man/WEBMAN381M00", "단말기 관리 - 단말기 설치계획"),
        ("https://eum.cw.or.kr/web/man/WEBMAN382M00", "단말기 관리 - 단말기 철거"),
        ("https://eum.cw.or.kr/web/man/WEBMAN390M00", "기타 관리 - 단말기설치현황"),
        ("https://eum.cw.or.kr/web/man/WEBMAN400M00", "기타 관리 - 단말기별 이력관리"),
        ("https://eum.cw.or.kr/mypage", "마이페이지 - 대시보드"),
    ]

    print("\n" + "="*80)
    print("[건설근로자공제회 단말기 보유 현황 - 사이트 네비게이션]")
    print("="*80)
    print(f"\n사용자 정보:")
    print(f"  • 총 보유 단말기: 40대")
    print(f"  • 현재 임대 중: 영천 현장 1대 (+추가 현장)")
    print(f"  • 목표: 전체 임대 현장 파악")

    results = []
    for url, page_name in pages_to_visit:
        result = visit_page(page, url, page_name)
        results.append(result)
        time.sleep(1)

    # 최종 요약
    print(f"\n{'='*80}")
    print("[방문 완료]")
    print(f"{'='*80}\n")

    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]

    print(f"✓ 성공: {len(successful)}개")
    for r in successful:
        print(f"  • {r['name']}")

    if failed:
        print(f"\n✗ 실패: {len(failed)}개")
        for r in failed:
            print(f"  • {r['name']}")

    # 다음 단계 제시
    print(f"\n{'='*80}")
    print("[다음 단계]")
    print(f"{'='*80}\n")

    print("""
실제 40대 단말기와 임대 현장을 모두 파악하기 위해:

1️⃣  WEBMAN380M00 (현장별 단말기 목록) - 수동 필터링
   • 필터: [지역] [상태] [기타] 조합으로 모든 데이터 조회
   • 스크린샷: 첫 번째 페이지부터 마지막 페이지까지
   • 각 현장의 임대 상태/종료일 기록

2️⃣  WEBMAN390M00 (단말기설치현황)
   • 설치됨/미설치 상태로 분류
   • 현재 운영 중인 단말기 파악

3️⃣  WEBMAN400M00 (단말기별 이력관리)
   • 단말기 상태: 정상/장애/수리중
   • 단말기 유형: 구매/임대
   • 형태: 이동형/벽부형/부스형

4️⃣  구체적 정보 입력 필요
   • 영천 외 다른 임대 현장명 확인
   • 각 현장별 단말기 수 파악
   • 반납/교체 예정일 확인
    """)

    # JSON 저장
    output_file = Path("data") / "site_navigation_report.json"
    output_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    _log.info(f"✓ 네비게이션 결과 저장: {output_file}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log.error(f"실행 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
