"""WEBMAN390M00 - 단말기설치현황에서 모든 데이터 추출
61개 행 = 40대 단말기 + 부가정보
"""
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
    print("[WEBMAN390M00 - 단말기설치현황]")
    print("="*80)

    # 페이지 구조 분석
    structure = page.evaluate("""
    (() => {
        const tables = document.querySelectorAll('table');

        // 각 테이블의 정보
        const tableInfos = Array.from(tables).map((table, idx) => {
            const thead = table.querySelector('thead');
            const tbody = table.querySelector('tbody');

            const headers = thead ?
                Array.from(thead.querySelectorAll('th')).map(h => h.innerText?.trim() || '') :
                [];

            const rows = tbody ?
                Array.from(tbody.querySelectorAll('tr')).length :
                0;

            return {
                index: idx,
                headerCount: headers.length,
                rowCount: rows,
                headers: headers.slice(0, 10)
            };
        });

        return {
            tableCount: tables.length,
            tables: tableInfos
        };
    })();
    """)

    print(f"\n테이블 {structure['tableCount']}개 발견:\n")
    for table in structure['tables']:
        print(f"  테이블 #{table['index']}: {table['rowCount']}행, {table['headerCount']}열")
        print(f"    헤더: {', '.join(table['headers'][:5])}")

    # 가장 많은 열을 가진 테이블 찾기 (실제 데이터 테이블)
    largest_col_idx = max(range(len(structure['tables'])),
                         key=lambda i: structure['tables'][i]['headerCount'])

    print(f"\n[데이터 추출] 테이블 #{largest_col_idx} ({structure['tables'][largest_col_idx]['rowCount']}행, {structure['tables'][largest_col_idx]['headerCount']}열)")

    # 테이블 데이터 상세 추출
    table_data = page.evaluate(f"""
    (() => {{
        const tables = document.querySelectorAll('table');
        const targetTable = tables[{largest_col_idx}];
        const tbody = targetTable?.querySelector('tbody');
        const rows = tbody?.querySelectorAll('tr') || [];

        const devices = [];
        const skipped = [];

        rows.forEach((row, idx) => {{
            const cells = row.querySelectorAll('td');
            if (cells.length === 0) return;

            const cellTexts = Array.from(cells).map(c => c.innerText?.trim() || '');

            // 데이터 행 필터링: 첫 셀이 번호/텍스트
            if (cellTexts[0]?.length > 0 && cellTexts[1]?.length > 0) {{
                devices.push({{
                    row_index: idx,
                    cells: cellTexts,
                    cell_count: cellTexts.length
                }});
            }} else {{
                skipped.push({{
                    row_index: idx,
                    first_cell: cellTexts[0]
                }});
            }}
        }});

        return {{
            total_rows: rows.length,
            valid_devices: devices.length,
            skipped: skipped.length,
            devices: devices,
            column_count: devices.length > 0 ? devices[0].cell_count : 0
        }};
    }})();
    """)

    print(f"\n✓ 유효한 데이터: {table_data['valid_devices']}행")
    print(f"  열: {table_data['column_count']}개")

    # 상위 데이터 샘플 출력
    print(f"\n[데이터 샘플] (상위 10개)")
    print("─"*80)

    for i, device in enumerate(table_data['devices'][:10], 1):
        cells = device['cells']
        # 첫 5개 열만 출력
        sample = ' | '.join(cells[:5])
        print(f"{i:2}. {sample}")

    if len(table_data['devices']) > 10:
        print(f"... 외 {len(table_data['devices']) - 10}개")

    # 모든 데이터 JSON으로 저장
    output_file = Path("data") / "installation_status_complete.json"
    output_file.write_text(json.dumps(table_data, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f"\n{'='*80}")
    print(f"✓ 완전한 데이터 저장: {output_file}")
    print(f"{'='*80}\n")

    # 간단한 분석
    print("[분석 정보]")
    print(f"  • 총 행 수: {table_data['total_rows']}")
    print(f"  • 데이터 행: {table_data['valid_devices']}")
    print(f"  • 컬럼 수: {table_data['column_count']}")

    if table_data['valid_devices'] >= 40:
        print(f"\n✓ 40대 이상의 데이터 확인됨!")
    else:
        print(f"\n⚠️  {table_data['valid_devices']}대 < 40대 (추가 페이지 확인 필요)")

    # 페이지네이션 확인
    has_next = page.evaluate("""
    (() => {
        const nextBtn = document.querySelector('a[title="다음"]');
        return nextBtn && nextBtn.offsetParent !== null;
    })();
    """)

    if has_next:
        print(f"\n📄 다음 페이지 있음 (페이지네이션 필요)")
    else:
        print(f"\n✓ 모든 데이터가 현재 페이지에 있음")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log.error(f"추출 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
