"""전체 단말기 인벤토리 확인 - 페이지네이션 체크 + 모든 레코드 추출"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.web_connector import get_page
from scripts.logger import get_logger

_log = get_logger(__name__)


def check_pagination_and_extract_all() -> dict:
    """페이지네이션 확인 후 모든 단말기 레코드 추출"""
    page = get_page()

    # 임대관리 페이지로 이동
    search_page = "https://eum.cw.or.kr/web/man/WEBMAN380M00"
    _log.info(f"[단말기관리] {search_page} 접속")
    page.goto(search_page, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=10000)

    # 팝업 처리
    try:
        from scripts.popup_detector import handle_page_popups
        popup_result = handle_page_popups(page, timeout_s=2.0)
        _log.info(f"[팝업처리] {popup_result}")
    except Exception as e:
        _log.debug(f"팝업 처리 오류: {e}")

    # 1. 페이지 정보 확인 (총 몇 개 검색 결과인지)
    search_info = page.evaluate("""
    (() => {
        // 검색 결과 수 파악
        const pageInfo = document.querySelector('span.pagingBtnEnd')?.innerText || '';
        const tableRows = document.querySelectorAll('table tbody tr');

        // 페이지네이션 버튼 확인
        const nextBtn = document.querySelector('a[title="다음"]');
        const lastBtn = document.querySelector('a[title="끝"]');

        return {
            pageInfo: pageInfo,
            visibleRows: tableRows.length,
            hasNext: nextBtn && nextBtn.offsetParent !== null,
            hasLast: lastBtn && lastBtn.offsetParent !== null,
            paginationHtml: document.querySelector('div.paging')?.innerText || 'N/A'
        };
    })();
    """)

    _log.info(f"[페이지정보] {search_info}")

    # 2. 현재 페이지의 모든 단말기 레코드 추출
    all_devices = []
    current_page = 1

    while True:
        # 현재 페이지의 테이블 데이터 추출
        rows_data = page.evaluate("""
        (() => {
            const rows = document.querySelectorAll('table tbody tr');
            const devices = [];

            rows.forEach((row, idx) => {
                const cells = row.querySelectorAll('td');
                if (cells.length > 0) {
                    const device = {
                        no: cells[0]?.innerText?.trim() || '',
                        project: cells[1]?.innerText?.trim() || '',
                        contract: cells[2]?.innerText?.trim() || '',
                        code: cells[3]?.innerText?.trim() || '',
                        contractor: cells[4]?.innerText?.trim() || '',
                        device_count: cells[5]?.innerText?.trim() || '1',
                        card_info: cells[6]?.innerText?.trim() || '',
                        teardown_date: cells[7]?.innerText?.trim() || '',
                        completion: cells[8]?.innerText?.trim() || '',
                        location: cells[9]?.innerText?.trim() || ''
                    };

                    // 데이터 유효성 확인
                    if (device.no && device.project) {
                        devices.push(device);
                    }
                }
            });

            return devices;
        })();
        """)

        if not rows_data:
            _log.info(f"[페이지{current_page}] 데이터 없음, 추출 종료")
            break

        _log.info(f"[페이지{current_page}] {len(rows_data)}개 레코드 추출")
        all_devices.extend(rows_data)

        # 다음 페이지 확인
        has_next = page.evaluate("""
        (() => {
            const nextBtn = document.querySelector('a[title="다음"]');
            return nextBtn && nextBtn.offsetParent !== null;
        })();
        """)

        if not has_next:
            _log.info(f"다음 페이지 없음 (총 {current_page}페이지)")
            break

        # 다음 페이지로 이동
        _log.info(f"다음 페이지로 이동...")
        try:
            page.click('a[title="다음"]')
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception as e:
            _log.error(f"페이지 이동 실패: {e}")
            break

        current_page += 1

    # 3. 데이터 집계
    total_devices = 0
    active_devices = 0
    terminated_devices = 0

    for device in all_devices:
        try:
            count = int(device.get('device_count', '1'))
        except:
            count = 1

        total_devices += count

        if not device.get('teardown_date'):
            active_devices += count
        else:
            terminated_devices += count

    result = {
        "total_records": len(all_devices),
        "total_devices": total_devices,
        "active_devices": active_devices,
        "terminated_devices": terminated_devices,
        "pages": current_page,
        "devices": all_devices,
        "summary": {
            "현재_임대중": active_devices,
            "임대_종료_반납대기": terminated_devices,
            "총_단말기_수": total_devices
        }
    }

    return result


if __name__ == "__main__":
    try:
        result = check_pagination_and_extract_all()

        # 결과 출력
        print("\n" + "="*60)
        print("[전체 단말기 인벤토리]")
        print("="*60)
        print(f"총 프로젝트 레코드: {result['total_records']}건")
        print(f"총 단말기 수: {result['total_devices']}대")
        print(f"  - 현재 임대 중: {result['active_devices']}대")
        print(f"  - 임대 종료(반납대기): {result['terminated_devices']}대")
        print(f"검색 페이지: {result['pages']}페이지")
        print("="*60 + "\n")

        # JSON으로 저장
        output_file = ROOT / "data" / "total_inventory_report.json"
        output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        _log.info(f"✓ 인벤토리 보고서 저장: {output_file}")

    except Exception as e:
        _log.error(f"인벤토리 조회 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
