"""테이블 구조 디버깅"""
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

    url = "https://eum.cw.or.kr/web/man/WEBMAN380M00"
    page.goto(url, timeout=30000)
    page.wait_for_load_state("load", timeout=5000)

    try:
        from scripts.popup_detector import handle_page_popups
        handle_page_popups(page, timeout_s=2.0)
    except:
        pass

    # 상태 필터를 "전체"로 변경
    page.evaluate("""
    (() => {
        const selects = document.querySelectorAll('select');
        for (let sel of selects) {
            const opts = Array.from(sel.options).map(o => o.text);
            if (opts.some(t => t.includes('진행')) && opts.some(t => t.includes('준공'))) {
                const allOpt = Array.from(sel.options).find(o => o.text.trim() === '전체');
                if (allOpt) {
                    sel.value = allOpt.value;
                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
        }
    })();
    """)

    time.sleep(2)
    page.wait_for_load_state("load", timeout=5000)

    # 테이블 상세 분석
    table_debug = page.evaluate("""
    (() => {
        const rows = document.querySelectorAll('table tbody tr');
        console.log('Total rows found:', rows.length);

        const debug = {
            totalRows: rows.length,
            firstRowCells: [],
            allRows: []
        };

        rows.forEach((row, rowIdx) => {
            const cells = row.querySelectorAll('td');
            const rowData = Array.from(cells).map((c, idx) => ({
                index: idx,
                text: c.innerText?.trim() || '',
                html: c.innerHTML?.substring(0, 50) || ''
            }));

            if (rowIdx === 0) {
                debug.firstRowCells = rowData;
            }

            // 처음 5개 행만 상세 저장
            if (rowIdx < 5) {
                debug.allRows.push({
                    rowIndex: rowIdx,
                    cellCount: cells.length,
                    cells: rowData
                });
            }
        });

        return debug;
    })();
    """)

    print("\n" + "="*80)
    print("[테이블 구조 분석]")
    print("="*80)

    print(f"\n총 행 수: {table_debug['totalRows']}")

    if table_debug['firstRowCells']:
        print(f"\n[첫 번째 행의 셀 정보] ({len(table_debug['firstRowCells'])}개 열)")
        for cell in table_debug['firstRowCells']:
            print(f"  [{cell['index']}] {cell['text'][:50]}")

    print(f"\n[첫 5개 행 상세 분석]")
    for row in table_debug['allRows']:
        print(f"\n  행 #{row['rowIndex']} ({row['cellCount']}개 셀)")
        for cell in row['cells'][:8]:  # 처음 8개만
            print(f"    [{cell['index']}] {cell['text'][:60]}")

    # 더 안전한 방식으로 데이터 추출 시도
    print(f"\n" + "="*80)
    print("[안전한 데이터 추출 시도]")
    print("="*80)

    safe_extract = page.evaluate("""
    (() => {
        const rows = document.querySelectorAll('table tbody tr');
        const devices = [];

        rows.forEach((row, idx) => {
            const cells = row.querySelectorAll('td');
            const cellTexts = Array.from(cells).map(c => c.innerText?.trim() || '');

            // 각 행을 문자열로 표현
            const rowStr = cellTexts.join(' | ');

            // 숫자로 시작하는 행만 수집 (NO 필드)
            if (cellTexts.length > 0 && /^\\d/.test(cellTexts[0])) {
                devices.push({
                    no: cellTexts[0],
                    row_text: rowStr.substring(0, 100),
                    cell_count: cellTexts.length,
                    cells: cellTexts
                });
            }
        });

        return {
            extracted_devices: devices.length,
            devices: devices.slice(0, 10)
        };
    })();
    """)

    print(f"\n추출된 항목: {safe_extract['extracted_devices']}건\n")

    for device in safe_extract['devices']:
        print(f"NO: {device['no']}")
        print(f"  {device['row_text']}")
        print()

    # JSON 저장
    output = {
        'table_structure': table_debug,
        'extracted': safe_extract
    }

    output_file = Path("data") / "table_debug.json"
    output_file.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"✓ 디버그 정보 저장: {output_file}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log.error(f"디버깅 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
