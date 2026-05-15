"""실제 데이터 테이블 찾기"""
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
                    console.log('Status filter changed to all');
                }
            }
        }
    })();
    """)

    time.sleep(3)
    page.wait_for_load_state("load", timeout=5000)

    # 모든 테이블 찾기
    all_tables = page.evaluate("""
    (() => {
        const tables = document.querySelectorAll('table');
        const tableInfo = [];

        tables.forEach((table, idx) => {
            const thead = table.querySelector('thead');
            const tbody = table.querySelector('tbody');

            const headerCount = thead?.querySelectorAll('th').length || 0;
            const rowCount = tbody?.querySelectorAll('tr').length || 0;
            const headers = thead ? Array.from(thead.querySelectorAll('th')).map(h => h.innerText?.trim().substring(0, 20) || '') : [];

            // 첫 행의 셀 텍스트 샘플
            const firstRow = tbody?.querySelector('tr');
            const firstRowSample = firstRow ?
                Array.from(firstRow.querySelectorAll('td')).map(c => c.innerText?.trim().substring(0, 30) || '') : [];

            tableInfo.push({
                tableIndex: idx,
                headerCount: headerCount,
                rowCount: rowCount,
                headers: headers,
                firstRowSample: firstRowSample,
                bodySelector: `table:nth-of-type(${idx+1}) tbody`
            });
        });

        return tableInfo;
    })();
    """)

    print("\n" + "="*80)
    print("[페이지의 모든 테이블 분석]")
    print("="*80)

    for table in all_tables:
        print(f"\n[테이블 #{table['tableIndex']}]")
        print(f"  헤더: {table['headerCount']}개")
        print(f"  행: {table['rowCount']}개")
        if table['headers']:
            print(f"  헤더 텍스트: {', '.join(table['headers'][:5])}")
        if table['firstRowSample']:
            print(f"  첫 행 샘플: {', '.join(table['firstRowSample'][:3])}")

    # 실제 데이터가 있는 테이블 찾기 (행이 많은 테이블)
    data_tables = [t for t in all_tables if t['rowCount'] > 5]

    if data_tables:
        print(f"\n{'='*80}")
        print(f"[데이터 테이블 후보] ({len(data_tables)}개)")
        print(f"{'='*80}")

        for table in data_tables:
            print(f"\n테이블 #{table['tableIndex']}: {table['rowCount']}행")

            # 이 테이블의 데이터 추출 시도
            table_index = table['tableIndex']
            table_data = page.evaluate(f"""
            (() => {{
                const tables = document.querySelectorAll('table');
                const targetTable = tables[{table_index}];
                const tbody = targetTable?.querySelector('tbody');
                const rows = tbody?.querySelectorAll('tr') || [];

                const devices = [];
                let validDataCount = 0;

                rows.forEach((row, idx) => {{
                    const cells = row.querySelectorAll('td');
                    const cellTexts = Array.from(cells).map(c => c.innerText?.trim() || '');

                    // 숫자로 시작하고 프로젝트명이 있는 행
                    if (cellTexts.length > 1 && /^\\d/.test(cellTexts[0]) && cellTexts[1]?.length > 3) {{
                        devices.push({{
                            no: cellTexts[0],
                            cells: cellTexts
                        }});
                        validDataCount++;

                        if (devices.length <= 5) {{
                            console.log(`Row ${{idx}}: ${{cellTexts.slice(0, 3).join(' | ')}}`);
                        }}
                    }}
                }});

                return {{
                    rowCount: rows.length,
                    validDataCount: validDataCount,
                    devices: devices.slice(0, 10)
                }};
            }})();
            """)

            print(f"  유효한 데이터: {table_data['validDataCount']}건")
            if table_data['devices']:
                for device in table_data['devices'][:3]:
                    print(f"    • NO:{device['no']} | {device['cells'][1][:40]}...")

    # 페이지의 핵심 내용 확인
    page_content = page.evaluate("""
    (() => {
        const allText = document.body.innerText;

        // "장애", "임대", "건수" 등의 키워드와 숫자 찾기
        const lines = allText.split('\\n');
        const significantLines = lines.filter(l =>
            (l.includes('장애') || l.includes('임대') || l.includes('건수') || l.includes('현황')) &&
            l.length < 100
        ).slice(0, 10);

        return {
            significantLines: significantLines,
            pageTitle: document.title
        };
    })();
    """)

    print(f"\n{'='*80}")
    print("[페이지 주요 정보]")
    print(f"{'='*80}")
    print(f"\n제목: {page_content['pageTitle']}")
    if page_content['significantLines']:
        print(f"\n주요 텍스트:")
        for line in page_content['significantLines']:
            print(f"  • {line.strip()}")

    # 결과 저장
    output = {
        'all_tables': all_tables,
        'page_content': page_content
    }

    output_file = Path("data") / "table_discovery.json"
    output_file.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n✓ 분석 결과 저장: {output_file}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _log.error(f"테이블 찾기 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
