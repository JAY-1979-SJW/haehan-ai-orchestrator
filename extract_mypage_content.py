"""마이페이지 실제 콘텐츠 추출."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

def extract_mypage_content():
    """현재 열려있는 페이지에서 마이페이지 콘텐츠 추출."""
    try:
        # CDP 브라우저에 연결
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            contexts = browser.contexts
            
            if not contexts:
                print("활성 컨텍스트 없음")
                return
            
            context = contexts[0]
            pages = context.pages
            
            if not pages:
                print("활성 페이지 없음")
                return
            
            # 마이페이지 찾기
            mypage = None
            for page in pages:
                if "myp" in page.url or "WEBMYP" in page.url:
                    mypage = page
                    break
            
            if not mypage:
                print("마이페이지를 찾을 수 없음")
                return
            
            print(f"\n[마이페이지 콘텐츠 추출]")
            print(f"URL: {mypage.url}")
            print(f"제목: {mypage.title()}\n")
            
            # 페이지 콘텐츠 추출
            content = mypage.evaluate("""
            (() => {
                return {
                    // 주요 제목
                    headings: Array.from(document.querySelectorAll('h1, h2, h3, h4'))
                        .slice(0, 20)
                        .map(h => ({
                            level: h.tagName,
                            text: (h.innerText || '').trim().substring(0, 100),
                        })),
                    
                    // 주요 텍스트 섹션
                    sections: Array.from(document.querySelectorAll('section, article, [role="main"], .container, .content, main'))
                        .slice(0, 10)
                        .map(s => ({
                            tag: s.tagName,
                            class: s.className,
                            text: (s.innerText || '').substring(0, 200).trim(),
                        })),
                    
                    // 모든 보이는 텍스트 (첫 500글자)
                    body_text: document.body.innerText.substring(0, 1000),
                    
                    // 테이블 데이터
                    tables: Array.from(document.querySelectorAll('table'))
                        .map((t, idx) => ({
                            index: idx,
                            headers: Array.from(t.querySelectorAll('th, td'))
                                .slice(0, 10)
                                .map(c => (c.innerText || '').trim().substring(0, 50)),
                        })),
                };
            })();
            """)
            
            # 결과 출력
            print("[페이지 제목들]")
            for heading in content['headings']:
                print(f"  {heading['level']}: {heading['text']}")
            
            print("\n[주요 섹션]")
            for i, section in enumerate(content['sections'], 1):
                text = section['text'][:100] if section['text'] else "(empty)"
                print(f"  {i}. {section['tag']} ({section['class']})")
                print(f"     {text}")
            
            print("\n[페이지 전체 텍스트 (처음 500글자)]")
            print("-" * 60)
            print(content['body_text'])
            print("-" * 60)
            
            print("\n[테이블]")
            for table in content['tables']:
                print(f"  테이블 {table['index']}: {', '.join(table['headers'][:5])}")
            
            browser.close()
            
    except Exception as e:
        print(f"✗ 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    extract_mypage_content()
