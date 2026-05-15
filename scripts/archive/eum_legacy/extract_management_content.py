"""관리 섹션 실제 콘텐츠 추출."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

def extract_management_content():
    """관리 섹션 콘텐츠 추출."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            contexts = browser.contexts
            
            if not contexts:
                print("활성 컨텍스트 없음")
                return
            
            context = contexts[0]
            pages = context.pages
            
            # 관리 페이지 찾기
            mgmt_page = None
            for page in pages:
                if "mng" in page.url or "WEBMNG" in page.url:
                    mgmt_page = page
                    break
            
            if not mgmt_page:
                print("관리 페이지를 찾을 수 없음")
                return
            
            print(f"\n[관리 섹션 콘텐츠]")
            print(f"URL: {mgmt_page.url}")
            print(f"제목: {mgmt_page.title()}\n")
            
            content = mgmt_page.evaluate("""
            (() => {
                return {
                    headings: Array.from(document.querySelectorAll('h1, h2, h3, h4'))
                        .slice(0, 30)
                        .map(h => (h.innerText || '').trim())
                        .filter(t => t.length > 0 && t.length < 100),
                    
                    tables: Array.from(document.querySelectorAll('table'))
                        .map((t, idx) => {
                            const rows = Array.from(t.querySelectorAll('tbody tr, tr'));
                            return {
                                index: idx,
                                row_count: rows.length,
                                content: rows.slice(0, 5).map(r => 
                                    Array.from(r.querySelectorAll('td, th'))
                                        .map(c => (c.innerText || '').trim().substring(0, 30))
                                        .join(' | ')
                                ).join('\n'),
                            };
                        }),
                    
                    body_text: document.body.innerText.substring(0, 1500),
                };
            })();
            """)
            
            print("[주요 제목]")
            for heading in content['headings'][:20]:
                print(f"  • {heading}")
            
            if content['tables']:
                print("\n[테이블 데이터]")
                for table in content['tables']:
                    if table['row_count'] > 0:
                        print(f"  테이블 {table['index']} ({table['row_count']}행):")
                        if table['content']:
                            for line in table['content'].split('\n')[:3]:
                                print(f"    {line}")
            
            print("\n[페이지 전체 텍스트]")
            print("-" * 70)
            print(content['body_text'])
            print("-" * 70)
            
            browser.close()
            
    except Exception as e:
        print(f"✗ 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    extract_management_content()
