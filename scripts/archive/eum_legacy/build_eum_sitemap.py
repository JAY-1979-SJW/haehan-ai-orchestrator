"""eum.cw.or.kr 사이트맵 생성 - 현재 저장된 스냅샷 분석."""
import json
from pathlib import Path

# 저장된 스냅샷 로드
snapshot_file = Path("data/sitemap/eum.cw.or.kr_main.json")
if not snapshot_file.exists():
    print("스냅샷 파일 없음:", snapshot_file)
    exit(1)

with open(snapshot_file, "r", encoding="utf-8") as f:
    snapshot = json.load(f)

# 사이트맵 생성
sitemap = {
    "site": "eum.cw.or.kr",
    "root": "https://eum.cw.or.kr/main",
    "pages": []
}

# 현재 페이지 정보
page_info = {
    "url": snapshot.get("url"),
    "title": snapshot.get("title"),
    "path": "/main",
    "links": [],
    "inputs": [],
    "buttons": [],
    "headings": [],
}

# 프레임 데이터 추출
if snapshot.get("frames"):
    frame = snapshot["frames"][0]
    
    # 내부 링크 추출 (http 시작 제외)
    internal_links = []
    for link in frame.get("links", []):
        href = link.get("href", "")
        text = link.get("text", "").strip()
        # 내부 링크만 추가
        if href and not href.startswith("http") and text and len(text) > 0:
            internal_links.append({"text": text, "href": href})
    
    page_info["links"] = internal_links[:20]
    page_info["inputs"] = frame.get("inputs", [])[:10]
    page_info["buttons"] = frame.get("buttons", [])[:10]
    page_info["headings"] = frame.get("headings", [])[:10]
    
    print(f"\n✓ 스냅샷 분석 완료")
    print(f"  URL: {page_info['url']}")
    print(f"  제목: {page_info['title']}")
    print(f"  내부 링크: {len(internal_links)}개")
    print(f"  입력 필드: {len(frame.get('inputs', []))}개")
    print(f"  버튼: {len(frame.get('buttons', []))}개")

sitemap["pages"].append(page_info)

# 사이트맵 저장
sitemap_file = Path("data/sitemap/eum.cw.or.kr_sitemap.json")
with open(sitemap_file, "w", encoding="utf-8") as f:
    json.dump(sitemap, f, ensure_ascii=False, indent=2)

print(f"\n✓ 사이트맵 저장 완료: {sitemap_file}")

# 요약 출력
print("\n[사이트맵 구조]")
print(f"사이트: {sitemap['site']}")
print(f"루트: {sitemap['root']}")
print(f"탐색된 페이지: {len(sitemap['pages'])}개")
print(f"\n주요 내부 링크:")
for link in page_info["links"][:10]:
    print(f"  - {link['text']} → {link['href']}")
