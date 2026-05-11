"""단말기 고장 신고 내역 확인 및 상세 데이터 추출."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

def check_failure_reports():
    """고장 신고 내역 확인."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            contexts = browser.contexts
            context = contexts[0]
            pages = context.pages
            
            # 마이페이지 찾기
            mypage = None
            for page in pages:
                if "WEBMYP" in page.url or "myp" in page.url:
                    mypage = page
                    break
            
            if not mypage:
                print("마이페이지를 찾을 수 없음")
                return
            
            print(f"\n[단말기 고장 신고 내역 분석]")
            print(f"URL: {mypage.url}\n")
            
            # 테이블 데이터 추출
            table_data = mypage.evaluate("""
            (() => {
                // 고장 신고내역 테이블 찾기
                const tables = Array.from(document.querySelectorAll('table'));
                const results = [];
                
                tables.forEach((table, idx) => {
                    const headers = Array.from(table.querySelectorAll('thead th, thead td'))
                        .map(h => (h.innerText || '').trim());
                    
                    const rows = Array.from(table.querySelectorAll('tbody tr'));
                    
                    results.push({
                        table_index: idx,
                        headers: headers,
                        row_count: rows.length,
                        rows: rows.slice(0, 10).map(tr => 
                            Array.from(tr.querySelectorAll('td'))
                                .map(td => (td.innerText || '').trim())
                        ),
                        has_content: rows.length > 0,
                    });
                });
                
                return {
                    total_tables: tables.length,
                    tables: results,
                    page_text: document.body.innerText.substring(0, 500),
                };
            })();
            """)
            
            print(f"테이블 총 개수: {table_data['total_tables']}개\n")
            
            # 각 테이블 분석
            for table_info in table_data['tables']:
                if table_info['row_count'] > 0:
                    print(f"[테이블 {table_info['table_index']}] - {table_info['row_count']}행")
                    print(f"열: {', '.join(table_info['headers'][:8])}")
                    
                    if table_info['rows']:
                        print(f"\n샘플 데이터 (처음 3행):")
                        for i, row in enumerate(table_info['rows'][:3], 1):
                            print(f"  행 {i}: {' | '.join(row[:6])}")
                    print()
            
            # 페이지 전체 텍스트에서 숫자 찾기
            page_text = table_data['page_text']
            print("[페이지 주요 내용]")
            lines = page_text.split('\n')
            for line in lines:
                line = line.strip()
                if ('고장' in line or '신고' in line or '임대' in line or '상태' in line) and len(line) > 0:
                    print(f"  {line}")
            
            # 필터 요소 확인
            filters = mypage.evaluate("""
            (() => {
                const filterElements = Array.from(document.querySelectorAll('select, input[type="text"], input[type="date"], button'))
                    .filter(el => {
                        const text = el.innerText || el.value || el.placeholder || '';
                        return text && text.length > 0;
                    })
                    .map(el => ({
                        type: el.tagName,
                        tag: el.tagName,
                        text: (el.innerText || el.value || el.placeholder || '').trim().substring(0, 30),
                        id: el.id,
                        name: el.name,
                    }))
                    .slice(0, 20);
                
                return filterElements;
            })();
            """)
            
            print("\n[페이지 필터 요소]")
            for f in filters[:15]:
                print(f"  {f['tag']}: {f['text']}")
            
            browser.close()
            
    except Exception as e:
        print(f"✗ 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_failure_reports()
