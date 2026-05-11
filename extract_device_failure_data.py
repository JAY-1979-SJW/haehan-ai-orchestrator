"""단말기 고장 신고 데이터 상세 추출."""
import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

def extract_device_failure_data():
    """고장 신고 데이터 추출."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            contexts = browser.contexts
            context = contexts[0]
            pages = context.pages
            
            current_page = pages[-1] if pages else None
            
            if not current_page:
                print("활성 페이지 없음")
                return
            
            print(f"\n[단말기 고장 신고 데이터 분석]\n")
            
            # 테이블 데이터 추출
            data = current_page.evaluate("""
            (() => {
                const tables = Array.from(document.querySelectorAll('table'));
                const allRows = [];
                
                tables.forEach((table, tidx) => {
                    // 헤더 추출
                    const headers = Array.from(table.querySelectorAll('thead th, thead td'))
                        .map(h => (h.innerText || '').trim())
                        .filter(h => h.length > 0);
                    
                    // 행 데이터 추출
                    const rows = Array.from(table.querySelectorAll('tbody tr'));
                    
                    if (rows.length > 0) {
                        const tableRows = rows.map(tr => {
                            const cells = Array.from(tr.querySelectorAll('td'));
                            return {
                                cells: cells.map(c => (c.innerText || '').trim()),
                                html: tr.innerHTML.substring(0, 200),
                            };
                        });
                        
                        allRows.push({
                            table_index: tidx,
                            headers: headers,
                            rows: tableRows,
                        });
                    }
                });
                
                return {
                    total_tables: tables.length,
                    tables_with_data: allRows,
                    page_url: window.location.href,
                    page_title: document.title,
                };
            })();
            """)
            
            print(f"페이지: {data['page_title']}")
            print(f"URL: {data['page_url']}\n")
            
            if data['tables_with_data']:
                for table in data['tables_with_data']:
                    print(f"[테이블 {table['table_index']}] - {len(table['rows'])}행")
                    
                    if table['headers']:
                        print(f"열: {', '.join(table['headers'][:8])}\n")
                    
                    # 데이터 출력
                    print("데이터 샘플:")
                    for i, row_data in enumerate(table['rows'][:10], 1):
                        cells = row_data['cells']
                        if len(cells) > 2:
                            print(f"  행 {i}: {' | '.join(cells[:6])}")
                        if len(table['rows']) > 10:
                            print(f"\n  ... 외 {len(table['rows']) - 10}행")
                            break
                    
                    print(f"\n총 행 수: {len(table['rows'])}")
                    
                    # 데이터 통계
                    if table['rows']:
                        print("\n[데이터 통계]")
                        rental_status = {}
                        for row in table['rows']:
                            if len(row['cells']) > 5:
                                status = row['cells'][5]  # 상태 열
                                rental_status[status] = rental_status.get(status, 0) + 1
                        
                        print("임대 상태별 현황:")
                        for status, count in sorted(rental_status.items(), key=lambda x: x[1], reverse=True):
                            print(f"  - {status}: {count}건")
            else:
                print("❌ 테이블 데이터가 없습니다")
                print("\n페이지 텍스트 (처음 500글자):")
                print(current_page.evaluate("() => document.body.innerText.substring(0, 500)"))
            
            browser.close()
            
    except Exception as e:
        print(f"✗ 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    extract_device_failure_data()
