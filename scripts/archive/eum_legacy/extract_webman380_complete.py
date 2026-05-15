"""현장별 단말기 목록 (WEBMAN380M00) - 모든 필터 '전체' 설정 후 추출"""
from __future__ import annotations

import json
import sys
import time
import re
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.web_connector import get_page
from scripts.logger import get_logger

_log = get_logger(__name__)


def main():
    page = get_page()

    print("\n" + "="*100)
    print("🔍 WEBMAN380M00 - 현장별 단말기 목록 완전 추출")
    print("="*100 + "\n")

    # WEBMAN380M00 접속
    url = "https://eum.cw.or.kr/web/man/WEBMAN380M00"
    print(f"[접속] {url}")
    page.goto(url, timeout=30000)
    page.wait_for_load_state("load", timeout=5000)

    # 팝업 처리
    try:
        from scripts.popup_detector import handle_page_popups
        handle_page_popups(page, timeout_s=2.0)
    except:
        pass

    # 1. 모든 필터를 "전체"로 설정
    print("\n[필터 설정] 모든 필터를 '전체'로 변경 중...\n")

    filter_result = page.evaluate("""
    (() => {
        const selects = document.querySelectorAll('select');
        let changed = 0;

        selects.forEach((sel, idx) => {
            const allOption = Array.from(sel.options).find(o =>
                o.text.trim() === '전체' || o.text.trim() === '선택'
            );

            if (allOption) {
                const oldValue = sel.value;
                sel.value = allOption.value;
                sel.dispatchEvent(new Event('change', { bubbles: true }));

                console.log(`Filter ${idx}: '${allOption.text}' 선택`);
                changed++;
            }
        });

        return { filters_changed: changed, total_filters: selects.length };
    })();
    """)

    print(f"  변경된 필터: {filter_result['filters_changed']}/{filter_result['total_filters']}개")

    # 2. 표시 개수를 최대(60개)로 설정
    print("\n[표시 개수] 60개로 설정 중...\n")

    time.sleep(2)
    page.wait_for_load_state("load", timeout=5000)

    display_set = page.evaluate("""
    (() => {
        const selects = document.querySelectorAll('select');

        for (let sel of selects) {
            const opts = Array.from(sel.options).map(o => o.text);
            if (opts.some(t => t.includes('개'))) {
                const opt60 = Array.from(sel.options).find(o => o.text.includes('60'));
                if (opt60) {
                    sel.value = opt60.value;
                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
            }
        }
        return false;
    })();
    """)

    if display_set:
        print("  ✓ 60개 옵션 설정 완료")
    else:
        print("  ⚠️ 60개 옵션 설정 실패 (기본값 사용)")

    time.sleep(2)
    page.wait_for_load_state("load", timeout=5000)

    # 3. 페이지 HTML 전체 추출
    print("\n[데이터 추출] HTML 전체 파싱 중...\n")

    html_content = page.content()

    # 4. 테이블 구조 분석
    table_info = page.evaluate("""
    (() => {
        const tables = document.querySelectorAll('table');
        const info = [];

        tables.forEach((table, idx) => {
            const thead = table.querySelector('thead');
            const tbody = table.querySelector('tbody');

            const headers = thead ? Array.from(thead.querySelectorAll('th')).map(h => h.innerText?.trim() || '') : [];
            const rows = tbody ? tbody.querySelectorAll('tr').length : 0;

            info.push({
                index: idx,
                header_count: headers.length,
                headers: headers,
                row_count: rows
            });
        });

        return info;
    })();
    """)

    print("  테이블 구조:")
    for tbl in table_info:
        print(f"    테이블 #{tbl['index']}: {tbl['row_count']}행 × {tbl['header_count']}열")
        if tbl['headers']:
            print(f"      헤더: {', '.join(tbl['headers'][:8])}")

    # 5. 데이터 테이블의 모든 행 추출 (가장 많은 행을 가진 테이블)
    largest_table_idx = max(range(len(table_info)),
                           key=lambda i: table_info[i]['row_count'] if table_info[i]['header_count'] > 0 else -1)

    if largest_table_idx < 0 or table_info[largest_table_idx]['row_count'] == 0:
        print("\n  ⚠️ 데이터 없음 - 필터 조건 확인 필요")
        sys.exit(0)

    print(f"\n  → 데이터 테이블: #{largest_table_idx} ({table_info[largest_table_idx]['row_count']}행)")

    all_rows = page.evaluate(f"""
    (() => {{
        const tables = document.querySelectorAll('table');
        const table = tables[{largest_table_idx}];

        if (!table) return [];

        const tbody = table.querySelector('tbody');
        if (!tbody) return [];

        const rows = [];
        tbody.querySelectorAll('tr').forEach((row, idx) => {{
            const cells = row.querySelectorAll('td');
            const cellTexts = Array.from(cells).map(c => c.innerText?.trim() || '');
            rows.push(cellTexts);
        }});

        return rows;
    }})();
    """)

    print(f"\n  ✓ 추출된 행: {len(all_rows)}개\n")

    # 6. 데이터 정제 및 분석
    headers = table_info[largest_table_idx]['headers']

    # 첫 셀이 숫자인 행만 필터링 (실제 데이터)
    valid_rows = []
    for row in all_rows:
        if row and row[0] and (row[0][0].isdigit() or row[0].startswith('2')):
            valid_rows.append(row)

    print(f"  유효한 데이터 행: {len(valid_rows)}개")

    # 7. 결과 저장
    result = {
        'timestamp': datetime.now().isoformat(),
        'page_url': url,
        'page_name': 'WEBMAN380M00 - 현장별 단말기 목록',
        'total_rows_extracted': len(all_rows),
        'valid_data_rows': len(valid_rows),
        'table_headers': headers,
        'table_index': largest_table_idx,
        'data_rows': [
            {
                'row_index': i,
                'cells': row,
                'mapped': {
                    headers[j]: row[j] if j < len(row) else ''
                    for j in range(min(len(headers), len(row)))
                }
            }
            for i, row in enumerate(valid_rows)
        ]
    }

    # 상세 정보 출력
    print("\n" + "="*100)
    print("[추출된 현장 데이터 샘플]")
    print("="*100)

    for i, item in enumerate(result['data_rows'][:5], 1):
        row = item['cells']
        mapped = item['mapped']

        print(f"\n[현장 {i}] NO={row[0] if row else '?'}")
        if len(row) > 1:
            print(f"  공사명: {row[1]}")
        if len(row) > 2:
            print(f"  도급구분: {row[2]}")
        if len(row) > 5:
            print(f"  단말기설치수: {row[5]}")

    if len(result['data_rows']) > 5:
        print(f"\n  ... 외 {len(result['data_rows']) - 5}개 항목")

    # JSON 저장
    output_file = Path("data") / "webman380_rental_projects.json"
    output_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f"\n{'='*100}")
    print(f"✓ 현장 데이터 저장: {output_file}")
    print(f"  - 총 행: {len(all_rows)}")
    print(f"  - 유효 데이터: {len(valid_rows)}개")
    print(f"  - 컬럼: {len(headers)}개")
    print("="*100 + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log.error(f"실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
