"""네이버 카페 탐색 — CDP 연결된 Chrome에서 가입 카페 목록 조회."""
from playwright.sync_api import sync_playwright
import json, time

GQL_QUERY = """
query {
  joinedCafeList {
    totalCount
    cafes {
      cafeId
      cafeName
      cafeUrl
      memberCount
    }
  }
}
"""

GQL_QUERY2 = """
query HomeJoinedCafeList {
  joinedCafeList(page: 1, perPage: 50) {
    totalCount
    cafes {
      cafeId
      cafeName
      cafeUrl
    }
  }
}
"""

def explore():
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp('http://localhost:9222')
        ctx = browser.contexts[0]
        page = ctx.pages[0]

        # 카페 홈 이동
        page.goto('https://cafe.naver.com/ca-fe/cafes/joined', timeout=20000)
        time.sleep(4)

        # 페이지 내 fetch로 GraphQL 호출 (쿠키 자동 포함)
        js = """
(async () => {
    const gql = "query { joinedCafeList { totalCount cafes { cafeId cafeName cafeUrl memberCount } } }";
    const r = await fetch('https://bff.cafe.naver.com/graphql', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'Referer': 'https://cafe.naver.com' },
        body: JSON.stringify({ query: gql })
    });
    return r.json();
})()
"""
        try:
            result = page.evaluate(js)
            cafes = result.get('data', {}).get('joinedCafeList', {}).get('cafes', [])
            total = result.get('data', {}).get('joinedCafeList', {}).get('totalCount', 0)
            print(f"\n가입 카페 총 {total}개:\n")
            for i, c in enumerate(cafes, 1):
                print(f"  {i:2}. {c.get('cafeName','?'):30} | 회원 {c.get('memberCount','?'):>8}명 | https://cafe.naver.com/{c.get('cafeUrl','')}")
            return cafes
        except Exception as e:
            print("GraphQL 오류:", e)

        # 폴백: 페이지 DOM 직접 파싱
        print("\n[폴백] DOM에서 카페 목록 추출 시도...")
        time.sleep(3)
        links = page.evaluate("""
() => {
    const all = document.querySelectorAll('a[href*="cafe.naver.com"]');
    const seen = new Set();
    const result = [];
    for (const a of all) {
        const href = a.href;
        const name = a.textContent.trim();
        if (name && href && !seen.has(href) && href.includes('cafe.naver.com/') && !href.includes('ca-fe')) {
            seen.add(href);
            result.push({ name, href });
        }
    }
    return result;
}
""")
        print(f"링크 {len(links)}개 발견:")
        for l in links[:30]:
            print(f"  - {l['name'][:40]:40} | {l['href']}")

        browser.close()

if __name__ == '__main__':
    explore()
