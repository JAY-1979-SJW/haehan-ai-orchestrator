"""eum.cw.or.kr 전체 사이트 자동 탐색 및 완전한 사이트맵 생성."""
import json
import time
from pathlib import Path
from datetime import datetime

SITEMAP_DIR = Path("data/sitemap")
SITEMAP_DIR.mkdir(exist_ok=True)

def explore_site():
    """사이트 전체 탐색."""
    print("\n[건설근로자공제회 사이트 전체 탐색 시작]")
    
    collected_pages = []
    
    # 탐색할 버튼/메뉴 목록 (텍스트로 정의)
    menu_buttons = [
        ("대표홈페이지", "홈", "https://eum.cw.or.kr/main"),
        ("마이페이지", "개인 대시보드", "https://eum.cw.or.kr/mypage"),
        ("관리", "사업장 관리", "https://eum.cw.or.kr/manage"),
        ("자료실", "공지사항/자료", "https://eum.cw.or.kr/resources"),
        ("고객센터", "고객 지원", "https://eum.cw.or.kr/support"),
        ("공제회", "공제회 정보", "https://eum.cw.or.kr/about"),
    ]

    base_url = "https://eum.cw.or.kr"
    
    for idx, (button_text, page_type, url) in enumerate(menu_buttons, 1):
        print(f"\n[{idx}/{len(menu_buttons)}] {button_text} 탐색 중...")
        
        try:
            # CDP 클라이언트로 이동
            import subprocess
            result = subprocess.run(
                ["python", "scripts/cdp_client.py", "goto", url],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            time.sleep(2)  # 페이지 로드 대기
            
            # 페이지 스냅샷 저장
            result = subprocess.run(
                ["python", "scripts/cdp_client.py", "explore", "page"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # 스냅샷 파일 찾기
            snapshot_files = list(SITEMAP_DIR.glob("eum.cw.or.kr_*.json"))
            if snapshot_files:
                latest_file = max(snapshot_files, key=lambda p: p.stat().st_mtime)
                
                # 스냅샷 분석
                with open(latest_file, "r", encoding="utf-8") as f:
                    snapshot = json.load(f)
                
                page_data = {
                    "menu": button_text,
                    "type": page_type,
                    "url": snapshot.get("url", url),
                    "title": snapshot.get("title", ""),
                    "captured_at": snapshot.get("captured_at", datetime.now().isoformat()),
                    "snapshot_file": str(latest_file.name),
                }
                
                if snapshot.get("frames"):
                    frame = snapshot["frames"][0]
                    page_data["structure"] = {
                        "links": len(frame.get("links", [])),
                        "inputs": len(frame.get("inputs", [])),
                        "buttons": len(frame.get("buttons", [])),
                        "headings": len(frame.get("headings", [])),
                    }
                
                collected_pages.append(page_data)
                print(f"  ✓ 저장 완료: {page_data['title']}")
            
        except subprocess.TimeoutExpired:
            print(f"  ✗ 타임아웃")
        except Exception as e:
            print(f"  ✗ 오류: {e}")
    
    # 종합 사이트맵 생성
    print("\n[사이트맵 생성 중...]")
    
    comprehensive_sitemap = {
        "site": "eum.cw.or.kr",
        "site_name": "건설근로자공제회",
        "site_description": "건설근로자 공제금 관리 및 조회 포털",
        "generated_at": datetime.now().isoformat(),
        "exploration": {
            "total_pages_explored": len(collected_pages),
            "exploration_duration": f"{len(collected_pages) * 5}초",
            "method": "자동 CDP 브라우저 탐색",
        },
        "pages": collected_pages,
        "site_structure": {
            "entry_point": "https://eum.cw.or.kr/main",
            "authentication": {
                "required": True,
                "method": "ID/PW 로그인",
                "password_policy": "영문+숫자+특수문자(~!@#$%^*()+=-) 조합 9자 이상",
            },
            "target_audience": [
                "건설근로자",
                "건설사업 담당자",
                "공제회원",
            ],
        },
    }
    
    # 완전한 사이트맵 저장
    sitemap_file = SITEMAP_DIR / "eum.cw.or.kr_complete_sitemap.json"
    with open(sitemap_file, "w", encoding="utf-8") as f:
        json.dump(comprehensive_sitemap, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ 완전한 사이트맵 저장: {sitemap_file}")
    
    # 요약 출력
    print(f"\n[탐색 결과 요약]")
    print(f"탐색된 페이지: {len(collected_pages)}개")
    print(f"\n페이지 목록:")
    for page in collected_pages:
        print(f"  - {page['menu']} ({page['type']})")
        print(f"    URL: {page['url']}")
        if page.get('structure'):
            print(f"    구조: 링크 {page['structure']['links']}개, "
                  f"입력 {page['structure']['inputs']}개, "
                  f"버튼 {page['structure']['buttons']}개")
    
    return comprehensive_sitemap

if __name__ == "__main__":
    explore_site()
