"""네이버 가입 카페 전체 목록 조회 + 주요 카페 탐색."""

import time

from playwright.sync_api import sync_playwright


def get_cafe_list(page):
    js = """
() => {
    const results = [];
    const skip = ['내가 쓴 글', '탈퇴', '새 창', '메일', '즐겨찾기'];
    for (const a of document.querySelectorAll('a')) {
        const txt = (a.innerText || '').trim().split('\\n')[0].trim();
        const href = a.href || '';
        if (!href.includes('cafe.naver.com/')) continue;
        if (href.includes('ca-fe')) continue;
        if (href.includes('MyCafe')) continue;
        if (href.includes('javascript')) continue;
        if (!txt || txt.length < 2) continue;
        if (skip.some(s => txt.includes(s))) continue;
        results.push({name: txt.substring(0, 50), href});
    }
    const seen = new Set();
    return results.filter(r => {
        if (seen.has(r.href)) return false;
        seen.add(r.href);
        return true;
    });
}
"""
    return page.evaluate(js)


def explore_cafe(page, name, url):
    """카페 메인 접속 후 최신 게시글 목록 읽기."""
    print(f"\n{'=' * 60}")
    print(f"카페: {name}")
    print(f"URL : {url}")
    print("=" * 60)
    try:
        page.goto(url, timeout=15000)
        time.sleep(3)
        text = page.inner_text("body")
        # 게시글 제목만 추출 (짧고 반복되는 노이즈 제거)
        lines = [l.strip() for l in text.splitlines() if l.strip()]  # noqa: E741
        # 의미있는 줄만 (5자 이상, 네비/버튼 제외)
        skip_words = ["새 창에서", "로그인", "댓글", "좋아요", "더보기", "Copyright", "이전", "다음", "NAVER"]
        content = [l for l in lines if len(l) > 4 and not any(w in l for w in skip_words)]  # noqa: E741
        print("\n".join(content[:40]))
    except Exception as e:
        print(f"  오류: {e}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        ctx = browser.contexts[0]
        page = ctx.pages[0]

        # 관리 페이지로 이동
        page.goto("https://section.cafe.naver.com/ca-fe/home/manage-my-cafe/join", timeout=15000)
        time.sleep(4)

        cafes = get_cafe_list(page)
        print(f"\n전체 가입 카페 {len(cafes)}개:\n")
        for i, c in enumerate(cafes, 1):
            print(f"  {i:2}. {c['name'][:45]:45} | {c['href']}")

        # 상위 관심 카페 5개 탐색
        priority = ["건설공무", "AI", "Revit", "BIM", "전기박사", "엑사모"]
        to_visit = []
        for keyword in priority:
            for c in cafes:
                if keyword.lower() in c["name"].lower() and c not in to_visit:
                    to_visit.append(c)
                    break

        print(f"\n\n탐색할 카페 {len(to_visit)}개:")
        for c in to_visit:
            explore_cafe(page, c["name"], c["href"])


if __name__ == "__main__":
    main()
