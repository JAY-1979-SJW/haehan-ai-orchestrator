"""blog_mixin 이미지/HTML 다운로드 기능 (BlogDownloadMixin).

download_images, download_all_images, save_post_html.
이미지 목록·다운로드 능력은 self(MRO)로 호출한다. [docs/module_separation_standard.md]
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any


class BlogDownloadMixin:
    if TYPE_CHECKING:
        # 다른 믹스인의 메서드를 self(MRO)로 호출한다 — 정적 검사기에는 합쳐진 클래스가 보이지 않으므로 알려 준다(런타임 영향 없음).
        def __getattr__(self, name: str) -> Any: ...

    def blog_download_images(self, post_url: str, save_dir: str = "data/blog_images") -> dict:
        """단일 포스트 이미지 다운로드."""
        m = re.search(r"blog\.naver\.com/(\w+)/(\d{10,})|blogId=(\w+).*logNo=(\d+)", post_url)
        blog_id = m.group(1) or m.group(3) if m else ""
        log_no = m.group(2) or m.group(4) if m else ""

        post_save_dir = Path(save_dir) / blog_id / log_no
        post_save_dir.mkdir(parents=True, exist_ok=True)

        images = self.blog_post_images(post_url)
        downloaded = 0
        failed = 0
        paths = []

        for i, img in enumerate(images, 1):
            src = img.get("src", "") if isinstance(img, dict) else img
            if not src:
                continue

            try:
                result = self.download_attachment(src, save_dir=str(post_save_dir))
                if result["ok"]:
                    downloaded += 1
                    paths.append(result["path"])
                    print(f"    이미지 {i}/{len(images)}: ✓ {Path(result['path']).name}")
                else:
                    failed += 1
                    print(f"    이미지 {i}/{len(images)}: ✗ {result['error']}")
            except Exception as e:  # noqa: BLE001 - 내 블로그 이미지/HTML을 로컬로 백업 다운로드(읽기전용, 외부 발행 없음) — 개별 이미지/포스트 다운로드 실패는 failed 카운트에 반영되어 은폐되지 않음.
                failed += 1
                print(f"    이미지 {i}/{len(images)}: ✗ {e}")

        return {
            "ok": failed == 0,
            "downloaded": downloaded,
            "failed": failed,
            "paths": paths,
            "save_dir": str(post_save_dir),
        }

    def blog_download_all_images(
        self, blog_url: str, save_dir: str = "data/blog_images", category_no: str = "", max_pages: int = 5
    ) -> dict:
        """블로그 전체 이미지 다운로드."""
        blog_id = blog_url.rstrip("/").split("/")[-1]
        total_posts = 0
        downloaded = 0
        failed = 0

        for page in range(1, max_pages + 1):
            print(f"\n[페이지 {page}/{max_pages}]")
            posts = self.blog_posts(blog_url, category_no=category_no, page=page, max_posts=30)

            if not posts:
                print("  포스트 없음, 종료")
                break

            for i, post in enumerate(posts, 1):
                total_posts += 1
                post_url = post.get("href", "")
                print(f"  [{i}/{len(posts)}] {post['title'][:40]}...")

                try:
                    result = self.blog_download_images(post_url, save_dir=save_dir)
                    downloaded += result["downloaded"]
                    failed += result["failed"]
                    time.sleep(1.5)
                except Exception as e:  # noqa: BLE001 - 내 블로그 이미지/HTML을 로컬로 백업 다운로드(읽기전용, 외부 발행 없음) — 개별 이미지/포스트 다운로드 실패는 failed 카운트에 반영되어 은폐되지 않음.
                    print(f"    오류: {e}")
                    failed += len(self.blog_post_images(post_url))

        return {
            "ok": failed == 0,
            "total_posts": total_posts,
            "downloaded": downloaded,
            "failed": failed,
            "save_dir": str(Path(save_dir) / blog_id),
        }

    def blog_save_post_html(self, post_url: str, save_dir: str = "data/blog_html") -> dict:
        """포스트를 HTML로 저장."""
        m = re.search(r"blog\.naver\.com/(\w+)/(\d{10,})|blogId=(\w+).*logNo=(\d+)", post_url)
        blog_id = m.group(1) or m.group(3) if m else ""
        log_no = m.group(2) or m.group(4) if m else ""

        self.go(post_url)
        time.sleep(2)

        try:
            html_content = self._page.content()
            save_path = Path(save_dir) / blog_id / f"{log_no}.html"
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_text(html_content, encoding="utf-8")

            return {
                "ok": True,
                "path": str(save_path),
                "size": save_path.stat().st_size,
                "error": "",
            }
        except Exception as e:  # noqa: BLE001 - 내 블로그 이미지/HTML을 로컬로 백업 다운로드(읽기전용, 외부 발행 없음) — 개별 이미지/포스트 다운로드 실패는 failed 카운트에 반영되어 은폐되지 않음.
            return {
                "ok": False,
                "path": "",
                "size": 0,
                "error": str(e),
            }
