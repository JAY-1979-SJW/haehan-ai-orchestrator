"""EUM 사이트 상세 재탐색
- 페이지 완전 분석
- 임차인 정보 포함 모든 데이터 추출
- 공사 현황 확인
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


def explore_webman390_detailed(page) -> dict:
    """WEBMAN390M00 상세 탐색"""
    print("\n" + "="*100)
    print("[1] WEBMAN390M00 - 단말기설치현황 완전 분석")
    print("="*100)

    url = "https://eum.cw.or.kr/web/man/WEBMAN390M00"
    page.goto(url, timeout=30000)
    page.wait_for_load_state("load", timeout=5000)

    try:
        from scripts.popup_detector import handle_page_popups
        handle_page_popups(page, timeout_s=2.0)
    except:
        pass

    # 1. 페이지 전체 정보
    page_info = page.evaluate("""
    (() => {
        return {
            title: document.title,
            tables: document.querySelectorAll('table').length,
            all_text_length: document.body.innerText.length,
            has_form: !!document.querySelector('form'),
            url: window.location.href
        };
    })();
    """)

    print(f"\n[페이지 정보]")
    print(f"  제목: {page_info['title']}")
    print(f"  테이블 수: {page_info['tables']}개")
    print(f"  텍스트 길이: {page_info['all_text_length']}자")

    # 2. 모든 테이블의 상세 분석
    print(f"\n[테이블 상세 분석]")

    table_details = page.evaluate("""
    (() => {
        const tables = document.querySelectorAll('table');
        const details = [];

        tables.forEach((table, idx) => {
            const thead = table.querySelector('thead');
            const tbody = table.querySelector('tbody');

            const headers = thead ? Array.from(thead.querySelectorAll('th')).map(h => h.innerText?.trim() || '') : [];
            const rows = tbody ? tbody.querySelectorAll('tr') : [];

            const firstRow = rows.length > 0 ?
                Array.from(rows[0].querySelectorAll('td')).map(c => c.innerText?.trim().substring(0, 50) || '') :
                [];

            details.push({
                table_index: idx,
                header_count: headers.length,
                headers: headers.slice(0, 15),
                row_count: rows.length,
                first_row_sample: firstRow.slice(0, 5),
                tbody_exists: !!tbody,
                thead_exists: !!thead
            });
        });

        return details;
    })();
    """)

    for tbl in table_details:
        print(f"\n  테이블 #{tbl['table_index']}: {tbl['row_count']}행 × {tbl['header_count']}열")
        if tbl['headers']:
            print(f"    헤더: {', '.join(tbl['headers'][:6])}")
        if tbl['first_row_sample']:
            print(f"    샘플: {' | '.join(tbl['first_row_sample'])}")

    # 3. 가장 큰 테이블의 전체 데이터 추출 (정확히)
    largest_table_idx = max(range(len(table_details)),
                           key=lambda i: table_details[i]['row_count'] if table_details[i]['thead_exists'] else -1)

    print(f"\n[데이터 테이블 추출] 테이블 #{largest_table_idx}")

    table_full_data = page.evaluate(f"""
    (() => {{
        const tables = document.querySelectorAll('table');
        const table = tables[{largest_table_idx}];

        if (!table) return {{ rows: [] }};

        const thead = table.querySelector('thead');
        const tbody = table.querySelector('tbody');

        // 헤더 추출
        const headers = thead ?
            Array.from(thead.querySelectorAll('th')).map(h => h.innerText?.trim() || '') :
            [];

        // 모든 데이터 행 추출
        const rows = [];
        if (tbody) {{
            tbody.querySelectorAll('tr').forEach((row, idx) => {{
                const cells = row.querySelectorAll('td');
                const cellTexts = Array.from(cells).map(c => c.innerText?.trim() || '');

                rows.push({{
                    row_index: idx,
                    cells: cellTexts
                }});
            }});
        }}

        return {{
            table_index: {largest_table_idx},
            headers: headers,
            rows: rows
        }};
    }})();
    """)

    print(f"\n  헤더 ({len(table_full_data['headers'])}개):")
    for i, h in enumerate(table_full_data['headers'][:15], 1):
        print(f"    [{i:2}] {h[:50]}")

    if len(table_full_data['headers']) > 15:
        print(f"    ... 외 {len(table_full_data['headers'])-15}개")

    print(f"\n  데이터 ({len(table_full_data['rows'])}행):")
    for i, row in enumerate(table_full_data['rows'][:5], 1):
        print(f"    [행 {i}] {len(row['cells'])}개 셀")
        for j, cell in enumerate(row['cells'][:5], 1):
            print(f"      [{j}] {cell[:60]}")

    if len(table_full_data['rows']) > 5:
        print(f"    ... 외 {len(table_full_data['rows'])-5}행")

    return {
        'page_info': page_info,
        'table_details': table_details,
        'table_full_data': table_full_data
    }


def explore_webman380_detailed(page) -> dict:
    """WEBMAN380M00 상세 탐색"""
    print("\n" + "="*100)
    print("[2] WEBMAN380M00 - 현장별 단말기 목록 완전 분석")
    print("="*100)

    url = "https://eum.cw.or.kr/web/man/WEBMAN380M00"
    page.goto(url, timeout=30000)
    page.wait_for_load_state("load", timeout=5000)

    try:
        from scripts.popup_detector import handle_page_popups
        handle_page_popups(page, timeout_s=2.0)
    except:
        pass

    # 필터와 버튼 정보
    filter_info = page.evaluate("""
    (() => {
        const filters = [];
        document.querySelectorAll('select').forEach((sel, idx) => {
            const opts = Array.from(sel.options).map(o => ({
                value: o.value,
                text: o.text
            }));

            filters.push({
                index: idx,
                name: sel.name || sel.id || `filter_${idx}`,
                option_count: opts.length,
                options: opts
            });
        });

        return { filters: filters };
    })();
    """)

    print(f"\n[필터 정보] {len(filter_info['filters'])}개")
    for filt in filter_info['filters']:
        print(f"  [{filt['index']}] {filt['name']}")
        print(f"      옵션: {filt['option_count']}개")
        for opt in filt['options'][:5]:
            print(f"        - {opt['text']}")

    # 테이블 정보
    table_info = page.evaluate("""
    (() => {
        const tables = document.querySelectorAll('table');
        const details = [];

        tables.forEach((table, idx) => {
            const thead = table.querySelector('thead');
            const tbody = table.querySelector('tbody');

            const headers = thead ? Array.from(thead.querySelectorAll('th')).map(h => h.innerText?.trim() || '') : [];
            const rows = tbody ? tbody.querySelectorAll('tr').length : 0;

            details.push({
                index: idx,
                headers: headers,
                header_count: headers.length,
                row_count: rows
            });
        });

        return details;
    })();
    """)

    print(f"\n[테이블 현황]")
    for tbl in table_info:
        print(f"  테이블 #{tbl['index']}: {tbl['row_count']}행 × {tbl['header_count']}열")
        if tbl['headers']:
            print(f"    헤더: {', '.join(tbl['headers'][:8])}")

    return {
        'filters': filter_info,
        'tables': table_info
    }


def main():
    page = get_page()

    print("\n" + "="*100)
    print("🔍 EUM 사이트 재탐색 - 임대 목록 정확 파악")
    print("="*100)
    print(f"시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 1. WEBMAN390M00 상세 탐색
    result390 = explore_webman390_detailed(page)
    time.sleep(1)

    # 2. WEBMAN380M00 상세 탐색
    result380 = explore_webman380_detailed(page)

    # 결과 저장
    results = {
        'timestamp': datetime.now().isoformat(),
        'webman390': result390,
        'webman380': result380
    }

    output_file = Path("data") / "eum_detailed_exploration.json"
    output_file.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    print(f"\n{'='*100}")
    print(f"✓ 탐색 결과 저장: {output_file}")
    print(f"완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*100 + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log.error(f"탐색 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
