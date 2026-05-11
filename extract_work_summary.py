"""업무 현황 요약 추출."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

def extract_work_summary():
    """현재 페이지의 업무 현황 추출."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            contexts = browser.contexts
            context = contexts[0]
            pages = context.pages
            
            print("\n[시스템 업무 현황 분석]\n")
            
            # 각 페이지에서 텍스트 추출
            for page in pages:
                url = page.url
                if any(x in url for x in ["myp", "mng", "eum"]):
                    try:
                        text = page.evaluate("() => document.body.innerText")
                        
                        # 주요 정보 추출
                        print(f"[{page.title()}]")
                        print(f"URL: {url}\n")
                        
                        # 숫자 포함 행 찾기
                        lines = text.split('\n')
                        for line in lines:
                            line = line.strip()
                            # 통계 정보, 미처리, 대기, 신청 등 포함
                            if any(kw in line for kw in ['미처리', '대기', '신청', '진행', '완료', '건', '명', '개', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9']) and len(line) > 3 and len(line) < 80:
                                print(f"  {line}")
                        
                        print()
                    except Exception as e:
                        pass
            
            browser.close()
            
    except Exception as e:
        print(f"✗ 오류: {e}")

if __name__ == "__main__":
    extract_work_summary()
