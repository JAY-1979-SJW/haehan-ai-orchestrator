"""단말기 상태 현황 완전 분석."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

def extract_complete_device_status():
    """현재 페이지의 모든 단말기 관련 데이터 추출."""
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
            
            print(f"\n[단말기 현황 전체 분석]")
            print(f"URL: {current_page.url}")
            print(f"제목: {current_page.title()}\n")
            
            # 모든 텍스트 콘텐츠 추출
            page_content = current_page.evaluate("""
            (() => {
                return {
                    // 전체 텍스트
                    full_text: document.body.innerText,
                    
                    // 모든 테이블 분석
                    tables: Array.from(document.querySelectorAll('table')).map((t, idx) => ({
                        index: idx,
                        row_count: t.querySelectorAll('tbody tr').length,
                        column_count: t.querySelectorAll('thead th').length || t.querySelectorAll('tbody tr:first-child td').length,
                        headers: Array.from(t.querySelectorAll('thead th, thead td')).map(h => h.innerText),
                        rows: Array.from(t.querySelectorAll('tbody tr')).slice(0, 5).map(r => 
                            Array.from(r.querySelectorAll('td')).map(c => c.innerText.trim())
                        ),
                    })),
                    
                    // 통계 정보 찾기
                    numbers: Array.from(document.querySelectorAll('*'))
                        .map(el => el.innerText)
                        .filter(t => /^\d+/.test(t.trim()) && t.trim().length < 50)
                        .slice(0, 30),
                };
            })();
            """)
            
            print("[페이지 주요 텍스트] (처음 1000글자)")
            print("-" * 70)
            text = page_content['full_text'][:1000]
            print(text)
            print("-" * 70)
            
            # 테이블 분석
            tables = page_content['tables']
            if tables:
                print(f"\n[테이블 분석] - {len(tables)}개 테이블\n")
                for table in tables:
                    if table['row_count'] > 0:
                        print(f"테이블 {table['index']}:")
                        print(f"  행: {table['row_count']}개")
                        print(f"  열: {table['column_count']}개")
                        print(f"  헤더: {', '.join(table['headers'][:5])}")
                        if table['rows']:
                            print(f"  샘플: {table['rows'][0][:4] if table['rows'][0] else 'N/A'}")
                        print()
            
            # 통계
            if page_content['numbers']:
                print("[페이지의 숫자 정보]")
                unique_numbers = list(set(page_content['numbers']))
                for num in unique_numbers[:20]:
                    print(f"  {num}")
            
            browser.close()
            
    except Exception as e:
        print(f"✗ 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    extract_complete_device_status()
