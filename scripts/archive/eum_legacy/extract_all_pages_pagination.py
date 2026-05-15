"""페이지네이션을 처리해서 모든 데이터 추출"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.web_connector import get_page
from scripts.logger import get_logger

_log = get_logger(__name__)


def main():
    page = get_page()

    url = "https://eum.cw.or.kr/web/man/WEBMAN390M00"
    _log.info(f"[접속] {url}")
    page.goto(url, timeout=30000)
    page.wait_for_load_state("load", timeout=5000)

    try:
        from scripts.popup_detector import handle_page_popups
        handle_page_popups(page, timeout_s=2.0)
    except:
        pass

    print("\n" + "="*80)
    print("[WEBMAN390M00 - 모든 페이지 수집 (페이지네이션)]")
    print("="*80)

    all_devices = []
    page_num = 0
    max_pages = 20

    while page_num < max_pages:
        page_num += 1

        # 현재 페이지에서 데이터 추출
        page_data = page.evaluate("""
        (() => {
            const tables = document.querySelectorAll('table');

            // 가장 많은 컬럼을 가진 테이블 찾기
            let targetTable = null;
            let maxCols = 0;
            for (let table of tables) {
                const thead = table.querySelector('thead');
                if (thead) {
                    const cols = thead.querySelectorAll('th').length;
                    if (cols > maxCols) {
                        maxCols = cols;
                        targetTable = table;
                    }
                }
            }

            if (!targetTable) return { devices: [], columnCount: 0 };

            const tbody = targetTable.querySelector('tbody');
            if (!tbody) return { devices: [], columnCount: maxCols };

            const rows = tbody.querySelectorAll('tr');
            const devices = [];

            rows.forEach((row) => {
                const cells = row.querySelectorAll('td');
                if (cells.length > 0) {
                    const cellTexts = Array.from(cells).map(c => c.innerText?.trim() || '');

                    // 첫 셀에 데이터가 있으면 수집
                    if (cellTexts[0]?.length > 0) {
                        devices.push({
                            cells: cellTexts.slice(0, 10)  // 처음 10개 열만
                        });
                    }
                }
            });

            return {
                devices: devices,
                columnCount: maxCols,
                rowCount: rows.length
            };
        })();
        """)

        devices_on_page = len(page_data['devices'])

        if devices_on_page == 0:
            _log.info(f"[페이지 {page_num}] 데이터 없음")
            break

        all_devices.extend(page_data['devices'])
        _log.info(f"[페이지 {page_num}] {devices_on_page}개 디바이스, 누계: {len(all_devices)}개")

        print(f"페이지 {page_num}: {devices_on_page}개 항목")

        # 다음 페이지 존재 확인
        pagination_info = page.evaluate("""
        (() => {
            const nextBtn = document.querySelector('a[title="다음"]');
            const pageInfo = document.querySelector('.paging')?.innerText || '';

            return {
                hasNext: nextBtn && nextBtn.offsetParent !== null,
                pageInfo: pageInfo,
                nextBtnText: nextBtn?.innerText || ''
            };
        })();
        """)

        if not pagination_info['hasNext']:
            _log.info(f"다음 페이지 없음 (총 {page_num}페이지)")
            print(f"  └─ 최종 페이지")
            break

        # 다음 페이지로 이동
        try:
            page.click('a[title="다음"]')
            time.sleep(2)
            page.wait_for_load_state("load", timeout=5000)
            print(f"  └─ 다음 페이지로 이동")
        except Exception as e:
            _log.error(f"페이지 이동 실패: {e}")
            break

    # 결과 정리
    print(f"\n{'='*80}")
    print(f"[수집 완료]")
    print(f"{'='*80}\n")

    print(f"✓ 총 페이지: {page_num}개")
    print(f"✓ 수집된 항목: {len(all_devices)}개\n")

    if len(all_devices) >= 40:
        print(f"✓ 40대 이상 확인됨!")
    else:
        print(f"⚠️  {len(all_devices)}대만 수집 (부족: {40 - len(all_devices)}대)")

    # 상세 출력
    print(f"\n[상위 10개 항목]")
    for i, device in enumerate(all_devices[:10], 1):
        cells = device['cells']
        sample = ' | '.join(cells[:3])
        print(f"  {i:2}. {sample}")

    # JSON 저장
    result = {
        'total_items': len(all_devices),
        'pages_scanned': page_num,
        'devices': all_devices
    }

    output_file = Path("data") / "complete_pagination_extract.json"
    output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    _log.info(f"✓ 전체 데이터 저장: {output_file}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log.error(f"추출 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
