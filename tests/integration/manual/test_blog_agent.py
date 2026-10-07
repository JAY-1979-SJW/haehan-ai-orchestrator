#!/usr/bin/env python3
"""네이버 블로그 도구 테스트."""

from scripts.browser.agent.agent import BrowserAgent


def test_blog_exploration():
    """블로그 탐색 기능 테스트."""

    print("=" * 60)
    print("네이버 블로그 도구 테스트")
    print("=" * 60)

    try:
        with BrowserAgent() as agent:
            # 네이버 블로그 홈 접속
            print("\n[1단계] 네이버 블로그 홈 접속...")
            agent.go("https://blog.naver.com")
            print("✓ 접속 완료")

            # 로그인 상태 확인
            print("\n[2단계] 로그인 상태 확인...")
            page_text = agent.read()[:500]
            if "내 블로그" in page_text or "내 활동" in page_text:
                print("✓ 로그인 상태: OK")
            else:
                print("⚠ 로그인이 필요할 수 있습니다")
                print("현재 페이지 텍스트:", page_text)

            # 네이버 블로그 검색
            print("\n[3단계] 블로그 검색 기능 테스트...")
            results = agent.blog_search("Python", max_results=5)
            print(f"✓ 검색 결과: {len(results)}개")
            if results:
                print(f"  첫 번째 결과: {results[0].get('title', 'N/A')}")

            # 특정 블로그 탐색 (공개 블로그)
            print("\n[4단계] 특정 블로그 탐색...")
            test_blog = "https://blog.naver.com/naver"
            blog_info = agent.blog_info(test_blog)
            print(f"✓ 블로그명: {blog_info.get('title', 'N/A')}")
            print(f"  이웃수: {blog_info.get('neighbor_count', 0)}")
            print(f"  오늘 방문: {blog_info.get('visitor_today', 0)}")

            # 카테고리 조회
            print("\n[5단계] 카테고리 조회...")
            categories = agent.blog_categories(test_blog)
            print(f"✓ 카테고리: {len(categories)}개")
            if categories:
                print(f"  예: {categories[0].get('name')} ({categories[0].get('post_count')}개)")

            # 포스트 목록
            print("\n[6단계] 포스트 목록 조회...")
            posts = agent.blog_posts(test_blog, max_posts=5)
            print(f"✓ 포스트: {len(posts)}개")
            for i, post in enumerate(posts[:3], 1):
                print(f"  {i}. {post.get('title', 'N/A')[:50]}")

            print("\n" + "=" * 60)
            print("✓ 모든 테스트 완료!")
            print("=" * 60)

    except Exception as e:  # noqa: BLE001 - 수동 통합 테스트 스크립트 — 예외 발생 시 traceback을 그대로 출력해 사람이 확인하도록 하는 진단용 except, 결과를 숨기지 않음.
        print(f"\n✗ 오류 발생: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_blog_exploration()
