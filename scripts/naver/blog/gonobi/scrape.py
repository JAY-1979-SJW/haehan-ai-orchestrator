"""gonobi 블로그 전체 카테고리 포스트 수집."""

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.browser.agent.agent import BrowserAgent

CATEGORIES = [
    ("블로그", "24"),
    ("라인/간접/T5", "21"),
    ("마그네틱/레일", "22"),
    ("매입/스포트", "11"),
    ("엠케이통상 소식", "13"),
    ("공지사항", "18"),
    ("★시공사례", "19"),
    ("제품소개", "17"),
    ("IoT 시리즈", "34"),
    ("홈조명", "14"),
    ("욕실/환풍기", "35"),
    ("배선기구", "29"),
    ("시계/거울", "31"),
    ("펜던트", "8"),
    ("센서/직부", "25"),
    ("벽등", "16"),
    ("스탠드", "10"),
    ("산업조명", "27"),
    ("소방기구", "30"),
    ("외벽등/외부등", "32"),
    ("램프", "12"),
    ("기타", "36"),
]


def extract_posts_from_html(html: str) -> list[dict]:
    """HTML에서 포스트 logNo + 제목 추출."""
    log_nos = list(dict.fromkeys(re.findall(r"gonobi[/\\\\](\d{10,})", html)))
    log_no_set = set(log_nos)  # 반복문 안 멤버십 검사를 O(1) 로(순서가 필요한 log_nos 는 그대로)
    title_map: dict[str, str] = {}
    # <a href="...logNo...">제목</a> 패턴
    for m in re.finditer(r'href="[^"]*?(\d{10,})[^"]*?"[^>]*>([^<]{3,80})</a>', html):
        ln, title = m.group(1), m.group(2).strip()
        if ln in log_no_set and title and ln not in title_map:
            title_map[ln] = title
    return [
        {"log_no": ln, "title": title_map.get(ln, ""), "url": f"https://blog.naver.com/gonobi/{ln}"} for ln in log_nos
    ]


def scrape_category(agent: BrowserAgent, name: str, cat_no: str) -> list[dict]:
    posts: list[Any] = []
    page = 1
    while True:
        url = f"https://blog.naver.com/PostList.naver?blogId=gonobi&categoryNo={cat_no}&currentPage={page}"
        agent.go(url)
        time.sleep(2.5)
        html = agent.page.content()
        found = extract_posts_from_html(html)
        if not found:
            break
        # 중복 제거
        existing = {p["log_no"] for p in posts}
        new = [p for p in found if p["log_no"] not in existing]
        if not new:
            break
        posts.extend(new)
        # 다음 페이지 존재 여부
        if f"currentPage={page + 1}" not in html and f"page={page + 1}" not in html:
            # 페이지 버튼 확인
            next_exists = re.search(rf"currentPage={page + 1}", html)
            if not next_exists:
                break
        page += 1
        if page > 20:
            break
    return posts


def main():
    agent = BrowserAgent()
    agent.connect()

    all_results: dict[str, list] = {}
    total = 0
    for name, cat_no in CATEGORIES:
        posts = scrape_category(agent, name, cat_no)
        all_results[name] = posts
        print(f"[{name:15}] {len(posts):3}건")
        total += len(posts)

    print(f"\n총 {total}건")
    out = Path("data/gonobi_all_posts.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {out}")


if __name__ == "__main__":
    main()
