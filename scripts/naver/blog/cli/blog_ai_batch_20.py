"""AI 블로그 일괄 작성 커맨드라인 진입점 (대상 계정: skyjwsin).

실제 로직은 scripts/naver/blog/marketing/ 패키지에 섹션별로 분리되어 있다:
  topics.py   - 주제 선정 (리서치 결과 우선, 부족분만 AI 보충)
  images.py   - Unsplash 이미지 수집/배분
  content.py  - AI 본문/제목 생성 + SEO 점검
  publish.py  - CDP 로그인 + 발행

흐름:
  1. data/blog_topic_cache.json 로드 (없으면 빈 캐시 생성)
  2. Unsplash API로 건설 실무 관련 이미지 수집 (주제별 3장)
  3. 리서치 결과(지식iN 실제 질문) 우선 사용, 부족하면 AI 보충 생성
  4. 각 주제: 제목+본문 생성(SEO 점검 포함) → 이미지 3장 다운로드 → 발행
  5. 발행 성공 시 캐시 업데이트

실행:
  python scripts/naver/blog/cli/blog_ai_batch_20.py [--dry-run] [--count N]
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, ".")

from scripts.common.logger import get_logger
from scripts.naver.blog.marketing import TARGET_BLOG_ID
from scripts.naver.blog.marketing.content import generate_post
from scripts.naver.blog.marketing.images import fetch_unsplash_images, pick_3_images
from scripts.naver.blog.marketing.publish import (
    connect_and_ensure_login,
    existing_unsplash_fallback,
    publish_one,
    record_success,
    wait_between_posts,
)
from scripts.naver.blog.marketing.topics import generate_topics, load_cache

_log = get_logger(__name__)


def _collect_images(dry_run: bool) -> list:
    """Unsplash 이미지 수집(dry-run 이면 기존 이미지 사용)."""
    print("\n[이미지] Unsplash 수집 중...")
    if dry_run:
        print("  [DRY-RUN] Unsplash API 호출 스킵 — 기존 images 사용")
        all_images = existing_unsplash_fallback()
        print(f"  기존 이미지: {len(all_images)}개")
    else:
        all_images = fetch_unsplash_images(count_per_query=5)
        print(f"  수집 완료: {len(all_images)}개")

    if len(all_images) < 3 and not dry_run:
        print("  경고: 이미지 부족. 기존 파일 보충...")
        all_images += existing_unsplash_fallback()
    return all_images


def _select_topics(cache: dict, count: int, dry_run: bool) -> list:
    """주제 선정 + 목록 출력."""
    print(f"\n[주제] 선정 중 ({count}개)...")
    topics = generate_topics(cache, count, dry_run=dry_run)
    print(f"  선정된 주제: {len(topics)}개")
    for i, t in enumerate(topics):
        print(f"  {i + 1:2d}. {t['topic']}")
    return topics


def _print_post_summary(post: dict) -> None:
    """생성된 포스트 요약 출력(제목/본문 길이/태그/SEO)."""
    segs = post.get("body_segments", [])
    print(f"  제목: {post['title']}")
    print(f"  본문: {len(post['body'])}자 ({len(segs)}구간)  태그: {post['tags']}")
    seo = post.get("seo")
    if seo:
        print(f"  SEO: {'✅ 통과' if seo['ok'] else '⚠ ' + ' / '.join(seo['warnings'])}")


def _print_run_summary(results: list, dry_run: bool) -> None:
    """완료 요약 출력."""
    print(f"\n{'=' * 60}")
    print(f"  완료 요약 ({'DRY-RUN' if dry_run else '실제 발행'})")
    print(f"{'=' * 60}")
    success = sum(1 for r in results if r.get("ok"))
    print(f"  성공: {success}/{len(results)}")
    for r in results:
        status = "✅" if r.get("ok") else "❌"
        tag = " [DRY]" if r.get("dry_run") else ""
        print(f"  {status} {r.get('title', r.get('topic', '?'))[:50]}{tag}")


def _pick_images(dry_run: bool, all_images: list, idx: int) -> list:
    """이미지 3장 선택/다운로드(dry-run 이면 더미 경로)."""
    if dry_run:
        img_paths = [f"[DRY] image{j + 1}.jpg" for j in range(3)]
    else:
        img_paths = pick_3_images(all_images, idx)
    return img_paths


def _require_batch_approval(dry_run: bool, approval: str | None, count: int) -> None:
    """이 일괄 작성은 글마다 즉시 발행한다 — 시작 전에 사용자가 직접 입력한 승인 문구를 확인한다(dry-run 은 제외)."""
    if dry_run:
        return
    from scripts.common.gate import require_approved

    require_approved("blog_publish", approval, via="blog_ai_batch_20", count=count)


def run(count: int = 20, dry_run: bool = False, approval: str | None = None) -> None:
    _require_batch_approval(dry_run, approval, count)
    print(f"\n{'=' * 60}")
    print(f"  블로그 AI 일괄 작성 {'[DRY-RUN]' if dry_run else '[실행]'}")
    print(f"  대상 계정: {TARGET_BLOG_ID}  |  목표: {count}편")
    print(f"{'=' * 60}\n")

    # 1. 캐시 로드
    cache = load_cache()
    print(f"[캐시] 기존 발행 주제: {len(cache.get('posted', []))}개")

    # 2. 이미지 수집
    all_images = _collect_images(dry_run)

    # 3. 주제 선정
    topics = _select_topics(cache, count, dry_run)

    if not topics:
        print("주제 선정 실패. 종료.")
        return

    # 4. CDP 연결 + 로그인 (dry-run 제외)
    page = None
    browser = None
    pw = None
    if not dry_run:
        pw, browser, page = connect_and_ensure_login()
        if page is None:
            return

    # 5. 포스트 작성 루프
    results = []
    for idx, topic_info in enumerate(topics[:count]):
        topic = topic_info["topic"]
        print(f"\n[{idx + 1}/{len(topics[:count])}] {topic}")
        print(f"  키워드: {topic_info.get('keywords', [])}")

        post = generate_post(topic_info, dry_run=dry_run)
        if not post:
            print("  본문 생성 실패 — 건너뜀")
            results.append({"topic": topic, "ok": False, "reason": "content_gen_failed"})
            continue

        _print_post_summary(post)

        # 이미지 3장 선택/다운로드
        img_paths = _pick_images(dry_run, all_images, idx)
        print(f"  이미지: {len(img_paths)}장 — {[Path(p).name for p in img_paths]}")

        if dry_run:
            print("  [DRY-RUN] 발행 스킵")
            results.append(
                {
                    "topic": topic,
                    "title": post["title"],
                    "ok": True,
                    "dry_run": True,
                    "images": img_paths,
                    "body_len": len(post["body"]),
                }
            )
            continue

        pub = publish_one(page, post=post, img_paths=img_paths, approval=approval)
        results.append(
            {
                "topic": topic,
                "title": post["title"],
                "ok": pub["ok"],
                "log_no": pub["log_no"],
                "posted_at": datetime.now().isoformat(),
                "images": img_paths,
            }
        )

        if pub["ok"]:
            record_success(cache, topic=topic, post=post, log_no=pub["log_no"], img_paths=img_paths)

        if idx < len(topics[:count]) - 1:
            wait_between_posts(90)

    # 6. 결과 요약
    _print_run_summary(results, dry_run)

    if not dry_run and browser:
        browser.close()
        pw.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="실제 발행 없이 시뮬레이션")
    parser.add_argument("--count", type=int, default=20, help="작성할 포스트 수")
    from scripts.common.gate import CONFIRM_TEXTS, GateBlocked

    parser.add_argument("--confirm", default=None, help=f"실제 발행 승인 문구(직접 입력): {CONFIRM_TEXTS['blog_publish']}")
    args = parser.parse_args()
    try:
        run(count=args.count, dry_run=args.dry_run, approval=args.confirm)
    except GateBlocked as exc:
        raise SystemExit(f"발행 차단: {exc.result.reason} (사용자가 직접 입력한 승인 문구가 필요합니다)") from exc
