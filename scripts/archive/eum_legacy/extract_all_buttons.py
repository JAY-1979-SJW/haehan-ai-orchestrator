"""모든 버튼 목록 추출."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

def extract_all_buttons():
    """현재 페이지의 모든 버튼 추출."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            contexts = browser.contexts
            context = contexts[0]
            pages = context.pages
            
            # 마이페이지 찾기
            current_page = pages[-1] if pages else None
            
            if not current_page:
                print("활성 페이지 없음")
                return
            
            print(f"\n[모든 버튼 목록]")
            print(f"현재 페이지: {current_page.url}\n")
            
            buttons = current_page.evaluate("""
            (() => {
                const buttonElements = Array.from(document.querySelectorAll('button, a[class*="btn"], input[type="button"]'));
                return buttonElements
                    .map(btn => ({
                        text: (btn.innerText || btn.value || btn.title || '').trim().substring(0, 50),
                        class: btn.className,
                        type: btn.tagName,
                        visible: btn.offsetParent !== null,
                    }))
                    .filter(b => b.text.length > 0)
                    .slice(0, 100);
            })();
            """)
            
            print(f"총 {len(buttons)}개 버튼 발견\n")
            
            # 카테고리별 필터링
            categories = {
                '단말기': [],
                '고장': [],
                '신고': [],
                '임대': [],
                '관리': [],
                '조회': [],
                '기타': [],
            }
            
            for btn in buttons:
                text = btn['text'].lower()
                categorized = False
                
                for cat_key in categories.keys():
                    if cat_key.lower() in text or text in cat_key.lower():
                        categories[cat_key].append(btn)
                        categorized = True
                        break
                
                if not categorized:
                    categories['기타'].append(btn)
            
            # 출력
            for category, items in categories.items():
                if items:
                    print(f"\n[{category}] - {len(items)}개")
                    for i, btn in enumerate(items[:10], 1):
                        print(f"  {i}. {btn['text']} ({btn['type']})")
            
            browser.close()
            
    except Exception as e:
        print(f"✗ 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    extract_all_buttons()
