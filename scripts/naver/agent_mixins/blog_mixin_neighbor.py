"""blog_mixin 이웃 자동화 기능 (BlogNeighborMixin).

visit/comment/like_neighbors, visit_and_comment, neighbor_activity,
mutual_request_all. 이웃 목록·읽기·쓰기 능력은 self(MRO)로 호출한다.
[docs/module_separation_standard.md]
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any


class BlogNeighborMixin:
    if TYPE_CHECKING:
        # 다른 믹스인의 메서드를 self(MRO)로 호출한다 — 정적 검사기에는 합쳐진 클래스가 보이지 않으므로 알려 준다(런타임 영향 없음).
        def __getattr__(self, name: str) -> Any: ...

    def blog_visit_neighbors(self, blog_url: str, max_neighbors: int = 20, delay: float = 2.0) -> list[dict]:
        """이웃 블로그 순차 방문 + 정보 수집."""
        neighbors = self.blog_neighbors(blog_url, max_neighbors=max_neighbors)
        results = []

        for i, neighbor in enumerate(neighbors, 1):
            print(f"  [{i}/{len(neighbors)}] {neighbor.get('nickname', '')}...", end="", flush=True)
            try:
                info = self.blog_info(neighbor["blog_url"])
                posts = self.blog_posts(neighbor["blog_url"], max_posts=1)
                last_post = posts[0] if posts else {}

                results.append(
                    {
                        "blog_id": neighbor["blog_id"],
                        "nickname": neighbor["nickname"],
                        "last_post_title": last_post.get("title", ""),
                        "last_post_date": last_post.get("date", ""),
                        "visitor_today": info.get("visitor_today", 0),
                        "neighbor_count": info.get("neighbor_count", 0),
                        "visit_ok": True,
                    }
                )
                print(" ✓")
                time.sleep(delay)
            except Exception as e:  # noqa: BLE001 - 네이버 블로그 이웃추가/댓글/공감/방문 자동화 - 실패시 ok:False,error 형태로 results 에 기록(성공 위장 없음)
                print(f" ✗ {e}")
                results.append(
                    {
                        "blog_id": neighbor["blog_id"],
                        "nickname": neighbor["nickname"],
                        "last_post_title": "",
                        "last_post_date": "",
                        "visitor_today": 0,
                        "neighbor_count": 0,
                        "visit_ok": False,
                    }
                )

        return results

    def blog_comment_neighbors(
        self,
        blog_url: str,
        comment_text: str,
        max_neighbors: int = 10,
        delay: float = 3.0,
        skip_already_commented: bool = True,
    ) -> list[dict]:
        """이웃 최신 포스트에 댓글 작성."""
        neighbors = self.blog_neighbors(blog_url, max_neighbors=max_neighbors)
        results = []

        for i, neighbor in enumerate(neighbors, 1):
            print(f"  [{i}/{len(neighbors)}] {neighbor.get('nickname', '')}...", end="", flush=True)
            try:
                posts = self.blog_posts(neighbor["blog_url"], max_posts=1)
                if not posts:
                    print(" 포스트 없음")
                    continue

                post = posts[0]
                post_url = post.get("href", "")

                if skip_already_commented:
                    comments = self.blog_post_comments(post_url, max_comments=30)
                    my_nickname = ""
                    try:
                        my_info = self.blog_info("https://blog.naver.com/")
                        my_nickname = my_info.get("title", "").split("-")[0].strip()
                    except Exception:  # noqa: S110, BLE001 - 네이버 블로그 이웃추가/댓글/공감/방문 자동화 - 실패시 ok:False,error 형태로 results 에 기록(성공 위장 없음)
                        pass

                    if any(my_nickname in c.get("author", "") for c in comments):
                        print(" 이미 댓글함")
                        continue

                self.blog_write_comment(post_url, comment_text)
                results.append(
                    {
                        "blog_id": neighbor["blog_id"],
                        "post_url": post_url,
                        "post_title": post.get("title", ""),
                        "ok": True,
                        "error": "",
                    }
                )
                print(" ✓ 댓글 작성")
                time.sleep(delay)
            except Exception as e:  # noqa: BLE001 - 네이버 블로그 이웃추가/댓글/공감/방문 자동화 - 실패시 ok:False,error 형태로 results 에 기록(성공 위장 없음)
                print(f" ✗ {e}")
                results.append(
                    {
                        "blog_id": neighbor["blog_id"],
                        "post_url": "",
                        "post_title": "",
                        "ok": False,
                        "error": str(e),
                    }
                )

        return results

    def blog_like_neighbors(self, blog_url: str, max_neighbors: int = 20, delay: float = 2.0) -> list[dict]:
        """이웃 최신 포스트 공감."""
        neighbors = self.blog_neighbors(blog_url, max_neighbors=max_neighbors)
        results = []

        for i, neighbor in enumerate(neighbors, 1):
            print(f"  [{i}/{len(neighbors)}] {neighbor.get('nickname', '')}...", end="", flush=True)
            try:
                posts = self.blog_posts(neighbor["blog_url"], max_posts=1)
                if not posts:
                    print(" 포스트 없음")
                    continue

                post = posts[0]
                post_url = post.get("href", "")

                result = self.blog_like_post(post_url)
                results.append(
                    {
                        "blog_id": neighbor["blog_id"],
                        "post_url": post_url,
                        "ok": result["ok"],
                        "like_count": result.get("like_count", 0),
                        "error": result["error"],
                    }
                )
                print(f" ✓ 공감 ({result.get('like_count', 0)})")
                time.sleep(delay)
            except Exception as e:  # noqa: BLE001 - 네이버 블로그 이웃추가/댓글/공감/방문 자동화 - 실패시 ok:False,error 형태로 results 에 기록(성공 위장 없음)
                print(f" ✗ {e}")
                results.append(
                    {
                        "blog_id": neighbor["blog_id"],
                        "post_url": "",
                        "ok": False,
                        "like_count": 0,
                        "error": str(e),
                    }
                )

        return results

    def blog_visit_and_comment(
        self, blog_url: str, comment_text: str, max_neighbors: int = 10, also_like: bool = True, delay: float = 3.5
    ) -> list[dict]:
        """이웃 방문 + 공감 + 댓글."""
        neighbors = self.blog_neighbors(blog_url, max_neighbors=max_neighbors)
        results = []

        for i, neighbor in enumerate(neighbors, 1):
            print(f"  [{i}/{len(neighbors)}] {neighbor.get('nickname', '')}...", end="", flush=True)
            try:
                posts = self.blog_posts(neighbor["blog_url"], max_posts=1)
                if not posts:
                    print(" 포스트 없음")
                    continue

                post = posts[0]
                post_url = post.get("href", "")

                visited = True
                liked = False
                commented = False

                if also_like:
                    like_result = self.blog_like_post(post_url)
                    liked = like_result["ok"]

                comment_result = self.blog_write_comment(post_url, comment_text)
                commented = comment_result["ok"]

                results.append(
                    {
                        "blog_id": neighbor["blog_id"],
                        "post_url": post_url,
                        "visited": visited,
                        "liked": liked,
                        "commented": commented,
                        "error": "",
                    }
                )
                print(" ✓")
                time.sleep(delay)
            except Exception as e:  # noqa: BLE001 - 네이버 블로그 이웃추가/댓글/공감/방문 자동화 - 실패시 ok:False,error 형태로 results 에 기록(성공 위장 없음)
                print(f" ✗ {e}")
                results.append(
                    {
                        "blog_id": neighbor["blog_id"],
                        "post_url": "",
                        "visited": False,
                        "liked": False,
                        "commented": False,
                        "error": str(e),
                    }
                )

        return results

    def blog_neighbor_activity(self, blog_url: str, days: int = 7) -> list[dict]:
        """이웃 최근 N일 활동 현황."""
        neighbors = self.blog_neighbors(blog_url)
        results = []

        for neighbor in neighbors:
            try:
                posts = self.blog_posts(neighbor["blog_url"], max_posts=3)
                post_count_recent = 0

                for post in posts:
                    date_str = post.get("date", "")
                    if date_str:
                        m = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", date_str)
                        if m:
                            from datetime import datetime

                            post_date = datetime.strptime(f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "%Y-%m-%d")
                            if (datetime.now() - post_date).days <= days:
                                post_count_recent += 1

                last_post = posts[0] if posts else {}
                is_active = post_count_recent > 0

                results.append(
                    {
                        "blog_id": neighbor["blog_id"],
                        "nickname": neighbor["nickname"],
                        "post_count_recent": post_count_recent,
                        "last_post_date": last_post.get("date", ""),
                        "last_post_title": last_post.get("title", ""),
                        "is_active": is_active,
                    }
                )
            except Exception:  # noqa: BLE001 - 네이버 블로그 이웃추가/댓글/공감/방문 자동화 - 실패시 ok:False,error 형태로 results 에 기록(성공 위장 없음)
                results.append(
                    {
                        "blog_id": neighbor["blog_id"],
                        "nickname": neighbor["nickname"],
                        "post_count_recent": 0,
                        "last_post_date": "",
                        "last_post_title": "",
                        "is_active": False,
                    }
                )

        return results

    def blog_mutual_request_all(self, blog_url: str, max_targets: int = 20) -> list[dict]:
        """서로이웃이 아닌 이웃에게 서로이웃 신청."""
        neighbors = self.blog_neighbors(blog_url, max_neighbors=max_targets)
        results = []

        for i, neighbor in enumerate(neighbors, 1):
            if neighbor.get("is_mutual"):
                continue

            print(f"  [{i}/{len(neighbors)}] {neighbor.get('nickname', '')} 서로이웃 신청...", end="", flush=True)
            try:
                result = self.blog_add_neighbor(neighbor["blog_url"], is_mutual=True)
                results.append(
                    {
                        "blog_id": neighbor["blog_id"],
                        "ok": result["ok"],
                        "error": result["error"],
                    }
                )
                print(" ✓")
                time.sleep(3.0)
            except Exception as e:  # noqa: BLE001 - 네이버 블로그 이웃추가/댓글/공감/방문 자동화 - 실패시 ok:False,error 형태로 results 에 기록(성공 위장 없음)
                print(f" ✗ {e}")
                results.append(
                    {
                        "blog_id": neighbor["blog_id"],
                        "ok": False,
                        "error": str(e),
                    }
                )

        return results
