"""blog_mixin 멀티 블로그 수집/추적 기능 (BlogCollectMixin).

bulk_collect, monitor_keywords, track_blogger, search_bulk, compare_bloggers.
개별 조회 능력은 self(MRO)로 호출한다. [docs/module_separation_standard.md]
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any


class BlogCollectMixin:
    if TYPE_CHECKING:
        # 다른 믹스인의 메서드를 self(MRO)로 호출한다 — 정적 검사기에는 합쳐진 클래스가 보이지 않으므로 알려 준다(런타임 영향 없음).
        def __getattr__(self, name: str) -> Any: ...

    def blog_bulk_collect(
        self,
        blog_urls: list[str],
        include_posts: bool = True,
        include_comments: bool = False,
        include_images: bool = False,
        max_posts_each: int = 20,
    ) -> list[dict]:
        """여러 블로그 일괄 수집."""
        results = []

        for i, blog_url in enumerate(blog_urls, 1):
            print(f"\n[{i}/{len(blog_urls)}] {blog_url} 수집 중...")
            try:
                blog_data = self.blog_info(blog_url)

                if include_posts:
                    blog_data["posts"] = self.blog_posts(blog_url, max_posts=max_posts_each)

                    if include_comments:
                        blog_data["comments"] = self.blog_all_comments(blog_url, max_posts=max_posts_each)

                    if include_images:
                        for post in blog_data.get("posts", [])[:5]:
                            post["images"] = self.blog_post_images(post.get("href", ""))

                results.append(blog_data)
                time.sleep(2.0)
            except Exception as e:  # noqa: BLE001 - 네이버 블로그 읽기전용 수집(글목록/태그/본문/좋아요수 비교) - 실패시 error 필드 기록 후 계속 진행, 쓰기 없음
                print(f"  오류: {e}")
                results.append({"blog_id": blog_url.split("/")[-1], "error": str(e)})

        return results

    def blog_monitor_keywords(self, keywords: list[str], page: int = 1, max_each: int = 20) -> dict:
        """키워드 검색 → 결과 수집."""
        results = {}

        for keyword in keywords:
            print(f"\n검색: '{keyword}'...")
            try:
                search_results = self.blog_search(keyword, page=page, max_results=max_each)
                results[keyword] = search_results
                time.sleep(1.5)
            except Exception as e:  # noqa: BLE001 - 네이버 블로그 읽기전용 수집(글목록/태그/본문/좋아요수 비교) - 실패시 error 필드 기록 후 계속 진행, 쓰기 없음
                print(f"  오류: {e}")
                results[keyword] = []

        return results

    def blog_track_blogger(self, target_blog_url: str, save_path: str = "") -> dict:
        """블로거 전체 정보 스냅샷."""
        from datetime import datetime

        print(f"블로거 추적: {target_blog_url}")
        info = self.blog_info(target_blog_url)
        categories = self.blog_categories(target_blog_url)
        recent_posts = self.blog_posts(target_blog_url, max_posts=10)
        stats = self.blog_stats_detail(target_blog_url)

        # 태그 수집 — 최근 포스트 최대 5개 읽어서 태그 집계
        top_tags: dict[str, int] = {}
        for post in recent_posts[:5]:
            href = post.get("href", "")
            if not href:
                continue
            try:
                post_data = self.blog_read_post(href)
                for tag in post_data.get("tags", []):
                    if tag:
                        top_tags[tag] = top_tags.get(tag, 0) + 1
            except Exception:  # noqa: S110, BLE001 - 네이버 블로그 읽기전용 수집(글목록/태그/본문/좋아요수 비교) - 실패시 error 필드 기록 후 계속 진행, 쓰기 없음
                pass
        # 빈도순 정렬
        top_tags = dict(sorted(top_tags.items(), key=lambda x: x[1], reverse=True))

        snapshot = {
            "captured_at": datetime.now().isoformat(),
            "blog_info": info,
            "categories": categories,
            "recent_posts": recent_posts,
            "stats": stats,
            "top_tags": top_tags,
        }

        if save_path:
            import json

            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            with Path(save_path).open("w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
            print(f"  저장: {save_path}")

        return snapshot

    def blog_search_bulk(self, query: str, max_pages: int = 3, collect_post: bool = False) -> list[dict]:
        """검색 결과 여러 페이지 수집."""
        results = []

        for page in range(1, max_pages + 1):
            print(f"  페이지 {page}/{max_pages}...", end="", flush=True)
            try:
                page_results = self.blog_search(query, page=page)

                if collect_post:
                    for result in page_results:
                        post_url = result.get("href", "")
                        if post_url:
                            try:
                                post_data = self.blog_read_post(post_url)
                                result["body"] = post_data.get("body", "")
                                result["images"] = post_data.get("images", [])
                            except Exception:  # noqa: S110, BLE001 - 네이버 블로그 읽기전용 수집(글목록/태그/본문/좋아요수 비교) - 실패시 error 필드 기록 후 계속 진행, 쓰기 없음
                                pass

                results.extend(page_results)
                print(f" {len(page_results)}개")
                time.sleep(1.5)
            except Exception as e:  # noqa: BLE001 - 네이버 블로그 읽기전용 수집(글목록/태그/본문/좋아요수 비교) - 실패시 error 필드 기록 후 계속 진행, 쓰기 없음
                print(f" 오류: {e}")

        return results

    def blog_compare_bloggers(self, blog_urls: list[str]) -> list[dict]:
        """블로거 비교표."""
        results = []

        for blog_url in blog_urls:
            try:
                info = self.blog_info(blog_url)
                posts = self.blog_posts(blog_url, max_posts=20)

                avg_comments = 0
                avg_likes = 0
                if posts:
                    avg_comments = sum(p.get("comment_count", 0) for p in posts) / len(posts)
                    # 좋아요: 최근 5개 포스트 직접 읽어서 like_count 평균
                    like_counts = []
                    for p in posts[:5]:
                        href = p.get("href", "")
                        if href:
                            try:
                                pd = self.blog_read_post(href)
                                like_counts.append(pd.get("like_count", 0))
                            except Exception:  # noqa: S110, BLE001 - 네이버 블로그 읽기전용 수집(글목록/태그/본문/좋아요수 비교) - 실패시 error 필드 기록 후 계속 진행, 쓰기 없음
                                pass
                    if like_counts:
                        avg_likes = sum(like_counts) / len(like_counts)

                results.append(
                    {
                        "blog_id": info["blog_id"],
                        "title": info["title"],
                        "post_count": len(posts),
                        "neighbor_count": info["neighbor_count"],
                        "visitor_total": info["visitor_total"],
                        "visitor_today": info["visitor_today"],
                        "avg_comments": round(avg_comments, 1),
                        "avg_likes": avg_likes,
                    }
                )
                time.sleep(2.0)
            except Exception as e:  # noqa: BLE001 - 네이버 블로그 읽기전용 수집(글목록/태그/본문/좋아요수 비교) - 실패시 error 필드 기록 후 계속 진행, 쓰기 없음
                print(f"  {blog_url} 오류: {e}")

        return results
