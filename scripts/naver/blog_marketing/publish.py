"""CDP 로그인 + 발행 루프 - 실제 네이버 블로그에 쓰는 유일한 지점.

정식 파이프라인(scripts/naver/blog/core/writer.py write_post)만 호출한다 —
즉석으로 편집기 단계를 새로 짜지 않는다(2026-08-14 안전 게이트 정책).

계정 감지: detect_login_state()의 표시 닉네임은 로그인 ID와 다른 문자열이라
비교해봤자 항상 불일치로 나와 매번 불필요한 재로그인을 유발했었다(2026-08-17
실측 — 정상 로그인 상태에서도 계속 계정 전환을 시도하다 엉뚱한 계정으로
이동하는 사고가 남). admin.blog.naver.com 링크에서 실제 blogId를 직접
확인하는 방식으로 교체했다.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from scripts.logger import get_logger
from scripts.naver.blog_marketing import TARGET_BLOG_ID
from scripts.naver.blog_marketing.topics import save_cache, topic_key

_log = get_logger(__name__)


def connect_and_ensure_login(cdp_url: str = "http://localhost:9222"):
    """CDP 연결 + 대상 블로그 계정(TARGET_BLOG_ID) 로그인 보장.

    Returns: (playwright, browser, page)
    """
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(cdp_url)
    page = browser.contexts[0].pages[0]
    print(f"\n[CDP] 연결됨: {page.url}")

    page.goto("https://section.blog.naver.com/BlogHome.naver", wait_until="domcontentloaded", timeout=15000)
    time.sleep(2)
    detected_blog_id = page.evaluate(
        """() => {
            const a = document.querySelector('a[href*="admin.blog.naver.com/"]');
            if (!a) return null;
            const m = a.href.match(/admin\\.blog\\.naver\\.com\\/([a-zA-Z0-9_]+)\\//);
            return m ? m[1] : null;
        }"""
    )
    print(f"[로그인] 현재 블로그 ID: {detected_blog_id}")

    if detected_blog_id != TARGET_BLOG_ID:
        print(f"  → {TARGET_BLOG_ID} 재로그인 필요 (현재: {detected_blog_id})")
        from scripts.credentials import get_naver_cred
        from scripts.naver.auth import login_naver

        cred = get_naver_cred(TARGET_BLOG_ID)
        if detected_blog_id:
            print("  → 현재 사용자 로그아웃 중...")
            page.goto(
                "https://nid.naver.com/nidlogin.logout",  # session-ok
                wait_until="domcontentloaded",
                timeout=15000,  # session-ok
            )
            time.sleep(3)
            page.goto("https://www.naver.com", wait_until="domcontentloaded", timeout=15000)
            time.sleep(2)
        r = login_naver(page, naver_id=TARGET_BLOG_ID, naver_pw=cred.get("pw", ""), force_relogin=True)
        if not r.get("ok"):
            print(f"  로그인 실패: {r}")
            browser.close()
            pw.stop()
            return pw, None, None
        time.sleep(3)

    return pw, browser, page


def publish_one(page, *, post: dict, img_paths: list[str]) -> dict:
    """포스트 1건 발행. body_segments + images로 이미지를 글 중간에 배치."""
    from scripts.naver.blog.core.writer import write_post

    segments = post.get("body_segments") or []
    try:
        result = write_post(
            page,
            title=post["title"],
            body=post["body"],
            body_segments=segments if segments else None,
            tags=post["tags"],
            images=img_paths,
            visibility="public",
            require_approval=False,
        )
        ok = result.get("ok", False)
        log_no = result.get("log_no", "")
        print(f"  발행: {'✅ 성공' if ok else '❌ 실패'} log_no={log_no}")
    except Exception as e:
        ok = False
        log_no = ""
        print(f"  발행 오류: {e}")

    return {"ok": ok, "log_no": log_no}


def edit_one(page, *, log_no: str, post: dict, img_paths: list[str]) -> dict:
    """기존 발행 글(log_no)을 새 제목/본문(AI 자동화 섹션 포함)으로 덮어쓴다."""
    from scripts.naver.blog.core.writer import edit_post

    segments = post.get("body_segments") or []
    try:
        result = edit_post(
            page,
            blog_id=TARGET_BLOG_ID,
            log_no=log_no,
            title=post["title"],
            body=post["body"],
            body_segments=segments if segments else None,
            tags=post["tags"],
            images=img_paths,
            visibility="public",
        )
        ok = result.get("ok", False)
        new_log_no = result.get("log_no", "")
        print(f"  수정 발행: {'✅ 성공' if ok else '❌ 실패'} log_no={new_log_no}")
    except Exception as e:
        ok = False
        new_log_no = ""
        print(f"  수정 오류: {e}")

    return {"ok": ok, "log_no": new_log_no}


def record_success(cache: dict, *, topic: str, post: dict, log_no: str, img_paths: list[str]) -> None:
    entry = {
        "key": topic_key(post["title"]),
        "topic": topic,
        "title": post["title"],
        "tags": post["tags"],
        "log_no": log_no,
        "posted_at": datetime.now().isoformat(),
    }
    cache.setdefault("posted", []).append(entry)
    save_cache(cache)
    print(f"  캐시 저장 ({len(cache['posted'])}개 누적)")


def wait_between_posts(seconds: int = 90) -> None:
    """포스트 간 대기 (봇 감지 방지)."""
    print(f"  다음 포스트 대기 {seconds}초...")
    time.sleep(seconds)


def existing_unsplash_fallback() -> list[dict]:
    existing = Path("data/unsplash_images.json")
    if existing.exists():
        import json

        return json.loads(existing.read_text(encoding="utf-8")).get("images", [])
    return []
