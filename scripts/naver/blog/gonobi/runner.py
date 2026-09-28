"""gonobi 수집 실행기 — 수집 + 분류 + DB 저장 통합 (L6 Workflow).

서버 백그라운드 태스크 및 크론잡에서 호출.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ScrapeResult:
    total: int = 0
    new: int = 0
    updated: int = 0
    errors: int = 0
    by_category: dict = field(default_factory=dict)


def run_scrape(
    delay: float = 0.5,
    categories=None,
    progress_cb: Callable | None = None,
    db_path: Path | None = None,
) -> ScrapeResult:
    """전체 수집 → AI 분류 → DB 저장."""
    from .classifier import classify_post
    from .db import open_db, upsert_images, upsert_post
    from .scraper import iter_all_posts

    result = ScrapeResult()

    with open_db(db_path) as conn:
        for post in iter_all_posts(delay=delay, categories=categories, progress_cb=progress_cb):
            try:
                our_cat = classify_post(post.title, post.body)
                post_dict = post.to_dict()
                post_dict["our_category"] = our_cat

                is_new = upsert_post(conn, post_dict)
                upsert_images(conn, post.log_no, post.images)

                result.total += 1
                if is_new:
                    result.new += 1
                else:
                    result.updated += 1

                by = result.by_category
                by[our_cat] = by.get(our_cat, 0) + 1

                if result.total % 50 == 0:
                    logger.info("수집 진행: %d건 (신규:%d)", result.total, result.new)
            except Exception as e:  # noqa: BLE001 - gonobi 블로그 포스트 수집 루프 - 개별 포스트 처리 실패는 errors 카운트 증가 후 다음 포스트로 계속 진행(읽기전용 수집)
                logger.error("포스트 처리 실패 %s: %s", post.log_no, e)
                result.errors += 1

    logger.info("수집 완료: 총%d건 신규%d건 오류%d건", result.total, result.new, result.errors)
    return result
